from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionEffect, ActionIntent
from opportunities.snapshot import _disagreements, evidence_refs


def _when(hours=24):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0
    ).isoformat()


class CalendarHarness:
    def __init__(self):
        from connectors.google_calendar.provider import FakeGoogleCalendarProvider

        self.provider = FakeGoogleCalendarProvider()
        self.provider.seed_calendar(
            calendar_id="primary", summary="Primary", primary=True
        )

    async def _get_access_token(self, *, user_id, instance):
        return "fake-access"

    async def list_calendars_for_instance(self, *, user_id, instance_id):
        return [{"id": "primary", "primary": True}]


async def _connected(db):
    await db.connector_instances.insert_one({
        "id": "gcal_1",
        "user_id": "alice",
        "connector_id": "calendar_google",
        "status": "connected",
        "metadata": {"default_calendar_id": "primary"},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def _modify_intent(event_id, start, *, title="Dentista"):
    return ActionIntent(
        owner_id="alice",
        goal_id="goal_1",
        step_id="step_1",
        capability="calendar.write",
        effect_summary="Aggiornare l'orario dell'appuntamento",
        target_ref=event_id,
        parameter_refs=[event_id],
        authority_required="calendar.write",
        expected_effect="L'appuntamento ha il nuovo orario",
        reversibility="easily",
        external_effect=True,
        status="prepared",
        effect=ActionEffect(
            effect_type="modify",
            target=event_id,
            effect_summary="Spostare l'appuntamento",
            external_party=False,
            reversibility="easily",
            expected_outcome="L'appuntamento ha il nuovo orario",
        ),
        parameters={
            "title": title,
            "starts_at": start,
            "ends_at": (
                datetime.fromisoformat(start) + timedelta(hours=1)
            ).isoformat(),
            "timezone": "Europe/Rome",
        },
    )


@pytest.mark.asyncio
async def test_google_calendar_modify_updates_existing_event_instead_of_creating_duplicate(monkeypatch):
    import agent.effects as effects

    db = AsyncMongoMockClient().test
    await _connected(db)
    calendar = CalendarHarness()
    old_start = _when(24)
    new_start = _when(26)
    calendar.provider.seed_event(
        calendar_id="primary",
        event={
            "id": "event_123",
            "summary": "Dentista",
            "description": "",
            "start": {"dateTime": old_start},
            "end": {"dateTime": (
                datetime.fromisoformat(old_start) + timedelta(hours=1)
            ).isoformat()},
            "status": "confirmed",
            "etag": "v1",
        },
    )
    monkeypatch.setattr(effects, "_calendar_service", lambda db_: calendar)

    outcome = await effects.calendar_write(
        db, "alice", _modify_intent("event_123", new_start)
    )

    assert outcome.receipt.provider_status == "succeeded"
    assert outcome.receipt.external_ref == "event_123"
    assert len(calendar.provider.events["primary"]) == 1
    changed = calendar.provider.events["primary"]["event_123"]
    assert changed["start"]["dateTime"] == new_start
    assert "aggiornato" in outcome.observation.lower()
    assert outcome.provenance.source_refs == ["event_123"]


@pytest.mark.asyncio
async def test_google_calendar_modify_refuses_shared_event_on_personal_path(monkeypatch):
    import agent.effects as effects

    db = AsyncMongoMockClient().test
    await _connected(db)
    calendar = CalendarHarness()
    old_start = _when(24)
    new_start = _when(26)
    calendar.provider.seed_event(
        calendar_id="primary",
        event={
            "id": "shared_123",
            "summary": "Riunione",
            "start": {"dateTime": old_start},
            "end": {"dateTime": (
                datetime.fromisoformat(old_start) + timedelta(hours=1)
            ).isoformat()},
            "attendees": [{"email": "other@example.test"}],
            "status": "confirmed",
        },
    )
    monkeypatch.setattr(effects, "_calendar_service", lambda db_: calendar)

    outcome = await effects.calendar_write(
        db, "alice", _modify_intent("shared_123", new_start, title="Riunione")
    )

    assert outcome.receipt.provider_status == "failed"
    assert outcome.receipt.error_type == "shared_event_requires_separate_authority"
    assert calendar.provider.events["primary"]["shared_123"]["start"]["dateTime"] == old_start


@pytest.mark.asyncio
async def test_disagreement_exposes_mail_and_calendar_refs_to_agent():
    db = AsyncMongoMockClient().test
    await db.connected_situation_links.insert_one({
        "id": "link_1",
        "owner_id": "alice",
        "signal_id": "sig_1",
        "source_type": "email",
        "source_object_ref": "m1",
        "relationship": "same_situation",
        "target_kind": "appointment",
        "target_ref": "event_123",
        "confidence": 0.9,
        "reason_summary": "La mail parla dello stesso appuntamento.",
        "disagreements": [{
            "about": "orario",
            "what_this_source_says": "Nuovo orario alle 16:30",
            "what_the_other_says": "05/10 alle 15:00",
            "how_this_source_knows": "somebody wrote it in a message",
            "how_the_other_knows": "the calendar itself holds this appointment",
        }],
        "decided_at": datetime.now(timezone.utc).isoformat(),
    })

    # A timing disagreement is actionable only while the original calendar
    # appointment remains verifiably future. A naked link id is not evidence
    # that the event still exists; that was the cause of stale trip prompts.
    start = datetime.now(timezone.utc) + timedelta(days=3)
    await db.calendar_events.insert_one({
        "user_id": "alice", "id": "event_123", "status": "active",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=1)).isoformat(),
        "timezone": "UTC",
    })

    rows = await _disagreements(db, "alice", datetime.now(timezone.utc))
    assert rows
    row = rows[0]
    assert row["source_ref"] == "mail:m1"
    assert row["target_ref"] == "event_123"
    assert row["target_kind"] == "appointment"

    refs = evidence_refs({"disagreements": rows})
    assert refs["mail:m1"] == "mail_message"
    assert refs["event_123"] == "calendar_event"
    assert refs["link_1"] == "disagreement"
