"""Typed, sanitized LLM failures shared by providers and the manager."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, Mapping, Optional


class LLMError(RuntimeError):
    """Base error with policy-safe metadata; never store raw provider payloads."""

    kind = "llm_error"
    failoverable = False

    def __init__(self, message: str = "llm_error", *, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMNotConfigured(LLMError):
    """No provider is enabled and configured for this manager."""

    kind = "not_configured"


class LLMProviderUnavailable(LLMNotConfigured):
    """Configured providers were attempted or cooling down, but none succeeded."""

    kind = "provider_unavailable"

    def __init__(self, attempts: Iterable[Mapping[str, Any]]):
        bounded = []
        for item in list(attempts)[:8]:
            bounded.append(
                {
                    "provider": str(item.get("provider") or "unknown")[:32],
                    "failure_kind": str(item.get("failure_kind") or "unknown")[:32],
                    "retryable": bool(item.get("retryable")),
                    "timestamp": str(item.get("timestamp") or "")[:40],
                }
            )
        self.attempts = tuple(bounded)
        LLMError.__init__(self, "Configured LLM providers are temporarily unavailable")


class LLMQuotaError(LLMError):
    kind = "quota"
    failoverable = True


class LLMRateLimitError(LLMError):
    kind = "rate_limit"
    failoverable = True


class LLMTimeoutError(LLMError):
    kind = "timeout"
    failoverable = True


class LLMNetworkError(LLMError):
    kind = "network"
    failoverable = True


class LLMAuthenticationError(LLMError):
    kind = "authentication"
    failoverable = True


class LLMConfigurationError(LLMError):
    kind = "configuration"
    failoverable = True


class LLMModelUnavailableError(LLMError):
    kind = "model_unavailable"
    failoverable = True


class LLMInvalidResponseError(LLMError):
    """The remote provider returned an empty or malformed protocol response."""

    kind = "invalid_response"
    failoverable = True


class LLMInternalError(LLMError):
    """ORA/application error: fail fast so another provider cannot mask it."""

    kind = "internal"


def is_failoverable(error: BaseException) -> bool:
    return isinstance(error, LLMError) and error.failoverable


def retry_after_seconds(error: BaseException, *, maximum: float = 300.0) -> Optional[float]:
    """Read a numeric Retry-After without retaining headers or raw payloads."""

    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or getattr(error, "headers", None)
    if not headers:
        return None
    value: Any = None
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
        return min(maximum, max(0.0, float(value)))
    except (TypeError, ValueError, AttributeError):
        try:
            target = parsedate_to_datetime(str(value))
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            delay = (target - datetime.now(timezone.utc)).total_seconds()
            return min(maximum, max(0.0, delay))
        except (TypeError, ValueError, OverflowError):
            return None
