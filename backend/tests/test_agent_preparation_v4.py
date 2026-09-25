import json
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.models import AutonomousGoal, ActionStep, AgentEvidence, ResultProvenance
from agent.providers import prepare_locally


async def fixture(with_evidence=True):
    db = AsyncMongoMockClient().test
    goal = AutonomousGoal(owner_id="alice", objective="Riassumi condizioni", desired_outcome="Bozza con costi e limiti", status="active")
    await db.agent_goals.insert_one(goal.model_dump())
    evidence = AgentEvidence(owner_id="alice", goal_id=goal.id, claim="Il documento indica 120 euro annui senza rimborso.",
        provenance=ResultProvenance(source_class="internal_observation", provider="documents", source_refs=["document:d1"]))
    if with_evidence:
        await db.agent_evidence.insert_one(evidence.model_dump())
    return db, goal, evidence, ActionStep(intent="Prepara riepilogo", step_type="prepare")


@pytest.mark.asyncio
async def test_preparation_saves_actual_content_and_sources_before_success(monkeypatch):
    db, goal, evidence, step = await fixture()
    content = "Costo dichiarato: 120 euro annui. I mesi inutilizzati non sono rimborsati."
    async def model(system, payload):
        assert json.loads(payload)["evidence"][0]["id"] == evidence.id
        return {"content": content, "evidence_ids": [evidence.id]}
    monkeypatch.setattr(reasoning, "_ask_model", model)
    result = await prepare_locally(db, "alice", goal, step)
    saved = await db.agent_goals.find_one({"id": goal.id})
    assert result.status == "succeeded"
    assert saved["prepared_text"] == goal.for_human()["prepared_text"] == content
    assert saved["prepared_sources"] == [evidence.id]
    assert content in result.claims[0].text
    assert result.provenance.provider == "generated_draft"


@pytest.mark.asyncio
async def test_no_evidence_cannot_become_ready(monkeypatch):
    db, goal, evidence, step = await fixture(False)
    model = AsyncMock()
    monkeypatch.setattr(reasoning, "_ask_model", model)
    assert (await prepare_locally(db, "alice", goal, step)).error_type == "preparation_sources_required"
    model.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [None, {"content": "Pronto", "evidence_ids": ["invented"]}, {"content": "", "evidence_ids": []}])
async def test_failed_or_ungrounded_draft_never_reports_success(monkeypatch, answer):
    db, goal, evidence, step = await fixture()
    monkeypatch.setattr(reasoning, "_ask_model", AsyncMock(return_value=answer))
    result = await prepare_locally(db, "alice", goal, step)
    assert result.status == "unavailable" and not result.claims and not goal.prepared_text


@pytest.mark.asyncio
async def test_owner_and_closed_goal_are_protected(monkeypatch):
    db, goal, evidence, step = await fixture()
    monkeypatch.setattr(reasoning, "_ask_model", AsyncMock(return_value={"content": "Bozza", "evidence_ids": [evidence.id]}))
    assert (await prepare_locally(db, "bob", goal, step)).error_type == "preparation_owner_mismatch"
    await db.agent_goals.update_one({"id": goal.id}, {"$set": {"status": "cancelled"}})
    assert (await prepare_locally(db, "alice", goal, step)).error_type == "preparation_goal_unavailable"


@pytest.mark.asyncio
async def test_generated_draft_cannot_cite_itself_as_independent_source(monkeypatch):
    db, goal, evidence, step = await fixture()
    await db.agent_evidence.update_one({"id": evidence.id}, {"$set": {"provenance.provider": "generated_draft"}})
    result = await prepare_locally(db, "alice", goal, step)
    assert result.error_type == "preparation_sources_required"
