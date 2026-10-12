"""An accepted useful outcome retires obsolete work, preserving its history."""
from unittest.mock import AsyncMock, patch

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.models import ActionPlan, ActionStep, AgentRun, AutonomousGoal
from agent.service import AgentService
from scripts import autonomy_completion_eval_v162 as gate


VERIFY_NOW = {"decision": "verify", "reasoning": "Verificare il risultato sulle fonti già lette."}


@pytest.mark.asyncio
async def test_early_verification_delivers_the_result_and_retires_the_unused_step():
    db = AsyncMongoMockClient().terminal_result
    with gate.isolated_engine(db) as probe:
        await gate.seed_case(db, "completed_result")
        goal_id = await gate.admit(db, "completed_result")
        await gate.first_read(db, goal_id, probe)
        service = AgentService(db)
        before = await service.repo.plan_for(gate.OWNER, goal_id)
        read, pending = before.steps
        assert read.status == "succeeded" and pending.status == "pending"
        read_history = read.model_dump()
        choose = AsyncMock(return_value=VERIFY_NOW)

        with patch.object(reasoning, "choose_next_action", choose):
            await gate.fire_due(db, goal_id, probe)

        after = await service.repo.plan_for(gate.OWNER, goal_id)
        unused = after.step(pending.id)
        assert unused.status == "skipped" and unused.attempts == 0
        assert unused.actual_result_ref == pending.actual_result_ref
        assert "verificat" in unused.note and "non è più necessario" in unused.note
        assert after.step(read.id).model_dump() == read_history
        assert len(after.steps) == len(before.steps) + 1
        assert after.steps[-1].status == "succeeded" and after.steps[-1].attempts == 1
        choose.assert_awaited_once()
        # The original prepare step never executes merely to tidy the plan.
        assert [row["capability"] for row in probe.steps] == ["information.read", "document.create"]
        result = await gate.verify_result(db, goal_id, probe)
        assert result["semantic_review"]["passed"]
        assert result["home_delivered"] and result["replay_idempotent"] and result["owner_isolation"]


@pytest.mark.asyncio
async def test_uncertain_verifier_keeps_the_goal_and_original_step_open():
    db = AsyncMongoMockClient().terminal_uncertain
    with gate.isolated_engine(db) as probe:
        await gate.seed_case(db, "completed_result")
        goal_id = await gate.admit(db, "completed_result")
        await gate.first_read(db, goal_id, probe)
        service = AgentService(db)
        original = await service.repo.plan_for(gate.OWNER, goal_id)
        pending = original.steps[1].model_dump()
        verify = AsyncMock(return_value={
            "outcome": "uncertain", "reasoning": "Il risultato richiede ancora una verifica.",
            "what_is_missing": "La verifica non consente ancora di concludere.",
        })

        with patch.object(reasoning, "choose_next_action", AsyncMock(return_value=VERIFY_NOW)), \
                patch.object(reasoning, "verify_goal", verify):
            await gate.fire_due(db, goal_id, probe)

        goal = await service.repo.get_goal(gate.OWNER, goal_id)
        plan = await service.repo.plan_for(gate.OWNER, goal_id)
        assert goal.is_open and not goal.completed_at
        assert plan.status == "active"
        assert plan.step(pending["id"]).model_dump() == pending
        assert not any(step.status == "skipped" for step in plan.steps)
        verify.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("unfinished", ["pending", "running", "blocked", "waiting"])
async def test_accepted_closure_preserves_terminal_steps_and_attempt_result_history(unfinished):
    db = AsyncMongoMockClient().terminal_history
    service = AgentService(db)
    await service.ensure_indexes()
    goal = AutonomousGoal(owner_id=gate.OWNER, status="active", objective="Raggiungere l'esito verificato.",
                          desired_outcome="Un risultato sostenuto dalle fonti.")
    await service.repo.create_goal(goal)
    historical = [ActionStep(
        intent="Passo storico", step_type="inspect", status=status, attempts=3,
        actual_result_ref=f"result_{status}", note=f"Nota storica: {status}",
    ) for status in ("succeeded", "failed", "skipped")]
    unused = ActionStep(intent="Passo residuo", step_type="prepare", status=unfinished,
                        attempts=2, actual_result_ref="previous_result", note="Nota prima della chiusura.")
    plan = ActionPlan(owner_id=gate.OWNER, goal_id=goal.id, status="active", steps=[*historical, unused])
    await service.repo.save_plan(plan)
    history = [step.model_dump() for step in historical]

    result = await service._close(gate.OWNER, goal, plan, AgentRun(owner_id=gate.OWNER),
                                  "completed", "Esito verificato dalle fonti.")

    assert result["state"] == "completed"
    saved = await service.repo.plan_for(gate.OWNER, goal.id)
    assert saved.status == "completed"
    assert [step.model_dump() for step in saved.steps[:3]] == history
    assert saved.step(unused.id).status == "skipped"
    assert saved.step(unused.id).attempts == 2
    assert saved.step(unused.id).actual_result_ref == "previous_result"
    assert await db.agent_action_attempts.count_documents({}) == 0


@pytest.mark.asyncio
async def test_cancelled_goal_write_never_retires_steps_as_a_verified_completion(monkeypatch):
    db = AsyncMongoMockClient().terminal_cancel_race
    service = AgentService(db)
    await service.ensure_indexes()
    goal = AutonomousGoal(owner_id=gate.OWNER, status="active", objective="Verificare il risultato.",
                          desired_outcome="Una conclusione sostenuta dalle fonti.")
    await service.repo.create_goal(goal)
    pending = ActionStep(intent="Passo ancora pendente", step_type="prepare")
    plan = ActionPlan(owner_id=gate.OWNER, goal_id=goal.id, status="active", steps=[pending])
    await service.repo.save_plan(plan)
    original_save = service.repo.save_goal

    async def cancelled_while_saving(current):
        await db.agent_goals.update_one({"owner_id": gate.OWNER, "id": current.id},
                                        {"$set": {"status": "cancelled"}})
        return await original_save(current)

    monkeypatch.setattr(service.repo, "save_goal", cancelled_while_saving)
    result = await service._close(gate.OWNER, goal, plan, AgentRun(owner_id=gate.OWNER),
                                  "completed", "Esito verificato dalle fonti.")

    assert result["state"] == "cancelled"
    saved = await service.repo.plan_for(gate.OWNER, goal.id)
    assert saved.status == "active"
    assert saved.step(pending.id).model_dump() == pending.model_dump()
    assert pending.status == "pending"
