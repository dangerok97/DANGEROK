"""An appointment said in chat lands in the calendar even when the model forgets."""
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core import appointment_net as net

ROME = ZoneInfo("Europe/Rome")
NOW = datetime(2026, 10, 30, 14, 17, tzinfo=ROME)  # Friday


@pytest.mark.parametrize("text,title,loc,when", [
    ("alle 15 ho l'appuntamento dal parrucchiere a Montalto di Castro", "Parrucchiere", "Montalto di Castro", "30 15:00"),
    ("Domani alle 9:30 ho la visita dal dentista in via Roma 12, Tarquinia", "Dentista", "via Roma 12", "31 09:30"),
    ("lunedì alle 18 ho un colloquio a Civitavecchia", "Colloquio", "Civitavecchia", "02 18:00"),
    ("alle 4 devo andare dal meccanico a Viterbo", "Meccanico", "Viterbo", "30 16:00"),
])
def test_it_reads_time_place_and_what(text, title, loc, when):
    found = net.parse(text, now=NOW)
    assert found["title"] == title and found["location"].startswith(loc)
    assert found["start"].strftime("%d %H:%M") == when


@pytest.mark.parametrize("text", [
    "alle 15 ho l'appuntamento dal parrucchiere?",        # question
    "alle 15 ho il parrucchiere",                          # no place
    "ho l'appuntamento a Montalto di Castro",              # no time
    "ieri alle 15 ho avuto la visita a Viterbo",           # past
    "alle 15 non ho l'appuntamento a Viterbo",             # negation
    "ricordami alle 15 di chiamare Asia",                  # no appointment cue/place
])
def test_it_stays_out_of_the_way(text):
    assert net.parse(text, now=NOW) is None


@pytest.mark.asyncio
async def test_writes_once_plans_departure_and_says_so(monkeypatch):
    import opportunities.snapshot as snapshot
    import timezone_service
    from places import leave_notice

    async def clock(_db, _owner, *, now=None):
        return {"local_datetime": NOW.isoformat(), "timezone": "Europe/Rome"}

    monkeypatch.setattr(timezone_service, "user_clock_context", clock)
    db = AsyncMongoMockClient().net_v1
    real_calendar = snapshot._calendar

    async def calendar(_db, owner, now):
        from home.manual_event import manual_events_between
        from datetime import timedelta
        return [{"starts_at": r["starts_at"], "title": r["title"]}
                for r in await manual_events_between(_db, owner, now, now + timedelta(days=7))]

    monkeypatch.setattr(snapshot, "_calendar", calendar)
    monkeypatch.setattr(leave_notice, "plan_owner", AsyncMock(return_value=[
        {"event": "Parrucchiere", "status": "planned", "leave_at_local": "14:25", "minutes": 25, "mode": "in auto"}]))
    text = "alle 15 ho l'appuntamento dal parrucchiere a Montalto di Castro"
    said = await net.ensure_after_turn(db, "u1", text, session_id="s1")
    assert said == ("Ho segnato nel calendario di ORA «Parrucchiere» oggi alle 15:00 a Montalto di Castro. "
                    "Ti avviso alle 14:25 quando è ora di partire (circa 25 min in auto), con il percorso pronto.")
    assert await db.life_nodes.count_documents({"type": "event"}) == 1
    # Already in the calendar: nothing more is written or said.
    assert await net.ensure_after_turn(db, "u1", text, session_id="s2") is None
    assert await db.life_nodes.count_documents({"type": "event"}) == 1
