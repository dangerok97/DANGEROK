from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.execution import StepExecutor
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal
from agent.service import AgentService, _unprepared_effect_reason


def _goal():
    return AutonomousGoal(
        id="goal_cross_domain",
        owner_id="alice",
        status="active",
        objective="Allineare il calendario alla comunicazione verificata",
        desired_outcome="L'appuntamento ha l'orario corretto",
        success_criteria=["L'evento esistente ha l'orario verificato"],
    )


def _step(**over):
    fields = {
        "id": "step_modify",
        "ordinal": 0,
        "intent": "Spostare l'appuntamento all'orario verificato.",
        "step_type": "execute",
        "status": "pending",
        "capability_needed": "calendar.write",
        "input_refs": ["link_1", "mail:m1", "calendar:event_123"],
        "expected_result": "L'evento esistente ha il nuovo orario.",
        "external_effect": True,
        "effect_type": "modify",
        "effect_target": "appuntamento esistente",
        "reaches_somebody_else": False,
        "reversibility": "easily",
        "parameters": {
            "title": "Dentista",
            "starts_at": "2026-10-06T16:30:00+02:00",
            "ends_at": "2026-10-06T17:30:00+02:00",
            "timezone": "Europe/Rome",
        },
    }
    fields.update(over)
    return ActionStep(**fields)


def test_calendar_modify_binds_to_calendar_ref_not_first_cross_domain_ref():
    db = AsyncMongoMockClient().test
    executor = StepExecutor(db)
    intent = executor._intent_for("alice", _goal(), _step())

    assert intent.target_ref == "calendar:event_123"
    assert intent.target_ref != "link_1"
    assert intent.target_ref != "mail:m1"
    assert intent.parameter_refs == ["link_1", "mail:m1", "calendar:event_123"]


def test_calendar_modify_is_not_ready_without_exact_target_or_time():
    db = AsyncMongoMockClient().test
    executor = StepExecutor(db)

    missing_target = _step(input_refs=["link_1", "mail:m1"])
    intent = executor._intent_for("alice", _goal(), missing_target)
    assert "riferimento esatto" in _unprepared_effect_reason(intent)

    missing_time = _step(parameters={"title": "Dentista"})
    intent = executor._intent_for("alice", _goal(), missing_time)
    assert "nuovo orario verificato" in _unprepared_effect_reason(intent)


@pytest.mark.asyncio
async def test_incomplete_effect_replans_before_authority_is_considered(monkeypatch):
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    step = _step(parameters={"title": "Dentista"})
    plan = ActionPlan(
        id="plan_cross_domain",
        goal_id=goal.id,
        owner_id=goal.owner_id,
        status="active",
        plan_summary="Verificare e poi correggere l'orario.",
        steps=[step],
    )
    run = AgentRun(owner_id="alice", goal_id=goal.id)
    budget = AgentBudget()

    authority = AsyncMock()
    reconsider = AsyncMock(return_value={"ok": True, "state": "replanned"})
    monkeypatch.setattr(service, "_authority_for", authority)
    monkeypatch.setattr(service, "_reconsider", reconsider)

    out = await service._do_step(
        "alice", goal, plan, step, run, budget, language="it"
    )

    assert out == {"ok": True, "state": "replanned"}
    authority.assert_not_awaited()
    reconsider.assert_awaited_once()
    payload = reconsider.await_args.kwargs["what_happened"]
    assert payload["problem"] == "l'azione non è ancora completamente preparata"
    assert "orario" in payload["what_is_missing"]


def test_action_step_exposes_only_bounded_calendar_parameters_to_next_judgement():
    step = _step()
    step.parameters["irrelevant_private_blob"] = "should-not-be-shown"
    shown = step.for_ai()

    assert shown["prepared_parameters"]["title"] == "Dentista"
    assert shown["prepared_parameters"]["starts_at"].endswith("+02:00")
    assert "irrelevant_private_blob" not in shown["prepared_parameters"]


@pytest.mark.asyncio
async def test_planner_contract_names_modify_target_and_replan_rule(monkeypatch):
    from agent import reasoning

    ask = AsyncMock(return_value={
        "plan_summary": "Leggere e poi correggere.",
        "expected_outcome": "Calendario coerente.",
        "steps": [{
            "intent": "Leggere la mail",
            "step_type": "inspect",
            "capability_needed": "mail.read",
            "input_refs": ["mail:m1"],
            "parameters": {},
            "expected_result": "Nuovo orario noto",
            "external_effect": False,
            "reversibility": "easily",
        }],
    })
    monkeypatch.setattr(reasoning, "_ask_model", ask)

    result = await reasoning.make_plan(
        _goal().for_ai(),
        capabilities=[
            {"capability": "mail.read", "status": "available_real"},
            {"capability": "calendar.write", "status": "available_real"},
        ],
        context={"weekday": "monday"},
    )

    assert result is not None
    instruction = ask.await_args.args[0]
    assert "effect_type=modify" in instruction
    assert "calendar:<id>" in instruction
    assert "replan" in instruction
    assert "authority" in instruction.lower()
