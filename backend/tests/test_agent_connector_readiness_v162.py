"""Readiness and account permissions must agree with the actual source read."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.capabilities import CapabilityResolver
from agent.models import AutonomousGoal
from agent.providers import read_calendar, read_mail_metadata
from permissions.service import PermissionService


OWNER = "synthetic-readiness-v162"


def goal():
    return AutonomousGoal(
        owner_id=OWNER, objective="Verificare una comunicazione già disponibile.",
        desired_outcome="Un esito fondato sulle fonti autorizzate.",
    )


async def connection(db, instance, *, connector="mail_gmail", capability="mail.metadata", status="connected", allowed=True, newer=False):
    now = datetime.now(timezone.utc)
    await db.connector_instances.insert_one({
        "id": instance, "user_id": OWNER, "connector_id": connector,
        "status": status, "last_sync_at": now.isoformat(),
        "updated_at": (now + timedelta(minutes=1 if newer else 0)).isoformat(),
        "selected_resource_ids": ["primary"],
    })
    if allowed:
        await PermissionService(db).grant(
            user_id=OWNER, capability_id=capability,
            connector_id=connector, connector_instance_id=instance,
        )


async def mail(db, instance, subject):
    await db.ingestion_events.insert_one({
        "id": f"event_{instance}", "user_id": OWNER, "connector_id": "mail_gmail",
        "connector_instance_id": instance, "source_record_type": "email_message",
        "external_id": f"message_{instance}", "ingestion_status": "processed",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "normalized_payload": {"subject": subject, "message_ref": f"message_{instance}"},
    })


@pytest.mark.asyncio
async def test_sync_in_progress_does_not_hide_a_connected_authorized_account():
    db = AsyncMongoMockClient().v162_readiness
    await connection(db, "syncing_account", status="syncing")
    result = await CapabilityResolver(db).resolve(OWNER, "mail.metadata")
    assert result.permitted and result.usable
    await mail(db, "syncing_account", "Comunicazione già sincronizzata")
    read = await read_mail_metadata(db, OWNER, goal())
    assert read.status == "succeeded"
    assert any("già sincronizzata" in claim.text for claim in read.claims)


@pytest.mark.asyncio
async def test_newer_account_without_grant_does_not_hide_an_older_authorized_one():
    db = AsyncMongoMockClient().v162_readiness
    await connection(db, "authorized")
    await connection(db, "newer_without_grant", allowed=False, newer=True)
    assert (await CapabilityResolver(db).resolve(OWNER, "mail.metadata")).usable


@pytest.mark.asyncio
async def test_mail_metadata_never_reads_another_connected_accounts_ungranted_records():
    db = AsyncMongoMockClient().v162_readiness
    await connection(db, "authorized")
    await connection(db, "without_grant", allowed=False)
    await connection(db, "revoked", status="revoked")
    for instance in ("authorized", "without_grant", "revoked"):
        await mail(db, instance, f"Record {instance}")
    result = await read_mail_metadata(db, OWNER, goal())
    text = " ".join(claim.text for claim in result.claims)
    assert "Record authorized" in text
    assert "Record without_grant" not in text
    assert "Record revoked" not in text


@pytest.mark.asyncio
async def test_calendar_read_uses_only_accounts_with_read_permission():
    db = AsyncMongoMockClient().v162_readiness
    for name, allowed in (("allowed_calendar", True), ("without_grant", False)):
        await connection(db, name, connector="calendar_google", capability="calendar.read", allowed=allowed)
        now = datetime.now(timezone.utc)
        await db.ingestion_events.insert_one({
            "id": f"event_{name}", "user_id": OWNER, "connector_id": "calendar_google",
            "connector_instance_id": name, "external_id": f"event_{name}",
            "source_record_type": "calendar_event", "ingestion_status": "processed",
            "ingested_at": now.isoformat(),
            "normalized_payload": {
                "title": {"value": name}, "calendar_id": {"value": "primary"},
                "starts_at": {"value": (now + timedelta(days=1)).isoformat()},
            },
        })
    result = await read_calendar(db, OWNER, goal())
    text = " ".join(claim.text for claim in result.claims)
    assert "allowed_calendar" in text
    assert "without_grant" not in text


@pytest.mark.asyncio
async def test_mail_reports_sync_freshness_instead_of_making_old_data_fresh():
    db = AsyncMongoMockClient().v162_readiness
    await connection(db, "old_sync")
    await mail(db, "old_sync", "Una comunicazione precedente")
    await db.connector_instances.update_one({"id": "old_sync"}, {"$set": {"last_sync_at": "2020-01-01T00:00:00+00:00"}})
    result = await read_mail_metadata(db, OWNER, goal())
    assert result.provenance.freshness == "stale"
    assert "2020-01-01" in result.observation


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", ["weather.read", "banking.read"])
async def test_unavailable_provider_is_never_advertised_usable_now(monkeypatch, capability):
    db = AsyncMongoMockClient().v162_readiness
    resolver = CapabilityResolver(db)
    monkeypatch.setattr(resolver, "_permitted", AsyncMock(return_value=True))
    monkeypatch.setattr("weather.capabilities", lambda: {"available": False})
    monkeypatch.setattr("connectors.bank.service.agent_bank_status", AsyncMock(return_value="unavailable"))
    resolved = await resolver.resolve(OWNER, capability)
    assert resolved.status == "unavailable"
    assert resolved.usable is False
    available = {item["capability"]: item for item in await resolver.available(OWNER)}
    assert available[capability]["can_be_used_now"] is False


@pytest.mark.asyncio
async def test_write_without_authority_is_real_but_not_usable_now():
    db = AsyncMongoMockClient().v162_readiness
    row = next(item for item in await CapabilityResolver(db).available(OWNER)
               if item["capability"] == "calendar.local.write")
    assert row["status"] == "requires_authority"
    assert row["can_be_used_now"] is False
    assert row["really_does_something"] is True
