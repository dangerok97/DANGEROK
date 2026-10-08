"""Phase 1: the final answer must reflect failed required capabilities.

These integration checks run the real session, cognitive loop, governance and
outcome contract with scripted model decisions and provider observations.
No account is accessed and no external side effect is performed.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import (
    _unverified_skill_failure_copy,
    run_cognitive_loop,
)
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession


@pytest.fixture(autouse=True)
def trace_for_synthetic_tests(monkeypatch):
    monkeypatch.setenv("AI_CORE_TRACE", "1")


def _session():
    return ConversationSession(
        user_id="synthetic-phase1-owner",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )


def _tool(name, *, required=None):
    decision = {
        "response_mode": "tool",
        "reasoning_status": "needs_tool",
        "tool_call": {"capability": name, "arguments": {}},
        "situation_update": {"operation": "none"},
    }
    if required is not None:
        decision["skill_plan"] = {
            "objective": "Controllare impegni e percorso",
            "required_capabilities": required,
            "completion_condition": "Entrambi i controlli verificati",
        }
    return decision


def _answer(text):
    return {
        "response_mode": "answer",
        "reasoning_status": "enough_information",
        "message_to_user": text,
        "situation_update": {"operation": "none"},
    }


async def _failed_route_turn(monkeypatch, *, final_text, retryable=False):
    observed = []

    async def execute(self, capability, arguments, *, runtime):
        observed.append(capability)
        if capability == "get_route":
            return Observation(
                kind="tool", name=capability, status="ok",
                payload={
                    "status": "unavailable",
                    "available": False,
                    "retryable": retryable,
                    "why_unavailable": "nessun percorso dal provider",
                },
            )
        return Observation(
            kind="tool", name=capability, status="ok",
            payload={"status": "ok", "events": []},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    turns = 0

    async def decide(system, payload):
        nonlocal turns
        turns += 1
        if turns == 1:
            return _tool(
                "get_calendar_events",
                required=["get_calendar_events", "get_route"],
            )
        if turns == 2:
            return _tool("get_route")
        return _answer(final_text)

    session = _session()
    result = await run_cognitive_loop(
        sess=session,
        user_message="Controlla il calendario e il tragitto.",
        db=AsyncMongoMockClient().phase1_final_skill_truth,
        decision_fn=decide,
        max_steps=3,
    )
    assert observed == ["get_calendar_events", "get_route"]
    assert result.ok and result.tool_calls == 2
    return result, session


@pytest.mark.asyncio
async def test_false_final_success_claim_is_replaced_when_required_route_failed(
    monkeypatch,
):
    result, session = await _failed_route_turn(
        monkeypatch, final_text="Ho completato tutto e organizzato il percorso.",
    )
    assert "La richiesta non è ancora completata" in result.ora_text
    assert "Ho completato tutto" not in result.ora_text
    assert result.trace.get("skill_plan_failed") == ["get_route"]
    assert any(
        item.get("event") == "SKILL_PLAN_FAILURE_USER_NOTICE"
        for item in result.trace.get("steps", [])
    )
    # One persisted answer, identical to the one the person actually read.
    assert session.meta["ai_core"]["recent_turns"][-1]["text"] == result.ora_text


@pytest.mark.asyncio
async def test_useful_partial_result_is_preserved_with_an_explicit_failure_notice(
    monkeypatch,
):
    result, session = await _failed_route_turn(
        monkeypatch,
        final_text=(
            "Ho verificato gli impegni del calendario, ma il servizio "
            "non ha restituito un percorso."
        ),
    )
    assert "Ho verificato gli impegni" in result.ora_text
    assert "La richiesta non è ancora completata" in result.ora_text
    assert session.meta["ai_core"]["recent_turns"][-1]["text"] == result.ora_text


def test_failure_copy_replaces_empty_and_bare_acknowledgements():
    for draft in ("", "Ok.", "Perfetto."):
        text = _unverified_skill_failure_copy(draft)
        assert "La richiesta non è ancora completata" in text
        assert draft not in text or not draft


def test_explicit_provider_retry_does_not_mean_execution_succeeded():
    text = _unverified_skill_failure_copy("Ho completato tutto.", retryable=True)
    assert "La richiesta non è ancora completata" in text
    assert "consente di riprovare" in text
    assert "Ho completato tutto" not in text


@pytest.mark.asyncio
async def test_successful_chain_does_not_receive_failure_notice(monkeypatch):
    async def execute(self, capability, arguments, *, runtime):
        return Observation(
            kind="tool", name=capability, status="ok",
            payload={"status": "ok", "events": []},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    decisions = 0

    async def decide(system, payload):
        nonlocal decisions
        decisions += 1
        if decisions == 1:
            return _tool(
                "get_calendar_events", required=["get_calendar_events"],
            )
        return _answer("Ho verificato il calendario.")

    result = await run_cognitive_loop(
        sess=_session(),
        user_message="Controlla il calendario.",
        db=AsyncMongoMockClient().phase1_success_no_notice,
        decision_fn=decide,
        max_steps=2,
    )
    assert result.ok
    assert result.ora_text == "Ho verificato il calendario."
    assert result.trace.get("skill_plan_completed") is True
