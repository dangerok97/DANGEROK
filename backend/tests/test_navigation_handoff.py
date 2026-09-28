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
