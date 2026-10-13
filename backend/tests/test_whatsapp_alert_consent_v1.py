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
    may_notify, record_status, set_opt_in, set_detail_preference, template_settings,
    public_copy, recurring_template_detail,
)
from whatsapp.cloud import CloudConfig, CloudSendError, iter_signed_delivery_statuses
from whatsapp.service import WhatsAppService, ensure_indexes as ensure_whatsapp_indexes
from whatsapp.template_provisioning import (
    TEMPLATE_NAME, TEMPLATE_BODY, TEMPLATE_SCOPE, TEMPLATE_LANGUAGE,
    EXAMPLE_TEXT, review_payload, request_review,
)


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
    monkeypatch.delenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", raising=False)
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
            public_title="Spedizione in consegna",
            public_body="Il corriere ha confermato la consegna per oggi.",
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
    assert "copy" not in row
    assert "Spedizione in consegna" not in str(row)
    assert "Spedizione in consegna" in cfg.decrypt(row["copy_enc"])
    assert "Il corriere ha confermato" in cfg.decrypt(row["copy_enc"])
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
    assert calls == [(PHONE, public_copy(item), None)]
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
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    from whatsapp import template_approval

    async def meta_approved(*args, **kwargs):
        return "approved_dynamic"

    monkeypatch.setattr(template_approval, "approval_status", meta_approved)
    assert template_settings() == (TEMPLATE_NAME, TEMPLATE_LANGUAGE)
    assert await may_notify(db, OWNER)
    item = plan()
    await db.delivery_plans.insert_one(item.model_dump())
    await db.opportunities.insert_one({
        "id": item.source_id, "owner_id": OWNER,
        "status": "active", "source_context": TEMPLATE_SCOPE,
    })
    assert await enqueue(db, OWNER, item)
    from delivery.service import DeliveryService
    async def source(*_):
        return SimpleNamespace(status="active", source_context=TEMPLATE_SCOPE)
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
    assert seen == [(PHONE, "", (TEMPLATE_NAME, "it", recurring_template_detail(public_copy(item))))]
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



@pytest.mark.parametrize("utterance", [
    "STOP", "stop.", "Stop notifiche", "STOP AVVISI",
    "Disattiva notifiche WhatsApp", "disattiva gli avvisi", 
    "Non inviarmi più notifiche", "Non mandarmi piu avvisi",
])
def test_explicit_whatsapp_opt_out_words(utterance):
    from whatsapp.service import _is_alert_optout
    assert _is_alert_optout(utterance)


@pytest.mark.parametrize("utterance", [
    "Cosa significa STOP?", "Voglio un cartello STOP",
    "STOP per favore, dimmi altro", "Non disattivare avvisi",
    "Attiva notifiche WhatsApp", "Stop! Ma che succede?",
])
def test_conversation_about_stop_does_not_revoke_consent(utterance):
    from whatsapp.service import _is_alert_optout
    assert not _is_alert_optout(utterance)


@pytest.mark.asyncio
async def test_stop_on_paired_whatsapp_revokes_notifications_immediately(cfg, monkeypatch):
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    db = AsyncMongoMockClient().wa_alert_stop_direct
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    assert await enqueue(db, OWNER, plan())
    outgoing = await db.whatsapp_alert_outbox.find_one({})
    assert outgoing["status"] == "ready"

    async def do_not_call_ai(self, *args, **kwargs):
        pytest.fail("STOP is a consent revoke, not an AI task")

    monkeypatch.setattr(AICoreOrchestrator, "start", do_not_call_ai)
    monkeypatch.setattr(AICoreOrchestrator, "message", do_not_call_ai)
    sender_item = {
        "phone_enc": cfg.encrypt(PHONE),
        "phone_hash": cfg.fingerprint("phone", PHONE),
        "text_enc": cfg.encrypt("STOP"),
        "kind": "text",
        "provider_message_id": "wamid.synthetic_user_stop",
    }
    response, owner = await WhatsAppService(db, cfg).prepare_reply(sender_item)
    assert owner == OWNER
    assert "disattivati" in response.lower()
    assert "Continuerò a rispondere" in response
    link = await db.whatsapp_links.find_one({"user_id": OWNER})
    assert link["notifications_enabled"] is False
    assert "opted_in_at" not in link
    assert await db.whatsapp_alert_outbox.count_documents({"status": "cancelled"}) == 1
    assert not await may_notify(db, OWNER)
    # Stop notifications must never unlink conversational access.
    assert (await WhatsAppService(db, cfg).status(OWNER))["linked"] is True



