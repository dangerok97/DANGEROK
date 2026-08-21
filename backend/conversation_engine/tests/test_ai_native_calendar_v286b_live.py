"""Minimal provider-real semantic gate for V2.8.6b AI-native Calendar (opt-in,
quota-bearing). Mirrors test_ai_native_context_graph_v285_live.py's shape and
budget discipline — a handful of high-value scenarios, never a stress test.

Every scenario here is a single raw `_call_ai` reasoning check: it never
executes a tool handler, never touches Mongo, and never calls Google in any
mode (fake or real) — it only verifies the *decision shape* the real model
produces given typed evidence/observations, exactly like the four other
`_live.py` gates in this directory. No real Google Calendar event is ever
created, modified or cancelled by this file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.loop import _call_ai
from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT, build_user_payload
from conversation_engine.ai_core.tools.registry import ToolRegistry


pytestmark = pytest.mark.skipif(
    not (os.environ.get("GEMINI_API_KEY") or "").strip(),
    reason="GEMINI_API_KEY absent — provider-real V2.8.6b not executed",
)

_CALENDAR_WRITE_CAPS = {"create_calendar_event", "update_calendar_event", "cancel_calendar_event"}


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
async def test_provider_real_simple_read_grounds_before_answering():
    # Turn 1: no calendar evidence supplied yet — the model must not
    # hallucinate an answer; it should retrieve (context/tool) or ask.
    first = await _decide("Cosa ho domani pomeriggio?")
    if first.response_mode == "tool":
        assert first.tool_call and first.tool_call.resolved_capability == "get_calendar_events"
    else:
        assert first.response_mode in ("context", "ask")
    # Turn 2: bounded calendar evidence is now supplied as retrieved fact.
    second = await _decide(
        "Cosa ho domani pomeriggio?",
        facts=[{
            "statement": "calendar:ced_qa_read --event--> Dentista, domani 15:30-16:00 Europe/Rome",
            "source": "calendar", "authority": "structured", "status": "active",
            "ref": "calendar:ced_qa_read", "provenance": ["qa_controlled"],
        }],
        observations=[{
            "kind": "tool", "name": "get_calendar_events", "status": "ok",
            "payload": {"status": "ok", "events": [{
                "calendar_ref": "calendar:ced_qa_read", "title": "Dentista",
                "start_datetime": "2026-08-21T15:30:00+02:00",
                "end_datetime": "2026-08-21T16:00:00+02:00",
            }]},
        }],
    )
    assert second.response_mode != "ask"
    if second.response_mode == "tool":
        assert second.tool_call.resolved_capability not in _CALENDAR_WRITE_CAPS


@pytest.mark.asyncio
async def test_provider_real_create_proposes_before_writing():
    decision = await _decide(
        "Domani alle 18 devo chiamare Luca per il progetto, mettilo in calendario."
    )
    # A first, unconfirmed turn must never directly execute a calendar
    # write — only propose (act), ground first (context/read tool), or ask.
    if decision.response_mode == "tool":
        assert decision.tool_call and decision.tool_call.resolved_capability not in _CALENDAR_WRITE_CAPS
    else:
        assert decision.response_mode in ("act", "ask", "context")


@pytest.mark.asyncio
async def test_provider_real_correction_updates_not_duplicates():
    decision = await _decide(
        "Anzi alle 18:30, non alle 18.",
        facts=[{
            "statement": "calendar:ced_qa_corr --event--> Chiamata con Luca, domani 18:00-18:30 Europe/Rome",
            "source": "calendar", "authority": "structured", "status": "active",
            "ref": "calendar:ced_qa_corr", "provenance": ["qa_controlled"],
        }],
        observations=[{
            "kind": "tool", "name": "create_calendar_event", "status": "ok",
            "payload": {
                "status": "ok", "operation": "created", "calendar_ref": "calendar:ced_qa_corr",
                "timezone": {"tz_name": "Europe/Rome", "authority": "connector_calendar"},
            },
        }],
    )
    if decision.response_mode == "tool" and decision.tool_call.resolved_capability in _CALENDAR_WRITE_CAPS:
        assert decision.tool_call.resolved_capability == "update_calendar_event"
        args = decision.tool_call.arguments or {}
        assert args.get("calendar_ref") == "calendar:ced_qa_corr"
    else:
        # proposing the change again (act) or asking for the missing ref is
        # also acceptable — a second create_calendar_event is not.
        assert decision.response_mode in ("act", "ask")


@pytest.mark.asyncio
async def test_provider_real_situation_linked_context_aware():
    decision = await _decide(
        "Con l'aggiornamento di oggi sul trasloco, quando è fissato l'appuntamento col notaio?",
        facts=[
            {
                "statement": "Situazione attuale: trasloco in corso, appartamento nuovo da firmare",
                "source": "situation", "authority": "user_stated", "status": "active",
                "ref": "situation:qa_move_v286b", "provenance": ["qa_controlled"],
            },
            {
                "statement": "calendar:ced_qa_notary --event--> Notaio, venerdì 10:00-11:00 Europe/Rome",
                "source": "calendar", "authority": "structured", "status": "active",
                "ref": "calendar:ced_qa_notary", "provenance": ["qa_controlled"],
            },
        ],
    )
    assert decision.response_mode != "ask"
    if decision.response_mode == "tool":
        assert decision.tool_call.resolved_capability not in _CALENDAR_WRITE_CAPS


@pytest.mark.asyncio
async def test_provider_real_arbitrary_vague_reminder_no_silent_write():
    decision = await _decide(
        "Ho iniziato a prendermi cura di un bonsai, vorrei ricordarmi di annaffiarlo ogni tanto."
    )
    assert decision.response_mode in ("answer", "ask", "tool", "act", "context", "finish")
    # a vague, timeless reminder must never become a silently-executed
    # calendar write on this same unconfirmed turn.
    if decision.response_mode == "tool":
        assert decision.tool_call.resolved_capability not in _CALENDAR_WRITE_CAPS
