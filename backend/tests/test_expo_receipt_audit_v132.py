"""V132: Expo ticket → delayed receipt audit; never claim phone delivery.

No HTTP ever leaves this test. Real provider adapter, owner-scoped endpoint
store, Mongo receipt ledger and ambient admission lane run with synthetic data.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from ambient.push import ExpoNotificationProvider, PushEndpointService, is_expo_push_token
from delivery.expo_receipts import ExpoReceiptAudit


OWNER = "synthetic-expo-owner"
FIRST = "ExponentPushToken[synthetic-device-one]"
SECOND = "ExponentPushToken[synthetic-device-two]"


async def setup(name, *, two=False):
    db = AsyncMongoMockClient()[name]
    await ExpoReceiptAudit(db).ensure_indexes()
    await PushEndpointService(db).register(
        OWNER, token=FIRST, device="iphone-test", platform="ios",
        permission_state="granted",
    )
    if two:
        await PushEndpointService(db).register(
            OWNER, token=SECOND, device="android-test", platform="android",
            permission_state="granted",
        )
    return db


async def send(provider, *, plan="dlv_synthetic", owner=OWNER):
    return await provider.send(
        owner_id=owner, plan_id=plan,
        title="Private notification title", body="Private notification message",
        public_title="Public title", public_body="Open the app",
        deep_link="/ora?entry=notification",
    )


@pytest.mark.asyncio
async def test_accepted_tickets_are_owner_scoped_persisted_and_later_confirmed(monkeypatch):
    db = await setup("expo_receipt_two_devices_v132", two=True)
    provider = ExpoNotificationProvider(db)
    post = AsyncMock(return_value=[
        {"status": "ok", "id": "ticket-opaque-A"},
        {"status": "ok", "id": "ticket-opaque-B"},
    ])
    monkeypatch.setattr(provider, "_post", post)
    result = await send(provider)
    assert result["ok"] is True
    assert result["provider_accepted"] == 2
    assert result["receipt_audit_tracked"] == 2
    assert result["receipt_audit_untracked"] == 0
    sent = post.await_args.args[0]
    assert {item["to"] for item in sent} == {FIRST, SECOND}
    assert all(item["title"] == "Public title" for item in sent)
    records = await db.expo_push_receipts.find({}, {"_id": 0}).to_list(None)
    assert len(records) == 2
    assert {row["ticket_id"] for row in records} == {"ticket-opaque-A", "ticket-opaque-B"}
    assert all(row["owner_id"] == OWNER and row["state"] == "pending" for row in records)
    assert FIRST not in str(records) and SECOND not in str(records)
    assert "Private notification" not in str(records)

    auditor = ExpoReceiptAudit(db)
    lookup = AsyncMock(return_value={
        "ticket-opaque-A": {"status": "ok"},
        "ticket-opaque-B": {"status": "ok"},
    })
    monkeypatch.setattr(auditor, "_post_receipts", lookup)
    too_early = await auditor.run_due()
    assert too_early["claimed"] == 0
    moment = datetime.now(timezone.utc) + timedelta(minutes=16)
    processed = await auditor.run_due(now=moment)
    assert processed["claimed"] == processed["handoff_confirmed"] == 2
    lookup.assert_awaited_once()
    assert set(lookup.await_args.args[0]) == {"ticket-opaque-A", "ticket-opaque-B"}
    stored = await db.expo_push_receipts.find({}).to_list(None)
    assert all(x["state"] == "handoff_confirmed" for x in stored)
    assert await auditor.run_due(now=moment) == {
        "claimed": 0, "handoff_confirmed": 0, "rejected": 0,
        "unconfirmed": 0, "retrying": 0,
    }


@pytest.mark.asyncio
async def test_denied_or_stub_device_never_receives_a_real_expo_request(monkeypatch):
    db = await setup("expo_permission_filter_v132")
    await PushEndpointService(db).register(
        OWNER, token=SECOND, device="other-device", permission_state="denied",
    )
    await PushEndpointService(db).register(
        OWNER, token="stub-token", device="web-only", permission_state="granted",
    )
    provider = ExpoNotificationProvider(db)
    post = AsyncMock(return_value=[{"status": "ok", "id": "receipt-1"}])
    monkeypatch.setattr(provider, "_post", post)
    answer = await send(provider)
    assert answer["provider_accepted"] == 1
    assert [item["to"] for item in post.await_args.args[0]] == [FIRST]
    await db.push_endpoints.update_one(
        {"token": FIRST}, {"$set": {"permission_state": "denied"}}
    )
    post.reset_mock()
    blocked = await send(provider, plan="dlv_blocked")
    assert blocked == {"ok": False, "provider": "expo", "reason": "no_endpoint"}
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_mismatched_ticket_count_fails_closed_without_disabling_devices(monkeypatch):
    db = await setup("expo_mismatch_v132", two=True)
    provider = ExpoNotificationProvider(db)
    outbound = AsyncMock(return_value=[{"status": "error", "details": {
        "error": "DeviceNotRegistered",
    }}])
    monkeypatch.setattr(provider, "_post", outbound)
    response = await send(provider)
    assert response["ok"] is False
    assert response["reason"] == "ticket_count_mismatch"
    assert response["transient"] is True
    assert await db.expo_push_receipts.count_documents({}) == 0
    assert await db.push_endpoints.count_documents({"status": "active"}) == 2


@pytest.mark.asyncio
async def test_missing_receipt_stays_pending_then_retries_without_resending(monkeypatch):
    db = await setup("expo_receipt_pending_v132")
    provider = ExpoNotificationProvider(db)
    monkeypatch.setattr(provider, "_post", AsyncMock(return_value=[
        {"status": "ok", "id": "opaque-pending"},
    ]))
    assert (await send(provider))["ok"]
    audit = ExpoReceiptAudit(db)
    receipt_lookup = AsyncMock(side_effect=[
        {}, {"opaque-pending": {"status": "ok"}},
    ])
    monkeypatch.setattr(audit, "_post_receipts", receipt_lookup)
    now = datetime.now(timezone.utc) + timedelta(minutes=16)
    first = await audit.run_due(now=now)
    assert first["retrying"] == 1 and first["handoff_confirmed"] == 0
    pending = await db.expo_push_receipts.find_one({"ticket_id": "opaque-pending"})
    assert pending["state"] == "pending"
    assert (await audit.run_due(now=now))["claimed"] == 0
    second = await audit.run_due(now=now + timedelta(minutes=10))
    assert second["handoff_confirmed"] == 1
    assert receipt_lookup.await_count == 2


@pytest.mark.asyncio
async def test_expo_transport_failure_recovers_and_unconfirmed_receipts_expire(monkeypatch):
    db = await setup("expo_receipt_expiry_v132")
    audit = ExpoReceiptAudit(db)
    older = datetime.now(timezone.utc) - timedelta(hours=25)
    await audit.track(OWNER, "dlv_expired", [
        {"ticket_id": "opaque-old", "endpoint_id": (
            await db.push_endpoints.find_one({"owner_id": OWNER})
        )["id"]},
    ], now=older)
    broken = AsyncMock(side_effect=ConnectionError("synthetic provider outage"))
    monkeypatch.setattr(audit, "_post_receipts", broken)
    result = await audit.run_due(now=datetime.now(timezone.utc))
    assert result["claimed"] == 1 and result["unconfirmed"] == 1
    record = await db.expo_push_receipts.find_one({"ticket_id": "opaque-old"})
    assert record["state"] == "unconfirmed"
    assert record["error_code"] == "receipts_unavailable"
    assert await db.push_endpoints.count_documents({"status": "active"}) == 1


@pytest.mark.asyncio
async def test_device_unregistered_receipt_disables_only_original_owner(monkeypatch):
    db = await setup("expo_receipt_reassignment_v132")
    provider = ExpoNotificationProvider(db)
    monkeypatch.setattr(provider, "_post", AsyncMock(return_value=[
        {"status": "ok", "id": "opaque-moved"},
    ]))
    assert (await send(provider))["ok"]
    # Re-register the same device for another owner before the receipt arrives.
    await PushEndpointService(db).register(
        "new-owner", token=FIRST, device="iphone-test",
        permission_state="granted",
    )
    audit = ExpoReceiptAudit(db)
    monkeypatch.setattr(audit, "_post_receipts", AsyncMock(return_value={
        "opaque-moved": {"status": "error", "details": {
            "error": "DeviceNotRegistered",
        }},
    }))
    summary = await audit.run_due(
        now=datetime.now(timezone.utc) + timedelta(minutes=16)
    )
    assert summary["rejected"] == 1
    new_owner = await db.push_endpoints.find_one({"token": FIRST})
    assert new_owner["owner_id"] == "new-owner"
    assert new_owner["status"] == "active"
    assert await db.expo_push_receipts.count_documents({
        "owner_id": OWNER, "state": "rejected",
    }) == 1


@pytest.mark.asyncio
async def test_device_unregistered_disables_just_the_active_target(monkeypatch):
    db = await setup("expo_receipt_disable_v132", two=True)
    provider = ExpoNotificationProvider(db)
    outbound = AsyncMock(return_value=[
        {"status": "ok", "id": "receipt-ios"},
        {"status": "ok", "id": "receipt-android"},
    ])
    monkeypatch.setattr(provider, "_post", outbound)
    assert (await send(provider))["receipt_audit_tracked"] == 2
    audit = ExpoReceiptAudit(db)
    monkeypatch.setattr(audit, "_post_receipts", AsyncMock(return_value={
        "receipt-ios": {"status": "error", "details": {
            "error": "DeviceNotRegistered",
        }},
        "receipt-android": {"status": "ok"},
    }))
    result = await audit.run_due(
        now=datetime.now(timezone.utc) + timedelta(minutes=16)
    )
    assert result["rejected"] == 1 and result["handoff_confirmed"] == 1
    assert await db.push_endpoints.count_documents({"status": "disabled"}) == 1
    assert await db.push_endpoints.count_documents({"status": "active"}) == 1


@pytest.mark.asyncio
async def test_recurring_lifecycle_uses_existing_delivery_lane(monkeypatch):
    from ambient import runtime
    from delivery import admission, provider as provider_module

    db = await setup("expo_background_lane_v132")
    expo = ExpoNotificationProvider(db)
    monkeypatch.setattr(provider_module, "get_provider", lambda: expo)
    admiss = AsyncMock(return_value=2)
    monkeypatch.setattr(admission, "drain", admiss)
    receipt = AsyncMock(return_value={"claimed": 0})
    monkeypatch.setattr(ExpoReceiptAudit, "run_due", receipt)
    assert await runtime._serve_delivery_admission(db) == 2
    admiss.assert_awaited_once_with(db)
    receipt.assert_awaited_once()


@pytest.mark.asyncio
async def test_both_expo_push_token_prefixes_are_registered_for_real_provider():
    db = AsyncMongoMockClient().expo_token_formats_v132
    assert is_expo_push_token("ExponentPushToken[synthetic-old]")
    assert is_expo_push_token("ExpoPushToken[synthetic-new]")
    assert not is_expo_push_token("untrusted-device-token")
    result = await PushEndpointService(db).register(
        OWNER, token="ExpoPushToken[synthetic-new]", device="new-synthetic-device",
        permission_state="granted",
    )
    assert result["ok"]
    assert result["endpoint"]["provider"] == "expo"
    provider = ExpoNotificationProvider(db)
    async def stub(messages):
        assert messages[0]["to"] == "ExpoPushToken[synthetic-new]"
        return [{"status": "ok", "id": "token-prefix-ticket"}]
    provider._post = stub
    outcome = await send(provider)
    assert outcome["ok"] and outcome["receipt_audit_tracked"] == 1
