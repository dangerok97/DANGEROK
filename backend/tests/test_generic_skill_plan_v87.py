"""V87 — AI owns skill selection; runtime enforces declared execution."""

from pathlib import Path

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import (
    _merge_required_skill_caps,
    _pending_required_skill_caps,
    _record_skill_attempt,
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
