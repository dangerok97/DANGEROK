"""Provider-agnostic LLM access for ORA."""
from .errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInternalError,
    LLMInvalidResponseError,
    LLMModelUnavailableError,
    LLMNetworkError,
    LLMNotConfigured,
    LLMProviderUnavailable,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from .manager import get_manager, set_runtime_preferred, get_runtime_preferred
from .provider import chat_completion, llm_status, llm_status_async
from .structured import chat_json, chunk_text

__all__ = [
    "LLMNotConfigured",
    "LLMProviderUnavailable",
    "LLMNetworkError",
    "LLMAuthenticationError",
    "LLMConfigurationError",
    "LLMModelUnavailableError",
    "LLMInvalidResponseError",
    "LLMInternalError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMQuotaError",
    "chat_completion",
    "chat_json",
    "chunk_text",
    "llm_status",
    "llm_status_async",
    "get_manager",
    "set_runtime_preferred",
    "get_runtime_preferred",
]
