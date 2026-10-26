"""Deadlines the person set are seen by the review, and a review runs in time."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from opportunities import deadlines
from ops import selfcheck

OWNER = "usr_deadlines_v1"
ROME = ZoneInfo("Europe/Rome")


async def _seed(db, now):
    tomorrow = (now + timedelta(days=1)).date().isoformat()
    await db.decisions.insert_many([
        {"id": "dec_tax", "user_id": OWNER, "status": "open", "title": "Pagare F24",
         "deadline": f"{tomorrow}T12:00:00+00:00"},
        {"id": "dec_done", "user_id": OWNER, "status": "resolved", "title": "Fatto",
         "deadline": f"{tomorrow}T12:00:00+00:00"},
        {"id": "dec_far", "user_id": OWNER, "status": "open", "title": "Lontano",
         "deadline": (now + timedelta(days=30)).isoformat()},
        {"id": "dec_step", "user_id": OWNER, "status": "open", "title": "Consegna tesi",
         "deadline": f"{tomorrow}T12:00:00+00:00", "metadata": {"plan_item_id": "it_linked"}},
    ])
    await db.life_os_plans.insert_one({
        "id": "lop_1", "user_id": OWNER, "status": "active", "title": "Tesi",
        "target_date": (now + timedelta(days=5)).date().isoformat(),
        "items": [
            {"id": "it_linked", "title": "Consegna tesi", "status": "not_started", "due_date": tomorrow},
            {"id": "it_open", "title": "Rileggere capitolo 2", "status": "in_progress",
             "due_date": now.date().isoformat()},
            {"id": "it_done", "title": "Bibliografia", "status": "completed", "due_date": tomorrow},
        ],
    })


@pytest.mark.asyncio
async def test_open_deadlines_are_read_once_and_as_facts():
    db = AsyncMongoMockClient().deadlines_v1
    now = datetime(2026, 10, 26, 10, 0, tzinfo=ROME)
    await _seed(db, now)
    rows = await deadlines.upcoming(db, OWNER, now)
    refs = [r["ref"] for r in rows]
    assert refs == ["plan_item:lop_1:it_open", "decision:dec_tax", "decision:dec_step", "plan:lop_1"]
    facts = {f["ref"]: f for f in deadlines.as_facts(rows, now)}
    assert facts["decision:dec_tax"]["due_local"] == "2026-10-27" and facts["decision:dec_tax"]["days_left"] == 1
    assert facts["plan_item:lop_1:it_open"]["days_left"] == 0 and not facts["plan_item:lop_1:it_open"]["overdue"]


@pytest.mark.asyncio
async def test_snapshot_carries_deadlines_and_they_are_citable(monkeypatch):
    from opportunities import snapshot

    db = AsyncMongoMockClient().deadlines_snapshot_v1
    now = datetime.now(ROME)
    await _seed(db, now)
    rows = await snapshot._deadlines(db, OWNER, now)
    snap = {"deadlines": rows, "calendar": []}
    refs = snapshot.evidence_refs(snap)
    assert refs["decision:dec_tax"] == "deadline"
    temporal = snapshot._temporal_facts(snap, now)
    assert temporal["deadline_today"] and temporal["deadline_tomorrow"]


def test_review_moments_evening_before_and_morning_of():
    local_now = datetime(2026, 10, 26, 10, 0, tzinfo=ROME)
    due = datetime(2026, 10, 27, 23, 59, tzinfo=ROME)
    moments = dict(selfcheck.deadline_moments(due, True, local_now))
    assert moments["eve"] == datetime(2026, 10, 26, 18, 0, tzinfo=ROME)
    assert moments["morning"] == datetime(2026, 10, 27, 9, 0, tzinfo=ROME)
    timed = dict(selfcheck.deadline_moments(datetime(2026, 10, 27, 15, 0, tzinfo=ROME), False, local_now))
    assert timed["before"] == datetime(2026, 10, 27, 13, 0, tzinfo=ROME)


@pytest.mark.asyncio
async def test_self_check_arranges_the_evening_review_once(monkeypatch):
    import timezone_service

    db = AsyncMongoMockClient().deadlines_selfcheck_v1
    await db.ambient_wakes.create_index("identity", unique=True)
    local_now = datetime.now(ROME).replace(hour=16, minute=0, second=0, microsecond=0)
    now = local_now.astimezone(timezone.utc)
    await _seed(db, local_now)

    async def clock(_db, _owner, *, now=None):
        return {"local_datetime": local_now.isoformat()}

    monkeypatch.setattr(timezone_service, "user_clock_context", clock)
    found = await selfcheck._review_near_deadlines(db, OWNER, now)
    refs = sorted(f["ref"] for f in found)
    # Tomorrow's deadlines get tonight's 18:00 look; today's step had its moments already.
    assert refs == ["decision:dec_step", "decision:dec_tax"] and all(f["repaired"] for f in found)
    wake = await db.ambient_wakes.find_one({"source_ref": {"$regex": "^deadline_due:decision:dec_tax:eve"}})
    assert datetime.fromisoformat(wake["scheduled_for"]) == local_now.replace(hour=18).astimezone(timezone.utc)
    assert not await selfcheck._review_near_deadlines(db, OWNER, now)
