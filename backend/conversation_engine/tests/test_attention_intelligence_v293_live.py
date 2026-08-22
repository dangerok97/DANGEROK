"""Minimal provider-real semantic gate for V2.9.3 Attention Intelligence
(opt-in, quota-bearing).

Six scenarios, one attention call each. Every scenario drives the REAL prompt
through the REAL Provider Manager and validates the decision shape; none of
them writes a suggestion, dispatches anything, or executes a tool.

Assertions check properties of the judgement, never a specific expected
sentence — and scenario 6 checks the property that matters most for this
sprint: the deterministic system gate can always overrule the model toward
quiet, whatever the model asked for.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from life_attention.gate import apply_system_gate  # noqa: E402
from life_attention.models import DELIVERY_ORDER  # noqa: E402
from life_attention.prompt import (  # noqa: E402
    ATTENTION_SYSTEM_PROMPT,
    build_attention_payload,
)
from life_attention.service import _parse_json  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (os.environ.get("GEMINI_API_KEY") or "").strip(),
    reason="GEMINI_API_KEY absent — provider-real V2.9.3 not executed",
)

_VALID = set(DELIVERY_ORDER)
_LOUD = {"ask_user", "propose_action", "notify"}
# Attention decisions the model must not smuggle in, and process traces.
_FORBIDDEN_KEYS = {
    "send_push", "chain_of_thought", "thinking", "reasoning_trace",
    "message_to_user", "scratchpad",
}

_FREE_CONTEXT = {
    "local_hour": 15, "timezone": "Europe/Rome",
    "busy_in_commitment_now": False, "commitments_next_2h": 0,
    "suggestions_shown_last_hour": 0, "suggestions_currently_visible": 0,
    "times_ora_already_raised_this": 0,
}


async def _attend(*, conclusions, situation=None):
    """One real attention call through the Provider Manager."""
    from llm.manager import get_manager

    payload = build_attention_payload(
        assessments=conclusions,
        operational_context={**_FREE_CONTEXT, **(situation or {})},
    )
    result = await get_manager().chat(
        system=ATTENTION_SYSTEM_PROMPT, user=payload, json_mode=True
    )
    parsed = _parse_json(getattr(result, "text", "") or "")
    assert parsed is not None, "attention returned unparseable output"
    return parsed


def _assert_contract(out):
    assert out.get("delivery") in _VALID, out.get("delivery")
    for key in ("utility", "urgency", "confidence", "novelty", "actionability"):
        if out.get(key) is not None:
            assert 0.0 <= float(out[key]) <= 1.0
    assert len(str(out.get("proposed_title") or "")) <= 200
    blob = json.dumps(out, ensure_ascii=False).lower()
    for key in _FORBIDDEN_KEYS:
        assert f'"{key}"' not in blob, f"forbidden field leaked: {key}"


def _conclusion(*, impacts, relevance=0.6, confidence=0.7, next_step="none",
                requires_more=False, ref="situation:sit_live"):
    return [{
        "assessment_id": "lia_live",
        "focal_refs": [ref],
        "relevance": relevance,
        "confidence": confidence,
        "requires_more_context": requires_more,
        "next_step_kind": next_step,
        "status": "complete",
        "impacts": impacts,
    }]


@pytest.mark.asyncio
async def test_provider_real_1_high_value_is_not_silent():
    """A concrete, well-supported, time-bound consequence should reach the
    user somehow — staying silent about this would be a miss."""
    out = await _attend(conclusions=_conclusion(
        relevance=0.9, confidence=0.9,
        impacts=[{
            "statement": "Un impegno confermato si sovrappone a un altro già preso lo stesso giorno.",
            "kind": "conflict", "epistemic_status": "confirmed", "confidence": 0.92,
            "temporal_horizon": "near_term", "capability_hint": "get_calendar_events",
        }],
    ))
    _assert_contract(out)
    assert out["delivery"] != "silent", "a confirmed imminent conflict deserves attention"


@pytest.mark.asyncio
async def test_provider_real_2_low_value_stays_silent():
    """A trivial, low-stakes change: the right answer is to say nothing."""
    out = await _attend(conclusions=_conclusion(
        relevance=0.1, confidence=0.5,
        impacts=[{
            "statement": "La descrizione di una nota personale è stata leggermente riformulata.",
            "kind": "constraint", "epistemic_status": "confirmed", "confidence": 0.6,
            "temporal_horizon": "unscheduled", "capability_hint": None,
        }],
    ))
    _assert_contract(out)
    assert out["delivery"] in ("silent", "defer"), (
        "a cosmetic change must not become an interruption"
    )


@pytest.mark.asyncio
async def test_provider_real_3_speculative_is_not_pushed():
    """Plausible but thinly evidenced: never a push, and preferably quiet."""
    out = await _attend(conclusions=_conclusion(
        relevance=0.4, confidence=0.3, requires_more=True,
        next_step="gather_context",
        impacts=[{
            "statement": "Potrebbe emergere la necessità di una preparazione aggiuntiva, ma le informazioni sono scarse.",
            "kind": "dependency", "epistemic_status": "tentative", "confidence": 0.3,
            "temporal_horizon": "unknown", "capability_hint": None,
        }],
    ))
    _assert_contract(out)
    assert out["delivery"] != "notify", "speculation must never interrupt"
    # And the model should not claim high confidence about a tentative item.
    assert float(out.get("confidence") or 0) < 0.85


@pytest.mark.asyncio
async def test_provider_real_4_missing_information_can_justify_asking():
    """A specific missing piece that blocks a CONCRETE benefit is the one case
    where a proactive question earns its cost.

    The scenario states what is blocked and what it costs, because the prompt
    deliberately tells the model not to ask questions whose payoff is unclear
    — an abstract "something is missing" should, correctly, stay silent.
    """
    out = await _attend(conclusions=_conclusion(
        relevance=0.85, confidence=0.85, requires_more=True, next_step="ask_user",
        impacts=[
            {
                "statement": "Una scadenza confermata fra tre giorni non può essere preparata finché manca un dato che solo l'utente conosce.",
                "kind": "dependency", "epistemic_status": "confirmed", "confidence": 0.9,
                "temporal_horizon": "near_term", "capability_hint": None,
            },
            {
                "statement": "Il dato mancante è una singola informazione che l'utente può fornire in una frase.",
                "kind": "missing_information", "epistemic_status": "inferred",
                "confidence": 0.85, "temporal_horizon": "near_term", "capability_hint": None,
            },
        ],
    ))
    _assert_contract(out)
    # Asking, showing it quietly, or deferring are all defensible; silently
    # dropping a near-term blocker the user alone can clear is not.
    assert out["delivery"] != "silent"


@pytest.mark.asyncio
async def test_provider_real_5_opportunity_is_surfaced_without_pushing():
    """A comparison opportunity may be worth surfacing, but it is not urgent
    and must stay vendor-neutral."""
    out = await _attend(conclusions=_conclusion(
        relevance=0.7, confidence=0.75, next_step="compare_options",
        impacts=[{
            "statement": "Potrebbe valere la pena confrontare le opzioni disponibili prima di decidere.",
            "kind": "opportunity", "epistemic_status": "tentative", "confidence": 0.7,
            "temporal_horizon": "later", "capability_hint": None,
        }],
    ))
    _assert_contract(out)
    assert out["delivery"] != "notify", "an opportunity is not an emergency"
    blob = json.dumps(out, ensure_ascii=False).lower()
    import re

    for invented in ("amazon", "google", "unicredit", "tan", "taeg", "eur", "usd"):
        assert not re.search(rf"\b{invented}\b", blob), f"named a vendor/rate: {invented}"
    assert "€" not in blob and "$" not in blob
    assert not re.search(r"\d+([.,]\d+)?\s*%", blob), "invented a rate"


@pytest.mark.asyncio
async def test_provider_real_6_system_gate_overrules_the_model():
    """The decisive property of this sprint: whatever the model asks for, the
    deterministic gate can only make the outcome quieter.

    One real reasoning call, then the SAME model output evaluated against a
    free context and a hostile one — the difference is the system's, not the
    model's.
    """
    out = await _attend(conclusions=_conclusion(
        relevance=0.95, confidence=0.95,
        impacts=[{
            "statement": "Un impegno confermato si sovrappone a un altro già preso.",
            "kind": "conflict", "epistemic_status": "confirmed", "confidence": 0.95,
            "temporal_horizon": "immediate", "capability_hint": None,
        }],
    ))
    _assert_contract(out)

    ai_delivery = out["delivery"]
    confidence = float(out.get("confidence") or 0.9)
    utility = float(out.get("utility") or 0.9)

    free_ctx = {
        "interruption_cost": 0.0, "user_dismiss_rate": 0.0,
        "notifications_allowed": True, "quiet_hours": False,
        "likely_sleep": False, "busy_in_commitment_now": False,
    }
    hostile_ctx = {
        "interruption_cost": 0.9, "user_dismiss_rate": 0.8,
        "notifications_allowed": False, "quiet_hours": True,
        "likely_sleep": True, "busy_in_commitment_now": True,
    }

    free_delivery, free_reasons = apply_system_gate(
        ai_delivery=ai_delivery, confidence=confidence, utility=utility,
        context=free_ctx, times_already_raised=0,
    )
    hostile_delivery, hostile_reasons = apply_system_gate(
        ai_delivery=ai_delivery, confidence=confidence, utility=utility,
        context=hostile_ctx, times_already_raised=5,
    )

    # The gate never amplifies the model's choice.
    assert DELIVERY_ORDER.index(free_delivery) <= DELIVERY_ORDER.index(ai_delivery)
    # A hostile moment is never louder than a free one...
    assert DELIVERY_ORDER.index(hostile_delivery) <= DELIVERY_ORDER.index(free_delivery)
    # ...and if the model wanted to speak at all, the system really did
    # intervene rather than merely agreeing.
    if ai_delivery in _LOUD:
        assert hostile_delivery == "silent"
        assert hostile_reasons