@pytest.mark.asyncio
async def test_template_name_alone_never_authorizes_external_outreach(cfg, monkeypatch):
    from whatsapp.template_approval import approval_status

    db = AsyncMongoMockClient().wa_alert_template_unverified
    await linked(db, cfg, last_at=datetime.now(timezone.utc) - timedelta(days=2))
    await set_opt_in(db, OWNER, True)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    monkeypatch.delenv("WHATSAPP_WABA_ID", raising=False)
    assert await approval_status(cfg) == "waba_not_configured"
    assert not await may_notify(db, OWNER)
    assert not await enqueue(db, OWNER, plan())


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "category", "body", "expected"), [
    ("APPROVED", "UTILITY", "ORA ha un aggiornamento.", "approved"),
    ("PENDING", "UTILITY", "ORA ha un aggiornamento.", "pending"),
    ("REJECTED", "UTILITY", "ORA ha un aggiornamento.", "rejected"),
    ("APPROVED", "MARKETING", "ORA ha un aggiornamento.", "wrong_category"),
    ("APPROVED", "UTILITY", TEMPLATE_BODY, "approved_dynamic"),
    ("APPROVED", "UTILITY", "ORA: {{1}}", "wrong_content"),
])
async def test_real_meta_template_metadata_required_before_outreach(
    cfg, monkeypatch, status, category, body, expected
):
    import httpx
    from whatsapp.template_approval import _CACHE, approval_status

    _CACHE.clear()
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    monkeypatch.setenv("WHATSAPP_WABA_ID", "1234567890123")
    calls = []

    async def fake_get(self, url, *, headers, params):
        calls.append((url, params.get("name"), params.get("fields")))
        assert headers.get("Authorization") == "Bearer " + cfg.access_token
        return httpx.Response(200, json={"data": [{
            "name": TEMPLATE_NAME,
            "language": "it",
            "status": status,
            "category": category,
            "components": [{"type": "BODY", "text": body}],
        }]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    actual = await approval_status(cfg, use_cache=False)
    assert actual == expected
    assert calls and "/1234567890123/message_templates" in calls[0][0]
    assert "category" in calls[0][2]


@pytest.mark.asyncio
async def test_unavailable_meta_validation_fails_closed(cfg, monkeypatch):
    import httpx
    from whatsapp.template_approval import _CACHE, approval_status

    _CACHE.clear()
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    monkeypatch.setenv("WHATSAPP_WABA_ID", "1234567890123")

    async def fail_get(self, url, *, headers, params):
        return httpx.Response(403, json={"error": {"message": "private-token"}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fail_get)
    assert await approval_status(cfg, use_cache=False) == "unverified"



@pytest.mark.asyncio
async def test_template_with_required_media_header_is_not_approved_for_static_alerts(
    cfg, monkeypatch
):
    import httpx
    from whatsapp.template_approval import _CACHE, approval_status

    _CACHE.clear()
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    monkeypatch.setenv("WHATSAPP_WABA_ID", "1234567890123")

    async def fake_get(self, url, *, headers, params):
        return httpx.Response(200, json={"data": [{
            "name": TEMPLATE_NAME,
            "language": "it",
            "status": "APPROVED", "category": "UTILITY",
            "components": [
                {"type": "HEADER", "format": "IMAGE"},
                {"type": "BODY", "text": "ORA ha un aggiornamento."},
            ],
        }]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    assert await approval_status(cfg, use_cache=False) == "requires_parameters"


@pytest.mark.asyncio
async def test_delayed_stop_revokes_consent_without_reopening_meta_window(cfg, monkeypatch):
    """STOP remains immediate, but a delayed worker cannot invent fresh activity."""
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    moment = datetime.now(timezone.utc)
    sent_at = moment - timedelta(hours=25)
    db = AsyncMongoMockClient().wa_delayed_signed_stop
    await linked(db, cfg, last_at=moment - timedelta(hours=30))
    await set_opt_in(db, OWNER, True)
    svc = WhatsAppService(db, cfg)

    async def do_not_call_ai(self, *args, **kwargs):
        pytest.fail("STOP must revoke consent without consulting the AI Core")

    monkeypatch.setattr(AICoreOrchestrator, "start", do_not_call_ai)
    monkeypatch.setattr(AICoreOrchestrator, "message", do_not_call_ai)
    msg = {
        "id": "wamid.delayed.signed.stop.111",
        "from": PHONE,
        "type": "text",
        "text": "STOP",
        "sent_at": int(sent_at.timestamp()),
    }
    assert await svc.persist_incoming(msg)
    before = await db.whatsapp_links.find_one({"user_id": OWNER})
    assert not in_service_window(before)

    queued = await db.whatsapp_inbox.find_one({})
    response, owner = await svc.prepare_reply(queued)
    assert owner == OWNER
    assert "disattivati" in response.lower()
    after = await db.whatsapp_links.find_one({"user_id": OWNER})
    assert after["notifications_enabled"] is False
    assert "opted_in_at" not in after
    assert not in_service_window(after)
    recorded = after["last_inbound_at"].replace(tzinfo=timezone.utc).timestamp()
    assert abs(recorded - sent_at.timestamp()) <= 1

    # Replayed signed callbacks must not open another service window.
    assert not await svc.persist_incoming(msg)
    assert not in_service_window(await db.whatsapp_links.find_one({"user_id": OWNER}))


@pytest.mark.asyncio
async def test_signed_message_time_does_not_reopen_expired_meta_window(cfg, monkeypatch):
    """A delayed worker cannot claim a message was received just now."""
    from whatsapp.service import _sender_message_moment

    moment = datetime.now(timezone.utc)
    old = moment - timedelta(hours=25)
    assert _sender_message_moment({"sent_at": int(old.timestamp())}, moment) <= old + timedelta(seconds=1)

    db = AsyncMongoMockClient().wa_sender_event_window
    await linked(db, cfg, last_at=moment - timedelta(hours=30))
    svc = WhatsAppService(db, cfg)
    msg = {
        "id": "wamid.delayed.signed.sender.111",
        "from": PHONE,
        "type": "text",
        "text": "Portami al Colosseo",
        "sent_at": int(old.timestamp()),
    }
    assert await svc.persist_incoming(msg)
    link = await db.whatsapp_links.find_one({"user_id": OWNER})
    assert not in_service_window(link)
    assert abs(link["last_inbound_at"].replace(tzinfo=timezone.utc).timestamp() - old.timestamp()) <= 1

    async def simple_answer(self, user_id, linked, body, incoming_id, **kwargs):
        return "Risposta tecnica al messaggio."
    monkeypatch.setattr(WhatsAppService, "_answer_ai", simple_answer)
    item = await db.whatsapp_inbox.find_one({})
    response, owner = await svc.prepare_reply(item)
    assert owner == OWNER
    assert response == "Risposta tecnica al messaggio."
    # The application worker performed work now, but Meta's sender window
    # still started 25 hours ago and must not be extended by that work.
    assert not in_service_window(await db.whatsapp_links.find_one({"user_id": OWNER}))

    assert not await svc.persist_incoming(msg)
    assert not in_service_window(await db.whatsapp_links.find_one({"user_id": OWNER}))


def test_parsed_sender_event_time_is_bounded_and_absent_is_not_invented():
    from whatsapp.cloud import iter_inbound_messages

    def webhook(timestamp):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "12345678909876"},
                "messages": [{
                    "id": "wamid.timestamp.signed.111",
                    "from": PHONE, "type": "text",
                    "text": {"body": "Ciao"},
                    **({"timestamp": timestamp} if timestamp is not None else {}),
                }],
            }}]}],
        }
        return list(iter_inbound_messages(payload, "12345678909876"))[0]

    assert webhook("1791920000")["sent_at"] == 1791920000
    assert webhook("bogus")["sent_at"] is None
    assert webhook(None)["sent_at"] is None
    assert webhook("-1791920000")["sent_at"] is None


