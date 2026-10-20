"""Signal LLM outages must not spin once per 10-second Ambient tick.

These regressions exercise the existing legacy interpretation lane and the
owner candidate selector. The model is faked; no real personal sources, weather
reads, emails or notifications are accessed. Retry state is operational-only.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from connected.models import ConnectedSignal
from connected.polling import _owners_with_something_to_understand, interpret_due
from connected.service import ConnectedLifeService
from connected.signals import (
    SignalService,
    LEGACY_RETRY_BASE_SECONDS,
    LEGACY_RETRY_MAX_SECONDS,
)


def instant(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


async def add(db, owner, sid):
    signal = ConnectedSignal(
        id=sid, owner_id=owner, source_id="mail-source",
        source_type="email", signal_type="email.message.added",
        source_object_ref="thread-" + sid,
        payload_summary="Observed source change (synthetic)",
    )
    await db.connected_signals.insert_one(signal.model_dump())


@pytest.mark.asyncio
async def test_failed_judgement_stays_pending_without_hammering_provider(monkeypatch):
    db = AsyncMongoMockClient().test_legacy_defer
    owner = "synthetic-owner"
    await add(db, owner, "sig_a")
    service = ConnectedLifeService(db)
    monkeypatch.setattr(service, "_life", AsyncMock(return_value={}))
    monkeypatch.setattr(service.sources, "list", AsyncMock(return_value=[]))
    decision = AsyncMock(return_value=None)
    monkeypatch.setattr("connected.reasoning.interpret_signal", decision)

    first = await service.interpret(owner, limit=1)
    assert first["looked_at"] == 1
    decision.assert_awaited_once()
    record = await db.connected_signals.find_one(
        {"owner_id": owner, "id": "sig_a"}, {"_id": 0},
    )
    assert record["status"] == "pending"
    assert record["_legacy_interpret"]["attempts"] == 1
    due = instant(record["_legacy_interpret"]["next_run_at"])
    delay = (due - datetime.now(timezone.utc)).total_seconds()
    assert LEGACY_RETRY_BASE_SECONDS - 5 <= delay <= LEGACY_RETRY_BASE_SECONDS + 5

    # Ambient may tick dozens of times; neither selection nor direct service
    # invocation should return the old signal while its retry is in the future.
    assert await _owners_with_something_to_understand(db, limit=3) == []
    for _ in range(3):
        outcome = await service.interpret(owner, limit=1)
        assert outcome["looked_at"] == 0
    decision.assert_awaited_once()
    assert (await db.connected_signals.find_one(
        {"owner_id": owner, "id": "sig_a"}, {"_id": 0}
    ))["status"] == "pending"
    assert await db.ambient_activity.count_documents({}) == 0

    # A NEW observation is never blocked by the earlier source failure.
    await add(db, owner, "sig_b")
    decision.return_value = {"outcome": "noise", "touches_money": False}
    done = await interpret_due(db)
    assert done == {"looked_at": 1, "understood": 0, "noise": 1}
    assert decision.await_count == 2
    latest = await db.connected_signals.find_one(
        {"owner_id": owner, "id": "sig_b"}, {"_id": 0},
    )
    assert latest["status"] == "skipped"
    old = await db.connected_signals.find_one(
        {"owner_id": owner, "id": "sig_a"}, {"_id": 0},
    )
    assert old["status"] == "pending"


@pytest.mark.asyncio
async def test_outage_retry_backoff_survives_restart_and_is_bounded(monkeypatch):
    db = AsyncMongoMockClient().test_legacy_restart
    owner = "synthetic-restart"
    await add(db, owner, "sig_old")
    service = ConnectedLifeService(db)
    monkeypatch.setattr(service, "_life", AsyncMock(return_value={}))
    monkeypatch.setattr(service.sources, "list", AsyncMock(return_value=[]))
    decision = AsyncMock(return_value=None)
    monkeypatch.setattr("connected.reasoning.interpret_signal", decision)
    delays = []

    for attempt in range(1, 8):
        # Simulate a later worker/restart after the agreed technical retry time.
        if attempt > 1:
            await db.connected_signals.update_one(
                {"owner_id": owner, "id": "sig_old"},
                {"$set": {"_legacy_interpret.next_run_at": (
                    datetime.now(timezone.utc) - timedelta(seconds=2)
                ).isoformat()}},
            )
        fresh = ConnectedLifeService(db)
        monkeypatch.setattr(fresh, "_life", AsyncMock(return_value={}))
        monkeypatch.setattr(fresh.sources, "list", AsyncMock(return_value=[]))
        r = await fresh.interpret(owner, limit=1)
        assert r["looked_at"] == 1
        row = await db.connected_signals.find_one(
            {"owner_id": owner, "id": "sig_old"}, {"_id": 0},
        )
        assert row["status"] == "pending"
        assert row["_legacy_interpret"]["attempts"] == attempt
        delays.append(
            (instant(row["_legacy_interpret"]["next_run_at"])
             - datetime.now(timezone.utc)).total_seconds()
        )
    assert decision.await_count == 7
    assert all(a < b for a, b in zip(delays[:4], delays[1:5]))
    assert delays[-1] <= LEGACY_RETRY_MAX_SECONDS + 5
    assert delays[-1] >= LEGACY_RETRY_MAX_SECONDS - 5
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_atomic_claim_prevents_duplicate_workers_and_foreign_claims():
    db = AsyncMongoMockClient().test_legacy_lease
    await add(db, "o1", "sig_lease")
    signals = SignalService(db)
    first = await signals.claim_legacy_interpret("o1", "sig_lease")
    second = await signals.claim_legacy_interpret("o1", "sig_lease")
    foreign = await signals.claim_legacy_interpret("o2", "sig_lease")
    assert first is True
    assert second is False
    assert foreign is False
    row = await db.connected_signals.find_one(
        {"owner_id": "o1", "id": "sig_lease"}, {"_id": 0}
    )
    assert row["_legacy_interpret"]["attempts"] == 1
    assert [s.id for s in await signals.pending("o1")] == ["sig_lease"]
    assert await signals.pending("o1", due_only=True) == []
    assert await signals.pending("o2") == []
    # Stale source must not be acknowledged as noise or completion.
    assert row["status"] == "pending"
    assert "payload" not in row["_legacy_interpret"]


@pytest.mark.asyncio
async def test_durable_source_work_owner_is_not_selected_before_due():
    db = AsyncMongoMockClient().test_durable_due
    owner = "source-owner"
    await add(db, owner, "sig_durable")
    now = datetime.now(timezone.utc)
    await db.connected_signals.update_one(
        {"owner_id": owner, "id": "sig_durable"},
        {"$set": {"_core_work": {
            "phase": "retry", "attempts": 2,
            "next_run_at": (now + timedelta(hours=1)).isoformat(),
            "lease_until": (now - timedelta(seconds=10)).isoformat(),
        }}},
    )
    assert await _owners_with_something_to_understand(db, limit=5) == []
    # Due time alone is insufficient when a different worker has a live lease.
    await db.connected_signals.update_one(
        {"owner_id": owner, "id": "sig_durable"},
        {"$set": {
            "_core_work.next_run_at": (now - timedelta(seconds=1)).isoformat(),
            "_core_work.lease_until": (now + timedelta(hours=1)).isoformat(),
        }},
    )
    assert await _owners_with_something_to_understand(db, limit=5) == []
    await db.connected_signals.update_one(
        {"owner_id": owner, "id": "sig_durable"},
        {"$set": {"_core_work.lease_until": (now - timedelta(seconds=1)).isoformat()}},
    )
    assert await _owners_with_something_to_understand(db, limit=5) == [owner]
    await db.connected_signals.update_one(
        {"owner_id": owner, "id": "sig_durable"},
        {"$set": {"_core_work.attempts": 5}},
    )
    assert await _owners_with_something_to_understand(db, limit=5) == []
