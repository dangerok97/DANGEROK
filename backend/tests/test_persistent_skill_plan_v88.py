"""V88 — multi-skill plans survive governed pauses and resume explicitly."""

from pathlib import Path

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import (
    _active_skill_plan_state,
    _observations_wait_for_user,
    _persist_active_skill_plan,
)
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_persisted_skill_plan_contains_only_orchestration_metadata():
    state = {}
    persisted = _persist_active_skill_plan(
        state,
        objective="Cancella l'impegno e poi prepara lo spostamento",
        required=["cancel_calendar_event", "open_navigation"],
        attempted={"cancel_calendar_event"},
        outcomes=[{
            "capability": "cancel_calendar_event",
            "observed_capability": "cancel_calendar_event",
            "status": "ok",
            "result_status": "ok",
            "failure_kind": "",
        }],
        waiting=True,
    )

    assert persisted["plan_ref"].startswith("skillplan_")
    assert persisted["required_capabilities"] == [
        "cancel_calendar_event",
        "open_navigation",
    ]
    assert persisted["attempted_capabilities"] == ["cancel_calendar_event"]
    assert "arguments" not in str(persisted)
    assert "confirmation_snapshot" not in str(persisted)

    visible = _active_skill_plan_state(state)
    assert visible is not None
    assert visible["plan_ref"] == persisted["plan_ref"]
    assert visible["pending_capabilities"] == ["open_navigation"]
    assert visible["waiting"] is True


def test_authority_required_observation_pauses_generic_skill_chain():
    obs = Observation(
        kind="tool",
        name="cancel_calendar_event",
        status="partial",
        payload={
            "status": "authority_required",
            "confirmation_request": {
                "question": "Elimino l'impegno?",
                "arguments": {"calendar_ref": "calendar:opaque"},
            },
        },
    )

    assert _observations_wait_for_user([obs.model_dump()]) is True


def test_normal_success_does_not_look_like_user_pause():
    obs = Observation(
        kind="tool",
        name="get_calendar_events",
        status="ok",
        payload={"status": "ok", "events": []},
    )

    assert _observations_wait_for_user([obs.model_dump()]) is False


def test_resume_plan_ref_survives_governance_validation():
    tools = ToolRegistry(db=None)
    result = validate_decision(
        {
            "response_mode": "tool",
            "reasoning_status": "needs_tool",
            "user_intent_summary": "continua quello che stavamo facendo",
            "tool_call": {
                "capability": "get_calendar_events",
                "operation": "run",
                "arguments": {"when": "today"},
            },
            "skill_plan": {
                "objective": "completare la richiesta",
                "required_capabilities": ["get_calendar_events"],
                "completion_condition": "avere l'osservazione",
                "resume_plan_ref": "skillplan_abc123",
            },
        },
        tools=tools,
    )

    assert result.ok is True
    assert result.decision is not None
    assert result.decision.skill_plan is not None
    assert result.decision.skill_plan.resume_plan_ref == "skillplan_abc123"


def test_loop_exposes_execution_plan_and_rejects_unknown_resume_ref():
    source = (
        ROOT / "conversation_engine" / "ai_core" / "loop.py"
    ).read_text(encoding="utf-8")

    assert '"execution_plan": active_execution_plan' in source
    assert "INVALID_SKILL_PLAN_RESUME" in source
    assert 'event="SKILL_PLAN_RESUMED"' in source
    assert "_persist_active_skill_plan(" in source


def test_prompt_requires_semantic_resume_not_blind_ref_echo():
    prompt = (
        ROOT / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")

    assert "resume_plan_ref" in prompt
    assert "semantically continues that work" in prompt
    assert "If the person clearly changed topic" in prompt
    assert "Do NOT skip ahead" in prompt
