"""Abuse and cost protection for the public API.

- ``RateLimiter``: per-key sliding-window limits (several windows at once,
  e.g. 5/minute and 40/day per IP).
- ``SpendGuard``: hard USD caps on LLM spend per UTC day and per UTC
  month, computed from the API's reported token usage. State is kept in
  memory and mirrored to a small JSON file so a restart on the same
  volume doesn't reset it. Before every LLM call the guard reserves the
  worst-case cost of that call, so concurrent requests can't overshoot
  the cap; the reservation is replaced by the real cost afterwards.

These caps are a second line of defence. The first is a spend limit set
on the Anthropic workspace that owns the key (Console > Limits).
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

# USD per million tokens (input, output). Override via LLM_PRICE_IN / LLM_PRICE_OUT.
MODEL_PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


class RateLimiter:
    def __init__(self, windows: list[tuple[int, float]]) -> None:
        """``windows`` is a list of (max_requests, window_seconds)."""
        self._windows = windows
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._longest = max(w for _, w in windows)

    def check(self, key: str, now: Optional[float] = None) -> Optional[int]:
        """Record a hit for ``key``. Returns None if allowed, or the number
        of seconds to wait if a limit is exceeded (the hit is not recorded)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self._longest:
                hits.popleft()
            for limit, window in self._windows:
                in_window = [t for t in hits if t > now - window]
                if len(in_window) >= limit:
                    return max(1, int(in_window[0] + window - now) + 1)
            hits.append(now)
            if len(self._hits) > 50_000:  # bound memory under a flood of distinct keys
                self._prune(now)
            return None

    def _prune(self, now: float) -> None:
        stale = [k for k, v in self._hits.items() if not v or v[-1] <= now - self._longest]
        for k in stale:
            del self._hits[k]


def _usage_cost(usage: Any, price_in: float, price_out: float) -> float:
    if usage is None:
        return 0.0
    inp = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25
    inp += (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.1
    out = getattr(usage, "output_tokens", 0) or 0
    return (inp * price_in + out * price_out) / 1_000_000


class SpendGuard:
    def __init__(
        self,
        daily_cap_usd: float,
        monthly_cap_usd: float,
        price_in: float,
        price_out: float,
        reserve_input_tokens: int,
        reserve_output_tokens: int,
        state_file: Optional[str] = None,
    ) -> None:
        self.daily_cap = daily_cap_usd
        self.monthly_cap = monthly_cap_usd
        self.price_in = price_in
        self.price_out = price_out
        self.reserve = (reserve_input_tokens * price_in + reserve_output_tokens * price_out) / 1_000_000
        self._state_file = state_file
        self._lock = threading.Lock()
        self._state = {"day": "", "day_usd": 0.0, "month": "", "month_usd": 0.0, "calls": 0}
        self._load()

    @staticmethod
    def _keys(now: Optional[datetime] = None) -> tuple[str, str]:
        now = now or datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")

    def _roll(self, now: Optional[datetime] = None) -> None:
        day, month = self._keys(now)
        if self._state["day"] != day:
            self._state["day"], self._state["day_usd"] = day, 0.0
        if self._state["month"] != month:
            self._state["month"], self._state["month_usd"] = month, 0.0

    def try_reserve(self, now: Optional[datetime] = None) -> bool:
        with self._lock:
            self._roll(now)
            if (
                self._state["day_usd"] + self.reserve > self.daily_cap
                or self._state["month_usd"] + self.reserve > self.monthly_cap
            ):
                return False
            self._state["day_usd"] += self.reserve
            self._state["month_usd"] += self.reserve
            return True

    def settle(self, usage: Any, now: Optional[datetime] = None) -> float:
        """Replace one reservation with the call's real cost. Returns that cost."""
        cost = _usage_cost(usage, self.price_in, self.price_out)
        with self._lock:
            self._roll(now)
            delta = cost - self.reserve
            self._state["day_usd"] = max(0.0, self._state["day_usd"] + delta)
            self._state["month_usd"] = max(0.0, self._state["month_usd"] + delta)
            self._state["calls"] += 1
            self._save()
        return cost

    def status(self) -> dict:
        with self._lock:
            self._roll()
            return {
                "day_usd": round(self._state["day_usd"], 4),
                "daily_cap_usd": self.daily_cap,
                "month_usd": round(self._state["month_usd"], 4),
                "monthly_cap_usd": self.monthly_cap,
                "llm_calls": self._state["calls"],
            }

    def _load(self) -> None:
        if not self._state_file or not os.path.exists(self._state_file):
            return
        try:
            with open(self._state_file, encoding="utf-8") as f:
                saved = json.load(f)
            for k in self._state:
                if k in saved:
                    self._state[k] = saved[k]
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        if not self._state_file:
            return
        try:
            tmp = self._state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f)
            os.replace(tmp, self._state_file)
        except OSError:
            pass
