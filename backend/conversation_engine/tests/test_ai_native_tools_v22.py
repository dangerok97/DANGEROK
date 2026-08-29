"""Prompt 7 V2.2 — general tool use, grounding, temporal facts (mocked)."""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

os.environ["AI_CORE_TRACE"] = "1"
os.environ["RESEARCH_ENABLED"] = "1"

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.grounding.temporal import apply_current_fact, get_current_facts
from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.ai_core.tools.providers.base import ProviderResult, RawHit
from conversation_engine.ai_core.tools.registry import ToolRegistry
from conversation_engine.ai_core.tools.sanitize import sanitize_external_query
from conversation_engine.ai_core.tools.web_search import execute_web_search
from conversation_engine.models import ConversationSession


def _scripted(queue: List[Dict[str, Any]]):
    payloads: List[str] = []

    async def fn(system: str, user: str) -> Dict[str, Any]:
        payloads.append(user)
        fn.payloads = payloads  # type: ignore[attr-defined]
        if not queue:
            return {
                "response_mode": "answer",
                "user_intent_summary": "done",
                "reasoning_status": "enough_information",
                "message_to_user": "Ok.",
            }
        return queue.pop(0)

    fn.payloads = payloads  # type: ignore[attr-defined]
    return fn


def _sess(uid="u1") -> ConversationSession:
    return ConversationSession(user_id=uid, meta={"ui_mode": "ai_core", "ai_core": {}})


# A — Travel/current: recognizes external operational need → web_search
@pytest.mark.asyncio
async def test_a_travel_needs_external_tool():
    q = [
        {
            "response_mode": "tool",
            "user_intent_summary": "reach city by noon tomorrow",
            "active_goal_summary": "Arrive by noon tomorrow",
            "reasoning_status": "needs_tool",
            "tool_call": {
                "capability": "web_search",
                "arguments": {
                    "query": "driving time tomorrow morning city arrival noon",
                    "purpose": "estimate travel duration",
                },
                "reason": "operational timing needs external grounding",
            },
        },
        {
            "response_mode": "answer",
            "user_intent_summary": "travel",
            "reasoning_status": "enough_information",
            "claim_grounding": "TOOL_OBSERVATION",
            "message_to_user": "Le stime disponibili suggeriscono circa 5 ore di guida.",
        },
    ]
    fake = ProviderResult(
        ok=True,
        provider="tavily",
        hits=[RawHit(title="Route info", url="https://example.com/route", snippet="About 5 hours driving")],
    )
    with patch(
        "conversation_engine.ai_core.tools.web_search._failover_search",
        new=AsyncMock(return_value=fake),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Domani devo andare a Roma e voglio arrivare alle 12.",
            db=None,
            decision_fn=_scripted(q),
        )
    assert res.tool_calls == 1
    assert res.external_queries == 1
    assert res.ai_calls == 2
    assert "5 ore" in res.ora_text
    assert res.sources


# B — Current public fact → web_search
@pytest.mark.asyncio
async def test_b_current_price_uses_web_search():
    q = [
        {
            "response_mode": "tool",
            "user_intent_summary": "current price",
            "reasoning_status": "needs_tool",
            "tool_call": {
                "capability": "web_search",
                "arguments": {"query": "current price of X today", "purpose": "current price"},
            },
        },
        {
            "response_mode": "answer",
            "user_intent_summary": "price",
            "claim_grounding": "TOOL_OBSERVATION",
            "message_to_user": "Le fonti indicano un prezzo intorno a 12 euro.",
        },
    ]
    fake = ProviderResult(
        ok=True,
        provider="brave",
        hits=[RawHit(title="Price", url="https://shop.example/x", snippet="12 EUR today")],
    )
    with patch(
        "conversation_engine.ai_core.tools.web_search._failover_search",
        new=AsyncMock(return_value=fake),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Quanto costa oggi X?",
            db=None,
            decision_fn=_scripted(q),
        )
    assert res.external_queries == 1
    assert "12" in res.ora_text


# C — Study: no StudyFlow; may ask/context/tool generically
@pytest.mark.asyncio
async def test_c_study_no_domain_flow():
    q = [
        {
            "response_mode": "ask",
            "user_intent_summary": "exam prep",
            "active_goal_summary": "Prepare for an exam",
            "reasoning_status": "needs_user_input",
            "question": "Di quale esame si tratta?",
        }
    ]
    res = await run_cognitive_loop(
        sess=_sess(),
        user_message="Tra dieci giorni ho l'esame di X. Aiutami a prepararlo.",
        db=None,
        decision_fn=_scripted(q),
    )
    assert res.mode == "ask"
    assert res.tool_calls == 0
    # no study-flow artifacts
    assert "StudyFlow" not in (res.ora_text or "")


