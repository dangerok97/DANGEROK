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
