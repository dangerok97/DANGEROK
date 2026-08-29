"""
Mistral chat adapter — OpenAI-compatible API (no extra package required).

The third step of the chain. Same shape as the Groq adapter above it, because
the difference between these providers is a base URL and a model name: keeping
two adapters that look alike is the point, not an accident, since anything that
looked different here would be a place for the reasoning to start depending on
who answered.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from llm.base import BaseLLMProvider, LLMResult
from llm.errors import (
    LLMAuthenticationError,
    LLMInvalidResponseError,
    LLMModelUnavailableError,
    LLMNetworkError,
    LLMNotConfigured,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
    retry_after_seconds,
)
from llm.failures import ProviderFailure, classify_http_status

logger = logging.getLogger("ora.llm.mistral")

_MISTRAL_BASE = "https://api.mistral.ai/v1"


class MistralProvider(BaseLLMProvider):
    name = "mistral"

    def is_configured(self) -> bool:
        return bool((os.environ.get("MISTRAL_API_KEY") or "").strip())

    def model_name(self) -> Optional[str]:
        return (os.environ.get("MISTRAL_MODEL") or "mistral-small-latest").strip()

    async def chat(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResult:
        api_key = (os.environ.get("MISTRAL_API_KEY") or "").strip()
        if not api_key:
            raise LLMNotConfigured("MISTRAL_API_KEY mancante")
        model = self.model_name() or "mistral-small-latest"
        timeout_s = float(os.environ.get("MISTRAL_TIMEOUT_S") or os.environ.get("LLM_TIMEOUT_S") or "60")

        try:
            return await self._chat_openai_sdk(
                api_key=api_key,
                model=model,
                system=system,
                user=user,
                json_mode=json_mode,
                timeout_s=timeout_s,
            )
        except ImportError:
            return await self._chat_httpx(
                api_key=api_key,
                model=model,
                system=system,
                user=user,
                json_mode=json_mode,
                timeout_s=timeout_s,
            )

    async def _chat_openai_sdk(
        self,
        *,
        api_key: str,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        timeout_s: float,
    ) -> LLMResult:
        from openai import APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

        client = AsyncOpenAI(api_key=api_key, base_url=_MISTRAL_BASE, timeout=timeout_s)
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
            # When the provider says how long to wait, that is better
            # information than any default the manager could pick.
            wait = retry_after_seconds(e)
            msg = str(e).lower()
            if "quota" in msg or "billing" in msg:
                raise LLMQuotaError("quota", retry_after=wait) from e
            raise LLMRateLimitError("rate_limit", retry_after=wait) from e
        except APITimeoutError as e:
            raise LLMTimeoutError("timeout") from e
        except APIStatusError as e:
            code = getattr(e, "status_code", None)
            fail = classify_http_status(code, str(e))
            wait = retry_after_seconds(e)
            if fail == ProviderFailure.QUOTA_EXHAUSTED:
                raise LLMQuotaError("quota", retry_after=wait) from e
            if fail == ProviderFailure.RATE_LIMITED:
                raise LLMRateLimitError("rate_limit", retry_after=wait) from e
            if fail == ProviderFailure.AUTH:
                raise LLMAuthenticationError("authentication") from e
            if code == 404:
                raise LLMModelUnavailableError("model_unavailable") from e
            raise LLMNetworkError("provider_error") from e
        content = resp.choices[0].message.content if resp.choices else None
        if not content:
            raise LLMInvalidResponseError("empty")
        usage: dict[str, Any] = {"provider": self.name, "model": model}
        if getattr(resp, "usage", None):
            usage["prompt_tokens"] = getattr(resp.usage, "prompt_tokens", None)
            usage["completion_tokens"] = getattr(resp.usage, "completion_tokens", None)
        return LLMResult(text=content, provider=self.name, model=model, usage=usage)

    async def _chat_httpx(
        self,
        *,
        api_key: str,
        model: str,
        system: str,
        user: str,
        json_mode: bool,
        timeout_s: float,
    ) -> LLMResult:
        import httpx

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2 if json_mode else 0.4,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.post(
                    f"{_MISTRAL_BASE}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as e:
            raise LLMTimeoutError("timeout") from e
        except httpx.HTTPError as e:
            raise LLMNetworkError("network") from e

        if r.status_code != 200:
            fail = classify_http_status(r.status_code, r.text[:200])
            wait = None
            raw = r.headers.get("retry-after") if r.headers else None
            if raw is not None:
                try:
                    wait = min(300.0, max(0.0, float(raw)))
                except (TypeError, ValueError):
                    wait = None
            if fail == ProviderFailure.QUOTA_EXHAUSTED:
                raise LLMQuotaError("quota", retry_after=wait)
            if fail == ProviderFailure.RATE_LIMITED:
                raise LLMRateLimitError("rate_limit", retry_after=wait)
            if fail == ProviderFailure.AUTH:
                # A wrong key is a configuration problem, not a busy server: the
                # manager cools this provider for minutes rather than trying
                # it again on the next request.
                raise LLMAuthenticationError("authentication")
            if r.status_code == 404:
                raise LLMModelUnavailableError("model_unavailable")
            raise LLMNetworkError(f"http_{r.status_code}")

        data = r.json()
        choices = data.get("choices") or []
        content = None
        if choices:
            content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise LLMInvalidResponseError("empty")
        usage: dict[str, Any] = {"provider": self.name, "model": model}
        u = data.get("usage") or {}
        if u:
            usage["prompt_tokens"] = u.get("prompt_tokens")
            usage["completion_tokens"] = u.get("completion_tokens")
        return LLMResult(text=content, provider=self.name, model=model, usage=usage)
