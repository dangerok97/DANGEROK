"""Revision-bound continuation of the same autonomous goal.

The opportunity owns the durable review request. A changed source invalidates
preparation, pending steps and old evidence, but keeps the history and goal ID.
"""
from datetime import datetime, timezone


def _situation_id(goal):
    if goal.source_kind not in ("situation_initial_review", "situation_followup"):
        return None
    refs = [ref.split(":", 1)[1] for ref in goal.source_refs if ref.startswith("situation:")]
    return refs[0] if len(refs) == 1 else None


async def _situation_state(db, goal):
    sid = _situation_id(goal)
    if sid is None:
        return None
    return await db.situations.find_one({"id": sid, "user_id": goal.owner_id}, {"_id": 0})


def _attention_closed(row, goal):
    if not row or row.get("status") not in ("active", "changed"):
        return True
    if row.get("attention_intent") or row.get("next_check_summary"):
        return False
    if goal.source_situation.get("attention_expected") == "true":
        return True
    # An explicit checkpoint can be requested on a plain active Situation.
    # Absence from the start is different from a subsequent withdrawal.
    try:
        snapshot_revision = int(goal.source_situation.get("situation_revision")
                                or goal.source_situation.get("attention_epoch") or 0)
    except (TypeError, ValueError):
        snapshot_revision = 0
    for event in reversed(row.get("history") or []):
        if event.get("revision", 0) <= snapshot_revision:
            continue
        changes = event.get("changes") or {}
        if any(key in changes for key in ("attention_intent", "next_check_summary")):
            if event.get("operation") != "create" or any(
                changes.get(key) for key in ("attention_intent", "next_check_summary")
            ):
                return True
    return (goal.source_kind == "situation_initial_review"
            and goal.source_situation.get("attention_expected") != "false")


async def _refresh_situation(service, goal):
    """A revoked or revised Situation fences work already queued or in flight."""
    row = await _situation_state(service.db, goal)
    closed = _attention_closed(row, goal)
    revision = str((row or {}).get("revision") or "")
    prior = goal.source_situation.get("situation_revision")
    if not closed and revision == prior:
        return False
    if not closed and not prior:
        # Bind pre-existing watches without discarding their already chosen
        # checkpoint. New/re-admitted watches are fenced at creation time.
        goal.source_situation.update(
            situation_id=_situation_id(goal), situation_revision=revision,
            attention_expected="true" if row.get("attention_intent") or row.get("next_check_summary") else "false",
        )
        await service.repo.save_goal(goal)
        return False

    plan = await service.repo.plan_for(goal.owner_id, goal.id)
    if plan:
        for step in plan.steps:
            if step.status in ("pending", "blocked", "waiting", "running"):
                step.status = "skipped"
                step.note = "La situazione è cambiata o il monitoraggio è stato revocato."
        plan.status = "cancelled"
        await service.repo.save_plan(plan)
    await service.db.agent_evidence.update_many(
        {"owner_id": goal.owner_id, "goal_id": goal.id},
        {"$set": {"superseded": True}},
    )
    await service.needs.close_for_goal(goal.owner_id, goal.id, why="Situazione aggiornata")
    goal.prepared_text, goal.prepared_sources = "", []
    goal.situation_outcome = None
    goal.requires_user_input = goal.requires_user_authority = False
    goal.background_runs = 0
    goal.user_deferred_until = None
    now = datetime.now(timezone.utc)
    goal.status = "cancelled" if closed else "active"
    goal.next_run_at = None if closed else now.isoformat()
    goal.rationale = ("Il monitoraggio di questa situazione è stato chiuso."
                      if closed else "Rivaluto la situazione con le informazioni aggiornate.")
    if not closed:
        goal.source_kind = "situation_initial_review"
        goal.source_situation.update(
            situation_id=_situation_id(goal), situation_revision=revision,
            attention_started_at=now.isoformat(),
            attention_expected="true" if row.get("attention_intent") or row.get("next_check_summary") else "false",
        )
        goal.objective = str(row.get("desired_outcome") or row.get("summary") or goal.objective)[:280]
        goal.desired_outcome = str(row.get("desired_outcome") or row.get("attention_intent")
                                   or row.get("next_check_summary") or goal.desired_outcome)[:400]
        goal.source_refs = [f"situation:{row['id']}", *list(row.get("linked_object_refs") or [])][:8]
    await service.repo.save_goal(goal)
    from ambient.repository import AmbientRepository
    wakes = AmbientRepository(service.db)
    await wakes.cancel_for(goal.owner_id, source_ref=f"goal:{goal.id}")
    latest = await service.repo.get_goal(goal.owner_id, goal.id)
    if latest and latest.is_open:
        from ambient.service import AmbientService
        await AmbientService(service.db).schedule(
            goal.owner_id, reason="opportunity_revisit", when=now,
            source_ref=f"goal:{goal.id}", provenance="code_schedule",
        )
        latest = await service.repo.get_goal(goal.owner_id, goal.id)
    if latest is None or not latest.is_open:
        # A user can cancel without taking the runner lease. Never leave a
        # newly inserted wake behind after that cancellation won the race.
        goal.status = latest.status if latest else "cancelled"
        goal.next_run_at = None
        await wakes.cancel_for(goal.owner_id, source_ref=f"goal:{goal.id}")
    await service.repo.journal(goal.owner_id, goal.id, kind="situation_source_refreshed",
                               note=goal.rationale, detail={"closed": closed, "revision": revision})
    return True