def test_informative_whatsapp_copy_has_a_fact_and_obeys_sensitive_boundary():
    item = plan()
    item.sensitivity = "personal"
    safe = public_copy(item)
    assert "Spedizione in consegna" in safe
    assert "Il corriere ha confermato" in safe
    assert "Private expanded" not in safe
    expanded = public_copy(item, detailed=True)
    assert "Private expanded title" in expanded
    assert "Private expanded details" in expanded
    item.sensitivity = "private"
    assert public_copy(item) is None  # private needs its own explicit opt-in

    item.words.public_title = "Un aggiornamento importante"
    item.words.public_body = "Apri ORA per i dettagli."
    assert public_copy(item) is None
    assert "Private expanded" in public_copy(item, detailed=True)
    item.words.title = ""
    item.words.body = ""
    assert public_copy(item, detailed=True) is None


@pytest.mark.asyncio
async def test_whatsapp_details_need_independent_explicit_consent_and_reset_on_stop(cfg):
    db = AsyncMongoMockClient().wa_private_detail_consent
    await linked(db, cfg)
    with pytest.raises(ValueError, match="whatsapp_alerts_not_enabled"):
        await set_detail_preference(db, OWNER, True)
    await set_opt_in(db, OWNER, True)
    assert (await WhatsAppService(db, cfg).status(OWNER))["notifications_detail_enabled"] is False
    assert (await set_detail_preference(db, OWNER, True))["notifications_detail_enabled"] is True
    state = await db.whatsapp_links.find_one({"user_id": OWNER})
    assert state["details_opt_in_source"] == "authenticated_ora_app"
    assert (await WhatsAppService(db, cfg).status(OWNER))["notifications_detail_enabled"] is True
    await set_opt_in(db, OWNER, False)
    state = await db.whatsapp_links.find_one({"user_id": OWNER})
    assert state["notifications_detail_enabled"] is False
    assert "details_opted_in_at" not in state
    await set_opt_in(db, OWNER, True)
    assert (await WhatsAppService(db, cfg).status(OWNER))["notifications_detail_enabled"] is False
    with pytest.raises(ValueError, match="whatsapp_not_linked"):
        await set_detail_preference(db, OTHER, True)


