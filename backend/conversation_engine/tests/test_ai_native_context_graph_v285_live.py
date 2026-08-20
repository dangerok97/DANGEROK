"""Minimal provider-real semantic gate for V2.8.5 Life Context Graph (opt-in,
quota-bearing). Mirrors test_ai_native_uncertainty_v284_live.py's shape and
budget discipline — a handful of high-value scenarios, never a stress test.
"""

from __future__ import annotations

import os

import pytest

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import _call_ai
from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT, build_user_payload
from conversation_engine.ai_core.tools.registry import ToolRegistry


pytestmark = pytest.mark.skipif(
    not (os.environ.get("GEMINI_API_KEY") or "").strip(),
    reason="GEMINI_API_KEY absent — provider-real V2.8.5 not executed",
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
async def test_provider_real_continuity_uses_retrieved_graph_evidence():
    # Turn 1: no graph evidence supplied yet — model should seek grounding rather
    # than guess. It may retrieve via response_mode=context, ask the user, or use
    # a READ_ONLY tool (e.g. get_active_plan) — any non-guessing path is valid.
    first = await _decide("Per quella cosa di cui parlavamo la scorsa volta, cosa manca ancora?")
    if first.response_mode == "tool":
        assert first.tool_call and first.tool_call.resolved_capability
    else:
        assert first.response_mode in ("context", "ask")
    # Turn 2: the relevant relationship is now supplied as retrieved evidence.
    second = await _decide(
        "Per quella cosa di cui parlavamo la scorsa volta, cosa manca ancora?",
        facts=[{
            "statement": "goal:qa_goal_v285 --depends_on--> plan:qa_plan_v285 (piano ancora incompleto)",
            "source": "life_context_graph", "authority": "structured", "status": "active",
            "ref": "lce_qa_v285", "provenance": ["qa_controlled"],
        }],
        observations=[{
            "kind": "context", "name": "context_broker", "status": "ok",
            "payload": {"item_count": 1, "grounding": "PERSONAL_CONTEXT"},
        }],
    )
    assert second.response_mode != "ask"


@pytest.mark.asyncio
async def test_provider_real_correction_proposes_supersede_not_duplicate():
    decision = await _decide(
        "In realta' quel collegamento non e' piu' giusto: ora dipende da un piano diverso.",
        facts=[{
            "statement": "goal:qa_goal_v285 --depends_on--> plan:qa_plan_old (relazione attiva)",
            "source": "life_context_graph", "authority": "structured", "status": "active",
            "ref": "lce_qa_old", "provenance": ["qa_controlled"],
        }],
        observations=[{
            "kind": "tool", "name": "context_graph_mutation", "status": "ok",
            "payload": {
                "results": [{
                    "decision": "REQUIRES_SUPERSESSION",
                    "code": "EXISTING_EDGE_REQUIRES_RELATIONSHIP",
                    "edge_id": "lce_qa_old",
                    "persisted": False,
                }]
            },
        }],
    )
    updates = decision.context_graph_updates
    if updates:
        op = updates[0].operation
        assert op in ("supersede", "update")
        if op == "supersede":
            assert updates[0].edge_id == "lce_qa_old"


@pytest.mark.asyncio
async def test_provider_real_arbitrary_life_scenario_no_crash_no_router():
    decision = await _decide(
        "Ho iniziato a occuparmi di un piccolo orto sul balcone: voglio collegarlo "
        "al mio obiettivo di rilassarmi di piu' durante la settimana."
    )
    assert decision.response_mode in ("answer", "ask", "tool", "act", "context", "finish")
    for u in decision.context_graph_updates:
        assert u.predicate is None or (1 <= len(u.predicate) <= 60)


@pytest.mark.asyncio
async def test_provider_real_uncertainty_retrieves_graph_before_asking_again():
    decision = await _decide(
        "Mi manca ancora qualcosa per quell'obiettivo collegato?",
        facts=[{
            "statement": "goal:qa_goal_v285 --related_to--> object:qa_object_v285",
            "source": "life_context_graph", "authority": "structured", "status": "active",
            "ref": "lce_qa_related", "provenance": ["qa_controlled"],
        }],
    )
    assert decision.response_mode != "ask" or bool(decision.uncertainty)
