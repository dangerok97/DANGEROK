from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.models import ActionPlan, ActionStep, AgentRun, AutonomousGoal
from agent.service import AgentService, _authority_question


def _goal():
    return AutonomousGoal(
        id="goal_authority",
        owner_id="alice",
        status="active",
        objective="Tenere il dentista all'orario corretto",
        desired_outcome="Il calendario riflette l'orario verificato",
        success_criteria=["L'evento ha il nuovo orario"],
    )


def _step():
    return ActionStep(
        id="step_calendar_modify",
        ordinal=0,
        intent="Spostare l'appuntamento del dentista all'orario verificato.",
        step_type="execute",
        status="pending",
        capability_needed="calendar.write",
        input_refs=["event_123"],
        expected_result="Il dentista è in calendario alle 16:30.",
        external_effect=True,
        effect_type="modify",
        effect_target="appuntamento dentista",
        reaches_somebody_else=False,
        reversibility="easily",
        parameters={
            "title": "Dentista",
            "starts_at": "2026-10-06T16:30:00+02:00",
            "ends_at": "2026-10-06T17:30:00+02:00",
            "timezone": "Europe/Rome",
        },
    )


def test_authority_question_names_the_frozen_calendar_change():
    service = AgentService(AsyncMongoMockClient().test)
    goal = _goal()
    step = _step()
    intent = service.executor._intent_for("alice", goal, step)

    question = _authority_question(intent)

    assert "Dentista" in question
    assert "06/10 alle 16:30" in question
    assert "Vuoi che applichi questa modifica?" in question
    assert "event_123" not in question
    assert intent.effect_hash


@pytest.mark.asyncio
async def test_waiting_authority_persists_exact_question_and_audit_binding():
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    step = _step()
    plan = ActionPlan(
        id="plan_authority",
        goal_id=goal.id,
        owner_id=goal.owner_id,
        status="active",
        plan_summary="Correggere l'orario verificato.",
        steps=[step],
    )
    await service.repo.save_goal(goal)
    await service.repo.save_plan(plan)

    result = await service._awaiting_authority(
        "alice",
        goal,
        plan,
        AgentRun(owner_id="alice", goal_id=goal.id),
        step,
    )

    assert result["state"] == "awaiting_authority"
    assert result["asks"] == step.asks
    assert "Dentista" in result["asks"]
    assert goal.requires_user_authority is True

    saved = await service.repo.plan_for("alice", goal.id)
    assert saved is not None
    assert saved.steps[0].asks == result["asks"]

    journal = await db.agent_journal.find_one(
        {"owner_id": "alice", "goal_id": goal.id, "kind": "awaiting_authority"},
        {"_id": 0},
    )
    assert journal is not None
    assert journal["note"] == result["asks"]
    assert journal["detail"]["effect_hash"]
    assert journal["detail"]["effect_type"] == "modify"


@pytest.mark.asyncio
async def test_approval_audit_records_the_same_question_the_person_saw(monkeypatch):
    db = AsyncMongoMockClient().test
    service = AgentService(db)
    goal = _goal()
    goal.status = "waiting"
    goal.requires_user_authority = True
    step = _step()
    step.status = "blocked"
    plan = ActionPlan(
        id="plan_authority",
        goal_id=goal.id,
        owner_id=goal.owner_id,
        status="waiting",
        plan_summary="Correggere l'orario verificato.",
        steps=[step],
    )
    await service.repo.save_goal(goal)
    await service.repo.save_plan(plan)

    consent = AsyncMock(return_value=SimpleNamespace(id="consent_1"))
    monkeypatch.setattr(service.authority, "consent", consent)
    monkeypatch.setattr(service.needs, "open_for_goal", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        service, "advance", AsyncMock(return_value={"ok": True, "state": "in_progress"})
    )

    intent = service.executor._intent_for("alice", goal, step)
    expected = _authority_question(intent)

    out = await service.authorise("alice", goal.id)

    assert out["ok"] is True
    assert consent.await_count == 1
    assert consent.await_args.kwargs["shown"] == expected
