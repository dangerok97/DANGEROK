"""Emergent integrations adapter (optional)."""
from __future__ import annotations

import logging
import os
from typing import Optional

from llm.base import BaseLLMProvider, LLMResult
from llm.errors import LLMNotConfigured

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
            raise LLMNotConfigured("emergentintegrations non disponibile") from e

        model = self.model_name() or "gpt-5.2"
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id or "ora",
            system_message=system
            + (" Rispondi SOLO con JSON valido." if json_mode else ""),
        ).with_model("openai", model)
        result = await chat.send_message(UserMessage(text=user))
        text = result if isinstance(result, str) else str(result)
        if not text:
            raise RuntimeError("Risposta Emergent vuota")
        return LLMResult(text=text, provider=self.name, model=model)
