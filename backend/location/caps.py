"""AI Core location capabilities — device presence, not semantic home/work."""
from __future__ import annotations

from typing import Any, Dict

from conversation_engine.ai_core.models import Observation


def _fail(name: str, code: str, detail: str = "") -> Observation:
    return Observation(
        kind="tool",
        name=name,
        status="error",
        payload={
            "capability": name,
            "status": "error",
            "error": code,
            "detail": detail[:200],
            "memory_eligible": False,
        },
    )


async def get_current_location(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("get_current_location", "NOT_CONFIGURED")
    from location.service import LocationService

    platform = str(arguments.get("platform") or runtime.get("platform") or "web")
    svc = LocationService(db)
    payload = await svc.capability_get_current_location(
        uid,
        session_id=runtime.get("session_id"),
        platform=platform,
    )
    status = payload.get("status") or "unknown"
    obs_status = "ok"
    if status in ("denied", "unavailable", "error", "timeout"):
        obs_status = "error"
    elif status in (
        "needs_client",
        "stale",
        "permission_required",
        "consent_required",
    ):
        obs_status = "needs_client"
    elif payload.get("needs_client"):
        obs_status = "needs_client"
    return Observation(
        kind="tool",
        name="get_current_location",
        status=obs_status,
        payload=payload,
        provenance=[f"location:{uid[:8]}"],
    )


async def get_current_presence(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("get_current_presence", "NOT_CONFIGURED")
    from location.service import LocationService

    platform = str(arguments.get("platform") or runtime.get("platform") or "web")
    svc = LocationService(db)
    payload = await svc.capability_get_current_presence(uid, platform=platform)
    obs_status = "needs_client" if payload.get("needs_client") else "ok"
    return Observation(
        kind="tool",
        name="get_current_presence",
        status=obs_status,
        payload=payload,
        provenance=[f"presence:{uid[:8]}"],
    )


async def get_recent_presence_context(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    """Latest presence only in V2.7.1 — no historical trail dump."""
    return await get_current_presence(arguments, runtime)
