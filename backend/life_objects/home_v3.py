"""Home V3 card DTO — PREDISPOSTO, flag OFF. No frontend Home changes.

Internal serializer for future Life Object cards. Not used by current Home UX.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def life_object_home_ui_enabled() -> bool:
    raw = (os.environ.get("LIFE_OBJECT_HOME_UI_ENABLED") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def to_home_v3_card(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Compact card shape for a future Home V3 — never branding 'Life Object' for end users."""
    health = obj.get("health") or {}
    narrative = obj.get("narrative") or {}
    insights = obj.get("insights") or []
    questions = obj.get("pending_questions") or []
    return {
        "id": obj.get("id"),
        "type": obj.get("type"),
        "title": obj.get("title"),
        "status": obj.get("status"),
        "narrative": (narrative.get("text") or obj.get("ai_summary") or obj.get("summary") or "")[:280],
        "health": {
            "score": health.get("score"),
            "label": health.get("label"),
            "completeness": health.get("completeness"),
            "reliability": health.get("reliability"),
        },
        "top_insight": (insights[0].get("title") if insights and isinstance(insights[0], dict) else None),
        "pending_question": (
            questions[0].get("question") if questions and isinstance(questions[0], dict) else None
        ),
        "documents_count": len(obj.get("documents") or []),
        "updated_at": obj.get("updated_at"),
    }


def serialize_home_v3_feed(
    objects: List[Dict[str, Any]],
    *,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """Return Home V3 feed only when flag ON (or force for tests). Default: None / disabled."""
    if not force and not life_object_home_ui_enabled():
        return {
            "enabled": False,
            "home_ui_enabled": False,
            "cards": [],
            "note": "Home V3 PREDISPOSTO — LIFE_OBJECT_HOME_UI_ENABLED=0",
        }
    cards = [to_home_v3_card(o) for o in objects]
    return {
        "enabled": True,
        "home_ui_enabled": True,
        "cards": cards,
        "count": len(cards),
    }
