"""Revision-bound continuation of the same autonomous goal.

The opportunity owns the durable review request. A changed source invalidates
preparation, pending steps and old evidence, but keeps the history and goal ID.
"""
from datetime import datetime, timezone


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
    goal.status = "abandoned" if closed else "active"
    goal.rationale = "La segnalazione di partenza è stata chiusa." if closed else "Rivaluto il lavoro con le informazioni aggiornate."
    goal.next_run_at = None if closed else datetime.now(timezone.utc).isoformat()
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
    if not goal.opportunity_revision:
        return False
    row = await current_source(db, goal)
    if not row or row.get("status") != "active" or row.get("agent_review_revision") != goal.opportunity_revision:
        return True
    if row.get("valid_until"):
        expiry = datetime.fromisoformat(row["valid_until"])
        return (expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc)
    return False
