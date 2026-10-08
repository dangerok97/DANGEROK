"""v142: an accepted autonomous result cannot be lost between Mongo writes.

The tests use one synthetic account and no real model, device or network.
Home and update records are the production repositories, not fake surfaces.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal, VisibilityDecision
from agent.visibility import VisibilityService
from delivery.repository import DeliveryRepository
from delivery.service import DeliveryService


def past():
    return (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()


async def scenario(db, owner="alice"):
    visibility = VisibilityService(db)
    await visibility.ensure_indexes()
    await DeliveryRepository(db).ensure_indexes()
    goal = AutonomousGoal(
        owner_id=owner, status="completed",
        objective="Confrontare due scelte", desired_outcome="Preparare una nota leggibile",
    )
    await db.agent_goals.insert_one(goal.model_dump())
    decision = VisibilityDecision(
        goal_id=goal.id,
        outcome="inform_user",
        headline="Confronto verificato pronto nella Home",
        reasoning="Risultato documentato con riferimenti",
        refs=["evidence:synthetic-result"],
        fingerprint="outbox-result-"+owner,
    )
    assert await visibility._record(owner, decision)
    pending = await db.agent_updates.find_one({"owner_id": owner, "fingerprint": decision.fingerprint})
    assert pending["home_pending"] is True and pending["home_due_at"]
    return visibility, goal, decision


@pytest.mark.asyncio
async def test_home_write_failure_recovers_without_another_ai_or_push(monkeypatch):
    db = AsyncMongoMockClient().durable_home_failure_v142
    visibility, goal, decision = await scenario(db)
    original = DeliveryService.note_activity
    sent = 0

    async def fail_once(self, *args, **kwargs):
        nonlocal sent
        sent += 1
        if sent == 1:
            raise ConnectionError("synthetic write interruption before Home")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(DeliveryService, "note_activity", fail_once)
    assert await visibility.show("alice", goal, decision) is False
    assert await db.ambient_activity.count_documents({"owner_id": "alice"}) == 0
    assert (await db.agent_updates.find_one({"owner_id": "alice"}))["home_pending"] is True

    await db.agent_updates.update_one(
        {"owner_id": "alice"}, {"$set": {"home_due_at": past()}},
    )
    recovered = await visibility.recover_pending_home()
    assert recovered == {"checked": 1, "shown": 1, "deferred": 0, "stale": 0}
    assert await db.ambient_activity.count_documents({"owner_id": "alice"}) == 1
    assert (await db.agent_updates.find_one({"owner_id": "alice"}))["home_pending"] is False
    assert "Confronto" in str(await DeliveryService(db).ambient_line("alice"))
    assert (await visibility.recover_pending_home())["checked"] == 0
    assert sent == 2
    assert await db.agent_needs.count_documents({}) == 0
    assert await db.delivery_plans.count_documents({}) == 0


@pytest.mark.asyncio
async def test_crash_after_home_insert_before_ack_does_not_repeat_activity():
    db = AsyncMongoMockClient().durable_home_ack_lost_v142
    visibility, goal, decision = await scenario(db)
    assert await visibility.show("alice", goal, decision)
    row = await db.ambient_activity.find_one({"owner_id": "alice"})
    assert row is not None and row["id"].startswith("ambv_")
    # The first process could die between the Activity insert and the
    # update acknowledgement. Reopen the durable state exactly as a crash.
    await db.agent_updates.update_one(
        {"owner_id": "alice"},
        {"$set": {"home_pending": True, "home_due_at": past()}},
    )
    out = await VisibilityService(db).recover_pending_home()
    assert out["shown"] == 1
    assert await db.ambient_activity.count_documents({"owner_id": "alice"}) == 1
    same = await db.ambient_activity.find_one({"owner_id": "alice"})
    assert same["id"] == row["id"] and same["occurred_at"] == row["occurred_at"]


@pytest.mark.asyncio
async def test_two_workers_and_two_owners_are_idempotent():
    db = AsyncMongoMockClient().durable_home_competing_workers_v142
    alice, goal_a, dec_a = await scenario(db, owner="alice")
    bob, goal_b, dec_b = await scenario(db, owner="bob")
    results = await asyncio.gather(
        alice.recover_pending_home(limit=4),
        VisibilityService(db).recover_pending_home(limit=4),
    )
    assert sum(x["shown"] for x in results) >= 2
    rows = await db.ambient_activity.find({}).to_list(10)
    assert len(rows) == 2
    assert {x["owner_id"] for x in rows} == {"alice", "bob"}
    assert len({x["id"] for x in rows}) == 2
    assert (await alice.recover_pending_home())["checked"] == 0


@pytest.mark.asyncio
async def test_cancelled_goal_is_not_reannounced_after_restart():
    db = AsyncMongoMockClient().durable_home_cancelled_v142
    visibility, goal, decision = await scenario(db)
    await db.agent_goals.update_one(
        {"id": goal.id, "owner_id": "alice"},
        {"$set": {"status": "cancelled"}},
    )
    result = await visibility.recover_pending_home()
    assert result["stale"] == 1 and result["shown"] == 0
    assert await db.ambient_activity.count_documents({}) == 0
    row = await db.agent_updates.find_one({"owner_id": "alice"})
    assert row["home_pending"] is False and row["home_skipped"] == "goal_no_longer_valid"


@pytest.mark.asyncio
async def test_legacy_visibility_history_is_not_replayed_as_a_new_home_item():
    db = AsyncMongoMockClient().durable_home_no_backfill_v142
    visibility = VisibilityService(db)
    await visibility.ensure_indexes()
    await db.agent_updates.insert_one({
        "owner_id": "alice", "goal_id": "historical-goal",
        "outcome": "inform_user", "headline": "Old accepted message",
        "fingerprint": "legacy-message", "refs": ["old-evidence"],
        "at": past(),
    })
    assert (await visibility.recover_pending_home())["checked"] == 0
    assert await db.ambient_activity.count_documents({}) == 0
