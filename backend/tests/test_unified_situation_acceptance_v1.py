"""One synthetic Situation through ORA's actual owned persistence chain.

This is not a real-world drying estimate or a delivered notification. It
asserts that a saved memory alone cannot pass the monitored-outcome gate.
The same invariant applies to any temporary physical process.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import AgentEvidence, AgentRun, ResultProvenance
from agent.service import AgentService
from opportunities.discovery import OpportunityDiscovery
from situations.followup import (
    INITIAL_KIND, KIND, arrange_followup, read_followup, goal_id_for,
)
from situations.models import SituationUpdate
from situations.outcomes import validate_assessment, current_outcome
from situations.repository import SituationRepository
from situations.service import SituationService

OWNER = "synthetic-situation-owner"
OTHER = "synthetic-other-owner"


async def create_synthetic_situation(db, *, epoch="situation-experiment-1"):
    return await SituationService(db).apply(
        user_id=OWNER, session_id="synthetic-chat", reasoning_epoch=epoch,
        update=SituationUpdate(
            operation="create", source="user_conversation",
            summary="TEST ORA: oggetto esposto alle condizioni esterne",
            semantic_kind="situazione temporanea",
            temporal_scope="temporary",
            desired_outcome="Sapere quando conviene intervenire.",
            attention_intent="Seguire la situazione sino a una conclusione utile.",
            next_check_summary="Rileggere condizioni attuali e fonti pertinenti.",
            started_at=(datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
            location_label="Località di prova, nessun luogo reale",
        ),
    )


@pytest.mark.asyncio
async def test_create_to_evidence_bound_checkpoint_and_result(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "1")
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().unified_situation_acceptance
    await db.agent_goals.create_index("id", unique=True)
    await db.ambient_wakes.create_index("identity", unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "claimed"]}})

    created = await create_synthetic_situation(db)
    assert created["status"] == "success"
    sid = created["situation"]["id"]
    goal_id = goal_id_for(OWNER, sid)
    initial = await read_followup(db, OWNER, sid)
    assert initial["status"] == "review_pending"
    assert initial["next_check_at"] is None
    assert initial["goal_id"] == goal_id
    assert (await db.agent_goals.find_one({"id": goal_id}))["source_kind"] == INITIAL_KIND
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal_id}", "status": "pending"}) == 1

    # A model-chosen future checkpoint is distinct from a claim of completion.
    due = (datetime.now(timezone.utc) + timedelta(minutes=22)).isoformat()
    scheduled = await arrange_followup(
        db, OWNER, situation_id=sid, expected_revision=1, check_at=due,
        purpose="Ricontrollare i dati osservabili alla fonte.",
        notify_when="Solo se un rischio richiede azione prima del previsto.",
        completion_when="Quando i dati giustificano una decisione utile.",
    )
    assert scheduled["ok"] is True, scheduled
    assert scheduled["status"] == "scheduled"
    assert scheduled["next_check_at"] == due
    assert await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": f"goal:{goal_id}", "status": "pending"}) == 1
    assert (await db.agent_goals.find_one({"id": goal_id}))["source_kind"] == KIND
    assert (await read_followup(db, OTHER, sid))["status"] == "unavailable"

    goal = await AgentService(db).repo.get_goal(OWNER, goal_id)
    now = datetime.now(timezone.utc)
    weather = AgentEvidence(
        id="evd_unified_live", owner_id=OWNER, goal_id=goal_id,
        claim="Solo osservazione meteo sintetica, NON una misura del processo.",
        provenance=ResultProvenance(
            source_class="external_research", capability="weather.read",
            provider="synthetic-weather", freshness="fresh",
            source_refs=[f"situation:{sid}:revision:1", "google_place:synthetic-source"],
            weather_valid_until=(now + timedelta(minutes=90)).isoformat(),
        ),
    )
    estimate = {
        "status": "estimated",
        "headline": "Finestra utile stimata, non un fatto osservato.",
        "action_summary": "Verifica il risultato prima di agire.",
        "basis": "estimate", "action_reason": None,
        "window_start": (now + timedelta(minutes=50)).isoformat(),
        "window_end": (now + timedelta(minutes=70)).isoformat(),
        "valid_until": (now + timedelta(minutes=40)).isoformat(),
        "evidence_ids": [weather.id],
    }
    assert await validate_assessment(db, OWNER, goal, estimate,
        evidence=[weather]) is None, "weather alone cannot establish a physical rate"

    research = AgentEvidence(
        id="evd_unified_baseline", owner_id=OWNER, goal_id=goal_id,
        observed_at=(now - timedelta(minutes=2)).isoformat(),
        claim="Baseline empirica sintetica, non riferita a un bucato reale.",
        provenance=ResultProvenance(
            source_class="external_research", capability="web.research",
            provider="synthetic-research", freshness="fresh",
            research_sufficient=True, source_refs=["synthetic:baseline"],
            observed_at=(now - timedelta(minutes=2)).isoformat(),
            research_valid_until=(now + timedelta(hours=2)).isoformat(),
        ),
    )
    service = AgentService(db)
    await service.evidence.record(weather)
    await service.evidence.record(research)
    estimate["evidence_ids"] = [research.id, weather.id]
    run = AgentRun(owner_id=OWNER, goal_id=goal_id,
        at=(now - timedelta(seconds=1)).isoformat())
    assert await service._record_situation_outcome(OWNER, goal, estimate, run)
    restored = await service.repo.get_goal(OWNER, goal_id)
    outcome = await current_outcome(db, OWNER, restored)
    assert outcome["status"] == "estimated"
    assert outcome["basis"] == "estimate"
    displayed = await read_followup(db, OWNER, sid)
    assert displayed["outcome"]["status"] == "estimated"
    assert displayed["status"] == "scheduled"
    state = await SituationRepository(db).get(OWNER, sid)
    assert state.status == "active", "an estimate cannot physically resolve a Situation"
    assert await db.delivery_plans.count_documents({}) == 0, "no provider receipt was created"
    assert await db.agent_goals.count_documents({"owner_id": OTHER}) == 0


@pytest.mark.asyncio
async def test_saved_situation_without_runtime_is_not_a_scheduled_monitor(monkeypatch):
    monkeypatch.setenv("AMBIENT_RUNTIME", "0")
    monkeypatch.setattr(OpportunityDiscovery, "note", AsyncMock(return_value={"outcome": "accepted"}))
    db = AsyncMongoMockClient().unified_situation_disabled
    created = await create_synthetic_situation(db, epoch="runtime-disabled")
    assert created["status"] == "success"
    sid = created["situation"]["id"]
    status = await read_followup(db, OWNER, sid)
    assert status["status"] == "not_scheduled"
    assert status["next_check_at"] is None
    assert await db.ambient_wakes.count_documents({}) == 0
    assert await db.agent_goals.count_documents({}) == 0
