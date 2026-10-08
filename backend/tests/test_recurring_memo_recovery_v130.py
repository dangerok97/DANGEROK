"""V130: durable Memory/reminder reconciliation recovers after interrupted writes.

Only a prior explicit reminder may transfer; nothing gets sent in this module.
All documents and owners are synthetic and isolated in mongomock-motor.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.models import MemoryCandidate
from life_memory.governance import MemoryGovernanceService
from memos.recovery import RecurringMemoRecovery
from memos.service import RecurringMemoService


def birthday(person="Persona test", day=13, operation="propose", previous=None):
    return MemoryCandidate(
        operation=operation, existing_memory_ref=previous,
        summary=f"Compleanno di {person} il {day} marzo.",
        kind="birthday", identity_key="birthday:synthetic_person",
        value={"person": person, "month": 3, "day": day},
        confidence=.99, authority="user_stated", epistemic_status="asserted",
        permanence="durable", recurrence="annual", sensitivity="normal",
        provenance=["synthetic_conversation"],
        reason_for_future_utility="Promemoria annuale richiesto dall'utente.",
    )


async def seed(db, *, schedule=True):
    government = MemoryGovernanceService(db)
    reminders = RecurringMemoService(db)
    await government.ensure_indexes()
    await reminders.ensure_indexes()
    first = (await government.process(
        user_id="owner", session_id="first", reasoning_epoch="initial",
        candidates=[birthday()],
    ))[0]
    assert first.persisted
    if schedule:
        saved = await reminders.save_annual(
            "owner", memory_ref=first.memory_id, category="birthday",
            label="Compleanno", person="Persona test",
            month=3, day=13, timezone_name="Europe/Rome",
            remind_hour_local=0,
        )
        assert saved["ok"] is True
    return government, first.memory_id


async def interrupt_then_correct(db):
    government, old_ref = await seed(db)
    with patch.object(RecurringMemoService, "reconcile_governed_memory",
                      side_effect=RuntimeError("synthetic crash before rebind")):
        changed = (await government.process(
            user_id="owner", session_id="second", reasoning_epoch="corrected",
            candidates=[birthday("Persona aggiornata", 14, "correct", old_ref)],
        ))[0]
    assert changed.persisted and changed.decision == "SUPERSEDE"
    old = await db.memories.find_one({"id": old_ref})
    assert old["status"] == "superseded"
    assert old["superseded_by"] == changed.memory_id
    assert old["recurring_reconcile"]["status"] == "pending"
    return old_ref, changed.memory_id


@pytest.mark.asyncio
async def test_background_recovery_moves_existing_authorized_memo_after_crash():
    db = AsyncMongoMockClient().phase2_recovery
    old_ref, new_ref = await interrupt_then_correct(db)
    before = await db.recurring_memos.find_one({"memory_ref": old_ref})
    assert before["status"] == "active"
    service = RecurringMemoRecovery(db)
    recovered = await service.run()
    assert recovered["claimed"] == recovered["completed"] == 1, recovered
    assert recovered["transferred"] == 1
    old = await db.recurring_memos.find_one({"memory_ref": old_ref})
    replacement = await db.recurring_memos.find_one({"memory_ref": new_ref})
    assert old["status"] == "superseded"
    assert replacement["status"] == "active"
    assert (replacement["month"], replacement["day"]) == (3, 14)
    assert replacement["remind_hour_local"] == 0
    assert replacement["person"] == "Persona aggiornata"
    assert await service.run() == {
        "claimed": 0, "completed": 0, "deferred": 0,
        "errors": 0, "transferred": 0, "disabled": 0,
    }
    assert await db.recurring_memos.count_documents({"status": "active"}) == 1


@pytest.mark.asyncio
async def test_missing_replacement_retries_without_discarding_original_reminder():
    db = AsyncMongoMockClient().phase2_missing_target
    old_ref, new_ref = await interrupt_then_correct(db)
    await db.memories.delete_one({"id": new_ref})
    service = RecurringMemoRecovery(db)
    moment = datetime.now(timezone.utc)
    first = await service.run(now=moment)
    assert first["deferred"] == 1 and first["completed"] == 0
    assert (await db.recurring_memos.find_one({"memory_ref": old_ref}))["status"] == "active"
    assert (await service.run(now=moment))["claimed"] == 0
    await db.memories.insert_one({
        "id": new_ref, "user_id": "owner", "status": "active",
        "kind": "birthday", "value": {"person": "Persona aggiornata", "month": 3, "day": 14},
    })
    second = await service.run(now=moment + timedelta(minutes=2))
    assert second["transferred"] == second["completed"] == 1


@pytest.mark.asyncio
async def test_real_error_keeps_claim_pending_and_retries_after_backoff():
    db = AsyncMongoMockClient().phase2_retry
    old_ref, new_ref = await interrupt_then_correct(db)
    svc = RecurringMemoRecovery(db)
    start = datetime.now(timezone.utc)
    with patch.object(RecurringMemoService, "reconcile_governed_memory",
                      side_effect=ConnectionError("synthetic Mongo error")):
        first = await svc.run(now=start)
    assert first["errors"] == 1 and first["completed"] == 0
    assert (await db.memories.find_one({"id": old_ref}))["recurring_reconcile"]["status"] == "pending"
    assert (await svc.run(now=start))["claimed"] == 0
    second = await svc.run(now=start + timedelta(minutes=2))
    assert second["transferred"] == 1
    assert (await db.recurring_memos.find_one({"memory_ref": new_ref}))["status"] == "active"


@pytest.mark.asyncio
async def test_expired_claim_can_be_recovered_by_another_worker():
    db = AsyncMongoMockClient().phase2_expired_lease
    old_ref, _ = await interrupt_then_correct(db)
    start = datetime.now(timezone.utc)
    await db.memories.update_one({"id": old_ref}, {"$set": {
        "recurring_reconcile.lease_token": "dead-worker",
        "recurring_reconcile.lease_until": (start + timedelta(seconds=30)).isoformat(),
    }})
    service = RecurringMemoRecovery(db)
    assert (await service.run(now=start))["claimed"] == 0
    assert (await service.run(now=start + timedelta(seconds=31)))["completed"] == 1


@pytest.mark.asyncio
async def test_forget_pending_and_owner_isolation():
    db = AsyncMongoMockClient().phase2_forgotten
    government, ref = await seed(db)
    candidate = MemoryCandidate(
        operation="forget", existing_memory_ref=ref,
        summary="Forget this birthday", kind="birthday",
        confidence=1, authority="user_stated", epistemic_status="confirmed",
        permanence="durable", reason_for_future_utility="Follow explicit user request",
    )
    with patch.object(RecurringMemoService, "reconcile_governed_memory",
                      side_effect=RuntimeError("simulated interruption")):
        forgotten = (await government.process(
            user_id="owner", session_id="forget", reasoning_epoch="forgotten",
            candidates=[candidate],
        ))[0]
    assert forgotten.persisted
    await db.memories.insert_one({
        "id": "other-memory", "user_id": "other", "status": "active",
        "kind": "birthday", "value": {"month": 3, "day": 13},
    })
    finished = await RecurringMemoRecovery(db).run()
    assert finished["disabled"] == 1
    assert (await db.recurring_memos.find_one({"memory_ref": ref}))["status"] == "disabled"
    assert await db.recurring_memos.count_documents({"owner_id": "other"}) == 0


@pytest.mark.asyncio
async def test_stale_due_does_not_destroy_reminder_before_recovery():
    db = AsyncMongoMockClient().phase2_due_claim
    old_ref, new_ref = await interrupt_then_correct(db)
    now = datetime.now(timezone.utc)
    await db.recurring_memos.update_one(
        {"memory_ref": old_ref},
        {"$set": {"next_due_at": (now - timedelta(minutes=1)).isoformat()}},
    )
    fired = await RecurringMemoService(db).fire_due(now=now)
    assert fired["raised"] == 0 and fired["disabled"] == 0
    assert await db.opportunities.count_documents({}) == 0
    assert (await db.recurring_memos.find_one({"memory_ref": old_ref}))["status"] == "superseded"
    assert (await db.recurring_memos.find_one({"memory_ref": new_ref}))["status"] == "active"


@pytest.mark.asyncio
async def test_correction_without_reminder_stays_reminder_free():
    db = AsyncMongoMockClient().phase2_without_reminder
    government, old_ref = await seed(db, schedule=False)
    with patch.object(RecurringMemoService, "reconcile_governed_memory",
                      side_effect=RuntimeError("transient")):
        changed = (await government.process(
            user_id="owner", session_id="s2", reasoning_epoch="e2",
            candidates=[birthday("Persona aggiornata", 14, "correct", old_ref)],
        ))[0]
    assert changed.persisted
    recovered = await RecurringMemoRecovery(db).run()
    assert recovered["completed"] == 1 and recovered["transferred"] == 0
    assert await db.recurring_memos.count_documents({}) == 0
