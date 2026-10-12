"""The autonomous reader must use governed Memory, not a legacy-only schema."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionStep, AutonomousGoal
from agent.providers import read_internal_state
from conversation_engine.ai_core.models import MemoryCandidate
from life_memory.governance import MemoryGovernanceService


OWNER = "synthetic-memory-reader-v162"


def goal(**overrides):
    return AutonomousGoal(
        owner_id=OWNER,
        objective="Preparare un riepilogo usando i dati già confermati.",
        desired_outcome="Un riepilogo fondato sulle memorie correnti.",
        **overrides,
    )


def step(*refs):
    return ActionStep(
        intent="Rileggere la memoria citata.", step_type="inspect",
        capability_needed="information.read", input_refs=list(refs),
    )


async def promote(db, text, **overrides):
    proposal = dict(
        summary=text, kind="preference", identity_key="synthetic-preference",
        confidence=0.95, authority="user_stated", epistemic_status="confirmed",
        provenance=["user_conversation"], permanence="indefinite",
        reason_for_future_utility="Usare i dati già confermati nelle richieste future.",
        user_authorized=True,
    )
    proposal.update(overrides)
    return await MemoryGovernanceService(db).apply(
        user_id=OWNER, session_id="synthetic-session",
        reasoning_epoch=str(await db.memories.count_documents({})),
        candidate=MemoryCandidate(**proposal), candidate_index=0,
    )


@pytest.mark.asyncio
async def test_promoted_memory_is_read_with_its_real_reference():
    db = AsyncMongoMockClient().v162_memory
    persisted = await promote(db, "Preferisco un riepilogo scritto e conciso.")
    assert persisted.persisted
    result = await read_internal_state(db, OWNER, goal())
    assert result.status == "succeeded"
    assert any("riepilogo scritto" in claim.text for claim in result.claims)
    assert persisted.memory_id in result.provenance.source_refs
    from agent.memory_sources import MEMORY_READ_PROJECTION, memory_source_version
    stored = await db.memories.find_one({"id": persisted.memory_id}, MEMORY_READ_PROJECTION)
    assert result.provenance.source_versions[persisted.memory_id] == memory_source_version(stored)


@pytest.mark.asyncio
async def test_superseded_memory_is_never_reported_as_a_current_fact():
    db = AsyncMongoMockClient().v162_memory
    old = await promote(db, "Preferisco un testo esteso.")
    new = await promote(
        db, "Preferisco un testo conciso.", operation="correct",
        existing_memory_ref=old.memory_id,
    )
    assert new.persisted and new.decision == "SUPERSEDE"
    result = await read_internal_state(db, OWNER, goal())
    assert any("testo conciso" in claim.text for claim in result.claims)
    assert all("testo esteso" not in claim.text for claim in result.claims)
    assert old.memory_id not in result.provenance.source_refs


@pytest.mark.asyncio
async def test_exact_goal_source_is_read_even_after_many_newer_memories():
    db = AsyncMongoMockClient().v162_memory
    now = datetime.now(timezone.utc)
    await db.memories.insert_one({
        "user_id": OWNER, "id": "mem_older_fact", "status": "active",
        "statement": "Il codice pubblico di riferimento è ALFA.",
        "updated_at": (now - timedelta(days=30)).isoformat(),
    })
    await db.memories.insert_many([
        {"user_id": OWNER, "id": f"mem_new_{i}", "status": "active",
         "statement": f"Nota sintetica non pertinente {i}.", "updated_at": now.isoformat()}
        for i in range(20)
    ])
    result = await read_internal_state(db, OWNER, goal(source_refs=["mem_older_fact"]))
    assert [claim.text for claim in result.claims] == ["Il codice pubblico di riferimento è ALFA."]
    assert result.provenance.source_refs == ["mem_older_fact"]


@pytest.mark.asyncio
async def test_step_reference_is_forwarded_by_the_actual_executor():
    from agent.execution import StepExecutor

    db = AsyncMongoMockClient().v162_memory
    await db.memories.insert_many([
        {"user_id": OWNER, "id": "mem_goal", "status": "active", "statement": "Fatto del goal."},
        {"user_id": OWNER, "id": "mem_step", "status": "active", "statement": "Fatto del passo."},
    ])
    objective = goal(source_refs=["mem_goal"])
    executor = StepExecutor(db)
    result = await executor.run(
        OWNER, objective, step("mem_step"), may_touch_the_world=False,
    )
    evidence = await executor.evidence.for_goal(OWNER, objective.id)
    assert result.status == "succeeded"
    assert [item.claim for item in evidence] == ["Fatto del passo."]
    assert result.provenance.source_refs == ["mem_step"]


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_status", ["foreign_owner", "forgotten", "superseded"])
async def test_unavailable_exact_reference_never_falls_back_to_an_unrelated_memory(missing_status):
    db = AsyncMongoMockClient().v162_memory
    await db.memories.insert_many([
        {"user_id": "another-owner" if missing_status == "foreign_owner" else OWNER,
         "id": "mem_requested", "status": "active" if missing_status == "foreign_owner" else missing_status,
         "statement": "Questo testo non deve essere letto."},
        {"user_id": OWNER, "id": "mem_unrelated", "status": "active", "statement": "Testo non pertinente."},
    ])
    result = await read_internal_state(db, OWNER, goal(source_refs=["mem_requested"]))
    assert result.status == "unavailable"
    assert result.error_type == "memory_not_observed"
    assert not result.claims
    assert not result.provenance.source_refs


@pytest.mark.asyncio
async def test_bounded_recent_read_keeps_legacy_notes_and_declares_coverage():
    db = AsyncMongoMockClient().v162_memory
    await db.memories.insert_many([
        {"user_id": OWNER, "id": f"legacy_{i}", "summary": f"Nota precedente {i}."}
        for i in range(20)
    ])
    result = await read_internal_state(db, OWNER, goal())
    assert 0 < len(result.claims) <= 8
    assert "limitat" in result.provenance.certainty_note.lower()
    assert "non" in result.provenance.certainty_note.lower()
    assert len(result.provenance.source_refs) == len(result.claims)


@pytest.mark.asyncio
async def test_empty_memory_does_not_claim_all_internal_sources_were_searched():
    db = AsyncMongoMockClient().v162_memory
    result = await read_internal_state(db, OWNER, goal())
    assert result.status == "succeeded"
    assert "memorie" in result.observation.lower()
    assert "altre fonti" in result.provenance.certainty_note.lower()
    assert "non risulta niente di registrato su questo" not in result.claims[0].text.lower()


@pytest.mark.asyncio
async def test_read_failure_is_retryable_instead_of_empty_success():
    def broken_find(*args, **kwargs):
        raise ConnectionError("synthetic database outage")

    db = SimpleNamespace(memories=SimpleNamespace(find=broken_find))
    result = await read_internal_state(db, OWNER, goal())
    assert result.status == "failed"
    assert result.retryable is True
    assert not result.claims
