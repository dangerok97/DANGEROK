"""Owner-grounded named-locality weather, no GPS fallback or invented point.

The conversational weather skill previously accepted only saved LifePlaces or
device location, so a named town could become a false clarification blocker.
This tests only a read-only resolution contract with synthetic Google responses.
A forecast is NOT evidence that an object's physical process is complete.
"""
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.tools.weather_caps import get_weather_forecast
from places import lookup
from situations.models import SituationEvent, SituationState
from situations.repository import SituationRepository

OWNER = "synthetic-weather-owner"
OTHER = "synthetic-weather-other"
SID = "sit_synthetic_named_place"


@pytest.fixture
def weather_context(monkeypatch):
    import weather
    from home.service import HomeService

    db = AsyncMongoMockClient().exp_named_weather
    suggestions = AsyncMock(return_value={
        "available": True,
        "suggestions": [
            {"place_id": "provider-place-t", "primary": "Tarquinia",
             "text": "Tarquinia, VT, Italia"},
            {"place_id": "provider-place-street", "primary": "Via Tarquinia",
             "text": "Via Tarquinia, Roma"},
        ],
    })
    resolve = AsyncMock(return_value={
        "available": True,
        "place_id": "provider-place-t",
        "locality": "Tarquinia",
        "address": "Tarquinia VT Italia",
        "latitude": 42.25,
        "longitude": 11.76,
    })
    forecast = AsyncMock(return_value={
        "available": True,
        "place": "Tarquinia",
        "provider": "synthetic-open-meteo",
        "timezone": "Europe/Rome",
        "observed_at": "2026-10-18T13:00:00+02:00",
        "retrieved_at": "2026-10-18T13:01:00+02:00",
        "temperature_c": 22,
        "humidity_pct": 54,
        "wind_kmh": 12,
        "precipitation_mm": 0,
        "hours": [{"time": "14:00", "datetime": "2026-10-18T14:00:00+02:00",
                   "rain_chance_pct": 20}],
    })
    gps = AsyncMock(side_effect=AssertionError(
        "explicit town must not silently be replaced by device GPS"
    ))
    monkeypatch.setattr(lookup, "suggest", suggestions)
    monkeypatch.setattr(lookup, "resolve", resolve)
    monkeypatch.setattr(weather, "forecast_at", forecast)
    monkeypatch.setattr(HomeService, "_where_they_are", gps)
    return db, suggestions, resolve, forecast, gps


@pytest.mark.asyncio
async def test_explicit_town_can_read_real_provider_with_unique_google_place_provenance(
    weather_context,
):
    db, suggest, resolve, forecast, gps = weather_context
    obs = await get_weather_forecast(
        {"place_query": "Tarquinia"},
        {"db": db, "user_id": OWNER,
         "user_message": "Ho steso i panni a Tarquinia. Dimmi se piove."},
    )
    assert obs.status == "ok", obs
    assert obs.payload["place"] == "Tarquinia"
    assert obs.provenance == ["google_place:provider-place-t"]
    suggest.assert_awaited_once_with("Tarquinia")
    resolve.assert_awaited_once_with("provider-place-t")
    forecast.assert_awaited_once_with(lat=42.25, lon=11.76, place="Tarquinia")
    gps.assert_not_awaited()
    assert await db.life_places.count_documents({}) == 0
    assert await db.agent_goals.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "Come va il meteo?",
    "Stendo il bucato a Tarquiniale.",
    "Ho steso il bucato a Roma.",
    "La località è nel messaggio precedente, oggi non la nomino.",
])
async def test_model_cannot_invent_location_or_match_substrings(
    weather_context, message,
):
    db, suggest, resolve, forecast, gps = weather_context
    obs = await get_weather_forecast(
        {"place_query": "Tarquinia"},
        {"db": db, "user_id": OWNER, "user_message": message},
    )
    assert obs.status == "partial"
    assert obs.payload["failure_code"] == "PLACE_QUERY_NOT_USER_GROUNDED"
    suggest.assert_not_awaited()
    resolve.assert_not_awaited()
    forecast.assert_not_awaited()
    gps.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_owned_active_situation_supplies_previous_turn_location(
    weather_context,
):
    db, suggest, resolve, forecast, gps = weather_context
    await SituationRepository(db).insert(SituationState(
        id=SID, user_id=OWNER, status="active",
        summary="Oggetto temporaneo all'aperto",
        location_label="Tarquinia",
        history=[
            SituationEvent(
                revision=1, operation="create", source="user_conversation",
                changes={"location_label": "Tarquinia"},
            ),
        ],
    ))
    args = {"place_query": "Tarquinia", "situation_id": SID}
    current = {"db": db, "user_id": OWNER,
               "user_message": "Ora controlla di nuovo le condizioni."}
    obs = await get_weather_forecast(args, current)
    assert obs.status == "ok"
    assert obs.provenance == ["google_place:provider-place-t"]
    forecast.assert_awaited_once()
    gps.assert_not_awaited()

    forecast.reset_mock()
    suggest.reset_mock()
    resolve.reset_mock()
    foreign = await get_weather_forecast(args, {**current, "user_id": OTHER})
    assert foreign.status == "partial"
    assert foreign.payload["failure_code"] == "PLACE_QUERY_NOT_USER_GROUNDED"
    forecast.assert_not_awaited()
    resolve.assert_not_awaited()
    suggest.assert_not_awaited()


