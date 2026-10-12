"""Optional second provider for ORA Vision, only after Gemini paths fail.

OpenAI is invoked only with an existing configured API key and a bounded
single request. Never logs images, messages, API keys, raw responses or users.
No image is persisted here. Distinguishes provider failure from negative sight.
"""
from __future__ import annotations
import asyncio
import base64
import json
import os
import re

import httpx

_MODEL = "gpt-4o-mini"


def configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


async def ask_openai(system: str, prompt: str, image: bytes | None = None,
                     *, client: httpx.AsyncClient | None = None) -> dict:
    from vision_provider import VisionProviderError
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise VisionProviderError("provider_configuration")
    model = os.environ.get("ORA_VISION_OPENAI_MODEL", _MODEL).strip()
    if not re.fullmatch(r"[a-zA-Z0-9._-]{3,80}", model):
        raise VisionProviderError("provider_configuration")
    contents: list[dict] = [{"type": "text", "text": prompt}]
    if image is not None:
        contents.append({"type": "image_url", "image_url": {
            "url": "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii"),
            "detail": "low"}})
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system +
                      "\nRestituisci esclusivamente JSON valido, senza markdown."},
                     {"role": "user", "content": contents}],
        "response_format": {"type": "json_object"},
        "max_tokens": 2400 if image is not None else 6000,
        "store": False,
    }
    own = client is None
    session = client or httpx.AsyncClient(timeout=httpx.Timeout(11, connect=4))
    try:
        response = await asyncio.wait_for(
            session.post("https://api.openai.com/v1/chat/completions",
                         headers={"Authorization": "Bearer " + key},
                         json=payload), timeout=12)
        if response.status_code in (402, 429):
            raise VisionProviderError("provider_quota")
        if response.status_code in (400, 401, 403, 404):
            raise VisionProviderError("provider_configuration")
        if response.status_code != 200:
            raise VisionProviderError("provider_unavailable")
        try:
            envelope = response.json()
            choices = envelope.get("choices", [])
            first = choices[0]
            if first.get("finish_reason") != "stop":
                raise ValueError("incomplete")
            raw = first["message"]["content"]
            if not isinstance(raw, str) or len(raw) > 100000:
                raise ValueError("invalid")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("not object")
            return value
        except (ValueError, KeyError, IndexError, TypeError):
            raise VisionProviderError("provider_invalid_response") from None
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise VisionProviderError("provider_timeout") from None
    except httpx.HTTPError:
        raise VisionProviderError("provider_unavailable") from None
    finally:
        if own:
            await session.aclose()
