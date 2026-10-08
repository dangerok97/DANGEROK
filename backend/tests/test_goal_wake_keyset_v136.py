"""V136: keyset recovery remains complete across equal times, owners and restarts.

Synthetic data only. No model, provider, user device or external effect.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.background import recover_due, _RECOVERY_CURSOR
from agent.repository import AgentRepository
from ambient.repository import AmbientRepository


def now():
    return datetime.now(timezone.utc)


def goal(owner, identifier, due):
    return {
        "id": identifier, "owner_id": owner, "status": "active",
        "next_run_at": due,
        "requires_user_input": False, "requires_user_authority": False,
    }


def existing_wake(owner, identifier, due):
    return {
        "id": f"wake_{owner}_{identifier}", "owner_id": owner,
        "reason": "opportunity_revisit",
        "source_ref": f"goal:{identifier}", "status": "pending",
        "identity": f"synthetic:{owner}:{identifier}",
        "scheduled_for": due,
    }


@pytest.mark.asyncio
async def test_keyset_recovery_reaches_both_owners_with_same_time_and_id():
    db = AsyncMongoMockClient().wake_cursor_same_key_v136
    await AmbientRepository(db).ensure_indexes()
    moment = now()
    due = (moment - timedelta(minutes=3)).isoformat()
    rows = [
        goal("alice", f"goal_{index:03d}", due)
        for index in range(32)
    ]
    rows.append(goal("bob", "goal_031", due))
    await db.agent_goals.insert_many(rows)
    await db.ambient_wakes.insert_many(
        [existing_wake("alice", row["id"], due) for row in rows[:32]]
    )

    assert await recover_due(db, now=moment, admit=False, limit=2) == 0
    cursor = await db.agent_goal_wake_recovery_progress.find_one({
        "_id": _RECOVERY_CURSOR,
    })
    assert cursor["after_owner"] == "alice"
    assert cursor["after_id"] == "goal_031"

    # Same due time/id but DIFFERENT owner must remain visible on next page.
    assert await recover_due(db, now=moment, admit=False, limit=2) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": "bob", "source_ref": "goal:goal_031",
        "status": "pending",
    }) == 1


@pytest.mark.asyncio
async def test_legacy_two_field_cursor_restarts_without_dropping_due_work():
    db = AsyncMongoMockClient().wake_cursor_legacy_v136
    await AmbientRepository(db).ensure_indexes()
    moment = now()
    due = (moment - timedelta(minutes=1)).isoformat()
    await db.agent_goals.insert_one(goal("alice", "goal_correct", due))
    await db.agent_goal_wake_recovery_progress.insert_one({
        "_id": _RECOVERY_CURSOR,
        "after_time": due, "after_id": "goal_z_end",
    })
    # Absence of after_owner is not a partial keyset that could skip data.
    assert await recover_due(db, now=moment, admit=False) == 1
    cursor = await db.agent_goal_wake_recovery_progress.find_one({
        "_id": _RECOVERY_CURSOR,
    })
    assert cursor["after_owner"] == "alice"


@pytest.mark.asyncio
async def test_cursor_is_persistent_across_fresh_recovery_calls_with_many_pages():
    db = AsyncMongoMockClient().wake_cursor_persisted_v136
    await AmbientRepository(db).ensure_indexes()
    moment = now()
    due = (moment - timedelta(minutes=8)).isoformat()
    before = [goal("alice", f"existing_{i:03d}", due) for i in range(69)]
    await db.agent_goals.insert_many(before)
    await db.ambient_wakes.insert_many(
        [existing_wake("alice", row["id"], due) for row in before]
    )
    await db.agent_goals.insert_one(
        goal("bob", "new_goal", (moment - timedelta(minutes=2)).isoformat())
    )

    for _ in range(2):
        assert await recover_due(db, now=moment, admit=False, limit=2) == 0
    assert await recover_due(db, now=moment, admit=False, limit=2) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": "bob", "source_ref": "goal:new_goal",
    }) == 1
    # The restart is represented by the next call with the same database but
    # no process-local scan state. Existing wake must not be duplicated.
    assert await recover_due(db, now=moment, admit=False, limit=2) == 0


@pytest.mark.asyncio
async def test_recovery_has_an_index_for_stable_next_run_owner_and_id():
    db = AsyncMongoMockClient().goal_wake_sorted_index_v136
    await AgentRepository(db).ensure_indexes()
    indexes = await db.agent_goals.index_information()
    keys = [tuple(tuple(part) for part in idx["key"]) for idx in indexes.values()]
    assert (("next_run_at", 1), ("owner_id", 1), ("id", 1)) in keys


@pytest.mark.asyncio
async def test_user_authority_and_required_input_never_create_new_wakes():
    db = AsyncMongoMockClient().goal_wake_consent_v136
    await AmbientRepository(db).ensure_indexes()
    moment = now()
    due = (moment - timedelta(minutes=1)).isoformat()
    await db.agent_goals.insert_many([
        {**goal("alice", "must_authorise", due),
         "requires_user_authority": True},
        {**goal("bob", "must_answer", due),
         "requires_user_input": True},
    ])
    assert await recover_due(db, now=moment, admit=False) == 0
    assert await db.ambient_wakes.count_documents({}) == 0
