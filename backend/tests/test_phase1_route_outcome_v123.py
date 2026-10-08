"""Phase 1: a route provider's unsuccessful read must not satisfy an ETA skill.

The route capability and cognitive outcome classifier are real. Only the
stored places, current location and external route provider are mocked.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import datetime, timezone

import pytest

from conversation_engine.ai_core.loop import (
    _required_skill_plan_satisfied,
    _skill_outcome_class,
    _skill_outcome_summary,
)
from places import caps
from places import routing


def _resolved():
    return SimpleNamespace(
        resolved=True,
        place=SimpleNamespace(
            label="Biblioteca",
            coordinates=SimpleNamespace(
                precise=lambda: {"latitude": 42.4, "longitude": 11.8},
            ),
        ),
        candidates=[],
        reason=None,
    )


def _mock_places(monkeypatch, resolution):
    class Places:
        async def resolve_destination(self, uid, text):
            assert uid == "owner"
            return resolution

    monkeypatch.setattr(caps, "_service", lambda runtime: Places())


def _mock_presence(monkeypatch, presence):
    import location.service as location_service

    class Location:
        def __init__(self, db):
            self.db = db

        async def build_presence(self, uid, **kwargs):
            assert uid == "owner"
            return presence

    monkeypatch.setattr(location_service, "LocationService", Location)


def _plan_state(obs):
    return _skill_outcome_summary("get_route", obs)


@pytest.mark.asyncio
async def test_ambiguous_destination_is_an_observed_failure_not_a_verified_route(
    monkeypatch,
):
    candidate = SimpleNamespace(for_ai=lambda: {"label": "Biblioteca centrale"})
    _mock_places(monkeypatch, SimpleNamespace(
        resolved=False, place=None, reason="destinazione ambigua",
        candidates=[candidate],
    ))

    obs = await caps.get_route(
        {"destination": "biblioteca"}, {"user_id": "owner", "db": object()},
    )
    assert obs.status == "ok"  # The adapter responded; no ETA was produced.
    assert obs.payload["status"] == "unavailable"
    assert obs.payload["available"] is False
    assert obs.payload["options"] == [{"label": "Biblioteca centrale"}]
    meta = _plan_state(obs)
    assert meta["result_status"] == "unavailable"
    assert _skill_outcome_class(meta) == "failed"
    assert not _required_skill_plan_satisfied(["get_route"], [meta])


@pytest.mark.asyncio
async def test_missing_origin_requires_client_position_not_route_success(
    monkeypatch,
):
    _mock_places(monkeypatch, _resolved())
    _mock_presence(monkeypatch, None)
    monkeypatch.setattr(routing, "capabilities", lambda: {
        "available": True, "provider": "google_routes",
        "why_unavailable": None,
    })

    obs = await caps.get_route(
        {"destination": "biblioteca"}, {"user_id": "owner", "db": object()},
    )
    assert obs.status == "needs_client"
    assert obs.payload["status"] == "unavailable"
    assert obs.payload["available"] is False
    assert obs.payload["why_unavailable"] == "non so dove si trova adesso"
    assert _skill_outcome_class(_plan_state(obs)) == "waiting"
    assert not _required_skill_plan_satisfied(["get_route"], [_plan_state(obs)])


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_response,expected", [
    ({"available": False, "provider": "google_routes", "why_unavailable": "il servizio ha risposto 503"}, "failed"),
    ({"available": True, "provider": "google_routes", "duration_seconds": None}, "failed"),
    ({"available": True, "provider": "google_routes", "duration_seconds": float("nan")}, "failed"),
    ({"available": True, "provider": "google_routes", "duration_seconds": 920, "distance_meters": 8000}, "succeeded"),
    ({"available": True, "provider": "google_routes", "duration_seconds": 0, "distance_meters": 0}, "succeeded"),
])
async def test_route_result_requires_a_real_finite_provider_eta(
    monkeypatch, provider_response, expected,
):
    _mock_places(monkeypatch, _resolved())
    _mock_presence(monkeypatch, SimpleNamespace(
        latitude=42.2, longitude=11.6,
        freshness="CURRENT", preference="while_using",
        permission_state="granted_foreground", source="foreground_device",
        acquisition_error=None, last_seen_at=datetime.now(timezone.utc).isoformat(),
    ))
    provider = AsyncMock(return_value=dict(provider_response))
    monkeypatch.setattr(routing, "get_route", provider)
    obs = await caps.get_route(
        {"destination": "biblioteca", "travel_mode": "drive"},
        {"user_id": "owner", "db": object()},
    )
    provider.assert_awaited_once()
    assert obs.status == "ok"
    assert obs.payload["available"] is (expected == "succeeded")
    assert obs.payload["status"] == (
        "ok" if expected == "succeeded" else "unavailable"
    )
    if expected == "failed":
        assert obs.payload["why_unavailable"]
    else:
        assert obs.payload["duration_seconds"] == provider_response["duration_seconds"]
    meta = _plan_state(obs)
    assert _skill_outcome_class(meta) == expected
    assert _required_skill_plan_satisfied(["get_route"], [meta]) is (
        expected == "succeeded"
    )
