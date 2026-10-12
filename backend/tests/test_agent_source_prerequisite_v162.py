"""A source-grounded draft cannot be the first action without evidence."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.models import ActionStep
from agent.service import AgentService, _InvalidNextSelection


def fixture(*steps):
    read = AsyncMock(return_value=[])
    journal = AsyncMock()
    service = SimpleNamespace(
        evidence=SimpleNamespace(for_goal=read),
        repo=SimpleNamespace(journal=journal),
    )
    goal = SimpleNamespace(id="synthetic-owned-goal")
    plan = SimpleNamespace(steps=list(steps))
    return service, goal, plan, read, journal


def prepared():
    return ActionStep(ordinal=0, step_type="prepare", intent="Prepare grounded text",
                      capability_needed="document.create", status="pending")


@pytest.mark.asyncio
async def test_source_read_is_selected_before_a_premature_draft():
    prepare = prepared()
    inspect = ActionStep(ordinal=1, step_type="inspect", intent="Read the owned source",
                         capability_needed="information.read", status="pending",
                         input_refs=["mem_synthetic"])
    service, goal, plan, read, journal = fixture(prepare, inspect)
    decision, step = await AgentService._next(service, "synthetic-owner", goal, plan,
                                             SimpleNamespace(), language="it")
    assert decision == "execute" and step.id == inspect.id
    read.assert_awaited_once_with("synthetic-owner", "synthetic-owned-goal")
    journal.assert_not_awaited()
    assert prepare.status == "pending" and inspect.status == "pending"


@pytest.mark.asyncio
async def test_missing_read_triggers_bounded_replanning_not_preparation():
    prepare = prepared()
    verify = ActionStep(ordinal=1, step_type="verify", intent="Verify grounded result",
                        capability_needed="information.read", status="pending")
    service, goal, plan, read, journal = fixture(prepare, verify)
    with pytest.raises(_InvalidNextSelection) as error:
        await AgentService._next(service, "synthetic-owner", goal, plan,
                                 SimpleNamespace(), language="it")
    assert error.value.context["problem"] == "preparation_sources_required"
    assert error.value.context["result"]["problem"] == "preparation_sources_required"
    assert error.value.context["selection"]["candidate_step_ids"] == [prepare.id, verify.id]
    journal.assert_awaited_once()
    assert journal.await_args.kwargs["kind"] == "planning_prerequisite_missing"
    assert all(item.status == "pending" for item in plan.steps)


@pytest.mark.asyncio
async def test_normal_first_read_still_executes_without_a_model():
    inspect = ActionStep(ordinal=0, step_type="inspect", intent="Read first",
                         capability_needed="information.read", status="pending")
    prepare = ActionStep(ordinal=1, step_type="prepare", intent="Write result",
                         capability_needed="document.create", status="pending")
    service, goal, plan, _, journal = fixture(inspect, prepare)
    decision, step = await AgentService._next(service, "synthetic-owner", goal, plan,
                                             SimpleNamespace(), language="it")
    assert decision == "execute" and step.id == inspect.id
    journal.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_read_does_not_start_unrelated_external_effect():
    prepare = prepared()
    effect = ActionStep(ordinal=1, step_type="execute", intent="Change world",
                        capability_needed="calendar.write", external_effect=True,
                        effect_type="modify", effect_target="calendar:synthetic",
                        status="pending")
    service, goal, plan, _, journal = fixture(prepare, effect)
    with pytest.raises(_InvalidNextSelection):
        await AgentService._next(service, "synthetic-owner", goal, plan,
                                 SimpleNamespace(), language="it")
    assert effect.status == "pending"
    journal.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_current_owned_memory_gets_one_readonly_prerequisite(monkeypatch):
    service, goal, plan, read, journal = fixture(prepared())
    goal.source_refs = ["mem_owned"]
    service.db = object()
    service.capabilities = SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(
        usable=True, is_real=True, writes=False,
    )))
    service.repo.save_plan = AsyncMock()

    async def owned_preview(db, owner_id, refs, *, limit):
        assert db is service.db and owner_id == "synthetic-owner"
        assert refs == ["mem_owned"] and limit == 1
        return [{"ref": "mem_owned", "status": "active"}]

    monkeypatch.setattr("agent.memory_sources.read_memory_previews", owned_preview)
    decision, step = await AgentService._next(service, "synthetic-owner", goal, plan,
                                             SimpleNamespace(), language="it")
    assert decision == "execute" and step.step_type == "inspect"
    assert step.capability_needed == "information.read"
    assert step.input_refs == ["mem_owned"] and step.external_effect is False
    assert len(plan.steps) == 2 and plan.steps[-1].id == step.id
    service.repo.save_plan.assert_awaited_once_with(plan)
    journal.assert_awaited_once()
    assert journal.await_args.kwargs["kind"] == "planning_prerequisite_added"
    read.assert_awaited_once()
    assert (await AgentService._owned_memory_prerequisite(
        service, "synthetic-owner", goal, plan
    )) is None
    assert len(plan.steps) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["withdrawn", "unavailable", "ambiguous"])
async def test_missing_or_unusable_memory_cannot_be_auto_read(monkeypatch, case):
    service, goal, plan, _, journal = fixture(prepared())
    goal.source_refs = ["mem_owned"] if case != "ambiguous" else ["mem_a", "mem_b"]
    service.db = object()
    service.capabilities = SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(
        usable=(case != "unavailable"), is_real=True, writes=False,
    )))
    service.repo.save_plan = AsyncMock()
    preview = AsyncMock(return_value=[])
    monkeypatch.setattr("agent.memory_sources.read_memory_previews", preview)
    with pytest.raises(_InvalidNextSelection):
        await AgentService._next(service, "synthetic-owner", goal, plan,
                                 SimpleNamespace(), language="it")
    assert len(plan.steps) == 1
    service.repo.save_plan.assert_not_awaited()
    journal.assert_awaited_once()
    assert journal.await_args.kwargs["kind"] == "planning_prerequisite_missing"
    if case == "withdrawn":
        preview.assert_awaited_once()
    else:
        preview.assert_not_awaited()
