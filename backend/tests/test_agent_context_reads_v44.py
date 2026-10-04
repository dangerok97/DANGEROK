from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AutonomousGoal
from agent import providers


def _goal(owner="alice"):
    return AutonomousGoal(
        owner_id=owner,
        status="active",
        objective="Capire cosa è cambiato",
        desired_outcome="Avere contesto aggiornato",
    )


@pytest.mark.asyncio
async def test_mail_metadata_is_real_bounded_and_omits_message_body():
    db = AsyncMongoMockClient().test
    uid = "alice"
    await db.connector_instances.insert_one({
        "id": "gmail_1",
        "user_id": uid,
        "connector_id": "mail_gmail",
        "status": "connected",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.ingestion_events.insert_one({
        "id": "ing_1",
        "user_id": uid,
        "connector_id": "mail_gmail",
        "connector_instance_id": "gmail_1",
        "source_record_type": "email_message",
        "external_id": "m_1",
        "ingested_at": "2026-10-04T20:01:00+00:00",
        "normalized_payload": {
            "message_ref": "m_1",
            "subject": "Cambio appuntamento",
            "sender_relationship": "known_person",
            "received_at": "2026-10-04T20:00:00+00:00",
            "attachments_present": True,
            "attachment_count": 1,
            "body": "contenuto del messaggio non destinato ai metadati",
        },
    })

    outcome = await providers.read_mail_metadata(db, uid, _goal(uid))

    assert outcome.status == "succeeded"
    assert outcome.provenance.capability == "mail.metadata"
    assert outcome.provenance.provider == "gmail_sync"
    joined = " ".join(c.text for c in outcome.claims)
    assert "mail:m_1" in joined
    assert "Cambio appuntamento" in joined
    assert "contenuto del messaggio" not in joined


@pytest.mark.asyncio
async def test_mail_metadata_distinguishes_no_connection_from_empty_mailbox():
    db = AsyncMongoMockClient().test
    outcome = await providers.read_mail_metadata(db, "alice", _goal())
    assert outcome.status == "unavailable"
    assert outcome.error_type == "requires_connection"
    assert not outcome.claims


@pytest.mark.asyncio
async def test_location_read_persists_semantics_not_coordinates():
    db = AsyncMongoMockClient().test
    uid = "alice"
    await db.users.insert_one({
        "user_id": uid,
        "settings": {"location_mode": "while_using"},
    })
    await db.user_presence.insert_one({
        "user_id": uid,
        "freshness": "CURRENT",
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
        "latitude": 42.25,
        "longitude": 11.75,
        "place_label": "Casa",
        "place_locality": "Tarquinia",
        "place_resolver_version": "place-label-v2",
        "source": "foreground_device",
        "permission_state": "granted_foreground",
        "preference": "while_using",
        "source_refs": [],
        "updated_at": "2026-10-04T20:00:00+00:00",
    })

    outcome = await providers.read_location(db, uid, _goal(uid))

    assert outcome.status == "succeeded"
    assert outcome.provenance.capability == "location.read"
    text = " ".join(c.text for c in outcome.claims)
    assert "Casa" in text
    assert "42.25" not in text
    assert "11.75" not in text


@pytest.mark.asyncio
async def test_stale_location_is_not_presented_as_current():
    db = AsyncMongoMockClient().test
    uid = "alice"
    await db.users.insert_one({
        "user_id": uid,
        "settings": {"location_mode": "while_using"},
    })
    await db.user_presence.insert_one({
        "user_id": uid,
        "freshness": "STALE",
        "last_seen_at": "2020-01-01T00:00:00+00:00",
        "latitude": 42.25,
        "longitude": 11.75,
        "place_label": "Casa",
        "source": "foreground_device",
        "permission_state": "granted_foreground",
        "preference": "while_using",
        "source_refs": [],
        "updated_at": "2020-01-01T00:00:00+00:00",
    })

    outcome = await providers.read_location(db, uid, _goal(uid))
    assert outcome.status == "partial"
    assert outcome.error_type == "stale_location"
    assert "non è abbastanza recente" in outcome.observation


@pytest.mark.asyncio
async def test_location_preference_is_mirrored_to_agent_permission_registry():
    db = AsyncMongoMockClient().test

    grant = AsyncMock()
    revoke = AsyncMock()
    fake = type("FakePermissions", (), {"grant": grant, "revoke": revoke})

    with patch("permissions.service.PermissionService", return_value=fake()):
        from location.service import LocationService
        service = LocationService(db)
        assert await service.set_preference("alice", "while_using") == "while_using"
        grant.assert_awaited_once()
        assert grant.await_args.kwargs["capability_id"] == "location.read"
        assert grant.await_args.kwargs["connector_id"] == "location_device"

        assert await service.set_preference("alice", "off") == "off"
        revoke.assert_awaited_once()
        assert revoke.await_args.kwargs["capability_id"] == "location.read"
        assert revoke.await_args.kwargs["connector_id"] == "location_device"


def test_agent_registry_uses_real_connector_ids_and_wiring():
    from agent.capabilities import _CONNECTOR, is_really_wired

    assert _CONNECTOR["location.read"] == "location_device"
    assert _CONNECTOR["contacts.read"] == "contacts_device"
    assert is_really_wired("mail.metadata") is True
    assert is_really_wired("location.read") is True
    assert is_really_wired("mail.read") is False
