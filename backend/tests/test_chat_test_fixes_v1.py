"""Owner chat test 3/11: wrong day in Google, «Appuntamento» duplicate, no model → no help."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core import appointment_net, offline
from conversation_engine.ai_core.tools import calendar_caps

ROME = ZoneInfo("Europe/Rome")
OWNER = "usr_chatfix_v1"
TUE = datetime(2026, 11, 3, 8, 27, tzinfo=ROME)


def test_stated_day_and_title():
    assert appointment_net.stated_day("Venerdì alle 17 ho la palestra a Tarquinia", now=TUE) == TUE.date() + timedelta(days=3)
    assert appointment_net.stated_day("domani alle 9 dentista", now=TUE) == TUE.date() + timedelta(days=1)
    assert appointment_net.stated_day("alle 9 dentista", now=TUE) is None
    assert appointment_net.stated_day("martedì scorso", now=TUE) is None
    found = appointment_net.parse("Venerdì alle 17 ho la palestra a Tarquinia", now=TUE)
    assert found["title"] == "Palestra" and found["start"].day == 6


def test_the_model_cannot_move_friday_to_today(monkeypatch):
    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return TUE.astimezone(tz) if tz else TUE
    monkeypatch.setattr(calendar_caps, "datetime", Fixed)
    start, end = calendar_caps._the_day_they_said("2026-11-03T17:00:00+01:00", "2026-11-03T18:00:00+01:00",
                                                  "Venerdì alle 17 ho la palestra a Tarquinia", "Europe/Rome")
    assert start.startswith("2026-11-06T17:00") and end.startswith("2026-11-06T18:00")
    # Two day words, or none: the model's date stands.
    assert calendar_caps._the_day_they_said("2026-11-03T17:00:00+01:00", None, "sposta da lunedì a venerdì", "Europe/Rome")[0] \
        == "2026-11-03T17:00:00+01:00"
    assert calendar_caps._the_day_they_said("2026-11-03T17:00:00+01:00", None, "alle 17 palestra", "Europe/Rome")[0] \
        == "2026-11-03T17:00:00+01:00"


@pytest.fixture
def clock(monkeypatch):
    import timezone_service

    async def user_clock(_db, _owner, *, now=None):
        return {"local_datetime": TUE.isoformat(), "timezone": "Europe/Rome"}

    monkeypatch.setattr(timezone_service, "user_clock_context", user_clock)
    import memos.caps as caps

    async def local_now(db, owner):
        return TUE
    monkeypatch.setattr(caps, "_local_now", local_now)


@pytest.mark.asyncio
async def test_without_a_model_reminders_and_appliances_still_work(clock):
    db = AsyncMongoMockClient().offline_v1
    said = await offline.answer(db, OWNER, "Ricordami tra 3 ore di chiamare il commercialista")
    assert "Chiamare il commercialista" in said and "11:27" in said
    said = await offline.answer(db, OWNER, "ricordami alle 18 di comprare il pane")
    assert "Comprare il pane" in said and "18:00" in said
    said = await offline.answer(db, OWNER, "Ho avviato la lavatrice")
    assert "lavatrice" in said and "10:27" in said
    assert await db.reminders.count_documents({"user_id": OWNER}) == 3
    assert await offline.answer(db, OWNER, "Che tempo fa domani?") == offline.UNAVAILABLE
    assert await offline.answer(db, OWNER, "Ho messo la moka") == offline.UNAVAILABLE


@pytest.mark.asyncio
async def test_a_deleted_google_event_stays_deleted_whatever_its_twin_says():
    from opportunities.snapshot import _appointments_that_still_stand
    db = AsyncMongoMockClient().twin_v1
    start = (TUE + timedelta(hours=8)).astimezone(ROME)
    def row(status, at):
        v = lambda x: {"value": x}
        return {"user_id": OWNER, "source_record_type": "calendar_event", "connector_id": "calendar_google",
                "external_id": "g1", "ingested_at": at, "ingestion_status": "ingested",
                "normalized_payload": {"title": v("Palestra a Tarquinia"), "starts_at": v(start.isoformat()),
                                       "status": v(status)}}
    await db.ingestion_events.insert_many([row("cancelled", "2026-11-03T07:32:45.572"),
                                           row("confirmed", "2026-11-03T07:32:45.580")])
    assert await _appointments_that_still_stand(db, OWNER, TUE, TUE + timedelta(days=2)) == []
