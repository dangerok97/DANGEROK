"""Minimal provider-real semantic gate for V2.9.2 Impact Reasoning (opt-in,
quota-bearing).

Five scenarios, one reasoning call each — the same budget discipline as the
other `_live.py` gates. Every scenario drives the REAL prompt through the REAL
Provider Manager and validates the decision shape; none of them writes to a
life subsystem, calls a tool, or creates a suggestion.

Each assertion checks a property of the reasoning, never a specific expected
sentence: the whole point of this layer is that it generalises to life areas
nobody enumerated.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from life_reasoning.prompt import IMPACT_SYSTEM_PROMPT, build_impact_payload  # noqa: E402
from life_reasoning.service import _parse_json  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (os.environ.get("GEMINI_API_KEY") or "").strip(),
    reason="GEMINI_API_KEY absent — provider-real V2.9.2 not executed",
)

_VALID_KINDS = {
    "dependency", "risk", "opportunity", "constraint", "conflict",
    "missing_information",
}
_VALID_STATUS = {"tentative", "asserted", "confirmed", "inferred"}
_VALID_NEXT = {"none", "gather_context", "ask_user", "propose_action", "compare_options"}
# Attention decisions belong to V2.9.3 and must never appear here.
_FORBIDDEN_KEYS = {
    "notify", "send_now", "surface_home", "interrupt", "notification_text",
    "batch_notification", "message_to_user", "chain_of_thought", "thinking",
}


async def _reason(*, changes, evidence, relations=None, capabilities=None, priors=None):
    """One real reasoning call through the Provider Manager — never a direct
    vendor SDK call, so failover and the circuit breaker stay in force."""
    from llm.manager import get_manager

    payload = build_impact_payload(
        changes=changes,
        evidence=evidence,
        relations=relations or [],
        capabilities=capabilities or [
            "get_calendar_events", "create_calendar_event", "create_plan",
            "search_life_memory", "web_search",
        ],
        prior_conclusions=priors or [],
        now_local="2026-08-21T10:00+02:00",
        timezone_name="Europe/Rome",
    )
    result = await get_manager().chat(
        system=IMPACT_SYSTEM_PROMPT, user=payload, json_mode=True
    )
    parsed = _parse_json(getattr(result, "text", "") or "")
    assert parsed is not None, "impact reasoning returned unparseable output"
    return parsed


def _assert_contract(out):
    """Shape guarantees every scenario must satisfy."""
    assert isinstance(out.get("impacts"), list)
    assert len(out["impacts"]) <= 8
    for impact in out["impacts"]:
        assert impact.get("kind") in _VALID_KINDS, impact.get("kind")
        assert impact.get("epistemic_status") in _VALID_STATUS
        assert 0.0 <= float(impact.get("confidence", 0)) <= 1.0
        assert len(str(impact.get("statement") or "")) <= 400
    assert out.get("next_step_kind") in _VALID_NEXT
    assert 0.0 <= float(out.get("relevance", 0)) <= 1.0
    blob = json.dumps(out, ensure_ascii=False).lower()
    for key in _FORBIDDEN_KEYS:
        assert f'"{key}"' not in blob, f"attention/CoT field leaked: {key}"


@pytest.mark.asyncio
async def test_provider_real_1_arbitrary_life_change_no_invention():
    """A neutral change in an unanticipated life area: the model should find
    plausible consequences without asserting facts nobody supplied."""
    out = await _reason(
        changes=[{
            "ref": "situation:sit_live_1", "system": "situation",
            "change": "created", "occurred_at": "2026-08-21T09:40+02:00",
        }],
        evidence=[{
            "statement": "L'utente ha iniziato a prendersi cura di un bonsai ereditato.",
            "source": "situation", "authority": "user_stated", "status": "active",
            "ref": "situation:sit_live_1",
        }],
    )
    _assert_contract(out)
    assert out["impacts"], "a real change should yield at least one consequence"
    # Nothing was supplied about dates, people or amounts — so nothing may be
    # asserted as confirmed on that basis.
    for impact in out["impacts"]:
        if impact["epistemic_status"] == "confirmed":
            assert impact.get("evidence_refs"), (
                "a confirmed impact must rest on evidence refs"
            )


@pytest.mark.asyncio
async def test_provider_real_2_goal_reveals_unstated_dependency():
    """A broad goal with little detail: the model should surface at least one
    dependency or missing piece the user never mentioned."""
    out = await _reason(
        changes=[{
            "ref": "goal:goal_live_2", "system": "life_os", "change": "created",
        }],
        evidence=[{
            "statement": "Obiettivo: organizzare una mostra fotografica di quartiere entro l'autunno.",
            "source": "life_os", "authority": "user_stated", "status": "active",
            "ref": "goal:goal_live_2",
        }],
    )
    _assert_contract(out)
    kinds = {i["kind"] for i in out["impacts"]}
    # The property is "something is not yet resolved". The contract lets the
    # model express that through an impact kind OR through the honesty
    # channels, and all of them are equally correct answers — pinning it to
    # one representation would test model phrasing, not model behaviour.
    surfaces_open_item = (
        bool(kinds & {"dependency", "missing_information"})
        or bool(out.get("requires_more_context"))
        or out.get("next_step_kind") in ("gather_context", "ask_user")
    )
    assert surfaces_open_item, (
        "a broad, under-specified goal should reveal something not yet resolved"
    )


@pytest.mark.asyncio
async def test_provider_real_3_context_linked_consequence_is_grounded():
    """Situation + Calendar + Plan, connected by a known relation: the
    consequence should reference the refs it was actually given."""
    out = await _reason(
        changes=[{
            "ref": "calendar:ced_live_3", "system": "calendar", "change": "updated",
            "related_refs": ["situation:sit_live_3"],
        }],
        evidence=[
            {
                "statement": "Situazione attiva: preparazione di un evento comunitario.",
                "source": "situation", "authority": "user_stated", "status": "active",
                "ref": "situation:sit_live_3",
            },
            {
                "statement": "Impegno spostato a venerdì 18:00 Europe/Rome.",
                "source": "calendar", "authority": "structured", "status": "active",
                "ref": "calendar:ced_live_3",
            },
            {
                "statement": "Piano collegato con due passi ancora aperti.",
                "source": "life_os", "authority": "structured", "status": "active",
                "ref": "plan:plan_live_3",
            },
        ],
        relations=["situation:sit_live_3 --scheduled_as--> calendar:ced_live_3"],
    )
    _assert_contract(out)
    known = {
        "situation:sit_live_3", "calendar:ced_live_3", "plan:plan_live_3",
    }
    cited = {
        r
        for impact in out["impacts"]
        for r in (impact.get("affected_refs") or []) + (impact.get("evidence_refs") or [])
    }
    assert cited, "a grounded consequence should cite the refs it was given"
    # Every cited ref must be one that actually existed in the input.
    assert cited <= known, f"invented refs: {cited - known}"


@pytest.mark.asyncio
async def test_provider_real_4_insufficient_evidence_is_admitted():
    """Almost no context: the honest answer is to say information is missing,
    not to produce a confident narrative."""
    out = await _reason(
        changes=[{"ref": "situation:sit_live_4", "system": "situation", "change": "updated"}],
        evidence=[],
    )
    _assert_contract(out)
    admits = (
        bool(out.get("requires_more_context"))
        or any(i["kind"] == "missing_information" for i in out["impacts"])
        or out.get("next_step_kind") in ("gather_context", "ask_user")
        or not out["impacts"]
    )
    assert admits, "with no evidence the model must not invent a confident story"
    # And nothing may be claimed as confirmed on the strength of nothing.
    for impact in out["impacts"]:
        assert impact["epistemic_status"] != "confirmed" or impact.get("evidence_refs")


@pytest.mark.asyncio
async def test_provider_real_5_option_comparison_stays_vendor_neutral():
    """A change that opens a real choice: the model may note that comparing
    options would help, but must not name a vendor or invent an offer."""
    out = await _reason(
        changes=[{"ref": "situation:sit_live_5", "system": "situation", "change": "created"}],
        evidence=[{
            "statement": "L'utente sta valutando un acquisto importante e non ha ancora deciso come procedere.",
            "source": "situation", "authority": "user_stated", "status": "active",
            "ref": "situation:sit_live_5",
        }],
    )
    _assert_contract(out)
    import re

    blob = json.dumps(out, ensure_ascii=False).lower()
    # No invented commercial specifics: no currency amounts, no rates, no
    # brands. Word-boundary matching, not substring — "tan" also lives inside
    # "importante", and a naive check would flag correct output.
    for invented in ("tan", "taeg", "amazon", "google", "unicredit", "eur", "usd"):
        assert not re.search(rf"\b{invented}\b", blob), (
            f"invented commercial specific: {invented}"
        )
    # No fabricated figures at all (prices, rates, percentages).
    assert "€" not in blob and "$" not in blob
    assert not re.search(r"\d+([.,]\d+)?\s*%", blob), "invented a rate/percentage"
    # It is legitimate (not required) to propose comparing options; if it does,
    # it must be as an opportunity, never as a completed search.
    if out.get("next_step_kind") == "compare_options":
        assert any(i["kind"] == "opportunity" for i in out["impacts"])
