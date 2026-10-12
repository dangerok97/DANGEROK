from unittest.mock import AsyncMock
import pytest
from mongomock_motor import AsyncMongoMockClient
from agent import reasoning
from agent.models import AutonomousGoal, ActionStep, ActionPlan, AgentRun, AgentBudget, AgentEvidence
from agent.service import AgentService, _InvalidNextSelection

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
    before = plan.model_dump()
    with pytest.raises(_InvalidNextSelection, match="action_selection_invalid") as rejected:
        await service._next("alice", goal, plan, AgentRun(owner_id="alice"), AgentBudget(), language="it")
    assert rejected.value.context == {
        "problem": "action_selection_invalid",
        "selection": {"decision": "execute", "issue": "not_pending",
                      "requested_step_id": old.id, "candidate_step_ids": [pending.id]},
    }
    # Neither the historical step nor a different pending step is selected
    # or rewritten. The worker owns the subsequent bounded reconsideration.
    assert plan.model_dump() == before
    assert old.status == previous_status

@pytest.mark.asyncio
async def test_cognitive_budget_exhaustion_does_not_finish_pending_plan(monkeypatch):
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = AutonomousGoal(
        owner_id="alice",
        objective="Prepara risultato",
        desired_outcome="Risultato utile",
    )
    pending = ActionStep(intent="Passo ancora da fare", step_type="prepare")
    plan = ActionPlan(owner_id="alice", goal_id=goal.id, steps=[pending])
    monkeypatch.setattr(
        service.evidence,
        "for_goal",
        AsyncMock(return_value=[
            AgentEvidence(owner_id="alice", goal_id=goal.id, claim="Fonte letta")
        ]),
    )
    budget = AgentBudget()
    budget.cognitive_calls = budget.max_cognitive_calls

    decision, chosen = await service._next(
        "alice", goal, plan, AgentRun(owner_id="alice"), budget, language="it"
    )

    assert decision == "budget"
    assert chosen is None
    assert pending.status == "pending"
