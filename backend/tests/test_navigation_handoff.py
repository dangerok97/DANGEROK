"""An explicit departure reaches an actionable map link without a saved place."""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _loop_harness


def run(coro):
    return _loop_harness.run(coro)


def test_public_destination_handoff(monkeypatch):
    from places import caps
    from places.models import PlaceResolution

    class Service:
        async def resolve_destination(self, uid, spoken):
            assert spoken == "Colosseo"
            return PlaceResolution(reason="non conosco ancora nessun luogo")

    monkeypatch.setattr(caps, "_service", lambda runtime: Service())
    obs = run(caps.open_navigation({"destination": "Colosseo"}, {"db": object(), "user_id": "u"}))
    assert obs.payload["ready"] is True
    assert obs.payload["destination_unverified"] is True
    url = obs.payload["url"]
    parsed = urlparse(url)
    assert parsed.netloc == "www.google.com"
    assert parsed.path == "/maps/dir/"
    assert parse_qs(parsed.query)["destination"] == ["Colosseo"]
    assert parse_qs(parsed.query)["dir_action"] == ["navigate"]
    assert "origin" not in parse_qs(parsed.query)
    assert obs.payload["route"] is None


def test_public_destination_prepares_traffic_without_saving_place(monkeypatch):
    from places import caps, routing, briefing, public_search
    from places.models import PlaceResolution
    from location.service import LocationService

    class Service:
        async def resolve_destination(self, uid, spoken):
            return PlaceResolution(reason="non conosco ancora nessun luogo")

    class Presence:
        freshness = "CURRENT"
        latitude = 42.25
        longitude = 11.75
        source = "foreground_device"
        acquisition_error = None
        last_seen_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

    async def presence(self, uid):
        return Presence()

    async def search(name, origin):
        assert origin == {"latitude": 42.25, "longitude": 11.75}
        return {"label": "Colosseo", "context": "Roma, Italia", "latitude": 41.89, "longitude": 12.49}

    async def route(**kwargs):
        assert kwargs["destination"] == {"latitude": 41.89, "longitude": 12.49}
        return {"available": True, "provider": "mapbox", "duration_seconds": 3600,
                "distance_meters": 80000, "reflects_current_traffic": True,
                "alternatives": [{"duration_seconds": 3600, "distance_meters": 80000,
                                  "delay_seconds": 600, "delay_reference": "tempo tipico",
                                  "polyline": "route", "incidents": [{"label": "Coda", "road": "A12"}]}]}

    async def weather(polyline, seconds):
        assert (polyline, seconds) == ("route", 3600)
        return [{"label": "Lungo il tragitto", "condition": "pioggia",
                 "rain_chance_pct": 80, "temperature_c": 15}]

    async def options(*args, **kwargs):
        return [{"mode": "drive", "duration_seconds": 3600, "duration_label": "1 ora",
                 "recommended": True, "reflects_current_traffic": True}]

    async def no_appointment(*args, **kwargs):
        return "", ""

    monkeypatch.setattr(caps, "_service", lambda runtime: Service())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setattr(LocationService, "build_presence", presence)
    monkeypatch.setattr(public_search, "preview_destination", search)
    monkeypatch.setattr(routing, "get_route", route)
    monkeypatch.setattr(briefing, "weather_along_route", weather)
    monkeypatch.setattr(caps, "_how_to_get_there", options)
    monkeypatch.setattr(caps, "_when_to_leave", no_appointment)
    obs = run(caps.open_navigation({"destination": "Colosseo"}, {"db": object(), "user_id": "u"}))
    assert obs.payload["road_choices"][0]["incidents"][0]["road"] == "A12"
    assert obs.payload["route_weather"][0]["rain_chance_pct"] == 80
    assert obs.payload["route_provider"] == "mapbox"
    assert "Percorso 1" in obs.payload["advice"]
    assert "Il traffico aggiunge circa 10 min" in obs.payload["advice"]
    from conversation_engine.ai_core.loop import _journey_from
    assert "Percorso 1" in _journey_from([obs.model_dump()])["advice"]
    assert parse_qs(urlparse(obs.payload["url"]).query)["destination"] == ["41.89,12.49"]
    assert "Roma, Italia" in obs.payload["say_this"]