@pytest.mark.asyncio
async def test_private_alert_not_sent_until_detail_consent_when_public_copy_is_generic(cfg):
    db = AsyncMongoMockClient().wa_detail_not_generic
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    item = plan()
    item.sensitivity = "private"
    item.words.public_title = "Un aggiornamento importante"
    item.words.public_body = "Apri ORA per i dettagli."
    assert not await enqueue(db, OWNER, item)
    assert await db.whatsapp_alert_outbox.count_documents({}) == 0
    await set_detail_preference(db, OWNER, True)
    assert await enqueue(db, OWNER, item)
    encrypted = await db.whatsapp_alert_outbox.find_one({})
    assert "Private expanded" not in str(encrypted)
    assert "Private expanded" in cfg.decrypt(encrypted["copy_enc"])


@pytest.mark.asyncio
async def test_detail_revoked_before_send_never_replays_queued_private_text(cfg, monkeypatch):
    from delivery.service import DeliveryService

    db = AsyncMongoMockClient().wa_detail_revoked_before_transport
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    await set_detail_preference(db, OWNER, True)
    item = plan()
    item.sensitivity = "personal"
    await db.delivery_plans.insert_one(item.model_dump())
    assert await enqueue(db, OWNER, item)
    await set_detail_preference(db, OWNER, False)

    async def source(self, owner, candidate):
        assert owner == OWNER and candidate.id == item.id
        return SimpleNamespace(status="active")
    async def not_muted(self, *_):
        return False
    sent = []
    async def fake_send(self, recipient, *, message="", template=None):
        sent.append(message)
        return "wamid.synthetic_redacted"

    monkeypatch.setattr(DeliveryService, "_current_subject_for_plan", source)
    monkeypatch.setattr(DeliveryService, "_muted", not_muted)
    monkeypatch.setattr(CloudConfig, "send_proactive", fake_send)
    assert await AlertWorker(db, cfg).process_one()
    assert len(sent) == 1
    assert "Spedizione in consegna" in sent[0]
    assert "Private expanded" not in sent[0]


