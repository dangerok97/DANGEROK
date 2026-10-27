"""Drying outdoors: computed from the hourly weather, announced by code."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from situations import outdoor_drying as od

ROME = ZoneInfo("Europe/Rome")
OWNER = "usr_drying_v1"


def day(start_local, *, temp, rh, wind=10, sun=500, rain_at=None, dusk_hour=18, hours=30):
    out = []
    base = start_local.replace(minute=0, second=0, microsecond=0)
    for i in range(-2, hours):
        at = base + timedelta(hours=i)
        is_day = 7 <= at.hour < dusk_hour
        out.append({"at": at.astimezone(timezone.utc), "temp_c": temp if is_day else temp - 4, "rh": rh if is_day else min(95, rh + 20),
                    "wind_kmh": wind, "radiation": sun if is_day else 0, "is_day": is_day,
                    "rain_pct": 80 if rain_at is not None and at.hour == rain_at and at.date() == base.date() else 5,
                    "rain_mm": 1.0 if rain_at is not None and at.hour == rain_at and at.date() == base.date() else 0})
    return out


def hours_to_dry(**kw):
    start = datetime(2026, 7, 10, 9, 0, tzinfo=ROME)
    r = od.compute(day(start, **kw), start=start, now=start)
    return (r["dry_at"] - start).total_seconds() / 3600 if r["dry_at"] else None


def test_calibration_matches_common_experience():
    assert 1.5 <= hours_to_dry(temp=30, rh=35, wind=12, sun=700) <= 3        # hot summer day
    assert 4.5 <= hours_to_dry(temp=17, rh=60, wind=12, sun=450) <= 8       # sunny autumn day
    grey = hours_to_dry(temp=14, rh=85, wind=5, sun=100)
    assert grey is None or grey > 10                                         # grey, damp: not today


def test_rain_before_dry_is_reported_and_stops_drying():
    start = datetime(2026, 10, 27, 9, 0, tzinfo=ROME)
    r = od.compute(day(start, temp=17, rh=60, rain_at=12), start=start, now=start)
    assert r["rain_at"].astimezone(ROME).hour == 12
    dry = od.compute(day(start, temp=17, rh=60), start=start, now=start)["dry_at"]
    assert r["dry_at"] > dry


@pytest.mark.parametrize("text,ok", [
    ("Ho steso i panni", True), ("ho messo il bucato fuori sul balcone", True),
    ("lenzuola stese in terrazzo", True), ("ho steso i panni in casa sul termosifone", False),
    ("quando si asciugano i panni?", False), ("ho messo la lavastoviglie", False),
])
def test_applies(text, ok):
    assert od.applies(text) is ok


class _Sit:
    id = "sit_dry"
    summary = "Panni stesi sul balcone"
    status = "active"
    attention_intent = "Dire quando sono asciutti"
    next_check_summary = None
    facts: list = []
    linked_object_refs: list = []

    def __init__(self, started):
        self.started_at = started.isoformat()
        self.created_at = started.isoformat()


PLACE = {"lat": 42.25, "lon": 11.76, "label": "Tarquinia", "ref": "place:pl_home"}


@pytest.mark.asyncio
async def test_plan_writes_the_reminders_and_moves_with_the_weather():
    db = AsyncMongoMockClient().drying_plan_v1
    start = datetime(2026, 10, 27, 9, 40, tzinfo=ROME)
    sit = _Sit(start)
    out = await od.plan(db, OWNER, sit, now=start.astimezone(timezone.utc), tz=ROME, place=PLACE,
                        hours=day(start, temp=17, rh=60, wind=12, sun=450))
    assert out["dry_at_local"] and not out["not_today"] and out["rain_at_local"] is None
    row = await db.reminders.find_one({"id": "rem_sit_sit_dry"})
    assert row["meta"]["kind"] == "drying_end" and row["title"].startswith("Dovrebbero essere asciutti")
    first_due = row["due_at"]
    # An hour later the forecast brings rain at 13: warning before, later end.
    later = start + timedelta(hours=1)
    out2 = await od.plan(db, OWNER, sit, now=later.astimezone(timezone.utc), tz=ROME, place=PLACE,
                         hours=day(start, temp=17, rh=60, wind=12, sun=450, rain_at=13))
    assert out2["rain_at_local"] == "13:00"
    rain = await db.reminders.find_one({"id": "rem_sit_sit_dry_rain"})
    assert datetime.fromisoformat(rain["due_at"]).astimezone(ROME).strftime("%H:%M") == "12:15"
    assert (await db.reminders.find_one({"id": "rem_sit_sit_dry"}))["due_at"] > first_due
    # The forecast clears again: the rain warning is withdrawn.
    await od.plan(db, OWNER, sit, now=(later + timedelta(minutes=5)).astimezone(timezone.utc), tz=ROME,
                  place=PLACE, hours=day(start, temp=17, rh=60, wind=12, sun=450))
    assert (await db.reminders.find_one({"id": "rem_sit_sit_dry_rain"}))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_grey_day_says_not_today_and_reminds_before_dark():
    db = AsyncMongoMockClient().drying_grey_v1
    start = datetime(2026, 10, 27, 10, 0, tzinfo=ROME)
    out = await od.plan(db, OWNER, _Sit(start), now=start.astimezone(timezone.utc), tz=ROME, place=PLACE,
                        hours=day(start, temp=13, rh=88, wind=4, sun=80))
    assert out["not_today"] and out["at_local"] == "17:30"
    row = await db.reminders.find_one({"id": "rem_sit_sit_dry"})
    assert "prima di sera" in row["title"]


@pytest.mark.asyncio
async def test_already_told_is_never_rewritten():
    db = AsyncMongoMockClient().drying_told_v1
    start = datetime(2026, 10, 27, 9, 0, tzinfo=ROME)
    await od.plan(db, OWNER, _Sit(start), now=start.astimezone(timezone.utc), tz=ROME, place=PLACE,
                  hours=day(start, temp=17, rh=60))
    await db.reminders.update_one({"id": "rem_sit_sit_dry"}, {"$set": {"notified_state": "raised"}})
    before = await db.reminders.find_one({"id": "rem_sit_sit_dry"})
    await od.plan(db, OWNER, _Sit(start), now=(start + timedelta(hours=2)).astimezone(timezone.utc), tz=ROME,
                  place=PLACE, hours=day(start, temp=12, rh=90))
    assert (await db.reminders.find_one({"id": "rem_sit_sit_dry"}))["due_at"] == before["due_at"]


@pytest.mark.asyncio
async def test_arm_uses_the_computation_for_things_drying_outdoors(monkeypatch):
    import timezone_service
    from situations.stated_time import arm

    now = datetime(2026, 10, 27, 9, 40, tzinfo=ROME)

    async def clock(_db, _owner, *, now=None):
        return {"local_datetime": datetime(2026, 10, 27, 9, 40, tzinfo=ROME).isoformat()}

    async def plan(db, owner, situation, **kw):
        return {"at_local": "15:10", "dry_at_local": "15:10", "not_today": False, "rain_at_local": None}

    monkeypatch.setattr(timezone_service, "user_clock_context", clock)
    monkeypatch.setattr(od, "plan", plan)
    out = await arm(AsyncMongoMockClient().drying_arm_v1, OWNER, _Sit(now), "Ho steso i panni")
    assert out["drying"] and out["at_local"] == "15:10"
