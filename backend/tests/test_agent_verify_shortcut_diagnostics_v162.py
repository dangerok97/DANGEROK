"""Boolean-only observations of a stalled internal verification checkpoint.

No real user, connector, payment, transport, external service or model call.
These flags are diagnostic and NEVER grant authority to close a goal.
"""
import json

from agent.evidence import real_support
from agent.models import ActionPlan, ActionStep, AgentEvidence, AutonomousGoal, ResultProvenance
from agent.service import _internal_verify_blocker_flags, _ready_to_verify_existing_internal_result


def state():
    goal = AutonomousGoal(
        owner_id="synthetic-owner", status="active", origin="agent_initiated",
        source_kind="opportunity", objective="Confronto di prova",
        desired_outcome="Documento interno, senza azioni esterne",
        source_refs=["mem_synthetic"],
        prepared_text="Secondo i dati forniti: 180 contro 120, differenza 60.",
        prepared_sources=["evd_synthetic_source"],
    )
    steps = [
        ActionStep(ordinal=0, step_type="inspect", status="succeeded",
                   intent="Leggere la nota", capability_needed="information.read"),
        ActionStep(ordinal=1, step_type="prepare", status="succeeded",
                   intent="Preparare il confronto", capability_needed="document.create"),
        ActionStep(ordinal=2, step_type="verify", status="pending",
                   intent="Verificare sulla fonte", capability_needed="information.read"),
    ]
    plan = ActionPlan(owner_id="synthetic-owner", goal_id=goal.id,
                      status="active", steps=steps)
    evidence = [AgentEvidence(
        id="evd_synthetic_source", owner_id="synthetic-owner", goal_id=goal.id,
        claim="Fonte sintetica", provenance=ResultProvenance(
            source_class="internal_observation", capability="information.read",
            source_refs=["mem_synthetic"],
        ),
    )]
    return goal, plan, steps[2:], evidence


def test_complete_internal_result_can_be_verified_without_another_choice():
    goal, plan, pending, evidence = state()
    flags = _internal_verify_blocker_flags(goal, plan, pending, evidence)
    assert flags and all(value is True for value in flags.values())
    assert _ready_to_verify_existing_internal_result(goal, plan, pending, evidence)
    assert real_support(evidence)  # Not a claim that the comparison itself is true.


def test_diagnostic_never_outputs_identifiers_or_private_content():
    goal, plan, pending, evidence = state()
    goal.prepared_text += " PRIVATE_DRAFT_SHOULD_NEVER_APPEAR"
    goal.source_refs.append("mem_PRIVATE_HANDLE")
    flags = _internal_verify_blocker_flags(goal, plan, pending, evidence)
    serialized = json.dumps(flags, ensure_ascii=False)
    assert all(type(value) is bool for value in flags.values())
    assert set(flags) == {
        "goal_active", "plan_active", "non_situation", "no_human_block",
        "has_artifact_and_sources", "review_absent", "prepared_sources_in_evidence",
        "no_external_step", "prepared_step_succeeded", "pending_verify_only",
        "pending_no_input_ref", "pending_no_parameters",
        "pending_no_human_or_effect_target",
    }
    assert "PRIVATE" not in serialized and "synthetic" not in serialized


def test_pending_unread_source_and_cursor_still_refuse_shortcut():
    goal, plan, pending, evidence = state()
    pending[0].input_refs = ["memory:missing-current-coverage"]
    flags = _internal_verify_blocker_flags(goal, plan, pending, evidence)
    assert flags["pending_no_input_ref"] is False
    assert not _ready_to_verify_existing_internal_result(goal, plan, pending, evidence)
    pending[0].input_refs = []
    pending[0].parameters = {"memory_offset": 600, "memory_version": "synthetic-v2"}
    assert _internal_verify_blocker_flags(goal, plan, pending, evidence)["pending_no_parameters"] is False
    assert not _ready_to_verify_existing_internal_result(goal, plan, pending, evidence)


def test_negative_review_and_external_effect_keep_completion_guard_closed():
    goal, plan, pending, evidence = state()
    from agent.models import PreparedResultReview
    # Even without crafting a review, a world-changing step must exclude this shortcut.
    other = ActionStep(ordinal=3, step_type="execute",
                       intent="Change an external provider", status="skipped",
                       capability_needed="calendar.write", external_effect=True)
    plan.steps.append(other)
    assert _internal_verify_blocker_flags(goal, plan, pending, evidence)["no_external_step"] is False
    assert not _ready_to_verify_existing_internal_result(goal, plan, pending, evidence)