@pytest.mark.asyncio
async def test_outside_window_static_template_is_not_misrepresented_as_detailed(cfg, monkeypatch):
    from whatsapp import template_approval
    db = AsyncMongoMockClient().wa_static_template_rejection
    await linked(db, cfg, last_at=datetime.now(timezone.utc) - timedelta(days=2))
    await set_opt_in(db, OWNER, True)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    async def static_approved(*args, **kwargs):
        return "approved"
    monkeypatch.setattr(template_approval, "approval_status", static_approved)
    assert not await may_notify(db, OWNER)
    assert not await enqueue(db, OWNER, plan())


@pytest.mark.asyncio
async def test_dynamic_approved_meta_template_binds_informative_summary(cfg, monkeypatch):
    import httpx
    sent = []
    async def fake_post(self, url, *, headers, json):
        sent.append((url, json))
        return httpx.Response(200, json={"messages": [{"id": "wamid.synthetic_realshape"}]})
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    mid = await cfg.send_proactive(
        PHONE,
        template=(TEMPLATE_NAME, "it",
                  "*ORA — aggiornamento*\\nSpedizione in consegna oggi"),
    )
    assert mid == "wamid.synthetic_realshape"
    assert len(sent) == 1
    payload = sent[0][1]
    assert payload["type"] == "template"
    assert payload["template"]["components"] == [{
        "type": "body", "parameters": [{
            "type": "text",
            "text": "*ORA — aggiornamento*\\nSpedizione in consegna oggi",
        }]
    }]
    with pytest.raises(ValueError, match="invalid_template_detail_parameter"):
        await cfg.send_proactive(PHONE, template=(TEMPLATE_NAME, "it", "{{unexpected}}"))
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_template_with_two_variables_or_button_variable_fails_closed(cfg, monkeypatch):
    import httpx
    from whatsapp.template_approval import _CACHE, approval_status
    _CACHE.clear()
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    monkeypatch.setenv("WHATSAPP_WABA_ID", "1234567890123")
    components = [{"type": "BODY", "text": "ORA: {{1}} ({{2}})"}]

    async def fake_get(self, url, *, headers, params):
        return httpx.Response(200, json={"data": [{
            "name": TEMPLATE_NAME, "language": "it",
            "status": "APPROVED", "category": "UTILITY",
            "components": components,
        }]})
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    assert await approval_status(cfg, use_cache=False) == "requires_parameters"
    components[:] = [
        {"type": "BODY", "text": "ORA: {{1}}"},
        {"type": "BUTTONS", "buttons": [{"type": "URL", "url": "https://example.com/{{2}}"}]},
    ]
    assert await approval_status(cfg, use_cache=False) == "requires_parameters"
    components[:] = [{"type": "BODY", "text": TEMPLATE_BODY}]
    assert await approval_status(cfg, use_cache=False) == "approved_dynamic"


