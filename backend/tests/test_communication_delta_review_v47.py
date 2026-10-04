from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from opportunities.discovery import OpportunityDiscovery
from opportunities.models import ScanResult
from opportunities.service import OpportunityService
from opportunities import snapshot


@pytest.mark.asyncio
async def test_fresh_communication_bypasses_stable_snapshot_dedupe_once(monkeypatch):
    db = AsyncMongoMockClient().test

    async def stable_snapshot(_db, _owner, *, changes=None):
        return {
            "calendar": [],
            "documents": [],
            "situations": [],
            "temporal": {"hour_bucket": "2026-10-04T21"},
            "what_changed": list(changes or []),
            "unavailable_sources": [],
        }

    monkeypatch.setattr(snapshot, "build", stable_snapshot)
    monkeypatch.setattr("opportunities.discovery.COOLDOWN_SECONDS", 0)

    scan = AsyncMock(return_value=ScanResult(silence=True))
    monkeypatch.setattr(OpportunityService, "scan", scan)

    discovery = OpportunityDiscovery(db)

    # Establish the stable life fingerprint first.
    baseline = await discovery.review("alice", scheduled=True)
    assert baseline.ran is True
    assert scan.await_count == 1

    # A message is a new fact even when none of the stable snapshot domains
    # changed. It must reach the semantic review exactly once.
    recorded = await discovery.changes.record(
        "alice",
        source="communications",
        kind="message.received",
        entity_ref="mail:m1",
        entity_kind="email",
        after="Appuntamento spostato",
    )
    assert recorded.outcome == "accepted"

    communication = await discovery.review("alice")
    assert communication.ran is True
    assert communication.changes_reviewed == 1
    assert scan.await_count == 2
    asked = scan.await_args.kwargs["prepared_snapshot"]["what_changed"]
    assert asked[0]["what_moved"] == "communications:message.received"
    assert asked[0]["ref"] == "mail:m1"

    # The stable fingerprint stays stable after that review. A different
    # envelope that has no durable state behind it is still suppressed by the
    # old rule, so the communication exception does not disable dedupe.
    await discovery.changes.record(
        "alice",
        source="documents",
        kind="document.added",
        entity_ref="doc_missing",
    )
    same_world = await discovery.review("alice")
    assert same_world.ran is False
    assert "stessi" in same_world.skipped
    assert scan.await_count == 2


@pytest.mark.asyncio
async def test_duplicate_communication_still_costs_one_review(monkeypatch):
    db = AsyncMongoMockClient().test

    async def stable_snapshot(_db, _owner, *, changes=None):
        return {
            "calendar": [],
            "documents": [],
            "situations": [],
            "temporal": {"hour_bucket": "2026-10-04T21"},
            "what_changed": list(changes or []),
            "unavailable_sources": [],
        }

    monkeypatch.setattr(snapshot, "build", stable_snapshot)
    monkeypatch.setattr("opportunities.discovery.COOLDOWN_SECONDS", 0)
    scan = AsyncMock(return_value=ScanResult(silence=True))
    monkeypatch.setattr(OpportunityService, "scan", scan)

    discovery = OpportunityDiscovery(db)
    first = await discovery.changes.record(
        "alice",
        source="communications",
        kind="thread.updated",
        entity_ref="mail:thread-1",
        after="Nuova risposta",
    )
    duplicate = await discovery.changes.record(
        "alice",
        source="communications",
        kind="thread.updated",
        entity_ref="mail:thread-1",
        after="Nuova risposta",
    )
    assert first.outcome == "accepted"
    assert duplicate.outcome == "duplicate"

    result = await discovery.review("alice")
    assert result.ran is True
    assert scan.await_count == 1

    second = await discovery.review("alice")
    assert second.ran is False
    assert scan.await_count == 1
