"""The morning brief: the day in one notification, by code, once a day."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from brief import morning

ROME = ZoneInfo("Europe/Rome")
OWNER = "usr_brief_v1"


def test_compose_reads_like_a_morning_line():
    text = morning.compose(["10:30 Dentista"], ["F24: scade oggi"], ["Pastiglia alle 20:00"],
                           "Sereno, 11–20 °C, niente pioggia", "Bucato: se stendi alle 9, è asciutto verso le 14.")
    assert text == ("Sereno, 11–20 °C, niente pioggia. Oggi: 10:30 Dentista. Scadenze: F24: scade oggi. "
                    "Promemoria: Pastiglia alle 20:00. Bucato: se stendi alle 9, è asciutto verso le 14.")
    assert morning.compose([], [], [], "") == ""
    assert morning.compose([], [], [], "Sereno").startswith("Sereno. Niente in agenda oggi.")
    assert len(morning.compose(["x" * 100] * 3, ["y" * 100], [], "")) == morning.MAX_CHARS


def test_people_say_the_hour_not_14_01():
    assert morning.clock(datetime(2026, 10, 31, 14, 1)) == "14"
    assert morning.clock(datetime(2026, 10, 31, 14, 23)) == "14:30"
    assert morning.clock(datetime(2026, 10, 31, 9, 0)) == "9"
    assert morning.day_label(datetime(2026, 10, 31).date()) == "Sabato 31 ottobre"


def test_weather_line_in_words():
    w = {"today": {"condition_label": "Sereno", "min_c": 11, "max_c": 20, "rain_chance_pct": 0}}
    assert morning.weather_line(w) == "Sereno, 11–20 °C, niente pioggia"
    w["today"]["rain_chance_pct"] = 60
    assert morning.weather_line(w).endswith("pioggia 60%")
    assert morning.weather_line(None) == ""


@pytest.fixture
def world(monkeypatch):
    import timezone_service
    clock = {"now": datetime(2026, 10, 30, 8, 5, tzinfo=ROME)}

    async def user_clock(_db, _owner, *, now=None):
        return {"local_datetime": clock["now"].isoformat()}

    async def agenda(db, owner, local_now):
        return {"today": ["10:30 · Dentista"], "tomorrow": []}

    async def nothing(db, owner, local_now):
        return [] if not isinstance(local_now, str) else ""

    async def no_weather(db, owner, local_now):
        return None

    monkeypatch.setattr(timezone_service, "user_clock_context", user_clock)
    monkeypatch.setattr(morning, "_agenda", agenda)
    monkeypatch.setattr(morning, "_deadlines", nothing)
    monkeypatch.setattr(morning, "_weather", no_weather)
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
    assert row["title"].startswith("Oggi: 10:30 Dentista")
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


@pytest.mark.asyncio
async def test_the_page_has_the_whole_day(world):
    db = AsyncMongoMockClient().brief_full_v1
    await db.users.insert_one({"user_id": OWNER, "name": "Francesco Rossi"})
    await db.situations.insert_one({"user_id": OWNER, "status": "active", "summary": "Lavatrice avviata",
                                    "next_check_summary": "finisce verso le 10", "updated_at": "x"})
    out = await morning.full(db, OWNER, world["now"])
    assert out["greeting"] == "Buongiorno, Francesco" and out["day"] == "Venerdì 30 ottobre"
    keys = [s["key"] for s in out["sections"]]
    assert keys == ["today", "watching", "missing"]  # no home: says how to get the weather
    assert out["sections"][1]["lines"] == ["Lavatrice avviata — finisce verso le 10"]
