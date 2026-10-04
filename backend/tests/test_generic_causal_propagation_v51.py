import pytest
from mongomock_motor import AsyncMongoMockClient

from connected.models import ConnectedSignal, FieldChange
from connected.situations import record_link


def _calendar_signal(ref="event_1"):
    return ConnectedSignal(
        owner_id="alice",
        source_id="gcal_1",
        source_type="calendar",
        signal_type="calendar.event.changed",
        observed_at="2026-10-05T00:00:00+00:00",
        effective_at="2026-10-06T15:00:00+02:00",
        source_object_ref=ref,
        payload_summary="L'evento calendario è cambiato.",
        before="15:00",
        after="16:00",
        changed_fields=[FieldChange(field="starts_at", before="15:00", after="16:00")],
        provenance={"calendar_id": "primary"},
    )


def _document_signal(ref="doc_1"):
    return ConnectedSignal(
        owner_id="alice",
        source_id="documents",
        source_type="documents",
        signal_type="document.updated",
        observed_at="2026-10-05T00:00:00+00:00",
        source_object_ref=ref,
        payload_summary="Un documento è stato aggiornato.",
        changed_fields=[FieldChange(field="title", after="Documento aggiornato")],
        provenance={},
    )


@pytest.mark.asyncio
async def test_calendar_change_linked_to_life_situation_propagates_generic_context():
    db = AsyncMongoMockClient().test

    await record_link(
        db,
        "alice",
        _calendar_signal(),
        {
            "relationship": "related",
            "target_ref": "life_house_purchase",
            "confidence": 0.88,
            "why": "L'evento riguarda questa situazione.",
            "relied_on": ["calendar", "life_object"],
        },
        candidate={
            "kind": "situation",
            "ref": "life_house_purchase",
            "what": "Acquisto casa",
        },
    )

    change = await db.meaningful_changes.find_one(
        {
            "owner_id": "alice",
            "source": "situations",
            "entity_ref": "life_house_purchase",
        },
        {"_id": 0},
    )
    assert change is not None
    assert change["kind"] == "linked_source_changed"
    assert change["entity_kind"] == "situation"
    assert change["after"] == "nuova evidenza collegata da calendar"


@pytest.mark.asyncio
async def test_document_change_linked_to_appointment_propagates_without_faking_calendar_edit():
    db = AsyncMongoMockClient().test

    await record_link(
        db,
        "alice",
        _document_signal(),
        {
            "relationship": "same_situation",
            "target_ref": "event_99",
            "confidence": 0.91,
            "why": "Il documento riguarda l'appuntamento.",
            "relied_on": ["document", "calendar"],
        },
        candidate={
            "kind": "appointment",
            "ref": "event_99",
            "what": "Rogito",
            "when": "2026-12-19T10:00:00+01:00",
        },
    )

    propagated = await db.meaningful_changes.find_one(
        {
            "owner_id": "alice",
            "source": "situations",
            "entity_ref": "event_99",
        },
        {"_id": 0},
    )
    assert propagated is not None
    assert propagated["entity_kind"] == "appointment"
    assert propagated["after"] == "nuova evidenza collegata da documents"

    assert await db.meaningful_changes.count_documents(
        {"owner_id": "alice", "source": "calendar", "entity_ref": "event_99"}
    ) == 0


@pytest.mark.asyncio
async def test_same_calendar_event_is_not_propagated_as_linked_context_to_itself():
    db = AsyncMongoMockClient().test

    await record_link(
        db,
        "alice",
        _calendar_signal("event_same"),
        {
            "relationship": "same_situation",
            "target_ref": "event_same",
            "confidence": 0.99,
            "why": "Stesso evento.",
            "relied_on": [],
        },
        candidate={
            "kind": "appointment",
            "ref": "event_same",
            "what": "Evento",
        },
    )

    assert await db.meaningful_changes.count_documents(
        {"owner_id": "alice", "source": "situations"}
    ) == 0


@pytest.mark.asyncio
async def test_uncertain_relationship_never_propagates_across_domains():
    db = AsyncMongoMockClient().test

    await record_link(
        db,
        "alice",
        _document_signal(),
        {
            "relationship": "uncertain",
            "target_ref": "life_1",
            "confidence": 0.4,
            "why": "Non è chiaro.",
            "relied_on": [],
        },
        candidate={"kind": "situation", "ref": "life_1", "what": "Situazione"},
    )

    assert await db.meaningful_changes.count_documents(
        {"owner_id": "alice", "source": "situations"}
    ) == 0
