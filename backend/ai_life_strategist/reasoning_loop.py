"""AI Reasoning Loop — every turn: read context → compute → ONE question → wait.

Never two questions at once. Re-plan when context changes.
Remember asked / refused / postponed — never repeat.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from ai_life_strategist.benefit_engine import (
    active_benefits,
    available_benefits,
    pick_best_benefit_for_gap,
)
from ai_life_strategist.knowledge_gap import compute_gaps, infer_domain_from_text, infer_known_from_text
from ai_life_strategist.minimum_life_context import compute_mlc_gaps, evaluate_mlc_coverage
from ai_life_strategist.models import ReasoningContext
from ai_life_strategist.policy import sanitize_known_facts, user_text_is_credential_dump

logger = logging.getLogger("ora.ai_life_strategist.reasoning_loop")


async def read_life_graph_summary(db, user_id: str) -> str:
    try:
        nodes = await db.life_nodes.find(
            {"user_id": user_id}, {"_id": 0, "type": 1, "label": 1, "domain": 1}
        ).to_list(12)
        if not nodes:
            return "Nessun nodo Life Graph ancora."
        bits = []
        for n in nodes:
            bits.append(str(n.get("label") or n.get("type") or n.get("domain") or "?"))
        return "Life Graph: " + ", ".join(bits[:8])
    except Exception:
        return "Life Graph non disponibile."


async def read_life_profile_facts(db, user_id: str) -> Dict[str, Any]:
    try:
        from life_setup.profile_service import LifeProfileService

        prof = await LifeProfileService(db).get(user_id)
        if not prof:
            return {}
        return LifeProfileService(db).flat_known(prof)
    except Exception:
        return {}


async def read_conversation_summary(db, user_id: str, asked: List[str]) -> str:
    try:
        sess = await db.conversation_sessions.find_one(
            {"user_id": user_id},
            {"_id": 0, "origin": 1, "status": 1, "updated_at": 1},
            sort=[("updated_at", -1)],
        )
        parts = []
        if sess:
            parts.append(f"Sessione CE: {sess.get('origin') or 'n/d'} ({sess.get('status')})")
        if asked:
            parts.append(f"Domande già poste: {len(asked)}")
        return "; ".join(parts) if parts else "Conversazione iniziale."
    except Exception:
        return f"Domande già poste: {len(asked)}" if asked else "Conversazione iniziale."


async def read_documents_summary(db, user_id: str, linked: List[str]) -> str:
    try:
        docs = await db.documents.find(
            {"user_id": user_id},
            {"_id": 0, "doc_type": 1, "filename": 1, "title": 1},
        ).to_list(8)
        types = list({*(linked or []), *[d.get("doc_type") for d in docs if d.get("doc_type")]})
        if not types and not docs:
            return "Nessun documento collegato."
        return "Documenti: " + ", ".join(str(t) for t in types[:8])
    except Exception:
        return "Documenti: " + (", ".join(linked) if linked else "nessuno")


async def read_goals_summary(db, user_id: str) -> str:
    try:
        goals = await db.goals.find(
            {"user_id": user_id},
            {"_id": 0, "title": 1, "status": 1, "type": 1},
        ).to_list(8)
        if not goals:
            return "Nessun obiettivo ancora."
        return "Obiettivi: " + ", ".join(
            str(g.get("title") or g.get("type") or "?") for g in goals[:6]
        )
    except Exception:
        return "Obiettivi non disponibili."


async def read_calendar_summary(db, user_id: str) -> str:
    try:
        ev = await db.calendar_events.find(
            {"user_id": user_id},
            {"_id": 0, "title": 1, "start_at": 1},
        ).to_list(5)
        if not ev:
            # Soft: Google calendar items may live elsewhere
            gcal = await db.google_calendar_events.find(
                {"user_id": user_id},
                {"_id": 0, "summary": 1, "start": 1},
            ).to_list(5)
            if not gcal:
                return "Nessun evento calendario recente."
            return "Calendario: " + ", ".join(
                str(e.get("summary") or "?") for e in gcal[:4]
            )
        return "Calendario: " + ", ".join(str(e.get("title") or "?") for e in ev[:4])
    except Exception:
        return "Calendario non disponibile."


def compute_useful_and_highest(
    known_keys: Set[str],
    missing_keys: List[str],
    *,
    focus_domain: Optional[str] = None,
) -> tuple[List[str], Optional[str]]:
    """What is useful next + highest concrete benefit code."""
    useful: List[str] = []
    highest: Optional[str] = None
    best_gain = -1.0
    gaps = compute_gaps(known_keys, asked_keys=set(), focus_domain=focus_domain)
    for g in gaps:
        if g.key not in missing_keys and missing_keys:
            # still consider top gaps
            pass
        useful.append(g.key)
        b = pick_best_benefit_for_gap(g.key, g.domain)
        if g.information_gain > best_gain:
            best_gain = g.information_gain
            highest = b.code
        if len(useful) >= 8:
            break
    return useful, highest


def confidence_from_coverage(known_keys: Set[str], missing_keys: List[str]) -> float:
    total = len(known_keys) + len(missing_keys)
    if total <= 0:
        return 0.4
    return max(0.15, min(0.95, len(known_keys) / total))


async def assemble_reasoning_context(
    user_id: str,
    *,
    db=None,
    known_facts: Optional[Dict[str, Any]] = None,
    asked_questions: Optional[List[str]] = None,
    asked_keys: Optional[List[str]] = None,
    refused_keys: Optional[List[str]] = None,
    postponed_keys: Optional[List[str]] = None,
    linked_doc_types: Optional[List[str]] = None,
    last_user_text: Optional[str] = None,
    session_phase: str = "active",
    domains_touched: Optional[List[str]] = None,
) -> ReasoningContext:
    """Full AI Reasoning Loop steps 1–7 → ReasoningContext for plan (steps 8–9)."""
    facts = sanitize_known_facts(dict(known_facts or {}))
    if db is not None:
        try:
            profile_facts = await read_life_profile_facts(db, user_id)
            for k, v in profile_facts.items():
                if k not in facts and v not in (None, "", [], False):
                    facts[k] = v
        except Exception:
            logger.debug("profile read skipped", exc_info=True)

    if last_user_text and not user_text_is_credential_dump(last_user_text):
        facts.update(infer_known_from_text(last_user_text))

    known_keys: Set[str] = {k for k, v in facts.items() if v not in (None, False, "", [])}
    skip_keys = set(asked_keys or []) | set(refused_keys or []) | set(postponed_keys or [])

    inferred = infer_domain_from_text(last_user_text or "")
    touched = list(domains_touched or [])
    if inferred and inferred not in touched:
        touched.append(inferred)

    # Prefer MLC gaps for first-launch planning; domain gaps remain available as fallback list
    mlc_gaps = compute_mlc_gaps(
        facts,
        asked_keys=skip_keys,
        refused_keys=set(refused_keys or []),
        postponed_keys=set(postponed_keys or []),
    )
    gaps = mlc_gaps or compute_gaps(
        known_keys,
        asked_keys=skip_keys,
        focus_domain=inferred,
        domains=None,
    )
    missing = [g.key for g in gaps]
    mlc_cov = evaluate_mlc_coverage(
        facts,
        refused_keys=set(refused_keys or []),
        postponed_keys=set(postponed_keys or []),
    )
    avail = available_benefits(known_keys)
    active = active_benefits(known_keys)
    useful, highest = compute_useful_and_highest(
        known_keys, missing, focus_domain=inferred
    )
    # Surface MLC gaps first for Gemini / observability (not a UI checklist)
    useful = [f"mlc_missing:{n}" for n in mlc_cov.missing] + [
        u for u in useful if not str(u).startswith("mlc_missing:")
    ]
    conf = confidence_from_coverage(known_keys, missing)
    if not mlc_cov.sufficient:
        conf = min(conf, 0.55 + 0.08 * mlc_cov.covered_count)

    goals_s = calendar_s = docs_s = conv_s = ""
    if db is not None:
        goals_s = await read_goals_summary(db, user_id)
        calendar_s = await read_calendar_summary(db, user_id)
        docs_s = await read_documents_summary(db, user_id, list(linked_doc_types or []))
        conv_s = await read_conversation_summary(db, user_id, list(asked_questions or []))
        # Enrich conversation with KG hint
        kg = await read_life_graph_summary(db, user_id)
        if kg:
            conv_s = f"{conv_s} | {kg}".strip(" |")
    else:
        docs_s = "Documenti: " + (", ".join(linked_doc_types or []) or "nessuno")
        conv_s = f"Domande già poste: {len(asked_questions or [])}"
        goals_s = "Obiettivi non caricati in questo turno."
        calendar_s = "Calendario non caricato in questo turno."

    return ReasoningContext(
        user_id=user_id,
        domains_touched=touched,
        known_facts=facts,
        missing_keys=missing,
        asked_questions=list(asked_questions or []),
        asked_keys=list(asked_keys or []),
        refused_keys=list(refused_keys or []),
        postponed_keys=list(postponed_keys or []),
        linked_doc_types=list(linked_doc_types or []),
        last_user_text=last_user_text,
        session_phase=session_phase,
        benefits_available=[b.code for b in avail],
        benefits_active=[b.code for b in active],
        goals_summary=goals_s,
        calendar_summary=calendar_s,
        documents_summary=docs_s,
        conversation_summary=conv_s,
        confidence_overall=conf,
        useful_next=useful,
        highest_benefit_code=highest,
    )


def to_gemini_context_json(ctx: ReasoningContext) -> Dict[str, Any]:
    """Structured context for Gemini — NOT only the user message."""
    safe = sanitize_known_facts(ctx.known_facts)
    # Keep payload minimal
    known_compact = {k: v for k, v in list(safe.items())[:40]}
    return {
        "known": known_compact,
        "missing": ctx.missing_keys[:40],
        "confidence": ctx.confidence_overall,
        "domains": ctx.domains_touched or list({k.split(".")[0] for k in known_compact}),
        "goals": ctx.goals_summary,
        "calendar_summary": ctx.calendar_summary,
        "documents_summary": ctx.documents_summary,
        "conversation_summary": ctx.conversation_summary,
        "asked_questions": ctx.asked_questions[-20:],
        "asked_keys": ctx.asked_keys[-30:],
        "refused_keys": ctx.refused_keys[-20:],
        "postponed_keys": ctx.postponed_keys[-20:],
        "linked_doc_types": ctx.linked_doc_types,
        "benefits_available": ctx.benefits_available,
        "benefits_active": ctx.benefits_active,
        "useful_next": ctx.useful_next[:8],
        "highest_benefit_code": ctx.highest_benefit_code,
        "phase": ctx.session_phase,
        "last_user_text": (ctx.last_user_text or "")[:500],
    }
