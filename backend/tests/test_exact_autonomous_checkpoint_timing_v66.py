from datetime import datetime, timedelta, timezone
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
from agent.service import (
    AgentService,
    MAX_WAIT_HOURS,
    _bounded_wait_until,
)


OWNER = "alice"
NOW = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
CLOCK = {
    "local_datetime": "2026-10-05T12:00:00+02:00",
    "local_time": "12:00",
    "local_date": "2026-10-05",
    "timezone": "Europe/Rome",
    "authority": "user_confirmed",
    "today": "2026-10-05",
    "today_weekday": "Monday",
}


def _goal():
    return AutonomousGoal(
        id="goal_exact_wait",
        owner_id=OWNER,
        status="active",
        objective="Ricontrollare nel momento locale utile",
        desired_outcome="Rileggere la situazione al momento giusto",
    )


def test_exact_checkpoint_requires_timezone_and_is_bounded():
    exact = _bounded_wait_until("2026-10-05T18:30:00+02:00", now=NOW)
    assert exact == datetime(2026, 10, 5, 16, 30, tzinfo=timezone.utc)

    assert _bounded_wait_until("2026-10-05T18:30:00", now=NOW) is None
    assert _bounded_wait_until("2026-10-05T09:59:00+00:00", now=NOW) is None

    too_close = _bounded_wait_until("2026-10-05T10:00:30+00:00", now=NOW)
    assert too_close == NOW + timedelta(minutes=1)

    too_far = _bounded_wait_until("2026-11-20T12:00:00+00:00", now=NOW)
    assert too_far == NOW + timedelta(hours=MAX_WAIT_HOURS)


@pytest.mark.asyncio
async def test_exact_wait_schedules_the_same_instant_and_uses_14_day_horizon(monkeypatch):
    import agent.service as agent_service
    import ambient.service as ambient_service

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    step = ActionStep(
        id="wait_exact",
        ordinal=0,
        intent="Ricontrollare alle 18:30 locali",
        step_type="wait",
        parameters={},
    )
    plan = ActionPlan(
        id="plan_exact",
        goal_id=goal.id,
        owner_id=OWNER,
        status="active",
        steps=[step],
    )

    seen = {}

    class Ambient:
        async def schedule(self, owner_id, **kwargs):
            seen["owner_id"] = owner_id
            seen.update(kwargs)
            return True

    monkeypatch.setattr(agent_service, "_now", lambda: NOW)
    monkeypatch.setattr(ambient_service, "AmbientService", lambda db_: Ambient())
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    out = await service._wait(
        OWNER,
        goal,
        plan,
        step,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        hours=6,
        wait_until="2026-10-05T18:30:00+02:00",
        note="Checkpoint preciso.",
    )

    target = datetime(2026, 10, 5, 16, 30, tzinfo=timezone.utc)
    assert out["state"] == "waiting"
    assert out["timing"] == "exact"
    assert out["until"] == target.isoformat()
    assert out["for_minutes"] == 390
    assert goal.next_run_at == target.isoformat()
    assert step.parameters["wait_until"] == target.isoformat()
    assert seen["when"] == target
    assert seen["max_horizon_hours"] == MAX_WAIT_HOURS
    assert seen["source_ref"] == f"goal:{goal.id}"


@pytest.mark.asyncio
async def test_long_relative_wait_no_longer_gets_ambient_72_hour_clamp(monkeypatch):
    import agent.service as agent_service
    import ambient.service as ambient_service

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    plan = ActionPlan(
        id="plan_long_wait",
        goal_id=goal.id,
        owner_id=OWNER,
        status="active",
        steps=[],
    )
    seen = {}

    class Ambient:
        async def schedule(self, owner_id, **kwargs):
            seen.update(kwargs)
            return True

    monkeypatch.setattr(agent_service, "_now", lambda: NOW)
    monkeypatch.setattr(ambient_service, "AmbientService", lambda db_: Ambient())
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    out = await service._wait(
        OWNER,
        goal,
        plan,
        None,
        AgentRun(owner_id=OWNER, goal_id=goal.id, background=True),
        hours=24 * 7,
        note="Fra una settimana.",
    )

    target = NOW + timedelta(days=7)
    assert out["timing"] == "relative"
    assert out["for_hours"] == 168
    assert goal.next_run_at == target.isoformat()
    assert seen["when"] == target
    assert seen["max_horizon_hours"] == MAX_WAIT_HOURS


