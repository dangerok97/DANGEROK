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
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from llm.base import BaseLLMProvider, LLMResult
from llm.errors import (
    LLMError,
    LLMConfigurationError,
    LLMInternalError,
    LLMNotConfigured,
    LLMProviderUnavailable,
    is_failoverable,
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

# Conservative, process-local cooldowns. Retry-After may extend these up to
# MAX_RETRY_AFTER_S; no request sleeps while a circuit is open.
COOLDOWN_SECONDS = {
    "quota": 60.0,
    "rate_limit": 30.0,
    "timeout": 5.0,
    "network": 5.0,
    "authentication": 300.0,
    "configuration": 300.0,
    "model_unavailable": 60.0,
    "invalid_response": 5.0,
}
MAX_RETRY_AFTER_S = 300.0


@dataclass
class _RuntimeState:
    state: str = "unknown"
    failure_kind: Optional[str] = None
    cooldown_until: float = 0.0


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
        self._runtime = {name: _RuntimeState() for name in DEFAULT_PRIORITY}
        self._state_lock = asyncio.Lock()
        self._clock = time.monotonic

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
        async with self._state_lock:
            return self._runtime[name].cooldown_until <= self._clock()

    async def _record_failure(self, name: str, error: LLMError) -> None:
        duration = COOLDOWN_SECONDS.get(error.kind, 0.0)
        if error.retry_after is not None:
            duration = max(duration, min(MAX_RETRY_AFTER_S, max(0.0, error.retry_after)))
        async with self._state_lock:
            self._runtime[name] = _RuntimeState(
                state=(
                    "config_error"
                    if error.kind in ("authentication", "configuration")
                    else ("cooldown" if duration else "degraded")
                ),
                failure_kind=error.kind,
                cooldown_until=self._clock() + duration,
            )

    async def _record_success(self, name: str) -> None:
        async with self._state_lock:
            self._runtime[name] = _RuntimeState(state="healthy")

    def runtime_snapshot(self, name: str) -> dict[str, Any]:
        """Non-blocking process-local snapshot for synchronous health views."""
        runtime = self._runtime[name]
        cooling = runtime.cooldown_until > self._clock()
        return {
            "runtime_state": "cooldown" if cooling else (
                "degraded" if runtime.state == "cooldown" else runtime.state
            ),
            "failure_kind": runtime.failure_kind,
        }

    @staticmethod
    def _attempt(name: str, kind: str, retryable: bool) -> dict[str, Any]:
        return {
            "provider": name,
            "failure_kind": kind,
            "retryable": retryable,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def status(self, user_preference: Optional[str] = None) -> dict[str, Any]:
        items = []
        for name in DEFAULT_PRIORITY:
            p = self._providers[name]
            configured = p.is_configured()
            async with self._state_lock:
                snapshot = self.runtime_snapshot(name)
                cooling = snapshot["runtime_state"] == "cooldown"
                runtime_state = "disabled" if not configured else snapshot["runtime_state"]
                failure_kind = snapshot["failure_kind"]
            available = configured and not cooling
            items.append({
                "id": name,
                "label": {
                    "gemini": "Gemini",
                    "openai": "OpenAI",
                    "ollama": "Ollama",
                    "emergent": "Emergent",
                }.get(name, name),
                "configured": configured,
                "enabled": configured,
                "available": available,
                "runtime_state": runtime_state,
                "failure_kind": failure_kind,
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
        attempts: list[dict[str, Any]] = []
        configured = [name for name in self.ordered_names(user_preference) if self._providers[name].is_configured()]
        if not configured:
            raise LLMNotConfigured("No LLM provider is configured")
        for name in self.ordered_names(user_preference):
            if not await self._available(name):
                if self._providers[name].is_configured():
                    attempts.append(self._attempt(name, "cooldown", True))
                    logger.info("LLM provider=%s result=cooldown", name)
                else:
                    logger.debug("LLM provider=%s result=skip", name)
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
                await self._record_success(name)
                logger.info("LLM provider=%s result=success latency_ms=%.1f", name, result.usage["latency_ms"])
                return result
            except LLMNotConfigured:
                # Adapter/runtime configuration drift: fail over, but do not
                # redefine the manager-level meaning of LLMNotConfigured.
                error = LLMConfigurationError("configuration")
                await self._record_failure(name, error)
                attempts.append(self._attempt(name, "configuration", True))
                errors.append(f"{name}:configuration")
                logger.warning("LLM provider=%s result=fail failure_kind=configuration", name)
                continue
            except LLMError as e:
                if not is_failoverable(e):
                    logger.error("LLM provider=%s result=fail failure_kind=%s", name, e.kind)
                    raise
                await self._record_failure(name, e)
                attempts.append(self._attempt(name, e.kind, True))
                errors.append(f"{name}:{e.kind}")
                logger.warning("LLM provider=%s result=fail failure_kind=%s", name, e.kind)
                continue
            except Exception:
                logger.error("LLM provider=%s result=internal_error", name)
                raise LLMInternalError("Internal ORA/provider adapter error") from None
        raise LLMProviderUnavailable(attempts)

    async def analyze_document(self, *, text: str, context: dict, user_preference: Optional[str] = None) -> LLMResult:
        return await self._capability("analyze_document", user_preference=user_preference, text=text, context=context)

    async def ask_document(self, *, text: str, question: str, user_preference: Optional[str] = None) -> LLMResult:
        return await self._capability("ask_document", user_preference=user_preference, text=text, question=question)

    async def _capability(self, method: str, user_preference: Optional[str] = None, **kwargs) -> LLMResult:
        errors: list[str] = []
        attempts: list[dict[str, Any]] = []
        configured = [name for name in self.ordered_names(user_preference) if self._providers[name].is_configured()]
        if not configured:
            raise LLMNotConfigured("No LLM provider is configured")
        for name in self.ordered_names(user_preference):
            if not await self._available(name):
                if self._providers[name].is_configured():
                    attempts.append(self._attempt(name, "cooldown", True))
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
                await self._record_success(name)
                return result
            except LLMNotConfigured:
                error = LLMConfigurationError("configuration")
                await self._record_failure(name, error)
                attempts.append(self._attempt(name, "configuration", True))
                continue
            except LLMError as e:
                if not is_failoverable(e):
                    raise
                await self._record_failure(name, e)
                attempts.append(self._attempt(name, e.kind, True))
                errors.append(f"{name}:{e.kind}")
                continue
            except Exception:
                raise LLMInternalError("Internal ORA/provider adapter error") from None
        raise LLMProviderUnavailable(attempts)


_manager: Optional[ProviderManager] = None


def get_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager
