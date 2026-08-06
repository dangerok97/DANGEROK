"""Goal Engine adapter — shadow upsert / link only."""
from __future__ import annotations

from typing import Any, Dict, Optional

from goal_engine import GoalService, goal_engine_enabled
from goal_engine.models import GoalCreateBody


class GoalAdapter:
    def __init__(self, db, *, life_graph=None, knowledge=None):
        self.svc = GoalService(db, life_graph=life_graph, knowledge=knowledge)

    async def shadow_from_intent(
        self,
        user_id: str,
        *,
        text: str,
        intent: Dict[str, Any],
        action_session_id: Optional[str] = None,
        conversation_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not goal_engine_enabled():
            return {"ok": False, "skipped": True, "error": "goal_engine_disabled"}

        intent_name = (intent or {}).get("intent") or "generic"
        entities = (intent or {}).get("entities") or {}
        if not isinstance(entities, dict):
            entities = {}

        title = _title_for_intent(text, intent_name, entities)
        goal_type = _goal_type(intent_name)
        body = GoalCreateBody(
            title=title,
            goal_type=goal_type,  # type: ignore[arg-type]
            goal_subtype=(intent or {}).get("subtype"),
            description=text[:400] if text else None,
            status="planning",
            source_action_session_id=action_session_id,
            idempotency_key=(
                f"ce:{conversation_session_id}:{intent_name}"
                if conversation_session_id
                else None
            ),
            created_from={
                "source": "conversation_engine",
                "intent": intent_name,
                "intent_subtype": (intent or {}).get("subtype"),
                "conversation_session_id": conversation_session_id,
                "action_session_id": action_session_id,
            },
            next_action="Completa la guida ORA",
        )
        result = await self.svc.create(user_id, body)
        return result


def _goal_type(intent_name: str) -> str:
    mapping = {
        "study": "study",
        "travel": "travel",
        "event": "event",
        "medical": "health",
        "admin": "admin",
    }
    return mapping.get(intent_name or "", "generic")


def _title_for_intent(text: str, intent_name: str, entities: Dict[str, Any]) -> str:
    if intent_name == "travel":
        dest = entities.get("travel") or entities.get("place") or entities.get("destination")
        if dest:
            return f"Organizzare viaggio — {dest}"
        return "Organizzare viaggio"
    if intent_name == "study":
        subject = entities.get("subject") or entities.get("exam")
        if subject:
            return f"Preparare esame — {subject}"
        return "Preparare esame"
    if text:
        t = text.strip()
        return t[:80] + ("…" if len(t) > 80 else "")
    return "Obiettivo ORA"
