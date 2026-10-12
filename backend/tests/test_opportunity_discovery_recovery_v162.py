"""A source change is acknowledged only after a current review is durable."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from opportunities import reasoning, snapshot
from opportunities.changes import MAX_PER_BATCH
from opportunities.discovery import OpportunityDiscovery, STATE
from opportunities.models import ScanResult
from opportunities.repository import OpportunityRepository
from opportunities.service import OpportunityService

OWNER = "discovery-recovery-synthetic-owner"
STATE_FIXTURE = {
    "documents": [{"ref": "document:synthetic", "title": "Fonte sintetica"}],
    "unavailable_sources": [],
}


def candidate(what="La fonte suggerisce una verifica utile"):
    return {"opportunities": [{
        "identity_key": "v162:source-review", "what": what,
        "why_it_matters": "Preparare una conclusione utile senza effetti esterni",
        "why_now": "La fonte è cambiata", "initiative": "prepare",
        "what_ora_can_do": "Rileggere e preparare le conclusioni",
        "evidence_refs": ["document:synthetic"],
    }]}


@pytest_asyncio.fixture
async def setup(monkeypatch):
    db = AsyncMongoMockClient().discovery_recovery_v162
    discovery = OpportunityDiscovery(db)
    await discovery.ensure_indexes()
    await OpportunityRepository(db).ensure_indexes()
    monkeypatch.setattr(snapshot, "build", AsyncMock(return_value=STATE_FIXTURE))
    monkeypatch.setattr(snapshot, "evidence_refs", lambda state: {"document:synthetic": "document"})
    return db, discovery


async def note(discovery, *, number=0, owner=OWNER):
    result = await discovery.note(
        owner, source="documents", kind="document.facts_changed",
        entity_ref=f"document:synthetic-{number}", after=f"Versione sintetica {number}", wake=False,
    )
    assert result["outcome"] == "accepted"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["cancel", "exception", "unavailable", "snapshot"])
async def test_interrupted_review_keeps_change_recoverable(setup, monkeypatch, failure):
    db, discovery = setup
    await note(discovery)
    if failure == "snapshot":
        failing = AsyncMock(side_effect=RuntimeError("synthetic snapshot failure"))
        monkeypatch.setattr(snapshot, "build", failing)
    else:
        result = ScanResult(silence=True, unavailable=True)
        failing = AsyncMock(return_value=result)
        if failure in ("cancel", "exception"):
            failing.side_effect = asyncio.CancelledError() if failure == "cancel" else TimeoutError("synthetic timeout")
        monkeypatch.setattr(OpportunityService, "scan", failing)
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await discovery.review(OWNER)
    else:
        assert (await discovery.review(OWNER)).unavailable
    rows = await db.meaningful_changes.find({"owner_id": OWNER}).to_list(5)
    assert len(rows) == 1 and rows[0]["status"] == "pending"
    assert not rows[0].get("consumed_by") and not rows[0].get("claim_token")
    assert len(await discovery.changes.pending(OWNER)) == 1
    assert not (await discovery._state(OWNER)).get("fingerprint")

    monkeypatch.setattr(snapshot, "build", AsyncMock(return_value=STATE_FIXTURE))
    resumed_scan = AsyncMock(return_value=ScanResult(silence=True))
    monkeypatch.setattr(OpportunityService, "scan", resumed_scan)
    resumed = await OpportunityDiscovery(db).review(OWNER)
    assert resumed.ran and not resumed.unavailable and resumed.changes_reviewed == 1
    resumed_scan.assert_awaited_once()
    row = await db.meaningful_changes.find_one({"owner_id": OWNER})
    assert row["status"] == "consumed" and row["consumed_by"]


@pytest.mark.asyncio
async def test_hard_crash_lease_expires_and_old_token_cannot_ack_or_release(setup, monkeypatch):
    db, discovery = setup
    await note(discovery)
    first = await discovery._claim_scan(OWNER, "old-worker")
    old = await discovery.changes.claim(OWNER, "old-worker", lease_until=first["lease_until"])
    assert not await discovery.changes.pending(OWNER)
    # The existing eligibility query still sees pending durable work.
    assert await db.meaningful_changes.count_documents({"owner_id": OWNER, "status": "pending"}) == 1
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    await db[STATE].update_one({"owner_id": OWNER}, {"$set": {"lease_until": expired}})
    await db.meaningful_changes.update_many({"owner_id": OWNER}, {"$set": {"claim_until": expired}})
    assert len(await OpportunityDiscovery(db).changes.pending(OWNER)) == 1
    second = await discovery._claim_scan(OWNER, "replacement-worker")
    new = await discovery.changes.claim(OWNER, "replacement-worker", lease_until=second["lease_until"])
    assert [item.id for item in new] == [item.id for item in old]
    assert await discovery.changes.acknowledge(OWNER, old) == 0
    assert not await discovery._remember(OWNER, scan_id="old-worker", fingerprint="obsolete")
    await discovery.changes.release(OWNER, old)
    row = await db.meaningful_changes.find_one({"owner_id": OWNER})
    assert row["claim_token"] == "replacement-worker" and row["status"] == "pending"
    assert await discovery.changes.acknowledge("another-owner", new) == 0
    assert await discovery.changes.acknowledge(OWNER, new) == 1
    assert await discovery.changes.acknowledge(OWNER, new) == 0


@pytest.mark.asyncio
async def test_two_workers_do_not_review_the_same_owner_concurrently(setup, monkeypatch):
    db, discovery = setup
    await note(discovery)
    entered, release = asyncio.Event(), asyncio.Event()
    async def scan(*args, **kwargs):
        entered.set()
        await release.wait()
        return {"opportunities": [], "reason_for_silence": "Nessun intervento utile"}
    model = AsyncMock(side_effect=scan)
    monkeypatch.setattr(reasoning, "scan", model)
    first = asyncio.create_task(discovery.review(OWNER))
    await entered.wait()
    second = await OpportunityDiscovery(db).review(OWNER, force=True)
    assert not second.ran and second.retry_after_seconds
    assert "già in corso" in second.skipped
    model.assert_awaited_once()
    release.set()
    assert not (await first).unavailable
    assert await db.meaningful_changes.count_documents({"status": "consumed"}) == 1


@pytest.mark.asyncio
async def test_response_after_takeover_never_persists_obsolete_conclusions(setup, monkeypatch):
    db, discovery = setup
    await note(discovery)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0
    async def scan(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
            return candidate("OBSOLETE response from the expired worker")
        return candidate("Current response from the replacement")
    monkeypatch.setattr(reasoning, "scan", scan)
    first = asyncio.create_task(discovery.review(OWNER))
    await entered.wait()
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    await db[STATE].update_one({"owner_id": OWNER}, {"$set": {"lease_until": expired}})
    await db.meaningful_changes.update_many({"owner_id": OWNER}, {"$set": {"claim_until": expired}})
    second = await OpportunityDiscovery(db).review(OWNER, force=True)
    assert second.ran and not second.unavailable and len(second.scan.created) == 1
    winner = await db.meaningful_changes.find_one({"owner_id": OWNER})
    release.set()
    old = await first
    assert old.unavailable
    rows = await db.opportunities.find({"owner_id": OWNER}).to_list(5)
    assert len(rows) == 1 and rows[0]["semantic_summary"] == "Current response from the replacement"
    assert (await db.meaningful_changes.find_one({"owner_id": OWNER}))["consumed_by"] == winner["consumed_by"]
    assert await db.opportunity_decisions.count_documents({"owner_id": OWNER}) == 0


@pytest.mark.asyncio
async def test_partial_persistence_replay_reuses_identity_and_admission_revision(setup, monkeypatch):
    db, discovery = setup
    await note(discovery)
    monkeypatch.setattr(reasoning, "scan", AsyncMock(return_value=candidate()))
    original = OpportunityService.scan
    async def persisted_then_cancelled(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        raise asyncio.CancelledError()
    monkeypatch.setattr(OpportunityService, "scan", persisted_then_cancelled)
    with pytest.raises(asyncio.CancelledError):
        await discovery.review(OWNER)
    original_row = await db.opportunities.find_one({"owner_id": OWNER})
    assert original_row and len(await discovery.changes.pending(OWNER)) == 1
    monkeypatch.setattr(OpportunityService, "scan", original)
    resumed = await OpportunityDiscovery(db).review(OWNER)
    assert resumed.ran and not resumed.unavailable and len(resumed.scan.updated) == 1
    row = await db.opportunities.find_one({"owner_id": OWNER})
    assert row["id"] == original_row["id"]
    assert row["agent_review_revision"] == original_row["agent_review_revision"]
    assert await db.opportunities.count_documents({"owner_id": OWNER}) == 1
    assert not await discovery.changes.pending(OWNER)


@pytest.mark.asyncio
async def test_bounded_oldest_batches_preserve_changes_arriving_during_review(setup, monkeypatch):
    db, discovery = setup
    for index in range(MAX_PER_BATCH + 2):
        await note(discovery, number=index)
    await note(discovery, number=99, owner="another-owner")
    seen = []
    async def scan(*args, **kwargs):
        seen.append(kwargs["changes"])
        if len(seen) == 1:
            await note(discovery, number=500)
        return ScanResult(silence=True)
    monkeypatch.setattr(OpportunityService, "scan", scan)
    first = await discovery.review(OWNER, force=True)
    assert first.changes_reviewed == MAX_PER_BATCH
    assert await db.meaningful_changes.count_documents({"owner_id": OWNER, "status": "pending"}) == 3
    second = await discovery.review(OWNER, force=True)
    assert second.changes_reviewed == 3
    assert len(seen[0]) == MAX_PER_BATCH and len(seen[1]) == 3
    assert not ({row["ref"] for row in seen[0]} & {row["ref"] for row in seen[1]})
    assert await db.meaningful_changes.count_documents({"owner_id": OWNER, "status": "consumed"}) == MAX_PER_BATCH + 3
    assert len(await discovery.changes.pending("another-owner")) == 1


@pytest.mark.asyncio
async def test_same_facts_acknowledge_without_another_model_call(setup, monkeypatch):
    db, discovery = setup
    import opportunities.discovery as module
    monkeypatch.setattr(module, "COOLDOWN_SECONDS", 0)
    model = AsyncMock(return_value={"opportunities": [], "reason_for_silence": "Nessun intervento utile"})
    monkeypatch.setattr(reasoning, "scan", model)
    await note(discovery)
    assert (await discovery.review(OWNER)).ran
    await note(discovery, number=1)
    repeated = await discovery.review(OWNER)
    assert not repeated.ran and repeated.changes_reviewed == 1 and "stessi" in repeated.skipped
    model.assert_awaited_once()
    assert await db.meaningful_changes.count_documents({"status": "consumed"}) == 2


@pytest.mark.asyncio
async def test_failed_state_write_never_acknowledges_the_batch(setup, monkeypatch):
    db, discovery = setup
    await note(discovery)
    monkeypatch.setattr(reasoning, "scan", AsyncMock(return_value={"opportunities": []}))
    monkeypatch.setattr(discovery, "_remember", AsyncMock(return_value=False))
    result = await discovery.review(OWNER)
    assert result.unavailable and len(await discovery.changes.pending(OWNER)) == 1
    assert await db.meaningful_changes.count_documents({"status": "consumed"}) == 0