# D — Energy: no EnergyFlow
@pytest.mark.asyncio
async def test_d_energy_no_domain_flow():
    q = [
        {
            "response_mode": "ask",
            "user_intent_summary": "electricity offer",
            "question": "Hai il dettaglio dell'offerta o la bolletta attuale?",
            "reasoning_status": "needs_user_input",
        }
    ]
    res = await run_cognitive_loop(
        sess=_sess(),
        user_message="Secondo te questa offerta luce mi conviene?",
        db=None,
        decision_fn=_scripted(q),
    )
    assert res.mode == "ask"
    assert "EnergyFlow" not in (res.ora_text or "")


# E — Adoption: stable guidance without DogFlow
@pytest.mark.asyncio
async def test_e_adoption_no_dogflow():
    q = [
        {
            "response_mode": "answer",
            "user_intent_summary": "adopt a dog",
            "claim_grounding": "MODEL_KNOWLEDGE",
            "message_to_user": (
                "In generale serve valutare tempo, spazio e requisiti del rifugio locale. "
                "Se vuoi requisiti aggiornati della tua zona posso verificarli."
            ),
        }
    ]
    res = await run_cognitive_loop(
        sess=_sess(),
        user_message="Vorrei adottare un cane, cosa devo fare?",
        db=None,
        decision_fn=_scripted(q),
    )
    assert res.tool_calls == 0
    assert "DogFlow" not in res.ora_text


# F — Novel domain: same architecture
@pytest.mark.asyncio
async def test_f_novel_domain_same_loop():
    q = [
        {
            "response_mode": "tool",
            "user_intent_summary": "urban beekeeping rules",
            "reasoning_status": "needs_tool",
            "tool_call": {
                "capability": "web_search",
                "arguments": {
                    "query": "urban rooftop beekeeping regulations",
                    "purpose": "local rules",
                },
            },
        },
        {
            "response_mode": "answer",
            "claim_grounding": "TOOL_OBSERVATION",
            "message_to_user": "Le fonti indicano che spesso servono regole comunali specifiche.",
        },
    ]
    fake = ProviderResult(
        ok=True,
        provider="tavily",
        hits=[RawHit(title="Rules", url="https://example.gov/bees", snippet="Municipal permit may be required")],
    )
    with patch(
        "conversation_engine.ai_core.tools.web_search._failover_search",
        new=AsyncMock(return_value=fake),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="Voglio iniziare ad allevare api sul terrazzo.",
            db=None,
            decision_fn=_scripted(q),
        )
    assert res.external_queries == 1
    assert "BeekeepingFlow" not in res.ora_text


# G — Stable concept: no unnecessary search
@pytest.mark.asyncio
async def test_g_inflation_no_search():
    q = [
        {
            "response_mode": "answer",
            "user_intent_summary": "explain inflation",
            "claim_grounding": "MODEL_KNOWLEDGE",
            "message_to_user": "L'inflazione è l'aumento generale dei prezzi nel tempo.",
        }
    ]
    res = await run_cognitive_loop(
        sess=_sess(),
        user_message="Spiegami cos'è l'inflazione.",
        db=None,
        decision_fn=_scripted(q),
    )
    assert res.tool_calls == 0
    assert res.external_queries == 0


# H — Personal name: context, no web
@pytest.mark.asyncio
async def test_h_personal_no_web():
    q = [
        {
            "response_mode": "answer",
            "user_intent_summary": "name",
            "claim_grounding": "PERSONAL_CONTEXT",
            "message_to_user": "Ti chiami Alex.",
        }
    ]
    res = await run_cognitive_loop(
        sess=_sess(),
        user_message="Come mi chiamo?",
        db=None,
        decision_fn=_scripted(q),
    )
    assert res.external_queries == 0
    assert res.tool_calls == 0


