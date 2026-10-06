"""V89 — required skills may change, but never disappear silently."""

from pathlib import Path

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import (
    _active_skill_plan_state,
    _apply_skill_plan_releases,
    _persist_active_skill_plan,
)
from conversation_engine.ai_core.models import (
    Observation,
    SkillPlanRelease,
)
from conversation_engine.ai_core.tools.registry import ToolRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_current_observation_can_ground_release_of_downstream_skill():
    required = ["get_calendar_events", "cancel_calendar_event"]
    observations = [
        Observation(
            kind="tool",
            name="get_calendar_events",
            status="ok",
            payload={"status": "ok", "events": []},
        ).model_dump()
    ]
    release = SkillPlanRelease(
        capability="cancel_calendar_event",
        reason="The observed read made the downstream cancellation unnecessary.",
        basis="observation",
        observation_capability="get_calendar_events",
    )

    remaining, released, rejected = _apply_skill_plan_releases(
        required,
        [release],
        observations,
        persisted_outcomes=[],
        user_message="",
    )

    assert remaining == ["get_calendar_events"]
    assert released == ["cancel_calendar_event"]
    assert rejected == []


def test_persisted_prior_turn_outcome_can_ground_release():
    required = ["get_calendar_events", "cancel_calendar_event"]
    release = SkillPlanRelease(
        capability="cancel_calendar_event",
        reason="The prior real calendar read changed the route.",
        basis="observation",
        observation_capability="get_calendar_events",
    )

    remaining, released, rejected = _apply_skill_plan_releases(
        required,
        [release],
        [],
        persisted_outcomes=[{
            "capability": "get_calendar_events",
            "observed_capability": "get_calendar_events",
            "status": "ok",
            "result_status": "ok",
            "failure_kind": "",
        }],
        user_message="",
    )

    assert remaining == ["get_calendar_events"]
    assert released == ["cancel_calendar_event"]
    assert rejected == []


def test_fake_observation_cannot_release_required_skill():
    release = SkillPlanRelease(
        capability="cancel_calendar_event",
        reason="A search supposedly made it unnecessary.",
        basis="observation",
        observation_capability="web_search",
    )

    remaining, released, rejected = _apply_skill_plan_releases(
        ["get_calendar_events", "cancel_calendar_event"],
        [release],
        [],
        persisted_outcomes=[],
        user_message="",
    )

    assert remaining == ["get_calendar_events", "cancel_calendar_event"]
    assert released == []
    assert rejected == ["cancel_calendar_event"]


def test_latest_user_words_can_explicitly_change_scope():
    release = SkillPlanRelease(
        capability="prepare_a_phone_call",
        reason="The person explicitly removed the call from the request.",
        basis="user_message",
        user_instruction_quote="non chiamarlo più",
    )

    remaining, released, rejected = _apply_skill_plan_releases(
        ["prepare_a_phone_call", "get_calendar_events"],
        [release],
        [],
        persisted_outcomes=[],
        user_message="Va bene, ma non chiamarlo più. Controlla solo il calendario.",
    )

    assert remaining == ["get_calendar_events"]
    assert released == ["prepare_a_phone_call"]
    assert rejected == []


def test_model_paraphrase_is_not_user_message_evidence():
    release = SkillPlanRelease(
        capability="prepare_a_phone_call",
        reason="The person changed scope.",
        basis="user_message",
        user_instruction_quote="annulla la telefonata",
    )

    remaining, released, rejected = _apply_skill_plan_releases(
        ["prepare_a_phone_call"],
        [release],
        [],
        persisted_outcomes=[],
        user_message="Non chiamarlo più.",
    )

    assert remaining == ["prepare_a_phone_call"]
    assert released == []
    assert rejected == ["prepare_a_phone_call"]


def test_cannot_release_skill_that_was_never_required():
    release = SkillPlanRelease(
        capability="web_search",
        reason="Not needed.",
        basis="user_message",
        user_instruction_quote="non cercare sul web",
    )

    remaining, released, rejected = _apply_skill_plan_releases(
        ["get_calendar_events"],
        [release],
        [],
        persisted_outcomes=[],
        user_message="non cercare sul web",
    )

    assert remaining == ["get_calendar_events"]
    assert released == []
    assert rejected == ["web_search"]


def test_governance_rejects_unknown_release_capability():
    tools = ToolRegistry(db=None)
    result = validate_decision(
        {
            "response_mode": "answer",
            "reasoning_status": "enough_information",
            "message_to_user": "Continuo sul percorso aggiornato.",
            "user_intent_summary": "adattare il lavoro",
            "skill_plan": {
                "objective": "completare la richiesta",
                "required_capabilities": ["get_calendar_events"],
                "release_capabilities": [
                    {
                        "capability": "skill_inventata",
                        "reason": "non serve",
                        "basis": "user_message",
                        "user_instruction_quote": "non serve",
                    }
                ],
            },
        },
        tools=tools,
    )

    assert result.ok is True
    assert result.decision is not None
    assert result.decision.skill_plan is not None
    assert result.decision.skill_plan.release_capabilities == []
    assert "skill_plan_release_unknown_capability:skill_inventata" in result.errors


def test_governance_requires_user_quote_for_user_message_release():
    tools = ToolRegistry(db=None)
    result = validate_decision(
        {
            "response_mode": "answer",
            "reasoning_status": "enough_information",
            "message_to_user": "Continuo.",
            "user_intent_summary": "adattare il lavoro",
            "skill_plan": {
                "objective": "completare la richiesta",
                "required_capabilities": ["get_calendar_events"],
                "release_capabilities": [
                    {
                        "capability": "get_calendar_events",
                        "reason": "scope changed",
                        "basis": "user_message",
                    }
                ],
            },
        },
        tools=tools,
    )

    assert result.ok is True
    assert result.decision.skill_plan.release_capabilities == []
    assert "skill_plan_release_missing_user_quote" in result.errors


def test_persisted_outcomes_are_sanitized_metadata_only():
    state = {}
    persisted = _persist_active_skill_plan(
        state,
        objective="Completare la richiesta",
        required=["get_calendar_events", "cancel_calendar_event"],
        attempted={"get_calendar_events"},
        outcomes=[{
            "capability": "get_calendar_events",
            "observed_capability": "get_calendar_events",
            "status": "ok",
            "result_status": "ok",
            "failure_kind": "",
            "arguments": {"private": "must-not-persist"},
            "payload": {"events": ["must-not-persist"]},
        }],
        waiting=True,
    )

    visible = _active_skill_plan_state(state)
    assert visible is not None
    assert visible["capability_outcomes"][0] == {
        "capability": "get_calendar_events",
        "observed_capability": "get_calendar_events",
        "status": "ok",
        "result_status": "ok",
        "failure_kind": "",
    }
    assert "private" not in str(persisted)
    outcome_keys = set(persisted["capability_outcomes"][0])
    assert outcome_keys == {
        "capability",
        "observed_capability",
        "status",
        "result_status",
        "failure_kind",
    }


def test_prompt_forbids_silent_skill_drops_and_requires_real_basis():
    prompt = (
        ROOT / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")
    loop = (
        ROOT / "conversation_engine" / "ai_core" / "loop.py"
    ).read_text(encoding="utf-8")

    assert "release_capabilities" in prompt
    assert "do NOT silently omit it" in prompt
    assert "user_instruction_quote" in prompt
    assert "Never" in prompt and "invent evidence" in prompt
    assert "INVALID_SKILL_PLAN_RELEASE" in loop
    assert 'event="SKILL_PLAN_REVISED"' in loop
