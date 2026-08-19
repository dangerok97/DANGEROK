"""Minimal provider-real semantic gate for V2.8.4 (opt-in, quota-bearing)."""

from __future__ import annotations

import os

import pytest

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import _call_ai
from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT, build_user_payload
from conversation_engine.ai_core.tools.registry import ToolRegistry


pytestmark = pytest.mark.skipif(
    not (os.environ.get("GEMINI_API_KEY") or "").strip(),
    reason="GEMINI_API_KEY absent — provider-real V2.8.4 not executed",
)


async def _decide(message, *, turns=None, facts=None, observations=None, life_os=None):
    raw = await _call_ai(
        decision_fn=None,
        system=COGNITIVE_SYSTEM_PROMPT,
        user=build_user_payload(
            user_message=message,
            recent_turns=turns or [],
            active_goal=None,
            context_facts=facts or [],
            tools=ToolRegistry().list_public(),
            observations=observations or [],
            life_os=life_os or {},
        ),
    )
    assert raw is not None
    governed = validate_decision(raw, tools=ToolRegistry())
    assert governed.ok and governed.decision
    return governed.decision


@pytest.mark.asyncio
async def test_provider_real_does_not_overclarify_non_blocking_statement():
    decision = await _decide("Domani viene Luca a cena.")
    assert decision.response_mode != "ask"


@pytest.mark.asyncio
async def test_provider_real_uses_context_before_redundant_question():
    first = await _decide("A che ora dovrei uscire per il mio impegno di domani?")
    assert first.response_mode == "context"
    second = await _decide(
        "A che ora dovrei uscire per il mio impegno di domani?",
        facts=[{
            "statement": "L'impegno di domani inizia alle 10:00; il piano indica 30 minuti di margine.",
            "source": "life_os", "authority": "system-structured", "status": "known",
            "ref": "qa:v284:commitment", "provenance": ["qa_controlled"],
        }],
        observations=[{
            "kind": "context", "name": "context_broker", "status": "ok",
            "payload": {"item_count": 1, "grounding": "PERSONAL_CONTEXT"},
        }],
    )
    assert second.response_mode != "ask"


@pytest.mark.asyncio
async def test_provider_real_asks_only_for_blocking_arbitrary_detail():
    decision = await _decide(
        "Invia il pacco al destinatario, ma non ti ho ancora dato l'indirizzo."
    )
    assert decision.response_mode in ("ask", "act")
    if decision.response_mode == "ask":
        assert decision.question and decision.uncertainty


@pytest.mark.asyncio
async def test_provider_real_correction_reuses_situation_and_supersedes_assumption():
    decision = await _decide(
        "No, il dettaglio corretto è venerdì, non giovedì.",
        facts=[{
            "statement": "Situation id=sit_qa_v284 revision=1; assumption: il dettaglio è giovedì",
            "source": "situation", "authority": "system-structured", "status": "known",
            "ref": "situation:sit_qa_v284", "provenance": ["user_conversation"],
        }],
    )
    update = decision.situation_update
    assert update and update.operation == "update"
    assert update.situation_id == "sit_qa_v284"
    assert update.supersedes
    assert decision.memory_candidates == []


@pytest.mark.asyncio
async def test_provider_real_refusal_does_not_repeat_question():
    decision = await _decide(
        "Non voglio specificarlo. Fai tu, ma non eseguire nulla senza di me.",
        turns=[
            {"role": "user", "text": "Organizza questa cosa.", "kind": "message"},
            {"role": "ora", "text": "Quale opzione preferisci?", "kind": "ask"},
        ],
    )
    assert decision.response_mode != "ask"
