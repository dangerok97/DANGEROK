"""An invalid discovery proposal must not consume a life change."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from opportunities import reasoning, snapshot
from opportunities.discovery import OpportunityDiscovery


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [
    {},
    {"opportunities": [{
        "identity_key": "study_deficit",
        "what": "",
        "why_it_matters": "Mancano due ore",
        "evidence_refs": ["document:d1"],
    }]},
])
async def test_invalid_proposal_is_retried_after_cooldown(monkeypatch, invalid):
    db = AsyncMongoMockClient().test
    owner = "synthetic-retry-owner"
    facts = {"documents": [{"ref": "document:d1"}], "unavailable_sources": []}
    monkeypatch.setattr(snapshot, "build", AsyncMock(return_value=facts))
    valid = {"opportunities": [{
        "identity_key": "study_deficit",
        "what": "Mancano due ore di studio",
        "why_it_matters": "Gli esercizi necessari non entrano nel tempo libero",
        "evidence_refs": ["document:d1"],
        "initiative": "prepare",
    }]}
    ask = AsyncMock(side_effect=[invalid, valid])
    monkeypatch.setattr(reasoning, "scan", ask)

    discovery = OpportunityDiscovery(db)
    await discovery.note(owner, source="documents", kind="document.added",
                         entity_ref="d1", wake=False)
    first = await discovery.review(owner)
    assert first.unavailable and first.scan.silence
    assert len(await discovery.changes.pending(owner)) == 1
    state = await db.opportunity_scan_state.find_one({"owner_id": owner})
    assert state["last_scan_at"] and not state.get("fingerprint")

    held = await discovery.review(owner)
    assert not held.ran and ask.await_count == 1
    await db.opportunity_scan_state.update_one(
        {"owner_id": owner},
        {"$set": {"last_scan_at": (
            datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()}},
    )
    retried = await discovery.review(owner)
    assert retried.ran and not retried.unavailable
    assert len(retried.scan.created) == 1
    assert ask.await_count == 2
    assert await discovery.changes.pending(owner) == []


@pytest.mark.asyncio
async def test_partial_batch_keeps_change_pending(monkeypatch):
    db = AsyncMongoMockClient().test
    owner = "synthetic-partial-owner"
    monkeypatch.setattr(
        snapshot, "build",
        AsyncMock(return_value={"documents": [{"ref": "document:d1"}]}),
    )
    first = {"opportunities": [
        {
            "identity_key": "travel_delay",
            "what": "Il viaggio crea un ritardo",
            "why_it_matters": "La riunione inizia prima dell'arrivo",
            "evidence_refs": ["document:d1"],
        },
        {
            "identity_key": "second_concern",
            "what": "",
            "why_it_matters": "Serve un controllo",
            "evidence_refs": ["document:d1"],
        },
    ]}
    second = {"opportunities": [{
        "identity_key": "second_concern",
        "what": "Un secondo fatto richiede una verifica",
        "why_it_matters": "La persona potrebbe perdere un'informazione utile",
        "evidence_refs": ["document:d1"],
    }]}
    monkeypatch.setattr(reasoning, "scan", AsyncMock(side_effect=[first, second]))
    discovery = OpportunityDiscovery(db)
    await discovery.note(owner, source="documents", kind="document.added",
                         entity_ref="d1", wake=False)
    partial = await discovery.review(owner)
    assert partial.unavailable and len(partial.scan.created) == 1
    assert len(await discovery.changes.pending(owner)) == 1
    await db.opportunity_scan_state.update_one(
        {"owner_id": owner},
        {"$set": {"last_scan_at": (
            datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()}},
    )
    completed = await discovery.review(owner)
    assert not completed.unavailable and len(completed.scan.created) == 1
    assert await db.opportunities.count_documents({"owner_id": owner}) == 2
    assert await discovery.changes.pending(owner) == []


@pytest.mark.asyncio
async def test_explicit_silence_consumes_the_change(monkeypatch):
    db = AsyncMongoMockClient().test
    owner = "synthetic-silence-owner"
    monkeypatch.setattr(
        snapshot, "build",
        AsyncMock(return_value={"documents": [{"ref": "document:d1"}]}),
    )
    monkeypatch.setattr(
        reasoning, "scan",
        AsyncMock(return_value={
            "opportunities": [],
            "reason_for_silence": "Nessun intervento utile",
        }),
    )
    discovery = OpportunityDiscovery(db)
    await discovery.note(owner, source="documents", kind="document.added",
                         entity_ref="d1", wake=False)
    reviewed = await discovery.review(owner)
    assert reviewed.ran and reviewed.scan.silence and not reviewed.unavailable
    assert await discovery.changes.pending(owner) == []

