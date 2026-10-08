"""The AI route skill must use a current, authorized device origin.

The real capability and the shared location bridge run here. Only the
location service and the external route response are controlled.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from conversation_engine.ai_core.loop import _skill_outcome_class, _skill_outcome_summary
from places import caps, routing


def _presence(**changes):
    values = dict(
        freshness="CURRENT", latitude=41.9028, longitude=12.4964,
        source="foreground_device", acquisition_error=None,
        last_seen_at=datetime.now(timezone.utc).isoformat(),
        preference="while_using", permission_state="granted_foreground",
    )
    values.update(changes)
    return SimpleNamespace(**values)


def _setup(monkeypatch, presence, location_result):
    resolution = SimpleNamespace(
        resolved=True, candidates=[], reason=None,
        place=SimpleNamespace(
            label="Museo di prova",
            coordinates=SimpleNamespace(
                precise=lambda: {"latitude": 41.8902, "longitude": 12.4922},
            ),
        ),
    )
    monkeypatch.setattr(caps, "_service", lambda runtime: SimpleNamespace(
        resolve_destination=AsyncMock(return_value=resolution),
    ))
    refresh = AsyncMock(return_value=location_result)
    location = SimpleNamespace(
        build_presence=AsyncMock(return_value=presence),
        capability_get_current_location=refresh,
    )
    monkeypatch.setattr("location.service.LocationService", lambda db: location)
    provider = AsyncMock(return_value={
        "available": True, "provider": "google_routes",
        "duration_seconds": 900, "distance_meters": 4000,
        "reflects_current_traffic": True,
    })
    monkeypatch.setattr(routing, "get_route", provider)
    monkeypatch.setattr(routing, "capabilities", lambda: {
        "available": True, "provider": "google_routes",
    })
    return provider, refresh


@pytest.mark.asyncio
@pytest.mark.parametrize("freshness,age", [("STALE", 3600), ("RECENT", 600), ("CURRENT", 240)])
async def test_outdated_origin_requests_refresh_without_contacting_routing(
    monkeypatch, freshness, age,
):
    presence = _presence(
        freshness=freshness,
        last_seen_at=(datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(),
    )
    location = {"status": "ok", "freshness": freshness}
    if freshness == "STALE":
        location = {
            "status": "needs_client", "freshness": freshness,
            "client_action": {"type": "request_foreground_location", "refresh": True},
        }
    provider, refresh = _setup(monkeypatch, presence, location)
    obs = await caps.get_route(
        {"destination": "Museo di prova"},
        {"db": object(), "user_id": "synthetic-route-owner", "session_id": "test-session"},
    )
    provider.assert_not_awaited()
    refresh.assert_awaited_once()
    assert obs.status == "needs_client"
    assert obs.payload["available"] is False
    assert obs.payload["client_action"]["type"] == "request_foreground_location"
    assert obs.payload["destination"] == "Museo di prova"
    assert not obs.payload.get("duration_seconds")
    assert _skill_outcome_class(_skill_outcome_summary("get_route", obs)) == "waiting"


@pytest.mark.asyncio
@pytest.mark.parametrize("changes,location", [
    ({"preference": "off"}, {"status": "consent_required", "client_action": {"type": "request_location_permission"}}),
    ({"permission_state": "denied"}, {"status": "denied"}),
    ({"permission_state": "unavailable"}, {"status": "unavailable"}),
    ({"source": "user_stated"}, {"status": "unavailable"}),
    ({"acquisition_error": "timeout"}, {"status": "timeout"}),
])
async def test_coordinates_never_override_consent_or_device_failure(monkeypatch, changes, location):
    provider, _ = _setup(monkeypatch, _presence(**changes), location)
    obs = await caps.get_route(
        {"destination": "Museo di prova"},
        {"db": object(), "user_id": "synthetic-route-owner"},
    )
    provider.assert_not_awaited()
    assert obs.payload["available"] is False
    assert _skill_outcome_class(_skill_outcome_summary("get_route", obs)) != "succeeded"
    if changes.get("preference") == "off":
        assert obs.payload["client_action"]["type"] == "request_location_permission"


@pytest.mark.asyncio
async def test_fresh_authorized_origin_reaches_provider_without_client_request(monkeypatch):
    provider, refresh = _setup(monkeypatch, _presence(), {})
    obs = await caps.get_route(
        {"destination": "Museo di prova", "travel_mode": "drive"},
        {"db": object(), "user_id": "synthetic-route-owner"},
    )
    refresh.assert_not_awaited()
    provider.assert_awaited_once_with(
        origin={"latitude": 41.9028, "longitude": 12.4964},
        destination={"latitude": 41.8902, "longitude": 12.4922}, travel_mode="drive",
    )
    assert obs.payload["available"] is True
    assert _skill_outcome_class(_skill_outcome_summary("get_route", obs)) == "succeeded"
