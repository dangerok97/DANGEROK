"""Siri through Comandi Rapidi: a key that opens one door, answers made to be heard."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from siri import service
from siri.service import SiriTurns


class FakeCore:
    def __init__(self, answer=None, delay=0.0, resume=None):
        self.calls = []
        self.answer = answer or {"ok": True, "session_id": "s1", "ora_text": "Fatto alle 16:00."}
        self.delay = delay
        self.resume = resume

    async def start(self, user_id, **kw):
        self.calls.append(("start", user_id, kw))
        if self.delay:
            await asyncio.sleep(self.delay)
        return dict(self.answer)

    async def message(self, user_id, session_id, **kw):
        self.calls.append(("message", session_id, kw))
        return {"ok": True, "session_id": session_id, "ora_text": "Continuo."}

    async def client_resume(self, user_id, session_id, *, completed=None):
        self.calls.append(("resume", session_id, completed))
        return self.resume or {"ok": True, "session_id": session_id, "ora_text": "Con la posizione: asciutti alle 18."}


class FakeLocation:
    def __init__(self):
        self.signals = []

    async def ingest_foreground_signal(self, user_id, **kw):
        self.signals.append(kw)
        return {"ok": True}


class FakeProvider:
    def __init__(self):
        self.sent = []

    async def send(self, **kw):
        self.sent.append(kw)
        return {"ok": True}


async def _db(name):
    db = AsyncMongoMockClient()[name]
    await db.users.insert_one({"user_id": "u1"})
    return db


@pytest.fixture(autouse=True)
def _reset_rate():
    service._recent.clear()
    yield
    service._recent.clear()


@pytest.mark.asyncio
async def test_key_is_shown_once_stored_as_digest_and_replaced():
    db = await _db("siri_key")
    first = await service.issue(db, "u1")
    assert first["key"].startswith("ora_siri_") and service.looks_like_key(first["key"])
    stored = await db.siri_keys.find_one({"user_id": "u1"})
    assert first["key"] not in str(stored)
    assert stored["digest"] == service.digest(first["key"])
    assert (await service.key_record(db, first["key"]))["user_id"] == "u1"
    second = await service.issue(db, "u1")
    assert await service.key_record(db, first["key"]) is None
    assert await service.key_record(db, second["key"]) is not None
    assert "key" not in await service.status(db, "u1")
    await service.revoke(db, "u1")
    assert await service.key_record(db, second["key"]) is None
    assert (await service.status(db, "u1"))["active"] is False
    assert await service.key_record(db, "not-a-key") is None


@pytest.mark.asyncio
async def test_turn_runs_the_app_core_and_is_said_for_the_ear():
    db = await _db("siri_turn")
    key = (await service.issue(db, "u1"))["key"]
    record = await service.key_record(db, key)
    core = FakeCore()
    out = await SiriTurns(db, core=core, location=FakeLocation()).handle(record, "ho steso i panni")
    assert out["ok"] and out["session_id"] == "s1"
    assert "16:00" not in out["reply"] and "quattro" in out["reply"]
    kind, _, kw = core.calls[0]
    assert kind == "start" and kw["entry_point"] == "siri" and kw["response_channel"] == "voice"
    # A follow-up a minute later continues the same thread.
    record = await service.key_record(db, key)
    out = await SiriTurns(db, core=core, location=FakeLocation()).handle(record, "sì")
    assert core.calls[-1][0] == "message" and core.calls[-1][1] == "s1"


@pytest.mark.asyncio
async def test_an_old_thread_is_not_continued():
    db = await _db("siri_old")
    key = (await service.issue(db, "u1"))["key"]
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    await db.siri_keys.update_one({"user_id": "u1"}, {"$set": {"last_session_id": "s0", "last_turn_at": old}})
    core = FakeCore()
    await SiriTurns(db, core=core, location=FakeLocation()).handle(await service.key_record(db, key), "ciao")
    assert core.calls[0][0] == "start"


@pytest.mark.asyncio
async def test_shortcut_location_answers_the_location_request():
    db = await _db("siri_loc")
    key = (await service.issue(db, "u1"))["key"]
    core = FakeCore(answer={
        "ok": True, "session_id": "s1", "ora_text": "",
        "client_actions": [{"type": "request_foreground_location"}],
    })
    loc = FakeLocation()
    out = await SiriTurns(db, core=core, location=loc).handle(
        await service.key_record(db, key), "ho steso i panni",
        {"latitude": 45.4, "longitude": 9.2, "accuracy": 20},
    )
    assert loc.signals and loc.signals[0]["latitude"] == 45.4
    assert core.calls[-1] == ("resume", "s1", ["request_foreground_location"])
    assert "18" in out["reply"] or "diciotto" in out["reply"].lower() or "sei" in out["reply"]


@pytest.mark.asyncio
async def test_without_location_the_person_is_told_to_open_the_app():
    db = await _db("siri_noloc")
    key = (await service.issue(db, "u1"))["key"]
    core = FakeCore(answer={
        "ok": True, "session_id": "s1", "ora_text": "Mi serve sapere dove sei.",
        "client_actions": [{"type": "request_foreground_location"}],
    })
    out = await SiriTurns(db, core=core, location=FakeLocation()).handle(
        await service.key_record(db, key), "ho steso i panni",
    )
    assert out["reply"].endswith(service.NEEDS_APP.strip())


@pytest.mark.asyncio
async def test_a_long_turn_keeps_going_and_arrives_as_a_notification():
    db = await _db("siri_late")
    key = (await service.issue(db, "u1"))["key"]
    provider = FakeProvider()
    turns = SiriTurns(db, core=FakeCore(delay=0.2), location=FakeLocation(), provider=provider)
    out = await turns.handle(await service.key_record(db, key), "cerca qualcosa", wait=0.05)
    assert out["pending"] and out["reply"] == service.STILL_WORKING
    for _ in range(40):
        if provider.sent:
            break
        await asyncio.sleep(0.02)
    assert provider.sent, "late answer was never delivered"
    sent = provider.sent[0]
    assert sent["deep_link"] == "/ora/s1" and sent["owner_id"] == "u1"
    assert "Siri" in sent["public_body"] and "16:00" not in sent["public_body"]


@pytest.mark.asyncio
async def test_empty_and_flooded_requests_get_a_sentence():
    db = await _db("siri_rate")
    key = (await service.issue(db, "u1"))["key"]
    turns = SiriTurns(db, core=FakeCore(), location=FakeLocation())
    rec = await service.key_record(db, key)
    assert (await turns.handle(rec, "   "))["reply"] == service.EMPTY
    for _ in range(service.RATE_PER_MINUTE):
        await turns.handle(rec, "ciao")
    assert (await turns.handle(rec, "ciao"))["reply"] == service.TOO_MANY


def test_router_reads_shortcut_bodies_and_never_needs_a_session():
    import inspect
    from siri import router
    src = inspect.getsource(router.ask)
    assert "get_current_user" not in src
    assert router._where({"latitude": "45,4", "longitude": "9.2"}) == {"latitude": 45.4, "longitude": 9.2, "accuracy": None}
    assert router._where({"latitude": "200", "longitude": "9"}) is None