def test_navigation_origin_requires_fix_from_this_departure():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from places.caps import _navigation_origin

    now = datetime.now(timezone.utc)
    presence = SimpleNamespace(freshness="CURRENT", latitude=42.25, longitude=11.75,
                               source="foreground_device", acquisition_error=None,
                               last_seen_at=(now - timedelta(seconds=20)).isoformat())
    assert _navigation_origin(presence) == {"latitude": 42.25, "longitude": 11.75}
    presence.last_seen_at = (now - timedelta(minutes=4)).isoformat()
    assert _navigation_origin(presence) is None
    presence.last_seen_at = now.isoformat()
    presence.acquisition_error = "timeout"
    assert _navigation_origin(presence) is None


def test_public_search_requires_unique_exact_match(monkeypatch):
    from places import public_search
    from places import routing

    class Response:
        status_code = 200

        def json(self):
            return {"features": [
                {"properties": {"name": "Colosseo", "coordinates": {
                    "latitude": 41.89, "longitude": 12.49}}},
                {"properties": {"name": "Colosseo", "coordinates": {
                    "latitude": 40, "longitude": 11}}},
            ]}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params):
            assert params["auto_complete"] == "false"
            assert params["proximity"] == "11.75,42.25"
            return Response()

    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setenv("ROUTING_API_KEY", "test-token")
    monkeypatch.setattr("httpx.AsyncClient", Client)
    found = run(public_search.preview_destination("Colosseo", {"latitude": 42.25, "longitude": 11.75}))
    assert found is None


def test_public_search_uses_routable_entrance(monkeypatch):
    from places import public_search, routing

    class Response:
        status_code = 200

        def json(self):
            return {"features": [{"properties": {
                "name": "Colosseo", "place_formatted": "Roma, Italia",
                "coordinates": {"latitude": 41.89, "longitude": 12.49,
                                "routable_points": [{"latitude": 41.891, "longitude": 12.491}]},
            }}]}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params):
            return Response()

    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setenv("ROUTING_API_KEY", "test-token")
    monkeypatch.setattr("httpx.AsyncClient", Client)
    found = run(public_search.preview_destination("Colosseo", {"latitude": 42.25, "longitude": 11.75}))
    assert found == {"label": "Colosseo", "context": "Roma, Italia",
                     "latitude": 41.891, "longitude": 12.491}


def test_public_search_skips_nearby_nonmatch_and_collapses_same_landmark(monkeypatch):
    from places import public_search, routing

    class Response:
        status_code = 200

        def json(self):
            return {"features": [
                {"properties": {"name": "Bar Colosseo", "coordinates": {
                    "latitude": 42.24, "longitude": 11.75}}},
                {"properties": {"name": "Colosseo", "place_formatted": "Roma, Italia",
                                "coordinates": {"latitude": 41.89021, "longitude": 12.49223}}},
                {"properties": {"name_preferred": "Colosseo", "name": "Colosseum",
                                "coordinates": {"latitude": 41.89025, "longitude": 12.49229}}},
            ]}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params):
            return Response()

    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setenv("ROUTING_API_KEY", "test-token")
    monkeypatch.setattr("httpx.AsyncClient", Client)
    found = run(public_search.preview_destination("Colosseo", {"latitude": 42.24, "longitude": 11.75}))
    assert found == {"label": "Colosseo", "context": "Roma, Italia",
                     "latitude": 41.89021, "longitude": 12.49223}


