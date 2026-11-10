"""Public HTTP API for the EU MDR classifier (deployed on Railway).

Two endpoints do the work:

- ``POST /classify`` - free-text description (plus optional image). An
  LLM extracts ``DeviceAttributes`` only; the deterministic rules engine
  classifies. If the LLM is unavailable, over its spend cap, or this IP
  has used its LLM quota, the request falls back to the deterministic
  keyword extractor and says so in the response - it never fails just
  because the LLM is off.
- ``POST /classify/attributes`` - structured attributes, no LLM at all.

Protection for public use: per-IP rate limits, a separate per-IP and
global quota on LLM-backed requests, hard daily/monthly USD caps on LLM
spend, request-size and input-length limits, and CORS restricted to the
portfolio origin. The API key only ever comes from the environment.

Configuration (environment variables, all optional except the key for LLM mode):
  ANTHROPIC_API_KEY        enables LLM extraction
  LLM_MODEL                default claude-opus-5-5
  LLM_DAILY_CAP_USD        default 0.50
  LLM_MONTHLY_CAP_USD      default 3.00
  LLM_PER_IP_PER_DAY       default 15
  LLM_GLOBAL_PER_DAY       default 150
  ALLOWED_ORIGINS          comma-separated, default https://samlukaitis.github.io
  SPEND_STATE_FILE         default /data/spend.json if /data exists, else none
  TRUST_PROXY_HEADERS      default 1 (use X-Real-IP / X-Forwarded-For from Railway's edge)
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
from typing import Any, Literal, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.limits import MODEL_PRICES, RateLimiter, SpendGuard
from api.llm_extractor import ExtractionFailed, LLMExtractor
from cli import DISCLAIMER, _result_to_dict, device_attributes_from_dict
from extraction import KeywordExtractor
from regulatory_pathway import build_pathway
from rules_engine.eu_mdr import EUMDRClassificationEngine
from rules_engine.sensitivity import class_drivers
from standards_mapper.eu_mdr import EUMDRStandardsMapper

log = logging.getLogger("mdr_api")
logging.basicConfig(level=logging.INFO)

MAX_DESCRIPTION_CHARS = 2000
MAX_IMAGE_B64_CHARS = 1_500_000  # ~1.1 MB decoded
MAX_BODY_BYTES = 1_700_000
IMAGE_MAGIC = {
    "image/png": b"\x89PNG",
    "image/jpeg": b"\xff\xd8\xff",
    "image/webp": b"RIFF",
    "image/gif": b"GIF8",
}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


MODEL = os.environ.get("LLM_MODEL", "claude-opus-5-5")
_default_prices = MODEL_PRICES.get(MODEL, (5.0, 25.0))
PRICE_IN = _env_float("LLM_PRICE_IN", _default_prices[0])
PRICE_OUT = _env_float("LLM_PRICE_OUT", _default_prices[1])
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 8000)
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "https://samlukaitis.github.io").split(",") if o.strip()
]
TRUST_PROXY = os.environ.get("TRUST_PROXY_HEADERS", "1") == "1"
_state_default = "/data/spend.json" if os.path.isdir("/data") else None
STATE_FILE = os.environ.get("SPEND_STATE_FILE", _state_default)

engine = EUMDRClassificationEngine()
mapper = EUMDRStandardsMapper()
keyword_extractor = KeywordExtractor()

request_limiter = RateLimiter([(8, 60), (120, 86_400)])
llm_ip_limiter = RateLimiter([(3, 60), (_env_int("LLM_PER_IP_PER_DAY", 15), 86_400)])
llm_global_limiter = RateLimiter([(_env_int("LLM_GLOBAL_PER_DAY", 150), 86_400)])
spend = SpendGuard(
    daily_cap_usd=_env_float("LLM_DAILY_CAP_USD", 0.50),
    monthly_cap_usd=_env_float("LLM_MONTHLY_CAP_USD", 3.00),
    price_in=PRICE_IN,
    price_out=PRICE_OUT,
    # Worst case for one call: description + schema + image, and max_tokens of output.
    reserve_input_tokens=8_000,
    reserve_output_tokens=LLM_MAX_TOKENS,
    state_file=STATE_FILE,
)


def _make_llm() -> Optional[LLMExtractor]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    client = anthropic.Anthropic(timeout=60.0, max_retries=1)
    return LLMExtractor(client, MODEL, max_tokens=LLM_MAX_TOKENS)


llm = _make_llm()

app = FastAPI(
    title="EU MDR device classifier",
    description="Educational demo. Not regulatory advice. " + DISCLAIMER,
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=3600,
)


def client_ip(request: Request) -> str:
    if TRUST_PROXY:
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            # The proxy appends the address it saw last; earlier entries are client-supplied.
            return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.method == "POST":
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse({"error": "Content-Length required."}, status_code=411)
        try:
            if int(length) > MAX_BODY_BYTES:
                return JSONResponse({"error": "Request too large."}, status_code=413)
        except ValueError:
            return JSONResponse({"error": "Bad Content-Length."}, status_code=400)
        wait = request_limiter.check(client_ip(request))
        if wait is not None:
            return JSONResponse(
                {"error": f"Too many requests. Try again in {wait}s."},
                status_code=429,
                headers={"Retry-After": str(wait)},
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


class ImageIn(BaseModel):
    media_type: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    data: str = Field(..., max_length=MAX_IMAGE_B64_CHARS)


class ClassifyIn(BaseModel):
    description: str = Field(..., min_length=10, max_length=MAX_DESCRIPTION_CHARS)
    image: Optional[ImageIn] = None
    use_llm: bool = True


class AttributesIn(BaseModel):
    attributes: dict[str, Any]


def _validate_image(image: ImageIn) -> tuple[str, str]:
    try:
        raw = base64.b64decode(image.data, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Image data is not valid base64.")
    if not raw.startswith(IMAGE_MAGIC[image.media_type]):
        raise ValueError("Image content does not match its media type.")
    return image.media_type, image.data


def _payload(device, extraction, extractor: str, fallback_reason: Optional[str]) -> dict:
    result = engine.classify(device)
    standards = mapper.map(device, result)
    out = _result_to_dict(device, result, extraction, standards)
    out["regulatory_pathway"] = [vars(item) for item in build_pathway(device, result)]
    out["class_drivers"] = [vars(d) for d in class_drivers(device, engine)]
    out["extractor"] = extractor
    out["fallback_reason"] = fallback_reason
    out["attributes"] = {
        k: (v.value if hasattr(v, "value") else v) for k, v in vars(device).items() if k != "description"
    }
    return out


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm_enabled": llm is not None, "model": MODEL if llm else None}


@app.post("/classify")
def classify(body: ClassifyIn, request: Request):
    image = None
    if body.image is not None:
        try:
            image = _validate_image(body.image)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    ip = client_ip(request)
    fallback_reason = None
    if not body.use_llm:
        fallback_reason = "LLM not requested."
    elif llm is None:
        fallback_reason = "LLM extraction is not configured on this server."
    elif llm_ip_limiter.check(ip) is not None:
        fallback_reason = "You've used this IP's LLM quota for now."
    elif llm_global_limiter.check("global") is not None:
        fallback_reason = "The demo's daily LLM quota is used up."
    elif not spend.try_reserve():
        fallback_reason = "The demo's LLM spend cap has been reached."
    else:
        try:
            extraction, usage = llm.extract_with_usage(body.description, image)
            cost = spend.settle(usage)
            log.info("llm ok cost=$%.5f status=%s", cost, spend.status())
            return _payload(extraction.device, extraction, "llm", None)
        except ExtractionFailed as exc:
            spend.settle(exc.usage)
            log.warning("llm extraction failed: %s", exc)
            fallback_reason = "LLM extraction failed; used the keyword extractor."
        except Exception as exc:  # network/API errors: never surface details, never fail the request
            spend.settle(None)
            log.warning("llm call error: %s", type(exc).__name__)
            fallback_reason = "LLM service unavailable; used the keyword extractor."

    extraction = keyword_extractor.extract(body.description)
    if image is not None:
        extraction.unmatched_notes.append("The image was not used (keyword mode reads text only).")
    return _payload(extraction.device, extraction, "keyword", fallback_reason)


@app.post("/classify/attributes")
def classify_attributes(body: AttributesIn):
    if len(body.attributes) > 80:
        return JSONResponse({"error": "Too many attributes."}, status_code=422)
    attrs = {k: v for k, v in body.attributes.items() if k != "description"}
    if isinstance(attrs.get("name"), str):
        attrs["name"] = attrs["name"][:200]
    try:
        device = device_attributes_from_dict(attrs)
    except (ValueError, TypeError) as exc:
        return JSONResponse({"error": str(exc)[:300]}, status_code=422)
    return _payload(device, None, "none", None)
