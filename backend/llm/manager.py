"""Provider Manager — select, failover, status.

Priority (default): gemini → openai → ollama → emergent

Preferred provider may come from:
  1. per-request / user preference (runtime, no restart)
  2. LLM_PROVIDER env
  3. first available in priority order
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from llm.base import BaseLLMProvider, LLMResult
from llm.errors import (
    LLMNotConfigured,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from llm.providers import (
    EmergentProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)

logger = logging.getLogger("ora.llm.manager")

DEFAULT_PRIORITY = ("gemini", "openai", "ollama", "emergent")
VALID_PROVIDERS = frozenset(DEFAULT_PRIORITY)

# Process-level preferred override (also updated via API without restart)
_runtime_preferred: Optional[str] = None


def set_runtime_preferred(name: Optional[str]) -> None:
    global _runtime_preferred
    if name is None or name in ("", "auto", "none"):
        _runtime_preferred = None
        return
    n = name.strip().lower()
    if n not in VALID_PROVIDERS:
        raise ValueError(f"Provider non valido: {name}")
    _runtime_preferred = n


def get_runtime_preferred() -> Optional[str]:
    return _runtime_preferred


class ProviderManager:
    def __init__(self) -> None:
        self._providers: dict[str, BaseLLMProvider] = {
            "gemini": GeminiProvider(),
            "openai": OpenAIProvider(),
            "ollama": OllamaProvider(),
            "emergent": EmergentProvider(),
        }

    def get(self, name: str) -> BaseLLMProvider:
        if name not in self._providers:
            raise LLMNotConfigured(f"Provider sconosciuto: {name}")
        return self._providers[name]

    def preferred_name(self, user_preference: Optional[str] = None) -> Optional[str]:
        for candidate in (
            (user_preference or "").strip().lower(),
            (_runtime_preferred or "").strip().lower(),
            (os.environ.get("LLM_PROVIDER") or "").strip().lower(),
        ):
            if candidate in ("", "none", "off", "disabled", "auto"):
                continue
            if candidate in VALID_PROVIDERS:
                return candidate
        return None

    def ordered_names(self, user_preference: Optional[str] = None) -> list[str]:
        pref = self.preferred_name(user_preference)
        order = list(DEFAULT_PRIORITY)
        if pref and pref in order:
            order.remove(pref)
            order.insert(0, pref)
        return order

    async def _available(self, name: str) -> bool:
        p = self._providers[name]
        if not p.is_configured():
            return False
        if name == "ollama":
            return await p.probe()  # type: ignore[attr-defined]
        return True

    async def status(self, user_preference: Optional[str] = None) -> dict[str, Any]:
        items = []
        for name in DEFAULT_PRIORITY:
            p = self._providers[name]
            configured = p.is_configured()
            available = await self._available(name) if configured or name == "ollama" else False
            # For ollama without OLLAMA_ENABLED, still probe for UI
            if name == "ollama" and not configured:
                available = await p.probe()  # type: ignore[attr-defined]
                configured = available
            items.append({
                "id": name,
                "label": {
                    "gemini": "Gemini",
                    "openai": "OpenAI",
                    "ollama": "Ollama",
                    "emergent": "Emergent",
                }.get(name, name),
                "configured": configured,
                "available": available,
                "model": p.model_name() if configured or available else None,
                "priority": DEFAULT_PRIORITY.index(name) + 1,
            })
        chain = []
        for name in self.ordered_names(user_preference):
            if await self._available(name):
                chain.append(name)
        active = chain[0] if chain else None
        return {
            "active": active,
            "preferred": self.preferred_name(user_preference),
            "fallback_chain": chain,
            "priority": list(DEFAULT_PRIORITY),
            "configured": bool(active),
            "providers": items,
            # backward-compatible fields for llm_status / health
            "provider": active or "none",
            "model": self._providers[active].model_name() if active else None,
        }

    async def chat(
        self,
        *,
        system: str,
        user: str,
        session_id: Optional[str] = None,
        json_mode: bool = False,
        user_preference: Optional[str] = None,
    ) -> LLMResult:
        errors: list[str] = []
        for name in self.ordered_names(user_preference):
            if not await self._available(name):
                continue
            p = self._providers[name]
            t0 = time.perf_counter()
            try:
                result = await p.chat(
                    system=system,
                    user=user,
                    session_id=session_id,
                    json_mode=json_mode,
                )
                result.usage = {
                    **(result.usage or {}),
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "failover_errors": errors,
                }
                return result
            except (LLMQuotaError, LLMRateLimitError, LLMTimeoutError) as e:
                errors.append(f"{name}:{type(e).__name__}")
                logger.warning("LLM failover from %s due to %s", name, type(e).__name__)
                continue
            except LLMNotConfigured:
                errors.append(f"{name}:not_configured")
                continue
            except Exception as e:
                errors.append(f"{name}:{type(e).__name__}")
                logger.warning("LLM failover from %s type=%s", name, type(e).__name__)
                continue
        raise LLMNotConfigured(
            "Nessun provider LLM disponibile. "
            "Configura GEMINI_API_KEY (consigliato), OPENAI_API_KEY, Ollama o EMERGENT_LLM_KEY."
        )

    async def analyze_document(self, *, text: str, context: dict, user_preference: Optional[str] = None) -> LLMResult:
        return await self._capability("analyze_document", user_preference=user_preference, text=text, context=context)

    async def ask_document(self, *, text: str, question: str, user_preference: Optional[str] = None) -> LLMResult:
        return await self._capability("ask_document", user_preference=user_preference, text=text, question=question)

    async def _capability(self, method: str, user_preference: Optional[str] = None, **kwargs) -> LLMResult:
        errors: list[str] = []
        for name in self.ordered_names(user_preference):
            if not await self._available(name):
                continue
            p = self._providers[name]
            t0 = time.perf_counter()
            try:
                fn = getattr(p, method)
                result: LLMResult = await fn(**kwargs)
                result.usage = {
                    **(result.usage or {}),
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "failover_errors": errors,
                }
                return result
            except (LLMQuotaError, LLMRateLimitError, LLMTimeoutError, LLMNotConfigured) as e:
                errors.append(f"{name}:{type(e).__name__}")
                logger.warning("LLM capability %s failover %s", method, type(e).__name__)
                continue
            except Exception as e:
                errors.append(f"{name}:{type(e).__name__}")
                logger.warning("LLM capability %s error type=%s", method, type(e).__name__)
                continue
        raise LLMNotConfigured("Nessun provider LLM disponibile")


_manager: Optional[ProviderManager] = None


def get_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager
