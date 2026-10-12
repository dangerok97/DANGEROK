"""WhatsApp explicit navigation must produce a usable map link without app GPS.

Google Maps acquires location on the user's device when the user taps.
ORA must not invent a live traffic ETA or treat WhatsApp as an Expo/browser
foreground geolocation client. Browser/Expo behavior remains unchanged.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

from places import caps, routing
from whatsapp.handoff import render_core_answer_for_whatsapp
from conversation_engine.ai_core import loop


class PublicPlaces:
    async def resolve_destination(self, uid, spoken):
        assert spoken.casefold() == "colosseo"
        return SimpleNamespace(
            resolved=False, place=None,
            reason="nessun luogo personale corrispondente", candidates=[],
        )


@pytest.mark.asyncio
async def test_whatsapp_public_destination_uses_maps_without_acquiring_gps(monkeypatch):
    monkeypatch.setattr(caps, "_service", lambda runtime: PublicPlaces())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    acquire = AsyncMock(side_effect=AssertionError("WhatsApp must not request foreground GPS"))
    preview = AsyncMock(side_effect=AssertionError("No current-origin route preview in WA"))
    monkeypatch.setattr(caps, "_fresh_origin_or_location_bridge", acquire)
    monkeypatch.setattr(caps, "_public_route_preview", preview)

    observed = await caps.open_navigation(
        {"destination": "Colosseo", "mode": "driving"},
        {"user_id": "owner", "db": object(), "platform": "whatsapp"},
    )
    assert observed.payload["ready"] is True
    assert observed.payload["app"] == "google_maps"
    assert observed.payload.get("client_action") is None
    assert observed.payload["route"] is None
    assert observed.payload["has_origin"] is False
    destination = parse_qs(urlparse(observed.payload["url"]).query)
    assert destination["destination"] == ["Colosseo"]
    assert destination["travelmode"] == ["driving"]
    assert "origin" not in destination
    assert "tempo" not in str(observed.payload.get("route") or "").lower()
    acquire.assert_not_awaited()
    preview.assert_not_awaited()

    reply = render_core_answer_for_whatsapp({
        "ora_text": observed.payload["say_this"],
        "navigation": loop._navigation_options([observed.model_dump()]),
        "client_actions": [],
        "session_id": "ces_0123456789abcd",
    })
    assert "Google Maps" in reply
    assert observed.payload["url"] in reply
    assert "/ora/ces_" not in reply


@pytest.mark.asyncio
async def test_navigation_fallback_receives_whatsapp_platform_and_returns_link(monkeypatch):
    monkeypatch.setattr(caps, "_service", lambda runtime: PublicPlaces())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setattr(
        caps, "_fresh_origin_or_location_bridge",
        AsyncMock(side_effect=AssertionError("No app GPS from WhatsApp")),
    )
    observations = []
    copy = await loop._ensure_navigation(
        observations, 0, "Portami al Colosseo", object(), "owner",
        platform="whatsapp",
    )
    links = loop._navigation_options(observations)
    assert "Colosseo" in copy
    assert len(links) == 1
    assert links[0]["label"] == "Google Maps"
    assert "destination=Colosseo" in links[0]["url"]


@pytest.mark.asyncio
async def test_web_navigation_still_waits_for_a_fresh_location(monkeypatch):
    monkeypatch.setattr(caps, "_service", lambda runtime: PublicPlaces())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    bridge = {
        "client_action": {"type": "request_foreground_location", "refresh": True},
        "location_status": "needs_client",
        "location_freshness": "UNKNOWN",
    }
    acquire = AsyncMock(return_value=(None, bridge))
    monkeypatch.setattr(caps, "_fresh_origin_or_location_bridge", acquire)
    observed = await caps.open_navigation(
        {"destination": "Colosseo"},
        {"user_id": "owner", "db": object(), "platform": "web"},
    )
    assert observed.payload["ready"] is False
    assert observed.payload["awaiting_location"] is True
    assert observed.payload["client_action"]["type"] == "request_foreground_location"
    assert observed.payload.get("url") is None
    acquire.assert_awaited_once()


@pytest.mark.asyncio
async def test_whatsapp_saved_place_uses_owner_preference_without_gps(monkeypatch):
    class Saved:
        label = "Ufficio"
        coordinates = SimpleNamespace(latitude=41.9, longitude=12.5)

        def for_ai(self):
            return {"label": self.label}

    class SavedPlaces:
        async def resolve_destination(self, uid, spoken):
            assert uid == "owner"
            return SimpleNamespace(
                resolved=True, place=Saved(), reason="", candidates=[],
            )

    monkeypatch.setattr(caps, "_service", lambda runtime: SavedPlaces())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setattr(
        caps, "_fresh_origin_or_location_bridge",
        AsyncMock(side_effect=AssertionError("WA must not demand GPS")),
    )
    monkeypatch.setattr(caps, "_preferred_app", AsyncMock(return_value="google_maps"))
    observed = await caps.open_navigation(
        {"destination": "Ufficio"}, {"user_id": "owner", "db": object(), "platform": "whatsapp"}
    )
    assert observed.payload["ready"]
    assert observed.payload["app"] == "google_maps"
    assert parse_qs(urlparse(observed.payload["url"]).query)["destination"] == ["41.9,12.5"]
    assert observed.payload["journey_options"] == []
    assert observed.payload["route"] is None
    assert not observed.payload.get("client_action")


@pytest.mark.asyncio
async def test_unresolved_private_place_is_never_silently_mapped(monkeypatch):
    class PrivatePlaces:
        async def resolve_destination(self, uid, spoken):
            return SimpleNamespace(resolved=False, place=None,
                                   reason="nessun luogo personale corrispondente",
                                   candidates=[])

    monkeypatch.setattr(caps, "_service", lambda runtime: PrivatePlaces())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    observed = await caps.open_navigation(
        {"destination": "casa"}, {"user_id": "owner", "db": object(), "platform": "whatsapp"}
    )
    assert observed.payload["ready"] is False
    assert observed.payload.get("url") is None


def test_whatsapp_open_navigation_client_action_renders_maps_not_ora_link():
    link = "https://www.google.com/maps/dir/?api=1&destination=Colosseo"
    rendered = render_core_answer_for_whatsapp({
        "ora_text": "", "session_id": "ces_0123456789abcd",
        "client_actions": [{"type": "open_navigation", "url": link}],
    })
    assert link in rendered
    assert "Ho preparato il collegamento" in rendered
    assert "/ora/ces_0123456789abcd" not in rendered


def test_unknown_device_action_still_requires_authenticated_ora_app():
    rendered = render_core_answer_for_whatsapp({
        "ora_text": "", "session_id": "ces_0123456789abcd",
        "client_actions": [{"type": "request_foreground_location"}],
    })
    assert "/ora/ces_0123456789abcd" in rendered
    assert "www.google.com/maps" not in rendered
