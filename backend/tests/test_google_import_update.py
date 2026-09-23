"""Imported Google events use the canonical write path, never create a twin."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.tools import calendar_caps as caps


def _field(value):
    return {"value": value, "provenance": {"provider": "google"}}


async def _seed(db, user_id="owner"):
    await db.ingestion_events.insert_one(
        {
            "id": "ing_google_owned",
            "user_id": user_id,
            "connector_id": "calendar_google",
            "source_status": "active",
            "external_id": "google_event_42",
            "ingested_at": "2026-09-23T10:00:00+00:00",
            "normalized_payload": {
                "title": _field("Dentista"),
                "starts_at": _field("2026-09-24T10:30:00+02:00"),
                "ends_at": _field("2026-09-24T11:30:00+02:00"),
                "calendar_id": "primary",
                "timezone": "Europe/Rome",
                "status": "confirmed",
            },
        }
    )


@pytest.mark.asyncio
async def test_import_bridge_is_idempotent_and_owner_scoped():
    db = AsyncMongoMockClient().db
    await _seed(db)

    first = await caps._linked_google_draft(db, "owner", "google:ing_google_owned")
    again = await caps._linked_google_draft(db, "owner", "google:ing_google_owned")

    assert first["id"] == again["id"]
    assert first["google_event_id"] == "google_event_42"
    assert await db.calendar_event_drafts.count_documents({"user_id": "owner"}) == 1
    assert (
        await caps._linked_google_draft(db, "somebody_else", "google:ing_google_owned")
        is None
    )


@pytest.mark.asyncio
async def test_update_imported_event_keeps_identity_duration_and_reads_back(
    monkeypatch,
):
    db = AsyncMongoMockClient().db
    await _seed(db)

    class Sync:
        async def reschedule_draft(self, *, user_id, draft_id, fields):
            await db.calendar_event_drafts.update_one(
                {"id": draft_id, "user_id": user_id},
                {"$set": {**fields, "sync_status": "synced"}},
            )
            return await db.calendar_event_drafts.find_one(
                {"id": draft_id, "user_id": user_id},
                {"_id": 0},
            )

    async def allowed(*args, **kwargs):
        return None

    async def sync(*args, **kwargs):
        return Sync()

    async def read_back(service, user_id, draft):
        return (
            {
                "id": draft["google_event_id"],
                "summary": draft["title"],
                "start": {"dateTime": draft["start_datetime"]},
            },
            True,
        )

    async def filed(*args, **kwargs):
        return True

    async def assess(*args, **kwargs):
        return SimpleNamespace(may_execute=True, basis="explicit", intent="move-42")

    async def begin(*args, **kwargs):
        return "go"

    async def settle(*args, **kwargs):
        return None

    monkeypatch.setattr(caps, "require_calendar_consent", allowed)
    monkeypatch.setattr(caps, "_sync_service", sync)
    monkeypatch.setattr(caps, "_read_back", read_back)
    monkeypatch.setattr(caps, "_file_it_now", filed)
    monkeypatch.setattr(caps.commanded, "assess", assess)
    monkeypatch.setattr(caps.commanded, "begin", begin)
    monkeypatch.setattr(caps.commanded, "settle", settle)

    result = await caps.update_calendar_event(
        {
            "calendar_ref": "calendar:google:ing_google_owned",
            "start_datetime": "2026-09-24T15:00:00+02:00",
            "user_authority": {
                "requested_by_user": True,
                "user_words": "spostalo alle 15",
            },
        },
        {"user_id": "owner", "db": db, "user_message": "spostalo alle 15"},
    )
    draft = await db.calendar_event_drafts.find_one({"user_id": "owner"}, {"_id": 0})

    assert result.status == "ok"
    assert result.payload["provider_identity_preserved"] is True
    assert draft["google_event_id"] == "google_event_42"
    assert draft["start_datetime"] == "2026-09-24T15:00:00+02:00"
    assert draft["end_datetime"] == "2026-09-24T16:00:00+02:00"
    assert await db.calendar_event_drafts.count_documents({"user_id": "owner"}) == 1
