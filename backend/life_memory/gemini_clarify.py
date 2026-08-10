"""Gemini clarification cognition — questions + free-text resolution.

Never writes canonical truth. Minimized context pack. Shared Provider Manager.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from life_memory.authority import question_switches_to_ora_perspective
from life_memory.models import (
    ClarificationSession,
    GeminiClarifyQuestion,
    GeminiClarifyResolution,
    ProposedFact,
)

logger = logging.getLogger("ora.life_memory.clarify.gemini")

QUESTION_SYSTEM = """Sei ORA, l'assistente. L'utente è la persona descritta dalle memorie.

Ruoli fissi:
- ORA = assistente (tu che chiedi)
- USER = persona delle memorie (seconda persona: tu / ti / te)

I belief descrivono SEMPRE l'utente, mai ORA.
Se il belief è "Ti chiami Francesco", chiedi conferma all'utente
(es. se ti chiami… / è corretto che ti chiami…), MAI "mi chiamo…".
Non reinterpretare i fatti come se parlassero di te (ORA).
Non dire "ti riferivi a me".

Voce: calma, breve, italiana, non giudicante, non da form/database.
Genera UNA sola domanda di chiarimento naturale in seconda persona verso l'utente.
Non menzionare confidence, schema, ID, Mongo, Profile.
Non inventare fatti. Non offrire menu di opzioni.
Output JSON: { "question": "...", "clarification_goal": "..." }
"""

RESOLVE_SYSTEM = """Sei ORA. Interpreta la risposta libera dell'utente su un dubbio di memoria.

NON inventare fatti. NON mutare ricordi non correlati.
Usa SOLO i profile_targets consentiti per proposed_facts sul target.
additional_facts possono proporre altre chiavi solo se l'utente le ha dette chiaramente;
action=suggest (non known automatico).

resolution:
- confirmed: l'utente conferma il belief corrente
- corrected: l'utente corregge con un nuovo valore
- still_ambiguous: ancora incerto / contraddittorio / insufficiente

