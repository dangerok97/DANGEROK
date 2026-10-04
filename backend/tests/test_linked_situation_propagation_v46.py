import pytest
from mongomock_motor import AsyncMongoMockClient

from connected.models import ConnectedSignal, FieldChange
from connected.situations import record_link


def _signal(owner="alice"):
    return ConnectedSignal(
        owner_id=owner,
        source_id="gmail_1",
        source_type="email",
        signal_type="email.message.added",
        observed_at="2026-10-04T20:00:00+00:00",
        effective_at="2026-10-04T19:59:00+00:00",
        source_object_ref="m1",
        payload_summary="È arrivato un messaggio: «Appuntamento spostato».",
        after="Appuntamento spostato",
        changed_fields=[FieldChange(field="subject", after="Appuntamento spostato")],
        provenance={"thread_ref": "t1"},
    )


@pytest.mark.asyncio
async def test_linked_email_to_appointment_records_situation_change_not_fake_calendar_update():
    db = AsyncMongoMockClient().test
    signal = _signal()

    row = await record_link(
        db,
        "alice",
        signal,
        {
            "relationship": "same_situation",
            "target_ref": "event_123",
            "confidence": 0.91,
            "why": "La mail parla dello stesso appuntamento.",
            "relied_on": ["subject", "calendar_time"],
        },
        candidate={
            "kind": "appointment",
            "ref": "event_123",
            "what": "Dentista",
            "when": "2026-10-05T15:00:00+02:00",
            "last_observed": "2026-10-04T18:00:00+00:00",
            "how_directly_it_knows": "the calendar itself holds this appointment",
        },
    )

    assert row["target_ref"] == "event_123"
    change = await db.meaningful_changes.find_one(
        {"owner_id": "alice", "source": "situations", "entity_ref": "event_123"},
        {"_id": 0},
    )
    assert change is not None
    assert change["kind"] == "linked_source_changed"
    assert change["entity_kind"] == "appointment"

    fake_calendar = await db.meaningful_changes.find_one(
        {"owner_id": "alice", "source": "calendar", "entity_ref": "event_123"}
    )
    assert fake_calendar is None


@pytest.mark.asyncio
async def test_uncertain_link_does_not_propagate_but_linked_document_does():
    db = AsyncMongoMockClient().test
    signal = _signal()

    await record_link(
        db,
        "alice",
        signal,
        {
            "relationship": "uncertain",
            "target_ref": "event_123",
            "confidence": 0.4,
            "why": "Non è chiaro.",
            "relied_on": [],
        },
        candidate={"kind": "appointment", "ref": "event_123"},
    )
    await record_link(
        db,
        "alice",
        signal,
        {
            "relationship": "same_situation",
            "target_ref": "doc_1",
            "confidence": 0.9,
            "why": "Parla del documento.",
            "relied_on": [],
        },
        candidate={"kind": "document", "ref": "doc_1"},
    )

    rows = await db.meaningful_changes.find(
        {"owner_id": "alice"}, {"_id": 0}
    ).to_list(10)
    assert len(rows) == 1
    assert rows[0]["source"] == "situations"
    assert rows[0]["kind"] == "linked_source_changed"
    assert rows[0]["entity_ref"] == "doc_1"
    assert rows[0]["entity_kind"] == "document"
    assert rows[0]["after"] == "nuova evidenza collegata da email"


@pytest.mark.asyncio
async def test_situation_change_is_admitted_for_fresh_opportunity_review():
    from opportunities.changes import ChangeLog

    db = AsyncMongoMockClient().test
    result = await ChangeLog(db).record(
        "alice",
        source="situations",
        kind="linked_source_changed",
        entity_ref="event_123",
        entity_kind="appointment",
        after="una fonte collegata all'appuntamento è cambiata",
    )
    assert result.outcome == "accepted"
    pending = await ChangeLog(db).pending("alice")
    assert len(pending) == 1
    assert pending[0].source == "situations"
    assert pending[0].entity_ref == "event_123"
