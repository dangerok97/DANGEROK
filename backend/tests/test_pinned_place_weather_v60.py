from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.execution import StepExecutor
from agent.models import ActionStep, AutonomousGoal
from places.models import Coordinates
from places.service import PlacesService


OWNER = "alice"


@pytest.mark.asyncio
async def test_weather_followup_stays_on_pinned_place_when_user_moves(monkeypatch):
    import weather
    from home.service import HomeService

    db = AsyncMongoMockClient().test
    home = await PlacesService(db).save_place(
        OWNER,
        label="Casa",
        role="home",
        locality="Tarquinia",
        coordinates=Coordinates(latitude=42.249, longitude=11.756),
        source="user_stated",
        role_confirmed_by_user=True,
    )

    current = AsyncMock(return_value=(41.9028, 12.4964, "Roma"))
    monkeypatch.setattr(HomeService, "_where_they_are", current)
    forecast = AsyncMock(return_value={
        "available": True,
        "place": "Tarquinia",
        "condition_label": "Nuvoloso",
        "temperature_c": 19,
        "humidity_pct": 72,
        "wind_kmh": 8,
        "precipitation_mm": 0,
        "hours": [{"time": "15:00", "temperature_c": 19, "rain_chance_pct": 55}],
        "days": [],
    })
    monkeypatch.setattr(weather, "forecast_at", forecast)

    goal = AutonomousGoal(
        id="goal_pinned_weather", owner_id=OWNER, status="active",
        objective="Seguire una situazione che rimane a Casa",
        desired_outcome="Rivalutare usando il meteo del luogo giusto",
    )
    step = ActionStep(
        id="weather_home", ordinal=0, step_type="inspect",
        intent="Rileggere il meteo del luogo della situazione",
        capability_needed="weather.read", input_refs=[f"place:{home.id}"],
        expected_result="Meteo aggiornato a Casa",
    )

    result = await StepExecutor(db).run(
        OWNER, goal, step, may_touch_the_world=False
    )

    assert result.status == "succeeded"
    current.assert_not_awaited()
    forecast.assert_awaited_once_with(
        lat=42.249, lon=11.756, place="Tarquinia"
    )
    assert result.provenance.source_refs == [f"place:{home.id}"]

    evidence = await db.agent_evidence.find(
        {"owner_id": OWNER, "goal_id": goal.id}, {"_id": 0}
    ).to_list(20)
    blob = str(evidence)
    assert "Tarquinia" in blob
    assert "Roma" not in blob
    assert "42.249" not in blob and "11.756" not in blob


@pytest.mark.asyncio
async def test_weather_pinned_place_is_owner_scoped_and_fails_closed(monkeypatch):
    import weather
    from home.service import HomeService

    db = AsyncMongoMockClient().test
    other = await PlacesService(db).save_place(
        "bob", label="Casa Bob", locality="Milano",
        coordinates=Coordinates(latitude=45.4642, longitude=9.19),
    )
    current = AsyncMock(return_value=(41.9028, 12.4964, "Roma"))
    monkeypatch.setattr(HomeService, "_where_they_are", current)
    forecast = AsyncMock()
    monkeypatch.setattr(weather, "forecast_at", forecast)

    goal = AutonomousGoal(
        id="goal_foreign_place", owner_id=OWNER, status="active",
        objective="Controllare un luogo", desired_outcome="Meteo reale",
    )
    step = ActionStep(
        id="weather_foreign", ordinal=0, step_type="inspect",
        intent="Leggere il meteo", capability_needed="weather.read",
        input_refs=[f"place:{other.id}"],
    )
    result = await StepExecutor(db).run(
        OWNER, goal, step, may_touch_the_world=False
    )

    assert result.status == "unavailable"
    assert result.error_type == "place_unavailable"
    current.assert_not_awaited()
    forecast.assert_not_awaited()


@pytest.mark.asyncio
async def test_planner_contract_pins_weather_to_observed_place(monkeypatch):
    from agent import reasoning

    captured = {}

    async def ask(system, user):
        captured["system"] = system
        captured["user"] = user
        return {
            "plan_summary": "Controllare il luogo e poi il meteo.",
            "expected_outcome": "Condizioni rivalutate.",
            "assumptions": [],
            "known_constraints": [],
            "steps": [{
                "intent": "Leggere il meteo del luogo osservato",
                "step_type": "inspect",
                "capability_needed": "weather.read",
                "input_refs": ["place:home_1"],
                "parameters": {},
                "expected_result": "Previsione aggiornata",
                "external_effect": False,
                "reversibility": "easily",
            }],
        }

    monkeypatch.setattr(reasoning, "_ask_model", ask)
    out = await reasoning.make_plan(
        {"objective": "Seguire una situazione rimasta in un luogo"},
        capabilities=[
            {"capability": "location.read", "status": "available_real"},
            {"capability": "weather.read", "status": "available_real"},
        ],
        context={"today": "2026-10-05", "today_weekday": "lunedì"},
    )

    assert out is not None
    assert "For weather.read" in captured["system"]
    assert "same place even if" in captured["system"]
    assert "weather.read" in captured["user"]