# I — Correction: temporary fact wins; durable not rewritten
@pytest.mark.asyncio
async def test_i_temporary_location_override():
    sess = _sess()
    q = [
        {
            "response_mode": "answer",
            "user_intent_summary": "temporary location",
            "active_goal_summary": "Travel planning",
            "state_updates": [
                {"path": "current_facts.location", "value": "Vibo Marina", "op": "set"},
                {"path": "active_goal.summary", "value": "Travel planning", "op": "set"},
            ],
            "message_to_user": "Ok, per ora parto dal fatto che sei a Vibo Marina.",
        }
    ]
    res = await run_cognitive_loop(
        sess=sess,
        user_message="Non sono a Tarquinia, questa settimana sono a Vibo Marina.",
        db=None,
        decision_fn=_scripted(q),
    )
    st = sess.meta["ai_core"]
    assert get_current_facts(st).get("location", {}).get("value") == "Vibo Marina"
    # Durable profile untouched (no profile write API called)
    assert "profile" not in json.dumps(st.get("last_ai_decision") or {})
    assert "Vibo Marina" in res.ora_text


# J — Tool failure: honest limitation, no invented facts
@pytest.mark.asyncio
async def test_j_tool_failure_honest():
    q = [
        {
            "response_mode": "tool",
            "reasoning_status": "needs_tool",
            "tool_call": {
                "capability": "web_search",
                "arguments": {"query": "current train schedule example", "purpose": "schedule"},
            },
        },
        {
            "response_mode": "answer",
            "claim_grounding": "INFERENCE",
            "message_to_user": (
                "Al momento non riesco ad accedere a dati aggiornati per dirtelo in modo affidabile."
            ),
        },
    ]
    with patch(
        "conversation_engine.ai_core.tools.web_search._failover_search",
        new=AsyncMock(
            return_value=ProviderResult(
                ok=False, provider="tavily", failure_code="NOT_CONFIGURED"
            )
        ),
    ):
        res = await run_cognitive_loop(
            sess=_sess(),
            user_message="A che ora parte il treno?",
            db=None,
            decision_fn=_scripted(q),
        )
    assert res.tool_calls == 1
    assert "affidabile" in res.ora_text.lower() or "non riesco" in res.ora_text.lower()
    # Must not invent a clock time as fact
    assert "09:42" not in res.ora_text


def test_sanitize_rejects_overpersonal():
    q, reason = sanitize_external_query(
        "Francesco Guardia di Finanza lives in Tarquinia currently on vacation with girlfriend"
    )
    assert q is None
    assert reason == "overpersonal_query"


def test_web_search_capability_registered():
    reg = ToolRegistry()
    spec = reg.get("web_search")
    assert spec is not None
    assert spec.side_effect == "READ_ONLY"
    assert spec.classification == "external"
    pub = reg.list_public()
    # V3.4 took it off the menu the model chooses from. Going out to the world
    # is one path now — response_mode=research — and this capability is the
    # tool layer underneath it, called directly by the research service. It
    # stays registered, executable and READ_ONLY; it is simply no longer a
    # second, blinder way to reach the same place.
    assert not any(p["capability"] == "web_search" for p in pub)
    # provider brands not exposed
    assert not any("tavily" in json.dumps(p).lower() for p in pub)


def test_consequential_write_not_auto():
    reg = ToolRegistry()
    g = validate_decision(
        {
            "response_mode": "tool",
            "tool_call": {"capability": "note_intention", "arguments": {"summary": "x"}},
            "reasoning_status": "needs_tool",
            "user_intent_summary": "x",
        },
        tools=reg,
    )
    # reversible write still allowed
    assert g.decision and g.decision.response_mode == "tool"


@pytest.mark.asyncio
async def test_research_disabled_observation():
    os.environ["RESEARCH_ENABLED"] = "0"
    try:
        obs = await execute_web_search({"query": "inflation rate italy"}, {})
        assert obs.status == "failed"
        assert (obs.payload.get("external") or {}).get("failure_code") == "NOT_CONFIGURED"
    finally:
        os.environ["RESEARCH_ENABLED"] = "1"


def test_no_domain_hardcoding_in_ai_core():
    root = Path(_BACKEND) / "conversation_engine" / "ai_core"
    banned = (
        "studyflow",
        "travelflow",
        "dogflow",
        "energyflow",
        "beekeepingflow",
        "francesco",
        "tarquinia",
        "vibo marina",
        "guardia di finanza",
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for b in banned:
            assert b not in text, f"{b} in {path}"


def test_prompt_has_tool_before_claim():
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    low = COGNITIVE_SYSTEM_PROMPT.lower()
    assert "tool before claim" in low or "tool before" in low
    assert "read_only" in low
    assert "current_facts" in low
