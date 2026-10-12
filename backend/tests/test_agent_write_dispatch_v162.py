"""The capability catalog, not a model's step label, identifies a write."""
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
import pytest

from agent import effects, reasoning
from agent.execution import ATTEMPTS, RECEIPTS, StepExecutor
from agent.models import ActionPlan, ActionStep, AgentBudget, AgentRun, AutonomousGoal, ResultProvenance
from agent.providers import CapabilityOutcome
from agent.service import AgentService


OWNER = "synthetic-write-dispatch"


@pytest.fixture(autouse=True)
def no_effect_or_model(monkeypatch):
    forbidden = AsyncMock(side_effect=AssertionError("No effect or model is permitted in this test"))
    monkeypatch.setattr(effects, "run_effect", forbidden)
    monkeypatch.setattr(reasoning, "_ask_model", forbidden)
    return forbidden


def goal():
    return AutonomousGoal(owner_id=OWNER, objective="Lavoro sintetico", desired_outcome="Risultato verificato",
                          status="active", success_criteria=["Esito della fonte corrente"])


def declared_write(step_type="inspect"):
    return ActionStep(intent="Passo dichiarato senza effetti", step_type=step_type,
                      capability_needed="calendar.local.write", external_effect=False,
                      reaches_somebody_else=False, effect_type="create", effect_target="",
                      parameters={"title": "Evento esclusivamente sintetico"})


async def no_write_records(db):
    for collection in (ATTEMPTS, RECEIPTS, "agent_evidence"):
        assert await db[collection].count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("step_type,may_touch", [
    (kind, True) for kind in ("inspect", "research", "compare", "prepare", "ask_user", "verify", "wait")
] + [("inspect", False)])
async def test_catalog_write_with_nonexecute_label_stops_before_effect_handler(monkeypatch, step_type, may_touch):
    db = AsyncMongoMockClient().write_dispatch_direct
    executor = StepExecutor(db)
    step = declared_write(step_type)
    touch = AsyncMock(side_effect=AssertionError("The effect handler must not be entered"))
    monkeypatch.setattr(executor, "_touch_the_world", touch)
    budget = AgentBudget()
    result = await executor.run(OWNER, goal(), step, may_touch_the_world=may_touch, budget=budget)
    assert result.status == "unavailable" and result.error_type == "write_requires_execute_step"
    assert result.retryable is False and result.step_id == step.id
    assert result.provenance.source_class == "internal_observation"
    assert result.provenance.capability == "calendar.local.write"
    touch.assert_not_awaited()
    assert budget.cognitive_calls == budget.capability_calls == budget.research_calls == 0
    assert step.step_type == step_type and step.external_effect is False
    await no_write_records(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("background", [False, True])
async def test_service_reconsiders_the_structural_error_without_granting_authority(monkeypatch, background):
    db = AsyncMongoMockClient().write_dispatch_service
    service = AgentService(db)
    current, step = goal(), declared_write()
    plan = ActionPlan(owner_id=OWNER, goal_id=current.id, steps=[step])
    await service.repo.save_goal(current)
    await service.repo.save_plan(plan)
    run = AgentRun(owner_id=OWNER, goal_id=current.id, background=background)
    budget = AgentBudget()
    continuation = {"ok": True, "state": "in_progress"}
    reconsider = AsyncMock(return_value=continuation)
    authority = AsyncMock(side_effect=AssertionError("The label is invalid, not authority"))
    touch = AsyncMock(side_effect=AssertionError("The effect handler must not be entered"))
    monkeypatch.setattr(service, "_reconsider", reconsider)
    monkeypatch.setattr(service, "_authority_for", authority)
    monkeypatch.setattr(service.executor, "_touch_the_world", touch)
    result = await service._do_step(OWNER, current, plan, step, run, budget, language="it")
    assert result is continuation and step.status == "failed"
    reconsider.assert_awaited_once()
    event = reconsider.await_args.kwargs["what_happened"]
    assert event["step"]["type"] == "inspect"
    assert event["result"]["problem"] == "write_requires_execute_step"
    assert event["result"]["worth_retrying"] is False
    authority.assert_not_awaited()
    touch.assert_not_awaited()
    assert budget.cognitive_calls == budget.capability_calls == 0
    assert budget.steps_executed == run.steps_executed == 1
    assert current.status == "active" and not current.requires_user_authority
    await no_write_records(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("step_type,capability,how", [
    ("inspect", "information.read", "read"), ("prepare", "document.create", "prepare"),
])
async def test_known_read_and_local_preparation_keep_the_existing_dispatch(monkeypatch, step_type, capability, how):
    db = AsyncMongoMockClient().write_dispatch_harmless
    executor = StepExecutor(db)
    current = goal()
    step = ActionStep(intent="Operazione locale sintetica", step_type=step_type, capability_needed=capability)
    harmless = AsyncMock(return_value=CapabilityOutcome(
        status="succeeded", observation="Operazione locale verificata nel test.",
        provenance=ResultProvenance(source_class="internal_observation", capability=capability),
    ))
    touch = AsyncMock(side_effect=AssertionError("No write belongs to this capability"))
    monkeypatch.setattr(executor, "_call", harmless)
    monkeypatch.setattr(executor, "_touch_the_world", touch)
    budget = AgentBudget()
    result = await executor.run(OWNER, current, step, may_touch_the_world=False, budget=budget)
    assert result.status == "succeeded" and result.error_type == ""
    harmless.assert_awaited_once_with(OWNER, current, step, how, budget=budget)
    touch.assert_not_awaited()
    assert budget.capability_calls == 1
    assert await db[ATTEMPTS].count_documents({}) == await db[RECEIPTS].count_documents({}) == 0


@pytest.mark.asyncio
async def test_execute_still_reaches_the_existing_authority_guard(no_effect_or_model):
    db = AsyncMongoMockClient().write_dispatch_authority
    step = declared_write("execute")
    result = await StepExecutor(db).run(OWNER, goal(), step, may_touch_the_world=False, budget=AgentBudget())
    assert result.status == "partial" and result.error_type == "authority_required"
    stored = await db[ATTEMPTS].find_one({"owner_id": OWNER, "step_id": step.id})
    assert stored is not None and stored["status"] == "prepared"
    assert await db[ATTEMPTS].count_documents({}) == 1
    assert await db[RECEIPTS].count_documents({}) == 0
    no_effect_or_model.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("capability,error", [
    ("not.a.real.capability", "capability_unknown"), ("calendar.write", "requires_connection"),
])
async def test_unknown_and_missing_permission_keep_their_existing_errors(monkeypatch, capability, error):
    db = AsyncMongoMockClient().write_dispatch_unavailable
    executor = StepExecutor(db)
    step = declared_write()
    step.capability_needed = capability
    touch = AsyncMock(side_effect=AssertionError("An unavailable capability cannot touch the world"))
    monkeypatch.setattr(executor, "_touch_the_world", touch)
    result = await executor.run(OWNER, goal(), step, may_touch_the_world=True)
    assert result.status == "unavailable" and result.error_type == error
    touch.assert_not_awaited()
    await no_write_records(db)
