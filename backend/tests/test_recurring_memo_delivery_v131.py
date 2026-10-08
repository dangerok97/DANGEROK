"""V131: synthetic, device-closed birthday reminder delivery end-to-end.

Uses actual Memory/Memo/Opportunity/Delivery/Expo adapter and persistence.
The AI decision, environment permission observation and outbound Expo HTTP are
scripted. No real account, provider request or device receives a push.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from ambient.push import ExpoNotificationProvider, PushEndpointService
from delivery.admission import drain
from delivery.service import DeliveryService
from memos.service import RecurringMemoService
from opportunities.repository import OpportunityRepository

OWNER = "synthetic-reminder-owner"
TOKEN = "ExponentPushToken[synthetic-device-only]"


def push(now=None):
    return {
        "mode": "push", "timing": "at" if now else "now",
        "not_before": now,
        "reason_to_interrupt": "Questa ricorrenza è stata chiesta dall'utente.",
        "reason_to_open": "Il compleanno è salvato fra i ricordi.",
        "what_decided_the_mode": "Ricorrenza annuale richiesta esplicitamente.",
        "copy_intent": "Ricordare il giorno utile.",
        "confidence": "strong", "sensitivity": "ordinary",
        "requires_recheck": True,
        "copy": {
            "title": "Compleanno da ricordare",
            "body": "Oggi è il compleanno di una persona che hai salvato.",
            "public_title": "Ricorrenza da ricordare",
            "public_body": "Apri ORA per il promemoria.",
        },
    }


async def create_due_opportunity(db):
    await OpportunityRepository(db).ensure_indexes()
    service = RecurringMemoService(db)
    await service.ensure_indexes()
    moment = datetime.now(timezone.utc)
    local = moment.astimezone(ZoneInfo("Europe/Rome"))
    await db.memories.insert_one({
        "id": "mem_synthetic_today", "user_id": OWNER, "status": "active",
        "kind": "birthday", "statement": "Compleanno sintetico",
        "value": {"person": "Persona sintetica", "month": local.month,
                  "day": local.day},
    })
    saved = await service.save_annual(
        OWNER, memory_ref="mem_synthetic_today", category="birthday",
        label="Compleanno sintetico", person="Persona sintetica",
        month=local.month, day=local.day,
        timezone_name="Europe/Rome", remind_hour_local=0,
    )
    assert saved["ok"], saved
    await db.recurring_memos.update_one(
        {"id": saved["memo"]["id"]},
        {"$set": {"next_due_at": (moment - timedelta(minutes=1)).isoformat()}},
    )
    fired = await service.fire_due(now=moment)
    assert fired == {"due": 1, "raised": 1, "disabled": 0}
    opportunities = await db.opportunities.find({"owner_id": OWNER}).to_list(5)
    assert len(opportunities) == 1
    return opportunities[0], saved["memo"]["id"]


def install_scripted_gate(monkeypatch, db, *, allowed=True, answer=None):
    import delivery.context as context_module
    import delivery.provider as provider_module
    import delivery.reasoning as reasoning

    observed = {
        "app_state": "background",
        "can_be_notified": {"push": allowed},
        "they_muted_this_concern": False,
        "recent_interruptions": [],
    }
    context = AsyncMock(return_value=observed)
    judgement = AsyncMock(return_value=answer or push())
    provider = ExpoNotificationProvider(db)
    outbound = AsyncMock(return_value=[{"status": "ok", "id": "synthetic-ticket"}])
    monkeypatch.setattr(context_module, "build", context)
    monkeypatch.setattr(reasoning, "decide_delivery", judgement)
    monkeypatch.setattr(provider, "_post", outbound)
    monkeypatch.setattr(provider_module, "get_provider", lambda: provider)
    return context, judgement, outbound


@pytest.mark.asyncio
async def test_due_birthday_passes_real_delivery_policy_and_reaches_expo_adapter(monkeypatch):
    db = AsyncMongoMockClient().birthday_push_v131
    opportunity, memo_id = await create_due_opportunity(db)
    registration = await PushEndpointService(db).register(
        OWNER, token=TOKEN, device="synthetic-ios", platform="ios",
        permission_state="granted",
    )
    assert registration["ok"] and TOKEN not in str(registration)
    context, judgement, outbound = install_scripted_gate(monkeypatch, db)

    handled = await drain(db, owner_id=OWNER, limit=2)
    assert handled == 1
    judgement.assert_awaited_once()
    assert context.await_args.kwargs["app_state"] == "unknown"
    outbound.assert_awaited_once()
    request = outbound.await_args.args[0]
    assert len(request) == 1
    assert request[0]["to"] == TOKEN
    assert request[0]["title"] == "Ricorrenza da ricordare"
    assert request[0]["body"] == "Apri ORA per il promemoria."
    assert opportunity["id"] in request[0]["data"]["deep_link"]
    plan = await db.delivery_plans.find_one({"owner_id": OWNER})
    assert plan["status"] == "delivered"  # Expo-ticket accepted, NOT proof of phone display.
    assert plan["outcome"] == "delivered"
    assert (await db.recurring_memos.find_one({"id": memo_id}))["status"] == "active"
    assert await drain(db, owner_id=OWNER, limit=2) == 0
    assert outbound.await_count == 1
    assert await RecurringMemoService(db).fire_due() == {
        "due": 0, "raised": 0, "disabled": 0,
    }


@pytest.mark.asyncio
async def test_forgetting_birthday_after_opportunity_prevents_pending_notification(monkeypatch):
    db = AsyncMongoMockClient().birthday_forgotten_delivery_v131
    opportunity, _ = await create_due_opportunity(db)
    await PushEndpointService(db).register(
        OWNER, token=TOKEN, device="synthetic-ios",
    )
    _, judgement, outbound = install_scripted_gate(monkeypatch, db)
    await db.memories.update_one(
        {"id": "mem_synthetic_today", "user_id": OWNER},
        {"$set": {"status": "forgotten"}},
    )
    assert await drain(db, owner_id=OWNER, limit=1) == 1
    judgement.assert_not_awaited()
    outbound.assert_not_awaited()
    assert await db.delivery_plans.count_documents({"owner_id": OWNER}) == 0
    opportunity_row = await db.opportunities.find_one({"id": opportunity["id"]})
    assert opportunity_row["delivery_review_state"] == "settled"


@pytest.mark.asyncio
async def test_correction_after_notification_plan_cancels_before_sending(monkeypatch):
    db = AsyncMongoMockClient().birthday_stale_plan_v131
    opportunity, _ = await create_due_opportunity(db)
    await PushEndpointService(db).register(OWNER, token=TOKEN, device="synthetic-ios")
    due_later = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _, judgement, outbound = install_scripted_gate(
        monkeypatch, db, answer=push(due_later),
    )
    result = await DeliveryService(db).evaluate(OWNER, opportunity["id"])
    assert result.mode == "push" and result.plan is not None
    assert outbound.await_count == 0
    await db.memories.update_one(
        {"id": "mem_synthetic_today", "user_id": OWNER},
        {"$set": {"value.day": 1 if datetime.now(ZoneInfo("Europe/Rome")).day != 1 else 2}},
    )
    await db.delivery_plans.update_one(
        {"id": result.plan.id},
        {"$set": {"not_before": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}},
    )
    delivered = await DeliveryService(db).deliver_due(OWNER)
    assert delivered["sent"] == 0 and delivered["cancelled"] == 1
    assert judgement.await_count == 1
    outbound.assert_not_awaited()
    plan = await db.delivery_plans.find_one({"id": result.plan.id})
    assert plan["status"] == "cancelled"


@pytest.mark.asyncio
async def test_denied_notification_permission_cannot_call_expo(monkeypatch):
    db = AsyncMongoMockClient().birthday_denied_v131
    await create_due_opportunity(db)
    await PushEndpointService(db).register(OWNER, token=TOKEN, device="synthetic-ios")
    _, judgement, outbound = install_scripted_gate(monkeypatch, db, allowed=False)
    assert await drain(db, owner_id=OWNER, limit=1) == 1
    judgement.assert_awaited_once()
    outbound.assert_not_awaited()
    saved = await db.delivery_plans.find_one({"owner_id": OWNER})
    assert saved["status"] == "held"


@pytest.mark.asyncio
async def test_other_persons_registered_device_cannot_receive_birthday(monkeypatch):
    db = AsyncMongoMockClient().birthday_other_owner_v131
    await create_due_opportunity(db)
    await PushEndpointService(db).register(
        "other-person", token=TOKEN, device="synthetic-ios",
    )
    _, _, outbound = install_scripted_gate(monkeypatch, db)
    assert await drain(db, owner_id=OWNER, limit=1) == 1
    outbound.assert_not_awaited()
    saved = await db.delivery_plans.find_one({"owner_id": OWNER})
    assert saved["status"] == "held"
