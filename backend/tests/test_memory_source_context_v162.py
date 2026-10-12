"""Cited Memory reaches admission and discovery without becoming fresh evidence."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning as agent_reasoning
from agent.admission import drain
from agent.memory_sources import MEMORY_PREVIEW_CHARACTERS, read_memory_previews
from agent.service import AgentService
from conversation_engine.ai_core.models import MemoryCandidate
from life_memory.governance import MemoryGovernanceService
from opportunities import reasoning as opportunity_reasoning, snapshot
from opportunities.changes import fingerprint
from opportunities.discovery import OpportunityDiscovery
from opportunities.models import EvidenceRef, Opportunity
from opportunities.repository import OpportunityRepository
from scripts.phase2_goal_outcome_eval_v140 import FACT


OWNER = "synthetic-memory-context-v162"
MOMENT = datetime(2030, 4, 5, 10, 0, tzinfo=timezone.utc)


async def canonical_memory(db):
    await db.users.insert_one({"id": OWNER, "user_id": OWNER,
                               "settings": {"timezone": "Europe/Rome"}})
    result = await MemoryGovernanceService(db).apply(
        user_id=OWNER, session_id="synthetic-context", reasoning_epoch="context-v162",
        candidate_index=0,
        candidate=MemoryCandidate(
            summary=FACT, kind="service_contract_note", identity_key="synthetic:archive-note",
            confidence=0.95, authority="user_stated", epistemic_status="confirmed",
            provenance=["user_conversation"], permanence="indefinite",
            reason_for_future_utility="Confrontare i costi riferiti e i rispettivi vincoli.",
            user_authorized=True,
        ),
    )
    assert result.persisted and result.memory_id
    return result.memory_id


def changed(ref):
    return {"what_moved": "conversation:constraint.changed", "ref": ref,
            "when": MOMENT.isoformat(), "from_to": {"before": None, "after": FACT[:160]}}


def observe_admission(monkeypatch):
    model = AsyncMock(return_value={"outcome": "no_goal", "reasoning": "Decisione sintetica osservativa."})
    monkeypatch.setattr(agent_reasoning, "_ask_model", model)
    return model


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["", "memory:", "user_memory:"])
async def test_real_admission_receives_the_cited_canonical_note_and_preserves_no_goal(monkeypatch, prefix):
    db = AsyncMongoMockClient().memory_context
    memory_id = await canonical_memory(db)
    ref = prefix + memory_id
    await db.memories.insert_many([
        {"id": "mem_uncited", "user_id": OWNER, "status": "active", "statement": "UNCITED-PRIVATE"},
        {"id": "mem_foreign", "user_id": "someone-else", "status": "active", "statement": "FOREIGN-PRIVATE"},
    ])
    await db.memories.update_one({"id": memory_id}, {"$set": {
        "summary": "OBSOLETE-LEGACY", "audit_private": "PRIVATE-AUDIT",
        "temporal_scope.starts_at": "2030-01-01T00:00:00+01:00",
    }})
    repository = OpportunityRepository(db)
    await repository.ensure_indexes()
    await AgentService(db).ensure_indexes()
    await repository.save(Opportunity(
        owner_id=OWNER, identity_key="synthetic:cost-comparison", status="active", initiative="prepare",
        semantic_summary="Una nota interna descrive due opzioni e i rispettivi costi.",
        why_it_matters="Confrontare il costo complessivo insieme ai limiti delle condizioni.",
        what_ora_can_do="Rileggere la nota e preparare il confronto senza operazioni esterne.",
        evidence=[EvidenceRef(kind="memory", ref=ref, summary="Nota interna sulle due opzioni.")],
    ))
    model = observe_admission(monkeypatch)

    assert await drain(db, owner_id=OWNER, limit=1) == 1

    payload = json.loads(model.await_args.args[1])
    assert payload["source_context_unavailable"] is False
    assert len(payload["source_context"]) == 1
    note = payload["source_context"][0]
    assert note["ref"] == ref and note["statement"] == FACT
    assert note["authority"] == "user_stated" and note["epistemic_status"] == "confirmed"
    assert note["provenance"] == ["user_conversation"]
    assert note["temporal_scope"]["starts_at"] == "2030-01-01T00:00:00+01:00"
    assert note["freshness"] == "unknown" and not note["excerpt_truncated"]
    assert all(secret not in str(payload) for secret in (
        "UNCITED-PRIVATE", "FOREIGN-PRIVATE", "PRIVATE-AUDIT", "OBSOLETE-LEGACY",
    ))
    # Supplying the missing facts does not force a semantic outcome or create evidence.
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.agent_evidence.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0
    assert (await db.opportunities.find_one({"owner_id": OWNER}))["agent_review_outcome"] == "no_goal"


@pytest.mark.asyncio
async def test_discovery_rereads_the_memory_behind_the_short_change_envelope(monkeypatch):
    db = AsyncMongoMockClient().memory_discovery
    memory_id = await canonical_memory(db)
    discovery = OpportunityDiscovery(db)
    await discovery.ensure_indexes()
    await OpportunityRepository(db).ensure_indexes()
    assert (await discovery.note(
        OWNER, source="conversation", kind="constraint.changed", entity_ref=memory_id,
        after=FACT, wake=False,
    ))["outcome"] == "accepted"
    model = AsyncMock(return_value={"opportunities": [], "reason_for_silence": "Decisione sintetica osservativa."})
    monkeypatch.setattr(opportunity_reasoning, "_ask_model", model)

    result = await discovery.review(OWNER)

    assert result.ran and not result.unavailable and result.scan.silence
    payload = json.loads(model.await_args.args[1])
    state = payload["life_right_now"]
    assert len(state["what_changed"][0]["from_to"]["after"]) == 160
    assert state["memories"][0]["statement"] == FACT
    assert "120 euro" in state["memories"][0]["statement"]
    assert "rimborso" in state["memories"][0]["statement"]
    assert state["memories"][0]["freshness"] == "unknown"
    assert state["unavailable_memory_refs"] == []
    assert "memories" not in state["unavailable_sources"]
    assert snapshot.evidence_refs(state)[memory_id] == "memory"
    assert await db.agent_evidence.count_documents({}) == 0
    assert await db.opportunities.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["missing", "forgotten", "superseded", "foreign", "empty"])
async def test_unreadable_reference_is_explicit_in_both_contexts_without_unrelated_fallback(monkeypatch, condition):
    db = AsyncMongoMockClient().memory_unavailable
    ref = "mem_unreadable"
    if condition != "missing":
        await db.memories.insert_one({
            "id": ref, "user_id": "someone-else" if condition == "foreign" else OWNER,
            "status": condition if condition in ("forgotten", "superseded") else "active",
            "statement": "" if condition == "empty" else "UNREADABLE-PRIVATE",
        })
    await db.memories.insert_one({
        "id": "mem_unrelated", "user_id": OWNER, "status": "active", "statement": "UNRELATED-PRIVATE",
    })
    model = observe_admission(monkeypatch)
    await AgentService(db).consider(OWNER, situation={"what": "Rileggere la nota citata."}, source_refs=[ref])
    admission = json.loads(model.await_args.args[1])
    assert admission["source_context"] == []
    assert admission["source_context_unavailable"] is True
    assert admission["unavailable_memory_refs"] == [ref]

    state = await snapshot.build(db, OWNER, changes=[changed(ref)])
    assert state["memories"] == []
    assert state["unavailable_memory_refs"] == [ref]
    assert "memories" in state["unavailable_sources"]
    assert all(secret not in str([admission, state]) for secret in ("UNREADABLE-PRIVATE", "UNRELATED-PRIVATE"))


@pytest.mark.asyncio
async def test_database_failure_is_unavailable_coverage_not_a_successful_empty_read(monkeypatch):
    backing = AsyncMongoMockClient().memory_failure
    failure = Mock(side_effect=ConnectionError("PRIVATE-DATABASE-ERROR"))

    class DatabaseWithUnreadableMemory:
        def __getattr__(self, name):
            return SimpleNamespace(find=failure) if name == "memories" else getattr(backing, name)

        def __getitem__(self, name):
            return getattr(self, name)

    db = DatabaseWithUnreadableMemory()
    ref = "mem_temporarily_unavailable"
    with pytest.raises(ConnectionError):
        await read_memory_previews(db, OWNER, [ref])
    model = observe_admission(monkeypatch)
    await AgentService(db).consider(OWNER, situation={"what": "Rileggere la nota citata."}, source_refs=[ref])
    admission = json.loads(model.await_args.args[1])
    state = await snapshot.build(db, OWNER, changes=[changed(ref)])
    assert admission["source_context_unavailable"] is True
    assert admission["unavailable_memory_refs"] == [ref]
    assert state["memories"] == [] and state["unavailable_memory_refs"] == [ref]
    assert "memories" in state["unavailable_sources"]
    assert "PRIVATE-DATABASE-ERROR" not in str([admission, state])


@pytest.mark.asyncio
async def test_uncited_or_non_memory_sources_never_trigger_a_memory_query():
    query = Mock(side_effect=AssertionError("No Memory reference was cited"))
    db = SimpleNamespace(memories=SimpleNamespace(find=query))
    assert await read_memory_previews(db, OWNER, []) == []
    assert await read_memory_previews(db, OWNER, ["document:one", "memory:index", "uncited-id"]) == []
    query.assert_not_called()


@pytest.mark.asyncio
async def test_preview_count_text_and_metadata_are_bounded_with_explicit_excerpt_limit():
    db = AsyncMongoMockClient().memory_bounds
    ids = [f"mem_bound_{index}" for index in range(12)]
    long_text = "Condizioni della nota. " * 80
    await db.memories.insert_many([
        {"id": ref, "user_id": OWNER, "status": "active", "statement": long_text,
         "temporal_scope": {"recurrence": "r" * 1000, "private_metadata": "PRIVATE-METADATA"},
         "provenance": ["p" * 1000] * 100}
        for ref in ids
    ])
    rows = await read_memory_previews(db, OWNER, ids, limit=100)
    assert len(rows) == 8
    assert [row["ref"] for row in rows] == ids[:8]
    assert all(row["statement"] == long_text[:MEMORY_PREVIEW_CHARACTERS] for row in rows)
    assert all(row["excerpt_truncated"] for row in rows)
    assert all(len(row["provenance"]) == 3 and len(row["provenance"][0]) == 80 for row in rows)
    assert all(len(row["temporal_scope"]["recurrence"]) == 120 for row in rows)
    assert "PRIVATE-METADATA" not in str(rows)
    state = await snapshot.build(db, OWNER, changes=[changed(ref) for ref in ids])
    assert len(state["memories"]) == 8
    assert state["unavailable_memory_refs"] == ids[8:]
    assert "memories" in state["unavailable_sources"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["statement", "content", "summary", "fact_summary"])
async def test_legacy_fields_remain_readable_by_the_exact_legacy_handle(field):
    db = AsyncMongoMockClient().memory_legacy
    await db.memories.insert_one({"id": "legacy_note", "user_id": OWNER, field: "Nota precedente citata."})
    rows = await read_memory_previews(db, OWNER, ["user_memory:legacy_note", "memory:legacy_note"])
    assert len(rows) == 1 and rows[0]["statement"] == "Nota precedente citata."
    assert rows[0]["ref"] == "user_memory:legacy_note"
    assert rows[0]["authority"] == "unknown" and rows[0]["freshness"] == "unknown"


@pytest.mark.asyncio
async def test_material_memory_correction_invalidates_discovery_fingerprint(monkeypatch):
    db = AsyncMongoMockClient().memory_fingerprint
    memory_id = await canonical_memory(db)
    monkeypatch.setattr(snapshot, "_now", lambda: MOMENT)
    changes = [changed(memory_id)]
    before = await snapshot.build(db, OWNER, changes=changes)
    await db.memories.update_one({"id": memory_id}, {"$set": {
        "statement": FACT.replace("120 euro", "150 euro"),
        "content": FACT.replace("120 euro", "150 euro"),
    }})
    after = await snapshot.build(db, OWNER, changes=changes)
    assert before["what_changed"] == after["what_changed"]
    assert before["temporal"] == after["temporal"]
    assert before["memories"] != after["memories"]
    assert fingerprint(before) != fingerprint(after)
