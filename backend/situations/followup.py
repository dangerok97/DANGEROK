"""A persisted Situation is not a scheduled check. Reuse the existing Agent/Ambient runtime.

Cognition chooses the purpose, notification condition and first checkpoint. This
module validates ownership/lifecycle and reports only persisted execution state.
No prose classification, domain timers, new worker or external write authority.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

from agent.models import AutonomousGoal
from agent.repository import AgentRepository
from ambient.service import AmbientService
from conversation_engine.ai_core.models import Observation
from situations.repository import SituationRepository

OPEN = ("proposed", "active", "waiting")
KIND = "situation_followup"


def _moment(value):
    try:
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def _enabled():
    return os.environ.get("AMBIENT_RUNTIME", "").strip().lower() in ("1", "true", "on")


def goal_id_for(owner, situation_id):
    return "gol_sit_" + hashlib.sha256(f"{owner}:{situation_id}".encode()).hexdigest()[:24]


async def read_followup(db, owner, situation_id):
    """Read back a real goal, wake and executed check, never presentation copy."""
    out = {"status": "unavailable", "next_check_at": None, "last_checked_at": None,
           "goal_id": None, "purpose": None, "notify_when": None,
           "runtime_enabled": _enabled(), "delivery_channel": "in_app",
           "delivery_note": "Gli aggiornamenti sono consultabili in ORA; nessuna push garantita."}
    if db is None or not owner or not situation_id:
        return out
    try:
        situation = await SituationRepository(db).get(owner, situation_id)
        if situation is None:
            return out
        if situation.status not in ("active", "changed"):
            return {**out, "status": "stopped"}
        ref = f"situation:{situation_id}"
        goals = await db.agent_goals.find({"owner_id": owner, "source_refs": ref,
                                           "status": {"$in": list(OPEN)}}, {"_id": 0}).sort("updated_at", -1).to_list(8)
        if not goals:
            return {**out, "status": "not_scheduled"}
        # Prefer the dedicated watch, otherwise expose legacy work rather than
        # pretending old users have no follow-up. Never match titles or keywords.
        goals.sort(key=lambda g: g.get("source_kind") != KIND)
        goal = goals[0]
        out.update(goal_id=goal["id"], purpose=str(goal.get("rationale") or "")[:300])
        arranged = await db.agent_journal.find_one(
            {"owner_id": owner, "goal_id": goal["id"], "kind": "situation_checkpoint_arranged"},
            {"_id": 0, "detail.notify_when": 1}, sort=[("at", -1)])
        if arranged:
            out["notify_when"] = str(((arranged.get("detail") or {}).get("notify_when") or ""))[:400] or None
        checked = await db.agent_journal.find_one(
            {"owner_id": owner, "goal_id": goal["id"], "kind": "step_done",
             "detail.really_happened": True, "detail.status": "succeeded"},
            {"_id": 0, "at": 1, "note": 1}, sort=[("at", -1)])
        if checked:
            out.update(last_checked_at=checked.get("at"), last_result=str(checked.get("note") or "")[:300])
        if goal.get("requires_user_input") or goal.get("requires_user_authority"):
            return {**out, "status": "waiting_for_user"}
        now = datetime.now(timezone.utc)
        running = await db.agent_runs.find_one(
            {"owner_id": owner, "goal_id": goal["id"], "lease_until": {"$gt": now.isoformat()}}, {"_id": 0, "goal_id": 1})
        # The scheduling lease is not an evidence-reading run.
        if running:
            run = await db.agent_runs.find_one({"owner_id": owner, "goal_id": goal["id"]}, {"_id": 0, "worker_id": 1})
            if not str((run or {}).get("worker_id") or "").startswith("schedule:"):
                return {**out, "status": "running" if _enabled() else "runtime_disabled"}
        due = _moment(goal.get("next_run_at"))
        if due is None:
            return {**out, "status": "not_scheduled"}
        wake = await db.ambient_wakes.find_one(
            {"owner_id": owner, "source_ref": f"goal:{goal['id']}",
             "status": {"$in": ["pending", "claimed"]}, "scheduled_for": {"$gte": due.isoformat()}},
            {"_id": 0, "scheduled_for": 1}, sort=[("scheduled_for", 1)])
        if not wake:
            return {**out, "status": "recovery_pending"}
        at = _moment(wake.get("scheduled_for"))
        if at is None:
            return out
        return {**out, "status": ("runtime_disabled" if not _enabled() else "due" if at <= now else "scheduled"),
                "next_check_at": at.isoformat()}
    except Exception:
        # A failed read is not proof that no job was scheduled.
        return out


async def arrange_followup(db, owner, *, situation_id, expected_revision, check_at, purpose, notify_when):
    """Ensure one real first checkpoint; reusing it must not move its deadline."""
    if not _enabled():
        return {"ok": False, "error": "runtime_disabled", "status": "runtime_disabled"}
    due = _moment(check_at)
    now = datetime.now(timezone.utc)
    if due is None or due < now - timedelta(minutes=1) or due > now + timedelta(hours=72):
        return {"ok": False, "error": "timezone_aware_checkpoint_within_72h_required"}
    purpose, notify_when = str(purpose or "").strip(), str(notify_when or "").strip()
    if not purpose or not notify_when or len(purpose) > 300 or len(notify_when) > 400:
        return {"ok": False, "error": "bounded_purpose_and_notification_condition_required"}
    situation = await SituationRepository(db).get(owner, situation_id)
    if not situation or situation.status not in ("active", "changed"):
        return {"ok": False, "error": "active_owned_situation_required"}
    if expected_revision != situation.revision:
        return {"ok": False, "error": "revision_conflict"}
    before = await read_followup(db, owner, situation_id)
    if before["status"] in ("scheduled", "due", "running", "waiting_for_user"):
        return {"ok": True, "reused": True, **before}
    if before["status"] == "unavailable":
        return {"ok": False, "error": "followup_state_unavailable"}
    repo = AgentRepository(db)
    gid = before.get("goal_id") or goal_id_for(owner, situation_id)
    worker = f"schedule:{situation_id}"
    if not await repo.claim(owner, gid, worker_id=worker):
        return {"ok": False, "error": "already_being_arranged", **(await read_followup(db, owner, situation_id))}
    try:
        # Re-read after the lease. Cancellation and corrections beat stale work.
        fresh = await SituationRepository(db).get(owner, situation_id)
        if not fresh or fresh.status not in ("active", "changed") or fresh.revision != expected_revision:
            return {"ok": False, "error": "situation_changed"}
        goal = await repo.get_goal(owner, gid)
        if goal and (not goal.is_open or goal.requires_user_input or goal.requires_user_authority):
            return {"ok": False, "error": "goal_not_resumable"}
        # A retry repairs the existing schedule, not a newly invented time.
        prior_due = _moment(goal.next_run_at) if goal else None
        due = max(now + timedelta(seconds=60), prior_due or due)
        if goal is None:
            outcome_hint = str(
                fresh.expected_outcome_summary
                or fresh.temporal_scope
                or "il prossimo momento utile per la persona"
            ).strip()[:220]
            goal = AutonomousGoal(
                id=gid, owner_id=owner, status="active", origin="agent_initiated",
                objective=f"Portare la situazione temporanea al suo prossimo esito utile: {fresh.summary}"[:280],
                desired_outcome=(
                    "Arrivare a una conclusione utile e verificabile per la persona, "
                    f"tenendo conto dell'esito atteso ({outcome_hint}), e comunicarla senza "
                    "continuare a monitorare quando ulteriori controlli non aggiungono valore."
                )[:400],
                why_now=purpose, rationale=purpose,
                source_kind=KIND, source_refs=[f"situation:{situation_id}", *fresh.linked_object_refs][:8],
                next_run_at=due.isoformat(),
                success_criteria=[
                    "Rileggere fonti reali pertinenti prima di decidere.",
                    "Distinguere una condizione di allarme dal momento utile in cui il monitoraggio può concludersi.",
                    "Se il momento utile non è ancora raggiunto, programmare un nuovo controllo giustificato.",
                    "Se il momento utile è raggiunto, comunicarlo e terminare il monitoraggio senza inventare che il mondo fisico sia cambiato.",
                    "Non scambiare il tempo trascorso per un esito osservato.",
                ],
                stop_conditions=[
                    "La situazione originale è risolta o annullata.",
                    "È stato raggiunto e comunicato un momento utile d'azione o ulteriori controlli non aggiungerebbero valore senza nuovo input della persona.",
                ],
                decision_provenance="model")
            if await repo.create_goal(goal) is None:
                return {"ok": False, "error": "goal_not_persisted"}
        else:
            goal.next_run_at = due.isoformat()
            await repo.save_goal(goal)
        wake = await AmbientService(db).schedule(owner, reason="opportunity_revisit", when=due,
                                                 source_ref=f"goal:{gid}", provenance="model")
        if wake and wake.scheduled_for != goal.next_run_at:
            goal.next_run_at = wake.scheduled_for
            await repo.save_goal(goal)
        await repo.journal(owner, gid, kind="situation_checkpoint_arranged", note=purpose,
                           detail={"situation_id": situation_id, "until": goal.next_run_at, "notify_when": notify_when})
    finally:
        await repo.release(gid, stopped_because="checkpoint_arranged", worker_id=worker)
    state = await read_followup(db, owner, situation_id)
    return {"ok": state["status"] in ("scheduled", "due", "running"), **state}


async def settle_completed_followup(db, owner, goal):
    """Stop monitoring while preserving the real-world Situation until confirmed.

    A completed monitoring goal means ORA reached the useful action/conclusion
    moment. It does NOT prove the physical Situation itself has ceased to exist.
    Clear only the attention/check intent so the safety net cannot restart an
    already-finished watch; the red Situation may remain until user/world evidence
    resolves it separately.
    """
    if getattr(goal, "source_kind", "") != KIND:
        return False
    refs = [str(ref) for ref in (getattr(goal, "source_refs", None) or [])
            if str(ref).startswith("situation:")]
    if len(refs) != 1:
        return False
    sid = refs[0].split(":", 1)[1]
    current = await SituationRepository(db).get(owner, sid)
    if current is None or current.status not in ("active", "changed"):
        return False
    from situations.models import SituationUpdate
    from situations.service import SituationService
    result = await SituationService(db).apply(
        user_id=owner,
        session_id=current.session_id or f"agent:{goal.id}",
        reasoning_epoch=f"followup-complete:{goal.id}",
        update=SituationUpdate(
            operation="update",
            situation_id=sid,
            expected_revision=current.revision,
            attention_intent="",
            next_check_summary="",
            source="background_agent",
        ),
    )
    return result.get("status") == "success"


async def cancel_dedicated_followup(db, owner, situation_id):
    """Close only this Situation's dedicated watch, never unrelated user plans."""
    from agent.service import AgentService
    gid = goal_id_for(owner, situation_id)
    found = await db.agent_goals.find_one({"owner_id": owner, "id": gid, "source_kind": KIND}, {"_id": 0, "id": 1})
    if found:
        await AgentService(db).cancel(owner, gid, reason="La situazione è stata risolta o annullata.")


