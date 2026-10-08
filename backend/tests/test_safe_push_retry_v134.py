"""v134: a refused Expo push gets bounded re-judgement, never a blind resend.

All owners, tokens, opportunity facts and notification tickets are synthetic.
No HTTP or user/device notification is sent. The actual Delivery policy,
Ambient wake queue and Expo adapter are used with a scripted provider response.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
import os
import uuid
from urllib.parse import urlsplit
from unittest.mock import AsyncMock

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from ambient.push import ExpoNotificationProvider, PushEndpointService
from ambient.repository import AmbientRepository
from ambient.runtime import tick
from delivery.service import DeliveryService
from delivery.transport_retry import (
    MAX_TRANSPORT_RETRIES,
    backoff_seconds,
    recover_unscheduled_retries,
)
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository

OWNER = "synthetic-retry-owner"
TOKEN = "ExpoPushToken[synthetic-retry-iphone]"

@asynccontextmanager
async def real_mongo_queue():
    """Strictly synthetic DB, using the actual Motor/Mongo wake claim path.

    mongomock-motor does not reproduce the real find_one_and_update claim
    behaviour for AmbientWake. Queue tests must use the real local Mongo
    provided by CI, with a guarded UUID database that cannot touch user data.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    url = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
    parsed = urlsplit(url)
    if (parsed.scheme != "mongodb" or parsed.hostname not in (
            "127.0.0.1", "localhost", "::1")
            or parsed.username or parsed.password or "," in parsed.netloc
            or parsed.path not in ("", "/") or parsed.fragment):
        raise RuntimeError("synthetic push test requires unauthenticated loopback Mongo")
    nonce = uuid.uuid4().hex
    name = "ora_push_retry_v134_" + uuid.uuid4().hex
    client = AsyncIOMotorClient(url)
    db = client[name]
    created = False
    try:
        await client.admin.command("ping")
        assert name not in await client.list_database_names()
        await db.test_owner.insert_one({"_id": "guard", "nonce": nonce})
        created = True
        yield db
    finally:
        if created:
            guard = await db.test_owner.find_one({"_id": "guard"})
            if name.startswith("ora_push_retry_v134_") and guard and guard.get("nonce") == nonce:
                await client.drop_database(name)
            else:
                raise AssertionError("synthetic database marker mismatch: cleanup refused")
        client.close()




def explicit_429():
    request = httpx.Request("POST", "https://exp.host/--/api/v2/push/send")
    response = httpx.Response(429, request=request)
    return httpx.HTTPStatusError("synthetic explicit rejection", request=request, response=response)


def uncertain_network_failure():
    request = httpx.Request("POST", "https://exp.host/--/api/v2/push/send")
    return httpx.ReadTimeout("synthetic ambiguous acceptance", request=request)


def push_decision():
    return {
        "mode": "push", "timing": "now",
        "reason_to_interrupt": "Un evento verificato richiede attenzione.",
        "reason_to_open": "ORA ha aggiornato il piano verificato.",
        "what_decided_the_mode": "La situazione è ancora attiva.",
        "confidence": "strong", "sensitivity": "ordinary",
        "requires_recheck": True,
        "copy": {
            "title": "Aggiornamento ORA", "body": "Apri per i dettagli.",
            "public_title": "Hai un aggiornamento",
            "public_body": "Apri ORA per vedere.",
        },
    }


async def setup(monkeypatch, name, *, valid_until=None, effect=None, db=None):
    from delivery import context as context_module
    from delivery import provider as provider_module
    from delivery import reasoning as reasoning_module

    db = db if db is not None else AsyncMongoMockClient()[name]
    await AmbientRepository(db).ensure_indexes()
    await OpportunityRepository(db).ensure_indexes()
    owner = OWNER
    opportunity = await OpportunityRepository(db).save(Opportunity(
        owner_id=owner, identity_key="synthetic:expo:retry",
        status="active", semantic_summary="Situazione sintetica da ricontrollare",
        why_it_matters="Verifica puntuale della disponibilità del provider",
        why_now="La scadenza è vicina", initiative="inform",
        valid_until=valid_until,
    ))
    registered = await PushEndpointService(db).register(
        owner, token=TOKEN, device="synthetic-iphone",
        platform="ios", permission_state="granted",
    )
    assert registered["ok"]
    context = AsyncMock(return_value={
        "app_state": "background", "can_be_notified": {"push": True},
        "they_muted_this_concern": False, "recent_interruptions": [],
    })
    judge = AsyncMock(return_value=push_decision())
    provider = ExpoNotificationProvider(db)
    outbound = AsyncMock(side_effect=(
        effect if effect is not None else [
            explicit_429(), [{"status": "ok", "id": "synthetic-ticket"}],
        ]
    ))
    monkeypatch.setattr(context_module, "build", context)
    monkeypatch.setattr(reasoning_module, "decide_delivery", judge)
    monkeypatch.setattr(provider_module, "get_provider", lambda: provider)
    monkeypatch.setattr(provider, "_post", outbound)
    return db, opportunity, judge, outbound


