"""OpenAI chat adapter."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

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
    retry_after_seconds,
)

logger = logging.getLogger("ora.llm.openai")


_REASONING_MODEL_PREFIXES = ("gpt-5.6", "gpt-6")
_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}


def _request_generation_options(model: str, *, json_mode: bool) -> Dict[str, Any]:
    """Provider-wire compatibility; never a domain or user-intent decision."""
    options: Dict[str, Any] = {}
    if model.startswith(_REASONING_MODEL_PREFIXES):
        configured = (os.environ.get("OPENAI_REASONING_EFFORT") or "medium").strip().lower()
        options["reasoning_effort"] = (
            configured if configured in _REASONING_EFFORTS else "medium"
        )
        # Current reasoning models reject custom sampling controls whenever
        # reasoning is active. Omitting temperature is valid for every effort,
        # including "none", and keeps one stable request shape across failover.
    else:
        options["temperature"] = 0.2 if json_mode else 0.4
    if json_mode:
        options["response_format"] = {"type": "json_object"}
    return options


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
            from openai import (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                AsyncOpenAI,
                AuthenticationError,
                NotFoundError,
                RateLimitError,
            )
        except ImportError as e:
            raise LLMConfigurationError("openai package unavailable") from e

        client = AsyncOpenAI(api_key=api_key, timeout=timeout_s)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **_request_generation_options(model, json_mode=json_mode),
        }
        try:
            resp = await client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            msg = str(e).lower()
            retry_after = retry_after_seconds(e)
            if "quota" in msg or "billing" in msg or "insufficient" in msg:
                raise LLMQuotaError("quota", retry_after=retry_after) from e
            raise LLMRateLimitError("rate_limit", retry_after=retry_after) from e
        except APITimeoutError as e:
            raise LLMTimeoutError("timeout") from e
        except APIConnectionError as e:
            raise LLMNetworkError("network") from e
        except AuthenticationError as e:
            raise LLMAuthenticationError("authentication") from e
        except NotFoundError as e:
            raise LLMModelUnavailableError("model_unavailable") from e
        except APIStatusError as e:
            code = getattr(e, "status_code", None)
            msg = str(e).lower()
            retry_after = retry_after_seconds(e)
            if code == 429 and ("quota" in msg or "billing" in msg):
                raise LLMQuotaError("quota", retry_after=retry_after) from e
            if code == 429:
                raise LLMRateLimitError("rate_limit", retry_after=retry_after) from e
            if code == 402 or "quota" in msg:
                raise LLMQuotaError("quota") from e
            if code in (401, 403):
                raise LLMAuthenticationError("authentication") from e
            if code == 404:
                raise LLMModelUnavailableError("model_unavailable") from e
            if code in (500, 502, 503, 504):
                raise LLMNetworkError("provider_unavailable") from e
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
            raise LLMInvalidResponseError("empty")
        usage: dict[str, Any] = {}
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                "completion_tokens": getattr(resp.usage, "completion_tokens", None),
            }
        return LLMResult(text=content, provider=self.name, model=model, usage=usage)
