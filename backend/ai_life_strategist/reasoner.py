"""Gemini structured reasoner via Provider Manager — never free-form dumps."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from ai_life_strategist.models import RecommendedDocument, ReasoningContext, StrategistPlan
from ai_life_strategist.policy import filter_unsafe_plan_fields, sanitize_known_facts
from ai_life_strategist.question_planner import avoid_duplicate, plan_greeting, plan_next

logger = logging.getLogger("ora.ai_life_strategist.reasoner")

SYSTEM_PROMPT = """Sei l'AI Life Strategist di ORA (Life Operating System).
NON sei un chatbot generico. NON produci saggi. NON fai questionari.
Dirigi una conversazione naturale di first-launch: scegli COSA chiedere, QUANDO e PERCHÉ.
Preferisci upload documenti quando più informativi delle risposte a voce.
Mai chiedere password, PIN, OTP, IBAN, CVV o credenziali bancarie.
Mai proporre eliminazione dati o azioni irreversibili senza consenso esplicito.
Rispondi SOLO con JSON valido secondo lo schema richiesto. Nessun testo fuori dal JSON.
"""


def strategist_gemini_enabled() -> bool:
    raw = (os.environ.get("AI_LIFE_STRATEGIST_GEMINI") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _schema_hint() -> Dict[str, Any]:
    return {
        "next_best_question": "string",
        "question_reason": "string",
        "expected_benefit": "string (beneficio concreto per l'utente)",
        "information_gain": 0.0,
        "recommended_document": {
            "doc_type": "string|null",
            "label": "string",
            "reason": "string",
            "expected_fields": [],
            "upload_hint": "string|null",
        },
        "alternative_question": "string|null",
        "confidence": 0.0,
        "domain": "casa|auto|finanze|studio|lavoro|salute|famiglia|animali|viaggi|documenti|assicurazioni|abbonamenti|internet|servizi",
        "priority": 50,
        "prefer_document": False,
        "gap_keys": [],
    }


async def reason_with_gemini(ctx: ReasoningContext) -> Optional[StrategistPlan]:
    if not strategist_gemini_enabled():
        return None
    try:
        from llm.manager import ProviderManager
    except Exception as e:
        logger.info("ProviderManager unavailable: %s", e)
        return None

    safe_facts = sanitize_known_facts(ctx.known_facts)
    user_payload = {
        "phase": ctx.session_phase,
        "last_user_text": (ctx.last_user_text or "")[:500],
        "known_facts": safe_facts,
        "missing_keys": ctx.missing_keys[:40],
        "asked_questions": ctx.asked_questions[-20:],
        "linked_doc_types": ctx.linked_doc_types,
        "domains_touched": ctx.domains_touched,
        "benefits_available": ctx.benefits_available,
        "benefits_active": ctx.benefits_active,
        "output_schema": _schema_hint(),
        "rules": [
            "Prefer document upload for rogito after house purchase.",
            "Every question must state a concrete benefit.",
            "No duplicate questions from asked_questions.",
            "Italian language for user-facing strings.",
        ],
    }
    user = (
        "Contesto Life Setup (proporzionato, senza segreti):\n"
        + json.dumps(user_payload, ensure_ascii=False, default=str)
        + "\n\nProduci il prossimo StrategistPlan JSON."
    )

    try:
        mgr = ProviderManager()
        # Prefer gemini; failover still ok but we only accept structured JSON
        res = await mgr.chat(
            system=SYSTEM_PROMPT,
            user=user,
            json_mode=True,
            user_preference="gemini",
        )
    except Exception as e:
        logger.info("strategist gemini chat failed: %s", e)
        return None

    text = None
    if hasattr(res, "text"):
        text = res.text
    elif isinstance(res, dict):
        text = res.get("text") or res.get("content")
    if not text:
        return None

    try:
        data = json.loads(text) if isinstance(text, str) else text
    except Exception:
        logger.info("strategist gemini returned non-JSON")
        return None
    if not isinstance(data, dict):
        return None

    try:
        rec = data.get("recommended_document")
        rec_doc = None
        if isinstance(rec, dict) and rec.get("doc_type"):
            rec_doc = RecommendedDocument(
                doc_type=str(rec["doc_type"]),
                label=str(rec.get("label") or rec["doc_type"]),
                reason=str(rec.get("reason") or ""),
                expected_fields=list(rec.get("expected_fields") or []),
                upload_hint=rec.get("upload_hint"),
            )
        q = str(data.get("next_best_question") or "").strip()
        reason = str(data.get("question_reason") or "").strip()
        benefit = str(data.get("expected_benefit") or "").strip()
        if not q or not benefit:
            return None
        q, reason, benefit, refused = filter_unsafe_plan_fields(q, reason, benefit)
        domain = str(data.get("domain") or "casa")
        plan = StrategistPlan(
            next_best_question=q,
            question_reason=reason or benefit,
            expected_benefit=benefit,
            information_gain=float(data.get("information_gain") or 0.5),
            recommended_document=rec_doc,
            alternative_question=data.get("alternative_question"),
            confidence=float(data.get("confidence") or 0.72),
            domain=domain,  # type: ignore[arg-type]
            priority=int(data.get("priority") or 50),
            prefer_document=bool(data.get("prefer_document") or rec_doc),
            source="gemini",
            gap_keys=list(data.get("gap_keys") or []),
            meta={"privacy_refused": refused, "phase": ctx.session_phase},
        )
        return avoid_duplicate(plan, ctx.asked_questions)
    except Exception as e:
        logger.info("strategist parse plan failed: %s", e)
        return None


async def reason(ctx: ReasoningContext, *, force_fallback: bool = False) -> StrategistPlan:
    """Produce structured plan: Gemini if available, else deterministic fallback."""
    if ctx.session_phase == "greeting" and not ctx.last_user_text:
        return plan_greeting(domains_touched=ctx.domains_touched)

    if not force_fallback:
        gem = await reason_with_gemini(ctx)
        if gem:
            return gem

    plan = plan_next(ctx)
    return avoid_duplicate(plan, ctx.asked_questions)