@pytest.mark.asyncio
async def test_next_action_exact_checkpoint_is_persisted_in_wait_step(monkeypatch):
    import agent.service as agent_service
    from agent import reasoning

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    open_step = ActionStep(
        id="verify_later",
        ordinal=0,
        intent="Rileggere la situazione",
        step_type="verify",
        capability_needed="weather.read",
        status="pending",
    )
    plan = ActionPlan(
        id="plan_choose_exact",
        goal_id=goal.id,
        owner_id=OWNER,
        status="active",
        steps=[open_step],
    )
    evidence = AgentEvidence(
        owner_id=OWNER,
        goal_id=goal.id,
        step_id="earlier",
        claim="Il prossimo dato utile sarà disponibile nel tardo pomeriggio.",
        provenance=ResultProvenance(
            source_class="internal_observation",
            capability="information.read",
        ),
    )

    monkeypatch.setattr(agent_service, "_now", lambda: NOW)
    monkeypatch.setattr(
        agent_service,
        "_user_clock_context",
        AsyncMock(return_value=dict(CLOCK)),
    )
    monkeypatch.setattr(service.evidence, "for_goal", AsyncMock(return_value=[evidence]))
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        reasoning,
        "choose_next_action",
        AsyncMock(return_value={
            "decision": "wait",
            "step_id": "",
            "reasoning": "Ricontrollare alle 18:30 locali.",
            "wait_hours": 6,
            "wait_until": "2026-10-05T18:30:00+02:00",
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
    assert step.parameters["wait_until"] == "2026-10-05T16:30:00+00:00"
    assert step.for_ai()["wait_until"] == "2026-10-05T16:30:00+00:00"


@pytest.mark.asyncio
async def test_invalid_exact_checkpoint_falls_back_to_relative_wait(monkeypatch):
    import agent.service as agent_service
    from agent import reasoning

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    plan = ActionPlan(
        id="plan_fallback",
        goal_id=goal.id,
        owner_id=OWNER,
        status="active",
        steps=[
            ActionStep(
                id="verify_later",
                ordinal=0,
                intent="Rileggere",
                step_type="verify",
                status="pending",
            )
        ],
    )
    evidence = AgentEvidence(
        owner_id=OWNER,
        goal_id=goal.id,
        claim="Serve aspettare.",
        provenance=ResultProvenance(source_class="internal_observation"),
    )

    monkeypatch.setattr(agent_service, "_now", lambda: NOW)
    monkeypatch.setattr(
        agent_service,
        "_user_clock_context",
        AsyncMock(return_value=dict(CLOCK)),
    )
    monkeypatch.setattr(service.evidence, "for_goal", AsyncMock(return_value=[evidence]))
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        reasoning,
        "choose_next_action",
        AsyncMock(return_value={
            "decision": "wait",
            "reasoning": "Aspettare due ore.",
            "wait_hours": 2,
            "wait_until": "2026-10-05T18:30:00",
        }),
    )

    decision, step = await service._next(
        OWNER,
        goal,
        plan,
        AgentRun(owner_id=OWNER, goal_id=goal.id),
        AgentBudget(),
        language="it",
    )

    assert decision == "wait"
    assert step is not None
    assert step.parameters["wait_hours"] == 2
    assert "wait_until" not in step.parameters


@pytest.mark.asyncio
async def test_verification_can_choose_precise_revisit_using_local_clock(monkeypatch):
    from agent import reasoning

    captured = {}

    async def ask_model(system, user):
        captured["system"] = system
        captured["user"] = user
        return {
            "outcome": "waiting_for_external_result",
            "reasoning": "Ricontrollare alle 18:30 locali.",
            "what_is_missing": "Serve il nuovo esito.",
            "revisit_in_hours": None,
            "revisit_at": "2026-10-05T18:30:00+02:00",
            "relied_on": [],
            "criteria_met": [],
        }

    monkeypatch.setattr(reasoning, "_ask_model", ask_model)
    result = await reasoning.verify_goal(
        {"objective": "Seguire l'esito"},
        evidence={"what_was_found": []},
        clock_context=dict(CLOCK),
        language="it",
    )

    assert result is not None
    assert result["revisit_at"] == "2026-10-05T18:30:00+02:00"
    assert '"local_time": "12:00"' in captured["user"]
    assert "revisit_at" in captured["system"]
