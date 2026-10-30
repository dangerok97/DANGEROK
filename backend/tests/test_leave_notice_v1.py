"""«È ora di metterti in moto»: leave time computed by code, route ready."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from places import leave_notice as ln

ROME = ZoneInfo("Europe/Rome")
OWNER = "usr_leave_v1"
NOW = datetime(2026, 10, 30, 13, 0, tzinfo=ROME)
EVENT = {"ref": "calendar:ev1", "title": "Parrucchiere", "location": "Montalto di Castro",
         "starts_at": datetime(2026, 10, 30, 15, 0, tzinfo=ROME).isoformat(), "all_day": False}


@pytest.fixture
def roads(monkeypatch):
    from places import routing
    monkeypatch.setattr(routing, "capabilities", lambda: {"available": True, "modes": ["drive", "walk"]})
    route = AsyncMock(return_value={"available": True, "duration_seconds": 25 * 60, "reflects_current_traffic": True})
    monkeypatch.setattr(routing, "get_route", route)
    monkeypatch.setattr(ln, "origin_for", AsyncMock(return_value={"latitude": 42.25, "longitude": 11.76, "kind": "home"}))
    monkeypatch.setattr(ln, "destination_for", AsyncMock(return_value={"latitude": 42.35, "longitude": 11.61,
                                                                       "label": "Montalto di Castro"}))
    return route


@pytest.mark.asyncio
async def test_leave_time_is_drive_time_plus_margin_with_route(roads):
    db = AsyncMongoMockClient().leave_v1
    out = await ln.plan_event(db, OWNER, EVENT, now=NOW.astimezone(timezone.utc), tz=ROME)
    assert out["status"] == "planned" and out["leave_at_local"] == "14:25" and out["minutes"] == 25
    row = await db.reminders.find_one({})
    assert datetime.fromisoformat(row["due_at"]).astimezone(ROME).strftime("%H:%M") == "14:25"
    assert row["title"].startswith("È ora di metterti in moto per «Parrucchiere» alle 15:00: circa 25 min in auto da casa")
    assert row["meta"]["route_url"].startswith("https://www.google.com/maps/dir/?api=1&destination=42.35000,11.61000")


@pytest.mark.asyncio
async def test_late_says_so_now_and_told_is_never_rewritten(roads):
    db = AsyncMongoMockClient().leave_late_v1
    now = datetime(2026, 10, 30, 14, 40, tzinfo=ROME).astimezone(timezone.utc)
    out = await ln.plan_event(db, OWNER, EVENT, now=now, tz=ROME)
    assert out["late"] is True
    row = await db.reminders.find_one({})
    assert "dovresti già essere in viaggio" in row["title"]
    await db.reminders.update_one({"id": row["id"]}, {"$set": {"notified_state": "raised"}})
    assert (await ln.plan_event(db, OWNER, EVENT, now=now, tz=ROME))["status"] == "already_told"


@pytest.mark.asyncio
async def test_no_origin_or_destination_is_said_not_guessed(monkeypatch):
    from places import routing
    monkeypatch.setattr(routing, "capabilities", lambda: {"available": True, "modes": ["drive"]})
    monkeypatch.setattr(ln, "origin_for", AsyncMock(return_value=None))
    db = AsyncMongoMockClient().leave_none_v1
    assert (await ln.plan_event(db, OWNER, EVENT, now=NOW, tz=ROME))["status"] == "needs_location"
    monkeypatch.setattr(ln, "origin_for", AsyncMock(return_value={"latitude": 1, "longitude": 1, "kind": "home"}))
    monkeypatch.setattr(ln, "destination_for", AsyncMock(return_value=None))
    assert (await ln.plan_event(db, OWNER, EVENT, now=NOW, tz=ROME))["status"] == "destination_unresolved"
    assert await db.reminders.count_documents({}) == 0


@pytest.mark.asyncio
async def test_plan_owner_cancels_the_notice_of_a_removed_appointment(roads, monkeypatch):
    import opportunities.snapshot as snapshot
    import timezone_service

    async def clock(_db, _owner, *, now=None):
        return {"local_datetime": NOW.isoformat()}

    events = [dict(EVENT)]

    async def calendar(_db, _owner, _now):
        return events

    monkeypatch.setattr(timezone_service, "user_clock_context", clock)
    monkeypatch.setattr(snapshot, "_calendar", calendar)
    db = AsyncMongoMockClient().leave_owner_v1
    rows = await ln.plan_owner(db, OWNER, now=NOW.astimezone(timezone.utc))
    assert rows[0]["status"] == "planned"
    events.clear()
    await ln.plan_owner(db, OWNER, now=NOW.astimezone(timezone.utc))
    assert (await db.reminders.find_one({}))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_the_notice_carries_the_route_to_the_app_and_its_own_push_words(roads):
    from memos import one_shot
    from opportunities.models import Opportunity

    db = AsyncMongoMockClient().leave_push_v1
    await ln.plan_event(db, OWNER, EVENT, now=NOW.astimezone(timezone.utc), tz=ROME)
    await one_shot.fire_due(db, now=datetime(2026, 10, 30, 14, 25, 30, tzinfo=ROME).astimezone(timezone.utc))
    opp = Opportunity(**{k: v for k, v in (await db.opportunities.find_one({})).items() if k != "_id"})
    home = opp.for_home()["reminder"]
    assert home["route_url"].startswith("https://www.google.com/maps/dir/")
    copy = one_shot.push_decision(opp)["copy"]
    assert copy["title"] == "È ora di metterti in moto" and "Parrucchiere" not in copy["public_body"]


@pytest.mark.asyncio
async def test_a_business_in_a_town_falls_back_to_the_town(monkeypatch):
    from places import lookup
    from places.service import PlacesService

    monkeypatch.setattr(PlacesService, "resolve_destination", AsyncMock(return_value=SimpleNamespace(resolved=False, place=None)))

    async def suggest(q, **kw):
        if q == "Montalto di Castro":
            return {"available": True, "suggestions": [{"place_id": "town", "primary": "Montalto di Castro", "types": ["locality"]}]}
        return {"available": True, "suggestions": [{"place_id": "a", "primary": "Salone A"}, {"place_id": "b", "primary": "Salone B"}]}

    monkeypatch.setattr(lookup, "suggest", suggest)
    monkeypatch.setattr(lookup, "resolve", AsyncMock(return_value={"available": True, "latitude": 42.35, "longitude": 11.61,
                                                                  "locality": "Montalto di Castro"}))
    d = await ln.destination_for(AsyncMongoMockClient().leave_dest_v1, OWNER, "parrucchiere a Montalto di Castro",
                                 {"latitude": 42.25, "longitude": 11.76})
    assert d == {"latitude": 42.35, "longitude": 11.61, "label": "Montalto di Castro"}
