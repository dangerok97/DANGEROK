from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import providers
from agent.models import AutonomousGoal
from location.service import LocationService, runtime_location_capabilities


def _goal():
    return AutonomousGoal(
        owner_id="alice",
        status="active",
        objective="Capire dove sono",
        desired_outcome="Avere contesto di luogo aggiornato",
    )


def test_native_runtime_reports_real_support_and_separate_background_consent():
    ios_off = runtime_location_capabilities(
        preference="while_using", platform="ios", background_enabled=False
    )
    assert ios_off["native_location"] == "available"
    assert ios_off["foreground_location"] == "available"
    assert ios_off["background_location"] == "requires_consent"
    assert ios_off["presence_history"] == "limited"

    ios_on = runtime_location_capabilities(
        preference="while_using", platform="ios", background_enabled=True
    )
    assert ios_on["background_location"] == "available"
    assert ios_on["presence_history"] == "available"

    web = runtime_location_capabilities(
        preference="while_using", platform="web", background_enabled=True
    )
    assert web["native_location"] == "unsupported"
    assert web["background_location"] == "unavailable"


@pytest.mark.asyncio
async def test_background_monitoring_truth_comes_from_device_choice():
    db = AsyncMongoMockClient().test
    await db.users.insert_one({
        "user_id": "alice",
        "settings": {"location_mode": "while_using"},
        "preferences": {"place_monitoring_enabled": True},
    })

    svc = LocationService(db)
    assert await svc.background_monitoring_enabled("alice") is True

    await db.users.update_one(
        {"user_id": "alice"},
        {"$set": {"preferences.place_monitoring_enabled": False}},
    )
    assert await svc.background_monitoring_enabled("alice") is False


@pytest.mark.asyncio
async def test_native_current_location_no_longer_claims_native_is_unsupported():
    db = AsyncMongoMockClient().test
    await db.users.insert_one({
        "user_id": "alice",
        "settings": {"location_mode": "while_using"},
        "preferences": {"place_monitoring_enabled": False},
    })

    out = await LocationService(db).capability_get_current_location(
        "alice", platform="ios"
    )

    assert out["status"] == "needs_client"
    assert out.get("error") == "no_signal"
    assert out["runtime_capabilities"]["native_location"] == "available"
    assert out["runtime_capabilities"]["background_location"] == "requires_consent"
    assert out["client_action"]["type"] == "request_foreground_location"


@pytest.mark.asyncio
async def test_agent_uses_background_place_presence_without_coordinates(monkeypatch):
    from places.service import PlacesService

    db = AsyncMongoMockClient().test
    await db.users.insert_one({
        "user_id": "alice",
        "settings": {"location_mode": "while_using"},
        "preferences": {"place_monitoring_enabled": True},
    })
    seen = datetime.now(timezone.utc).isoformat()
    where = AsyncMock(return_value={
        "at_a_known_place": True,
        "place": "Casa",
        "place_id": "place_home",
        "since": seen,
        "last_seen_at": seen,
        "seconds_here": 600,
    })
    monkeypatch.setattr(PlacesService, "where_now", where)

    outcome = await providers.read_location(db, "alice", _goal())

    assert outcome.status == "succeeded"
    assert outcome.provenance.provider == "native_place_presence"
    assert outcome.provenance.freshness == "fresh"
    assert outcome.provenance.source_refs == ["place:place_home"]
    surface = " ".join([
        outcome.observation,
        *[claim.text for claim in outcome.claims],
        outcome.data_ref,
    ])
    assert "Casa" in surface
    assert "latitude" not in surface.lower()
    assert "longitude" not in surface.lower()
    assert "42." not in surface
    where.assert_awaited_once_with("alice")
