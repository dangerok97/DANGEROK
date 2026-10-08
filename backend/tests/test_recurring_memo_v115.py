"""V115 — annual Memo overdue recovery and midnight hour regression."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from memos.service import RecurringMemoService


async def seed(db, *, reminder_hour=9):
    await db.memories.insert_one({
        "id": "mem_elena", "user_id": "owner", "status": "active",
        "statement": "Il 13 marzo è il compleanno di zia Elena.",
        "value": {"person": "zia Elena", "month": 3, "day": 13},
    })
    await db.recurring_memos.insert_one({
        "id": "rmm_elena", "owner_id": "owner", "memory_ref": "mem_elena",
        "category": "birthday", "label": "Compleanno di zia Elena",
        "person": "zia Elena", "recurrence": "annual",
        "month": 3, "day": 13, "timezone": "Europe/Rome",
        "remind_hour_local": reminder_hour,
        "next_due_at": "2026-03-13T08:00:00+00:00",
        "status": "active", "claim_until": "",
    })


@pytest.mark.asyncio
async def test_stale_birthday_rearms_without_false_today_notification():
    db = AsyncMongoMockClient().memo_overdue_v115
    await seed(db)
    now = datetime(2027, 10, 8, 10, 0, tzinfo=timezone.utc)
    result = await RecurringMemoService(db).fire_due(now=now)
    assert result == {"due": 1, "raised": 0, "disabled": 0}
    assert await db.opportunities.count_documents({"owner_id": "owner"}) == 0
    memo = await db.recurring_memos.find_one({"id": "rmm_elena"})
    due = datetime.fromisoformat(memo["next_due_at"]).astimezone(ZoneInfo("Europe/Rome"))
    assert (due.year, due.month, due.day, due.hour) == (2028, 3, 13, 9)


@pytest.mark.asyncio
async def test_old_due_before_todays_hour_rearms_for_today():
    db = AsyncMongoMockClient().memo_todays_hour_v115
    await seed(db)
    now = datetime(2027, 3, 13, 8, 30, tzinfo=ZoneInfo("Europe/Rome")).astimezone(timezone.utc)
    result = await RecurringMemoService(db).fire_due(now=now)
    assert result == {"due": 1, "raised": 0, "disabled": 0}
    memo = await db.recurring_memos.find_one({"id": "rmm_elena"})
    due = datetime.fromisoformat(memo["next_due_at"]).astimezone(ZoneInfo("Europe/Rome"))
    assert (due.year, due.month, due.day, due.hour) == (2027, 3, 13, 9)


@pytest.mark.asyncio
async def test_midnight_reminder_fires_and_stays_midnight_next_year():
    db = AsyncMongoMockClient().memo_midnight_v115
    await seed(db, reminder_hour=0)
    await db.recurring_memos.update_one(
        {"id": "rmm_elena"}, {"$set": {"next_due_at": "2027-03-12T23:00:00+00:00"}}
    )
    now = datetime(2027, 3, 13, 0, 5, tzinfo=ZoneInfo("Europe/Rome")).astimezone(timezone.utc)
    result = await RecurringMemoService(db).fire_due(now=now)
    assert result == {"due": 1, "raised": 1, "disabled": 0}
    assert await db.opportunities.count_documents({"owner_id": "owner"}) == 1
    memo = await db.recurring_memos.find_one({"id": "rmm_elena"})
    due = datetime.fromisoformat(memo["next_due_at"]).astimezone(ZoneInfo("Europe/Rome"))
    assert (due.year, due.month, due.day, due.hour) == (2028, 3, 13, 0)
