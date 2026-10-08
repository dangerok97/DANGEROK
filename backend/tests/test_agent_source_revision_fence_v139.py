"""v139: stale source revisions must never create an actionable autonomous goal.

All sources, owners and model answers are synthetic. These tests exercise
production admission, owner-scoped Mongo persistence and wake scheduling.
"""
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.admission import drain
from agent.repository import AgentRepository
from agent.service import AgentService
from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository


def goal_answer():
    return {
        "outcome": "create_goal",
        "objective": "Verificare la fonte prima di agire",
        "desired_outcome": "Proposta basata sui fatti correnti",
        "reasoning": "Serve esaminare i cambiamenti verificati",
    }


async def saved_source(db, owner="alice"):
    return await OpportunityRepository(db).save(Opportunity(
        owner_id=owner, identity_key="v139-source-" + owner,
        status="active", semantic_summary="Appuntamento confermato alle 15:00",
        why_it_matters="Cambia una decisione nel calendario",
        initiative="prepare",
    ))


@pytest.mark.asyncio
async def test_revised_during_model_reasoning_never_spawns_stale_goal(monkeypatch):
    db = AsyncMongoMockClient().source_revision_v139
    repo = OpportunityRepository(db)
    source = await saved_source(db)
    before = await db.opportunities.find_one({"id": source.id})
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())

    async def changed_during_model(*args, **kwargs):
        source.semantic_summary = "La comunicazione è stata corretta: ore 16:30"
        await repo.save(source)
        return goal_answer()

    monkeypatch.setattr(reasoning, "decide_goal", changed_during_model)
    assert await drain(db, owner_id="alice", limit=1) == 1
    saved = await db.opportunities.find_one({"id": source.id})
    assert saved["agent_review_revision"] != before["agent_review_revision"]
    assert saved["agent_review_state"] == "pending"
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0

    monkeypatch.setattr(reasoning, "decide_goal", AsyncMock(return_value=goal_answer()))
    assert await drain(db, owner_id="alice", limit=1) == 1
    goals = await db.agent_goals.find({"owner_id": "alice"}).to_list(3)
    assert len(goals) == 1 and goals[0]["status"] == "active"
    assert goals[0]["opportunity_revision"] == saved["agent_review_revision"]
    assert await db.ambient_wakes.count_documents({
        "owner_id": "alice", "source_ref": "goal:" + goals[0]["id"],
        "status": "pending",
    }) == 1


@pytest.mark.asyncio
async def test_closed_during_model_reasoning_does_not_start_work(monkeypatch):
    db = AsyncMongoMockClient().closed_source_v139
    source = await saved_source(db)
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())

    async def resolved(*args, **kwargs):
        source.status = "resolved"
        await OpportunityRepository(db).save(source)
        return goal_answer()

    monkeypatch.setattr(reasoning, "decide_goal", resolved)
    assert await drain(db, owner_id="alice", limit=1) == 1
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0
    assert (await db.opportunities.find_one({"id": source.id}))["status"] == "resolved"


@pytest.mark.asyncio
async def test_reclaimed_admission_token_rejects_old_workers_goal(monkeypatch):
    db = AsyncMongoMockClient().old_worker_v139
    source = await saved_source(db)
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())

    async def reclaimed(*args, **kwargs):
        await db.opportunities.update_one(
            {"id": source.id}, {"$set": {"agent_review_token": "new-worker-owns-the-claim"}}
        )
        return goal_answer()

    monkeypatch.setattr(reasoning, "decide_goal", reclaimed)
    assert await drain(db, owner_id="alice", limit=1) == 1
    assert await db.agent_goals.count_documents({}) == 0
    assert await db.ambient_wakes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_revision_change_between_validation_and_insert_abandons_draft(monkeypatch):
    db = AsyncMongoMockClient().write_race_v139
    source = await saved_source(db)
    repo = OpportunityRepository(db)
    monkeypatch.setattr(AgentService, "_note_ambient", AsyncMock())
    monkeypatch.setattr(reasoning, "decide_goal", AsyncMock(return_value=goal_answer()))
    original_create = AgentRepository.create_goal

    async def source_changes_after_insert(self, goal):
        inserted = await original_create(self, goal)
        source.semantic_summary = "Nuova comunicazione valida, decisione vecchia annullata"
        await repo.save(source)
        return inserted

    monkeypatch.setattr(AgentRepository, "create_goal", source_changes_after_insert)
    assert await drain(db, owner_id="alice", limit=1) == 1
    obsolete = await db.agent_goals.find_one({"owner_id": "alice"})
    assert obsolete and obsolete["status"] == "abandoned"
    assert obsolete["next_run_at"] is None
    assert await db.ambient_wakes.count_documents({}) == 0

    monkeypatch.setattr(AgentRepository, "create_goal", original_create)
    assert await drain(db, owner_id="alice", limit=1) == 1
    goals = await db.agent_goals.find({"owner_id": "alice"}).to_list(3)
    current = [g for g in goals if g["status"] == "active"]
    assert len(goals) == 2 and len(current) == 1
    assert current[0]["opportunity_revision"] == (
        await db.opportunities.find_one({"id": source.id})
    )["agent_review_revision"]
