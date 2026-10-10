"""Synthetic regression tests for bounded phone conversations; no real calls."""
import pytest
from mongomock_motor import AsyncMongoMockClient
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.models import ConversationSession
from telephone.caps import _the_person_said_yes


@pytest.mark.asyncio
async def test_phone_tool_sentence_survives_reasoning_limit(monkeypatch):
    expected = "Non ho un recapito. Quale numero devo usare?"

    async def execute(self, capability, args, *, runtime):
        assert capability == "prepare_a_phone_call"
        return Observation(
            kind="tool", name=capability, status="ok",
            payload={"status": "preparing", "say_this": expected},
        )

    async def decide(system, user):
        return {
            "response_mode": "tool", "reasoning_status": "needs_tool",
            "tool_call": {"capability": "prepare_a_phone_call", "arguments": {}},
            "user_intent_summary": "preparare una chiamata",
            "situation_update": {"operation": "none"},
        }

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    result = await run_cognitive_loop(
        sess=ConversationSession(
            user_id="synthetic-owner", meta={"ui_mode": "ai_core", "ai_core": {}},
        ),
        user_message="Chiama il contatto fittizio.",
        db=AsyncMongoMockClient().test_phone_bound,
        decision_fn=decide, max_steps=1,
    )
    assert result.ora_text == expected
    assert result.tool_calls == 1


def test_go_ahead_requires_explicit_post_summary_assent():
    assert _the_person_said_yes("non aggiungo altro, chiama", via_libera=True)
    assert not _the_person_said_yes("non aggiungo altro, chiama", via_libera=False)
    assert not _the_person_said_yes("non chiamare", via_libera=True)
    assert not _the_person_said_yes("chiama", via_libera=True)


@pytest.mark.asyncio
async def test_ask_for_missing_number_survives_short_followup(monkeypatch):
    from preparation.preparation import MissionPreparation, MissingInformation, remember

    db = AsyncMongoMockClient().phone_followup
    prep = MissionPreparation(
        owner_id="synthetic-owner", counterparty="Persona Esempio",
        user_request="Chiama Persona Esempio.",
        missing_information=[MissingInformation(
            field="phone", question="Mi serve il recapito di Persona Esempio.",
        )],
    )
    await remember(db, prep)

    async def execute(self, capability, args, *, runtime):
        return Observation(kind="tool", name=capability, status="ok", payload={})

    async def decide(system, user):
        return {
            "response_mode": "tool", "reasoning_status": "needs_tool",
            "tool_call": {"capability": "note_intention", "arguments": {}},
            "user_intent_summary": "continuare una richiesta",
            "situation_update": {"operation": "none"},
        }

    monkeypatch.setattr(ToolRegistry, "execute", execute)
    result = await run_cognitive_loop(
        sess=ConversationSession(
            user_id="synthetic-owner",
            meta={"ui_mode": "ai_core", "ai_core": {
                "active_preparation_id": prep.preparation_id,
            }},
        ),
        user_message="non aggiungo altro, chiama",
        db=db, decision_fn=decide, max_steps=1,
    )
    assert result.ora_text == "Mi serve il recapito di Persona Esempio."
