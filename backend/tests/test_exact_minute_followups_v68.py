from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, ActionStep, AgentBudget, AgentEvidence, AgentRun, AutonomousGoal, ResultProvenance
from agent.service import (
    AgentService,
    MAX_WAIT_MINUTES,
    _wait_parameters,
    _wait_schedule,
)


OWNER = "alice"
FIXED = datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc)  # 13:00 Europe/Rome


def goal():
    return AutonomousGoal(
        id="goal_v68",
        owner_id=OWNER,
        status="active",
        objective="Seguire un esito al momento preciso",
        desired_outcome="Rivalutare senza arrotondare il momento utile",
    )


def test_wait_minutes_preserve_sub_hour_precision():
    due, minutes = _wait_schedule(wait_minutes=20, now=FIXED)
    assert minutes == 20
    assert due == FIXED + timedelta(minutes=20)


def test_wait_until_preserves_exact_local_clock_with_offset():
    due, minutes = _wait_schedule(
        wait_until="2026-10-05T18:35:00+02:00",
        now=FIXED,
    )
    assert due == datetime(2026, 10, 5, 16, 35, tzinfo=timezone.utc)
    assert minutes == 335


def test_invalid_naive_clock_falls_through_to_duration():
    due, minutes = _wait_schedule(
        wait_until="2026-10-05T18:35:00",
        wait_minutes=25,
        now=FIXED,
    )
    assert minutes == 25
    assert due == FIXED + timedelta(minutes=25)


def test_wait_duration_is_capped_at_fourteen_days():
    due, minutes = _wait_schedule(wait_minutes=999999, now=FIXED)
    assert minutes == MAX_WAIT_MINUTES
    assert due == FIXED + timedelta(minutes=MAX_WAIT_MINUTES)


def test_legacy_wait_hours_contract_survives():
    assert _wait_parameters({"wait_hours": 2}) == {"wait_hours": 2}
    assert _wait_parameters({"wait_hours": 9999}) == {"wait_hours": 336}


@pytest.mark.asyncio
async def test_next_action_can_persist_twenty_minute_checkpoint(monkeypatch):
    from agent import reasoning

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    g = goal()
    plan = ActionPlan(
        id="plan_v68_next",
        owner_id=OWNER,
        goal_id=g.id,
        status="active",
        steps=[ActionStep(
            id="verify_later",
            ordinal=0,
            intent="Verificare di nuovo",
            step_type="verify",
            capability_needed="information.read",
        )],
    )
    evidence = AgentEvidence(
        owner_id=OWNER,
        goal_id=g.id,
        claim="Fra venti minuti la fonte può cambiare.",
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
            "reasoning": "Ricontrollare fra venti minuti.",
            "wait_minutes": 20,
            "wait_until": None,
            "wait_hours": None,
            "step_id": "",
            "asks": "",
            "ask_kind": None,
        }),
    )

    decision, step = await service._next(
        OWNER,
        g,
        plan,
        AgentRun(owner_id=OWNER, goal_id=g.id, background=True),
        AgentBudget(),
        language="it",
    )

    assert decision == "wait"
    assert step is not None
    assert step.parameters == {"wait_minutes": 20}
    assert step.for_ai()["wait_minutes"] == 20
    assert step.for_ai()["wait_until"] is None
    assert step.for_ai()["wait_hours"] is None


@pytest.mark.asyncio
async def test_wait_uses_one_identical_due_instant_for_goal_and_ambient(monkeypatch):
    import agent.service as agent_service
    from ambient.service import AmbientService

    db = AsyncMongoMockClient().test
    service = AgentService(db)
    g = goal()
    plan = ActionPlan(
        id="plan_v68_exact",
        owner_id=OWNER,
        goal_id=g.id,
        status="active",
        steps=[],
    )
    schedule = AsyncMock(return_value=True)
    monkeypatch.setattr(agent_service, "_now", lambda: FIXED)
    monkeypatch.setattr(AmbientService, "schedule", schedule)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())

    out = await service._wait(
        OWNER,
        g,
        plan,
        None,
        AgentRun(owner_id=OWNER, goal_id=g.id, background=True),
        wait_until="2026-10-05T18:35:00+02:00",
        note="Ricontrollare alle 18:35 locali.",
    )

    expected = datetime(2026, 10, 5, 16, 35, tzinfo=timezone.utc)
    assert datetime.fromisoformat(g.next_run_at) == expected
    assert schedule.await_args.kwargs["when"] == expected
    assert out["for_minutes"] == 335
    assert datetime.fromisoformat(out["until"]) == expected


@pytest.mark.asyncio
async def test_reasoning_payload_accepts_absolute_minute_checkpoint(monkeypatch):
    from agent import reasoning

    captured = {}

    async def ask_model(system, user):
        captured["user"] = user
        return {
            "decision": "wait",
            "reasoning": "Alle 18:35 locali.",
            "wait_until": "2026-10-05T18:35:00+02:00",
            "wait_minutes": None,
            "wait_hours": None,
            "step_id": "",
            "asks": "",
            "ask_kind": None,
        }

    monkeypatch.setattr(reasoning, "_ask_model", ask_model)
    result = await reasoning.choose_next_action(
        {"objective": "Seguire il momento utile"},
        plan={"summary": "Piano"},
        candidates=[{"id": "verify", "status": "pending"}],
        evidence=[{"what_was_found": "Serve un controllo più tardi."}],
        capabilities=[],
        clock_context={
            "local_datetime": "2026-10-05T13:00:00+02:00",
            "local_time": "13:00",
            "local_date": "2026-10-05",
            "timezone": "Europe/Rome",
            "authority": "user_confirmed",
        },
        language="it",
    )
    assert result["wait_until"] == "2026-10-05T18:35:00+02:00"
    assert '"local_time": "13:00"' in captured["user"]
    assert "wait_until" in captured["user"] or result["wait_until"]
