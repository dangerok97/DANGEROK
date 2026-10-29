"""A reminder asked again and again becomes an offer to make it repeat."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from memos import habits, one_shot

ROME = ZoneInfo("Europe/Rome")
OWNER = "usr_habit_v1"


def _row(day, hour, minute, title="Pastiglia"):
    due = datetime(2026, 10, day, hour, minute, tzinfo=ROME).astimezone(timezone.utc)
    return {"title": title, "due_at": due.isoformat(), "meta": {}}


def test_three_days_same_time_is_a_daily_habit_two_is_not():
    rows = [_row(20, 20, 0), _row(22, 20, 15), _row(23, 19, 50, "ricordami la pastiglia")]
    found = habits.find(rows, ROME)
    assert len(found) == 1 and found[0]["repeat"] == "daily" and (found[0]["hour"], found[0]["minute"]) == (20, 0)
    assert habits.find(rows[:2], ROME) == []
    scattered = [_row(20, 8, 0), _row(22, 13, 0), _row(23, 20, 0)]
    assert habits.find(scattered, ROME) == []


def test_same_weekday_three_weeks_is_weekly():
    rows = [_row(6, 19, 0, "Plastica"), _row(13, 19, 10, "Plastica"), _row(20, 18, 55, "Plastica")]
    p = habits.find(rows, ROME)[0]
    assert p["repeat"] == "weekly" and p["weekday"] == 1  # Tuesday
    assert "ogni martedì alle 19:00" in habits.wording(p)


@pytest.mark.asyncio
async def test_propose_once_accept_creates_a_series_decline_never_again():
    db = AsyncMongoMockClient().habit_v1
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    for r in [_row(20, 20, 0), _row(22, 20, 0), _row(27, 20, 5)]:
        await db.reminders.insert_one({**r, "user_id": OWNER, "origin": "chat_reminder", "status": "done"})
    found = await habits.propose(db, OWNER, now=now)
    assert found and found[0]["code"] == "habit_proposed"
    assert await habits.propose(db, OWNER, now=now) == []  # never twice
    opp = await db.opportunities.find_one({"source_context": "habit_proposal"})
    from opportunities.models import Opportunity
    assert Opportunity(**{k: v for k, v in opp.items() if k != "_id"}).for_home()["reminder"] == {"kind": "habit"}
    out = await one_shot.act(db, OWNER, opp["id"], "accept")
    assert out["accepted"] and out["first_at"]
    series = await db.reminders.find_one({"meta.from_habit": {"$exists": True}})
    assert series["meta"]["repeat"] == "daily"
    assert datetime.fromisoformat(series["due_at"]).astimezone(ROME).strftime("%H:%M") == "20:00"
    again = await one_shot.act(db, OWNER, opp["id"], "decline")
    assert again["ok"] is False


@pytest.mark.asyncio
async def test_declined_is_not_offered_again():
    db = AsyncMongoMockClient().habit_decline_v1
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    for r in [_row(20, 20, 0), _row(22, 20, 0), _row(27, 20, 5)]:
        await db.reminders.insert_one({**r, "user_id": OWNER, "origin": "chat_reminder", "status": "done"})
    await habits.propose(db, OWNER, now=now)
    opp = await db.opportunities.find_one({"source_context": "habit_proposal"})
    assert (await one_shot.act(db, OWNER, opp["id"], "decline"))["accepted"] is False
    await db.reminders.insert_one({**_row(28, 20, 0), "user_id": OWNER, "origin": "chat_reminder", "status": "done"})
    assert await habits.propose(db, OWNER, now=now) == []
