"""Experimental Situation continuity after a worker interruption.

These tests exercise the actual persistent Agent/Ambient admission paths with
a synthetic owner and MongoDB stand-in. A technical recovery wake is only an
initial AI review, NOT verified weather, a monitoring checkpoint or a push.
No real account, API credentials, external model or notifications are used.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.background import recover_due
from ambient.repository import AmbientRepository
from opportunities.discovery import OpportunityDiscovery
from situations.followup import INITIAL_KIND, goal_id_for, read_followup
from situations.models import SituationUpdate
from situations.service import SituationService

OWNER = "synthetic-exp-wake-owner"
OTHER = "synthetic-exp-wake-other"


async def setup(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(
        return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().exp_situation_restart
    await db.agent_goals.create_index("id", unique=True)
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.ambient_wakes.create_index(
        "identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}},
    )
    created = await SituationService(db).apply(
        user_id=OWNER,
        session_id="synthetic-session",
        reasoning_epoch="synthetic-create-one",
        update=SituationUpdate(
            operation="create", source="user_conversation",
            summary="TEST: processo all'aperto da monitorare",
            attention_intent="Controllare quando si raggiunge l'esito utile",
            desired_outcome="Un consiglio con evidenza, non una data inventata",
            location_label="Luogo dichiarato senza coordinate simulate",
        ),
    )
    assert created["status"] == "success"
    sid = created["situation"]["id"]
    gid = goal_id_for(OWNER, sid)
    assert (await db.agent_goals.find_one({"id": gid}))["source_kind"] == INITIAL_KIND
    return db, sid, gid


@pytest.mark.asyncio
async def test_consumed_review_without_checkpoint_gets_exactly_one_recovery_wake(monkeypatch):
    db, sid, gid = await setup(monkeypatch)
    original = await db.ambient_wakes.find_one({
        "owner_id": OWNER, "source_ref": f"goal:{gid}", "status": "pending"
    })
    assert original is not None
    # A worker previously acknowledged its INITIAL REVIEW but the cognitive
    # model had not yet persisted an evidence-backed next check.
    await db.ambient_wakes.update_one({"id": original["id"]}, {
        "$set": {"status": "completed", "last_error": "synthetic_process_exit"}
    })
    broken = await read_followup(db, OWNER, sid)
    assert broken["status"] == "recovery_pending"
    assert broken["next_check_at"] is None

    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    scheduled = await recover_due(db, now=later, limit=2, admit=False)
    assert scheduled == 1
    fixed = await read_followup(db, OWNER, sid)
    assert fixed["status"] == "review_pending"
    assert fixed["next_check_at"] is None
    assert fixed["assessment_at"] is not None
    open_wakes = await db.ambient_wakes.find({
        "owner_id": OWNER, "source_ref": f"goal:{gid}",
        "status": {"$in": ["pending", "claimed"]},
    }, {"_id": 0}).to_list(10)
    assert len(open_wakes) == 1
    assert open_wakes[0]["reason"] == "opportunity_revisit"
    assert open_wakes[0]["id"] != original["id"]

    # The recovery cursor may revisit the same due goal; that must not create
    # another pending wake, alter its deadline or duplicate the Situation.
    repeated = await recover_due(db, now=later, limit=2, admit=False)
    assert repeated == 0
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    assert await db.situations.count_documents({"user_id": OWNER}) == 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "status": {"$in": ["pending", "claimed"]}
    }) == 1
    assert await db.delivery_plans.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({"owner_id": OTHER}) == 0


@pytest.mark.asyncio
async def test_expired_claimed_review_is_reclaimed_by_one_new_worker(monkeypatch):
    db, sid, gid = await setup(monkeypatch)
    repo = AmbientRepository(db)
    original = await db.ambient_wakes.find_one({
        "owner_id": OWNER, "source_ref": f"goal:{gid}", "status": "pending",
    })
    assert original is not None
    # Use the actual persisted due moment, not an assumption about how
    # many seconds Ambient's scheduling floor uses in this environment.
    first_due = datetime.fromisoformat(original["scheduled_for"])
    first = await repo.claim_due(
        worker_id="synthetic-worker-that-died",
        now=first_due + timedelta(seconds=5),
    )
    assert first and first.status == "claimed"
    lease_expired = datetime.fromisoformat(first.lease_until) + timedelta(seconds=2)
    recovered = await repo.claim_due(
        worker_id="synthetic-replacement-worker",
        now=lease_expired,
    )
    assert recovered and recovered.id == first.id
    assert recovered.worker_id == "synthetic-replacement-worker"
    assert recovered.attempts == first.attempts + 1
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{gid}",
        "status": {"$in": ["pending", "claimed"]}
    }) == 1
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 1
    # Claiming work is not evidence that its source was read or its physical
    # process completed.
    assert (await read_followup(db, OWNER, sid))["next_check_at"] is None


@pytest.mark.asyncio
async def test_explicit_cancel_stops_review_and_cannot_resurrect_from_due_scan(monkeypatch):
    db, sid, gid = await setup(monkeypatch)
    closed = await SituationService(db).apply(
        user_id=OWNER, session_id="synthetic-session",
        reasoning_epoch="synthetic-cancel-one",
        update=SituationUpdate(
            operation="cancel", situation_id=sid, expected_revision=1,
            source="user_conversation",
        ),
    )
    assert closed["status"] == "success"
    assert (await read_followup(db, OWNER, sid))["status"] == "stopped"
    recovered = await recover_due(
        db, now=datetime.now(timezone.utc) + timedelta(minutes=30),
        admit=False,
    )
    assert recovered == 0
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{gid}",
        "status": {"$in": ["pending", "claimed"]},
    }) == 0
    assert await db.agent_goals.count_documents({
        "owner_id": OWNER, "status": "cancelled",
    }) == 1