async def get_situation_followup(args, runtime):
    state = await read_followup(runtime.get("db"), runtime.get("user_id"), str(args.get("situation_id") or ""))
    return Observation(kind="tool", name="get_situation_followup", status="ok" if state["status"] != "unavailable" else "error", payload=state)


async def schedule_situation_check(args, runtime):
    state = await arrange_followup(runtime.get("db"), runtime.get("user_id"),
        situation_id=str(args.get("situation_id") or ""), expected_revision=args.get("expected_revision"),
        check_at=args.get("check_at"), purpose=args.get("purpose"), notify_when=args.get("notify_when"))
    return Observation(kind="tool", name="schedule_situation_check", status="ok" if state.get("ok") else "error", payload=state)


def register_followup_tools(registry):
    from conversation_engine.ai_core.tools.capability import CapabilitySpec
    registry.register(CapabilitySpec(
        capability="get_situation_followup", description="Read the actual scheduled next check, last executed check and notification condition of an owned Situation. Active state or presentation copy is not a schedule. Use for when/why ORA planned to revisit or notify.",
        input_schema={"type": "object", "properties": {"situation_id": {"type": "string"}}, "required": ["situation_id"]},
        classification="personal", side_effect="READ_ONLY", freshness="fresh", handler=get_situation_followup))
    registry.register(CapabilitySpec(
        capability="schedule_situation_check", description="Persist a real first follow-up in the existing background runtime for an active Situation. Choose checkpoint and purpose from current evidence, not by asking the user to supervise ORA. Reuses existing work without postponing it. Does not send a notification, grant external write authority, or prove an outcome. Read the returned status before promising a check.",
        input_schema={"type": "object", "properties": {"situation_id": {"type": "string"}, "expected_revision": {"type": "integer"}, "check_at": {"type": "string", "description": "Timezone-aware ISO8601, within 72 hours. A recheck time, not a predicted completion."}, "purpose": {"type": "string", "maxLength": 300}, "notify_when": {"type": "string", "maxLength": 400}}, "required": ["situation_id", "expected_revision", "check_at", "purpose", "notify_when"]},
        classification="personal", side_effect="REVERSIBLE_WRITE", risk="write_soft", freshness="fresh", handler=schedule_situation_check))
