"""Proactive candidates for interrupted Conversation Engine sessions.

Example: "Ieri hai interrotto la preparazione dell'esame" → Riprendi.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from proactive_engine.models import SuggestionAction, SuggestionCandidate


async def generate_conversation_candidates(
    db, user_id: str, *, now: Optional[datetime] = None,
) -> List[SuggestionCandidate]:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=7)).isoformat()
    out: List[SuggestionCandidate] = []

    try:
        sessions = await db.conversation_sessions.find(
            {
                "user_id": user_id,
                "status": {"$in": ["paused", "waiting_user", "active", "running_action"]},
                "updated_at": {"$lte": (now - timedelta(hours=2)).isoformat()},
                "created_at": {"$gte": cutoff},
            },
            {"_id": 0},
        ).sort("updated_at", -1).to_list(8)
    except Exception:
        return []

    for s in sessions:
        intent = (s.get("intent") or {}).get("intent") if isinstance(s.get("intent"), dict) else None
        if intent == "study":
            title = "Ieri hai interrotto la preparazione dell'esame"
            reason = "Hai una guida studio non completata"
            stype = "study"
        elif intent == "travel":
            title = "Stavi organizzando la tua vacanza"
            reason = "Hai una guida viaggio non completata"
            stype = "travel"
        else:
            title = s.get("summary") or "Continua dove avevi lasciato"
            reason = "Collaborazione ORA interrotta"
            stype = "life"
        ces_id = s["id"]
        action_sid = s.get("action_session_id")
        route = f"/action/{action_sid}" if action_sid else f"/conversation?resume={ces_id}"
        out.append(SuggestionCandidate(
            title=title,
            description=s.get("summary") or s.get("input"),
            reason=reason,
            type=stype,  # type: ignore[arg-type]
            source="conversation_session",
            goal_id=s.get("goal_id"),
            project_id=s.get("project_id"),
            action=SuggestionAction(
                kind="resume_conversation",
                label="Riprendi",
                route=route,
                params={"conversation_session_id": ces_id},
            ),
            dedupe_key=f"ce_resume:{ces_id}",
            evidence={
                "conversation_session_id": ces_id,
                "action_session_id": action_sid,
                "intent": intent,
            },
            meta={"conversation_session_id": ces_id},
            importance_hint=0.7,
            urgency_hint=0.55,
            confidence=0.85,
        ))
    return out
