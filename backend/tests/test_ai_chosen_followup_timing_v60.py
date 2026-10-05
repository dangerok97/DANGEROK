from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import (
    ActionPlan,
    ActionStep,
    AgentBudget,
    AgentEvidence,
    AgentRun,
    AutonomousGoal,
    ResultProvenance,
)
from agent.service import AgentService


OWNER = "alice"


def _goal():
    return AutonomousGoal(
        id="goal_timing",
        owner_id=OWNER,
        status="active",
        objective="Seguire un esito futuro senza chiedere un nuovo comando",
        desired_outcome="Ricontrollare nel momento più utile",
        source_refs=["situation:sit_1"],
    )


@pytest.mark.asyncio
async def test_ai_wait_choice_becomes_persisted_timed_checkpoint(monkeypatch):
    from agent import reasoning

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    plan = ActionPlan(
        id="plan_timing",
        owner_id=OWNER,
        goal_id=goal.id,
        status="active",
        steps=[
            ActionStep(
                id="inspect_done",
                ordinal=0,
                intent="Leggere il contesto disponibile",
                step_type="inspect",
                capability_needed="weather.read",
                status="succeeded",
            ),
            ActionStep(
                id="verify_later",
                ordinal=1,
                intent="Verificare di nuovo quando il contesto può essere cambiato",
                step_type="verify",
                capability_needed="weather.read",
                status="pending",
            ),
        ],
    )
    evidence = AgentEvidence(
        owner_id=OWNER,
        goal_id=goal.id,
        step_id="inspect_done",
        claim="La previsione attuale copre le prossime ore.",
        supports="Capire quando vale la pena rileggere.",
        provenance=ResultProvenance(
            source_class="external_research",
            capability="weather.read",
            provider="open_meteo",
            freshness="fresh",
        ),
    )

    monkeypatch.setattr(service.evidence, "for_goal", AsyncMock(return_value=[evidence]))
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        reasoning,
        "choose_next_action",
        AsyncMock(return_value={
            "decision": "wait",
            "step_id": "",
            "reasoning": "Fra due ore una nuova lettura può aggiungere informazione reale.",
            "asks": "",
            "ask_kind": None,
            "wait_hours": 2,
        }),
    )

    decision, step = await service._next(
        OWNER,
        goal,
        plan,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert decision == "wait"
    assert step is not None
    assert step.step_type == "wait"
    assert step.parameters["wait_hours"] == 2
    assert "due ore" in step.intent.lower()
    assert plan.steps[-1].id == step.id
    assert plan.steps[-1].for_ai()["wait_hours"] == 2


@pytest.mark.asyncio
async def test_existing_wait_step_uses_its_own_hours_in_runtime(monkeypatch):
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    plan = ActionPlan(
        id="plan_existing_wait",
        owner_id=OWNER,
        goal_id=goal.id,
        status="active",
        steps=[
            ActionStep(
                id="wait_3h",
                ordinal=0,
                intent="Aspettare tre ore prima di rileggere la situazione",
                step_type="wait",
                parameters={"wait_hours": 3},
                expected_result="È arrivato il momento di verificare di nuovo",
            )
        ],
    )
    await service.repo.save_goal(goal)
    await service.repo.save_plan(plan)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    before = datetime.now(timezone.utc)
    out = await service._work(
        OWNER,
        goal,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert out["state"] == "waiting"
    assert out["for_hours"] == 3
    saved = await service.repo.get_goal(OWNER, goal.id)
    assert saved is not None
    assert saved.status == "waiting"
    assert saved.next_run_at is not None
    delta = datetime.fromisoformat(saved.next_run_at) - before
    assert 2.9 <= delta.total_seconds() / 3600 <= 3.1

    saved_plan = await service.repo.plan_for(OWNER, goal.id)
    assert saved_plan is not None
    wait_step = next(s for s in saved_plan.steps if s.id == "wait_3h")
    assert wait_step.status == "waiting"


@pytest.mark.asyncio
async def test_model_wait_interval_is_bounded_before_it_enters_plan(monkeypatch):
    from agent import reasoning

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    plan = ActionPlan(
        id="plan_bounded_wait",
        owner_id=OWNER,
        goal_id=goal.id,
        status="active",
        steps=[
            ActionStep(
                id="open_step",
                ordinal=0,
                intent="Passo ancora aperto",
                step_type="verify",
                capability_needed="information.read",
            )
        ],
    )
    evidence = AgentEvidence(
        owner_id=OWNER,
        goal_id=goal.id,
        claim="C'è già evidenza da cui scegliere quando ricontrollare.",
        provenance=ResultProvenance(
            source_class="internal_observation",
            capability="information.read",
        ),
    )
    monkeypatch.setattr(service.evidence, "for_goal", AsyncMock(return_value=[evidence]))
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        reasoning,
        "choose_next_action",
        AsyncMock(return_value={
            "decision": "wait",
            "reasoning": "Aspettare molto a lungo.",
            "wait_hours": 9999,
            "step_id": "",
            "asks": "",
            "ask_kind": None,
        }),
    )

    decision, step = await service._next(
        OWNER,
        goal,
        plan,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert decision == "wait"
    assert step is not None
    assert step.parameters["wait_hours"] == 336

