"""Ollama local HTTP adapter (OpenAI-compatible /api/chat)."""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from llm.base import BaseLLMProvider, LLMResult
from llm.errors import (
    LLMAuthenticationError,
    LLMInvalidResponseError,
    LLMModelUnavailableError,
    LLMNetworkError,
    LLMNotConfigured,
    LLMRateLimitError,
    LLMTimeoutError,
    retry_after_seconds,
)

logger = logging.getLogger("ora.llm.ollama")


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def _base_url(self) -> str:
        return (os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")

    def is_configured(self) -> bool:
        # auto (default): include in failover chain; availability via probe.
        flag = (os.environ.get("OLLAMA_ENABLED") or "auto").strip().lower()
        return flag not in ("0", "false", "no", "off")

    def model_name(self) -> Optional[str]:
        return (os.environ.get("OLLAMA_MODEL") or "llama3.2").strip()

    async def probe(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=0.8) as client:
                r = await client.get(f"{self._base_url()}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResult:
        if not await self.probe():
            raise LLMNotConfigured("Ollama non raggiungibile")
        model = self.model_name() or "llama3.2"
        timeout_s = float(os.environ.get("DOCUMENT_AI_TIMEOUT_S") or "60")
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["format"] = "json"
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.post(f"{self._base_url()}/api/chat", json=payload)
                r.raise_for_status()
                data = r.json()
        except httpx.TimeoutException as e:
            raise LLMTimeoutError("timeout") from e
        except httpx.ConnectError as e:
            raise LLMNetworkError("network") from e
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429:
                raise LLMRateLimitError(
                    "rate_limit", retry_after=retry_after_seconds(e)
                ) from e
            if code in (401, 403):
                raise LLMAuthenticationError("authentication") from e
            if code == 404:
                raise LLMModelUnavailableError("model_unavailable") from e
            if code >= 500:
                raise LLMNetworkError("provider_unavailable") from e
            raise LLMInvalidResponseError("provider_protocol") from e
        except Exception as e:
            logger.warning("Ollama error type=%s", type(e).__name__)
            raise
        msg = (data.get("message") or {}).get("content") or ""
        if not msg:
            raise LLMInvalidResponseError("empty")
        return LLMResult(text=msg, provider=self.name, model=model)
