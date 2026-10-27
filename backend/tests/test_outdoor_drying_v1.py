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


@pytest.mark.asyncio
async def test_the_place_is_the_situations_never_the_phone(monkeypatch):
    from unittest.mock import AsyncMock
    from home.service import HomeService
    from places import lookup

    monkeypatch.setattr(HomeService, "_where_they_are", AsyncMock(side_effect=AssertionError("no device GPS")))
    monkeypatch.setattr(lookup, "suggest", AsyncMock(return_value={
        "available": True, "suggestions": [{"place_id": "t", "primary": "Tarquinia", "text": "Tarquinia, VT"}]}))
    monkeypatch.setattr(lookup, "resolve", AsyncMock(return_value={
        "available": True, "place_id": "t", "locality": "Tarquinia", "latitude": 42.2534, "longitude": 11.7581}))
    sit = _Sit(datetime(2026, 10, 27, 9, 0, tzinfo=ROME))
    sit.location_label = "Tarquinia"
    place = await od.where(AsyncMongoMockClient().drying_where_v1, OWNER, sit)
    assert place == {"lat": 42.25, "lon": 11.76, "label": "Tarquinia", "ref": ""}
    sit.location_label = ""
    assert await od.where(AsyncMongoMockClient().drying_where2_v1, OWNER, sit) is None


# --- 27/10: the plan must exist whatever path created the Situation ---------

@pytest.mark.asyncio
async def test_a_drying_situation_created_without_attention_is_still_planned(monkeypatch):
    from unittest.mock import AsyncMock
    from situations.models import SituationUpdate
    from situations.service import SituationService

    calls = []

    async def plan(db, owner, situation, **kw):
        calls.append(situation.id)
        await db.reminders.insert_one({"id": f"rem_sit_{situation.id}", "user_id": owner,
                                       "status": "open", "meta": {"kind": "drying_end"}})
        return {"at_local": "16:45"}

    monkeypatch.setattr(od, "plan", plan)
    from opportunities.discovery import OpportunityDiscovery
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().drying_created_v1
    out = await SituationService(db).apply(
        user_id=OWNER, session_id="s", reasoning_epoch="e1", user_message="",
        update=SituationUpdate(operation="create", summary="Panni stesi in terrazzo"))
    assert out["status"] == "success" and len(calls) == 1
    # The self-check finds nothing left to plan.
    assert await od.plan_missing(db, OWNER) == []


@pytest.mark.asyncio
async def test_self_check_plans_a_drying_situation_that_has_none(monkeypatch):
    from situations.models import SituationState

    async def plan(db, owner, situation, **kw):
        return {"at_local": "16:45"}

    monkeypatch.setattr(od, "plan", plan)
    db = AsyncMongoMockClient().drying_missing_v1
    await db.situations.insert_one(SituationState(id="sit_x", user_id=OWNER, summary="Ho steso il bucato").model_dump())
    await db.situations.insert_one(SituationState(id="sit_y", user_id=OWNER, summary="Riunione alle 15").model_dump())
    found = await od.plan_missing(db, OWNER)
    assert [f["ref"] for f in found] == ["situation:sit_x"]


@pytest.mark.asyncio
async def test_one_voice_for_a_drying_situation():
    from types import SimpleNamespace

    db = AsyncMongoMockClient().drying_voice_v1
    await db.agent_goals.insert_one({"owner_id": OWNER, "id": "gol_1", "source_refs": ["situation:sit_dry"]})
    need = SimpleNamespace(goal_id="gol_1")
    assert await od.situation_of(db, OWNER, "agent_need", need) == "sit_dry"
    assert not await od.speaks_for(db, OWNER, "sit_dry")
    await db.reminders.insert_one({"id": "rem_sit_sit_dry", "user_id": OWNER, "status": "open",
                                   "meta": {"kind": "drying_end"}})
    assert await od.speaks_for(db, OWNER, "sit_dry")
    opp = SimpleNamespace(evidence=[SimpleNamespace(ref="situation:sit_dry")])
    assert await od.situation_of(db, OWNER, "opportunity", opp) == "sit_dry"


def test_delivery_keeps_the_watch_in_the_app_when_the_plan_speaks():
    import inspect
    from delivery import service

    src = inspect.getsource(service.DeliveryService.evaluate_subject)
    assert "computed_plan_speaks" in src and "requires_response" in src


@pytest.mark.asyncio
async def test_after_dark_it_says_so_now():
    db = AsyncMongoMockClient().drying_night_v1
    hung = datetime(2026, 10, 27, 15, 30, tzinfo=ROME)
    now = datetime(2026, 10, 27, 18, 40, tzinfo=ROME)
    out = await od.plan(db, OWNER, _Sit(hung), now=now.astimezone(timezone.utc), tz=ROME, place=PLACE,
                        hours=day(hung, temp=15, rh=75, wind=6, sun=200, dusk_hour=17))
    row = await db.reminders.find_one({"id": "rem_sit_sit_dry"})
    assert out["not_today"] and row["title"].startswith("È già buio")
    assert datetime.fromisoformat(row["due_at"]).astimezone(ROME).strftime("%H:%M") == "18:42"
