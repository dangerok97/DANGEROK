from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient


OWNER = "alice"


def _google_row(*, row_id="ing_dentista", external_id="g_dentista", title="Dentista"):
    start = datetime.now(timezone.utc) + timedelta(days=2)
    end = start + timedelta(hours=1)
    return {
        "id": row_id,
        "user_id": OWNER,
        "connector_id": "calendar_google",
        "source_record_type": "event",
        "source_status": "active",
        "external_id": external_id,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "normalized_payload": {
            "title": {"value": title},
            "starts_at": {"value": start.isoformat()},
            "ends_at": {"value": end.isoformat()},
            "timezone": {"value": "Europe/Rome"},
            "calendar_id": {"value": "primary"},
            "status": {"value": "confirmed"},
            "all_day": {"value": False},
            "location": {"value": ""},
            "description": {"value": ""},
        },
    }


@pytest.mark.asyncio
async def test_imported_google_canonical_ref_is_linked_before_cancel():
    from conversation_engine.ai_core.tools.calendar_caps import cancel_calendar_event

    db = AsyncMongoMockClient().test
    await db.ingestion_events.insert_one(_google_row())

    obs = await cancel_calendar_event(
        {"calendar_ref": "calendar:google:ing_dentista"},
        {
            "user_id": OWNER,
            "db": db,
            "user_message": "cancella il dentista",
        },
    )

    # Before v85 this owner-scoped canonical ref was stripped to
    # "google:ing_dentista" and then looked up literally, producing not_found.
    assert obs.status == "partial"
    assert obs.payload["status"] == "authority_required"
    assert "Dentista" in obs.payload["confirmation_request"]["question"]

    linked = await db.calendar_event_drafts.find_one(
        {"user_id": OWNER, "google_event_id": "g_dentista"},
        {"_id": 0},
    )
    assert linked is not None
    assert linked["title"] == "Dentista"
    assert obs.payload["confirmation_request"]["arguments"]["calendar_ref"].startswith(
        "calendar:ced_google_"
    )


@pytest.mark.asyncio
async def test_exact_title_can_prepare_cancel_without_pre_resolved_ref():
    from conversation_engine.ai_core.tools.calendar_caps import cancel_calendar_event

    db = AsyncMongoMockClient().test
    await db.ingestion_events.insert_one(_google_row())

    obs = await cancel_calendar_event(
        {"target_title": "Dentista"},
        {
            "user_id": OWNER,
            "db": db,
            "user_message": "cancella Dentista",
        },
    )

    assert obs.status == "partial"
    assert obs.payload["status"] == "authority_required"
    assert "Dentista" in obs.payload["confirmation_request"]["question"]
    assert obs.payload["confirmation_request"]["arguments"]["calendar_ref"].startswith(
        "calendar:ced_google_"
    )


@pytest.mark.asyncio
async def test_similar_title_only_suggests_and_never_reaches_delete(monkeypatch):
    from conversation_engine.ai_core.tools import calendar_caps

    db = AsyncMongoMockClient().test
    await db.ingestion_events.insert_one(
        _google_row(title="Visita dentistica controllo")
    )

    deleted = False

    async def must_not_delete(*args, **kwargs):
        nonlocal deleted
        deleted = True
        raise AssertionError("fuzzy title must never reach deletion")

    monkeypatch.setattr("home.calendar_event.delete_event", must_not_delete)

    obs = await calendar_caps.cancel_calendar_event(
        {"target_title": "Visita dentistica"},
        {
            "user_id": OWNER,
            "db": db,
            "user_message": "cancella visita dentistica",
        },
    )

    assert obs.status in ("partial", "not_found")
    if obs.status == "partial":
        assert obs.payload["status"] in ("needs_confirmation", "needs_information")
    assert deleted is False


@pytest.mark.asyncio
async def test_confirmed_local_calendar_cancel_really_archives_event():
    from conversation_engine.ai_core.tools.calendar_caps import (
        cancel_calendar_event,
        continue_calendar_action,
    )
    from home.manual_event import create_manual_event, get_manual_event

    db = AsyncMongoMockClient().test
    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(hours=1)

    event = await create_manual_event(
        db,
        OWNER,
        title="Dentista",
        start=start.isoformat(),
        end=end.isoformat(),
        tz_name="Europe/Rome",
        request_id="cancel-v85",
    )

    first = await cancel_calendar_event(
        {"calendar_ref": f"calendar:{event['id']}"},
        {
            "user_id": OWNER,
            "db": db,
            "user_message": "cancella il dentista",
        },
    )

    assert first.status == "partial"
    assert first.payload["status"] == "authority_required"
    request = first.payload["confirmation_request"]

    pending = {
        "at": datetime.now(timezone.utc).isoformat(),
        "asked": request["question"],
        "calendar_cancel": request,
    }
    second = await continue_calendar_action(
        {},
        {
            "user_id": OWNER,
            "db": db,
            "user_message": "sì",
            "pending_act": pending,
        },
    )

    assert second.status == "ok"
    assert second.payload["verified"] is True
    assert second.payload["operation"] in ("cancelled", "already_cancelled")
    assert second.payload["what_was_removed"] == "Dentista"

    observed = await get_manual_event(db, OWNER, event["id"])
    assert observed is not None
    assert observed["status"] == "archived"
