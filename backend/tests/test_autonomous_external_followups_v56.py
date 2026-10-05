from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal
from agent.service import AgentService


def _goal(*, background_runs=2):
    return AutonomousGoal(
        id="goal_followup",
        owner_id="alice",
        status="waiting",
        objective="Sapere se è arrivata la conferma attesa",
        desired_outcome="La conferma è verificata da una fonte reale",
        success_criteria=["La fonte collegata mostra l'esito"],
        source_kind="opportunity",
        source_refs=["mail:m1"],
        next_run_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        background_runs=background_runs,
    )


@pytest.mark.asyncio
async def test_due_checkpoint_reactivates_waiting_provider_step():
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    step = ActionStep(
        id="step_mail",
        ordinal=0,
        intent="Rileggere la comunicazione attesa",
        step_type="inspect",
        status="waiting",
        capability_needed="mail.metadata",
        expected_result="Sapere se è arrivata una risposta",
    )
    plan = ActionPlan(
        id="plan_followup",
        goal_id=goal.id,
        owner_id=goal.owner_id,
        status="waiting",
        plan_summary="Aspettare e poi rileggere la fonte.",
        steps=[step],
    )
    await service.repo.save_goal(goal)
    await service.repo.save_plan(plan)

    out = await service._resume_due_wait(
        "alice",
        goal,
        plan,
        AgentRun(owner_id="alice", goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert out is None
    assert goal.status == "active"
    assert plan.status == "active"
    assert plan.steps[0].status == "pending"
    assert goal.next_run_at is None

    journal = await db.agent_journal.find_one(
        {"owner_id": "alice", "goal_id": goal.id, "kind": "external_checkpoint_due"},
        {"_id": 0},
    )
    assert journal is not None


@pytest.mark.asyncio
async def test_elapsed_timer_never_counts_as_external_result(monkeypatch):
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    step = ActionStep(
        id="step_wait",
        ordinal=0,
        intent="Aspettare che il mondo possa cambiare",
        step_type="wait",
        status="waiting",
        expected_result="È arrivato il momento di controllare di nuovo",
    )
    plan = ActionPlan(
        id="plan_followup",
        goal_id=goal.id,
        owner_id=goal.owner_id,
        status="waiting",
        steps=[step],
    )

    reconsider = AsyncMock(return_value=None)
    rewait = AsyncMock(return_value={"ok": True, "state": "waiting", "for_hours": 6})
    monkeypatch.setattr(service, "_reconsider", reconsider)
    monkeypatch.setattr(service, "_wait", rewait)

    out = await service._resume_due_wait(
        "alice",
        goal,
        plan,
        AgentRun(owner_id="alice", goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert plan.steps[0].status == "succeeded"
    reconsider.assert_awaited_once()
    happened = reconsider.await_args.kwargs["what_happened"]
    assert happened["problem"] == "scheduled_external_checkpoint"
    assert "non prova" in happened["what_happened"]
    rewait.assert_awaited_once()
    assert out["state"] == "waiting"


@pytest.mark.asyncio
async def test_new_deliberate_wait_opens_fresh_background_burst(monkeypatch):
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal(background_runs=3)
    goal.status = "active"
    step = ActionStep(
        id="step_wait",
        ordinal=0,
        intent="Aspettare una risposta esterna",
        step_type="wait",
    )
    plan = ActionPlan(
        id="plan_followup",
        goal_id=goal.id,
        owner_id=goal.owner_id,
        status="active",
        steps=[step],
    )
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    class Ambient:
        async def schedule(self, *args, **kwargs):
            return True

    import ambient.service as ambient_service
    monkeypatch.setattr(ambient_service, "AmbientService", lambda db_: Ambient())

    out = await service._wait(
        "alice",
        goal,
        plan,
        step,
        AgentRun(owner_id="alice", goal_id=goal.id, background=True),
        hours=12,
        note="Aspetto una risposta.",
    )

    assert out["state"] == "waiting"
    assert goal.background_runs == 0
    assert goal.status == "waiting"
    assert step.status == "waiting"
    assert goal.next_run_at is not None


@pytest.mark.asyncio
async def test_reconsider_contract_says_checkpoint_requires_fresh_evidence(monkeypatch):
    from agent import reasoning

    ask = AsyncMock(return_value={
        "decision": "wait",
        "reasoning": "La fonte non ha ancora dato un nuovo esito.",
        "replace_step_ids": [],
        "revised_steps": [],
        "wait_hours": 6,
        "asks": "",
        "ask_kind": None,
    })
    monkeypatch.setattr(reasoning, "_ask_model", ask)

    answer = await reasoning.reconsider(
        {"objective": "Verificare una risposta esterna"},
        plan={"steps": []},
        what_happened={"problem": "scheduled_external_checkpoint"},
        capabilities=[{"capability": "mail.metadata", "status": "available_real"}],
    )

    assert answer["decision"] == "wait"
    instruction = ask.await_args.args[0]
    assert "elapsed time is NOT evidence" in instruction
    assert "Never choose complete" in instruction