@pytest.mark.asyncio
async def test_explicit_http_429_schedules_one_durable_recheck_then_sends(monkeypatch):
    async with real_mongo_queue() as real_db:
        db, opportunity, judge, outbound = await setup(
            monkeypatch, "push_retry_429_v134",
            db=real_db,
        )
        response = await DeliveryService(db).evaluate(OWNER, opportunity.id)
        assert response.mode == "push" and response.plan is not None
        held = await DeliveryService(db).repo.get_plan(OWNER, response.plan.id)
        assert held.status == "held"
        assert held.transport_retry_attempts == 1
        assert held.transport_retry_due
        assert held.transport_retry_alarm_queued is True
        assert held.delivered_at is None
        wakes = await db.ambient_wakes.find({"owner_id": OWNER}).to_list(None)
        assert len(wakes) == 1 and wakes[0]["reason"] == "retry"
        assert wakes[0]["provenance"] == "technical_retry"
        assert wakes[0]["delivery_plan_id"] == held.id
        assert await DeliveryService(db).deliver_due(OWNER) == {
            "sent": 0, "cancelled": 0, "held": 1,
        }
        assert outbound.await_count == 1, "manual due cannot skip backoff"

        due = datetime.fromisoformat(held.transport_retry_due) + timedelta(seconds=2)
        assert await db.ambient_wakes.count_documents({
            "owner_id": OWNER,
            "status": "pending",
            "scheduled_for": {"$lte": due.isoformat()},
            "attempts": {"$lt": 5},
        }) == 1
        wake_result = await tick(db, now=due, limit=1)
        assert wake_result["completed"] == 1, {
            "result": wake_result,
            "wake": await db.ambient_wakes.find_one({"delivery_plan_id": held.id}, {"_id": 0}),
            "due": due.isoformat(),
            "plan": (await db.delivery_plans.find_one({"id": held.id}, {"_id": 0})),
        }
        finished = await DeliveryService(db).repo.get_plan(OWNER, held.id)
        assert finished.status == "delivered"
        assert finished.transport_retry_due is None
        assert finished.transport_retry_attempts == 1
        assert outbound.await_count == judge.await_count == 2
        assert await db.ambient_wakes.count_documents({"status": "completed"}) == 1


@pytest.mark.asyncio
async def test_uncertain_network_result_is_held_without_automatic_resend(monkeypatch):
    db, opportunity, _, outbound = await setup(
        monkeypatch, "push_retry_unknown_v134", effect=uncertain_network_failure()
    )
    result = await DeliveryService(db).evaluate(OWNER, opportunity.id)
    saved = await DeliveryService(db).repo.get_plan(OWNER, result.plan.id)
    assert saved.status == "held" and saved.transport_retry_due is None
    assert saved.transport_retry_attempts == 0
    assert await db.ambient_wakes.count_documents({}) == 0
    assert outbound.await_count == 1


@pytest.mark.asyncio
async def test_malformed_tickets_and_partial_acceptance_cannot_retry_whole_batch(monkeypatch):
    db, opportunity, _, outbound = await setup(
        monkeypatch, "push_retry_malformed_v134", effect=[[]]
    )
    result = await DeliveryService(db).evaluate(OWNER, opportunity.id)
    held = await DeliveryService(db).repo.get_plan(OWNER, result.plan.id)
    assert held.status == "held" and held.transport_retry_due is None
    assert await db.ambient_wakes.count_documents({}) == 0
    assert outbound.await_count == 1


@pytest.mark.asyncio
async def test_one_accepted_device_never_causes_whole_batch_retry(monkeypatch):
    db, opportunity, judge, outbound = await setup(
        monkeypatch, "push_retry_partial_v134",
        effect=[[{"status": "ok", "id": "accepted-iphone"},
                 {"status": "error", "details": {
                     "error": "DeviceNotRegistered",
                 }}]],
    )
    await PushEndpointService(db).register(
        OWNER, token="ExpoPushToken[synthetic-android]", device="synthetic-android",
        platform="android", permission_state="granted",
    )
    result = await DeliveryService(db).evaluate(OWNER, opportunity.id)
    stored = await DeliveryService(db).repo.get_plan(OWNER, result.plan.id)
    assert stored.status == "delivered"
    assert stored.transport_retry_due is None
    assert await db.ambient_wakes.count_documents({}) == 0
    assert outbound.await_count == judge.await_count == 1
    assert await db.expo_push_receipts.count_documents({}) == 1
    assert await db.push_endpoints.count_documents({"status": "disabled"}) == 1


