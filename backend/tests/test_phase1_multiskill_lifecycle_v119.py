"""Phase 1: exercise real AI Core orchestration over scripted tool observations.

The cognitive loop, plan persistence, governance and turn boundaries are real.
Only the model decisions and tool-provider responses are controlled fixtures.
No real accounts, network access or personal user data are touched.
"""
import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession


@pytest.fixture(autouse=True)
def enable_diagnostic_trace(monkeypatch):
    monkeypatch.setenv("AI_CORE_TRACE", "1")


def session():
    return ConversationSession(
        user_id="phase1-multiskill-owner",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )


def tool_decision(capability, *, plan=None, resume=None):
    decision = {
        "response_mode": "tool",
        "reasoning_status": "needs_tool",
        "user_intent_summary": "organizzare una richiesta con più strumenti",
        "tool_call": {"capability": capability, "arguments": {}},
        "situation_update": {"operation": "none"},
    }
    if plan:
        decision["skill_plan"] = {
            "objective": "Verificare impegni e percorso",
            "required_capabilities": ["get_calendar_events", "get_route"],
            "completion_condition": "Esito osservato e riuscito di entrambe le skill",
            **({"resume_plan_ref": resume} if resume else {}),
        }
    return decision


def answer(text):
    return {
        "response_mode": "answer",
        "reasoning_status": "enough_information",
        "message_to_user": text,
        "situation_update": {"operation": "none"},
    }


@pytest.mark.asyncio
async def test_two_required_skills_complete_only_after_both_observations(monkeypatch):
    observed = []

    async def execute(self, capability, args, *, runtime):
        observed.append(capability)
        return Observation(
            kind="tool", name=capability, status="ok",
            payload={"status": "ok"},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return tool_decision("get_calendar_events", plan=True)
        if calls == 2:
            return tool_decision("get_route")
        return answer("Ho completato i due controlli richiesti.")

    sess = session()
    result = await run_cognitive_loop(
        sess=sess, user_message="Controlla impegni e percorso.",
        db=AsyncMongoMockClient().phase1_chain_complete,
        decision_fn=decide, max_steps=5,
    )
    assert result.ok
    assert observed == ["get_calendar_events", "get_route"]
    assert result.tool_calls == 2
    assert "due controlli" in result.ora_text
    assert result.trace.get("skill_plan_completed") is True
    assert sess.meta["ai_core"]["active_skill_plan"] is None


@pytest.mark.asyncio
async def test_failed_second_skill_does_not_claim_completion(monkeypatch):
    observed = []

    async def execute(self, capability, args, *, runtime):
        observed.append(capability)
        if capability == "get_route":
            return Observation(
                kind="tool", name=capability, status="error",
                payload={"status": "provider_error", "failure_code": "ROUTE_UNAVAILABLE"},
            )
        return Observation(kind="tool", name=capability, status="ok",
                           payload={"status": "ok"})

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return tool_decision("get_calendar_events", plan=True)
        if calls == 2:
            return tool_decision("get_route")
        return answer(
            "Non ho potuto verificare il percorso: l'organizzazione non è completa."
        )

    sess = session()
    result = await run_cognitive_loop(
        sess=sess, user_message="Organizza il mio spostamento.",
        db=AsyncMongoMockClient().phase1_chain_fail,
        decision_fn=decide, max_steps=5,
    )
    assert result.ok
    assert observed == ["get_calendar_events", "get_route"]
    assert result.tool_calls == 2
    assert "non è completa" in result.ora_text
    assert "get_route" in result.trace.get("skill_plan_failed", [])
    assert sess.meta["ai_core"]["active_skill_plan"] is None


@pytest.mark.asyncio
async def test_multi_skill_chain_survives_user_clarification_across_turns(monkeypatch):
    observed = []

    async def execute(self, capability, args, *, runtime):
        observed.append(capability)
        return Observation(
            kind="tool", name=capability, status="ok",
            payload={"status": "ok"},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    first_calls = 0

    async def first_decide(system, payload):
        nonlocal first_calls
        first_calls += 1
        if first_calls == 1:
            return tool_decision("get_calendar_events", plan=True)
        return {
            "response_mode": "ask",
            "reasoning_status": "needs_user_input",
            "question": "Da quale indirizzo partiamo?",
            "message_to_user": "Da quale indirizzo partiamo?",
            "situation_update": {"operation": "none"},
        }

    sess = session()
    db = AsyncMongoMockClient().phase1_chain_resume
    first = await run_cognitive_loop(
        sess=sess, user_message="Controlla il calendario e poi il percorso.",
        db=db, decision_fn=first_decide, max_steps=3,
    )
    assert first.ok
    assert first.mode == "ask"
    state = sess.meta["ai_core"]
    plan = state["active_skill_plan"]
    assert plan and plan["waiting"] is True
    assert plan["required_capabilities"] == ["get_calendar_events", "get_route"]
    assert observed == ["get_calendar_events"]
    plan_ref = plan["plan_ref"]

    resumed_calls = 0

    async def resumed_decide(system, payload):
        nonlocal resumed_calls
        resumed_calls += 1
        if resumed_calls == 1:
            return tool_decision("get_route", plan=True, resume=plan_ref)
        return answer("Ho completato i controlli dopo il tuo chiarimento.")

    second = await run_cognitive_loop(
        sess=sess, user_message="Partiamo da casa.",
        db=db, decision_fn=resumed_decide, max_steps=4,
    )
    assert second.ok
    assert observed == ["get_calendar_events", "get_route"]
    assert second.tool_calls == 1
    assert second.trace.get("skill_plan_completed") is True
    assert sess.meta["ai_core"]["active_skill_plan"] is None


@pytest.mark.asyncio
async def test_sixth_skill_stays_pending_after_five_tool_calls(monkeypatch):
    """The per-turn budget must never turn a 6-step request into 5-step success."""
    required = [
        "get_calendar_events", "get_route", "get_weather_forecast",
        "get_profile_snapshot", "list_life_places", "search_my_life",
    ]
    observed = []

    async def execute(self, capability, args, *, runtime):
        observed.append(capability)
        return Observation(
            kind="tool", name=capability, status="ok",
            payload={"status": "ok"},
        )

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    calls = 0

    async def decide(system, payload):
        nonlocal calls
        calls += 1
        if calls <= 6:
            decision = {
                "response_mode": "tool",
                "reasoning_status": "needs_tool",
                "tool_call": {"capability": required[calls - 1], "arguments": {}},
                "situation_update": {"operation": "none"},
            }
            if calls == 1:
                decision["skill_plan"] = {
                    "objective": "Completa sei verifiche necessarie",
                    "required_capabilities": required,
                    "completion_condition": "Tutte le sei letture osservate",
                }
            return decision
        return answer("Ho concluso tutto.")

    sess = session()
    result = await run_cognitive_loop(
        sess=sess, user_message="Organizza sei verifiche indispensabili.",
        db=AsyncMongoMockClient().phase1_sixth_skill,
        decision_fn=decide, max_steps=7,
    )
    assert result.ok
    assert result.tool_calls == 5
    assert observed == required[:5]
    assert "completare la richiesta" in result.ora_text.lower()
    plan = sess.meta["ai_core"]["active_skill_plan"]
    assert plan["required_capabilities"] == required
    assert "search_my_life" in plan["required_capabilities"]
    assert result.trace.get("skill_plan_paused") is True
