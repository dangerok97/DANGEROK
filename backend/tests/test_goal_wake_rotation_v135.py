"""V135: unattended goals cannot be hidden by older already-scheduled wakes.

All data is synthetic; no model call, transport, external API or person.
"""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.background import recover_due
from ambient.repository import AmbientRepository


def moment():
    return datetime.now(timezone.utc)


def goal(uid, name, due):
    return {
        "id": name, "owner_id": uid,
        "status": "active", "next_run_at": due,
        "requires_user_input": False, "requires_user_authority": False,
    }


def wake(uid, name):
    return {
        "id": f"wake_{uid}_{name}", "owner_id": uid,
        "source_ref": f"goal:{name}", "status": "pending",
        "reason": "opportunity_revisit",
        "identity": f"synthetic:{uid}:{name}",
        "scheduled_for": moment().isoformat(),
    }


@pytest.mark.asyncio
async def test_old_already_woken_goals_do_not_hide_new_due_goal():
    db = AsyncMongoMockClient().goal_wake_skip_v135
    await AmbientRepository(db).ensure_indexes()
    now = moment()
    first = (now - timedelta(minutes=3)).isoformat()
    second = (now - timedelta(minutes=2)).isoformat()
    third = (now - timedelta(minutes=1)).isoformat()
    await db.agent_goals.insert_many([
        goal("alice", "goal_old_a", first),
        goal("alice", "goal_old_b", second),
        goal("bob", "goal_new_c", third),
    ])
    await db.ambient_wakes.insert_many([
        wake("alice", "goal_old_a"), wake("alice", "goal_old_b"),
    ])
    assert await recover_due(db, now=now, limit=2, admit=False) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": "bob", "source_ref": "goal:goal_new_c",
        "status": "pending",
    }) == 1


@pytest.mark.asyncio
async def test_persistent_cursor_reaches_later_page_without_scanning_everything():
    db = AsyncMongoMockClient().goal_wake_cursor_v135
    await AmbientRepository(db).ensure_indexes()
    now = moment()
    due = (now - timedelta(minutes=3)).isoformat()
    old_goals = [goal("alice", f"goal_existing_{i:03d}", due) for i in range(65)]
    old_wakes = [wake("alice", f"goal_existing_{i:03d}") for i in range(65)]
    await db.agent_goals.insert_many(old_goals)
    await db.ambient_wakes.insert_many(old_wakes)
    await db.agent_goals.insert_one(
        goal("bob", "goal_new_final", (now - timedelta(minutes=1)).isoformat())
    )

    assert await recover_due(db, now=now, limit=2, admit=False) == 0
    first_cursor = await db.agent_goal_wake_recovery_progress.find_one({})
    assert first_cursor is not None and first_cursor["after_id"] == "goal_existing_031"
    assert await recover_due(db, now=now, limit=2, admit=False) == 0
    assert await recover_due(db, now=now, limit=2, admit=False) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": "bob", "source_ref": "goal:goal_new_final",
        "status": "pending",
    }) == 1


@pytest.mark.asyncio
async def test_mixed_due_owners_each_receive_one_slot_when_possible():
    db = AsyncMongoMockClient().goal_wake_owner_fair_v135
    await AmbientRepository(db).ensure_indexes()
    now = moment()
    due = (now - timedelta(minutes=1)).isoformat()
    await db.agent_goals.insert_many([
        goal("alice", "goal_a1", due),
        goal("alice", "goal_a2", due),
        goal("bob", "goal_b1", due),
    ])
    assert await recover_due(db, now=now, limit=2, admit=False) == 2
    wake_docs = await db.ambient_wakes.find({"status": "pending"}).to_list(None)
    assert {row["owner_id"] for row in wake_docs} == {"alice", "bob"}
    assert await recover_due(db, now=now, limit=2, admit=False) == 1
    assert await db.ambient_wakes.count_documents({"status": "pending"}) == 3


@pytest.mark.asyncio
async def test_two_owners_with_equal_goal_names_never_share_wake():
    db = AsyncMongoMockClient().goal_wake_same_id_v135
    await AmbientRepository(db).ensure_indexes()
    now = moment()
    due = (now - timedelta(minutes=1)).isoformat()
    await db.agent_goals.insert_many([
        goal("alice", "same_goal", due),
        goal("bob", "same_goal", due),
    ])
    await db.ambient_wakes.insert_one(wake("alice", "same_goal"))
    assert await recover_due(db, now=now, limit=2, admit=False) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": "bob", "source_ref": "goal:same_goal",
    }) == 1
