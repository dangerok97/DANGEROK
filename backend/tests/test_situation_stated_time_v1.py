"""A moment the person states becomes a reminder that does not need a model."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from situations.stated_time import already_said, arm, disarm, stated_moment

ROME = ZoneInfo("Europe/Rome")
NOW = datetime(2026, 10, 26, 10, 0, tzinfo=ROME)
OWNER = "usr_stated_v1"


@pytest.mark.parametrize("text,expected", [
    ("Ho messo la lavatrice, dura due ore", NOW + timedelta(hours=2)),
    ("ho acceso il forno, tra 40 minuti tolgo l'arrosto", NOW + timedelta(minutes=40)),
    ("il pane è pronto alle 11", NOW.replace(hour=11)),
    ("Finisce alle 13:30", NOW.replace(hour=13, minute=30)),
    ("ci vogliono un'ora e mezza", NOW + timedelta(minutes=90)),
    ("mancano mezz'ora", NOW + timedelta(minutes=30)),
    ("il programma da 2 ore e 15", NOW + timedelta(minutes=135)),
    ("il corriere arriva verso le 3", NOW.replace(hour=15)),
    ("deve lievitare per 3 ore", NOW + timedelta(hours=3)),
])
def test_stated_moments(text, expected):
    found = stated_moment(text, now=NOW)
    assert found and found[0] == expected


@pytest.mark.parametrize("text", [
    "Ho steso i panni",
    "quanto dura la lavatrice?",
    "non dura due ore",
    "l'ho messa due ore fa",
    "ci vogliono 3 giorni",
    "finisce alle 25",
])
def test_nothing_is_armed_without_a_stated_future_moment(text):
    assert stated_moment(text, now=NOW) is None


def test_duration_counts_from_the_stated_start():
    start = NOW - timedelta(minutes=30)
    found = stated_moment("l'ho messa alle 9:30, dura 2 ore", now=NOW, started_at=start)
    assert found[0] == start + timedelta(hours=2)


class _Sit:
    def __init__(self, **kw):
        self.id = "sit_stated"
        self.summary = "Lavatrice avviata"
        self.status = "active"
        self.attention_intent = "Avvisare quando finisce"
        self.next_check_summary = None
        self.started_at = None
        self.__dict__.update(kw)


async def _clock(monkeypatch):
    import timezone_service

    async def clock(_db, _owner, *, now=None):
        return {"local_datetime": NOW.isoformat()}

    monkeypatch.setattr(timezone_service, "user_clock_context", clock)


@pytest.mark.asyncio
async def test_arm_moves_and_disarm_cancels(monkeypatch):
    await _clock(monkeypatch)
    db = AsyncMongoMockClient().stated_v1
    sit = _Sit()
    out = await arm(db, OWNER, sit, "dura due ore")
    assert out["at_local"] == "12:00"
    row = await db.reminders.find_one({"id": "rem_sit_sit_stated"})
    assert row["status"] == "open" and row["meta"]["situation_id"] == "sit_stated"
    assert datetime.fromisoformat(row["due_at"]) == (NOW + timedelta(hours=2)).astimezone(timezone.utc)
    await db.reminders.update_one({"id": row["id"]}, {"$set": {"notified_state": "raised"}})
    moved = await arm(db, OWNER, sit, "no aspetta, ci vogliono tre ore")
    assert moved["at_local"] == "13:00"
    row = await db.reminders.find_one({"id": "rem_sit_sit_stated"})
    assert "notified_state" not in row
    assert await db.reminders.count_documents({}) == 1
    await disarm(db, OWNER, "sit_stated")
    assert (await db.reminders.find_one({"id": row["id"]}))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_a_situation_nobody_watches_arms_nothing(monkeypatch):
    await _clock(monkeypatch)
    db = AsyncMongoMockClient().stated_off_v1
    assert await arm(db, OWNER, _Sit(attention_intent=None), "dura due ore") is None
    assert await db.reminders.count_documents({}) == 0


@pytest.mark.asyncio
async def test_the_reminder_steps_aside_when_the_watch_already_said_it(monkeypatch):
    from memos import one_shot

    await _clock(monkeypatch)
    db = AsyncMongoMockClient().stated_said_v1
    await db.situations.insert_one({"id": "sit_stated", "user_id": OWNER, "status": "active"})
    await arm(db, OWNER, _Sit(), "tra 30 minuti")
    row = await db.reminders.find_one({})
    assert not await already_said(db, OWNER, row)
    await db.agent_goals.insert_one({"owner_id": OWNER, "source_refs": ["situation:sit_stated"],
                                     "updated_at": "2026-10-26T09:00:00+00:00",
                                     "situation_outcome": {"action_reason": "outcome_ready"}})
    assert await already_said(db, OWNER, row)
    out = await one_shot.fire_due(db, now=(NOW + timedelta(minutes=31)).astimezone(timezone.utc))
    assert out["raised"] == 0 and out.get("superseded") == 1
    assert await db.opportunities.count_documents({}) == 0


@pytest.mark.asyncio
async def test_creating_a_watched_situation_from_chat_sets_the_reminder(monkeypatch):
    from unittest.mock import AsyncMock
    from situations.models import SituationUpdate
    from situations.service import SituationService

    await _clock(monkeypatch)
    monkeypatch.setattr(SituationService, "_note_opportunity_change", AsyncMock())
    db = AsyncMongoMockClient().stated_chat_v1
    result = await SituationService(db).apply(
        user_id=OWNER, session_id="s1", reasoning_epoch="e1",
        user_message="Ho messo su il ragù, deve cuocere per 2 ore",
        update=SituationUpdate(operation="create", summary="Ragù sul fuoco",
                               attention_intent="Dire quando è pronto"),
    )
    assert result["stated_reminder"]["at_local"] == "12:00"
    assert await db.reminders.count_documents({"origin": "situation_stated_time"}) == 1