@pytest.mark.asyncio
async def test_private_copy_cancelled_if_detail_consent_removed_before_send(cfg, monkeypatch):
    from delivery.service import DeliveryService
    db = AsyncMongoMockClient().wa_private_optout_pending
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    await set_detail_preference(db, OWNER, True)
    item = plan()
    item.sensitivity = "private"
    await db.delivery_plans.insert_one(item.model_dump())
    assert await enqueue(db, OWNER, item)
    await set_detail_preference(db, OWNER, False)

    async def source(self, owner, candidate):
        return SimpleNamespace(status="active")
    async def not_muted(self, *_):
        return False
    async def never_send(*args, **kwargs):
        pytest.fail("Revoked consent must not leak private copy via Meta")
    monkeypatch.setattr(DeliveryService, "_current_subject_for_plan", source)
    monkeypatch.setattr(DeliveryService, "_muted", not_muted)
    monkeypatch.setattr(CloudConfig, "send_proactive", never_send)
    assert await AlertWorker(db, cfg).process_one()
    row = await db.whatsapp_alert_outbox.find_one({})
    assert row["status"] == "cancelled"
    assert row["failure_code"] == "no_informative_copy"


def test_delivery_lock_screen_never_falls_back_to_expanded_private_copy():
    from delivery.service import _lockscreen_copy_for
    item = plan()
    item.words.public_title = ""
    item.words.public_body = ""
    item.sensitivity = "private"
    locked = _lockscreen_copy_for(item)
    assert locked["title"] == "Avviso riservato di ORA"
    assert locked["body"] == "Apri ORA per i dettagli."
    assert "Private expanded" not in str(locked)
    item.sensitivity = "personal"
    assert "Private expanded" not in str(_lockscreen_copy_for(item))
    item.sensitivity = "ordinary"
    assert _lockscreen_copy_for(item)["title"] == item.words.title


def test_recurring_template_parameter_keeps_the_fact_not_the_ora_heading():
    item = plan()
    copy = public_copy(item)
    detail = recurring_template_detail(copy)
    assert detail == "Spedizione in consegna. Il corriere ha confermato la consegna per oggi"
    assert "ORA — aggiornamento" not in detail
    assert recurring_template_detail("*ORA — aggiornamento*") is None
    assert recurring_template_detail("*ORA — aggiornamento*\\n{{malicious}}") is None


def test_recurring_meta_template_review_payload_is_specific_and_sampled():
    payload = review_payload()
    assert payload["name"] == TEMPLATE_NAME
    assert payload["language"] == TEMPLATE_LANGUAGE
    assert payload["category"] == "UTILITY"
    assert payload["allow_category_change"] is False
    assert len(payload["components"]) == 1
    body = payload["components"][0]
    assert body["type"] == "BODY"
    assert body["text"] == TEMPLATE_BODY
    assert body["text"].count("{{1}}") == 1
    assert not body["text"].startswith("{{1}}")
    assert not body["text"].endswith("{{1}}")
    assert body["example"]["body_text"] == [[EXAMPLE_TEXT]]
    assert "telefono" not in str(payload).lower()
    assert "account" not in str(payload).lower()


def test_template_name_without_reviewed_scope_cannot_activate_outreach(cfg, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    assert template_settings() is None
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", "all_ai_updates")
    assert template_settings() is None
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    assert template_settings() == (TEMPLATE_NAME, TEMPLATE_LANGUAGE)


@pytest.mark.asyncio
async def test_nonrecurring_source_never_uses_approved_recurring_template(cfg, monkeypatch):
    from whatsapp import template_approval
    db = AsyncMongoMockClient().wa_scope_admission
    await linked(db, cfg, last_at=datetime.now(timezone.utc) - timedelta(days=2))
    await set_opt_in(db, OWNER, True)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)

    async def approved(*_args, **_kwargs):
        return "approved_dynamic"
    monkeypatch.setattr(template_approval, "approval_status", approved)
    assert await may_notify(db, OWNER)
    item = plan()
    await db.opportunities.insert_one({
        "id": item.source_id, "owner_id": OWNER,
        "status": "active", "source_context": "financial_update",
    })
    assert not await enqueue(db, OWNER, item)
    assert await db.whatsapp_alert_outbox.count_documents({}) == 0