Output JSON conforme allo schema. Niente chain-of-thought.
"""


async def generate_clarify_question(session: ClarificationSession) -> Optional[str]:
    try:
        from llm.structured import chat_json
    except Exception as e:
        logger.info("clarify question gemini unavailable: %s", type(e).__name__)
        return None

    pack = {
        "roles": {
            "assistant": "ORA",
            "user": "the person described by current_belief",
            "perspective": "second_person_to_user",
        },
        "current_belief": session.belief_statement,
        "status": session.status_before,
        "candidate_values": session.candidate_values[:6],
        "provenance": session.provenance_label,
        "evidence_refs": session.evidence_refs[:8],
        "goal": session.clarification_goal,
        "constraints": [
            "Ask the USER about themselves",
            "Never use first-person as if ORA had the name/job/city",
            "Never ask 'mi chiamo…' or 'ti riferivi a me'",
        ],
        "task": "Generate one short natural clarification question to the user.",
    }
    try:
        parsed, _ = await chat_json(
            system=QUESTION_SYSTEM,
            user=json.dumps(pack, ensure_ascii=False),
            model_cls=GeminiClarifyQuestion,
            user_preference="gemini",
        )
    except Exception as e:
        logger.info("clarify question soft-fail: %s", type(e).__name__)
        return None
    q = " ".join((parsed.question or "").split()).strip()
    if 8 <= len(q) <= 280 and not question_switches_to_ora_perspective(q):
        return q
    if q and question_switches_to_ora_perspective(q):
        logger.info("clarify question rejected: ora_perspective")
    return None


def deterministic_clarify_question(session: ClarificationSession) -> str:
    belief = assertive_belief(session.belief_statement or "")
    if belief:
        return (
            f"Mi risulta che {belief[0].lower() + belief[1:]}, "
            "ma non ne sono ancora sicura. È corretto?"
        )
    return "Puoi aiutarmi a capire meglio questo dettaglio su di te?"


def assertive_belief(statement: str) -> str:
    from life_memory.present import assertive_core

    return assertive_core(statement).rstrip(".")


async def interpret_clarify_answer(
    session: ClarificationSession,
    *,
    user_text: str,
) -> Optional[GeminiClarifyResolution]:
    try:
        from llm.structured import chat_json
    except Exception as e:
        logger.info("clarify resolve gemini unavailable: %s", type(e).__name__)
        return None

    allowed = [
        {"domain": t.domain, "key": t.key} for t in session.profile_targets
    ]
    pack = {
        "target_memory_id": session.memory_id,
        "current_belief": session.belief_statement,
        "status": session.status_before,
        "candidate_values": session.candidate_values[:6],
        "allowed_profile_targets": allowed,
        "evidence_refs": session.evidence_refs[:8],
        "user_answer": user_text,
        "schema": {
            "resolution": "confirmed|corrected|still_ambiguous",
            "target_memory_id": session.memory_id,
            "proposed_facts": [
                {
                    "domain": "…",
                    "key": "…",
                    "value": "…",
                    "action": "confirm|correct|suggest",
                    "confidence": 0.0,
                }
            ],
            "additional_facts": [],
            "superseded_keys": [],
            "confidence": 0.0,
            "needs_followup": False,
            "followup_question": None,
        },
    }
    try:
        parsed, _ = await chat_json(
            system=RESOLVE_SYSTEM,
            user=json.dumps(pack, ensure_ascii=False),
            model_cls=GeminiClarifyResolution,
            user_preference="gemini",
        )
        return parsed
    except Exception as e:
        logger.info("clarify resolve soft-fail: %s", type(e).__name__)
        return None


def heuristic_resolve(
    session: ClarificationSession,
    *,
    user_text: str,
) -> GeminiClarifyResolution:
    """Deterministic fallback when Gemini is down — never invents new cities/jobs."""
    t = " ".join((user_text or "").split()).strip().lower().rstrip(".!?")
    yes = t in ("sì", "si", "yes", "ok", "corretto", "esatto", "confermo", "vero")
    no = t.startswith("no") or t in ("falso", "sbagliato")
    targets = list(session.profile_targets)
    primary = targets[0] if targets else None
    if yes and primary and session.candidate_values:
        return GeminiClarifyResolution(
            resolution="confirmed",
            target_memory_id=session.memory_id,
            proposed_facts=[
                ProposedFact(
                    domain=primary.domain,
                    key=primary.key,
                    value=session.candidate_values[0],
                    action="confirm",
                    confidence=0.9,
                )
            ],
            confidence=0.85,
        )
    if no:
        return GeminiClarifyResolution(
            resolution="still_ambiguous",
            target_memory_id=session.memory_id,
            confidence=0.4,
            needs_followup=True,
            followup_question="Mi dici qual è il valore corretto?",
        )
    # Free text without Gemini — keep ambiguous (do not guess)
    return GeminiClarifyResolution(
        resolution="still_ambiguous",
        target_memory_id=session.memory_id,
        confidence=0.3,
        needs_followup=False,
        evidence_interpretation="gemini_unavailable_free_text",
    )


def validate_resolution(
    session: ClarificationSession,
    raw: GeminiClarifyResolution,
) -> GeminiClarifyResolution:
    """Governance gate on Gemini output — reject invent/unrelated."""
    allowed = {(t.domain, t.key) for t in session.profile_targets}
    if raw.target_memory_id and raw.target_memory_id != session.memory_id:
        logger.info("clarify reject hallucinated memory_id=%s", raw.target_memory_id)
        raw.target_memory_id = session.memory_id
        raw.resolution = "still_ambiguous"
        raw.proposed_facts = []
        raw.additional_facts = []

    safe_proposed: List[ProposedFact] = []
    for f in raw.proposed_facts or []:
        if (f.domain, f.key) in allowed:
            safe_proposed.append(f)
        else:
            logger.info("clarify drop unauthorized proposed %s.%s", f.domain, f.key)
    raw.proposed_facts = safe_proposed

    # Additional facts: allow only well-formed keys; mark suggest
    safe_add: List[ProposedFact] = []
    for f in raw.additional_facts or []:
        if not f.domain or not f.key or f.value in (None, ""):
            continue
        if f.sensitivity if hasattr(f, "sensitivity") else False:
            continue
        # Block sensitive key fragments
        from life_memory.statements import is_sensitive_key

        if is_sensitive_key(f.key):
            continue
        f.action = "suggest"
        safe_add.append(f)
    raw.additional_facts = safe_add[:5]

    if raw.resolution == "confirmed" and not raw.proposed_facts and session.profile_targets:
        t = session.profile_targets[0]
        val = session.candidate_values[0] if session.candidate_values else None
        if val is not None:
            raw.proposed_facts = [
                ProposedFact(
                    domain=t.domain, key=t.key, value=val, action="confirm", confidence=0.9
                )
            ]
    if raw.resolution == "corrected" and not raw.proposed_facts:
        raw.resolution = "still_ambiguous"
    return raw
