from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.tools import calendar_caps
from home.manual_event import create_manual_event


OWNER = "alice"
ROME = ZoneInfo("Europe/Rome")


@pytest.mark.asyncio
async def test_named_cancel_finds_event_already_started_but_still_running(monkeypatch):
    db = AsyncMongoMockClient().test
    now = datetime.now(ROME)
    event = await create_manual_event(
        db,
        OWNER,
        title="TEST ORA - seconda passata",
        start=(now - timedelta(minutes=5)).isoformat(),
        end=(now + timedelta(minutes=55)).isoformat(),
        tz_name="Europe/Rome",
        request_id="v85-current-event",
    )

    obs = await calendar_caps.cancel_calendar_event(
        {"target_title": "TEST ORA - seconda passata"},
        {
            "db": db,
            "user_id": OWNER,
            "session_id": "chat-v85",
            "reasoning_epoch": "v85",
            "user_message": "Elimina l'appuntamento TEST ORA - seconda passata",
        },
    )

    # Destructive calendar work still asks for the precise confirmation, but
    # the ongoing event must be found instead of disappearing at its start time.
    assert obs.status == "partial"
    assert obs.payload["status"] == "authority_required"
    assert obs.payload["calendar_ref"] == f"calendar:{event['id']}"
    request = obs.payload["confirmation_request"]
    assert "TEST ORA - seconda passata" in request["question"]
    assert request["arguments"]["calendar_ref"] == f"calendar:{event['id']}"


@pytest.mark.asyncio
async def test_named_cancel_does_not_resurrect_event_that_already_ended():
    db = AsyncMongoMockClient().test
    now = datetime.now(ROME)
    await create_manual_event(
        db,
        OWNER,
        title="TEST ORA - seconda passata",
        start=(now - timedelta(hours=2)).isoformat(),
        end=(now - timedelta(hours=1)).isoformat(),
        tz_name="Europe/Rome",
        request_id="v85-ended-event",
    )

    resolved = await calendar_caps._named_calendar_ref_resolution(
        db,
        OWNER,
        "TEST ORA - seconda passata",
        now=now,
    )

    assert resolved["status"] == "not_found"


@pytest.mark.asyncio
async def test_fuzzy_title_can_suggest_but_never_cancel():
    db = AsyncMongoMockClient().test
    now = datetime.now(ROME)
    event = await create_manual_event(
        db,
        OWNER,
        title="TEST ORA - seconda passata",
        start=(now + timedelta(minutes=15)).isoformat(),
        end=(now + timedelta(minutes=75)).isoformat(),
        tz_name="Europe/Rome",
        request_id="v85-fuzzy-event",
    )

    obs = await calendar_caps.cancel_calendar_event(
        {"target_title": "TEST ORA seconda pasata"},
        {
            "db": db,
            "user_id": OWNER,
            "session_id": "chat-v85",
            "reasoning_epoch": "v85",
            "user_message": "Elimina TEST ORA seconda pasata",
        },
    )

    assert obs.status == "partial"
    assert obs.payload["failure_kind"] == "close_title_candidate"
    assert obs.payload["suggested_event"]["calendar_ref"] == f"calendar:{event['id']}"
    # The event is still active: fuzzy matching is suggestion-only.
    row = await db.life_nodes.find_one({"id": event["id"]}, {"_id": 0, "status": 1})
    assert row["status"] == "active"


def test_calendar_and_navigation_lifecycles_own_their_followup():
    from conversation_engine.ai_core.loop import _LIFECYCLE_OWNING_CAPS

    assert "cancel_calendar_event" in _LIFECYCLE_OWNING_CAPS
    assert "continue_calendar_action" in _LIFECYCLE_OWNING_CAPS
    assert "prepare_a_phone_call" in _LIFECYCLE_OWNING_CAPS
    assert "open_navigation" in _LIFECYCLE_OWNING_CAPS
