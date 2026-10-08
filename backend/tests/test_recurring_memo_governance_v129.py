"""Phase 2: governed corrections preserve explicit recurring reminder consent."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.models import MemoryCandidate
from life_memory.governance import MemoryGovernanceService
from life_profile.knowledge_map import knowledge_map
from memos.service import RecurringMemoService


def birthday(person="zia Elena", day=13, *, operation="propose", previous=None):
    return MemoryCandidate(
        operation=operation, existing_memory_ref=previous,
        summary=f"Il {day} marzo è il compleanno di {person}.",
        kind="birthday", identity_key="birthday:zia_elena",
        value={"person": person, "month": 3, "day": day},
        confidence=0.99, authority="user_stated", epistemic_status="asserted",
        provenance=["user_conversation"], permanence="durable",
        recurrence="annual", sensitivity="normal",
        reason_for_future_utility="Ricordare ogni anno il compleanno.",
        requires_confirmation=False, user_authorized=False,
    )


async def initial(db, *, schedule=True, hour=9):
    governance = MemoryGovernanceService(db)
    reminders = RecurringMemoService(db)
    await governance.ensure_indexes()
    await reminders.ensure_indexes()
    first = (await governance.process(
        user_id="owner", session_id="s1", reasoning_epoch="e1",
        candidates=[birthday()],
    ))[0]
    assert first.decision == "PROMOTE" and first.persisted
    if schedule:
        created = await reminders.save_annual(
            "owner", memory_ref=first.memory_id, category="birthday",
            label="Compleanno di zia Elena", person="zia Elena",
            month=3, day=13, timezone_name="Europe/Rome",
            remind_hour_local=hour,
        )
        assert created["ok"]
    return governance, reminders, first.memory_id


@pytest.mark.asyncio
async def test_governed_birthday_correction_transfers_existing_schedule_and_star():
    db = AsyncMongoMockClient().birthday_supersession_v129
    governance, _, old_id = await initial(db, hour=0)
    correction = (await governance.process(
        user_id="owner", session_id="s2", reasoning_epoch="e2",
        candidates=[birthday("zia Elena aggiornata", 14, operation="correct", previous=old_id)],
    ))[0]
    assert correction.decision == "SUPERSEDE" and correction.persisted
    new_id = correction.memory_id
    assert new_id != old_id
    assert (await db.memories.find_one({"id": old_id}))["status"] == "superseded"
    old = await db.recurring_memos.find_one({"owner_id": "owner", "memory_ref": old_id})
    assert old["status"] == "superseded"
    new = await db.recurring_memos.find_one({"owner_id": "owner", "memory_ref": new_id})
    assert new["status"] == "active"
    assert (new["month"], new["day"], new["remind_hour_local"]) == (3, 14, 0)
    assert new["person"] == "zia Elena aggiornata"
    due = datetime.fromisoformat(new["next_due_at"]).astimezone(ZoneInfo("Europe/Rome"))
    assert (due.month, due.day, due.hour) == (3, 14, 0)
    assert await db.recurring_memos.count_documents({"owner_id": "owner", "status": "active"}) == 1
    projected = await knowledge_map(db, "owner")
    items = [star for star in projected["stars"] if star.get("title") == "Compleanno"]
    assert len(items) == 1 and "14 marzo" in items[0]["statement"]


@pytest.mark.asyncio
async def test_no_existing_reminder_is_not_silently_created_by_a_correction():
    db = AsyncMongoMockClient().birthday_no_autoschedule_v129
    governance, _, old_id = await initial(db, schedule=False)
    changed = (await governance.process(
        user_id="owner", session_id="s2", reasoning_epoch="e2",
        candidates=[birthday(day=14, operation="correct", previous=old_id)],
    ))[0]
    assert changed.decision == "SUPERSEDE"
    assert await db.recurring_memos.count_documents({"owner_id": "owner"}) == 0


@pytest.mark.asyncio
async def test_forgetting_an_owned_birthday_disables_reminder_immediately():
    db = AsyncMongoMockClient().birthday_forget_v129
    governance, _, old_id = await initial(db)
    forgot = MemoryCandidate(
        operation="forget", existing_memory_ref=old_id,
        summary="Dimentica questo compleanno",
        kind="birthday", identity_key="birthday:zia_elena", value=None,
        confidence=1, authority="user_stated", epistemic_status="confirmed",
        permanence="durable", reason_for_future_utility="Seguire il comando di cancellazione",
    )
    decision = (await governance.process(
        user_id="owner", session_id="s3", reasoning_epoch="e3",
        candidates=[forgot],
    ))[0]
    assert decision.decision == "FORGET_ALLOWED" and decision.persisted
    memo = await db.recurring_memos.find_one({"owner_id": "owner", "memory_ref": old_id})
    assert memo["status"] == "disabled"
    assert await db.recurring_memos.count_documents({"owner_id": "owner", "status": "active"}) == 0


@pytest.mark.asyncio
async def test_transfer_respects_owner_and_is_repeatable_without_duplicates():
    db = AsyncMongoMockClient().birthday_transfer_owner_v129
    governance, reminders, old_id = await initial(db)
    new = (await governance.process(
        user_id="owner", session_id="s2", reasoning_epoch="e2",
        candidates=[birthday(day=14, operation="correct", previous=old_id)],
    ))[0]
    rows_before = await db.recurring_memos.count_documents({"owner_id": "owner"})
    repeat = await reminders.reconcile_governed_memory(
        "owner", old_ref=old_id, new_ref=new.memory_id
    )
    outsider = await reminders.reconcile_governed_memory(
        "other", old_ref=old_id, new_ref=new.memory_id
    )
    assert repeat == {"transferred": 0, "disabled": 0}
    assert outsider == {"transferred": 0, "disabled": 0}
    assert await db.recurring_memos.count_documents({"owner_id": "owner"}) == rows_before
