"""
LLM provider adapter.

Configured via env (never required at process import/boot):

  LLM_PROVIDER=none|openai|emergent
  OPENAI_API_KEY=...
  OPENAI_MODEL=gpt-4o-mini
  EMERGENT_LLM_KEY=...          # only if LLM_PROVIDER=emergent

App code should call `chat_completion(...)`. Missing provider raises
LLMNotConfigured — routes map that to HTTP 503 with a clear message.
Never log API keys or full prompts.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from llm.errors import (
    LLMNotConfigured,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger("ora.llm")

# Re-export for backward compatibility
__all__ = [
    "LLMNotConfigured",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMQuotaError",
    "chat_completion",
    "llm_status",
]


def _provider_name() -> str:
    explicit = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if explicit:
        return explicit
    if (os.environ.get("EMERGENT_LLM_KEY") or "").strip():
        return "emergent"
    if (os.environ.get("OPENAI_API_KEY") or "").strip():
        return "openai"
    return "none"


def llm_status() -> Dict[str, Any]:
    name = _provider_name()
    configured = name not in ("", "none", "off", "disabled")
    model = (
        os.environ.get("OPENAI_MODEL")
        or os.environ.get("LLM_MODEL")
        or ("gpt-4o-mini" if name == "openai" else ("gpt-5.2" if name == "emergent" else None))
    )
    return {
        "provider": name if configured else "none",
        "configured": configured,
        "model": model if configured else None,
    }


async def chat_completion(
    *,
    system: str,
    user: str,
    session_id: Optional[str] = None,
    json_mode: bool = False,
) -> str:
    status = llm_status()
    if not status["configured"]:
        raise LLMNotConfigured(
            "Nessun provider LLM configurato. Imposta LLM_PROVIDER=openai "
            "e OPENAI_API_KEY, oppure LLM_PROVIDER=emergent e EMERGENT_LLM_KEY."
        )

    provider = status["provider"]
    if provider == "openai":
        return await _openai_chat(system=system, user=user, json_mode=json_mode)
    if provider == "emergent":
        return await _emergent_chat(
            system=system, user=user, session_id=session_id or "ora"
        )
    raise LLMNotConfigured(f"Provider LLM sconosciuto: {provider}")


async def _openai_chat(*, system: str, user: str, json_mode: bool = False) -> str:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise LLMNotConfigured("OPENAI_API_KEY mancante")
    model = (os.environ.get("OPENAI_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini").strip()
    timeout_s = float(os.environ.get("DOCUMENT_AI_TIMEOUT_S") or os.environ.get("OPENAI_TIMEOUT_S") or "60")

    try:
        from openai import AsyncOpenAI, APITimeoutError, RateLimitError, APIStatusError
    except ImportError as e:
        raise LLMNotConfigured(
            "Pacchetto openai non installato. Esegui: pip install openai"
        ) from e

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
        logger.warning("OpenAI rate limit")
        raise LLMRateLimitError("rate_limit") from e
    except APITimeoutError as e:
        logger.warning("OpenAI timeout")
        raise LLMTimeoutError("timeout") from e
    except APIStatusError as e:
        code = getattr(e, "status_code", None)
        if code == 429:
            raise LLMRateLimitError("rate_limit") from e
        if code == 402 or "quota" in str(e).lower():
            raise LLMQuotaError("quota") from e
        logger.warning("OpenAI APIStatusError status=%s", code)
        raise
    except Exception as e:
        msg = str(e).lower()
        if "timeout" in msg:
            raise LLMTimeoutError("timeout") from e
        if "rate" in msg:
            raise LLMRateLimitError("rate_limit") from e
        if "quota" in msg:
            raise LLMQuotaError("quota") from e
        logger.warning("OpenAI error type=%s", type(e).__name__)
        raise

    content = resp.choices[0].message.content if resp.choices else None
    if not content:
        raise RuntimeError("Risposta LLM vuota")
    return content


async def _emergent_chat(*, system: str, user: str, session_id: str) -> str:
    api_key = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
    if not api_key:
        raise LLMNotConfigured("EMERGENT_LLM_KEY mancante")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except ImportError as e:
        raise LLMNotConfigured(
            "emergentintegrations non disponibile in questo ambiente. "
            "Usa LLM_PROVIDER=openai con OPENAI_API_KEY, oppure installa "
            "il pacchetto Emergent."
        ) from e

    model = (os.environ.get("LLM_MODEL") or "gpt-5.2").strip()
    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=system,
    ).with_model("openai", model)
    result = await chat.send_message(UserMessage(text=user))
    return result if isinstance(result, str) else str(result)