def context(row):
    return {key: str(row.get(key) or "")[:600] for key in (
        "semantic_summary", "why_it_matters", "why_now", "what_ora_can_do")}


async def queue_existing(db, owner, opportunity_id, row, *, now=None):
    if not row or not row.get("agent_review_revision"):
        return
    moment = now or datetime.now(timezone.utc)
    closed = row.get("status") != "active"
    if row.get("valid_until"):
        expiry = datetime.fromisoformat(row["valid_until"])
        closed = closed or (expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)) <= moment
    query = {
        "owner_id": owner, "opportunity_id": opportunity_id,
        "origin": "agent_initiated", "status": {"$in": ["active", "waiting", "proposed"]},
    }
    if not closed:
        query["opportunity_revision"] = {"$ne": row["agent_review_revision"]}
    await db.agent_goals.update_many(query, {"$set": {"source_review_pending": row["agent_review_revision"],
                 "next_run_at": moment.isoformat()}})


async def current_source(db, goal):
    if not goal.opportunity_id or goal.origin != "agent_initiated":
        return None
    return await db.opportunities.find_one({"id": goal.opportunity_id, "owner_id": goal.owner_id})


async def refresh(service, goal):
    """Called only while holding the existing goal lease, before any new work."""
    if _situation_id(goal) is not None:
        return await _refresh_situation(service, goal)
    row = await current_source(service.db, goal)
    if row is None and not goal.opportunity_revision:
        return False  # Older/manual goals have no enforced source revision.
    if not goal.opportunity_id or goal.origin != "agent_initiated":
        return False
    revision = str((row or {}).get("agent_review_revision") or "")
    closed = not row or row.get("status") in ("dismissed", "suppressed", "resolved", "expired")
    if row and row.get("valid_until"):
        expiry = datetime.fromisoformat(row["valid_until"])
        closed = closed or (expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc)
    if revision == goal.opportunity_revision and not closed:
        return False

    plan = await service.repo.plan_for(goal.owner_id, goal.id)
    if plan:
        for step in plan.steps:
            if step.status in ("pending", "blocked", "waiting"):
                step.status = "skipped"
                step.note = "Le informazioni di partenza sono cambiate."
        plan.status = "cancelled"
        await service.repo.save_plan(plan)
    await service.db.agent_evidence.update_many(
        {"owner_id": goal.owner_id, "goal_id": goal.id},
        {"$set": {"superseded": True}},
    )
    await service.needs.close_for_goal(goal.owner_id, goal.id, why="Informazioni aggiornate")
    goal.prepared_text, goal.prepared_sources = "", []
    goal.requires_user_input = goal.requires_user_authority = False
    goal.opportunity_revision = revision
    goal.source_situation = context(row or {})
    goal.background_runs = 0

    now = datetime.now(timezone.utc)
    deferred_until = None
    if goal.user_deferred_until:
        try:
            parsed = datetime.fromisoformat(goal.user_deferred_until)
            parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            if parsed > now and not closed:
                deferred_until = parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            deferred_until = None

    goal.status = "abandoned" if closed else ("waiting" if deferred_until else "active")
    goal.rationale = "La segnalazione di partenza è stata chiusa." if closed else "Rivaluto il lavoro con le informazioni aggiornate."
    goal.next_run_at = None if closed else (deferred_until or now.isoformat())
    goal.user_deferred_until = None if closed else deferred_until
    if row:
        from agent.source_refs import expand_opportunity_source_refs
        goal.source_refs = await expand_opportunity_source_refs(
            service.db, goal.owner_id, row.get("evidence", [])
        )
        goal.why_now = str(row.get("why_now") or "")[:400]
    await service.repo.save_goal(goal)
    await service.db.agent_goals.update_one(
        {"id": goal.id, "owner_id": goal.owner_id, "source_review_pending": revision},
        {"$unset": {"source_review_pending": ""}},
    )
    await service.repo.journal(goal.owner_id, goal.id, kind="source_refreshed", note=goal.rationale)
    return True


async def changed(db, goal):
    if _situation_id(goal) is not None:
        row = await _situation_state(db, goal)
        prior = goal.source_situation.get("situation_revision")
        return _attention_closed(row, goal) or bool(prior and str(row.get("revision") or "") != prior)
    if not goal.opportunity_revision:
        return False
    row = await current_source(db, goal)
    if not row or row.get("status") != "active" or row.get("agent_review_revision") != goal.opportunity_revision:
        return True
    if row.get("valid_until"):
        expiry = datetime.fromisoformat(row["valid_until"])
        return (expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc)
    return False
