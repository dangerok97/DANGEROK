"""Normalized provider failure taxonomy — adapters translate native errors here."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class ProviderFailure(str, Enum):
    AUTH = "AUTH"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    PROVIDER_5XX = "PROVIDER_5XX"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    CONTENT_BLOCKED = "CONTENT_BLOCKED"
    UNKNOWN = "UNKNOWN"
    NOT_CONFIGURED = "NOT_CONFIGURED"


# Failures that should trigger cooldown + failover (do not hammer)
FAILOVER_FAILURES = frozenset(
    {
        ProviderFailure.QUOTA_EXHAUSTED,
        ProviderFailure.RATE_LIMITED,
        ProviderFailure.TIMEOUT,
        ProviderFailure.NETWORK,
        ProviderFailure.PROVIDER_5XX,
        ProviderFailure.AUTH,
        ProviderFailure.NOT_CONFIGURED,
    }
)

# Longer cooldown for quota; short for rate limit
COOLDOWN_SECONDS = {
    ProviderFailure.QUOTA_EXHAUSTED: 900,  # 15 min
    ProviderFailure.RATE_LIMITED: 60,
    ProviderFailure.TIMEOUT: 30,
    ProviderFailure.NETWORK: 30,
    ProviderFailure.PROVIDER_5XX: 60,
    ProviderFailure.AUTH: 600,
    ProviderFailure.NOT_CONFIGURED: 3600,
}


def classify_http_status(code: Optional[int], message: str = "") -> ProviderFailure:
    msg = (message or "").lower()
    if code in (401, 403) or "unauthenticated" in msg or "permission" in msg:
        return ProviderFailure.AUTH
    if code == 429:
        if "quota" in msg or "billing" in msg or "exceeded" in msg or "resource_exhausted" in msg:
            return ProviderFailure.QUOTA_EXHAUSTED
        return ProviderFailure.RATE_LIMITED
    if code in (402,) or "quota" in msg or "billing" in msg or "resource_exhausted" in msg:
        return ProviderFailure.QUOTA_EXHAUSTED
    if code in (500, 502, 503, 504):
        return ProviderFailure.PROVIDER_5XX
    if code == 400 and ("blocked" in msg or "safety" in msg):
        return ProviderFailure.CONTENT_BLOCKED
    if "timeout" in msg or "timed out" in msg:
        return ProviderFailure.TIMEOUT
    if "network" in msg or "connection" in msg:
        return ProviderFailure.NETWORK
    return ProviderFailure.UNKNOWN


def classify_exception(exc: BaseException) -> ProviderFailure:
    """Map typed LLM errors + common exception shapes → taxonomy."""
    from llm.errors import (
        LLMInvalidResponseError,
        LLMNotConfigured,
        LLMQuotaError,
        LLMRateLimitError,
        LLMTimeoutError,
    )

    if isinstance(exc, LLMQuotaError):
        return ProviderFailure.QUOTA_EXHAUSTED
    if isinstance(exc, LLMRateLimitError):
        return ProviderFailure.RATE_LIMITED
    if isinstance(exc, LLMTimeoutError):
        return ProviderFailure.TIMEOUT
    if isinstance(exc, LLMNotConfigured):
        return ProviderFailure.NOT_CONFIGURED
    if isinstance(exc, LLMInvalidResponseError):
        msg = str(exc).lower()
        if "blocked" in msg:
            return ProviderFailure.CONTENT_BLOCKED
        return ProviderFailure.INVALID_RESPONSE
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    if "timeout" in msg or "timeout" in name:
        return ProviderFailure.TIMEOUT
    if "429" in msg or "rate" in msg:
        if "quota" in msg or "resource_exhausted" in msg:
            return ProviderFailure.QUOTA_EXHAUSTED
        return ProviderFailure.RATE_LIMITED
    if "quota" in msg or "resource_exhausted" in msg:
        return ProviderFailure.QUOTA_EXHAUSTED
    if "401" in msg or "403" in msg or "auth" in msg:
        return ProviderFailure.AUTH
    if "502" in msg or "503" in msg or "500" in msg:
        return ProviderFailure.PROVIDER_5XX
    if "network" in msg or "connection" in msg:
        return ProviderFailure.NETWORK
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(code, int):
        return classify_http_status(code, msg)
    return ProviderFailure.UNKNOWN


def failure_from_research_error(error: Optional[str]) -> ProviderFailure:
    e = (error or "").lower()
    if e in ("no_api_key", "sdk_missing", "unavailable", "auth"):
        return ProviderFailure.NOT_CONFIGURED if e != "auth" else ProviderFailure.AUTH
    if e == "quota_exhausted":
        return ProviderFailure.QUOTA_EXHAUSTED
    if e == "rate_limited" or "429" in e or "rate" in e:
        return ProviderFailure.RATE_LIMITED
    if "timeout" in e:
        return ProviderFailure.TIMEOUT
    if e.startswith("http_5") or "5xx" in e:
        return ProviderFailure.PROVIDER_5XX
    if e.startswith("http_401") or e.startswith("http_403"):
        return ProviderFailure.AUTH
    if e.startswith("http_429"):
        return ProviderFailure.RATE_LIMITED
    if e in ("empty", "all_providers_failed"):
        return ProviderFailure.INVALID_RESPONSE
    if not e:
        return ProviderFailure.UNKNOWN
    return ProviderFailure.UNKNOWN

def should_failover(failure: ProviderFailure) -> bool:
    return failure in FAILOVER_FAILURES


def cooldown_for(failure: ProviderFailure) -> int:
    return int(COOLDOWN_SECONDS.get(failure, 60))
