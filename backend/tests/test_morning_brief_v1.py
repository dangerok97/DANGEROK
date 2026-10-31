"""The morning brief: the day in one notification, by code, once a day."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from brief import morning

ROME = ZoneInfo("Europe/Rome")
OWNER = "usr_brief_v1"


def test_compose_reads_like_a_morning_line():
    text = morning.compose(["Dentista alle 10:30"], ["F24 oggi"], ["Pastiglia alle 20:00"],
                           "Tarquinia, 12-19 °C, pioggia 10%: se stendi alle 09:00, asciutti verso le 15:10")
    assert text == ("Oggi: Dentista alle 10:30; F24 oggi. Promemoria: Pastiglia alle 20:00. "
                    "Tarquinia, 12-19 °C, pioggia 10%: se stendi alle 09:00, asciutti verso le 15:10.")
    assert morning.compose([], [], [], "") == ""
    assert len(morning.compose(["x" * 100] * 3, ["y" * 100], [], "")) == morning.MAX_CHARS


@pytest.fixture
def world(monkeypatch):
    import timezone_service
    clock = {"now": datetime(2026, 10, 30, 8, 5, tzinfo=ROME)}

    async def user_clock(_db, _owner, *, now=None):
        return {"local_datetime": clock["now"].isoformat()}

    async def apps(db, owner, local_now):
        return ["Dentista alle 10:30"]

    async def nothing(db, owner, local_now):
        return [] if not isinstance(local_now, str) else ""

    async def no_weather(db, owner, local_now):
        return ""

    monkeypatch.setattr(timezone_service, "user_clock_context", user_clock)
    monkeypatch.setattr(morning, "_appointments", apps)
    monkeypatch.setattr(morning, "_deadlines", nothing)
    monkeypatch.setattr(morning, "_home_weather", no_weather)
    return clock


@pytest.mark.asyncio
async def test_once_a_day_at_the_hour_through_the_reminder_lane(world):
    from memos import one_shot

    db = AsyncMongoMockClient().brief_v1
    await db.push_endpoints.insert_one({"owner_id": OWNER, "status": "active"})
    await db.users.insert_one({"user_id": OWNER})
    out = await morning.fire_due(db)
    assert out["queued"] == 1
    assert (await morning.fire_due(db))["queued"] == 0  # not twice the same day
    row = await db.reminders.find_one({"origin": "morning_brief"})
    assert row["title"].startswith("Oggi: Dentista alle 10:30")
    await one_shot.fire_due(db)
    opp = await db.opportunities.find_one({})
    from opportunities.models import Opportunity
    o = Opportunity(**{k: v for k, v in opp.items() if k != "_id"})
    assert o.for_home()["reminder"] == {"kind": "morning_brief"}
    decision = one_shot.push_decision(o)
    assert decision["copy"]["public_title"] == "Il punto del mattino" and "Dentista" not in decision["copy"]["public_body"]


@pytest.mark.asyncio
async def test_not_before_the_hour_not_when_off_not_when_late(world):
    db = AsyncMongoMockClient().brief_off_v1
    await db.push_endpoints.insert_one({"owner_id": OWNER, "status": "active"})
    await db.users.insert_one({"user_id": OWNER})
    world["now"] = datetime(2026, 10, 30, 7, 55, tzinfo=ROME)
    assert (await morning.fire_due(db))["checked"] == 0
    world["now"] = datetime(2026, 10, 30, 11, 30, tzinfo=ROME)
    assert (await morning.fire_due(db))["checked"] == 0
    world["now"] = datetime(2026, 10, 30, 8, 1, tzinfo=ROME)
    await morning.set_preference(db, OWNER, enabled=False)
    assert (await morning.fire_due(db))["checked"] == 0
    await morning.set_preference(db, OWNER, enabled=True, hour=7)
    assert (await morning.preference(db, OWNER)) == {"enabled": True, "hour": 7}
    assert (await morning.fire_due(db))["queued"] == 1


@pytest.mark.asyncio
async def test_todays_reminders_are_listed():
    db = AsyncMongoMockClient().brief_rem_v1
    now = datetime(2026, 10, 30, 8, 0, tzinfo=ROME)
    await db.reminders.insert_many([
        {"user_id": OWNER, "status": "open", "title": "Pastiglia", "due_at": now.replace(hour=20).astimezone(timezone.utc).isoformat()},
        {"user_id": OWNER, "status": "open", "title": "Domani", "due_at": (now + timedelta(days=1)).astimezone(timezone.utc).isoformat()},
    ])
    assert await morning._reminders(db, OWNER, now) == ["Pastiglia alle 20:00"]


@pytest.mark.asyncio
async def test_without_a_saved_home_the_last_drying_place_is_used(monkeypatch):
    from unittest.mock import AsyncMock
    from home.service import HomeService

    monkeypatch.setattr(HomeService, "_where_they_are", AsyncMock(return_value=None))
    db = AsyncMongoMockClient().brief_where_v1
    assert await morning._where(db, OWNER) is None
    await db.situations.insert_one({"user_id": OWNER, "id": "sit_1", "location_label": "Tarquinia"})
    await db.reminders.insert_one({"user_id": OWNER, "updated_at": "2026-10-27T20:00:00+00:00",
                                   "meta": {"kind": "drying_end", "situation_id": "sit_1", "point": [42.25, 11.76]}})
    assert await morning._where(db, OWNER) == (42.25, 11.76, "Tarquinia")


@pytest.mark.asyncio
async def test_setup_status_lists_what_is_missing(monkeypatch):
    from brief import router as br
    from location.service import LocationService
    from unittest.mock import AsyncMock

    db = AsyncMongoMockClient().setup_v1
    monkeypatch.setattr(br, "db", db)
    monkeypatch.setattr(LocationService, "get_preference", AsyncMock(return_value="off"))
    await db.users.insert_one({"user_id": OWNER})
    out = await br.setup_status(user={"user_id": OWNER})
    assert out["missing"] == ["notifications", "location", "home", "travel_mode", "morning_brief"] and not out["done"]
    await db.push_endpoints.insert_one({"owner_id": OWNER, "status": "active"})
    await db.life_places.insert_one({"user_id": OWNER, "role": "home", "state": "confirmed",
                                     "coordinates": {"latitude": 42.2, "longitude": 11.7}})
    from places.travel_mode import set_mode
    await set_mode(db, OWNER, "drive")
    await morning.set_preference(db, OWNER, enabled=True)
    monkeypatch.setattr(LocationService, "get_preference", AsyncMock(return_value="while_using"))
    out = await br.setup_status(user={"user_id": OWNER})
    assert out["done"] and out["missing"] == []
    await br.setup_dismiss(user={"user_id": OWNER})
    assert (await br.setup_status(user={"user_id": OWNER}))["dismissed"]
