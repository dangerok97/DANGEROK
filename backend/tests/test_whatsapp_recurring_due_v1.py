"""A user-requested recurring date must reach opted-in WhatsApp without Expo.

Provider and phones are synthetic; these tests never send a real message.
Use today's local anniversary to exercise the same recovery path as production.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from cryptography.fernet import Fernet
from mongomock_motor import AsyncMongoMockClient

from memos.service import RecurringMemoService
from whatsapp.alerts import AlertWorker, enqueue, alert_id, set_opt_in
from whatsapp.cloud import CloudConfig
from whatsapp.recurring_delivery import (
    recurring_key, enqueue_due_recurring, reconcile_recent_recurring,
    retry_failed_recurring_once,
)
from whatsapp.template_provisioning import TEMPLATE_NAME, TEMPLATE_LANGUAGE

OWNER = "synthetic_annual_whatsapp_owner"
PHONE = "393331112233"


@pytest.fixture
def cfg(monkeypatch):
    for name, value in {
        "WHATSAPP_APP_SECRET": "synthetic-secret",
        "WHATSAPP_VERIFY_TOKEN": "synthetic-verify",
        "WHATSAPP_ACCESS_TOKEN": "synthetic-token",
        "WHATSAPP_PHONE_NUMBER_ID": "12345678909876",
        "WHATSAPP_DATA_KEY": Fernet.generate_key().decode(),
        "WHATSAPP_ALERT_TEMPLATE_NAME": TEMPLATE_NAME,
        "WHATSAPP_ALERT_TEMPLATE_LANGUAGE": TEMPLATE_LANGUAGE,
        "WHATSAPP_ALERT_TEMPLATE_SCOPE": "recurring_memo",
        "WHATSAPP_WABA_ID": "1234567890123",
    }.items():
        monkeypatch.setenv(name, value)
    return CloudConfig.load()


async def make_due(db, cfg, *, allow_details=True, link=True):
    service = RecurringMemoService(db)
    await service.ensure_indexes()
    moment = datetime.now(timezone.utc)
    local = moment.astimezone(ZoneInfo("Europe/Rome"))
    await db.memories.insert_one({
        "id": "mem_anniversary_synthetic",
        "user_id": OWNER, "status": "active",
        "kind": "annual_memo",
        "statement": "Il giorno di prova è il mio anniversario sintetico",
        "value": {"month": local.month, "day": local.day},
    })
    if link:
        await db.whatsapp_links.insert_one({
            "user_id": OWNER, "phone_hash": cfg.fingerprint("phone", PHONE),
            "phone_enc": cfg.encrypt(PHONE),
            "notifications_enabled": True, "opted_in_at": moment,
            "notifications_detail_enabled": allow_details,
            **({"details_opted_in_at": moment} if allow_details else {}),
            "last_inbound_at": moment - timedelta(hours=30),
        })
    saved = await service.save_annual(
        OWNER, memory_ref="mem_anniversary_synthetic",
        category="annual_memo", label="Anniversario sintetico",
        person="", month=local.month, day=local.day,
        timezone_name="Europe/Rome", remind_hour_local=0,
    )
    assert saved["ok"]
    await db.recurring_memos.update_one(
        {"id": saved["memo"]["id"]},
        {"$set": {"next_due_at": (moment - timedelta(minutes=1)).isoformat()}},
    )
    fired = await service.fire_due(now=moment)
    assert fired == {"due": 1, "raised": 1, "disabled": 0}
    rows = await db.opportunities.find({"owner_id": OWNER}).to_list(5)
    assert len(rows) == 1
    return rows[0]


@pytest.mark.asyncio
async def test_due_anniversary_enqueues_even_without_expo_or_ai_delivery_plan(cfg):
    db = AsyncMongoMockClient().wa_direct_due_no_expo
    event = await make_due(db, cfg)
    assert await db.delivery_plans.count_documents({}) == 0
    rows = await db.whatsapp_alert_outbox.find({}).to_list(5)
    assert len(rows) == 1
    assert rows[0]["source_kind"] == "recurring_due"
    assert rows[0]["source_id"] == event["id"]
    assert rows[0]["_id"] == alert_id(OWNER, recurring_key(event["id"]))
    assert rows[0]["status"] == "ready"
    assert "Anniversario sintetico" not in str(rows[0])
    assert "Anniversario sintetico" in cfg.decrypt(rows[0]["copy_enc"])


@pytest.mark.asyncio
async def test_due_anniversary_uses_approved_template_outside_24h(cfg, monkeypatch):
    from whatsapp import template_approval
    db = AsyncMongoMockClient().wa_direct_due_meta_template
    await make_due(db, cfg)
    calls = []
    async def approved(*_args, **_kwargs):
        return "approved_dynamic"
    async def fake_send(self, recipient, *, message="", template=None):
        calls.append((recipient, message, template))
        return "wamid.synthetic_due_recurring"
    monkeypatch.setattr(template_approval, "approval_status", approved)
    monkeypatch.setattr(CloudConfig, "send_proactive", fake_send)
    assert await AlertWorker(db, cfg).process_one()
    assert len(calls) == 1
    recipient, message, template = calls[0]
    assert recipient == PHONE
    assert message == ""
    assert template[:2] == (TEMPLATE_NAME, TEMPLATE_LANGUAGE)
    assert "Anniversario sintetico" in template[2]
    assert "{{" not in template[2]
    row = await db.whatsapp_alert_outbox.find_one({})
    assert row["status"] == "accepted"  # accepted by mock Meta, not phone delivery
    assert row["kind"] == "approved_template"
    assert not await AlertWorker(db, cfg).process_one()


@pytest.mark.asyncio
async def test_due_reminder_privacy_and_unlinked_owner_never_admitted(cfg):
    db = AsyncMongoMockClient().wa_direct_due_no_consent
    event = await make_due(db, cfg, allow_details=False)
    assert await db.whatsapp_alert_outbox.count_documents({}) == 0
    assert not await enqueue_due_recurring(db, event)
    await db.whatsapp_links.delete_many({})
    assert not await enqueue_due_recurring(db, event)
    assert await db.whatsapp_alert_outbox.count_documents({}) == 0


@pytest.mark.asyncio
async def test_recovery_backfills_todays_unqueued_due_once(cfg):
    db = AsyncMongoMockClient().wa_due_after_old_backend
    event = await make_due(db, cfg)
    await db.whatsapp_alert_outbox.delete_many({})  # simulate old build
    assert await reconcile_recent_recurring(db) == 1
    assert await reconcile_recent_recurring(db) == 0
    row = await db.whatsapp_alert_outbox.find_one({})
    assert row["source_id"] == event["id"]
    assert row["status"] == "ready"


@pytest.mark.asyncio
async def test_revoked_memory_cancels_pending_due_without_provider(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_direct_due_forgotten
    await make_due(db, cfg)
    await db.memories.update_one(
        {"id": "mem_anniversary_synthetic", "user_id": OWNER},
        {"$set": {"status": "forgotten"}},
    )
    async def no_send(*_args, **_kwargs):
        pytest.fail("A forgotten memory must not send a reminder")
    monkeypatch.setattr(CloudConfig, "send_proactive", no_send)
    assert await AlertWorker(db, cfg).process_one()
    row = await db.whatsapp_alert_outbox.find_one({})
    assert row["status"] == "cancelled"
    assert row["failure_code"] == "source_closed_or_muted"


@pytest.mark.asyncio
async def test_stop_cancels_queued_direct_annual_alert(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_direct_due_stop
    await make_due(db, cfg)
    await set_opt_in(db, OWNER, False)
    row = await db.whatsapp_alert_outbox.find_one({})
    assert row["status"] == "cancelled"
    assert await db.whatsapp_links.find_one({"user_id": OWNER, "notifications_enabled": False})
    assert not await AlertWorker(db, cfg).process_one()


@pytest.mark.asyncio
async def test_canonical_plan_cannot_duplicate_direct_due_event(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_direct_due_dedupe
    event = await make_due(db, cfg)
    from delivery.models import DeliveryPlan, PushCopy
    plan = DeliveryPlan(
        id="dp_synthetic_canonical",
        owner_id=OWNER, source_type="opportunity", source_id=event["id"],
        mode="push", sensitivity="ordinary",
        words=PushCopy(public_title="Ricorrenza di oggi",
                       public_body="Un anniversario salvato"),
    )
    from whatsapp import template_approval
    async def approved(*_args, **_kwargs):
        return "approved_dynamic"
    monkeypatch.setattr(template_approval, "approval_status", approved)
    assert not await enqueue(db, OWNER, plan)
    assert await db.whatsapp_alert_outbox.count_documents({}) == 1


async def mark_failed_receipt(db, *, kind="approved_template"):
    now = datetime.now(timezone.utc)
    await db.whatsapp_alert_outbox.update_one(
        {"owner_id": OWNER, "source_kind": "recurring_due"},
        {"$set": {
            "status": "failed", "kind": kind,
            "wamid": "wamid.synthetic_failure_001",
            "meta_status_at": now, "failure_code": "meta_delivery_failed",
        }},
    )


@pytest.mark.asyncio
async def test_confirmed_failed_reminder_retry_is_once_and_preserves_original(cfg, monkeypatch):
    from whatsapp import template_approval
    db = AsyncMongoMockClient().wa_manual_one_failure_retry
    event = await make_due(db, cfg)
    await mark_failed_receipt(db)

    async def approved(*_args, **_kwargs):
        return "approved_dynamic"

    monkeypatch.setattr(template_approval, "approval_status", approved)
    first = await retry_failed_recurring_once(db, OWNER)
    assert first == {"queued": True, "status": "queued"}
    second = await retry_failed_recurring_once(db, OWNER)
    assert second == {"queued": False, "reason": "retry_already_requested"}

    originals = await db.whatsapp_alert_outbox.find({"owner_id": OWNER}).to_list(5)
    assert len(originals) == 2
    old = next(x for x in originals if x["status"] == "failed")
    retry = next(x for x in originals if x["status"] == "ready")
    assert old["wamid"] == "wamid.synthetic_failure_001"
    assert retry["source_id"] == event["id"]
    assert retry["retry_kind"] == "owner_confirmed_failed_once"
    assert retry["force_template"] is True
    assert "wamid" not in retry
    assert retry["phone_hash"] == old["phone_hash"]
    assert cfg.decrypt(retry["copy_enc"]).startswith("*ORA — aggiornamento*")
    assert await retry_failed_recurring_once(db, "not-this-owner") == {
        "queued": False, "reason": "no_confirmed_failed_reminder",
    }


@pytest.mark.asyncio
async def test_manual_retry_forces_template_even_when_24h_window_reopens(cfg, monkeypatch):
    from whatsapp import template_approval
    db = AsyncMongoMockClient().wa_force_template_on_retry
    await make_due(db, cfg)
    await mark_failed_receipt(db)

    async def approved(*_args, **_kwargs):
        return "approved_dynamic"

    monkeypatch.setattr(template_approval, "approval_status", approved)
    assert (await retry_failed_recurring_once(db, OWNER))["queued"] is True
    await db.whatsapp_links.update_one(
        {"user_id": OWNER},
        {"$set": {"last_inbound_at": datetime.now(timezone.utc)}},
    )
    sent = []

    async def send(self, recipient, *, message="", template=None):
        sent.append((recipient, message, template))
        return "wamid.synthetic_retry_sent"

    monkeypatch.setattr(CloudConfig, "send_proactive", send)
    assert await AlertWorker(db, cfg).process_one()
    assert len(sent) == 1
    assert sent[0][0] == PHONE
    assert sent[0][1] == ""
    assert sent[0][2][:2] == (TEMPLATE_NAME, TEMPLATE_LANGUAGE)
    assert "Anniversario sintetico" in sent[0][2][2]
    retry = await db.whatsapp_alert_outbox.find_one({
        "owner_id": OWNER, "retry_kind": "owner_confirmed_failed_once",
    })
    assert retry["status"] == "accepted"
    assert (await db.whatsapp_alert_outbox.find_one({
        "owner_id": OWNER, "status": "failed",
    }))["wamid"] == "wamid.synthetic_failure_001"


@pytest.mark.asyncio
async def test_retry_rejected_when_meta_has_not_confirmed_failure(cfg, monkeypatch):
    db = AsyncMongoMockClient().wa_uncertain_no_retry
    await make_due(db, cfg)
    await db.whatsapp_alert_outbox.update_one(
        {"owner_id": OWNER},
        {"$set": {"status": "acceptance_unknown", "kind": "approved_template"}},
    )
    assert await retry_failed_recurring_once(db, OWNER) == {
        "queued": False, "reason": "no_confirmed_failed_reminder",
    }
    assert await db.whatsapp_alert_outbox.count_documents({}) == 1


@pytest.mark.asyncio
async def test_retry_rechecks_memory_and_owner_consent(cfg, monkeypatch):
    from whatsapp import template_approval
    db = AsyncMongoMockClient().wa_retry_privacy_fence
    await make_due(db, cfg)
    await mark_failed_receipt(db)

    async def approved(*_args, **_kwargs):
        return "approved_dynamic"

    monkeypatch.setattr(template_approval, "approval_status", approved)
    await db.memories.update_one(
        {"id": "mem_anniversary_synthetic", "user_id": OWNER},
        {"$set": {"status": "forgotten"}},
    )
    result = await retry_failed_recurring_once(db, OWNER)
    assert result == {"queued": False, "reason": "reminder_not_current"}
    await db.memories.update_one(
        {"id": "mem_anniversary_synthetic", "user_id": OWNER},
        {"$set": {"status": "active"}},
    )
    await db.whatsapp_links.update_one(
        {"user_id": OWNER},
        {"$set": {"notifications_detail_enabled": False},
         "$unset": {"details_opted_in_at": ""}},
    )
    result = await retry_failed_recurring_once(db, OWNER)
    assert result == {"queued": False, "reason": "consent_or_link_changed"}
    assert await db.whatsapp_alert_outbox.count_documents({}) == 1
