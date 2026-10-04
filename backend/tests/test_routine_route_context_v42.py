import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from opportunities.snapshot import evidence_refs
from places.models import Coordinates, LifePlace, ObservedRoutine
from places.routine_context import RoutineRouteContextService, ground_candidate
from places.service import PlacesService
import places.routing as routing
import ambient.service as ambient_service


@pytest.mark.asyncio
async def test_routine_route_is_conditional_live_evidence(monkeypatch):
    db = AsyncMongoMockClient().test
    now = datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc)

    routine = ObservedRoutine(
        id="rtn_commute",
        user_id="alice",
        place_sequence=["home", "work"],
        weekdays=["lunedì"],
        typical_start="09:00",
        proactive_review_lead_minutes=30,
        interpretation="Di solito vai da casa al lavoro.",
    )
    await db.observed_routines.insert_one(routine.model_dump())
    await db.users.insert_one({
        "user_id": "alice",
        "preferences": {"place_monitoring_enabled": True},
    })

    home = LifePlace(
        id="home",
        user_id="alice",
        label="Casa",
        coordinates=Coordinates(latitude=42.25, longitude=11.75),
    )
    work = LifePlace(
        id="work",
        user_id="alice",
        label="Lavoro",
        coordinates=Coordinates(latitude=42.10, longitude=11.80),
    )

    monkeypatch.setattr(
        PlacesService,
        "where_now",
        AsyncMock(return_value={"at_a_known_place": True, "place_id": "home"}),
    )

    async def get_place(self, owner_id, place_id):
        return {"home": home, "work": work}.get(place_id)

    monkeypatch.setattr(PlacesService, "get_place", get_place)
    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": True, "modes": ["drive"], "provider": "fake"},
    )
    monkeypatch.setattr(
        routing,
        "get_route",
        AsyncMock(return_value={
            "available": True,
            "provider": "fake",
            "duration_seconds": 1800,
            "distance_meters": 24000,
            "reflects_current_traffic": True,
            "alternatives": [{
                "duration_seconds": 1800,
                "distance_meters": 24000,
                "delay_seconds": 300,
                "polyline": "",
            }],
        }),
    )

    evidence = await RoutineRouteContextService(db).refresh(
        "alice", "rtn_commute", now=now
    )

    assert evidence["status"] == "ready"
    assert evidence["hypothesis_only"] is True
    assert evidence["from_place"] == "Casa"
    assert evidence["to_place"] == "Lavoro"
    assert evidence["options"][0]["duration_minutes"] == 30
    assert evidence["options"][0]["reflects_current_traffic"] is True

    current = await RoutineRouteContextService(db).current("alice", now=now)
    assert [row["ref"] for row in current] == [evidence["ref"]]
    assert evidence_refs({"routine_routes": current})[evidence["ref"]] == "routine_route"


def test_routine_route_grounding_never_claims_the_trip_will_happen():
    candidate = SimpleNamespace()
    ground_candidate(candidate, {
        "routine_ref": "rtn_commute",
        "from_place": "Casa",
        "to_place": "Lavoro",
        "observed_at": "2026-10-05T06:30:00+00:00",
        "valid_until": "2026-10-05T06:35:00+00:00",
        "options": [{"label": "in auto", "duration_minutes": 30}],
    })

    assert candidate.semantic_summary.startswith("Se la routine osservata si ripetesse ora")
    assert "non la previsione" in candidate.why_it_matters
    assert candidate.time_sensitivity == "perishable"


def test_routine_wake_refreshes_route_before_snapshot_review():
    source = inspect.getsource(ambient_service.AmbientService.review_life)
    assert "RoutineRouteContextService" in source
    assert source.index("RoutineRouteContextService") < source.index("discovery.review")
