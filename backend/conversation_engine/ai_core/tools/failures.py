"""Normalized tool failure taxonomy — observations, not crashes."""
from __future__ import annotations

from typing import Literal

ToolFailureCode = Literal[
    "NOT_CONFIGURED",
    "AUTH",
    "RATE_LIMITED",
    "QUOTA_EXHAUSTED",
    "TIMEOUT",
    "NETWORK",
    "PROVIDER_ERROR",
    "INVALID_RESPONSE",
    "UNSUPPORTED",
    "UNKNOWN",
]

ALL_FAILURE_CODES = frozenset(
    {
        "NOT_CONFIGURED",
        "AUTH",
        "RATE_LIMITED",
        "QUOTA_EXHAUSTED",
        "TIMEOUT",
        "NETWORK",
        "PROVIDER_ERROR",
        "INVALID_RESPONSE",
        "UNSUPPORTED",
        "UNKNOWN",
    }
)


def normalize_failure(code: str | None) -> str:
    c = (code or "UNKNOWN").strip().upper()
    return c if c in ALL_FAILURE_CODES else "UNKNOWN"