def test_navigation_rescue_produces_link_when_model_skips_tool(monkeypatch):
    from conversation_engine.ai_core import loop
    from places import caps
    from places.models import PlaceResolution

    class Service:
        async def resolve_destination(self, uid, spoken):
            return PlaceResolution(reason="non conosco ancora nessun luogo")

    monkeypatch.setattr(caps, "_service", lambda runtime: Service())
    observations = []
    message = "portami dalla mia posizione al colosseo"
    assert loop._navigation_destination(message) == "colosseo"
    assert loop._navigation_destination(
        "Portami al Colosseo e dimmi traffico, alternative e meteo lungo il percorso."
    ) == "Colosseo"
    assert loop._navigation_destination("Portami a Via Roma e mostrami il meteo") == "Via Roma"
    assert loop._navigation_destination("Portami a Castiglione della Pescaia, dimmi quando partire") == "Castiglione della Pescaia"
    assert loop._navigation_destination("portami il Colosseo") == "Colosseo"
    response = run(loop._ensure_navigation(observations, 0, message, object(), "u"))
    assert "Google Maps" in response
    assert len(loop._navigation_options(observations)) == 1
    assert loop._navigation_options(observations)[0]["label"] == "Google Maps"
    assert "destination=colosseo" in loop._navigation_options(observations)[0]["url"]
    run(loop._ensure_navigation(observations, 0, message, object(), "u"))
    assert len(observations) == 1
    assert loop._navigation_destination("quanto tempo ci vuole al Colosseo?") == ""


def test_unknown_personal_role_does_not_search_maps(monkeypatch):
    from places import caps
    from places.models import PlaceResolution

    class Service:
        async def resolve_destination(self, uid, spoken):
            return PlaceResolution(reason="non conosco ancora nessun luogo")

    monkeypatch.setattr(caps, "_service", lambda runtime: Service())
    obs = run(caps.open_navigation({"destination": "casa"}, {"db": object(), "user_id": "u"}))
    assert obs.payload["ready"] is False
    assert "url" not in obs.payload


def test_explicit_departure_bypasses_model_and_persists_handoff(monkeypatch):
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.ai_core.state import get_ai_state
    from conversation_engine.models import ConversationSession
    from places import caps
    from places.models import PlaceResolution

    class Service:
        async def resolve_destination(self, uid, spoken):
            return PlaceResolution(reason="non conosco ancora nessun luogo")

    monkeypatch.setattr(caps, "_service", lambda runtime: Service())

    async def model_must_not_run(*args):
        raise AssertionError("A direct departure must not wait for the model")

    sess = ConversationSession(user_id="navigation-test-owner")
    result = run(run_cognitive_loop(
        sess=sess,
        user_message="portami dalla mia posizione al Colosseo",
        db=object(),
        decision_fn=model_must_not_run,
    ))
    assert result.ok and result.ai_calls == 0 and result.context_calls == 0
    assert result.tool_calls == 1
    assert result.navigation[0]["label"] == "Google Maps"
    assert "Colosseo" in result.ora_text
    assert get_ai_state(sess)["recent_turns"][-1]["text"] == result.ora_text


