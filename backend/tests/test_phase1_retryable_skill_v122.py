"""Phase 1 — explicit transient failures do not destroy a resumable skill plan.

Only the model's decisions and external tool outcomes are scripted. The
cognitive loop, persisted session and skill completion logic are real.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import (
    _merge_skill_outcomes,
    _required_skill_states,
    _retryable_failed_skill_caps,
    _skill_outcome_summary,
    run_cognitive_loop,
)
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession


@pytest.fixture(autouse=True)
def enable_trace(monkeypatch):
    monkeypatch.setenv("AI_CORE_TRACE", "1")


def outcome(cap, *, status="ok", result_status="ok", retryable=False):
    return {
        "capability": cap,
        "observed_capability": cap,
        "status": status,
        "result_status": result_status,
        "failure_kind": "" if status == "ok" else "PROVIDER_DOWN",
        "retryable": retryable,
    }


def test_retryability_is_explicit_boolean_not_string_or_error_guess():
    for flag, expected in ((True, True), (False, False), ("true", False)):
        obs = Observation(
            kind="tool", name="get_route", status="failed",
            payload={
                "status": "provider_error",
                "failure_code": "PROVIDER_DOWN",
                "retryable": flag,
                "private_message": "should never persist",
            },
        )
        meta = _skill_outcome_summary("get_route", obs)
        assert meta["retryable"] is expected
        assert "private_message" not in str(meta)
        assert "arguments" not in str(meta)


def test_only_latest_failed_retry_is_recoverable():
    required = ["get_calendar_events", "get_route"]
    history = _merge_skill_outcomes([], [
        outcome("get_calendar_events"),
        outcome("get_route", status="failed", result_status="provider_error", retryable=True),
    ])
    assert _retryable_failed_skill_caps(required, history) == ["get_route"]
    assert _required_skill_states(required, history)["failed"] == ["get_route"]
    after_retry = _merge_skill_outcomes(history, [outcome("get_route")])
    assert _retryable_failed_skill_caps(required, after_retry) == []
    assert _required_skill_states(required, after_retry)["failed"] == []


def test_a_new_terminal_failure_replaces_an_earlier_retryable_failure():
    required = ["get_route"]
    before = _merge_skill_outcomes([], [
        outcome("get_route", status="failed", result_status="provider_error", retryable=True),
    ])
    after = _merge_skill_outcomes(before, [
        outcome("get_route", status="failed", result_status="unsupported", retryable=False),
    ])
    assert _retryable_failed_skill_caps(required, before) == required
    assert _retryable_failed_skill_caps(required, after) == []


def _tool_decision(name, required=None, resume_ref=""):
    row = {
        "response_mode": "tool",
        "reasoning_status": "needs_tool",
        "tool_call": {"capability": name, "arguments": {}},
        "situation_update": {"operation": "none"},
    }
    if required is not None:
        row["skill_plan"] = {
            "objective": "Controllare calendario e percorso",
            "required_capabilities": required,
            "completion_condition": "Entrambe le skill hanno esito verificato",
            **({"resume_plan_ref": resume_ref} if resume_ref else {}),
        }
    return row


def _answer(text):
    return {
        "response_mode": "answer",
        "reasoning_status": "enough_information",
        "message_to_user": text,
        "situation_update": {"operation": "none"},
    }


@pytest.mark.asyncio
async def test_transient_second_skill_failure_survives_and_resumes_across_turns(
    monkeypatch,
):
    required = ["get_calendar_events", "get_route"]
    observed = []
    route_tries = 0

    async def execute(self, capability, args, *, runtime):
        nonlocal route_tries
        observed.append(capability)
        if capability == "get_route":
            route_tries += 1
            if route_tries == 1:
                return Observation(
                    kind="tool", name=capability, status="failed",
                    payload={
                        "status": "provider_error",
                        "failure_code": "TEMPORARY_ROUTING_OUTAGE",
                        "retryable": True,
                    },
                )
        return Observation(
            kind="tool", name=capability, status="ok", payload={"status": "ok"},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    db = AsyncMongoMockClient().phase1_retry_resume
    sess = ConversationSession(
        user_id="synthetic-owner",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )
    turns = 0

    async def first_decide(system, payload):
        nonlocal turns
        turns += 1
        if turns == 1:
            return _tool_decision("get_calendar_events", required=required)
        if turns == 2:
            return _tool_decision("get_route")
        return _answer("Il provider del percorso è temporaneamente indisponibile.")

    first = await run_cognitive_loop(
        sess=sess, user_message="Controlla calendario e percorso.",
        db=db, decision_fn=first_decide, max_steps=5,
    )
    assert first.ok
    assert observed == required
    assert "temporaneamente" in first.ora_text
    stored = sess.meta["ai_core"]["active_skill_plan"]
    assert stored is not None
    assert stored["required_capabilities"] == required
    assert stored["waiting"] is False
    assert _required_skill_states(required, stored["capability_outcomes"]) == {
        "succeeded": ["get_calendar_events"],
        "waiting": [], "failed": ["get_route"], "unseen": [],
    }
    assert _retryable_failed_skill_caps(
        required, stored["capability_outcomes"]
    ) == ["get_route"]
    assert first.trace.get("skill_plan_retryable") == ["get_route"]
    assert "args" not in str(stored)
    ref = stored["plan_ref"]
    resumes = 0

    async def resumed_decide(system, payload):
        nonlocal resumes
        resumes += 1
        if resumes == 1:
            return _tool_decision("get_route", required=required, resume_ref=ref)
        return _answer("Adesso anche il percorso è stato verificato.")

    second = await run_cognitive_loop(
        sess=sess, user_message="Riprendi il controllo del percorso.",
        db=db, decision_fn=resumed_decide, max_steps=4,
    )
    assert second.ok
    assert observed == [*required, "get_route"]
    assert second.tool_calls == 1
    assert second.trace.get("skill_plan_completed") is True
    assert sess.meta["ai_core"]["active_skill_plan"] is None


@pytest.mark.asyncio
async def test_transient_failure_at_last_reasoning_step_remains_recoverable(
    monkeypatch,
):
    async def execute(self, capability, args, *, runtime):
        return Observation(
            kind="tool", name=capability, status="failed",
            payload={
                "status": "provider_error",
                "failure_code": "TEMPORARY_DOWN",
                "retryable": True,
            },
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    sess = ConversationSession(
        user_id="synthetic-owner",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )

    async def decide(system, payload):
        return _tool_decision("get_route", required=["get_route"])

    result = await run_cognitive_loop(
        sess=sess, user_message="Verifica il percorso",
        db=AsyncMongoMockClient().phase1_retry_bound,
        decision_fn=decide, max_steps=1,
    )
    assert result.ok
    assert result.trace.get("skill_plan_retryable") == ["get_route"]
    assert result.trace.get("skill_plan_paused") is True
    assert "provider permette di riprovare" in result.ora_text
    assert sess.meta["ai_core"]["active_skill_plan"] is not None
