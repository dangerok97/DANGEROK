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
