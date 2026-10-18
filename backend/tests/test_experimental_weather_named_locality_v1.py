"""Read-only, source-grounded local weather for any user-named town.

Mocks Google Places and the weather provider. Never touches a real location,
account, device position, model, API key, billing or notification.
"""
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.tools.weather_caps import get_weather_forecast
from places import lookup
import weather
from situations.models import SituationEvent, SituationState
from situations.repository import SituationRepository


def sources(monkeypatch, *, candidates=None, resolved=None):
    suggestions = AsyncMock(return_value={
        "available": True,
        "suggestions": candidates if candidates is not None else [
            {"place_id": "synthetic-town-one", "primary": "Tarquinia",
             "text": "Tarquinia, provincia di Viterbo"}
        ],
    })
    detail = AsyncMock(return_value=resolved if resolved is not None else {
        "available": True,
        "place_id": "synthetic-town-one",
        "locality": "Tarquinia",
        "address": "Tarquinia, provincia di Viterbo",
        "latitude": 42.254, "longitude": 11.758,
    })
    forecast = AsyncMock(return_value={
        "available": True,
        "place": "Tarquinia",
        "provider": "synthetic-weather-provider",
        "retrieved_at": "2026-10-18T12:00:00Z",
        "observed_at": "2026-10-18T11:50:00Z",
        "timezone": "Europe/Rome",
        "temperature_c": 19, "humidity_pct": 53,
        "wind_kmh": 11, "precipitation_mm": 0,
        "hours": [],
    })
    monkeypatch.setattr(lookup, "suggest", suggestions)
    monkeypatch.setattr(lookup, "resolve", detail)
    monkeypatch.setattr(weather, "forecast_at", forecast)
    return suggestions, detail, forecast


@pytest.mark.asyncio
async def test_user_named_locality_uses_unique_verified_place_not_gps(monkeypatch):
    suggest, resolve, forecast = sources(monkeypatch)
    result = await get_weather_forecast(
        {"place_query": "Tarquinia"},
        {"user_id": "synthetic-owner", "db": object(),
         "user_message": "Ho steso i panni a Tarquinia, controlla il meteo."},
    )
    assert result.status == "ok", result.payload
    assert result.payload["place"] == "Tarquinia"
    assert result.payload["provider"] == "synthetic-weather-provider"
    assert result.provenance == ["google_place:synthetic-town-one"]
    suggest.assert_awaited_once_with("Tarquinia")
    resolve.assert_awaited_once_with("synthetic-town-one")
    forecast.assert_awaited_once_with(
        lat=42.254, lon=11.758, place="Tarquinia",
    )
    assert "asciutti" not in str(result.payload).lower(), (
        "Weather facts alone cannot establish that any physical item dried."
    )


@pytest.mark.asyncio
async def test_model_invented_town_is_rejected_without_egress(monkeypatch):
    suggest, resolve, forecast = sources(monkeypatch)
    result = await get_weather_forecast(
        {"place_query": "Tarquinia"},
        {"user_id": "synthetic-owner", "db": object(),
         "user_message": "Ho steso i panni a Milano."},
    )
    assert result.status == "partial"
    assert result.payload["failure_code"] == "PLACE_QUERY_NOT_USER_GROUNDED"
    suggest.assert_not_awaited()
    resolve.assert_not_awaited()
    forecast.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_locality_never_selects_first_hit(monkeypatch):
    suggest, resolve, forecast = sources(monkeypatch, candidates=[
        {"place_id": "synthetic-a", "primary": "San Giorgio"},
        {"place_id": "synthetic-b", "primary": "San Giorgio"},
    ])
    result = await get_weather_forecast(
        {"place_query": "San Giorgio"},
        {"user_id": "synthetic-owner", "db": object(),
         "user_message": "Sono a San Giorgio."},
    )
    assert result.status == "partial"
    assert result.payload["failure_code"] == "PLACE_QUERY_AMBIGUOUS"
    suggest.assert_awaited_once()
    resolve.assert_not_awaited()
    forecast.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_locality_mismatch_stays_unverified(monkeypatch):
    _, resolve, forecast = sources(monkeypatch, resolved={
        "available": True, "place_id": "synthetic-town-one",
        "locality": "Milano", "address": "Milano, Italia",
        "latitude": 45.46, "longitude": 9.19,
    })
    result = await get_weather_forecast(
        {"place_query": "Tarquinia"},
        {"user_id": "synthetic-owner", "db": object(),
         "user_message": "I panni sono stesi a Tarquinia."},
    )
    assert result.status == "partial"
    assert result.payload["failure_code"] == "PLACE_QUERY_MISMATCH"
    resolve.assert_awaited_once()
    forecast.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_active_owned_user_recorded_situation_can_reuse_locality(monkeypatch):
    suggest, resolve, forecast = sources(monkeypatch)
    db = AsyncMongoMockClient().experiment_weather_named_locality
    sid = "sit_synthetic_place"
    await SituationRepository(db).insert(SituationState(
        id=sid, user_id="owner-a", summary="Synthetic clothes outside",
        location_label="Tarquinia",
        history=[SituationEvent(
            revision=1, operation="create", source="user_conversation",
            changes={"location_label": "Tarquinia"}
        )],
    ))
    args = {"place_query": "Tarquinia", "situation_id": sid}
    no = await get_weather_forecast(
        args, {"user_id": "owner-b", "db": db,
               "user_message": "Ricontrolla la situazione"},
    )
    assert no.status == "partial"
    assert no.payload["failure_code"] == "PLACE_QUERY_SITUATION_NOT_CURRENT"
    suggest.assert_not_awaited()
    yes = await get_weather_forecast(
        args, {"user_id": "owner-a", "db": db,
               "user_message": "Ricontrolla la situazione"},
    )
    assert yes.status == "ok"
    assert len(yes.provenance) == 1
    suggest.assert_awaited_once()
    resolve.assert_awaited_once()
    forecast.assert_awaited_once()


@pytest.mark.asyncio
async def test_dual_conflicting_place_inputs_are_rejected(monkeypatch):
    suggest, resolve, forecast = sources(monkeypatch)
    result = await get_weather_forecast(
        {"place_query": "Tarquinia", "place_ref": "place:synthetic-other"},
        {"user_id": "owner-a", "db": object(), "user_message": "Tarquinia"},
    )
    assert result.status == "error"
    assert result.payload["error"] == "AMBIGUOUS_PLACE_INPUT"
    suggest.assert_not_awaited()
    resolve.assert_not_awaited()
    forecast.assert_not_awaited()
