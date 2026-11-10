"""Tests for the public HTTP API (api/main.py) and its protections.

The Claude client is replaced by a fake throughout - these tests never
call the real API or spend money.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import api.main as main  # noqa: E402
from api.limits import RateLimiter, SpendGuard  # noqa: E402
from api.llm_extractor import (  # noqa: E402
    LLMExtractor,
    attribute_fields,
    build_output_schema,
    device_from_llm_attributes,
)
from rules_engine.models import ActiveDeviceType, DeviceClass, Invasiveness  # noqa: E402

ORIGIN = "https://samlukaitis.github.io"


class FakeMessages:
    def __init__(self, payload, stop_reason="end_turn", usage=(1500, 400)):
        self.payload = payload
        self.stop_reason = stop_reason
        self.usage = SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1])
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            usage=self.usage,
            content=[SimpleNamespace(type="text", text=text)],
        )


def _llm_payload(**attrs):
    return {
        "device_name": "Test device",
        "attributes": attrs,
        "evidence": [{"field": k, "reason": "stated"} for k in attrs],
        "uncertain": [],
    }


HIP = dict(invasiveness="surgically_invasive", duration="long_term", is_implantable=True, is_joint_replacement=True)


@pytest.fixture
def fresh(monkeypatch):
    """Reset all module-level limiters/guards and install a fake LLM."""
    monkeypatch.setattr(main, "request_limiter", RateLimiter([(1000, 60)]))
    monkeypatch.setattr(main, "llm_ip_limiter", RateLimiter([(1000, 60)]))
    monkeypatch.setattr(main, "llm_global_limiter", RateLimiter([(1000, 60)]))
    monkeypatch.setattr(main, "spend", SpendGuard(1.0, 5.0, 4.0, 20.0, 8000, 8000))
    fake = FakeMessages(_llm_payload(**HIP))
    monkeypatch.setattr(main, "llm", LLMExtractor(SimpleNamespace(messages=fake), "claude-opus-5-5"))
    return fake


@pytest.fixture
def client():
    return TestClient(main.app)


# --- schema / extractor -------------------------------------------------


def test_schema_covers_every_engine_field_and_no_class_output():
    schema = build_output_schema()
    props = schema["properties"]["attributes"]["properties"]
    assert set(props) == {name for name, _ in attribute_fields()}
    assert len(props) >= 60
    # The LLM is never given a field for the final classification.
    assert "device_class" not in schema["properties"]
    assert "predicted_class" not in schema["properties"]


def test_invalid_llm_values_fall_back_to_defaults():
    device = device_from_llm_attributes(
        {"invasiveness": "very_invasive", "is_implantable": "yes", "unknown_field": True, "duration": "long_term"}
    )
    assert device.invasiveness == Invasiveness.NON_INVASIVE
    assert device.is_implantable is False
    assert device.duration.value == "long_term"


def test_active_type_forces_is_active():
    device = device_from_llm_attributes({"active_type": "other_active", "is_active": False})
    assert device.active_type == ActiveDeviceType.OTHER_ACTIVE
    assert device.is_active is True


def test_optional_class_field_accepts_null_and_value():
    device = device_from_llm_attributes({"drives_or_influences_device_class": "IIb"})
    assert device.drives_or_influences_device_class == DeviceClass.IIB
    device = device_from_llm_attributes({"drives_or_influences_device_class": None})
    assert device.drives_or_influences_device_class is None


# --- endpoints ------------------------------------------------------------


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_llm_path_classifies_with_rules_engine(fresh, client):
    r = client.post("/classify", json={"description": "Total hip replacement implant, metal on polyethylene."})
    body = r.json()
    assert r.status_code == 200
    assert body["extractor"] == "llm"
    assert body["predicted_class"] == "III"
    assert any(t["rule_id"] == "Rule 8" for t in body["triggered_rules"])
    ids = {s["standard_id"] for req in body["standards_mapping"]["applicable_requirements"] for s in req["standards"]}
    assert {"ISO 13485", "ISO 14971", "ISO 10993-1"} <= ids
    # The description is passed as delimited data and the call uses structured outputs.
    call = fresh.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "<description>" in call["messages"][0]["content"][-1]["text"]


def test_llm_output_cannot_inject_a_class(monkeypatch, fresh, client):
    payload = _llm_payload(**HIP)
    payload["predicted_class"] = "I"
    payload["attributes"]["device_class"] = "I"
    fresh.payload = payload
    body = client.post("/classify", json={"description": "Total hip replacement implant."}).json()
    assert body["predicted_class"] == "III"


def test_no_llm_configured_falls_back_to_keyword(monkeypatch, fresh, client):
    monkeypatch.setattr(main, "llm", None)
    body = client.post("/classify", json={"description": "A sterile single-use hypodermic syringe."}).json()
    assert body["extractor"] == "keyword"
    assert "not configured" in body["fallback_reason"]
    assert body["predicted_class"] is not None


def test_spend_cap_falls_back_without_calling_llm(monkeypatch, fresh, client):
    monkeypatch.setattr(main, "spend", SpendGuard(0.0001, 5.0, 4.0, 20.0, 8000, 8000))
    body = client.post("/classify", json={"description": "Total hip replacement implant."}).json()
    assert body["extractor"] == "keyword"
    assert "spend cap" in body["fallback_reason"]
    assert fresh.calls == []


def test_per_ip_llm_quota(monkeypatch, fresh, client):
    monkeypatch.setattr(main, "llm_ip_limiter", RateLimiter([(1, 60)]))
    first = client.post("/classify", json={"description": "Total hip replacement implant."}).json()
    second = client.post("/classify", json={"description": "Total hip replacement implant."}).json()
    assert first["extractor"] == "llm"
    assert second["extractor"] == "keyword"
    assert len(fresh.calls) == 1


def test_llm_refusal_or_bad_json_falls_back(fresh, client):
    fresh.stop_reason = "refusal"
    body = client.post("/classify", json={"description": "Total hip replacement implant."}).json()
    assert body["extractor"] == "keyword"
    fresh.stop_reason = "end_turn"
    fresh.payload = "not json"
    body = client.post("/classify", json={"description": "Total hip replacement implant."}).json()
    assert body["extractor"] == "keyword"


def test_llm_exception_falls_back_and_releases_reservation(monkeypatch, fresh, client):
    def boom(**kwargs):
        raise RuntimeError("network down")

    fresh.create = boom
    body = client.post("/classify", json={"description": "Total hip replacement implant."}).json()
    assert body["extractor"] == "keyword"
    assert main.spend.status()["day_usd"] == 0


def test_request_rate_limit(monkeypatch, client):
    monkeypatch.setattr(main, "request_limiter", RateLimiter([(2, 60)]))
    codes = [
        client.post("/classify/attributes", json={"attributes": {}}).status_code for _ in range(3)
    ]
    assert codes == [200, 200, 429]


def test_description_length_limits(fresh, client):
    assert client.post("/classify", json={"description": "x" * 2001}).status_code == 422
    assert client.post("/classify", json={"description": "short"}).status_code == 422


def test_body_size_limit(fresh, client):
    big = "A" * (main.MAX_BODY_BYTES + 10)
    r = client.post("/classify", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_image_validation(fresh, client):
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 50).decode()
    ok = client.post(
        "/classify",
        json={"description": "Total hip replacement implant.", "image": {"media_type": "image/png", "data": png}},
    )
    assert ok.status_code == 200
    assert fresh.calls[-1]["messages"][0]["content"][0]["type"] == "image"
    mismatched = client.post(
        "/classify",
        json={"description": "Total hip replacement implant.", "image": {"media_type": "image/jpeg", "data": png}},
    )
    assert mismatched.status_code == 422
    svg = client.post(
        "/classify",
        json={"description": "Total hip replacement implant.", "image": {"media_type": "image/svg+xml", "data": png}},
    )
    assert svg.status_code == 422


def test_attributes_endpoint(client, fresh):
    r = client.post("/classify/attributes", json={"attributes": HIP})
    assert r.status_code == 200
    assert r.json()["predicted_class"] == "III"
    assert r.json()["extractor"] == "none"
    bad = client.post("/classify/attributes", json={"attributes": {"nope": 1}})
    assert bad.status_code == 422


def test_cors_allows_only_portfolio_origin(client):
    ok = client.options(
        "/classify", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"}
    )
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    evil = client.options(
        "/classify", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert evil.headers.get("access-control-allow-origin") is None


def test_client_ip_uses_last_forwarded_hop(monkeypatch):
    req = SimpleNamespace(headers={"x-forwarded-for": "1.1.1.1, 9.9.9.9"}, client=SimpleNamespace(host="10.0.0.1"))
    assert main.client_ip(req) == "9.9.9.9"
    req = SimpleNamespace(headers={"x-real-ip": "8.8.8.8"}, client=None)
    assert main.client_ip(req) == "8.8.8.8"


# --- limits -----------------------------------------------------------------


def test_rate_limiter_windows():
    rl = RateLimiter([(2, 10), (3, 100)])
    assert rl.check("a", now=0) is None
    assert rl.check("a", now=1) is None
    assert rl.check("a", now=2) is not None  # 2 per 10s
    assert rl.check("a", now=11) is None
    assert rl.check("a", now=50) is not None  # 3 per 100s
    assert rl.check("b", now=50) is None


def test_spend_guard_caps_and_rolls_over(tmp_path):
    state = tmp_path / "spend.json"
    g = SpendGuard(0.10, 0.15, 4.0, 20.0, 1000, 1000, state_file=str(state))
    day1 = datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert g.try_reserve(day1)  # reserve = 0.024
    g.settle(SimpleNamespace(input_tokens=2000, output_tokens=4000), day1)  # 0.088
    assert not g.try_reserve(day1)  # 0.088 + 0.024 > 0.10
    day2 = datetime(2026, 11, 11, tzinfo=timezone.utc)
    assert g.try_reserve(day2)
    g.settle(SimpleNamespace(input_tokens=1000, output_tokens=1000), day2)  # 0.024, month 0.112
    assert g.try_reserve(day2)  # day 0.048, month 0.136
    assert not g.try_reserve(day2)  # month would pass its 0.15 cap
    g2 =SpendGuard(0.10, 0.15, 4.0, 20.0, 1000, 1000, state_file=str(state))  # reload from disk
    assert g2._state["month_usd"] > 0.1
