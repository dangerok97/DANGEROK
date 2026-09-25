from unittest.mock import AsyncMock
import pytest
from mongomock_motor import AsyncMongoMockClient
from agent import reasoning
from agent.models import AutonomousGoal, ActionStep, ActionPlan, AgentRun, AgentBudget, AgentEvidence
from agent.service import AgentService

@pytest.mark.asyncio
@pytest.mark.parametrize("previous_status", ["succeeded", "failed", "skipped"])
async def test_model_cannot_reexecute_a_step_outside_pending_candidates(monkeypatch, previous_status):
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = AutonomousGoal(owner_id="alice", objective="Prepara risultato", desired_outcome="Risultato utile")
    old = ActionStep(intent="Passo storico", step_type="inspect", status=previous_status)
    pending = ActionStep(intent="Passo ancora da fare", step_type="prepare")
    plan = ActionPlan(owner_id="alice", goal_id=goal.id, steps=[old, pending])
    monkeypatch.setattr(service.evidence, "for_goal", AsyncMock(return_value=[AgentEvidence(owner_id="alice", goal_id=goal.id, claim="Fonte letta")]))
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))
    monkeypatch.setattr(reasoning, "choose_next_action", AsyncMock(return_value={"decision": "execute", "step_id": old.id}))
    decision, chosen = await service._next("alice", goal, plan, AgentRun(owner_id="alice"), AgentBudget(), language="it")
    assert decision == "execute" and chosen.id == pending.id
    assert old.status == previous_status
