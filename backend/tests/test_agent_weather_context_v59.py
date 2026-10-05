from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.capabilities import CapabilityResolver
from agent.execution import StepExecutor
from agent.models import ActionStep, AutonomousGoal


OWNER = "alice"


@pytest.mark.asyncio
async def test_weather_read_is_real_bounded_agent_evidence(monkeypatch):
    import weather
    from home.service import HomeService

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(
        HomeService,
        "_where_they_are",
        AsyncMock(return_value=(42.25, 11.76, "Tarquinia")),
    )
    forecast = AsyncMock(return_value={
        "available": True,
        "place": "Tarquinia",
        "condition_label": "Poco nuvoloso",
        "temperature_c": 22,
        "humidity_pct": 61,
        "wind_kmh": 14,
        "precipitation_mm": 0,
        "hours": [
            {"time": "11:00", "temperature_c": 22, "rain_chance_pct": 10},
            {"time": "12:00", "temperature_c": 23, "rain_chance_pct": 20},
            {"time": "13:00", "temperature_c": 24, "rain_chance_pct": 35},
        ],
        "days": [
            {"label": "Oggi", "condition_label": "Poco nuvoloso", "min_c": 17, "max_c": 24, "rain_chance_pct": 35},
            {"label": "Domani", "condition_label": "Pioggia", "min_c": 15, "max_c": 20, "rain_chance_pct": 70},
        ],
    })
    monkeypatch.setattr(weather, "forecast_at", forecast)

    resolution = await CapabilityResolver(db).resolve(OWNER, "weather.read")
    assert resolution.status == "available_real"
    assert resolution.writes is False

    goal = AutonomousGoal(
        id="goal_weather", owner_id=OWNER, status="active",
        objective="Capire come evolve una situazione temporanea all'aperto",
        desired_outcome="Avere condizioni reali utili al prossimo controllo",
    )
    step = ActionStep(
        id="weather_step", ordinal=0, step_type="inspect",
        intent="Leggere il meteo del posto corrente",
        capability_needed="weather.read",
        expected_result="Condizioni meteo attuali e prossime ore",
    )

    result = await StepExecutor(db).run(
        OWNER, goal, step, may_touch_the_world=False
    )

    assert result.status == "succeeded"
    assert result.provenance.source_class == "external_research"
    assert result.provenance.capability == "weather.read"
    assert result.provenance.is_real is True
    assert result.data_ref == "weather:forecast"
    forecast.assert_awaited_once_with(lat=42.25, lon=11.76, place="Tarquinia")

    evidence = await db.agent_evidence.find(
        {"owner_id": OWNER, "goal_id": goal.id}, {"_id": 0}
    ).to_list(20)
    serialized = str(evidence)
    assert "umidità 61%" in serialized
    assert "probabilità massima di pioggia" in serialized
    assert "42.25" not in serialized and "11.76" not in serialized


@pytest.mark.asyncio
async def test_weather_read_fails_closed_without_current_authorized_location(monkeypatch):
    import weather
    from home.service import HomeService

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(HomeService, "_where_they_are", AsyncMock(return_value=None))
    forecast = AsyncMock()
    monkeypatch.setattr(weather, "forecast_at", forecast)

    goal = AutonomousGoal(
        id="goal_weather_none", owner_id=OWNER, status="active",
        objective="Leggere il meteo pertinente", desired_outcome="Dato reale",
    )
    step = ActionStep(
        id="weather_step_none", ordinal=0, step_type="inspect",
        intent="Leggere il meteo corrente", capability_needed="weather.read",
    )
    result = await StepExecutor(db).run(
        OWNER, goal, step, may_touch_the_world=False
    )

    assert result.status == "unavailable"
    assert result.error_type == "location_unavailable"
    forecast.assert_not_awaited()
    assert await db.agent_evidence.count_documents({"owner_id": OWNER}) == 0
