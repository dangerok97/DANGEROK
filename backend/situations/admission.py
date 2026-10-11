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
from situations.followup import (
    INITIAL_KIND, KIND, _enabled, _moment, cancel_dedicated_followup,
    goal_id_for, read_followup, repair_missing_dedicated_wakes,
)

logger = logging.getLogger("ora.situations.admission")


def _attentive(situation) -> bool:
    return bool(
        situation and situation.status in ("active", "changed")
        and (
            str(situation.attention_intent or "").strip()
            or str(situation.next_check_summary or "").strip()
        )
    )


def _renewed_intent(situation, goal) -> str | None:
    """A new explicit attention request may start a new cycle after a stop.

    A new title, a recovery sweep or the old intent left in storage cannot
    override a terminal goal. Keep the previous history; require a later
    user-authored positive attention update, not just any Situation revision.
    """
    stopped_at = _moment(goal.updated_at)
    if stopped_at is None:
        return None
    for event in reversed(situation.history):
        at = _moment(event.at)
        if event.source != "user_conversation" or at is None or at <= stopped_at:
            continue
        if any(str(event.changes.get(field) or "").strip()
               for field in ("attention_intent", "next_check_summary")):
            return str(event.revision)
    return None


def _review_goal(owner, situation, gid, *, epoch=None, created_at=None):
    now = datetime.now(timezone.utc).isoformat()
    return AutonomousGoal(
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
        source_refs=[f"situation:{situation.id}", *list(situation.linked_object_refs or [])][:8],
        source_situation={
            "situation_id": situation.id,
            "situation_revision": str(situation.revision),
            "attention_epoch": str(epoch or situation.revision),
            "attention_started_at": now,
            "attention_expected": "true",
        },
        next_run_at=now, created_at=created_at or now,
        rationale=str(situation.attention_intent or situation.next_check_summary)[:300],
        decision_provenance="model",
    )


