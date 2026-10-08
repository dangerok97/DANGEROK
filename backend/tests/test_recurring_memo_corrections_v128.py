"""Phase 2: annual reminders stay aligned with corrected durable memory."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from memos.caps import save_recurring_memo
from memos.service import RecurringMemoService


def rome(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Europe/Rome")).astimezone(timezone.utc)


async def seeded_service(name):
    db = AsyncMongoMockClient()[name]
    await db.memories.insert_one({
        "id": "birthday-elena", "user_id": "owner", "status": "active",
        "statement": "Compleanno di zia Elena",
        "value": {"person": "zia Elena", "month": 3, "day": 13},
    })
    service = RecurringMemoService(db)
    await service.ensure_indexes()
    saved = await service.save_annual(
        "owner", memory_ref="birthday-elena", category="birthday",
        label="Compleanno di zia Elena", person="zia Elena", month=3, day=13,
        timezone_name="Europe/Rome", remind_hour_local=9,
    )
    assert saved["ok"]
    return db, service, saved["memo"]["id"]


@pytest.mark.asyncio
async def test_midnight_from_cognitive_capability_is_not_reset_to_nine():
    db, _, _ = await seeded_service("memo_midnight_cap_v128")
    observation = await save_recurring_memo({
        "memory_ref": "birthday-elena", "category": "birthday",
        "label": "Compleanno di zia Elena", "person": "zia Elena",
        "month": 3, "day": 13, "timezone": "Europe/Rome",
        "remind_hour_local": 0,
    }, {"db": db, "user_id": "owner"})
    assert observation.status == "ok"
    memo = observation.payload["memo"]
    assert memo["remind_hour_local"] == 0
    due = datetime.fromisoformat(memo["next_due_at"]).astimezone(ZoneInfo("Europe/Rome"))
    assert due.hour == 0


@pytest.mark.asyncio
async def test_corrected_birthday_does_not_fire_stale_date_and_rearms_next_day():
    db, service, memo_id = await seeded_service("memo_changed_date_v128")
    await db.recurring_memos.update_one(
        {"id": memo_id}, {"$set": {"next_due_at": rome(2027, 3, 13, 9).isoformat()}})
    await db.memories.update_one(
        {"id": "birthday-elena"}, {"$set": {
            "value": {"person": "zia Elena corretta", "month": 3, "day": 14},
        }}
    )
    stale = await service.fire_due(now=rome(2027, 3, 13, 9, 5))
    assert stale == {"due": 1, "raised": 0, "disabled": 0}
    assert await db.opportunities.count_documents({"owner_id": "owner"}) == 0
    memo = await db.recurring_memos.find_one({"id": memo_id})
    due = datetime.fromisoformat(memo["next_due_at"]).astimezone(ZoneInfo("Europe/Rome"))
    assert (due.year, due.month, due.day, due.hour) == (2027, 3, 14, 9)
    assert memo["person"] == "zia Elena corretta"
    result = await service.fire_due(now=rome(2027, 3, 14, 9, 5))
    assert result == {"due": 1, "raised": 1, "disabled": 0}
    opportunities = await db.opportunities.find({"owner_id": "owner"}).to_list(None)
    assert len(opportunities) == 1
    assert "zia Elena corretta" in opportunities[0]["semantic_summary"]


@pytest.mark.asyncio
async def test_invalid_corrected_memory_disables_stale_reminder():
    db, service, memo_id = await seeded_service("memo_invalid_date_v128")
    await db.recurring_memos.update_one(
        {"id": memo_id}, {"$set": {"next_due_at": rome(2027, 3, 13, 9).isoformat()}})
    await db.memories.update_one(
        {"id": "birthday-elena"}, {"$set": {
            "value": {"person": "zia Elena", "month": 2, "day": 30},
        }}
    )
    outcome = await service.fire_due(now=rome(2027, 3, 13, 9, 5))
    assert outcome == {"due": 1, "raised": 0, "disabled": 1}
    assert await db.opportunities.count_documents({"owner_id": "owner"}) == 0
    memo = await db.recurring_memos.find_one({"id": memo_id})
    assert memo["status"] == "disabled"
