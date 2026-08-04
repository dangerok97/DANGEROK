"""Typed LLM errors (no secrets in messages)."""
from __future__ import annotations


class LLMNotConfigured(RuntimeError):
    pass


class LLMRateLimitError(RuntimeError):
    pass


class LLMTimeoutError(RuntimeError):
    pass


class LLMQuotaError(RuntimeError):
    pass


class LLMInvalidResponseError(RuntimeError):
    pass