@pytest.mark.asyncio
async def test_queued_unrelated_alert_never_crosses_meta_scope_after_window_expires(
    cfg, monkeypatch,
):
    from delivery.service import DeliveryService

    db = AsyncMongoMockClient().wa_scope_window_close
    await linked(db, cfg)
    await set_opt_in(db, OWNER, True)
    item = plan()
    await db.delivery_plans.insert_one(item.model_dump())
    assert await enqueue(db, OWNER, item)
    await db.whatsapp_links.update_one(
        {"user_id": OWNER},
        {"$set": {"last_inbound_at": datetime.now(timezone.utc) - timedelta(days=2)}},
    )
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)

    async def current(self, uid, requested_plan):
        assert uid == OWNER
        return SimpleNamespace(status="active", source_context="financial_update")

    async def not_muted(self, *_):
        return False

    async def never_send(*_args, **_kwargs):
        pytest.fail("Non-recurring details must never go into recurring Utility template")

    monkeypatch.setattr(DeliveryService, "_current_subject_for_plan", current)
    monkeypatch.setattr(DeliveryService, "_muted", not_muted)
    monkeypatch.setattr(CloudConfig, "send_proactive", never_send)
    assert await AlertWorker(db, cfg).process_one()
    row = await db.whatsapp_alert_outbox.find_one({})
    assert row["status"] == "cancelled"
    assert row["failure_code"] == "template_scope_unsupported"


@pytest.mark.asyncio
async def test_operator_submission_requires_explicit_confirm_and_real_not_found(
    cfg, monkeypatch,
):
    import httpx
    from whatsapp.template_approval import _CACHE

    _CACHE.clear()
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    monkeypatch.setenv("WHATSAPP_WABA_ID", "1234567890123")
    seen = []

    async def get_template(self, url, *, headers, params):
        assert headers["Authorization"] == "Bearer " + cfg.access_token
        assert url.endswith("/1234567890123/message_templates")
        return httpx.Response(200, json={"data": []})

    async def create_template(self, url, *, headers, json):
        seen.append(json)
        assert headers["Authorization"] == "Bearer " + cfg.access_token
        return httpx.Response(200, json={"id": "123456789123", "status": "PENDING"})

    monkeypatch.setattr(httpx.AsyncClient, "get", get_template)
    monkeypatch.setattr(httpx.AsyncClient, "post", create_template)
    with pytest.raises(ValueError, match="explicit_review_confirmation_required"):
        await request_review()
    assert not seen
    result = await request_review(confirm=True)
    assert result == {"requested": True, "template": TEMPLATE_NAME, "status": "PENDING"}
    assert seen == [review_payload()]
    assert "Bearer" not in str(result)


@pytest.mark.asyncio
async def test_operator_does_not_resubmit_if_template_exists_or_meta_unknown(
    cfg, monkeypatch,
):
    import httpx
    from whatsapp.template_approval import _CACHE

    _CACHE.clear()
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_NAME", TEMPLATE_NAME)
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_SCOPE", TEMPLATE_SCOPE)
    monkeypatch.setenv("WHATSAPP_WABA_ID", "1234567890123")
    response = {"data": [{
        "name": TEMPLATE_NAME, "language": TEMPLATE_LANGUAGE,
        "status": "APPROVED", "category": "UTILITY",
        "components": [{"type": "BODY", "text": TEMPLATE_BODY}],
    }]}
    async def get_template(self, url, *, headers, params):
        return httpx.Response(200, json=response)
    async def never_post(*_args, **_kwargs):
        pytest.fail("No second template request for an already approved or uncertain state")

    monkeypatch.setattr(httpx.AsyncClient, "get", get_template)
    monkeypatch.setattr(httpx.AsyncClient, "post", never_post)
    result = await request_review(confirm=True)
    assert result["requested"] is False
    assert result["status"] == "approved_dynamic"
    response.clear()
    assert (await request_review(confirm=True))["status"] == "unverified"
