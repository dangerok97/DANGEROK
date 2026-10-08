"""V87 — AI owns skill selection; runtime enforces declared execution."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import (
    _merge_required_skill_caps,
    _pending_required_skill_caps,
    _record_skill_attempt,
    _required_skill_states,
)
from conversation_engine.ai_core.models import SkillPlan
from conversation_engine.ai_core.tools.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_skill_plan_is_bounded_and_deduplicated():
    plan = SkillPlan(
        objective="Portare a termine la richiesta",
        required_capabilities=[
            "get_calendar_events",
            "get_calendar_events",
            "cancel_calendar_event",
            "web_search",
            "search_my_life",
            "get_profile_snapshot",
            "prepare_amazon_search",
        ],
    )

    assert plan.required_capabilities == [
        "get_calendar_events",
        "cancel_calendar_event",
        "web_search",
        "search_my_life",
        "get_profile_snapshot",
        "prepare_amazon_search",
    ]


def test_governance_keeps_only_real_catalogue_capabilities():
    tools = ToolRegistry(db=None)
    result = validate_decision(
        {
            "response_mode": "answer",
            "reasoning_status": "enough_information",
            "message_to_user": "Sto verificando.",
            "user_intent_summary": "fare qualcosa",
            "skill_plan": {
                "objective": "ottenere il risultato reale",
                "required_capabilities": [
                    "get_calendar_events",
                    "capability_che_non_esiste",
                ],
                "completion_condition": "avere una prova reale",
            },
        },
        tools=tools,
    )

    assert result.ok is True
    assert result.decision is not None
    assert result.decision.skill_plan is not None
    assert result.decision.skill_plan.required_capabilities == [
        "get_calendar_events"
    ]
    assert "skill_plan_unknown_capability:capability_che_non_esiste" in result.errors


def test_declared_requirements_survive_later_model_rounds():
    required = _merge_required_skill_caps(
        [], ["search_my_life", "get_calendar_events"]
    )
    required = _merge_required_skill_caps(
        required, ["get_calendar_events", "open_navigation"]
    )

    assert required == [
        "search_my_life",
        "get_calendar_events",
        "open_navigation",
    ]
    assert _pending_required_skill_caps(
        required, {"search_my_life"}
    ) == ["get_calendar_events", "open_navigation"]


def test_wrapper_and_leaf_observation_both_count_as_attempted():
    attempted = _record_skill_attempt(
        set(),
        "continue_calendar_action",
        "cancel_calendar_event",
    )

    assert "continue_calendar_action" in attempted
    assert "cancel_calendar_event" in attempted
    assert _pending_required_skill_caps(
        ["cancel_calendar_event"], attempted
    ) == []


def test_prompt_makes_skill_selection_ai_owned_not_keyword_routed():
    prompt = (
        ROOT / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")
    loop = (
        ROOT / "conversation_engine" / "ai_core" / "loop.py"
    ).read_text(encoding="utf-8")

    assert "skill_plan" in prompt
    assert "backend must NOT infer it from keywords or domains" in prompt
    assert "required_capabilities" in prompt
    assert "DECLARED_SKILL_PLAN_INCOMPLETE" in loop
    assert 'event="SKILL_PLAN_INCOMPLETE_NUDGE"' in loop


def test_required_skills_beyond_single_turn_budget_survive_without_false_success():
    """Six steps cannot be silently reduced to five because one turn has 5 calls."""
    from conversation_engine.ai_core.loop import (
        _persist_active_skill_plan,
        _active_skill_plan_state,
        _required_skill_plan_satisfied,
    )

    required = [
        "get_calendar_events", "get_route", "get_weather_forecast",
        "search_my_life", "get_profile_snapshot", "get_current_location",
    ]
    plan = SkillPlan(
        objective="Preparare una partenza completa",
        required_capabilities=required,
    )
    assert plan.required_capabilities == required
    state = {}
    outcomes = [{
        "capability": name, "observed_capability": name,
        "status": "ok", "result_status": "ok", "failure_kind": "",
    } for name in required[:5]]
    _persist_active_skill_plan(
        state, objective=plan.objective, required=plan.required_capabilities,
        attempted=set(required[:5]), outcomes=outcomes,
    )
    restored = _active_skill_plan_state(state)
    assert restored is not None
    assert restored["required_capabilities"] == required
    assert restored["pending_capabilities"] == ["get_current_location"]
    assert not _required_skill_plan_satisfied(required, outcomes)


def test_plan_above_twelve_skills_must_be_rejected_not_truncated():
    tools = ToolRegistry(db=None)
    catalog = [row["capability"] for row in tools.list_public()]
    assert len(catalog) >= 13
    with pytest.raises(ValidationError):
        SkillPlan(objective="Many steps", required_capabilities=catalog[:13])
    answer = validate_decision({
        "response_mode": "answer",
        "reasoning_status": "ready_to_act",
        "message_to_user": "Fatto.",
        "skill_plan": {
            "objective": "Many steps",
            "required_capabilities": catalog[:13],
        },
    }, tools=tools)
    assert answer.ok is False
    assert "skill_plan_invalid" in answer.errors


def test_plan_state_keeps_successes_beyond_ten_observations():
    from conversation_engine.ai_core.loop import _merge_skill_outcomes
    required = [
        "get_calendar_events", "get_route", "get_weather_forecast",
        "search_my_life", "get_profile_snapshot", "get_current_location",
        "get_life_place", "list_life_places", "get_time_at_place",
        "get_journeys_between_places", "get_day_patterns", "web_search",
    ]
    outcomes = _merge_skill_outcomes([], [{
        "capability": name, "observed_capability": name,
        "status": "ok", "result_status": "ok", "failure_kind": "",
    } for name in required])
    assert len(outcomes) == 12
    assert all(
        name in _required_skill_states(required, outcomes)["succeeded"]
        for name in required
    )
