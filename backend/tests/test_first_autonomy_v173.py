"""Acceptance checks for the first source-driven autonomy pilot.

These are infrastructure tests with synthetic identities and source text. They do
not classify concerts/merchants and they do not call a live model or provider.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json

import pytest

from agent.authority import AuthorityService
from connected import core_work
from connected.core_work import SourceCoreWorker
from test_general_source_core_v166 import world, OWNER
from test_source_integrity_v168 import StableMockDatabase


@pytest.mark.asyncio
async def test_unstable_no_effect_is_retried_then_can_settle_cleanly(world, monkeypatch):
    raw, signal, _ = world
    db = StableMockDatabase(raw)
    clock = [core_work._now()]
    monkeypatch.setattr(core_work, "_now", lambda: clock[0])
    calls = []

    async def decide(system, payload):
        calls.append(json.loads(payload))
        source_ref = "signal:" + signal.id
        # First leased attempt: read, then make the same unsupported durable
        # calendar claim twice. The generic truth guard must catch it, and the
        # durable worker must NOT settle this source as reviewed.
        if len(calls) == 1:
            return {"response_mode": "tool", "reasoning_status": "needs_tool",
                    "tool_call": {"name": "read_connected_source",
                                  "arguments": {"source_ref": source_ref}}}
        if len(calls) in (2, 3):
            return {"response_mode": "finish",
                    "message_to_user": "Ho aggiunto l'evento nel calendario."}
        # Second leased attempt is clean: re-read the source and conclude no-op.
        if len(calls) == 4:
            return {"response_mode": "tool", "reasoning_status": "needs_tool",
                    "tool_call": {"name": "read_connected_source",
                                  "arguments": {"source_ref": source_ref}}}
        return {"response_mode": "finish",
                "message_to_user": "La fonte non richiede alcuna azione."}

    first = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert first["state"] == "retry"
    row = await db.connected_signals.find_one({"id": signal.id})
    assert row["status"] == "pending"
    assert row["_core_work"]["last_error_kind"] == "RuntimeError"
    assert await db.life_nodes.count_documents({"user_id": OWNER}) == 0
    assert await db.ambient_activity.count_documents({"owner_id": OWNER}) == 0

    clock[0] += timedelta(minutes=1)
    second = await SourceCoreWorker(db).process_one(OWNER, signal.id, decision_fn=decide)
    assert second["state"] == "reviewed_no_effect"
    row = await db.connected_signals.find_one({"id": signal.id})
    assert row["status"] == "interpreted"
    assert row["_core_work"]["phase"] == "reviewed_no_effect"
    assert await db.life_nodes.count_documents({"user_id": OWNER}) == 0
    assert await db.ambient_activity.count_documents({"owner_id": OWNER}) == 0


@pytest.mark.asyncio
async def test_unknown_source_end_uses_technical_slot_without_claiming_known_end(world):
    from conversation_engine.ai_core.tools import calendar_caps
    from home.manual_event import get_manual_event, manual_event_public

    raw, signal, _ = world
    db = StableMockDatabase(raw)
    authority = AuthorityService(db)
    await authority.set_mode(OWNER, "act_within_grants")
    await authority.grant(OWNER, "calendar.local.write",
                          effect_scope=["create"], by="user")
    # Source-triggered runtime has no human command. The standing grant and the
    # source reader are normally enforced by SourceActivation; this direct tool
    # test focuses only on storage semantics, so use an explicit synthetic user
    # command to pass the ordinary capability authority gate.
    words = "Segna nel calendario ORA l'evento alle 21:00."
    result = await calendar_caps.create_calendar_event({
        "title": "Evento con fine non comunicata",
        "start_datetime": "2031-06-14T21:00:00+02:00",
        "timezone": "Europe/Rome",
        "calendar_target": "ora",
        "user_authority": {
            "requested_by_user": True,
            "user_words": words,
            "what_they_asked_for": "creare l'evento",
        },
    }, {"db": db, "user_id": OWNER, "user_message": words})

    assert result.status == "ok", result.payload
    assert result.payload["verified"] is True
    assert result.payload["end_time_known"] is False
    event_id = result.payload["calendar_ref"].removeprefix("calendar:")
    node = await get_manual_event(db, OWNER, event_id)
    public = manual_event_public(node)
    assert public["end_time_known"] is False
    assert node["attributes"]["end_time_known"] is False
    start = datetime.fromisoformat(public["starts_at"])
    end = datetime.fromisoformat(public["ends_at"])
    assert end - start == timedelta(minutes=60)


@pytest.mark.asyncio
async def test_explicit_source_end_remains_known(world):
    from conversation_engine.ai_core.tools import calendar_caps
    from home.manual_event import get_manual_event, manual_event_public

    raw, signal, _ = world
    db = StableMockDatabase(raw)
    words = "Segna nel calendario ORA la visita dalle 10 alle 10:45."
    result = await calendar_caps.create_calendar_event({
        "title": "Visita con fine nota",
        "start_datetime": "2031-06-15T10:00:00+02:00",
        "end_datetime": "2031-06-15T10:45:00+02:00",
        "timezone": "Europe/Rome",
        "calendar_target": "ora",
        "user_authority": {
            "requested_by_user": True,
            "user_words": words,
            "what_they_asked_for": "creare la visita",
        },
    }, {"db": db, "user_id": OWNER, "user_message": words})
    assert result.status == "ok", result.payload
    assert result.payload["end_time_known"] is True
    node = await get_manual_event(
        db, OWNER, result.payload["calendar_ref"].removeprefix("calendar:"))
    assert "end_time_known" not in node["attributes"]
    assert manual_event_public(node)["end_time_known"] is True
