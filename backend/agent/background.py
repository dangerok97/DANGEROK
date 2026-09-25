"""Connect the existing opportunity/agent loop to the durable ambient runtime."""
from datetime import datetime, timezone
import logging

from ambient.models import WakeOutcome

logger = logging.getLogger(__name__)


async def consider_opportunities(db, owner_id, scan):
    from agent.admission import drain
    # scan is only an accelerator; durable opportunity records own the work.
    await drain(db, owner_id=owner_id)


async def recover_due(db, *, now=None, limit=2, admit=True):
    """Recover the write-to-wake gap, bounded and ordered by oldest due work.

    Only explicitly scheduled goals qualify. Never auto-run legacy goals or
    anything waiting for a person's answer/authority. The existing goal lease
    remains the execution lock; this function only arranges wakes.
    """
    from ambient.service import AmbientService
    from agent.admission import drain
    moment = now or datetime.now(timezone.utc)
    if admit:
        await drain(db, now=moment, limit=limit)
    rows = await db.agent_goals.find({
        "status": {"$in": ["active", "waiting"]},
        "next_run_at": {"$type": "string", "$lte": moment.isoformat()},
        "requires_user_input": {"$ne": True},
        "requires_user_authority": {"$ne": True},
    }, {"_id": 0, "id": 1, "owner_id": 1}).sort("next_run_at", 1).to_list(limit)
    scheduled = 0
    for row in rows:
        ref = f"goal:{row['id']}"
        if await db.ambient_wakes.find_one({
            "owner_id": row["owner_id"], "source_ref": ref,
            "status": {"$in": ["pending", "claimed"]},
        }, {"_id": 1}):
            continue
        wake = await AmbientService(db).schedule(
            row["owner_id"], reason="opportunity_revisit", when=moment,
            source_ref=ref,
        )
        scheduled += bool(wake)
    return scheduled


async def advance_wake(db, wake):
    from agent.service import AgentService
    service = AgentService(db)
    goal_id = wake.source_ref.removeprefix("goal:")
    goal = await service.repo.get_goal(wake.owner_id, goal_id)
    outcome = WakeOutcome(wake_id=wake.id, reason=wake.reason, handled=True)
    if goal is None or not goal.is_open:
        outcome.result = "goal_closed"
        return outcome
    if goal.requires_user_input or goal.requires_user_authority:
        outcome.result = "waiting_for_person"
        return outcome
    now = datetime.now(timezone.utc)
    if goal.next_run_at and goal.next_run_at > now.isoformat():
        outcome.result = "goal_not_due"
        return outcome
    result = await service.advance(wake.owner_id, goal_id, worker_id=f"ambient:{wake.id}")
    outcome.result = str(result.get("state") or result.get("reason") or "advanced")[:80]
    if outcome.result == "already_running":
        outcome.retry_after_seconds = 300
    logger.info("background_goal result=%s", outcome.result)
    return outcome
