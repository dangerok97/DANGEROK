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

    monkeypatch.setattr(caps, "_service", lambda runtime: Service())
    monkeypatch.setattr(routing, "configured_provider", lambda: "mapbox")
    monkeypatch.setattr(LocationService, "build_presence", presence)
    monkeypatch.setattr(public_search, "preview_destination", search)
    monkeypatch.setattr(routing, "get_route", route)
    monkeypatch.setattr(briefing, "weather_along_route", weather)
    monkeypatch.setattr(caps, "_how_to_get_there", options)
    obs = run(caps.open_navigation({"destination": "Colosseo"}, {"db": object(), "user_id": "u"}))
    assert obs.payload["road_choices"][0]["incidents"][0]["road"] == "A12"
    assert obs.payload["route_weather"][0]["rain_chance_pct"] == 80
    assert obs.payload["route_provider"] == "mapbox"
    assert parse_qs(urlparse(obs.payload["url"]).query)["destination"] == ["41.89,12.49"]
    assert "Roma, Italia" in obs.payload["say_this"]


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
