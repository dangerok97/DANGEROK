"""A grounded internal draft needs a real verdict, not another chooser call.

This tests only the *selection* of verification. It never supplies an
"achieved" verdict, bypasses source validity or performs a world action.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent import reasoning
from agent.models import (
    ActionPlan, ActionStep, AgentBudget, AgentEvidence, AgentRun,
    AutonomousGoal, ResultProvenance,
)
from agent.service import AgentService, _ready_to_verify_existing_internal_result


def prepared_internal():
    goal = AutonomousGoal(
        owner_id="synthetic-internal-owner",
        status="active", origin="agent_initiated",
        source_kind="memory", objective="Confronto della nota",
        desired_outcome="Confronto scritto con limiti e differenza",
    )
    source = AgentEvidence(
        owner_id=goal.owner_id, goal_id=goal.id,
        claim="Nota della persona: 15 al mese e 120 annui.",
        provenance=ResultProvenance(source_class="internal_observation",
                                    capability="information.read"),
    )
    goal.prepared_text = (
        "Secondo la nota, su dodici mesi 15 per 12 è 180, "
        "contro 120 annui: differenza 60, termini ulteriori ignoti."
    )
    goal.prepared_sources = [source.id]
    done = ActionStep(
        ordinal=0, status="succeeded", step_type="prepare",
        intent="Preparare il documento", capability_needed="document.create",
    )
    pending = ActionStep(
        ordinal=1, status="pending", step_type="verify",
        intent="Verificare il risultato interno", capability_needed="information.read",
    )
    plan = ActionPlan(owner_id=goal.owner_id, goal_id=goal.id,
                      status="active", steps=[done, pending])
    return goal, plan, [source]


@pytest.mark.asyncio
async def test_grounded_internal_result_reaches_real_verifier_without_extra_model_choice(monkeypatch):
    goal, plan, evidence = prepared_internal()
    choose = AsyncMock(side_effect=AssertionError("Redundant model choice"))
    monkeypatch.setattr(reasoning, "choose_next_action", choose)
    reads = AsyncMock(return_value=evidence)
    service = SimpleNamespace(evidence=SimpleNamespace(for_goal=reads))
    budget = AgentBudget()
    run = AgentRun(owner_id=goal.owner_id, goal_id=goal.id)
    verdict, step = await AgentService._next(
        service, goal.owner_id, goal, plan, run, budget, language="it",
    )
    assert verdict == "finish" and step is None
    choose.assert_not_awaited()
    reads.assert_awaited_once_with(goal.owner_id, goal.id)
    assert budget.cognitive_calls == 0  # _finish still owns the verdict budget.
    assert plan.steps[1].status == "pending"
    assert goal.status == "active"  # No claim of completion or delivered Home.
    assert goal.prepared_sources == [evidence[0].id]


@pytest.mark.parametrize("change", [
    "no_draft", "uncited", "no_evidence", "wrong_goal_status",
    "person_input", "person_authority", "deferred", "weather_situation",
    "pending_inspection", "pending_effect", "pending_read_cursor",
    "pending_explicit_read", "pending_research", "unsaved_preparation",
    "no_successful_preparation", "plan_waiting", "prior_world_effect",
])
def test_shortcut_requires_a_complete_internal_preparation_without_remaining_effects(change):
    goal, plan, evidence = prepared_internal()
    if change == "no_draft":
        goal.prepared_text = ""
    elif change == "uncited":
        goal.prepared_sources = ["evd_absent"]
    elif change == "no_evidence":
        evidence.clear()
    elif change == "wrong_goal_status":
        goal.status = "waiting"
    elif change == "person_input":
        goal.requires_user_input = True
    elif change == "person_authority":
        goal.requires_user_authority = True
    elif change == "deferred":
        goal.user_deferred_until = "2026-10-15T10:00:00+00:00"
    elif change == "weather_situation":
        goal.source_kind = "situation_followup"
    elif change == "pending_inspection":
        plan.steps[1].step_type = "inspect"
    elif change == "pending_effect":
        plan.steps.append(ActionStep(
            ordinal=2, step_type="execute", status="pending",
            intent="Modificare calendario", capability_needed="calendar.write",
            external_effect=True, effect_target="calendar:synthetic",
        ))
    elif change == "pending_read_cursor":
        plan.steps[1].parameters = {"memory_offset": 600}
    elif change == "pending_explicit_read":
        plan.steps[1].input_refs = ["mem_synthetic"]
    elif change == "pending_research":
        plan.steps[1].capability_needed = "web.research"
    elif change == "unsaved_preparation":
        plan.steps[0].status = "pending"
    elif change == "no_successful_preparation":
        plan.steps[0].step_type = "inspect"
    elif change == "plan_waiting":
        plan.status = "waiting"
    elif change == "prior_world_effect":
        plan.steps[0].external_effect = True

    assert _ready_to_verify_existing_internal_result(
        goal, plan, [s for s in plan.steps if s.status == "pending"], evidence
    ) is False


def test_shortcut_never_repeats_a_negative_verification_for_the_same_draft(monkeypatch):
    goal, plan, evidence = prepared_internal()
    monkeypatch.setattr(
        "agent.prepared_review.current_prepared_review",
        lambda _goal: {"outcome": "partial", "what_is_missing": "Calcolo incompleto"},
    )
    assert not _ready_to_verify_existing_internal_result(
        goal, plan, [s for s in plan.steps if s.status == "pending"], evidence
    )