@pytest.mark.asyncio
async def test_inferred_location_is_not_authority_to_request_geocoding(
    weather_context,
):
    db, suggest, resolve, forecast, gps = weather_context
    await SituationRepository(db).insert(SituationState(
        id=SID, user_id=OWNER, status="active",
        summary="Situazione con luogo solo inferito",
        location_label="Tarquinia",
        history=[
            SituationEvent(
                revision=1, operation="create", source="inferred",
                changes={"location_label": "Tarquinia"},
            ),
        ],
    ))
    obs = await get_weather_forecast(
        {"place_query": "Tarquinia", "situation_id": SID},
        {"db": db, "user_id": OWNER,
         "user_message": "Come evolve la situazione?"},
    )
    assert obs.status == "partial"
    assert obs.payload["failure_code"] == "PLACE_QUERY_NOT_USER_GROUNDED"
    suggest.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_and_changed_geocoding_never_read_wrong_weather(
    weather_context,
):
    db, suggest, resolve, forecast, gps = weather_context
    suggest.return_value = {
        "available": True,
        "suggestions": [
            {"place_id": "a", "primary": "Tarquinia"},
            {"place_id": "b", "primary": "Tarquinia"},
        ],
    }
    ctx = {"db": db, "user_id": OWNER, "user_message": "Sono a Tarquinia"}
    out = await get_weather_forecast({"place_query": "Tarquinia"}, ctx)
    assert out.status == "partial"
    assert out.payload["failure_code"] == "PLACE_QUERY_AMBIGUOUS"
    resolve.assert_not_awaited()
    forecast.assert_not_awaited()

    suggest.return_value = {
        "available": True,
        "suggestions": [{"place_id": "a", "primary": "Tarquinia"}],
    }
    resolve.return_value = {
        "available": True, "place_id": "different",
        "locality": "Tarquinia", "latitude": 42.25, "longitude": 11.76,
    }
    out = await get_weather_forecast({"place_query": "Tarquinia"}, ctx)
    assert out.status == "partial"
    assert out.payload["failure_code"] == "PLACE_QUERY_MISMATCH"
    forecast.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_silent_switch_from_exact_saved_ref_to_city_or_device(
    weather_context,
):
    db, suggest, resolve, forecast, gps = weather_context
    obs = await get_weather_forecast(
        {"place_query": "Tarquinia", "place_ref": "place:someone-else"},
        {"db": db, "user_id": OWNER, "user_message": "Tarquinia"},
    )
    assert obs.status == "error"
    assert obs.payload["error"] == "AMBIGUOUS_PLACE_INPUT"
    suggest.assert_not_awaited()
    resolve.assert_not_awaited()
    forecast.assert_not_awaited()
    gps.assert_not_awaited()
