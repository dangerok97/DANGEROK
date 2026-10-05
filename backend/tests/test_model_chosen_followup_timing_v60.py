from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.capabilities import CapabilityResolver
from agent.models import (
    ActionPlan,
    ActionStep,
    AgentBudget,
    AgentEvidence,
    AgentRun,
    AutonomousGoal,
    ResultProvenance,
)
from agent.service import AgentService, _wait_hours_for


OWNER = "alice"


def _goal():
    return AutonomousGoal(
        id="goal_timing",
        owner_id=OWNER,
        status="active",
        objective="Seguire un esito futuro senza chiedere un nuovo comando",
        desired_outcome="Rivalutare nel momento utile",
    )


@pytest.mark.asyncio
async def test_weather_is_not_advertised_usable_when_location_is_off(monkeypatch):
    import weather

    db = AsyncMongoMockClient().test
    monkeypatch.setattr(
        weather,
        "capabilities",
        lambda: {"available": True, "provider": "open_meteo"},
    )

    off = await CapabilityResolver(db).resolve(OWNER, "weather.read")
    assert off.permitted is False
    assert off.usable is False
    assert off.status == "requires_connection"
    assert off.reason == "location_not_permitted"

    await db.users.insert_one({
        "user_id": OWNER,
        "settings": {"location_mode": "while_using"},
    })
    on = await CapabilityResolver(db).resolve(OWNER, "weather.read")
    assert on.permitted is True
    assert on.usable is True
    assert on.status == "available_real"


@pytest.mark.asyncio
async def test_choose_next_wait_persists_model_selected_interval(monkeypatch):
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
                id="step_check",
                ordinal=0,
                intent="Controllare di nuovo quando può essere cambiato qualcosa",
                step_type="inspect",
                capability_needed="information.read",
                expected_result="Nuova evidenza",
            )
        ],
    )
    await service.repo.save_goal(goal)
    await service.repo.save_plan(plan)
    await service.evidence.record(AgentEvidence(
        owner_id=OWNER,
        goal_id=goal.id,
        step_id="weather_done",
        claim="Il forecast indica che il prossimo controllo utile è tra due ore.",
        supports="timing del follow-up",
        provenance=ResultProvenance(
            source_class="external_research",
            capability="weather.read",
            provider="open_meteo",
            freshness="fresh",
        ),
    ))

    choose = AsyncMock(return_value={
        "decision": "wait",
        "step_id": "",
        "reasoning": "La finestra utile di rivalutazione è tra due ore.",
        "asks": "",
        "ask_kind": None,
        "wait_hours": 2,
    })
    monkeypatch.setattr(reasoning, "choose_next_action", choose)
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))

    decision, wait_step = await service._next(
        OWNER,
        goal,
        plan,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert decision == "wait"
    assert wait_step is not None
    assert wait_step.step_type == "wait"
    assert wait_step.parameters["wait_hours"] == 2
    assert _wait_hours_for(wait_step) == 2

    persisted = await service.repo.plan_for(OWNER, goal.id)
    assert persisted is not None
    saved_waits = [s for s in persisted.steps if s.step_type == "wait"]
    assert len(saved_waits) == 1
    assert saved_waits[0].parameters["wait_hours"] == 2


@pytest.mark.asyncio
async def test_work_loop_uses_wait_step_interval_not_fixed_six_hours(monkeypatch):
    import agent.source_refresh as source_refresh

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    wait_step = ActionStep(
        id="wait_two_hours",
        ordinal=0,
        intent="Rivalutare quando la previsione diventa utile",
        step_type="wait",
        parameters={"wait_hours": 2},
        expected_result="Nuovo checkpoint",
    )
    plan = ActionPlan(
        id="plan_wait_two",
        owner_id=OWNER,
        goal_id=goal.id,
        status="active",
        steps=[wait_step],
    )
    await service.repo.save_goal(goal)
    await service.repo.save_plan(plan)

    monkeypatch.setattr(source_refresh, "changed", AsyncMock(return_value=False))
    monkeypatch.setattr(
        service,
        "_next",
        AsyncMock(return_value=("wait", wait_step)),
    )
    waiting = AsyncMock(return_value={
        "ok": True,
        "state": "waiting",
        "for_hours": 2,
        "goal": goal.for_human(),
    })
    monkeypatch.setattr(service, "_wait", waiting)

    out = await service._work(
        OWNER,
        goal,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert out["for_hours"] == 2
    waiting.assert_awaited_once()
    assert waiting.await_args.kwargs["hours"] == 2


@pytest.mark.asyncio
async def test_wait_runtime_clamps_model_interval_and_records_it(monkeypatch):
    import ambient.service as ambient_service

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    step = ActionStep(
        id="wait_long",
        ordinal=0,
        intent="Aspettare",
        step_type="wait",
        parameters={"wait_hours": 9999},
    )
    plan = ActionPlan(
        id="plan_clamp",
        owner_id=OWNER,
        goal_id=goal.id,
        status="active",
        steps=[step],
    )
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    class Ambient:
        async def schedule(self, *args, **kwargs):
            return True

    monkeypatch.setattr(ambient_service, "AmbientService", lambda db_: Ambient())

    out = await service._wait(
        OWNER,
        goal,
        plan,
        step,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        hours=_wait_hours_for(step),
        note="checkpoint scelto dal modello",
    )

    assert out["for_hours"] == 336
    journal = await db.agent_journal.find_one(
        {"owner_id": OWNER, "goal_id": goal.id, "kind": "waiting"},
        {"_id": 0},
    )
    assert journal is not None
    assert journal["detail"]["for_hours"] == 336
    assert journal["detail"]["step_id"] == step.id
