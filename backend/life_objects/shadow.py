"""Soft-fail shadow hooks for Life Object Engine.

Callers should wrap with try/except; these helpers never raise to callers.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.life_objects.shadow")


async def shadow_upsert_from_document(
    db,
    *,
    user_id: str,
    doc: Dict[str, Any],
    reasoning: Dict[str, Any],
    life_graph=None,
) -> Dict[str, Any]:
    try:
        from life_objects.service import get_life_object_service, life_object_engine_enabled

        if not life_object_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "life_object_engine_disabled"}
        svc = get_life_object_service(db, life_graph=life_graph)
        return await svc.upsert_from_document(user_id, doc, reasoning)
    except Exception as e:
        logger.info("life_object document shadow soft-fail: %s", type(e).__name__)
        return {"ok": False, "soft_fail": True, "error": type(e).__name__}


async def shadow_attach_goal(
    db,
    *,
    user_id: str,
    goal: Dict[str, Any],
    life_graph=None,
) -> Dict[str, Any]:
    try:
        from life_objects.service import get_life_object_service, life_object_engine_enabled

        if not life_object_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "life_object_engine_disabled"}
        svc = get_life_object_service(db, life_graph=life_graph)
        return await svc.attach_goal(user_id, goal)
    except Exception as e:
        logger.info("life_object goal shadow soft-fail: %s", type(e).__name__)
        return {"ok": False, "soft_fail": True, "error": type(e).__name__}


async def shadow_upsert_from_travel(
    db,
    *,
    user_id: str,
    project: Dict[str, Any],
    life_graph=None,
) -> Dict[str, Any]:
    try:
        from life_objects.service import get_life_object_service, life_object_engine_enabled

        if not life_object_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "life_object_engine_disabled"}
        svc = get_life_object_service(db, life_graph=life_graph)
        return await svc.upsert_from_travel(user_id, project)
    except Exception as e:
        logger.info("life_object travel shadow soft-fail: %s", type(e).__name__)
        return {"ok": False, "soft_fail": True, "error": type(e).__name__}


async def shadow_upsert_from_study(
    db,
    *,
    user_id: str,
    plan: Dict[str, Any],
    life_graph=None,
) -> Dict[str, Any]:
    try:
        from life_objects.service import get_life_object_service, life_object_engine_enabled

        if not life_object_engine_enabled():
            return {"ok": True, "skipped": True, "reason": "life_object_engine_disabled"}
        svc = get_life_object_service(db, life_graph=life_graph)
        return await svc.upsert_from_study(user_id, plan)
    except Exception as e:
        logger.info("life_object study shadow soft-fail: %s", type(e).__name__)
        return {"ok": False, "soft_fail": True, "error": type(e).__name__}
