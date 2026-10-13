"""Regression suite for consent-governed ORA -> WhatsApp notifications.

These tests use fake phones/providers. No real WhatsApp message is transmitted.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import hashlib
import hmac
import json

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from delivery.models import DeliveryPlan, PushCopy
from whatsapp.alerts import (
    AlertWorker, enqueue, ensure_indexes, in_service_window,
    may_notify, record_status, set_opt_in, template_settings,
)
from whatsapp.cloud import CloudConfig, CloudSendError, iter_signed_delivery_statuses
from whatsapp.service import WhatsAppService, ensure_indexes as ensure_whatsapp_indexes


PHONE = "393331112233"
OWNER = "alert-owner"
OTHER = "another-owner"


@pytest.fixture
def cfg(monkeypatch):
    vars = {
        "WHATSAPP_APP_SECRET": "only-a-test-secret",
        "WHATSAPP_VERIFY_TOKEN": "test-verify",
        "WHATSAPP_ACCESS_TOKEN": "test-meta-token",
        "WHATSAPP_PHONE_NUMBER_ID": "12345678909876",
        "WHATSAPP_DATA_KEY": Fernet.generate_key().decode(),
    }
    for key, value in vars.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("WHATSAPP_ALERT_TEMPLATE_NAME", raising=False)
    return CloudConfig.load()


async def linked(db, cfg, *, last_at=None):
    await ensure_whatsapp_indexes(db)
    await db.whatsapp_links.insert_one({
        "user_id": OWNER,
        "phone_hash": cfg.fingerprint("phone", PHONE),
        "phone_enc": cfg.encrypt(PHONE),
        "phone_last4": "2233",
        "last_inbound_at": last_at or datetime.now(timezone.utc),
        "notifications_enabled": False,
    })


def plan(id="dp_alert_1"):
    return DeliveryPlan(
        id=id, owner_id=OWNER, source_type="opportunity", source_id="opp_1",
        mode="push", status="pending",
        words=PushCopy(
            title="Private expanded title",
            body="Private expanded details, do not deliver via WhatsApp",
            public_title="Un aggiornamento importante",
            public_body="Apri ORA per la situazione",
        ),
    )


@pytest.mark.asyncio
async def test_pairing_is_not_notification_consent_and_no_alert_is_enqueued(cfg):
    db = AsyncMongoMockClient().wa_alert_pairing
    await linked(db, cfg)
    assert (await WhatsAppService(db, cfg).status(OWNER))["notifications_enabled"] is False
    assert not await may_notify(db, OWNER)
    assert not await enqueue(db, OWNER, plan())
    assert await db.whatsapp_alert_outbox.count_documents({}) == 0


@pytest.mark.asyncio
async def test_owner_opt_in_then_deduplicated_alert_and_opt_out(cfg):
    db = AsyncMongoMockClient().wa_alert_consent
    await linked(db, cfg)
    assert (await set_opt_in(db, OWNER, True))["notifications_enabled"]
    link = await db.whatsapp_links.find_one({"user_id": OWNER})
    assert link.get("opt_in_source") == "authenticated_ora_app"
    assert link.get("opt_in_scope") == "important_ora_updates"
    assert await may_notify(db, OWNER)
    assert await enqueue(db, OWNER, plan()) is True
    assert await enqueue(db, OWNER, plan()) is False
    row = await db.whatsapp_alert_outbox.find_one({})
    assert row["owner_id"] == OWNER
    assert row["copy"] == "Un aggiornamento importante. Apri ORA per la situazione"
    assert "Private expanded" not in str(row)
    assert "phone_enc" not in row
    assert await db.whatsapp_alert_outbox.count_documents({}) == 1
    assert not await enqueue(db, OTHER, plan())
    await set_opt_in(db, OWNER, False)
    assert not await may_notify(db, OWNER)
    assert (await db.whatsapp_alert_outbox.find_one({}))["status"] == "cancelled"
    assert not await enqueue(db, OWNER, plan(id="dp_alert_2"))


@pytest.mark.asyncio
async def test_relink_unlinks_and_resets_opt_in(cfg):
    db = AsyncMongoMockClient().wa_alert_unlink
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    await enqueue(db, OWNER, plan())
    await WhatsAppService(db, cfg).disconnect(OWNER)
    assert not await db.whatsapp_links.find_one({"user_id": OWNER})
    assert (await db.whatsapp_alert_outbox.find_one({}))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_worker_sends_once_in_real_customer_window(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_alert_send
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    item = plan()
    await db.delivery_plans.insert_one(item.model_dump())
    assert await enqueue(db, OWNER, item)
    from delivery.service import DeliveryService

    async def source(self, user_id, candidate):
        assert user_id == OWNER and candidate.id == item.id
        return SimpleNamespace(status="active")

    async def not_muted(self, *_):
        return False

    calls = []

    async def fake_send(self, recipient, *, message="", template=None):
        calls.append((recipient, message, template))
        return "wamid.synthetic_outbound_1"

    monkeypatch.setattr(DeliveryService, "_current_subject_for_plan", source)
    monkeypatch.setattr(DeliveryService, "_muted", not_muted)
    monkeypatch.setattr(CloudConfig, "send_proactive", fake_send)

    worker = AlertWorker(db, cfg)
    assert await worker.process_one()
    assert not await worker.process_one()
    row = await db.whatsapp_alert_outbox.find_one({})
    assert row["status"] == "accepted"
    assert row["wamid"] == "wamid.synthetic_outbound_1"
    assert calls == [(PHONE, "Un aggiornamento importante. Apri ORA per la situazione", None)]
    assert row["status"] != "delivered"  # Meta accepted, did not prove device delivery.


@pytest.mark.asyncio
async def test_closed_source_fences_outbound_before_provider(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_alert_closed
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    item = plan()
    await db.delivery_plans.insert_one(item.model_dump())
    await enqueue(db, OWNER, item)
    from delivery.service import DeliveryService

    async def vanished(*_):
        return None

    async def fail_send(*_args, **_kwargs):
        pytest.fail("Cannot alert about closed source")

    monkeypatch.setattr(DeliveryService, "_current_subject_for_plan", vanished)
    monkeypatch.setattr(CloudConfig, "send_proactive", fail_send)
    assert await AlertWorker(db, cfg).process_one()
    assert (await db.whatsapp_alert_outbox.find_one({}))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_outside_window_requires_configured_meta_template(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_alert_template
    await linked(db, cfg, last_at=datetime.now(timezone.utc) - timedelta(days=2))
    await set_opt_in(db, OWNER, True)
    assert not await may_notify(db, OWNER)
    assert not await enqueue(db, OWNER, plan())
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", "ora_aggiornamento_importante")
    assert template_settings() == ("ora_aggiornamento_importante", "it")
    assert await may_notify(db, OWNER)
    item = plan()
    await db.delivery_plans.insert_one(item.model_dump())
    await enqueue(db, OWNER, item)
    from delivery.service import DeliveryService
    async def source(*_):
        return SimpleNamespace(status="active")
    async def not_muted(*_):
        return False
    seen = []
    async def fake_send(self, recipient, *, message="", template=None):
        seen.append((recipient, message, template))
        return "wamid.synthetic_template"
    monkeypatch.setattr(DeliveryService, "_current_subject_for_plan", source)
    monkeypatch.setattr(DeliveryService, "_muted", not_muted)
    monkeypatch.setattr(CloudConfig, "send_proactive", fake_send)
    assert await AlertWorker(db, cfg).process_one()
    assert seen == [(PHONE, "", ("ora_aggiornamento_importante", "it"))]
    row = await db.whatsapp_alert_outbox.find_one({})
    assert row["status"] == "accepted"
    assert row["kind"] == "approved_template"


@pytest.mark.asyncio
async def test_ambiguous_acceptance_is_never_resent(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_alert_uncertain
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    item = plan()
    await db.delivery_plans.insert_one(item.model_dump())
    await enqueue(db, OWNER, item)
    from delivery.service import DeliveryService
    async def source(*_):
        return SimpleNamespace(status="active")
    async def not_muted(*_):
        return False
    calls = []
    async def ambiguous(*_args, **_kwargs):
        calls.append(1)
        raise CloudSendError(502)
    monkeypatch.setattr(DeliveryService, "_current_subject_for_plan", source)
    monkeypatch.setattr(DeliveryService, "_muted", not_muted)
    monkeypatch.setattr(CloudConfig, "send_proactive", ambiguous)
    worker = AlertWorker(db, cfg)
    assert await worker.process_one()
    assert not await worker.process_one()
    assert calls == [1]
    assert (await db.whatsapp_alert_outbox.find_one({}))["status"] == "acceptance_unknown"


@pytest.mark.asyncio
async def test_receipt_updates_are_owner_phone_bound_and_monotonic(cfg):
    db = AsyncMongoMockClient().wa_alert_receipt
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    await enqueue(db, OWNER, plan())
    await db.whatsapp_alert_outbox.update_one(
        {"owner_id": OWNER},
        {"$set": {"status": "accepted", "wamid": "wamid.synthetic_4"}},
    )
    receipt = {"id": "wamid.synthetic_4", "recipient_id": PHONE}
    assert not await record_status(db, cfg, {**receipt, "status": "delivered",
                                           "recipient_id": "393339999999"})
    assert await record_status(db, cfg, {**receipt, "status": "delivered"})
    assert not await record_status(db, cfg, {**receipt, "status": "sent"})
    assert await record_status(db, cfg, {**receipt, "status": "read"})
    assert not await record_status(db, cfg, {**receipt, "status": "failed"})
    assert (await db.whatsapp_alert_outbox.find_one({}))["status"] == "read"


def test_meta_status_parser_accepts_only_business_number_and_supported_status():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "12345678909876"},
            "statuses": [
                {"id": "wamid.synthetic_4", "status": "delivered",
                 "recipient_id": PHONE},
                {"id": "wamid.invalid", "status": "unknown",
                 "recipient_id": PHONE},
            ],
        }}]}],
    }
    parsed = list(iter_signed_delivery_statuses(payload, "12345678909876"))
    assert parsed == [{"id": "wamid.synthetic_4", "status": "delivered",
                       "recipient_id": PHONE}]
    assert list(iter_signed_delivery_statuses(payload, "another_id")) == []


@pytest.mark.asyncio
async def test_channel_permission_is_not_tied_to_expo_push(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_alert_permissions
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    from delivery import context as delivery_context
    from life_attention import context as life_context

    async def expo_not_allowed(*_):
        return False

    monkeypatch.setattr(life_context, "notifications_allowed", expo_not_allowed)
    allowed = await delivery_context._permission(db, OWNER, datetime.now(timezone.utc))
    assert allowed["push"] is True
    assert (await delivery_context._permission(db, OTHER, datetime.now(timezone.utc)))["push"] is False

@pytest.mark.asyncio
async def test_canonical_delivery_service_adds_whatsapp_alert_once(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_alert_delivery_bridge
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    item = plan("dp_integrated")
    await db.delivery_plans.insert_one(item.model_dump())
    from delivery.service import DeliveryService
    from delivery import provider as delivery_provider

    async def current_subject(*_):
        return SimpleNamespace(status="active", evidence=[])

    class FakeProvider:
        async def send(self, **kwargs):
            return {"ok": True, "provider": "test"}

    monkeypatch.setattr(DeliveryService, "_current_subject_for_plan", current_subject)
    monkeypatch.setattr(delivery_provider, "get_provider", lambda: FakeProvider())
    await DeliveryService(db)._send(OWNER, item)
    assert item.status == "delivered"
    assert await db.whatsapp_alert_outbox.count_documents({"owner_id": OWNER}) == 1
    row = await db.whatsapp_alert_outbox.find_one({"owner_id": OWNER})
    assert row["plan_id"] == "dp_integrated"
    assert row["status"] == "ready"
