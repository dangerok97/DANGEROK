"""Google Gemini adapter (official google-genai SDK)."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

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

logger = logging.getLogger("ora.llm.gemini")

# Secondary model after configured GEMINI_MODEL (then Provider Manager failover).
_DEFAULT_ALTERNATE = "gemini-2.0-flash"


def _api_key() -> str:
    """GEMINI_API_KEY only (no ADC / Vertex implicit auth)."""
    return (os.environ.get("GEMINI_API_KEY") or "").strip()


def _model_candidates(primary: str) -> list[str]:
    alt = (
        os.environ.get("GEMINI_FALLBACK_MODEL") or _DEFAULT_ALTERNATE
    ).strip()
    out: list[str] = []
    for m in (primary, alt):
        if m and m not in out:
            out.append(m)
    return out


def _map_api_error(exc: BaseException) -> BaseException:
    """Map google.genai errors → typed LLM errors (no secrets in messages)."""
    code = getattr(exc, "code", None)
    status = (getattr(exc, "status", None) or "").lower()
    msg = str(exc).lower()
    name = type(exc).__name__
    retry_after = retry_after_seconds(exc)

    if isinstance(exc, asyncio.TimeoutError) or "timeout" in msg or "timed out" in msg:
        return LLMTimeoutError("timeout")

    # Auth
    if code in (401, 403) or "unauthenticated" in msg or "permission_denied" in status:
        return LLMAuthenticationError("authentication")

    # Quota / rate
    if code == 429 or "resource_exhausted" in msg or "resource_exhausted" in status:
        if "quota" in msg or "billing" in msg or "exceeded" in msg:
            return LLMQuotaError("quota", retry_after=retry_after)
        return LLMRateLimitError("rate_limit", retry_after=retry_after)
    if "quota" in msg or "billing" in msg:
        return LLMQuotaError("quota")
    if "rate" in msg or name == "ResourceExhausted":
        return LLMRateLimitError("rate_limit")

    # Model unavailable
    if code == 404 or "not_found" in status or "not found" in msg or "is not found" in msg:
        return LLMModelUnavailableError("model_unavailable")

    # Safety / blocked
    if "blocked" in msg or "safety" in msg or "prohibit" in msg:
        return LLMInvalidResponseError("blocked")

    # Invalid request (permanent-ish client error)
    if code in (400, 422) or "invalid" in msg or "invalid_argument" in status:
        return LLMInvalidResponseError("invalid")

    # Transient server
    if code in (500, 502, 503, 504) or "unavailable" in status or "internal" in status:
        return LLMNetworkError("provider_unavailable")

    if (
        "connector" in name.lower()
        or any(
            marker in msg
            for marker in (
                "connection",
                "cannot connect",
                "connecterror",
                "dns",
                "network",
            )
        )
    ):
        return LLMNetworkError("network")

    return exc


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def is_configured(self) -> bool:
        return bool(_api_key())

    def model_name(self) -> Optional[str]:
        return (
            os.environ.get("GEMINI_MODEL")
            or os.environ.get("LLM_MODEL")
            or "gemini-flash-lite-latest"
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

        primary = self.model_name() or "gemini-flash-lite-latest"
        candidates = _model_candidates(primary)
        timeout_s = float(
            os.environ.get("DOCUMENT_AI_TIMEOUT_S")
            or os.environ.get("GEMINI_TIMEOUT_S")
            or "60"
        )

        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise LLMConfigurationError(
                "Pacchetto google-genai non installato"
            ) from e

        # Single safe client: explicit API key only (never logged).
        client = genai.Client(api_key=api_key)
        config_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "temperature": 0.2 if json_mode else 0.4,
            "http_options": types.HttpOptions(timeout=int(timeout_s * 1000)),
        }
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        config = types.GenerateContentConfig(**config_kwargs)

        models_tried: list[str] = []
        last_error: Optional[BaseException] = None
        t0 = time.perf_counter()

        try:
            for idx, model_name in enumerate(candidates):
                models_tried.append(model_name)
                fallback_used = idx > 0
                try:
                    resp = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=model_name,
                            contents=user,
                            config=config,
                        ),
                        timeout=timeout_s,
                    )
                except asyncio.TimeoutError as e:
                    last_error = LLMTimeoutError("timeout")
                    # Timeout: do not burn alternate; escalate to manager.
                    raise last_error from e
                except Exception as e:
                    mapped = _map_api_error(e)
                    last_error = mapped
                    # Alternate model on unavailable / blocked / invalid / temp.
                    # Quota / rate / auth / timeout → Provider Manager failover.
                    retryable = isinstance(
                        mapped, (LLMModelUnavailableError, LLMNetworkError)
                    ) or (
                        isinstance(mapped, LLMInvalidResponseError)
                        and str(mapped) in ("blocked", "invalid", "empty")
                    )
                    if retryable and idx + 1 < len(candidates):
                        logger.warning(
                            "Gemini model=%s outcome=%s trying_alternate",
                            model_name,
                            type(mapped).__name__,
                        )
                        continue
                    raise mapped from e

                text = ""
                try:
                    text = (getattr(resp, "text", None) or "").strip()
                except Exception:
                    text = ""
                if not text:
                    last_error = LLMInvalidResponseError("empty")
                    if idx + 1 < len(candidates):
                        logger.warning(
                            "Gemini model=%s outcome=empty trying_alternate",
                            model_name,
                        )
                        continue
                    raise last_error

                usage: dict[str, Any] = {
                    "provider": self.name,
                    "model": model_name,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "outcome": "success",
                    "fallback_used": fallback_used,
                    "models_tried": list(models_tried),
                }
                meta = getattr(resp, "usage_metadata", None)
                if meta is not None:
                    for src, dst in (
                        ("prompt_token_count", "prompt_tokens"),
                        ("candidates_token_count", "completion_tokens"),
                        ("total_token_count", "total_tokens"),
                    ):
                        val = getattr(meta, src, None)
                        if val is not None:
                            usage[dst] = val
                else:
                    usage["approx_tokens_in"] = (len(system) + len(user)) // 4
                    usage["approx_tokens_out"] = len(text) // 4

                return LLMResult(
                    text=text,
                    provider=self.name,
                    model=model_name,
                    usage=usage,
                )
        finally:
            try:
                await client.aio.aclose()
            except Exception:
                pass

        if last_error is not None:
            raise last_error
        raise LLMInvalidResponseError("empty")
