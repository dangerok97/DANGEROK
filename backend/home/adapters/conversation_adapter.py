"""
What a conversation left behind, if anything.

An exchange is not a task because it took place. Somebody asked what a car
inspection costs, ORA told them, and Home answered with "DA FARE ADESSO:
conoscere il costo medio della revisione auto — Continua la collaborazione con
ORA". Nothing had been taken on. The conversation existed, and existing was
being read as unfinished work.

So this asks a different question: did the reasoning leave something that has
to be returned to?

  * a plan it drew up — it decided to organise something, and the plan is
    waiting;
  * a guided flow it opened — there are steps part-way through;
  * a question it is blocked on — V3.1: work stopped, and only this person can
    restart it.

Each of those is an artefact of a decision the model made, not a reading of
what anybody said. There is no look at the title, no words, no categories: a
conversation about a mortgage and a conversation about a driving licence are
treated identically, and what separates them is only whether ORA went on to do
something that is still open.

Everything else is history. It is in the conversation list, where a person can
find it; it is not on their plate.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from home.models import HomeAction, HomeItem, ReasonFactor

logger = logging.getLogger("ora.home.adapters.conversation")


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

    blocked = await _sessions_with_an_open_question(db, user_id, sessions)

    for s in sessions:
        reason = _what_it_left_behind(s, blocked)
        if reason is None:
            # An exchange. It happened; it is not owed.
            continue
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
                "work_reason": reason,
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


async def _sessions_with_an_open_question(db, user_id: str, sessions: List[Dict[str, Any]]) -> set:
    """
    Which of these are stopped on something only this person can answer.

    V3.1's own record, read as it was written: an OpenQuestion means work
    halted. Home has to be able to bring somebody back to it.
    """
    out: set = set()
    try:
        from waiting.service import get_waiting_service

        service = get_waiting_service(db)
    except Exception as e:
        logger.info("open questions unavailable: %s", type(e).__name__)
        return out
    for s in sessions:
        sid = s.get("id")
        if not sid:
            continue
        try:
            if await service.open_for_session(user_id, sid):
                out.add(sid)
        except Exception as e:
            logger.info("open question read soft-fail: %s", type(e).__name__)
    return out


def _what_it_left_behind(session: Dict[str, Any], blocked: set) -> Optional[str]:
    """The reason this conversation is still owed, or None if it is not."""
    if session.get("id") in blocked:
        return "confirmation_required"
    if session.get("action_session_id"):
        # A guided flow is part-way through: steps exist and are unfinished.
        return "user_request"
    ai_state = (session.get("meta") or {}).get("ai_core") or {}
    if ai_state.get("active_plan_id") or session.get("project_id"):
        # ORA drew something up. That is a commitment on the page.
        return "goal_blocker"
    # `active_goal` is deliberately not consulted. The model fills it on every
    # turn as a running description of what is being talked about — the purely
    # informational session carried "Conoscere il costo medio della revisione
    # auto" in exactly the same field as the one that carried a real plan — so
    # reading it as a goal is how a question became a task.
    return None


def _default_summary(intent: str | None) -> str:
    if intent == "travel":
        return "Stavamo organizzando la tua vacanza."
    if intent == "study":
        return "Stavamo preparando il tuo esame."
    return "Hai una guida ORA da completare."
