"""OpenAI chat adapter."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from llm.base import BaseLLMProvider, LLMResult
from llm.errors import (
    LLMNotConfigured,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger("ora.llm.openai")


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def is_configured(self) -> bool:
        return bool((os.environ.get("OPENAI_API_KEY") or "").strip())

    def model_name(self) -> Optional[str]:
        return (os.environ.get("OPENAI_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini").strip()

    async def chat(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResult:
        api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise LLMNotConfigured("OPENAI_API_KEY mancante")
        model = self.model_name() or "gpt-4o-mini"
        timeout_s = float(
            os.environ.get("DOCUMENT_AI_TIMEOUT_S")
            or os.environ.get("OPENAI_TIMEOUT_S")
            or "60"
        )
        try:
            from openai import AsyncOpenAI, APITimeoutError, RateLimitError, APIStatusError
        except ImportError as e:
            raise LLMNotConfigured("Pacchetto openai non installato") from e

        client = AsyncOpenAI(api_key=api_key, timeout=timeout_s)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2 if json_mode else 0.4,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = await client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            msg = str(e).lower()
            if "quota" in msg or "billing" in msg or "insufficient" in msg:
                raise LLMQuotaError("quota") from e
            raise LLMRateLimitError("rate_limit") from e
        except APITimeoutError as e:
            raise LLMTimeoutError("timeout") from e
        except APIStatusError as e:
            code = getattr(e, "status_code", None)
            msg = str(e).lower()
            if code == 429 and ("quota" in msg or "billing" in msg):
                raise LLMQuotaError("quota") from e
            if code == 429:
                raise LLMRateLimitError("rate_limit") from e
            if code == 402 or "quota" in msg:
                raise LLMQuotaError("quota") from e
            logger.warning("OpenAI status=%s", code)
            raise
        except Exception as e:
            msg = str(e).lower()
            if "timeout" in msg:
                raise LLMTimeoutError("timeout") from e
            if "quota" in msg or "billing" in msg:
                raise LLMQuotaError("quota") from e
            if "rate" in msg:
                raise LLMRateLimitError("rate_limit") from e
            raise

        content = resp.choices[0].message.content if resp.choices else None
        if not content:
            raise RuntimeError("Risposta LLM vuota")
        usage: dict[str, Any] = {}
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                "completion_tokens": getattr(resp.usage, "completion_tokens", None),
            }
        return LLMResult(text=content, provider=self.name, model=model, usage=usage)
