from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import providers
from agent.capabilities import CapabilityResolver
from agent.execution import StepExecutor
from agent.models import ActionStep, AutonomousGoal


OWNER = "alice"


def _goal():
    return AutonomousGoal(
        id="goal_weather",
        owner_id=OWNER,
        status="active",
        objective="Seguire una situazione il cui esito dipende dalle prossime ore",
        desired_outcome="Rivalutare usando condizioni meteo reali",
    )


@pytest.mark.asyncio
async def test_weather_capability_is_real_only_with_location_consent(monkeypatch):
    import weather as meteo

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(
        meteo,
        "capabilities",
        lambda: {
            "available": True,
            "provider": "open_meteo",
            "why_unavailable": None,
        },
    )

    denied = await CapabilityResolver(db).resolve(OWNER, "weather.read")
    assert denied.known is True
    assert denied.permitted is False
    assert denied.usable is False
    assert denied.status == "requires_connection"
    assert denied.reason == "location_not_permitted"

    await db.users.insert_one({
        "user_id": OWNER,
        "settings": {"location_mode": "while_using"},
    })
    allowed = await CapabilityResolver(db).resolve(OWNER, "weather.read")
    assert allowed.permitted is True
    assert allowed.executable is True
    assert allowed.status == "available_real"
    assert allowed.usable is True


@pytest.mark.asyncio
async def test_weather_read_uses_real_forecast_but_persists_no_coordinates(monkeypatch):
    import weather as meteo
    from home.service import HomeService

    db = AsyncMongoMockClient().test
    await db.users.insert_one({
        "user_id": OWNER,
        "settings": {"location_mode": "while_using"},
    })

    monkeypatch.setattr(
        meteo,
        "capabilities",
        lambda: {
            "available": True,
            "provider": "open_meteo",
            "why_unavailable": None,
        },
    )
    where = AsyncMock(return_value=(42.2501, 11.7562, "Tarquinia"))
    monkeypatch.setattr(HomeService, "_where_they_are", where)
    forecast = AsyncMock(return_value={
        "available": True,
        "place": "Tarquinia",
        "condition_label": "Poco nuvoloso",
        "temperature_c": 22,
        "humidity_pct": 61,
        "wind_kmh": 14,
        "precipitation_mm": 0,
        "hours": [
            {"time": "11:00", "temperature_c": 22, "rain_chance_pct": 5},
            {"time": "12:00", "temperature_c": 23, "rain_chance_pct": 10},
            {"time": "13:00", "temperature_c": 24, "rain_chance_pct": 15},
        ],
        "days": [
            {"label": "Oggi", "min_c": 16, "max_c": 24, "rain_chance_pct": 15},
        ],
    })
    monkeypatch.setattr(meteo, "forecast_at", forecast)

    outcome = await providers.read_weather(db, OWNER, _goal())

    assert outcome.status == "succeeded"
    assert outcome.provenance.provider == "open_meteo"
    assert outcome.data_ref == "weather:forecast"
    assert any("umidità 61%" in c.text for c in outcome.claims)
    assert any("pioggia max 15%" in c.text for c in outcome.claims)
    surface = " ".join([
        outcome.observation,
        *[c.text for c in outcome.claims],
        outcome.data_ref,
        str(outcome.provenance.model_dump()),
    ])
    assert "42.2501" not in surface
    assert "11.7562" not in surface
    assert "latitude" not in surface.lower()
    assert "longitude" not in surface.lower()
    where.assert_awaited_once_with(OWNER)
    forecast.assert_awaited_once_with(
        lat=42.2501, lon=11.7562, place="Tarquinia"
    )


@pytest.mark.asyncio
async def test_agent_executor_can_use_weather_as_real_read(monkeypatch):
    import weather as meteo
    from home.service import HomeService

    db = AsyncMongoMockClient().test
    await db.users.insert_one({
        "user_id": OWNER,
        "settings": {"location_mode": "while_using"},
    })
    monkeypatch.setattr(
        meteo,
        "capabilities",
        lambda: {
            "available": True,
            "provider": "open_meteo",
            "why_unavailable": None,
        },
    )
    monkeypatch.setattr(
        HomeService,
        "_where_they_are",
        AsyncMock(return_value=(42.25, 11.75, "Tarquinia")),
    )
    monkeypatch.setattr(
        meteo,
        "forecast_at",
        AsyncMock(return_value={
            "available": True,
            "condition_label": "Sereno",
            "temperature_c": 23,
            "humidity_pct": 55,
            "wind_kmh": 12,
            "precipitation_mm": 0,
            "hours": [
                {"time": "11:00", "temperature_c": 23, "rain_chance_pct": 0}
            ],
            "days": [],
        }),
    )

    step = ActionStep(
        id="weather_step",
        ordinal=0,
        intent="Verificare le condizioni meteo che possono cambiare l'esito",
        step_type="inspect",
        capability_needed="weather.read",
        expected_result="Avere condizioni e previsione reale delle prossime ore",
    )
    result = await StepExecutor(db).run(
        OWNER, _goal(), step, may_touch_the_world=False
    )

    assert result.status == "succeeded"
    assert result.data_ref == "weather:forecast"
    saved = await db.agent_evidence.find(
        {"owner_id": OWNER, "goal_id": "goal_weather"}, {"_id": 0}
    ).to_list(20)
    assert saved
    blob = str(saved)
    assert "Sereno" in blob
    assert "42.25" not in blob
    assert "11.75" not in blob
