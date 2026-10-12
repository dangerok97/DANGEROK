"""Invalid model waits preserve the existing technical continuation.

The observed zero-minute wait did have a persisted wake: the defect was its
conversion to a one-minute world wait and a reset of background_runs. These
synthetic service tests exercise that protocol boundary without real models,
provider reads or effects, and keep valid minute/absolute/legacy waits intact.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import socket
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import reasoning
from agent.background import advance_wake, recover_due
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal
from agent.service import AgentService
from ambient.models import AmbientWake
from test_autonomy_wait_recovery_v162 import (
    clock, successful_reply, waiting_after_rejected_preparation,
)
from test_preparation_recovery_v162 import OWNER, RESULT


@pytest.fixture(autouse=True)
def no_uncontrolled_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network belongs to this synthetic protocol test")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(reasoning, "_ask_model", AsyncMock(side_effect=AssertionError("Unexpected model call")))


async def setup(monkeypatch):
    from agent import service as service_module

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(service_module, "_now", lambda: now)
    db = AsyncMongoMockClient().synthetic_wait_protocol
    service = AgentService(db)
    goal = AutonomousGoal(owner_id=OWNER, status="active", background_runs=2,
        objective="Preparare il risultato sintetico dalle condizioni disponibili.",
        desired_outcome="Un risultato interno qualificato.",
        next_run_at=(now + timedelta(minutes=5)).isoformat())
    plan = ActionPlan(owner_id=OWNER, goal_id=goal.id, status="active", revisions=2, steps=[
        ActionStep(step_type="inspect", status="succeeded", intent="Lettura già fatta",
                   note="La fonte non attestava condizioni aggiuntive."),
        ActionStep(step_type="prepare", status="failed", attempts=1,
                   intent="Tentativo precedente", note="La revisione precedente non era valida."),
        ActionStep(step_type="verify", intent="Passo ancora aperto"),
    ])
    await service.repo.save_goal(goal)
    await service.repo.save_plan(plan)
    wake = AmbientWake(owner_id=OWNER, reason="opportunity_revisit",
        scheduled_for=goal.next_run_at, source_ref="goal:" + goal.id)
    await db.ambient_wakes.insert_one(wake.model_dump())
    monkeypatch.setattr(service.capabilities, "available", AsyncMock(return_value=[]))
    assessment = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "_record_situation_outcome", assessment)
    return db, service, goal, plan, now, assessment


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid,field,issue", [
    ("zero", "wait_minutes", "invalid_time"),
    ("missing", "wait_minutes", "missing"),
    ("boolean", "wait_minutes", "invalid_time"),
    ("non_finite", "wait_minutes", "invalid_time"),
    ("naive", "wait_until", "invalid_time"),
    ("revision", "revised_steps", "incompatible_with_wait"),
    ("replacement", "replace_step_ids", "incompatible_with_wait"),
    ("shape", "revised_steps", "wrong_type"),
])
async def test_invalid_wait_preserves_checkpoint_budget_history_and_untrusted_values(
    monkeypatch, invalid, field, issue,
):
    db, service, goal, plan, now, assessment = await setup(monkeypatch)
    answer = {"decision": "wait", "wait_minutes": 17,
        "reasoning": "PRIVATE_UNTRUSTED_REASON",
        "situation_outcome": {"headline": "PRIVATE_UNTRUSTED_OUTCOME"}}
    if invalid == "zero":
        answer["wait_minutes"] = 0
    elif invalid == "missing":
        answer.pop("wait_minutes")
    elif invalid == "boolean":
        answer["wait_minutes"] = True
    elif invalid == "non_finite":
        answer["wait_minutes"] = float("inf")
    elif invalid == "naive":
        answer.pop("wait_minutes")
        answer["wait_until"] = (now + timedelta(minutes=17)).replace(tzinfo=None).isoformat()
    elif invalid == "revision":
        answer["revised_steps"] = [{"step_type": "prepare", "intent": "PRIVATE_NEW_ROUTE"}]
    elif invalid == "replacement":
        answer["replace_step_ids"] = [plan.steps[-1].id]
    else:
        answer["revised_steps"] = {"PRIVATE_NEW_ROUTE": True}
    original_answer = deepcopy(answer)
    original_goal = deepcopy(goal.model_dump())
    original_steps = deepcopy([step.model_dump() for step in plan.steps])
    original_wakes = await db.ambient_wakes.find({}).to_list(None)
    model = AsyncMock(return_value=answer)
    monkeypatch.setattr(reasoning, "reconsider", model)
    budget = AgentBudget(cognitive_calls=1)
    run = AgentRun(owner_id=OWNER, goal_id=goal.id)

    result = await service._reconsider(OWNER, goal, plan, run, budget,
        what_happened={"result": {"problem": "prepared_result_verification_incomplete"}}, language="it")

    assert result["state"] == "in_progress" and result["reason"] == "replan_protocol_invalid"
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    current_plan = await AgentService(db).repo.plan_for(OWNER, goal.id)
    assert current.model_dump() == original_goal
    assert current_plan.status == "active" and current_plan.revisions == 2
    assert [step.model_dump() for step in current_plan.steps] == original_steps
    assert await db.ambient_wakes.find({}).to_list(None) == original_wakes
    assert budget.cognitive_calls == 2 and run.replans == model.await_count == 1
    assert run.stopped_because == "replan_protocol_invalid"
    assessment.assert_not_awaited()
    diagnostic = await db.agent_journal.find_one({"owner_id": OWNER, "goal_id": goal.id,
                                                  "kind": "replan_protocol_invalid"})
    assert {"field": field, "issue": issue} in diagnostic["detail"]["validation_errors"]
    assert "PRIVATE_" not in json.dumps(diagnostic, default=str)
    assert await db.agent_journal.count_documents({"kind": "replanned"}) == 0
    assert await db.agent_action_attempts.count_documents({}) == 0
    assert answer == original_answer


@pytest.mark.asyncio
@pytest.mark.parametrize("timing", ["minutes", "absolute", "legacy_hours"])
async def test_valid_wait_keeps_existing_exact_time_and_world_wait_semantics(monkeypatch, timing):
    db, service, goal, plan, now, assessment = await setup(monkeypatch)
    target = now + timedelta(minutes=37)
    fields = {"wait_minutes": 37}
    if timing == "absolute":
        # The existing documented precedence is preserved, not reinterpreted
        # as a conflict between the exact target and a legacy duration.
        fields = {"wait_until": target.astimezone(timezone(timedelta(hours=2))).isoformat(),
                  "wait_minutes": 120, "wait_hours": 4}
    elif timing == "legacy_hours":
        fields = {"wait_hours": 2}
        target = now + timedelta(hours=2)
    answer = {"decision": "wait", "reasoning": "Una condizione esterna può cambiare al checkpoint.",
              "revised_steps": [], "replace_step_ids": [], **fields}
    original = deepcopy(answer)
    model = AsyncMock(return_value=answer)
    monkeypatch.setattr(reasoning, "reconsider", model)
    budget = AgentBudget()
    result = await service._reconsider(OWNER, goal, plan, AgentRun(owner_id=OWNER, goal_id=goal.id),
        budget, what_happened={"problem": "scheduled_external_checkpoint"}, language="it")
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    current_plan = await AgentService(db).repo.plan_for(OWNER, goal.id)
    assert result["state"] == current.status == current_plan.status == "waiting"
    assert current.next_run_at == target.isoformat() and current.background_runs == 0
    assert not current.requires_user_input and not current.requires_user_authority
    assert current_plan.revisions == 3 and model.await_count == budget.cognitive_calls == 1
    assert [step.status for step in current_plan.steps] == ["succeeded", "failed", "pending"]
    assert await db.agent_journal.count_documents({"kind": "replan_protocol_invalid"}) == 0
    assessment.assert_awaited_once()
    assert answer == original


@pytest.mark.asyncio
async def test_invalid_due_wait_resumes_after_reload_on_owned_existing_checkpoint(monkeypatch, clock):
    db, goal, plan, source = await waiting_after_rejected_preparation(clock)
    failed_history = deepcopy(plan.steps[1].model_dump())
    calls = []

    async def reply(_system, encoded, *, response_schema=None):
        payload = json.loads(encoded)
        calls.append(payload)
        if "what_happened" in payload:
            return {"decision": "wait", "wait_minutes": 0,
                    "reasoning": "La risposta sintetica non ha dichiarato un'attesa valida."}
        return successful_reply(payload, source)

    monkeypatch.setattr(reasoning, "_ask_model", reply)
    first = await AgentService(db).advance(OWNER, goal.id, worker_id="ambient:invalid-wait")
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    assert first["state"] == "in_progress" and len(calls) == 1
    assert current.status == "active" and current.background_runs == 1
    assert current.next_run_at == (clock[0] + timedelta(minutes=5)).isoformat()
    assert not current.requires_user_input and not current.requires_user_authority

    clock[0] = datetime.fromisoformat(current.next_run_at) + timedelta(seconds=1)
    assert await recover_due(db, now=clock[0], admit=False) == 1
    wake = await db.ambient_wakes.find_one({"owner_id": OWNER, "source_ref": "goal:" + goal.id,
                                            "status": "pending"})
    resumed = await advance_wake(db, AmbientWake.model_validate(wake))
    current = await AgentService(db).repo.get_goal(OWNER, goal.id)
    current_plan = await AgentService(db).repo.plan_for(OWNER, goal.id)
    assert resumed.result == current.status == current_plan.status == "completed"
    assert current.background_runs == 2 and current.next_run_at is None
    assert current.prepared_text == RESULT and current.prepared_sources == [source.id]
    assert current_plan.steps[1].model_dump() == failed_history
    assert await db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": goal.id,
        "provenance.capability": "information.read"}) == 1
    assert await db.agent_action_attempts.count_documents({}) == 0
