"""Explicit arrival times use the current route without pretending to forecast traffic."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from conversation_engine.ai_core.loop import _arrival_request, _ensure_navigation, _navigation_destination
from conversation_engine.ai_core.models import Observation
from places.caps import _when_to_leave


def test_direct_destination_keeps_arrival_out_of_the_place_name():
    message = "Portami al Colosseo, devo arrivare oggi alle 15:00"
    assert _navigation_destination(message) == "Colosseo"
    assert _arrival_request(message) == {"day": "oggi", "hour": 15, "minute": 0}
    assert _arrival_request(message + " e dimmi il traffico") == _arrival_request(message)
    assert _navigation_destination(message + " e dimmi il traffico") == "Colosseo"
    assert _navigation_destination("Portami a Via Roma domani alle 9") == "Via Roma"
    assert _arrival_request("Portami a Via Roma domani alle 9") == {
        "day": "domani", "hour": 9, "minute": 0,
    }
    assert _arrival_request("Quanto ci vuole per il Colosseo alle 15?") == {}


@pytest.mark.asyncio
async def test_chat_fast_path_passes_the_time_to_navigation(monkeypatch):
    from places import caps

    async def navigation(arguments, runtime):
        assert arguments == {"destination": "Colosseo",
                             "arrival_request": {"day": "oggi", "hour": 15, "minute": 0}}
        return Observation(kind="tool", name="open_navigation", status="needs_client",
                           payload={"ready": True, "say_this": "Parti entro le 13:50"})

    monkeypatch.setattr(caps, "open_navigation", navigation)
    observations = []
    sentence = await _ensure_navigation(observations, 0,
                                        "Portami al Colosseo, devo arrivare oggi alle 15:00",
                                        object(), "test")
    assert sentence == "Parti entro le 13:50"
    assert len(observations) == 1


@pytest.mark.asyncio
async def test_explicit_arrival_produces_grounded_leave_time_without_calendar(monkeypatch):
    async def zone(db, uid):
        return SimpleNamespace(tz_name="Europe/Rome")

    class AgendaMustNotRun:
        def __init__(self, db):
            raise AssertionError("La richiesta contiene già l'ora di arrivo")

    monkeypatch.setattr("timezone_service.resolve_user_timezone", zone)
    monkeypatch.setattr("agenda.service.AgendaService", AgendaMustNotRun)
    choices = [{"mode": "drive", "label": "In auto", "duration_seconds": 3600}]
    sentence, leave = await _when_to_leave(
        None, "test", choices, SimpleNamespace(label="Colosseo"),
        arrival_request={"day": "oggi", "hour": 15, "minute": 0},
        now_utc=datetime(2026, 9, 29, 11, 30, tzinfo=timezone.utc),
    )
    assert leave == "13:50"
    assert "parti entro le 13:50" in sentence
    assert "1 h di percorso stimato in auto" in sentence
    assert "10 minuti di margine" in sentence


@pytest.mark.asyncio
async def test_future_traffic_is_not_claimed_as_known(monkeypatch):
    async def zone(db, uid):
        return SimpleNamespace(tz_name="Europe/Rome")

    monkeypatch.setattr("timezone_service.resolve_user_timezone", zone)
    choices = [{"mode": "drive", "label": "In auto", "duration_seconds": 3600}]
    place = SimpleNamespace(label="Colosseo")
    now = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
    later, _ = await _when_to_leave(None, "test", choices, place,
                                    arrival_request={"day": "oggi", "hour": 16, "minute": 0},
                                    now_utc=now)
    assert "partenza indicativa" in later and "traffico futuro può cambiare" in later
    tomorrow, leave = await _when_to_leave(None, "test", choices, place,
                                            arrival_request={"day": "domani", "hour": 16, "minute": 0},
                                            now_utc=now)
    assert leave == "" and "non posso indicare ancora un orario" in tomorrow
