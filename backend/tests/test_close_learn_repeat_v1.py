"""Finished things close, the person's own times teach, reminders repeat."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from memos import one_shot
from situations import calibration, closing

ROME = ZoneInfo("Europe/Rome")
OWNER = "usr_clr_v1"


@pytest.fixture
def quiet(monkeypatch):
    from opportunities.discovery import OpportunityDiscovery
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))


async def _situation(db, sid="sit_1", summary="Riunione"):
    from situations.models import SituationState
    await db.situations.insert_one(SituationState(id=sid, user_id=OWNER, summary=summary).model_dump())


@pytest.mark.asyncio
async def test_told_six_hours_ago_and_never_closed_is_closed_by_ora(quiet):
    db = AsyncMongoMockClient().clr_auto_v1
    await _situation(db)
    now = datetime(2026, 10, 28, 4, 0, tzinfo=timezone.utc)
    await db.reminders.insert_one({"id": "rem_sit_sit_1", "user_id": OWNER, "status": "open",
                                   "notified_state": "raised", "notified_at": (now - timedelta(hours=7)).isoformat(),
                                   "meta": {"situation_id": "sit_1", "kind": "drying_end"}})
    found = await closing.close_finished(db, OWNER, now=now)
    assert found == [{"code": "situation_auto_closed", "ref": "situation:sit_1", "repaired": True}]
    sit = await db.situations.find_one({"id": "sit_1"})
    assert sit["status"] == "resolved" and sit["history"][-1]["source"] == "inferred"
    exp = await db.situation_experiences.find_one({"situation_id": "sit_1"})
    assert exp["closed_by"] == "ora"


@pytest.mark.asyncio
async def test_recent_notice_or_pending_not_yet_keeps_it_open(quiet):
    db = AsyncMongoMockClient().clr_open_v1
    await _situation(db)
    now = datetime(2026, 10, 28, 4, 0, tzinfo=timezone.utc)
    await db.reminders.insert_one({"id": "rem_sit_sit_1", "user_id": OWNER, "status": "open",
                                   "notified_state": "raised", "notified_at": (now - timedelta(hours=2)).isoformat(),
                                   "meta": {"situation_id": "sit_1"}})
    assert await closing.close_finished(db, OWNER, now=now) == []
    await db.reminders.update_one({"id": "rem_sit_sit_1"}, {"$set": {"notified_at": (now - timedelta(hours=9)).isoformat()}})
    await db.reminders.insert_one({"id": "rem_later", "user_id": OWNER, "status": "open",
                                   "due_at": (now + timedelta(minutes=10)).isoformat(), "meta": {"situation_id": "sit_1"}})
    assert await closing.close_finished(db, OWNER, now=now) == []


async def _arrived(db, meta, *, start, told):
    await db.reminders.insert_one({"id": "rem_sit_sit_1", "user_id": OWNER, "status": "open", "title": "Asciutti?",
                                   "due_at": told.isoformat(), "meta": {**meta, "start": start.isoformat()}})
    await one_shot.fire_due(db, now=told + timedelta(minutes=1))
    return (await db.opportunities.find_one({}))["id"]


@pytest.mark.asyncio
async def test_not_yet_teaches_and_done_closes(quiet):
    db = AsyncMongoMockClient().clr_learn_v1
    await _situation(db, summary="Panni stesi")
    start = datetime.now(timezone.utc) - timedelta(hours=4)
    opp = await _arrived(db, {"situation_id": "sit_1", "kind": "drying_end"}, start=start, told=start + timedelta(hours=4) - timedelta(minutes=2))
    later = await one_shot.act(db, OWNER, opp, "snooze", 60)
    assert later["ok"]
    f = await calibration.factor(db, OWNER, "drying")
    assert 1.1 < f < 1.15  # 4 h planned, needed +1 h: halfway to 1.25
    # The second «non ancora» on the same thing does not teach twice.
    snoozed = await db.reminders.find_one({"origin": "snooze"})
    assert snoozed["meta"]["situation_id"] == "sit_1"
    await db.reminders.update_one({"id": snoozed["id"]}, {"$set": {"due_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}})
    await one_shot.fire_due(db)
    opp2 = (await db.opportunities.find_one({"identity_key": f"one_shot_reminder:{snoozed['id']}"}))["id"]
    await one_shot.act(db, OWNER, opp2, "snooze", 10)
    assert await calibration.factor(db, OWNER, "drying") == f
    # «Fatto» on the next one closes the Situation as the person's moment.
    nxt = await db.reminders.find_one({"origin": "snooze", "status": "open", "notified_state": {"$exists": False}})
    await db.reminders.update_one({"id": nxt["id"]}, {"$set": {"due_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}})
    await one_shot.fire_due(db)
    opp3 = (await db.opportunities.find_one({"identity_key": f"one_shot_reminder:{nxt['id']}"}))["id"]
    done = await one_shot.act(db, OWNER, opp3, "done")
    assert done["situation_closed"] is True
    exp = await db.situation_experiences.find_one({"situation_id": "sit_1"})
    assert exp["closed_by"] == "person"


@pytest.mark.asyncio
async def test_the_factor_is_used_and_bounded():
    db = AsyncMongoMockClient().clr_bound_v1
    meta = {"kind": "typical_end", "typical_key": "dishwasher"}
    for _ in range(10):
        await calibration.learn_not_yet(db, OWNER, meta, planned_minutes=60, extra_minutes=180)
    assert await calibration.factor(db, OWNER, "typical:dishwasher") == calibration.HIGH
    assert await calibration.factor(db, OWNER, "drying") == 1.0
    assert calibration.key_of({"kind": "stated_end"}) is None


def test_next_occurrence_keeps_local_time_across_dst_and_skips_weekends():
    due = datetime(2026, 10, 24, 8, 0, tzinfo=ROME).astimezone(timezone.utc)  # Saturday, CEST
    nxt = one_shot.next_occurrence(due, "daily", "Europe/Rome", after=due)
    assert nxt.astimezone(ROME).strftime("%d %H:%M") == "25 08:00"  # Sunday, now CET
    fri = datetime(2026, 10, 30, 8, 0, tzinfo=ROME).astimezone(timezone.utc)
    assert one_shot.next_occurrence(fri, "weekdays", "Europe/Rome", after=fri).astimezone(ROME).day == 2
    assert one_shot.next_occurrence(fri, "weekly", "Europe/Rome", after=fri).astimezone(ROME).day == 6


@pytest.mark.asyncio
async def test_a_repeating_reminder_plans_the_next_one_even_if_missed(monkeypatch):
    import timezone_service
    from memos.caps import list_reminders, set_reminder

    now = datetime(2026, 10, 28, 7, 0, tzinfo=ROME)

    async def clock(_db, _owner, *, now=None):
        return {"local_datetime": datetime(2026, 10, 28, 7, 0, tzinfo=ROME).isoformat()}

    monkeypatch.setattr(timezone_service, "user_clock_context", clock)
    db = AsyncMongoMockClient().clr_repeat_v1
    rt = {"db": db, "user_id": OWNER}
    out = await set_reminder({"what": "Pastiglia", "at_local": "2026-10-28T08:00", "repeat": "daily"}, rt)
    assert out.payload["repeat"] == "ogni giorno" and out.payload["repeats"] == "ogni giorno"
    # Missed (ORA stopped for hours): still the next day is planned.
    await one_shot.fire_due(db, now=datetime(2026, 10, 28, 12, 0, tzinfo=ROME).astimezone(timezone.utc))
    rows = await db.reminders.find({"status": "open", "notified_state": {"$exists": False}}).to_list(5)
    assert [datetime.fromisoformat(r["due_at"]).astimezone(ROME).strftime("%d %H:%M") for r in rows] == ["29 08:00"]
    bad = await set_reminder({"what": "X", "delay_minutes": 5, "repeat": "hourly"}, rt)
    assert bad.payload["error"] == "invalid_repeat"
