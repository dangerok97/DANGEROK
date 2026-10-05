from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.capabilities import CapabilityResolver
from agent.execution import StepExecutor
from agent.models import ActionStep, AutonomousGoal
from places.models import Coordinates, LifePlace


OWNER = "alice"


def _goal():
    return AutonomousGoal(
        id="goal_route",
        owner_id=OWNER,
        status="active",
        objective="Preparare uno spostamento con dati reali",
        desired_outcome="Conoscere tempo e traffico pertinenti",
    )


@pytest.mark.asyncio
async def test_route_capability_truth_follows_real_provider(monkeypatch):
    from places import routing

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": False, "provider": None, "live_traffic": False},
    )
    off = await CapabilityResolver(db).resolve(OWNER, "route.read")
    assert off.known is True
    assert off.usable is False
    assert off.status == "unavailable"
    assert off.reason == "routing_provider_unavailable"

    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": True, "provider": "mapbox", "live_traffic": True},
    )
    on = await CapabilityResolver(db).resolve(OWNER, "route.read")
    assert on.permitted is True
    assert on.usable is True
    assert on.status == "available_real"


@pytest.mark.asyncio
async def test_two_owned_places_route_without_current_location_and_persist_no_coords(monkeypatch):
    from home.service import HomeService
    from places import routing

    db = AsyncMongoMockClient().test
    await db.life_places.insert_many([
        LifePlace(
            id="plc_home",
            user_id=OWNER,
            label="Casa",
            locality="Tarquinia",
            coordinates=Coordinates(latitude=42.249, longitude=11.756),
        ).model_dump(),
        LifePlace(
            id="plc_work",
            user_id=OWNER,
            label="Ufficio",
            locality="Civitavecchia",
            coordinates=Coordinates(latitude=42.093, longitude=11.793),
        ).model_dump(),
    ])

    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": True, "provider": "mapbox", "live_traffic": True},
    )
    live = AsyncMock(return_value={
        "available": True,
        "provider": "mapbox",
        "travel_mode": "drive",
        "duration_seconds": 2100,
        "distance_meters": 31200,
        "reflects_current_traffic": True,
        "duration_without_traffic_seconds": 1800,
    })
    monkeypatch.setattr(routing, "get_route", live)
    current = AsyncMock()
    monkeypatch.setattr(HomeService, "_where_they_are", current)

    step = ActionStep(
        id="route_step",
        ordinal=0,
        intent="Controllare il tragitto Casa-Ufficio",
        step_type="inspect",
        capability_needed="route.read",
        input_refs=["place:plc_home", "place:plc_work"],
        parameters={"travel_mode": "drive"},
        expected_result="Tempo e traffico live",
    )
    result = await StepExecutor(db).run(
        OWNER, _goal(), step, may_touch_the_world=False
    )

    assert result.status == "succeeded"
    assert result.data_ref == "route:live"
    assert result.provenance.source_refs == ["place:plc_home", "place:plc_work"]
    assert result.provenance.freshness == "fresh"
    assert "traffico" in result.provenance.certainty_note
    current.assert_not_awaited()
    live.assert_awaited_once_with(
        origin={"latitude": 42.249, "longitude": 11.756},
        destination={"latitude": 42.093, "longitude": 11.793},
        travel_mode="drive",
        alternatives=False,
    )

    evidence = await db.agent_evidence.find(
        {"owner_id": OWNER, "goal_id": "goal_route"}, {"_id": 0}
    ).to_list(20)
    blob = str(evidence)
    assert "Casa" in blob and "Ufficio" in blob
    assert "35 min" in blob
    assert "31.2 km" in blob
    assert "5 min" in blob
    assert "42.249" not in blob
    assert "11.756" not in blob
    assert "42.093" not in blob
    assert "11.793" not in blob


@pytest.mark.asyncio
async def test_one_destination_uses_only_authorized_current_origin(monkeypatch):
    from home.service import HomeService
    from places import routing

    db = AsyncMongoMockClient().test
    await db.life_places.insert_one(
        LifePlace(
            id="plc_work",
            user_id=OWNER,
            label="Ufficio",
            coordinates=Coordinates(latitude=42.093, longitude=11.793),
        ).model_dump()
    )
    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": True, "provider": "google_routes", "live_traffic": True},
    )
    current = AsyncMock(return_value=(42.249, 11.756, "Posizione attuale"))
    monkeypatch.setattr(HomeService, "_where_they_are", current)
    live = AsyncMock(return_value={
        "available": True,
        "provider": "google_routes",
        "duration_seconds": 1800,
        "distance_meters": 30000,
        "reflects_current_traffic": True,
        "duration_without_traffic_seconds": 1700,
    })
    monkeypatch.setattr(routing, "get_route", live)

    step = ActionStep(
        id="route_current",
        ordinal=0,
        intent="Controllare il tragitto fino a Ufficio",
        step_type="inspect",
        capability_needed="route.read",
        input_refs=["place:plc_work"],
        parameters={"travel_mode": "drive"},
    )
    result = await StepExecutor(db).run(
        OWNER, _goal(), step, may_touch_the_world=False
    )

    assert result.status == "succeeded"
    assert result.provenance.source_refs == ["location:presence", "place:plc_work"]
    current.assert_awaited_once_with(OWNER)


@pytest.mark.asyncio
async def test_foreign_destination_fails_closed_before_provider(monkeypatch):
    from places import routing

    db = AsyncMongoMockClient().test
    await db.life_places.insert_one(
        LifePlace(
            id="plc_bob",
            user_id="bob",
            label="Casa Bob",
            coordinates=Coordinates(latitude=45.46, longitude=9.19),
        ).model_dump()
    )
    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": True, "provider": "mapbox", "live_traffic": True},
    )
    live = AsyncMock()
    monkeypatch.setattr(routing, "get_route", live)

    step = ActionStep(
        id="route_foreign",
        ordinal=0,
        intent="Controllare il tragitto",
        step_type="inspect",
        capability_needed="route.read",
        input_refs=["place:plc_bob"],
    )
    result = await StepExecutor(db).run(
        OWNER, _goal(), step, may_touch_the_world=False
    )

    assert result.status == "unavailable"
    assert result.error_type == "place_unavailable"
    live.assert_not_awaited()


def test_planner_contract_for_live_route_is_explicit():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    prompt = (root / "agent" / "reasoning.py").read_text(encoding="utf-8")
    assert "For route.read" in prompt
    assert "[origin, destination]" in prompt
    assert "current/recent authorized device position" in prompt
    assert "pretend traffic was considered" in prompt
