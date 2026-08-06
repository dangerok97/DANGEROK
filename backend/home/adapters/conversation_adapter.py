"""Surface Conversation Engine sessions on Home resume — never 'Apri chat'."""
from __future__ import annotations

from typing import List, Tuple

from home.models import HomeAction, HomeItem, ReasonFactor


async def load_conversation_items(db, user_id: str) -> Tuple[List[HomeItem], list]:
    items: List[HomeItem] = []
    try:
        from conversation_engine.service import conversation_engine_enabled
        if not conversation_engine_enabled():
            return [], []
    except Exception:
        return [], []

    sessions = await db.conversation_sessions.find(
        {
            "user_id": user_id,
            "status": {"$in": ["active", "waiting_user", "running_action", "paused"]},
        },
        {"_id": 0},
    ).sort("updated_at", -1).to_list(12)

    for s in sessions:
        intent = (s.get("intent") or {}).get("intent") if isinstance(s.get("intent"), dict) else None
        summary = s.get("summary") or _default_summary(intent)
        action_sid = s.get("action_session_id")
        route = f"/action/{action_sid}" if action_sid else f"/conversation?resume={s['id']}"
        it = HomeItem(
            id=f"ce_session_{s['id']}",
            type="resume",
            subtype=intent or "conversation",
            title=summary,
            description="Continua la collaborazione con ORA",
            source_type="conversation_session",
            source_id=s["id"],
            priority="today",
            urgency="soon",
            status="open",
            reason_factors=[ReasonFactor(
                code="conversation_resume",
                label="Collaborazione in corso",
                weight=0.75,
            )],
            reason_summary=summary,
            goal_id=s.get("goal_id"),
            meta={
                "dedupe_key": f"ce_session:{s['id']}",
                "resume_kind": "conversation",
                "conversation_session_id": s["id"],
                "action_session_id": action_sid,
                "resume_token": s.get("resume_token"),
                "goal_id": s.get("goal_id"),
                "ui_mode": "action_engine",
            },
            created_at=s.get("created_at"),
            updated_at=s.get("updated_at"),
            actions=[
                HomeAction(
                    id="resume_ce",
                    label="Continua",
                    kind="resume",
                    route=route,
                    primary=True,
                    params={"conversation_session_id": s["id"]},
                ),
            ],
        )
        items.append(it)
    return items, []


def _default_summary(intent: str | None) -> str:
    if intent == "travel":
        return "Stavamo organizzando la tua vacanza."
    if intent == "study":
        return "Stavamo preparando il tuo esame."
    return "Hai una guida ORA da completare."
