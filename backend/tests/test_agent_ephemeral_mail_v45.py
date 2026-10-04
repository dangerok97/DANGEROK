from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionStep, AutonomousGoal
from agent import providers


def _goal(owner="alice"):
    return AutonomousGoal(
        owner_id=owner,
        status="active",
        objective="Capire se l'appuntamento è cambiato",
        desired_outcome="Sapere quale orario è valido",
        success_criteria=["L'orario valido è identificato"],
    )


def _step(ref="mail:m1"):
    return ActionStep(
        intent="Leggere il messaggio che potrebbe contenere il nuovo orario",
        step_type="inspect",
        capability_needed="mail.read",
        input_refs=[ref],
        expected_result="Il nuovo orario comunicato nella mail è noto",
    )


@pytest.mark.asyncio
async def test_mail_metadata_exposes_observed_refs_for_selective_body_read():
    db = AsyncMongoMockClient().test
    await db.connector_instances.insert_one({
        "id": "gmail_1", "user_id": "alice",
        "connector_id": "mail_gmail", "status": "connected",
    })
    await db.ingestion_events.insert_one({
        "id": "ing1", "user_id": "alice",
        "connector_instance_id": "gmail_1",
        "source_record_type": "email_message",
        "external_id": "m1",
        "ingested_at": "2026-10-04T20:00:00+00:00",
        "normalized_payload": {
            "message_ref": "m1",
            "subject": "Appuntamento spostato",
            "sender_relationship": "known_person",
            "received_at": "2026-10-04T19:59:00+00:00",
        },
    })

    outcome = await providers.read_mail_metadata(db, "alice", _goal())
    assert "mail:m1" in outcome.provenance.source_refs
    assert any("mail:m1" in claim.text for claim in outcome.claims)


@pytest.mark.asyncio
async def test_mail_body_is_transient_and_only_distilled_facts_leave_provider(monkeypatch):
    db = AsyncMongoMockClient().test
    await db.ingestion_events.insert_one({
        "id": "ing1", "user_id": "alice",
        "connector_instance_id": "gmail_1",
        "source_record_type": "email_message",
        "external_id": "m1",
        "ingested_at": "2026-10-04T20:00:00+00:00",
        "normalized_payload": {"message_ref": "m1"},
    })

    raw_body = "Ciao Francesco, l'appuntamento è stato spostato alle 16:30. CODICE-PRIVATO-991."
    body_for = AsyncMock(return_value=raw_body)

    class Mail:
        pass

    mail = Mail()
    mail.body_for = body_for
    monkeypatch.setattr("deps.get_gmail_service", lambda: mail)

    distill = AsyncMock(return_value={
        "facts": ["L'appuntamento è stato spostato alle 16:30."],
        "enough_for_this_step": True,
        "reasoning": "La mail contiene il nuovo orario.",
    })
    monkeypatch.setattr("agent.reasoning.distill_private_mail", distill)

    outcome = await providers.read_mail_body(
        db, "alice", _goal(), step=_step()
    )

    body_for.assert_awaited_once_with(
        user_id="alice", instance_id="gmail_1", message_id="m1"
    )
    assert outcome.status == "succeeded"
    assert outcome.provenance.capability == "mail.read"
    assert outcome.provenance.source_refs == ["mail:m1"]
    assert outcome.claims[0].text == "L'appuntamento è stato spostato alle 16:30."

    durable_surface = " ".join([
        outcome.observation,
        *[claim.text for claim in outcome.claims],
        *outcome.provenance.source_refs,
    ])
    assert "CODICE-PRIVATO-991" not in durable_surface
    assert raw_body not in durable_surface


@pytest.mark.asyncio
async def test_mail_body_requires_exactly_one_observed_message(monkeypatch):
    db = AsyncMongoMockClient().test
    get_mail = AsyncMock()
    monkeypatch.setattr("deps.get_gmail_service", get_mail)

    no_ref = await providers.read_mail_body(
        db, "alice", _goal(), step=_step(ref="document:d1")
    )
    assert no_ref.status == "unavailable"
    assert no_ref.error_type == "mail_reference_required"

    invented = await providers.read_mail_body(
        db, "alice", _goal(), step=_step(ref="mail:not_seen")
    )
    assert invented.status == "unavailable"
    assert invented.error_type == "message_not_observed"
    get_mail.assert_not_called()


@pytest.mark.asyncio
async def test_failed_distillation_persists_no_private_content(monkeypatch):
    db = AsyncMongoMockClient().test
    await db.ingestion_events.insert_one({
        "id": "ing1", "user_id": "alice",
        "connector_instance_id": "gmail_1",
        "source_record_type": "email_message",
        "external_id": "m1",
        "ingested_at": "2026-10-04T20:00:00+00:00",
        "normalized_payload": {"message_ref": "m1"},
    })

    raw_body = "testo privato che non deve diventare evidenza"
    body_for = AsyncMock(return_value=raw_body)

    class Mail:
        pass

    mail = Mail()
    mail.body_for = body_for
    monkeypatch.setattr("deps.get_gmail_service", lambda: mail)
    monkeypatch.setattr(
        "agent.reasoning.distill_private_mail",
        AsyncMock(return_value=None),
    )

    outcome = await providers.read_mail_body(
        db, "alice", _goal(), step=_step()
    )
    assert outcome.status == "failed"
    assert outcome.error_type == "private_content_distillation_unavailable"
    assert outcome.claims == []
    assert raw_body not in outcome.observation


def test_mail_read_is_real_but_remains_read_only():
    from agent.capabilities import capability_facts, is_really_wired

    facts = capability_facts("mail.read")
    assert facts is not None
    assert facts.writes is False
    assert is_really_wired("mail.read") is True