async def ensure_initial_review(db, owner: str, sid: str) -> dict:
    """Persist exactly one owner-scoped initial review for an attention intent.

    The stable id makes retries idempotent. An existing dedicated scheduled
    check always wins; a closed/cancelled Situation cannot resurrect work.
    """
    if not _enabled():
        return {"status": "runtime_disabled"}
    if db is None or not owner or not sid:
        return {"status": "unavailable"}
    situations = SituationRepository(db)
    situation = await situations.get(owner, sid)
    if not _attentive(situation):
        return {"status": "no_attention"}

    gid = goal_id_for(owner, sid)
    repo = AgentRepository(db)
    existing = await repo.get_goal(owner, gid)
    before = await read_followup(db, owner, sid)
    if before["status"] == "unavailable":
        return {"status": "unavailable"}
    # Reuse a typed legacy Situation watch. A generic goal is independent:
    # preserve it if it really has an execution/input to wait for, otherwise
    # leave it untouched and record why this dedicated review is needed.
    other_id = before.get("goal_id")
    if existing is None and other_id:
        if before.get("goal_source_kind") in (KIND, INITIAL_KIND):
            gid = other_id
        elif before["status"] != "not_scheduled":
            return {"status": "already_pursuing", "goal_id": other_id}

    worker = f"schedule:admit:{sid}"
    if not await repo.claim(owner, gid, worker_id=worker):
        return {"status": "already_being_admitted", "goal_id": gid}
    try:
        situation = await situations.get(owner, sid)
        if not _attentive(situation):
            await cancel_dedicated_followup(db, owner, sid)
            return {"status": "no_attention"}
        existing = await repo.get_goal(owner, gid)
        if existing and existing.source_kind not in (KIND, INITIAL_KIND):
            return {"status": "already_pursuing", "goal_id": gid}
        renewed = _renewed_intent(situation, existing) if existing and not existing.is_open else None
        if existing and not existing.is_open and not renewed:
            return {"status": "already_stopped", "goal_id": gid}

        if existing and existing.is_open:
            state = await read_followup(db, owner, sid)
            if state["status"] in ("scheduled", "due", "running", "waiting_for_user", "review_pending"):
                return {"status": "already_admitted", "goal_id": gid}
            if existing.source_kind == KIND and existing.next_run_at:
                await repair_missing_dedicated_wakes(db, owner)
                state = await read_followup(db, owner, sid)
                return {"status": "already_admitted" if state["status"] in ("scheduled", "due", "running")
                        else "recovery_pending", "goal_id": gid}
            if (existing.background_runs >= 3
                    and existing.source_situation.get("situation_revision") == str(situation.revision)):
                return {"status": "review_paused", "goal_id": gid}

        if existing and existing.is_open and existing.source_kind == INITIAL_KIND and existing.next_run_at:
            goal = existing  # Repair the original assessment; no new judgment.
        else:
            goal = _review_goal(owner, situation, gid, epoch=renewed,
                                created_at=existing.created_at if existing else None)
            if existing:
                # Holding the same execution lease excludes an older runner.
                # Only the terminal version inspected above can be restarted.
                changed = await db.agent_goals.update_one(
                    {"id": gid, "owner_id": owner, "status": existing.status,
                     "updated_at": existing.updated_at},
                    {"$set": goal.model_dump()},
                )
                if not changed.matched_count:
                    return {"status": "source_changed", "goal_id": gid}
                await db.agent_plans.update_many(
                    {"owner_id": owner, "goal_id": gid, "status": {"$ne": "cancelled"}},
                    {"$set": {"status": "cancelled"}},
                )
                await db.agent_evidence.update_many(
                    {"owner_id": owner, "goal_id": gid}, {"$set": {"superseded": True}},
                )
                from ambient.repository import AmbientRepository
                await AmbientRepository(db).cancel_for(owner, source_ref=f"goal:{gid}")
                await repo.journal(owner, gid, kind="situation_review_reopened",
                                   note="Nuova valutazione dopo un aggiornamento dell'attenzione.",
                                   detail={"situation_id": sid, "revision": situation.revision,
                                           "previous_status": existing.status})
            elif await repo.create_goal(goal) is None:
                current = await repo.get_goal(owner, gid)
                return {"status": "already_admitted" if current and current.is_open else "persistence_failed",
                        "goal_id": gid if current else None}
            elif other_id and other_id != gid:
                await repo.journal(owner, gid, kind="situation_review_admitted",
                                   note="Il lavoro generico collegato non aveva un'esecuzione o una richiesta in attesa.",
                                   detail={"situation_id": sid, "unattended_goal_id": other_id})

        # Cancellation can complete before the goal is inserted. A second
        # owned read after persistence closes that race before any wake exists.
        fresh = await situations.get(owner, sid)
        current = await repo.get_goal(owner, gid)
        if not _attentive(fresh) or not current or not current.is_open:
            await cancel_dedicated_followup(db, owner, sid)
            return {"status": "no_attention", "goal_id": gid}
        wake = await AmbientService(db).schedule(
            owner, reason="opportunity_revisit", when=_moment(goal.next_run_at) or datetime.now(timezone.utc),
            source_ref=f"goal:{gid}", provenance="code_schedule",
        )
        fresh = await situations.get(owner, sid)
        current = await repo.get_goal(owner, gid)
        if not _attentive(fresh) or not current or not current.is_open:
            await cancel_dedicated_followup(db, owner, sid)
            return {"status": "no_attention", "goal_id": gid}
        if wake and current.next_run_at != wake.scheduled_for:
            current.next_run_at = wake.scheduled_for
            await repo.save_goal(current)
        state = await read_followup(db, owner, sid)
        if state["status"] == "review_pending":
            return {"status": "review_queued", "goal_id": gid}
        return {"status": "recovery_pending", "goal_id": gid}
    finally:
        await repo.release(gid, stopped_because="initial_review_admission", worker_id=worker)


async def recover_unadmitted_attention(db, owner: str, *, limit: int = 8) -> dict:
    """Give existing, unattended Situations the same first admission as new ones.

    The previous system could persist attention_intent but create no Agent
    goal. Replaying a generic opportunity review was not sufficient: a model
    may return silence, leaving the Situation indefinitely without any work.
    This bounded owner-scoped sweep only admits intents already saved by
    cognition, and creates NO physical checkpoint by itself.
    """
    if not _enabled():
        return {"queued": 0, "reason": "runtime_disabled"}
    count = max(1, min(8, int(limit)))
    rows = await db.situations.find(
        {"user_id": owner, "status": {"$in": ["active", "changed"]},
         "$or": [
             {"attention_intent": {"$type": "string", "$regex": r"\S"}},
             {"next_check_summary": {"$type": "string", "$regex": r"\S"}},
         ]},
        {"_id": 0, "id": 1},
    ).sort("updated_at", -1).to_list(count)
    queued = 0
    for row in rows:
        sid = str(row.get("id") or "")
        if not sid:
            continue
        outcome = await ensure_initial_review(db, owner, sid)
        if outcome.get("status") == "review_queued":
            queued += 1
    return {"queued": queued}
