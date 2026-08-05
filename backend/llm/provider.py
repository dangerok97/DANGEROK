"""Backward-compatible facade over ProviderManager.

Prefer importing from `llm` / `llm.manager`. This module keeps existing
`chat_completion` / `llm_status` call sites working.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from llm.errors import (
    LLMNotConfigured,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from llm.manager import get_manager

logger = logging.getLogger("ora.llm")

__all__ = [
    "LLMNotConfigured",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMQuotaError",
    "chat_completion",
    "llm_status",
]


def llm_status() -> Dict[str, Any]:
    """Sync snapshot for health checks (no Ollama probe await).

    For full async status with probes use `get_manager().status()`.
    """
    import asyncio
    mgr = get_manager()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Best-effort sync view without probe
            return _sync_status_snapshot()
        return loop.run_until_complete(mgr.status())
    except RuntimeError:
        return asyncio.run(mgr.status())


def _sync_status_snapshot() -> Dict[str, Any]:
    mgr = get_manager()
    pref = mgr.preferred_name()
    # Prefer configured cloud providers without network probe
    for name in mgr.ordered_names(pref):
        p = mgr.get(name)
        if name == "ollama":
            continue
        if p.is_configured():
            return {
                "provider": name,
                "configured": True,
                "model": p.model_name(),
                "preferred": pref,
                "active": name,
            }
    # If only ollama might be up, report preferred/none without claiming available
    return {
        "provider": pref or "none",
        "configured": False,
        "model": None,
        "preferred": pref,
        "active": None,
    }


async def llm_status_async(user_preference: Optional[str] = None) -> Dict[str, Any]:
    return await get_manager().status(user_preference=user_preference)


async def chat_completion(
    *,
    system: str,
    user: str,
    session_id: Optional[str] = None,
    json_mode: bool = False,
    user_preference: Optional[str] = None,
) -> str:
    result = await get_manager().chat(
        system=system,
        user=user,
        session_id=session_id,
        json_mode=json_mode,
        user_preference=user_preference,
    )
    return result.text
