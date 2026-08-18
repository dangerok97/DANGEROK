"""Emergent integrations adapter (optional)."""
from __future__ import annotations

import logging
import os
from typing import Optional

from llm.base import BaseLLMProvider, LLMResult
from llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMModelUnavailableError,
    LLMNetworkError,
    LLMNotConfigured,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger("ora.llm.emergent")


class EmergentProvider(BaseLLMProvider):
    name = "emergent"

    def is_configured(self) -> bool:
        return bool((os.environ.get("EMERGENT_LLM_KEY") or "").strip())

    def model_name(self) -> Optional[str]:
        return (os.environ.get("LLM_MODEL") or "gpt-5.2").strip()

    async def chat(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResult:
        api_key = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
        if not api_key:
            raise LLMNotConfigured("EMERGENT_LLM_KEY mancante")
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
        except ImportError as e:
            raise LLMConfigurationError("emergentintegrations unavailable") from e

        model = self.model_name() or "gpt-5.2"
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id or "ora",
            system_message=system
            + (" Rispondi SOLO con JSON valido." if json_mode else ""),
        ).with_model("openai", model)
        try:
            result = await chat.send_message(UserMessage(text=user))
        except Exception as e:
            msg = str(e).lower()
            if "quota" in msg or "billing" in msg or "insufficient" in msg:
                raise LLMQuotaError("quota") from e
            if "429" in msg or "rate" in msg:
                raise LLMRateLimitError("rate_limit") from e
            if "timeout" in msg or "timed out" in msg:
                raise LLMTimeoutError("timeout") from e
            if "401" in msg or "403" in msg or "auth" in msg:
                raise LLMAuthenticationError("authentication") from e
            if "404" in msg or ("model" in msg and "not found" in msg):
                raise LLMModelUnavailableError("model_unavailable") from e
            if any(marker in msg for marker in ("connection", "network", "dns", "unavailable")):
                raise LLMNetworkError("network") from e
            raise LLMInvalidResponseError("provider_protocol") from e
        text = result if isinstance(result, str) else str(result)
        if not text:
            raise LLMInvalidResponseError("empty")
        return LLMResult(text=text, provider=self.name, model=model)
