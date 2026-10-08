"""Saved place identities must reach routing without fuzzy location guesses.

The capability, place service and owner-scoped Mongo reads are real. Only the
already-covered device-origin bridge and external route provider are fixtures.
"""
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import _skill_outcome_class, _skill_outcome_summary
from places import caps, routing
from places.models import Coordinates, LifePlace
from places.service import PlacesService


OWNER = "synthetic-route-reference-owner"
ORIGIN = {"latitude": 41.9010, "longitude": 12.5018}
DESTINATION = {"latitude": 41.8902, "longitude": 12.4922}


async def _world(monkeypatch, *, state="confirmed", has_coordinates=True):
    db = AsyncMongoMockClient().phase1_route_references
    place = LifePlace(
        id="plc_syntheticmuseum", user_id=OWNER, label="Museo centrale",
        locality="Roma", state=state,
        coordinates=Coordinates(**DESTINATION) if has_coordinates else None,
    )
    await PlacesService(db).repo.save_place(place)
    origin = AsyncMock(return_value=(dict(ORIGIN), None))
    monkeypatch.setattr(caps, "_fresh_origin_or_location_bridge", origin)
    provider = AsyncMock(return_value={
        "available": True, "provider": "google_routes",
        "duration_seconds": 900, "distance_meters": 3800,
        "reflects_current_traffic": True,
    })
    monkeypatch.setattr(routing, "get_route", provider)
    return {"user_id": OWNER, "db": db}, place, provider, origin


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["ref", "place_id", "name"])
async def test_actual_route_resolves_the_exact_identity_exposed_in_context(monkeypatch, identity):
    runtime, place, provider, origin = await _world(monkeypatch)
    # Use the actual model-facing projection instead of constructing an alias.
    exposed = place.for_ai()
    observation = await caps.get_route(
        {"destination": exposed[identity], "travel_mode": "drive"}, runtime,
    )
    origin.assert_awaited_once_with(runtime)
    provider.assert_awaited_once_with(
        origin=ORIGIN, destination=DESTINATION, travel_mode="drive",
    )
    assert observation.payload["destination"] == place.label
    assert observation.payload["duration_seconds"] == 900
    assert _skill_outcome_class(_skill_outcome_summary("get_route", observation)) == "succeeded"


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["ref", "place_id"])
async def test_another_owners_place_never_supplies_route_coordinates(monkeypatch, identity):
    runtime, _, provider, origin = await _world(monkeypatch)
    foreign = LifePlace(
        id="plc_other_owner", user_id="synthetic-other-owner", label="Luogo privato altrui",
        coordinates=Coordinates(latitude=42.25, longitude=11.76),
    )
    await PlacesService(runtime["db"]).repo.save_place(foreign)
    observation = await caps.get_route(
        {"destination": foreign.for_ai()[identity]}, runtime,
    )
    provider.assert_not_awaited()
    origin.assert_not_awaited()
    assert observation.payload["available"] is False
    assert foreign.label not in str(observation.payload)
    assert "42.25" not in str(observation.payload)


@pytest.mark.asyncio
async def test_unavailable_canonical_ref_never_falls_back_to_a_matching_label(monkeypatch):
    runtime, place, provider, origin = await _world(monkeypatch)
    unavailable_ref = "place:plc_missing"
    # A label resembling an unavailable identity is a different saved place.
    place.label = unavailable_ref
    await PlacesService(runtime["db"]).repo.save_place(place)
    observation = await caps.get_route({"destination": unavailable_ref}, runtime)
    provider.assert_not_awaited()
    origin.assert_not_awaited()
    assert observation.payload["available"] is False
    assert observation.payload["options"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["candidate", "dismissed", "deleted"])
async def test_ref_does_not_reactivate_an_unconfirmed_or_removed_place(monkeypatch, state):
    runtime, place, provider, origin = await _world(monkeypatch, state=state)
    observation = await caps.get_route({"destination": place.for_ai()["ref"]}, runtime)
    provider.assert_not_awaited()
    origin.assert_not_awaited()
    assert observation.payload["available"] is False
    assert _skill_outcome_class(_skill_outcome_summary("get_route", observation)) == "failed"


@pytest.mark.asyncio
async def test_exact_ref_without_coordinates_is_still_not_a_verified_route(monkeypatch):
    runtime, place, provider, origin = await _world(monkeypatch, has_coordinates=False)
    observation = await caps.get_route({"destination": place.for_ai()["ref"]}, runtime)
    provider.assert_not_awaited()
    origin.assert_not_awaited()
    assert observation.payload["available"] is False


@pytest.mark.asyncio
async def test_appending_a_locality_does_not_invent_an_exact_label_match(monkeypatch):
    runtime, place, provider, origin = await _world(monkeypatch)
    observation = await caps.get_route(
        {"destination": place.label + ", " + place.locality}, runtime,
    )
    provider.assert_not_awaited()
    origin.assert_not_awaited()
    assert observation.payload["available"] is False
    assert observation.payload["options"] == [place.for_ai()]