@pytest.mark.asyncio
async def test_delivery_admission_restores_missing_retry_without_sending(monkeypatch):
    from delivery import admission
    from delivery.expo_receipts import ExpoReceiptAudit

    db, opportunity, _, outbound = await setup(
        monkeypatch, "push_retry_admission_v134",
    )
    result = await DeliveryService(db).evaluate(OWNER, opportunity.id)
    plan = await DeliveryService(db).repo.get_plan(OWNER, result.plan.id)
    await db.ambient_wakes.delete_many({"delivery_plan_id": plan.id})
    await db.delivery_plans.update_one(
        {"id": plan.id}, {"$set": {
            "transport_retry_due": (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            ).isoformat(),
            "transport_retry_alarm_queued": False,
        }},
    )
    patched_drain = AsyncMock(return_value=0)
    patched_receipts = AsyncMock(return_value={"claimed": 0})
    monkeypatch.setattr(admission, "drain", patched_drain)
    monkeypatch.setattr(ExpoReceiptAudit, "run_due", patched_receipts)
    assert await admission.drain_with_receipts(db) == 0
    patched_drain.assert_awaited_once_with(db)
    patched_receipts.assert_awaited_once()
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "reason": "retry", "status": "pending",
    }) == 1
    assert outbound.await_count == 1, "recovery cannot bypass fresh judgement"


@pytest.mark.asyncio
async def test_recovered_alarm_after_interruption_is_single_and_owner_scoped(monkeypatch):
    db, opportunity, _, _ = await setup(monkeypatch, "push_retry_recovery_v134")
    result = await DeliveryService(db).evaluate(OWNER, opportunity.id)
    plan = await DeliveryService(db).repo.get_plan(OWNER, result.plan.id)
    assert plan.transport_retry_alarm_queued
    await db.ambient_wakes.delete_many({"delivery_plan_id": plan.id})
    await db.delivery_plans.update_one(
        {"id": plan.id}, {"$set": {"transport_retry_alarm_queued": False}},
    )
    resumed_at = datetime.fromisoformat(plan.transport_retry_due) + timedelta(seconds=1)
    recovered = await recover_unscheduled_retries(db, now=resumed_at)
    assert recovered == {"due": 1, "scheduled": 1, "deferred": 0}
    assert (await recover_unscheduled_retries(db, now=resumed_at))["due"] == 0
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "delivery_plan_id": plan.id,
        "reason": "retry", "status": "pending",
    }) == 1
    assert await db.ambient_wakes.count_documents({"owner_id": "other"}) == 0
    assert await DeliveryService(db).repo.get_plan("other", plan.id) is None


@pytest.mark.asyncio
async def test_closed_source_is_not_announced_after_transient_throttle(monkeypatch):
    async with real_mongo_queue() as real_db:
        db, opportunity, judge, outbound = await setup(
            monkeypatch, "push_retry_closed_v134",
            db=real_db,
        )
        first = await DeliveryService(db).evaluate(OWNER, opportunity.id)
        waiting = await DeliveryService(db).repo.get_plan(OWNER, first.plan.id)
        opportunity.status = "resolved"
        await OpportunityRepository(db).save(opportunity)
        due = datetime.fromisoformat(waiting.transport_retry_due) + timedelta(seconds=2)
        assert (await tick(db, now=due, limit=1))["completed"] == 1
        current = await DeliveryService(db).repo.get_plan(OWNER, waiting.id)
        assert current.status == "cancelled"
        assert judge.await_count == outbound.await_count == 1


@pytest.mark.asyncio
async def test_a_past_validity_window_does_not_schedule_retry(monkeypatch):
    expiry = datetime.now(timezone.utc) + timedelta(minutes=2)
    db, opportunity, _, _ = await setup(
        monkeypatch, "push_retry_expired_window_v134",
        valid_until=expiry.isoformat(),
    )
    initial = await DeliveryService(db).evaluate(OWNER, opportunity.id)
    saved = await DeliveryService(db).repo.get_plan(OWNER, initial.plan.id)
    assert saved.status == "held"
    assert saved.transport_retry_due is None
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_rate_limit_respects_three_rechecks_and_stops(monkeypatch):
    async with real_mongo_queue() as real_db:
        db, opportunity, judge, outbound = await setup(
            monkeypatch, "push_retry_budget_v134", effect=explicit_429(),
            db=real_db,
        )
        first = await DeliveryService(db).evaluate(OWNER, opportunity.id)
        for repeat in range(MAX_TRANSPORT_RETRIES):
            previous = await DeliveryService(db).repo.get_plan(OWNER, first.plan.id)
            assert previous.transport_retry_attempts == repeat + 1
            assert previous.transport_retry_due
            due = datetime.fromisoformat(previous.transport_retry_due) + timedelta(seconds=2)
            assert (await tick(db, now=due, limit=1))["completed"] == 1
        latest = await DeliveryService(db).repo.get_plan(OWNER, first.plan.id)
        assert latest.status == "held" and latest.transport_retry_due is None
        assert latest.transport_retry_attempts == MAX_TRANSPORT_RETRIES + 1
        assert outbound.await_count == judge.await_count == MAX_TRANSPORT_RETRIES + 1
        assert await db.ambient_wakes.count_documents({"reason": "retry"}) == MAX_TRANSPORT_RETRIES


def test_backoff_is_bounded_and_increases():
    assert [backoff_seconds(i) for i in range(1, 4)] == [300, 600, 1200]
    assert backoff_seconds(100) == 1200
