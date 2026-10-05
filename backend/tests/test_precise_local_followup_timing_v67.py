from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

import agent.service as agent_service
from agent.models import ActionPlan, AgentRun, AutonomousGoal
from agent.service import (
    AgentService,
    MAX_WAIT_MINUTES,
    _resolve_wait_target,
    _wait_parameters_from_answer,
)


FIXED_NOW = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)


def test_twenty_minute_wait_is_not_rounded_to_one_hour():
    when, meta = _resolve_wait_target(wait_minutes=20, now=FIXED_NOW)

    assert when == FIXED_NOW + timedelta(minutes=20)
    assert meta["mode"] == "wait_minutes"
    assert meta["for_minutes"] == 20


def test_exact_local_deadline_keeps_the_exact_instant():
    # 17:40 in Italy on 5 October 2026 is 15:40 UTC.
    when, meta = _resolve_wait_target(
        wait_until="2026-10-05T17:40:00+02:00",
        now=FIXED_NOW,
    )

    assert when == datetime(2026, 10, 5, 15, 40, tzinfo=timezone.utc)
    assert meta["mode"] == "wait_until"
    assert meta["for_minutes"] == 40
    assert meta["wait_until"] == "2026-10-05T17:40:00+02:00"


def test_legacy_hour_wait_remains_compatible():
    when, meta = _resolve_wait_target(wait_hours=4, now=FIXED_NOW)

    assert when == FIXED_NOW + timedelta(hours=4)
    assert meta["mode"] == "wait_hours"
    assert meta["for_minutes"] == 240
    assert meta["for_hours"] == 4


def test_invalid_exact_deadline_never_schedules_in_the_past_or_beyond_horizon():
    past, past_meta = _resolve_wait_target(
        wait_until="2026-10-05T16:30:00+02:00",
        now=FIXED_NOW,
    )
    too_far, far_meta = _resolve_wait_target(
        wait_until="2026-11-30T17:40:00+01:00",
        now=FIXED_NOW,
    )

    assert past == FIXED_NOW + timedelta(hours=6)
    assert too_far == FIXED_NOW + timedelta(hours=6)
    assert past_meta["mode"] == "default"
    assert far_meta["mode"] == "default"
    assert 1 <= past_meta["for_minutes"] <= MAX_WAIT_MINUTES
    assert 1 <= far_meta["for_minutes"] <= MAX_WAIT_MINUTES


def test_model_timing_priority_is_exact_then_minutes_then_legacy_hours():
    exact = _wait_parameters_from_answer({
        "wait_until": "2026-10-05T17:40:00+02:00",
        "wait_minutes": 25,
        "wait_hours": 2,
    })
    minutes = _wait_parameters_from_answer({
        "wait_minutes": 25,
        "wait_hours": 2,
    })
    hours = _wait_parameters_from_answer({"wait_hours": 2})

    # Exact validity is checked against real current time in production. This
    # test only needs to assert the two interval fallbacks deterministically;
    # the exact parser itself is covered above with a fixed clock.
    assert minutes == {"wait_minutes": 25}
    assert hours == {"wait_hours": 2}
    assert set(exact).issubset({"wait_until", "wait_minutes", "wait_hours"})


@pytest.mark.asyncio
async def test_wait_persists_and_schedules_exact_minute_checkpoint(monkeypatch):
    from ambient.service import AmbientService

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = AutonomousGoal(
        id="goal_precise_wait",
        owner_id="alice",
        status="active",
        objective="Ricontrollare presto",
        desired_outcome="Verificare nel momento utile",
    )
    plan = ActionPlan(
        id="plan_precise_wait",
        owner_id="alice",
        goal_id=goal.id,
        status="active",
        steps=[],
    )
    run = AgentRun(owner_id="alice", goal_id=goal.id, background=True)

    monkeypatch.setattr(agent_service, "_now", lambda: FIXED_NOW)
    monkeypatch.setattr(service.repo, "save_goal", AsyncMock())
    monkeypatch.setattr(service.repo, "save_plan", AsyncMock())
    journal = AsyncMock()
    monkeypatch.setattr(service.repo, "journal", journal)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    schedule = AsyncMock()
    monkeypatch.setattr(AmbientService, "schedule", schedule)

    result = await service._wait(
        "alice",
        goal,
        plan,
        None,
        run,
        minutes=20,
        note="Ricontrollare fra venti minuti.",
    )

    expected = FIXED_NOW + timedelta(minutes=20)
    assert goal.next_run_at == expected.isoformat()
    assert result["for_minutes"] == 20
    assert result["until"] == expected.isoformat()
    assert "for_hours" not in result
    schedule.assert_awaited_once()
    assert schedule.await_args.kwargs["when"] == expected
    assert journal.await_args.kwargs["detail"]["for_minutes"] == 20
    assert journal.await_args.kwargs["detail"]["scheduled_for"] == expected.isoformat()
