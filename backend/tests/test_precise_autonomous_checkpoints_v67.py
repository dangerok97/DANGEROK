from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, ActionStep, AgentBudget, AgentEvidence, AgentRun, AutonomousGoal, ResultProvenance
from agent.service import (
    AgentService,
    MAX_WAIT_MINUTES,
    MIN_WAIT_MINUTES,
    _wait_target,
)


OWNER = "alice"


def goal():
    return AutonomousGoal(
        id="goal_precise_wait",
        owner_id=OWNER,
        status="active",
        objective="Ricontrollare nel momento esatto utile",
        desired_outcome="Non arrivare né troppo presto né troppo tardi",
    )


def plan_with(step):
    return ActionPlan(
        id="plan_precise_wait",
        owner_id=OWNER,
        goal_id="goal_precise_wait",
        status="active",
        steps=[step],
    )


def test_wait_target_prefers_exact_offset_aware_moment():
    now = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    target, minutes, source = _wait_target(
        {"wait_until": "2026-10-05T13:20:00+02:00", "wait_minutes": 90, "wait_hours": 4},
        now=now,
    )
    assert target == datetime(2026, 10, 5, 11, 20, tzinfo=timezone.utc)
    assert minutes == 80
    assert source == "wait_until"


def test_precise_waits_are_bounded_and_naive_exact_times_are_not_guessed():
    now = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)

    soon, soon_minutes, source = _wait_target(
        {"wait_until": "2026-10-05T10:01:00+00:00"}, now=now
    )
    assert source == "wait_until"
    assert soon_minutes == MIN_WAIT_MINUTES
    assert soon == now + timedelta(minutes=MIN_WAIT_MINUTES)

    far, far_minutes, source = _wait_target(
        {"wait_until": "2027-01-05T10:00:00+00:00"}, now=now
    )
    assert source == "wait_until"
    assert far_minutes == MAX_WAIT_MINUTES
    assert far == now + timedelta(minutes=MAX_WAIT_MINUTES)

    naive, naive_minutes, source = _wait_target(
        {"wait_until": "2026-10-05T11:00:00", "wait_minutes": 20}, now=now
    )
    assert source == "wait_minutes"
    assert naive_minutes == 20
    assert naive == now + timedelta(minutes=20)


@pytest.mark.asyncio
async def test_twenty_minute_wait_persists_same_target_as_ambient_wake(monkeypatch):
    import ambient.service as ambient_service
    import agent.service as agent_service

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    g = goal()
    step = ActionStep(
        id="wait_20m",
        ordinal=0,
        intent="Ricontrollare tra venti minuti",
        step_type="wait",
        parameters={"wait_minutes": 20},
    )
    p = plan_with(step)
    await service.repo.save_goal(g)
    await service.repo.save_plan(p)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    scheduled = AsyncMock(return_value=True)
    monkeypatch.setattr(ambient_service.AmbientService, "schedule", scheduled)

    fixed = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(agent_service, "_now", lambda: fixed)

    out = await service._wait(
        OWNER, g, p, step,
        AgentRun(owner_id=OWNER, goal_id=g.id, background=True),
        parameters=step.parameters,
        note=step.intent,
    )

    expected = fixed + timedelta(minutes=20)
    assert out["state"] == "waiting"
    assert out["for_minutes"] == 20
    assert datetime.fromisoformat(out["until"]) == expected

    saved = await service.repo.get_goal(OWNER, g.id)
    assert saved is not None
    assert datetime.fromisoformat(saved.next_run_at) == expected

    scheduled.assert_awaited_once()
    assert scheduled.await_args.kwargs["when"] == expected


@pytest.mark.asyncio
async def test_legacy_three_hour_wait_is_unchanged(monkeypatch):
    import agent.service as agent_service

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    g = goal()
    p = plan_with(ActionStep(
        id="legacy_3h",
        ordinal=0,
        intent="Aspettare tre ore",
        step_type="wait",
        parameters={"wait_hours": 3},
    ))
    await service.repo.save_goal(g)
    await service.repo.save_plan(p)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    fixed = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(agent_service, "_now", lambda: fixed)

    out = await service._wait(
        OWNER, g, p, p.steps[0],
        AgentRun(owner_id=OWNER, goal_id=g.id, background=True),
        hours=3,
        note="legacy",
    )

    assert out["for_hours"] == 3
    assert out["for_minutes"] == 180
    assert datetime.fromisoformat(out["until"]) == fixed + timedelta(hours=3)


@pytest.mark.asyncio
async def test_next_action_preserves_exact_wait_until(monkeypatch):
    from agent import reasoning

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    g = goal()
    p = plan_with(ActionStep(
        id="verify_later",
        ordinal=0,
        intent="Verificare più tardi",
        step_type="verify",
        capability_needed="information.read",
    ))
    evidence = AgentEvidence(
        owner_id=OWNER,
        goal_id=g.id,
        claim="Serve un checkpoint più tardi.",
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
            "reasoning": "Ricontrollare alle 18 locali.",
            "wait_until": "2026-10-05T18:00:00+02:00",
            "wait_minutes": None,
            "wait_hours": None,
            "step_id": "",
            "asks": "",
            "ask_kind": None,
        }),
    )

    decision, step = await service._next(
        OWNER, g, p,
        AgentRun(owner_id=OWNER, goal_id=g.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert decision == "wait"
    assert step is not None
    assert "wait_until" in step.parameters
    assert "wait_minutes" not in step.parameters
    assert "wait_hours" not in step.parameters
    exact = datetime.fromisoformat(step.parameters["wait_until"])
    assert exact.tzinfo is not None
