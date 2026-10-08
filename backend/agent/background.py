"""Connect the existing opportunity/agent loop to the durable ambient runtime."""
from datetime import datetime, timezone
import logging

from ambient.models import WakeOutcome

logger = logging.getLogger(__name__)


async def consider_opportunities(db, owner_id, scan):
    from agent.admission import drain
    # scan is only an accelerator; durable opportunity records own the work.
    await drain(db, owner_id=owner_id)


# Existing ambient lane; a bounded indexed page visits all due goals over
# successive cycles. Old goals with pending wakes cannot hide later goals.
_RECOVERY_PAGE = 32
_RECOVERY_MAX_PAGE = 128
_RECOVERY_CURSOR = "agent_goal_wake_recovery_cursor"


async def recover_due(db, *, now=None, limit=2, admit=True):
    """Recover due goals after bounded passes, even behind existing wakes.

    Previously the query fetched the oldest limit rows before checking for
    existing wakes. Two permanently pending old wakes could hide newer goals.
    The cursor and bounded keyset paging prevent this starvation without a
    new scheduler, unlimited database scans, or extra model calls.
    """
    from ambient.service import AmbientService
    from agent.admission import drain

    moment = now or datetime.now(timezone.utc)
    capacity = max(1, min(int(limit or 1), 10))
    if admit:
        await drain(db, now=moment, limit=capacity)

    due_query = {
        "status": {"$in": ["active", "waiting"]},
        "next_run_at": {"$type": "string", "$lte": moment.isoformat()},
        "$or": [
            {"requires_user_input": {"$ne": True},
             "requires_user_authority": {"$ne": True}},
            {"source_review_pending": {"$type": "string", "$gt": ""}},
        ],
    }
    page_size = min(_RECOVERY_MAX_PAGE, max(_RECOVERY_PAGE, capacity * 16))
    state_collection = db.agent_goal_wake_recovery_progress
    stored = await state_collection.find_one({"_id": _RECOVERY_CURSOR}) or {}
    after_time = str(stored.get("after_time") or "")
    after_id = str(stored.get("after_id") or "")

    async def page(query):
        return await db.agent_goals.find(
            query, {"_id": 0, "id": 1, "owner_id": 1,
                    "next_run_at": 1},
        ).sort([("next_run_at", 1), ("id", 1)]).limit(page_size).to_list(page_size)

    query = due_query
    if after_time and after_id:
        query = {
            "$and": [
                due_query,
                {"$or": [
                    {"next_run_at": {"$gt": after_time}},
                    {"next_run_at": after_time, "id": {"$gt": after_id}},
                ]},
            ],
        }
    rows = await page(query)
    if not rows and after_time:
        rows = await page(due_query)
    if not rows:
        return 0

    refs = [f"goal:{row['id']}" for row in rows if row.get("id")]
    active = await db.ambient_wakes.find({
        "source_ref": {"$in": refs},
        "status": {"$in": ["pending", "claimed"]},
    }, {"_id": 0, "owner_id": 1, "source_ref": 1}).to_list(page_size)
    already = {
        (str(wake.get("owner_id")), str(wake.get("source_ref")))
        for wake in active
    }
    candidates = [
        row for row in rows
        if row.get("id") and row.get("owner_id")
        and (str(row["owner_id"]), f"goal:{row['id']}") not in already
    ]

    selected = []
    chosen_ids = set()
    seen_owners = set()
    # First give different owners a chance, then fill unused batch capacity.
    for row in candidates:
        owner = str(row["owner_id"])
        if owner not in seen_owners:
            selected.append(row)
            chosen_ids.add((owner, str(row["id"])))
            seen_owners.add(owner)
            if len(selected) == capacity:
                break
    if len(selected) < capacity:
        for row in candidates:
            key = (str(row["owner_id"]), str(row["id"]))
            if key not in chosen_ids:
                selected.append(row)
                chosen_ids.add(key)
                if len(selected) == capacity:
                    break

    scheduled = 0
    for row in selected:
        wake = await AmbientService(db).schedule(
            row["owner_id"], reason="opportunity_revisit",
            when=moment, source_ref=f"goal:{row['id']}",
        )
        scheduled += bool(wake)

    last = rows[-1]
    await state_collection.update_one(
        {"_id": _RECOVERY_CURSOR},
        {"$set": {
            "after_time": str(last.get("next_run_at") or ""),
            "after_id": str(last.get("id") or ""),
            "last_scan_at": moment.isoformat(),
        }},
        upsert=True,
    )
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
    if goal.source_kind == "situation_followup":
        from situations.repository import SituationRepository
        refs = [ref for ref in goal.source_refs if ref.startswith("situation:")]
        source = await SituationRepository(db).get(wake.owner_id, refs[0].split(":", 1)[1]) if len(refs) == 1 else None
        if source is None or source.status not in ("active", "changed"):
            await service.cancel(wake.owner_id, goal.id, reason="La situazione non è più attiva.")
            outcome.result = "situation_closed"
            return outcome
    if (goal.requires_user_input or goal.requires_user_authority) and not goal.source_review_pending:
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
