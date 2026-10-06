from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from places.models import Coordinates


OWNER = "alice"


def _runtime(db):
    return {
        "db": db,
        "user_id": OWNER,
        "session_id": "chat-v84",
        "platform": "web",
        "user_message": "portami al Colosseo",
    }


def _presence(*, freshness="STALE", source="foreground_device"):
    return SimpleNamespace(
        freshness=freshness,
        latitude=41.9,
        longitude=12.5,
        acquisition_error=None,
        source=source,
        last_seen_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.mark.asyncio
async def test_public_destination_requests_fresh_foreground_location_before_route(monkeypatch):
    from places import caps, routing
    from places.service import PlacesService
    from location.service import LocationService

    db = AsyncMongoMockClient().test

    monkeypatch.setattr(
        PlacesService,
        "resolve_destination",
        AsyncMock(return_value=SimpleNamespace(
            resolved=False,
            place=None,
            candidates=[],
            reason="non è un luogo Vita salvato",
        )),
    )
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": True, "provider": "mapbox", "live_traffic": True},
    )
    monkeypatch.setattr(
        LocationService,
        "build_presence",
        AsyncMock(return_value=_presence(freshness="STALE")),
    )
    monkeypatch.setattr(
        LocationService,
        "capability_get_current_location",
        AsyncMock(return_value={
            "status": "stale",
            "freshness": "STALE",
            "needs_client": True,
            "client_action": {
                "type": "request_foreground_location",
                "reason": "refresh",
                "refresh": True,
            },
        }),
    )
    preview = AsyncMock()
    monkeypatch.setattr(caps, "_public_route_preview", preview)

    obs = await caps.open_navigation(
        {"destination": "Colosseo", "mode": "driving"},
        _runtime(db),
    )

    assert obs.status == "needs_client"
    assert obs.payload["ready"] is False
    assert obs.payload["needs_current_location"] is True
    assert obs.payload["client_action"]["type"] == "request_foreground_location"
    assert obs.payload["destination"] == "Colosseo"
    assert "posizione corrente" in obs.payload["say_this"].lower()
    preview.assert_not_awaited()
    assert "url" not in obs.payload


@pytest.mark.asyncio
async def test_public_destination_uses_fresh_origin_for_live_preview(monkeypatch):
    from places import caps, routing
    from places.service import PlacesService
    from location.service import LocationService

    db = AsyncMongoMockClient().test

    monkeypatch.setattr(
        PlacesService,
        "resolve_destination",
        AsyncMock(return_value=SimpleNamespace(
            resolved=False,
            place=None,
            candidates=[],
            reason="non è un luogo Vita salvato",
        )),
    )
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": True, "provider": "mapbox", "live_traffic": True},
    )
    current = _presence(freshness="CURRENT")
    monkeypatch.setattr(
        LocationService,
        "build_presence",
        AsyncMock(return_value=current),
    )
    refresh = AsyncMock()
    monkeypatch.setattr(
        LocationService,
        "capability_get_current_location",
        refresh,
    )

    preview = AsyncMock(return_value={
        "label": "Colosseo",
        "context": "Roma, Italia",
        "route": {
            "duration_seconds": 1200,
            "distance_meters": 9000,
            "reflects_current_traffic": True,
            "is_live": True,
        },
        "journey_options": [{
            "mode": "drive",
            "label": "In auto",
            "duration_seconds": 1200,
            "duration_label": "20 min",
            "recommended": True,
            "reflects_current_traffic": True,
        }],
        "road_choices": [],
        "route_weather": [],
        "advice": "Parti ora.",
        "handoff": {
            "needs_choice": False,
            "app": "google_maps",
            "url": "https://www.google.com/maps/dir/?api=1&destination=Colosseo",
            "destination_label": "Colosseo",
        },
    })
    monkeypatch.setattr(caps, "_public_route_preview", preview)

    obs = await caps.open_navigation(
        {"destination": "Colosseo", "mode": "driving"},
        _runtime(db),
    )

    assert obs.payload["ready"] is True
    assert obs.payload["route"]["duration_seconds"] == 1200
    assert obs.payload["journey_options"][0]["duration_label"] == "20 min"
    assert obs.payload["has_origin"] is True
    assert "tempi stimati" in obs.payload["say_this"].lower()
    refresh.assert_not_awaited()
    preview.assert_awaited_once()
    assert preview.await_args.kwargs["origin"] == {
        "latitude": 41.9,
        "longitude": 12.5,
    }


@pytest.mark.asyncio
async def test_saved_destination_also_refreshes_origin_before_live_route(monkeypatch):
    from places import caps, routing
    from places.service import PlacesService
    from location.service import LocationService

    db = AsyncMongoMockClient().test
    place = SimpleNamespace(
        label="Ufficio",
        coordinates=Coordinates(latitude=42.093, longitude=11.793),
        for_ai=lambda: {"label": "Ufficio"},
    )

    monkeypatch.setattr(
        PlacesService,
        "resolve_destination",
        AsyncMock(return_value=SimpleNamespace(
            resolved=True,
            place=place,
            candidates=[],
            reason="",
        )),
    )
    monkeypatch.setattr(routing, "configured_provider", lambda: "google_routes")
    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": True, "provider": "google_routes", "live_traffic": True},
    )
    monkeypatch.setattr(
        LocationService,
        "build_presence",
        AsyncMock(return_value=_presence(freshness="RECENT")),
    )
    monkeypatch.setattr(
        LocationService,
        "capability_get_current_location",
        AsyncMock(return_value={
            "status": "ok",
            "freshness": "RECENT",
            "needs_client": False,
        }),
    )

    obs = await caps.open_navigation(
        {"destination": "Ufficio", "mode": "driving"},
        _runtime(db),
    )

    assert obs.status == "needs_client"
    assert obs.payload["ready"] is False
    assert obs.payload["needs_current_location"] is True
    assert obs.payload["client_action"]["type"] == "request_foreground_location"
    assert obs.payload["client_action"]["refresh"] is True


@pytest.mark.asyncio
async def test_location_denial_falls_back_with_specific_reason_not_combined_guess(monkeypatch):
    from places import caps, routing
    from places.service import PlacesService
    from location.service import LocationService

    db = AsyncMongoMockClient().test

    monkeypatch.setattr(
        PlacesService,
        "resolve_destination",
        AsyncMock(return_value=SimpleNamespace(
            resolved=False,
            place=None,
            candidates=[],
            reason="non è un luogo Vita salvato",
        )),
    )
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setattr(
        routing,
        "capabilities",
        lambda: {"available": True, "provider": "mapbox", "live_traffic": True},
    )
    monkeypatch.setattr(
        LocationService,
        "build_presence",
        AsyncMock(return_value=_presence(freshness="UNKNOWN")),
    )
    monkeypatch.setattr(
        LocationService,
        "capability_get_current_location",
        AsyncMock(return_value={
            "status": "denied",
            "freshness": "UNKNOWN",
            "needs_client": False,
        }),
    )
    monkeypatch.setattr(caps, "_public_route_preview", AsyncMock(return_value=None))

    obs = await caps.open_navigation(
        {"destination": "Colosseo", "mode": "driving"},
        _runtime(db),
    )

    why = obs.payload["routing"]["why_unavailable"]
    assert "permesso" in why.lower()
    assert "destinazione univoca" not in why.lower()
    assert "non posso confrontare i tempi live" in obs.payload["say_this"].lower()
    assert obs.payload["url"].startswith("https://")
