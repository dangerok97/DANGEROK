"""Bounded vision-provider transport. Never log keys, image bytes or model prose.

A provider timeout/configuration error is NOT evidence that a photo is unclear.
The transport is independent of application state for HTTP-contract tests.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time

import httpx

log = logging.getLogger("ora.vision.provider")
# This variation responded in the production trace; keep another alias as fallback.
DEFAULT_MODELS = "gemini-flash-lite-latest,gemini-flash-latest"
_BACKOFF: dict[tuple[str, str], tuple[float, str]] = {}
# Billing failures are credential-scoped; model 404 and 429 are route-scoped.
# All state is bounded and held in memory; no credentials or photos are stored.
_PREFERRED: tuple[str, str] | None = None

MESSAGES = {
    "provider_timeout": "Il servizio di riconoscimento non ha risposto in tempo. La foto non è stata giudicata poco chiara: riprova.",
    "provider_quota": "Il servizio AI ha raggiunto un limite di utilizzo. Non è un problema dell’inquadratura: riprova più tardi.",
    "provider_configuration": "Il servizio di riconoscimento non è disponibile con la configurazione attuale. Il catalogo resta consultabile.",
    "provider_unavailable": "Il servizio di riconoscimento è temporaneamente indisponibile. La fotocamera resta aperta.",
    "provider_invalid_response": "L’AI ha restituito una risposta incompleta. Riprova: non occorre cambiare inquadratura per questo errore.",
}

class VisionProviderError(RuntimeError):
    def __init__(self, code: str):
        self.code = code if code in MESSAGES else "provider_unavailable"
        super().__init__(MESSAGES[self.code])

OBSERVATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "recognized": {"type": "BOOLEAN"},
        "canonical_key": {"type": "STRING", "description": "Generic common English family in snake_case, never brand or serial."},
        "object_name": {"type": "STRING", "description": "Common Italian name."},
        "confidence": {"type": "STRING", "enum": ["high", "medium", "low"]},
        "bbox": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 4, "maxItems": 4,
                 "description": "[ymin,xmin,ymax,xmax], 0..1000; [0,0,0,0] if not localizable."},
        "safe_to_generate": {"type": "BOOLEAN"},
        "uncertainty": {"type": "STRING"},
        "body_region": {"type": "STRING", "enum": ["full_body","face","hand","arm","torso","abdomen","leg"]},
        "pose_points": {"type": "OBJECT", "properties": {
            "left_shoulder": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "right_shoulder": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "left_hip": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "right_hip": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "left_elbow": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "right_elbow": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "left_wrist": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "right_wrist": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "left_knee": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "right_knee": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "left_ankle": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
            "right_ankle": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 2, "maxItems": 2},
        }},
    },
    "required": ["recognized", "canonical_key", "object_name", "confidence", "bbox", "safe_to_generate", "uncertainty"],
}


def parse_response(body: object) -> dict:
    if not isinstance(body, dict):
        raise VisionProviderError("provider_invalid_response")
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise VisionProviderError("provider_invalid_response")
    candidate = candidates[0]
    if candidate.get("finishReason") not in (None, "STOP"):
        raise VisionProviderError("provider_invalid_response")
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise VisionProviderError("provider_invalid_response")
    text = "".join(p["text"] for p in parts if isinstance(p, dict)
                   and p.get("thought") is not True and isinstance(p.get("text"), str))
    if not text or len(text) > 100_000:
        raise VisionProviderError("provider_invalid_response")
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        raise VisionProviderError("provider_invalid_response") from None
    if not isinstance(parsed, dict):
        raise VisionProviderError("provider_invalid_response")
    return parsed


def _route(model: str, key: str) -> tuple[str, str]:
    return model, hashlib.sha256(key.encode()).hexdigest()[:16]


def _status_code(status: int) -> str:
    if status in (402, 429):
        return "provider_quota"
    if status in (400, 401, 403, 404):
        return "provider_configuration"
    return "provider_unavailable"


async def ask_gemini_json(system: str, prompt: str, image: bytes | None = None,
                   *, client: httpx.AsyncClient | None = None) -> dict:
    """At most four provider attempts; caller owns the overall phase deadline."""
    global _PREFERRED
    keys = list(dict.fromkeys(os.environ.get(k, "").strip()
                             for k in ("GEMINI_API_KEY", "GEMINI2_API_KEY") if os.environ.get(k, "").strip()))
    models = list(dict.fromkeys(x.strip() for x in os.environ.get("ORA_VISION_MODELS", DEFAULT_MODELS).split(",")
                               if re.fullmatch(r"[a-zA-Z0-9._-]+", x.strip())))[:2]
    if not keys or not models:
        raise VisionProviderError("provider_configuration")
    parts: list[dict] = [{"text": prompt}]
    if image is not None:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode("ascii")}})
    config = {"temperature": 0.1, "responseMimeType": "application/json", "maxOutputTokens": 6000}
    if "[VISION_OBSERVATION_V2]" in system:
        config.update(responseSchema=OBSERVATION_SCHEMA, maxOutputTokens=1600)
    payload = {"systemInstruction": {"parts": [{"text": system}]},
               "contents": [{"role": "user", "parts": parts}], "generationConfig": config}
    current = time.monotonic()
    for route in list(_BACKOFF):
        if _BACKOFF[route][0] <= current:
            _BACKOFF.pop(route, None)
    candidates = [(m,k) for m in models for k in keys[:2]]
    candidates.sort(key=lambda mk: _route(*mk) != _PREFERRED)
    failures: list[str] = []
    owned = client is None
    # Observation has an 11s caller deadline; generation keeps its separate 24s budget.
    session = client or httpx.AsyncClient(timeout=httpx.Timeout(16, connect=4))
    try:
        for model, key in candidates[:4]:
            route = _route(model, key)
            key_block = ("*", route[1])
            blocked = _BACKOFF.get(key_block) or _BACKOFF.get(route)
            if blocked:
                failures.append(blocked[1]); continue
            try:
                response = await session.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent",
                    headers={"x-goog-api-key": key}, json=payload)
                if response.status_code != 200:
                    code = _status_code(response.status_code)
                    seconds = 600 if response.status_code == 402 else 90 if response.status_code == 429 else 300 if code == "provider_configuration" else 15
                    blocked_route = ("*", route[1]) if response.status_code in (401, 402) else route
                    _BACKOFF[blocked_route] = (time.monotonic() + seconds, code)
                    if len(_BACKOFF) > 40:
                        _BACKOFF.clear()
                    failures.append(code)
                    log.warning("vision_provider status=%s model=%s code=%s", response.status_code, model, code)
                    continue
                try:
                    body = response.json()
                except ValueError:
                    raise VisionProviderError("provider_invalid_response") from None
                result = parse_response(body)
                _PREFERRED = route
                return result
            except asyncio.CancelledError:
                # Do not send the second phase straight back to its just-expired route.
                _BACKOFF[route] = (time.monotonic() + 5, "provider_timeout")
                raise
            except (httpx.TimeoutException, asyncio.TimeoutError):
                _BACKOFF[route] = (time.monotonic() + 5, "provider_timeout")
                failures.append("provider_timeout")
                log.warning("vision_provider model=%s code=provider_timeout", model)
            except httpx.HTTPError:
                failures.append("provider_unavailable")
                log.warning("vision_provider model=%s code=provider_unavailable", model)
            except VisionProviderError as exc:
                failures.append(exc.code)
                log.warning("vision_provider model=%s code=%s", model, exc.code)
    finally:
        if owned:
            await session.aclose()
    for code in ("provider_quota", "provider_configuration", "provider_invalid_response", "provider_timeout", "provider_unavailable"):
        if code in failures:
            raise VisionProviderError(code)
    raise VisionProviderError("provider_unavailable")

# A second provider is tried only after all healthy Gemini routes fail.
# Fallback state never contains an image, key, prompt, name or user identifier.
_FALLBACK_COOLDOWN: dict[str, tuple[float, str]] = {}


async def ask_json(system: str, prompt: str, image: bytes | None = None,
                   *, client: httpx.AsyncClient | None = None) -> dict:
    from vision_openai_fallback import ask_openai, configured
    gemini_error = None
    if any(os.environ.get(k, "").strip() for k in ("GEMINI_API_KEY", "GEMINI2_API_KEY")):
        try:
            return await ask_gemini_json(system, prompt, image, client=client)
        except VisionProviderError as exc:
            gemini_error = exc
    if not configured():
        raise gemini_error or VisionProviderError("provider_configuration")
    key_hash = hashlib.sha256(os.environ["OPENAI_API_KEY"].strip().encode()).hexdigest()[:16]
    block = _FALLBACK_COOLDOWN.get(key_hash)
    if block and block[0] > time.monotonic():
        raise VisionProviderError(block[1])
    try:
        # The image is sent only on explicit foreground scan and no data is stored.
        # Do not reuse a mocked Gemini client for the OpenAI domain in production.
        result = await ask_openai(system, prompt, image)
        _FALLBACK_COOLDOWN.pop(key_hash, None)
        log.info("vision_provider fallback=success provider=openai")
        return result
    except VisionProviderError as exc:
        seconds = 300 if exc.code in ("provider_quota", "provider_configuration") else 15
        _FALLBACK_COOLDOWN[key_hash] = (time.monotonic() + seconds, exc.code)
        if len(_FALLBACK_COOLDOWN) > 24:
            _FALLBACK_COOLDOWN.clear()
        log.warning("vision_provider fallback=failure provider=openai code=%s", exc.code)
        raise
