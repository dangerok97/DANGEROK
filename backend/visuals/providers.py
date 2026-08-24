"""Image generation providers — capability-verified, never assumed.

ORA is not a Gemini product. A provider that can hold a conversation is not
therefore able to make a picture, so this layer keeps the two capabilities
separate and asks each provider whether it can actually do this one.

The chain is ordered and every link is optional: whichever image-capable
provider is configured and healthy answers, and if none is, the caller gets a
typed refusal rather than a fabricated result. ORA never pretends to have
generated an image.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

logger = logging.getLogger("ora.visuals.providers")

# Bounded so one slow provider cannot hold a background worker forever.
IMAGE_TIMEOUT_S = float(os.environ.get("IMAGE_GEN_TIMEOUT_S", "90"))


class NoImageProviderAvailable(RuntimeError):
    """No configured provider can generate an image right now.

    Carries the reason per provider so the operator learns *which* credential
    or quota is missing instead of seeing a generic failure.
    """

    def __init__(self, reasons: dict[str, str]):
        self.reasons = reasons
        detail = "; ".join(f"{k}: {v}" for k, v in reasons.items()) or "none configured"
        super().__init__(f"no image-capable provider available ({detail})")


@dataclass
class ImageResult:
    content: bytes
    mime_type: str
    provider: str
    model: str


class ImageProvider(Protocol):
    name: str

    def configured(self) -> bool: ...

    async def generate(self, *, prompt: str, aspect: str) -> ImageResult: ...


# --- Gemini -------------------------------------------------------------------

class GeminiImageProvider:
    """Google image models via the `google-genai` client."""

    name = "gemini"

    # Cheapest capable model first, then up. Overridable end-to-end with
    # GEMINI_IMAGE_MODELS so the order is an operations decision, not a code one.
    DEFAULT_MODELS = (
        "models/gemini-3.1-flash-lite-image",
        "models/gemini-3.1-flash-image",
        "models/gemini-2.5-flash-image",
    )

    def __init__(self) -> None:
        configured = (os.environ.get("GEMINI_IMAGE_MODELS") or "").strip()
        self._models = tuple(
            m.strip() for m in configured.split(",") if m.strip()
        ) or self.DEFAULT_MODELS

    def configured(self) -> bool:
        return bool((os.environ.get("GEMINI_API_KEY") or "").strip())

    async def generate(self, *, prompt: str, aspect: str) -> ImageResult:
        import asyncio

        from google import genai

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        last: Exception | None = None

        # A model can be rate-limited while the next one is not; that is a
        # reason to step up, not to fail the whole provider.
        for model in self._models:
            def _call(m=model):
                return client.models.generate_content(model=m, contents=prompt)

            try:
                resp = await asyncio.wait_for(asyncio.to_thread(_call), timeout=IMAGE_TIMEOUT_S)
            except Exception as exc:
                last = exc
                logger.info("gemini image model %s unavailable: %s", model, type(exc).__name__)
                continue

            for cand in (resp.candidates or []):
                for part in (getattr(cand.content, "parts", None) or []):
                    inline = getattr(part, "inline_data", None)
                    data = getattr(inline, "data", None)
                    if not data:
                        continue
                    content = data if isinstance(data, (bytes, bytearray)) else base64.b64decode(data)
                    return ImageResult(
                        content=bytes(content),
                        mime_type=getattr(inline, "mime_type", None) or "image/png",
                        provider=self.name,
                        model=model,
                    )
            last = RuntimeError(f"{model} returned no image part")

        raise last or RuntimeError("gemini produced no image")


# --- OpenAI -------------------------------------------------------------------

class OpenAIImageProvider:
    """OpenAI image models. Returns either base64 or a short-lived URL; both
    are materialised into bytes here, because a provider URL that expires is
    not a durable source of truth."""

    name = "openai"

    def __init__(self) -> None:
        self._model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")

    def configured(self) -> bool:
        return bool((os.environ.get("OPENAI_API_KEY") or "").strip())

    async def generate(self, *, prompt: str, aspect: str) -> ImageResult:
        import asyncio

        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        size = "1024x1024" if aspect in ("1:1", "square") else "1536x1024"

        def _call():
            return client.images.generate(model=self._model, prompt=prompt, n=1, size=size)

        resp = await asyncio.wait_for(asyncio.to_thread(_call), timeout=IMAGE_TIMEOUT_S)
        item = resp.data[0]
        b64 = getattr(item, "b64_json", None)
        if b64:
            return ImageResult(
                content=base64.b64decode(b64), mime_type="image/png",
                provider=self.name, model=self._model,
            )
        url = getattr(item, "url", None)
        if url:
            import httpx

            async with httpx.AsyncClient(timeout=IMAGE_TIMEOUT_S) as http:
                r = await http.get(url)
                r.raise_for_status()
                return ImageResult(
                    content=r.content,
                    mime_type=r.headers.get("content-type", "image/png"),
                    provider=self.name, model=self._model,
                )
        raise RuntimeError("openai returned no image payload")


# --- manager ------------------------------------------------------------------

def _default_chain() -> list[ImageProvider]:
    order = [p.strip() for p in (os.environ.get("IMAGE_PROVIDER_PRIORITY") or "gemini,openai").split(",") if p.strip()]
    known: dict[str, ImageProvider] = {
        "gemini": GeminiImageProvider(),
        "openai": OpenAIImageProvider(),
    }
    return [known[n] for n in order if n in known]


class ImageProviderManager:
    """Try each configured image provider in order; first success wins.

    Deliberately separate from the text `ProviderManager`: the failure modes do
    not overlap. A vendor whose chat quota is intact can still refuse to make a
    picture, and one whose image billing is capped should not take the rest of
    the product down with it.
    """

    def __init__(self, providers: Optional[list[ImageProvider]] = None):
        self.providers = providers if providers is not None else _default_chain()

    def available(self) -> list[str]:
        return [p.name for p in self.providers if p.configured()]

    async def generate(self, *, prompt: str, aspect: str = "4:3") -> ImageResult:
        reasons: dict[str, str] = {}
        for provider in self.providers:
            if not provider.configured():
                reasons[provider.name] = "not configured"
                continue
            try:
                result = await provider.generate(prompt=prompt, aspect=aspect)
                if not result.content:
                    raise RuntimeError("empty image")
                logger.info("image generated provider=%s model=%s bytes=%s",
                            result.provider, result.model, len(result.content))
                return result
            except Exception as exc:
                # The message can name a quota or a billing cap, which is
                # exactly what an operator needs; it never contains user data.
                reasons[provider.name] = f"{type(exc).__name__}: {str(exc)[:160]}"
                logger.warning("image provider %s failed: %s", provider.name, reasons[provider.name])
        raise NoImageProviderAvailable(reasons)


__all__ = [
    "ImageProviderManager",
    "ImageProvider",
    "ImageResult",
    "NoImageProviderAvailable",
    "GeminiImageProvider",
    "OpenAIImageProvider",
]
