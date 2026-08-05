"""Google Gemini adapter (official google-generativeai SDK)."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from llm.base import BaseLLMProvider, LLMResult
from llm.errors import (
    LLMNotConfigured,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger("ora.llm.gemini")


def _api_key() -> str:
    return (
        (os.environ.get("GEMINI_API_KEY") or "").strip()
        or (os.environ.get("GOOGLE_API_KEY") or "").strip()
    )


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def is_configured(self) -> bool:
        return bool(_api_key())

    def model_name(self) -> Optional[str]:
        return (
            os.environ.get("GEMINI_MODEL")
            or os.environ.get("LLM_MODEL")
            or "gemini-2.0-flash"
        ).strip()

    async def chat(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResult:
        api_key = _api_key()
        if not api_key:
            raise LLMNotConfigured("GEMINI_API_KEY mancante")
        model_name = self.model_name() or "gemini-2.0-flash"
        timeout_s = float(
            os.environ.get("DOCUMENT_AI_TIMEOUT_S")
            or os.environ.get("GEMINI_TIMEOUT_S")
            or "60"
        )
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise LLMNotConfigured(
                "Pacchetto google-generativeai non installato"
            ) from e

        genai.configure(api_key=api_key)
        generation_config: dict = {
            "temperature": 0.2 if json_mode else 0.4,
        }
        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system,
            generation_config=generation_config,
        )

        async def _call():
            if hasattr(model, "generate_content_async"):
                return await model.generate_content_async(user)
            return await asyncio.to_thread(model.generate_content, user)

        try:
            resp = await asyncio.wait_for(_call(), timeout=timeout_s)
        except asyncio.TimeoutError as e:
            raise LLMTimeoutError("timeout") from e
        except Exception as e:
            msg = str(e).lower()
            name = type(e).__name__
            if "timeout" in msg:
                raise LLMTimeoutError("timeout") from e
            if "quota" in msg or "resource_exhausted" in msg or "429" in msg:
                if "quota" in msg or "billing" in msg:
                    raise LLMQuotaError("quota") from e
                raise LLMRateLimitError("rate_limit") from e
            if "rate" in msg or name in ("ResourceExhausted",):
                raise LLMRateLimitError("rate_limit") from e
            logger.warning("Gemini error type=%s", name)
            raise

        text = ""
        try:
            text = (resp.text or "").strip()
        except Exception:
            # blocked / empty candidates
            text = ""
        if not text:
            raise RuntimeError("Risposta Gemini vuota")
        return LLMResult(
            text=text,
            provider=self.name,
            model=model_name,
            usage={"approx_tokens_in": (len(system) + len(user)) // 4, "approx_tokens_out": len(text) // 4},
        )