def test_confirming_prepared_navigation_executes_handoff_without_model():
    from datetime import datetime, timezone
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.ai_core.state import (
        get_ai_state, save_ai_state,
    )
    from conversation_engine.models import ConversationSession

    sess = ConversationSession(user_id="navigation-confirm-owner")
    state = get_ai_state(sess)
    state["pending_navigation"] = {
        "options": [{
            "id": "google_maps",
            "label": "Google Maps",
            "url": "https://www.google.com/maps/dir/?api=1&destination=38.716%2C16.129",
        }],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_ai_state(sess, state)

    async def model_must_not_run(*_args, **_kwargs):
        raise AssertionError("A confirmation of a verified handoff must not go back to the model")

    result = run(run_cognitive_loop(
        sess=sess,
        user_message="si",
        db=object(),
        decision_fn=model_must_not_run,
    ))

    assert result.ok
    assert result.ai_calls == 0
    assert result.ora_text == "Apro Google Maps e avvio la navigazione."
    assert result.navigation[0]["label"] == "Google Maps"
    assert result.client_actions == [{
        "type": "open_navigation",
        "url": "https://www.google.com/maps/dir/?api=1&destination=38.716%2C16.129",
        "label": "Google Maps",
    }]
    assert "pending_navigation" not in get_ai_state(sess)


def test_rejecting_prepared_navigation_clears_handoff_without_model():
    from datetime import datetime, timezone
    from conversation_engine.ai_core.loop import run_cognitive_loop
    from conversation_engine.ai_core.state import (
        get_ai_state, save_ai_state,
    )
    from conversation_engine.models import ConversationSession

    sess = ConversationSession(user_id="navigation-cancel-owner")
    state = get_ai_state(sess)
    state["pending_navigation"] = {
        "options": [{
            "id": "google_maps",
            "label": "Google Maps",
            "url": "https://www.google.com/maps/dir/?api=1&destination=38.716%2C16.129",
        }],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_ai_state(sess, state)

    async def model_must_not_run(*_args, **_kwargs):
        raise AssertionError("A rejection of a pending handoff is deterministic")

    result = run(run_cognitive_loop(
        sess=sess,
        user_message="no",
        db=object(),
        decision_fn=model_must_not_run,
    ))

    assert result.ok
    assert result.ai_calls == 0
    assert result.client_actions == []
    assert result.navigation == []
    assert result.ora_text == "Va bene, non avvio la navigazione."
    assert "pending_navigation" not in get_ai_state(sess)



def test_public_destination_refreshes_stale_origin_before_giving_up(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from places import caps, routing
    from places.models import PlaceResolution
    from location.service import LocationService

    class Service:
        async def resolve_destination(self, uid, spoken):
            assert spoken == "Colosseo"
            return PlaceResolution(reason="non conosco ancora nessun luogo")

    class Presence:
        freshness = "CURRENT"
        latitude = 42.25
        longitude = 11.75
        source = "foreground_device"
        acquisition_error = None
        permission_state = "granted_foreground"
        last_seen_at = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()

    async def presence(self, uid, platform="web"):
        return Presence()

    async def preference(self, uid):
        return "while_using"

    monkeypatch.setattr(caps, "_service", lambda runtime: Service())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setattr(LocationService, "build_presence", presence)
    monkeypatch.setattr(LocationService, "get_preference", preference)

    obs = run(caps.open_navigation(
        {"destination": "Colosseo"},
        {"db": object(), "user_id": "u", "platform": "web"},
    ))

    assert obs.status == "needs_client"
    assert obs.payload["ready"] is False
    assert obs.payload["destination_pending"] == "Colosseo"
    assert obs.payload["needs_client"] is True
    assert obs.payload["client_action"]["type"] == "request_foreground_location"
    assert obs.payload["client_action"]["refresh"] is True
    assert "posizione aggiornata" in obs.payload["say_this"].lower()
    assert obs.payload.get("url") is None


def test_public_destination_without_location_consent_requests_permission(monkeypatch):
    from places import caps, routing
    from places.models import PlaceResolution
    from location.service import LocationService

    class Service:
        async def resolve_destination(self, uid, spoken):
            return PlaceResolution(reason="non conosco ancora nessun luogo")

    class Presence:
        freshness = "UNKNOWN"
        latitude = None
        longitude = None
        source = None
        acquisition_error = None
        permission_state = "not_requested"
        last_seen_at = None

    async def presence(self, uid, platform="web"):
        return Presence()

    async def preference(self, uid):
        return "off"

    monkeypatch.setattr(caps, "_service", lambda runtime: Service())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setattr(LocationService, "build_presence", presence)
    monkeypatch.setattr(LocationService, "get_preference", preference)

    obs = run(caps.open_navigation(
        {"destination": "Colosseo"},
        {"db": object(), "user_id": "u", "platform": "web"},
    ))

    assert obs.status == "needs_client"
    assert obs.payload["client_action"]["type"] == "request_location_permission"
    assert "tempi e traffico" in obs.payload["client_action"]["reason"].lower()


def test_public_destination_does_not_request_location_when_routing_is_unavailable(monkeypatch):
    from places import caps, routing
    from places.models import PlaceResolution

    class Service:
        async def resolve_destination(self, uid, spoken):
            return PlaceResolution(reason="non conosco ancora nessun luogo")

    async def should_not_run(runtime):
        raise AssertionError("location should not be requested without live routing")

    monkeypatch.setattr(caps, "_service", lambda runtime: Service())
    monkeypatch.setattr(routing, "configured_provider", lambda: None)
    monkeypatch.setattr(caps, "_route_origin_or_client", should_not_run)

    obs = run(caps.open_navigation(
        {"destination": "Colosseo"},
        {"db": object(), "user_id": "u", "platform": "web"},
    ))

    assert obs.payload["ready"] is True
    assert obs.payload["route"] is None
    assert obs.payload["routing"]["available"] is False
