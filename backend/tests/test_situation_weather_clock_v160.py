"""Weather evidence retains the provider's place and clock through the agent.

All responses are synthetic. These tests measure adapter/lifecycle integrity,
not forecast accuracy, physical drying time or real notification delivery.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import providers
from agent.models import AutonomousGoal
from places.models import Coordinates
from places.service import PlacesService
from situations.models import SituationEvent, SituationState
from situations.repository import SituationRepository

OWNER = "weather-v160-synthetic"
NOW = datetime(2026, 10, 11, 21, 45, tzinfo=timezone.utc)


def forecast():
    return {
        "available": True, "provider": "open_meteo", "place": "Tarquinia",
        "observed_at": "2026-10-11T23:30", "retrieved_at": NOW.isoformat(),
        "timezone": "Europe/Rome", "utc_offset_seconds": 7200,
        "condition_label": "Sintetico", "temperature_c": 20, "humidity_pct": 60,
        "wind_kmh": 12, "precipitation_mm": 0,
        "hours": [
            {"time": clock, "datetime": day, "temperature_c": 20,
             "humidity_pct": 60, "wind_kmh": 12, "rain_chance_pct": rain}
            for clock, day, rain in [
                ("23:00", "2026-10-11T23:00", 5),
                ("00:00", "2026-10-12T00:00", 25),
                ("01:00", "2026-10-12T01:00", 55),
            ]
        ], "days": [],
    }


async def setup(monkeypatch, data=None):
    import weather
    from home.service import HomeService

    db = AsyncMongoMockClient().weather_v160
    home = await PlacesService(db).save_place(
        OWNER, label="Luogo sintetico", role="home", locality="Tarquinia",
        coordinates=Coordinates(latitude=42.249, longitude=11.756),
        source="user_stated", role_confirmed_by_user=True,
    )
    goal = AutonomousGoal(
        owner_id=OWNER, status="active", objective="Seguire un esito sintetico",
        desired_outcome="Conoscere il momento utile stimato",
        source_kind="situation_followup", source_refs=["situation:sit_synthetic_v160"],
    )
    await SituationRepository(db).insert(SituationState(
        id="sit_synthetic_v160", user_id=OWNER, summary="Processo sintetico in un luogo fissato",
        attention_intent="Seguire l'esito", location_label="Tarquinia",
        linked_object_refs=[f"place:{home.id}"],
        history=[SituationEvent(revision=1, operation="create", source="user_conversation",
                                changes={"location_label": "Tarquinia"})],
    ))
    read = AsyncMock(return_value=forecast() if data is None else data)
    moved = AsyncMock(return_value=(41.9028, 12.4964, "Roma"))
    monkeypatch.setattr(weather, "capabilities", lambda: {"available": True})
    monkeypatch.setattr(weather, "configured_provider", lambda: "open_meteo")
    monkeypatch.setattr(weather, "forecast_at", read)
    monkeypatch.setattr(HomeService, "_where_they_are", moved)
    monkeypatch.setattr(providers, "_now", lambda: NOW)
    return db, goal, home, read, moved


@pytest.mark.asyncio
async def test_agent_retains_provider_clock_place_and_forecast_dates_across_midnight(monkeypatch):
    db, goal, home, read, moved = await setup(monkeypatch)
    out = await providers.read_weather(db, OWNER, goal,
                                      step=SimpleNamespace(input_refs=[f"place:{home.id}"]))
    assert out.status == "succeeded"
    assert out.provenance.observed_at == "2026-10-11T23:30:00+02:00"
    assert out.provenance.freshness == "fresh"
    assert datetime.fromisoformat(out.provenance.weather_valid_until) > NOW
    assert out.provenance.source_refs == [
        f"place:{home.id}", "situation:sit_synthetic_v160:revision:1",
        f"place_snapshot:{home.id}:{home.updated_at}",
    ]
    text = " ".join(item.text for item in out.claims)
    assert "2026-10-12T00:00:00+02:00" in text
    assert "2026-10-11T23:00:00+02:00" in text
    assert NOW.isoformat() in text and "Europe/Rome" in text
    assert "Tarquinia" in text and "open_meteo" in text
    assert "42.249" not in text and "11.756" not in text
    assert "non misura l'esito fisico" in text
    read.assert_awaited_once_with(lat=42.249, lon=11.756, place="Tarquinia")
    moved.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("case,expected", [
    ("ancient", "stale"), ("three_hours", "stale"), ("ninety_five_minutes", "recent"),
    ("future", "unknown"), ("missing", "unknown"), ("no_clock_anchor", "unknown"),
    ("wrong_offset", "unknown"), ("bad_timezone", "unknown"),
])
async def test_fresh_retrieval_never_turns_old_or_unanchored_data_into_current_evidence(monkeypatch, case, expected):
    data = forecast()
    if case == "ancient":
        data.update(observed_at="2020-01-01T12:00", utc_offset_seconds=3600)
    elif case == "three_hours":
        data["observed_at"] = "2026-10-11T20:30"
    elif case == "ninety_five_minutes":
        data["observed_at"] = "2026-10-11T22:10"
    elif case == "future":
        data["observed_at"] = "2026-10-12T00:00"
    elif case == "missing":
        data["observed_at"] = None
    elif case == "no_clock_anchor":
        data.update(timezone=None, utc_offset_seconds=None)
    elif case == "wrong_offset":
        data["utc_offset_seconds"] = 3600
    else:
        data["timezone"] = "not-a-zone"
    db, goal, home, _, _ = await setup(monkeypatch, data)
    out = await providers.read_weather(db, OWNER, goal,
                                      step=SimpleNamespace(input_refs=[f"place:{home.id}"]))
    assert out.provenance.freshness == expected
    assert out.provenance.weather_valid_until is None
    assert out.provenance.observed_at != NOW.isoformat()
    assert "occorre una lettura aggiornata" in out.observation


@pytest.mark.asyncio
async def test_dst_offset_preserves_observation_instant_without_guessing_ambiguous_forecast(monkeypatch):
    data = forecast()
    data.update(observed_at="2026-10-25T02:30", utc_offset_seconds=7200)
    data["hours"] = [
        {"time": "02:00", "datetime": "2026-10-25T02:00", "temperature_c": 12},
        {"time": "03:00", "datetime": "2026-10-25T03:00", "temperature_c": 13},
    ]
    db, goal, home, _, _ = await setup(monkeypatch, data)
    now = datetime(2026, 10, 25, 0, 45, tzinfo=timezone.utc)
    monkeypatch.setattr(providers, "_now", lambda: now)
    out = await providers.read_weather(db, OWNER, goal,
                                      step=SimpleNamespace(input_refs=[f"place:{home.id}"]))
    observed = datetime.fromisoformat(out.provenance.observed_at)
    assert observed.astimezone(timezone.utc).isoformat() == "2026-10-25T00:30:00+00:00"
    assert datetime.fromisoformat(out.provenance.weather_valid_until) - observed == timedelta(minutes=90)
    text = " ".join(item.text for item in out.claims)
    assert "2026-10-25T02:00 (data/fuso non verificabili)" in text
    assert "2026-10-25T03:00:00+01:00" in text


@pytest.mark.asyncio
async def test_situation_without_fixed_place_does_not_follow_the_users_new_location(monkeypatch):
    db, goal, _, read, moved = await setup(monkeypatch)
    await db.situations.update_one({"id": "sit_synthetic_v160"}, {
        "$set": {"linked_object_refs": [], "location_label": None, "history": []},
    })
    out = await providers.read_weather(db, OWNER, goal, step=SimpleNamespace(input_refs=[]))
    assert out.status == "unavailable"
    assert out.error_type == "situation_location_required"
    assert out.provenance.weather_valid_until is None
    read.assert_not_awaited()
    moved.assert_not_awaited()


@pytest.mark.asyncio
async def test_declared_city_is_resolved_read_only_without_a_saved_home_or_device_location(monkeypatch):
    from places import lookup

    db, goal, home, read, moved = await setup(monkeypatch)
    await db.situations.update_one({"id": "sit_synthetic_v160"}, {"$set": {"linked_object_refs": []}})
    # The owner may have other saved places; the local text is the source.
    before = await db.life_places.count_documents({"user_id": OWNER})
    suggest = AsyncMock(return_value={"available": True, "suggestions": [
        {"place_id": "google-city-synthetic", "primary": "Tarquinia", "text": "Tarquinia, VT, Italia"},
    ]})
    resolve = AsyncMock(return_value={"available": True, "place_id": "google-city-synthetic",
                                    "locality": "Tarquinia", "address": "Tarquinia, VT, Italia",
                                    "latitude": 42.249, "longitude": 11.756})
    monkeypatch.setattr(lookup, "suggest", suggest)
    monkeypatch.setattr(lookup, "resolve", resolve)
    out = await providers.read_weather(db, OWNER, goal, step=SimpleNamespace(input_refs=[]))
    assert out.status == "succeeded" and out.provenance.freshness == "fresh"
    assert out.provenance.source_refs == ["situation:sit_synthetic_v160:revision:1", "google_place:google-city-synthetic"]
    suggest.assert_awaited_once_with("Tarquinia")
    resolve.assert_awaited_once_with("google-city-synthetic")
    read.assert_awaited_once_with(lat=42.249, lon=11.756, place="Tarquinia")
    moved.assert_not_awaited()
    assert await db.life_places.count_documents({"user_id": OWNER}) == before
    assert (await SituationRepository(db).get(OWNER, "sit_synthetic_v160")).revision == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["ambiguous", "wrong_locality", "inferred_label"])
async def test_unverified_text_location_cannot_become_a_weather_anchor(monkeypatch, case):
    from places import lookup

    db, goal, _, read, moved = await setup(monkeypatch)
    await db.situations.update_one({"id": "sit_synthetic_v160"}, {"$set": {"linked_object_refs": []}})
    suggestions = [{"place_id": "synthetic-city-1", "primary": "Tarquinia"}]
    if case == "ambiguous":
        suggestions.append({"place_id": "synthetic-city-2", "primary": "Tarquinia"})
    elif case == "inferred_label":
        await db.situations.update_one({"id": "sit_synthetic_v160"}, {"$set": {"history.0.source": "inferred"}})
    suggest = AsyncMock(return_value={"available": True, "suggestions": suggestions})
    resolve = AsyncMock(return_value={"available": True, "place_id": "synthetic-city-1", "locality": "Another locality",
                                    "latitude": 42.249, "longitude": 11.756})
    monkeypatch.setattr(lookup, "suggest", suggest)
    monkeypatch.setattr(lookup, "resolve", resolve)
    out = await providers.read_weather(db, OWNER, goal, step=SimpleNamespace(input_refs=[]))
    assert out.status == "unavailable" and out.provenance.weather_valid_until is None
    if case == "inferred_label":
        suggest.assert_not_awaited()
    read.assert_not_awaited()
    moved.assert_not_awaited()


@pytest.mark.asyncio
async def test_another_owned_place_is_not_the_situation_anchor(monkeypatch):
    db, goal, _, read, moved = await setup(monkeypatch)
    elsewhere = await PlacesService(db).save_place(
        OWNER, label="Altro luogo sintetico", locality="Roma",
        coordinates=Coordinates(latitude=41.9028, longitude=12.4964), source="user_stated",
    )
    out = await providers.read_weather(db, OWNER, goal,
                                      step=SimpleNamespace(input_refs=[f"place:{elsewhere.id}"]))
    assert out.status == "unavailable" and out.error_type == "situation_place_mismatch"
    read.assert_not_awaited()
    moved.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["situation_revision", "physical_resolution", "place_update"])
async def test_a_source_change_during_forecast_read_invalidates_the_returned_weather(monkeypatch, change):
    db, goal, home, read, _ = await setup(monkeypatch)

    async def read_then_change(**kwargs):
        if change == "situation_revision":
            await db.situations.update_one({"id": "sit_synthetic_v160"}, {"$inc": {"revision": 1}})
        elif change == "physical_resolution":
            await db.situations.update_one({"id": "sit_synthetic_v160"}, {"$set": {"status": "resolved"}})
        else:
            await db.life_places.update_one({"id": home.id}, {"$set": {"updated_at": "synthetic-new-version"}})
        return forecast()

    read.side_effect = read_then_change
    out = await providers.read_weather(db, OWNER, goal,
                                      step=SimpleNamespace(input_refs=[f"place:{home.id}"]))
    assert out.status == "unavailable" and out.error_type == "situation_source_changed"
    assert out.claims == [] and out.provenance.weather_valid_until is None
    read.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_place_mismatch_is_not_accepted_as_the_situation_weather(monkeypatch):
    data = forecast()
    data["place"] = "Different synthetic locality"
    db, goal, home, _, moved = await setup(monkeypatch, data)
    out = await providers.read_weather(db, OWNER, goal,
                                      step=SimpleNamespace(input_refs=[f"place:{home.id}"]))
    assert out.status == "unavailable" and out.error_type == "weather_place_mismatch"
    assert out.claims == [] and out.provenance.weather_valid_until is None
    moved.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_timestamp_without_environmental_data_is_not_useful_weather(monkeypatch):
    data = {key: value for key, value in forecast().items() if key in (
        "available", "provider", "place", "observed_at", "retrieved_at", "timezone", "utc_offset_seconds",
    )}
    db, goal, home, _, _ = await setup(monkeypatch, data)
    out = await providers.read_weather(db, OWNER, goal,
                                      step=SimpleNamespace(input_refs=[f"place:{home.id}"]))
    assert out.status == "partial" and out.error_type == "weather_insufficient"
    assert out.provenance.weather_valid_until is None
