from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _Places:
    async def resolve_destination(self, uid, spoken):
        return SimpleNamespace(
            resolved=False,
            place=None,
            reason="nessun luogo personale corrispondente",
            candidates=[],
        )


@pytest.mark.asyncio
async def test_public_navigation_requests_fresh_location_before_generic_map_fallback(monkeypatch):
    from places import caps, routing

    monkeypatch.setattr(caps, "_service", lambda runtime: _Places())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")

    bridge = {
        "client_action": {
            "type": "request_foreground_location",
            "reason": "Serve posizione corrente.",
            "refresh": True,
        },
        "location_status": "needs_client",
        "location_freshness": "UNKNOWN",
    }
    monkeypatch.setattr(
        caps,
        "_fresh_origin_or_location_bridge",
        AsyncMock(return_value=(None, bridge)),
    )

    preview = AsyncMock()
    monkeypatch.setattr(caps, "_public_route_preview", preview)

    runtime = {
        "user_id": "alice",
        "db": object(),
        "session_id": "chat_1",
        "platform": "web",
    }
    obs = await caps.open_navigation(
        {"destination": "Colosseo", "mode": "driving"},
        runtime,
    )

    assert obs.status == "needs_client"
    assert obs.payload["awaiting_location"] is True
    assert obs.payload["destination"] == "Colosseo"
    assert obs.payload["client_action"]["type"] == "request_foreground_location"
    assert "tempi e traffico" in obs.payload["reason"].lower()
    preview.assert_not_awaited()
    # Most important regression: this turn must not pretend the generic Maps
    # handoff is the finished route when a fresh origin can still be acquired.
    assert not obs.payload.get("url")
    assert not obs.payload.get("options")


@pytest.mark.asyncio
async def test_public_navigation_resumes_with_fresh_origin_and_live_route(monkeypatch):
    from places import caps, routing

    monkeypatch.setattr(caps, "_service", lambda runtime: _Places())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")

    origin = {"latitude": 42.249, "longitude": 11.756}
    monkeypatch.setattr(
        caps,
        "_fresh_origin_or_location_bridge",
        AsyncMock(return_value=(origin, None)),
    )
    preview = AsyncMock(return_value={
        "label": "Colosseo",
        "context": "Roma RM, Italia",
        "route": {
            "duration_seconds": 5100,
            "distance_meters": 92500,
            "reflects_current_traffic": True,
        },
        "journey_options": [{
            "mode": "drive",
            "label": "In auto",
            "duration_seconds": 5100,
            "distance_meters": 92500,
            "reflects_current_traffic": True,
        }],
        "advice": "Parti ora.",
        "road_choices": [],
        "route_weather": [],
        "handoff": {
            "url": "https://www.google.com/maps/dir/?api=1&destination=Colosseo",
            "app": "google_maps",
        },
    })
    monkeypatch.setattr(caps, "_public_route_preview", preview)

    runtime = {
        "user_id": "alice",
        "db": object(),
        "session_id": "chat_1",
        "platform": "web",
    }
    obs = await caps.open_navigation(
        {"destination": "Colosseo", "mode": "driving"},
        runtime,
    )

    assert obs.status == "needs_client"
    assert obs.payload["ready"] is True
    assert obs.payload["has_origin"] is True
    assert obs.payload["route"]["duration_seconds"] == 5100
    assert obs.payload["route"]["reflects_current_traffic"] is True
    assert obs.payload["app"] == "google_maps"
    assert "tempi stimati e il traffico" in obs.payload["say_this"].lower()
    preview.assert_awaited_once_with(
        "Colosseo",
        runtime,
        origin=origin,
        arrival_request=None,
    )
