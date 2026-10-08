"""V137 — Multiple backend workers must not race the shared due-goal cursor.

Use the real Mongo lease semantics through synthetic mongomock-motor data.
No AI, external notifications, provider calls or real accounts.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.background import recover_due, _RECOVERY_CURSOR
from ambient.repository import AmbientRepository
from ambient.service import AmbientService


def due(minutes=3):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def goal(owner, identifier, timestamp):
    return {
        "id": identifier, "owner_id": owner, "status": "active",
        "next_run_at": timestamp, "requires_user_input": False,
        "requires_user_authority": False,
    }


@pytest.mark.asyncio
async def test_concurrent_recovery_runners_claim_only_one_global_cursor():
    db = AsyncMongoMockClient().v137_global_cursor_competition
    await AmbientRepository(db).ensure_indexes()
    await db.agent_goals.insert_many([
        goal("alice", "goal_one", due()),
        goal("bob", "goal_two", due()),
    ])
    entered, release = asyncio.Event(), asyncio.Event()
    original = AmbientService.schedule
    calls = []

    async def hold_first(self, owner_id, **kwargs):
        calls.append(owner_id)
        if len(calls) == 1:
            entered.set()
            await release.wait()
        return await original(self, owner_id, **kwargs)

    now = datetime.now(timezone.utc)
    with patch.object(AmbientService, "schedule", hold_first):
        first = asyncio.create_task(recover_due(
            db, now=now, limit=2, admit=False
        ))
        await asyncio.wait_for(entered.wait(), 3)
        try:
            # The other replica cannot consume the cursor or duplicate wakes
            # while the first backend replica still owns its Mongo lease.
            assert await recover_due(
                db, now=now, limit=2, admit=False,
            ) == 0
            row = await db.agent_goal_wake_recovery_progress.find_one({
                "_id": _RECOVERY_CURSOR,
            })
            assert row["lease_token"] and row["lease_until"]
        finally:
            release.set()
        assert await first == 2
    assert await db.ambient_wakes.count_documents({"status": "pending"}) == 2
    row = await db.agent_goal_wake_recovery_progress.find_one({
        "_id": _RECOVERY_CURSOR,
    })
    assert "lease_token" not in row and "lease_until" not in row
    assert await recover_due(db, now=now, limit=2, admit=False) == 0


@pytest.mark.asyncio
async def test_dead_worker_lease_is_recovered_after_expiry_without_resetting_cursor():
    db = AsyncMongoMockClient().v137_dead_cursor_worker
    await AmbientRepository(db).ensure_indexes()
    now = datetime.now(timezone.utc)
    await db.agent_goals.insert_one(goal("alice", "goal_after_dead_worker", due()))
    await db.agent_goal_wake_recovery_progress.insert_one({
        "_id": _RECOVERY_CURSOR,
        "after_time": "", "after_owner": "", "after_id": "",
        "lease_token": "synthetic_dead_worker",
        "lease_until": (now + timedelta(seconds=30)).isoformat(),
    })
    assert await recover_due(db, now=now, limit=1, admit=False) == 0
    assert await recover_due(
        db, now=now + timedelta(seconds=31), limit=1, admit=False,
    ) == 1
    row = await db.agent_goal_wake_recovery_progress.find_one({
        "_id": _RECOVERY_CURSOR,
    })
    assert "lease_token" not in row
    assert row["after_id"] == "goal_after_dead_worker"


@pytest.mark.asyncio
async def test_exception_releases_only_current_claim_and_keeps_cursor_retryable():
    db = AsyncMongoMockClient().v137_cursor_error_recovery
    await AmbientRepository(db).ensure_indexes()
    now = datetime.now(timezone.utc)
    await db.agent_goals.insert_one(goal("alice", "goal_retry", due()))

    async def throw(*args, **kwargs):
        raise ConnectionError("simulated transient Mongo scheduling outage")

    with patch.object(AmbientService, "schedule", throw):
        with pytest.raises(ConnectionError):
            await recover_due(db, now=now, limit=1, admit=False)
    saved = await db.agent_goal_wake_recovery_progress.find_one({
        "_id": _RECOVERY_CURSOR,
    })
    assert not saved.get("lease_token")
    assert not saved.get("after_id")
    assert await recover_due(db, now=now, limit=1, admit=False) == 1


@pytest.mark.asyncio
async def test_require_both_permission_flags_false_before_ordinary_recovery():
    db = AsyncMongoMockClient().v137_authority_gate_unchanged
    await AmbientRepository(db).ensure_indexes()
    timestamp = due()
    await db.agent_goals.insert_many([
        {**goal("alice", "requires_reply", timestamp),
         "requires_user_input": True},
        {**goal("bob", "requires_authority", timestamp),
         "requires_user_authority": True},
        goal("charlie", "no_authority_needed", timestamp),
    ])
    assert await recover_due(db, admit=False) == 1
    rows = await db.ambient_wakes.find({}, {"_id": 0}).to_list(None)
    assert len(rows) == 1 and rows[0]["owner_id"] == "charlie"
    await db.agent_goals.update_one(
        {"id": "requires_authority"},
        {"$set": {"source_review_pending": "synthetic-changed-source"}},
    )
    # Recheck of changed source is allowed; the execution gate still holds.
    assert await recover_due(db, admit=False) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": "bob", "status": "pending",
    }) == 1
