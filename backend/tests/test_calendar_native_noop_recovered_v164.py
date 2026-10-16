"""Selective recovery from experimental CAL164 for current ORA calendar.

No live account or external calendar is touched. Model is not involved;
real native calendar store and capability run against synthetic Mongo.
"""
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from home import manual_event
from conversation_engine.ai_core.tools import calendar_caps

OWNER = "cal164-recovery-owner"
OTHER = "cal164-recovery-neighbor"
DAY = "2027-01-15"
TITLE = "TEST ORA CAL164 – appuntamento fittizio"


@pytest.fixture
def fields():
    return {"start_datetime": DAY + "T11:00:00+01:00", "timezone": "Europe/Rome"}


@pytest.mark.asyncio
async def test_identical_native_updates_only_write_and_wake_once(monkeypatch, fields):
    db = AsyncMongoMockClient().recover_calendar_repeat
    wake = AsyncMock()
    monkeypatch.setattr(manual_event, "_wake", wake)
    event = await manual_event.create_manual_event(
        db, OWNER, title=TITLE, start=DAY+"T10:00:00+01:00",
        end=DAY+"T10:45:00+01:00", tz_name="Europe/Rome", request_id="initial",
    )
    neighbor = await manual_event.create_manual_event(
        db, OTHER, title="Another person's test", start=DAY+"T10:00:00+01:00",
        end=DAY+"T10:45:00+01:00", tz_name="Europe/Rome", request_id="other",
    )
    wake.reset_mock()
    collection = db.life_nodes
    monkeypatch.setattr(db, "life_nodes", collection)
    write = AsyncMock(wraps=collection.update_one)
    monkeypatch.setattr(collection, "update_one", write)

    moved = await manual_event.update_manual_event(db, OWNER, event["id"], fields)
    again = await manual_event.update_manual_event(db, OWNER, event["id"], fields)
    retry = await manual_event.update_manual_event(
        db, OWNER, event["id"], fields, expected_updated_at=event["updated_at"],
    )
    assert moved["changed_now"] is True
    assert again["changed_now"] is retry["changed_now"] is False
    assert write.await_count == wake.await_count == 1
    assert moved["updated_at"] == retry["updated_at"]
    assert moved["starts_at"] == DAY+"T11:00:00+01:00"
    assert moved["ends_at"] == DAY+"T11:45:00+01:00"
    assert manual_event.manual_event_public(
        await manual_event.get_manual_event(db, OTHER, neighbor["id"])
    ) == neighbor


@pytest.mark.asyncio
async def test_native_core_capability_has_no_second_effect(monkeypatch, fields):
    db = AsyncMongoMockClient().recover_calendar_capability
    await db.users.insert_one({"user_id": OWNER, "timezone": "Europe/Rome"})
    wake = AsyncMock()
    monkeypatch.setattr(manual_event, "_wake", wake)
    event = await manual_event.create_manual_event(
        db, OWNER, title=TITLE, start=DAY+"T10:00:00+01:00",
        end=DAY+"T10:45:00+01:00", tz_name="Europe/Rome", request_id="initial",
    )
    wake.reset_mock()
    spoken = "Sposta TEST ORA CAL164 – appuntamento fittizio alle 11:00 nel calendario ORA"
    args = {
        "calendar_ref": "calendar:"+event["id"], **fields,
        "user_authority": {
            "requested_by_user": True, "user_words": spoken,
            "what_they_asked_for": spoken,
        },
    }
    runtime = {"db": db, "user_id": OWNER, "user_message": spoken,
               "reasoning_epoch": "cal164-first"}
    first = await calendar_caps.update_calendar_event(args, runtime)
    assert first.status == "ok", first.model_dump()
    assert first.payload["operation"] == "updated"
    receipt_count = await db.agent_receipts.count_documents({"owner_id": OWNER})
    repeat = await calendar_caps.update_calendar_event(
        args, {**runtime, "reasoning_epoch": "cal164-second"},
    )
    assert repeat.status == "ok", repeat.model_dump()
    assert repeat.payload["operation"] == "already_updated"
    assert repeat.payload["changed_now"] is False
    assert await db.agent_receipts.count_documents({"owner_id": OWNER}) == receipt_count
    assert wake.await_count == 1


@pytest.mark.asyncio
async def test_actual_change_still_updates_and_wrong_owner_does_not(monkeypatch, fields):
    db = AsyncMongoMockClient().recover_calendar_changed
    wake = AsyncMock()
    monkeypatch.setattr(manual_event, "_wake", wake)
    first = await manual_event.create_manual_event(
        db, OWNER, title=TITLE, start=DAY+"T10:00:00+01:00",
        end=DAY+"T10:45:00+01:00", tz_name="Europe/Rome", request_id="initial",
    )
    wake.reset_mock()
    m = await manual_event.update_manual_event(db, OWNER, first["id"], fields)
    n = await manual_event.update_manual_event(
        db, OWNER, first["id"], {**fields, "start_datetime": DAY+"T12:00:00+01:00"},
    )
    assert m["changed_now"] and n["changed_now"]
    assert wake.await_count == 2
    with pytest.raises(ValueError, match="event_not_found"):
        await manual_event.update_manual_event(db, OTHER, first["id"], fields)
    with pytest.raises(ValueError, match="event_changed"):
        await manual_event.update_manual_event(
            db, OWNER, first["id"], fields, expected_updated_at=first["updated_at"],
        )
