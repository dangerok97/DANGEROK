"""Admit a model-authored Situation attention intent into the existing Agent/Ambient lane.

This is an INITIAL REVIEW, NOT a monitoring check, weather forecast, or
notification. The first *real* checkpoint is chosen by the cognitive agent
after its source reads. No default drying/wait time and no domain classifier.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from agent.models import AutonomousGoal
from agent.repository import AgentRepository
from ambient.service import AmbientService
from situations.repository import SituationRepository
from situations.followup import _enabled, goal_id_for

logger = logging.getLogger("ora.situations.admission")
INITIAL_KIND = "situation_initial_review"


async def ensure_initial_review(db, owner: str, sid: str) -> dict:
    """Persist exactly one owner-scoped initial review for an attention intent.

    The stable id makes retries idempotent. An existing dedicated scheduled
    check always wins; a closed/cancelled Situation cannot resurrect work.
    """
    if not _enabled():
        return {"status": "runtime_disabled"}
    situation = await SituationRepository(db).get(owner, sid)
    if situation is None or situation.status not in ("active", "changed"):
        return {"status": "not_active"}
    if not (situation.attention_intent or situation.next_check_summary):
        return {"status": "no_attention"}

    ref = f"situation:{sid}"
    gid = goal_id_for(owner, sid)
    repo = AgentRepository(db)
    existing = await repo.get_goal(owner, gid)
    if existing:
        return {"status": "already_admitted", "goal_id": gid}

    # Do not introduce a second watch if a legacy agent already owns this
    # Situation. The existing goal remains responsible for its own timeline.
    other = await db.agent_goals.find_one(
        {"owner_id": owner, "source_refs": ref,
         "status": {"$in": ["proposed", "active", "waiting"]}},
        {"_id": 0, "id": 1},
    )
    if other:
        return {"status": "already_pursuing", "goal_id": str(other.get("id") or "")}

    now = datetime.now(timezone.utc)
    goal = AutonomousGoal(
        id=gid, owner_id=owner, status="active", origin="agent_initiated",
        objective=(f"Rivalutare la situazione temporanea: {situation.summary}")[:280],
        desired_outcome=(
            str(situation.attention_intent or situation.next_check_summary)
            + "; individuare con fonti verificabili se e quando serve agire"
        )[:400],
        why_now="La situazione ha un'intenzione di attenzione ancora aperta.",
        success_criteria=[
            "Usare le fonti pertinenti disponibili, senza inventare condizioni o tempi.",
            "Scegliere un controllo successivo solo se ha un'utilità concreta.",
            "Un risultato fisico non si presume dal tempo trascorso.",
        ],
        stop_conditions=[
            "La situazione viene risolta, annullata o l'attenzione revocata.",
            "L'AI conclude il lavoro con un risultato utile verificabile.",
        ],
        source_kind=INITIAL_KIND,
        source_refs=[ref, *list(situation.linked_object_refs or [])][:8],
        next_run_at=now.isoformat(),
        rationale=str(situation.attention_intent or situation.next_check_summary)[:300],
        decision_provenance="model",
    )
    created = await repo.create_goal(goal)
    if created is None:
        # Check the database: uniqueness rejection and unavailable storage are
        # distinct outcomes, neither is permission to report a scheduled check.
        current = await repo.get_goal(owner, gid)
        return {"status": "already_admitted" if current else "persistence_failed",
                "goal_id": gid if current else None}

    wake = await AmbientService(db).schedule(
        owner, reason="opportunity_revisit", when=now,
        source_ref=f"goal:{gid}", provenance="code_schedule",
    )
    if wake is None:
        # The goal remains durable and eligible for the existing recovery
        # sweep; explicitly mark the missing executable wake.
        logger.warning("situation initial review wake not confirmed")
        return {"status": "recovery_pending", "goal_id": gid}
    return {"status": "review_queued", "goal_id": gid}
