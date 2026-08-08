"""Gemini structured reasoner via Provider Manager — never free-form dumps."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from ai_life_strategist.models import RecommendedDocument, ReasoningContext, StrategistPlan
from ai_life_strategist.policy import filter_unsafe_plan_fields, sanitize_known_facts
from ai_life_strategist.question_planner import (
    avoid_duplicate,
    enforce_mlc_on_plan,
    plan_greeting,
    plan_next,
)
from ai_life_strategist.reasoning_loop import to_gemini_context_json

logger = logging.getLogger("ora.ai_life_strategist.reasoner")

SYSTEM_PROMPT = """Sei l'AI Life Strategist di ORA (Life Operating System).
NON sei un chatbot generico. NON produci saggi. NON fai questionari.
Dirigi una conversazione naturale: scegli COSA chiedere, QUANDO e PERCHÉ.
Obiettivo del primo avvio: Minimum Life Context (identità, situazione attuale, luoghi,
impegni, priorità immediata) — NON un profilo completo (niente mutuo/banca/auto obbligatori).
Una sola domanda per turno. Non richiedere informazioni già presenti in known.
I documenti sono utili ma NON obbligatori per chiudere il contesto minimo.
Mai chiedere password, PIN, OTP, IBAN, CVV o credenziali bancarie.
Mai proporre eliminazioni o azioni irreversibili senza consenso esplicito.
Tutte le stringhe rivolte all'utente devono essere in italiano semplice.
Rispondi SOLO con JSON valido secondo lo schema. Nessun testo fuori dal JSON.
Nessuna catena di pensiero interna nell'output.
"""

GEMINI_TASK_QUESTION = (
    "Qual è la prossima domanda che produce il maggior beneficio concreto "
    "per colmare il Minimum Life Context (senza ripetere ciò che è già noto)?"
)


def strategist_gemini_enabled() -> bool:
    raw = (os.environ.get("AI_LIFE_STRATEGIST_GEMINI") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _schema_hint() -> Dict[str, Any]:
    return {
        "next_best_question": "string (UNA sola domanda in italiano)",
        "question_reason": "string (perché questa domanda, italiano semplice)",
        "expected_benefit": "string (beneficio concreto per l'utente, italiano)",
        "user_explanation": "string (spiegazione breve per l'utente, senza gergo interno)",
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

    context_json = to_gemini_context_json(ctx)
    user_payload = {
        "context": context_json,
        "output_schema": _schema_hint(),
        "regole": [
            "Una sola domanda in next_best_question — mai due domande insieme.",
            "Preferisci il documento se sostituisce molte domande (rogito, libretto, piano di studi).",
            "Ogni domanda deve avere un beneficio concreto in expected_benefit.",
            "Non ripetere asked_questions, asked_keys, refused_keys, postponed_keys.",
            "Tutte le stringhe utente in italiano.",
            "Non chiedere password, PIN, OTP o dati bancari.",
            "Non dire «continua liberamente» né «completa il profilo».",
        ],
    }
    user = (
        "Contesto strutturato Life Experience (proporzionato, senza segreti):\n"
        + json.dumps(user_payload, ensure_ascii=False, default=str)
        + f"\n\n{GEMINI_TASK_QUESTION}\n"
        + "Produci SOLO lo StrategistPlan JSON."
    )

    try:
        mgr = ProviderManager()
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
        user_expl = str(data.get("user_explanation") or "").strip() or None
        if not q or not benefit:
            return None
        # Reject multi-question dumps (heuristic)
        if q.count("?") > 1 or q.count("？") > 1:
            logger.info("gemini returned multiple questions — discard")
            return None
        q, reason, benefit, refused = filter_unsafe_plan_fields(q, reason, benefit)
        if user_expl:
            _, _, user_expl, _ = filter_unsafe_plan_fields(user_expl, user_expl, user_expl)
        domain = str(data.get("domain") or "casa")
        plan = StrategistPlan(
            next_best_question=q,
            question_reason=reason or benefit,
            expected_benefit=benefit,
            user_explanation=user_expl or benefit,
            information_gain=float(data.get("information_gain") or 0.5),
            recommended_document=rec_doc,
            alternative_question=data.get("alternative_question"),
            confidence=float(data.get("confidence") or 0.72),
            domain=domain,  # type: ignore[arg-type]
            priority=int(data.get("priority") or 50),
            prefer_document=bool(data.get("prefer_document") or rec_doc),
            source="gemini",
            asked_keys=list(ctx.asked_keys),
            refused_keys=list(ctx.refused_keys),
            postponed_keys=list(ctx.postponed_keys),
            gap_keys=list(data.get("gap_keys") or []),
            meta={
                "privacy_refused": refused,
                "phase": ctx.session_phase,
                "highest_benefit_code": ctx.highest_benefit_code,
                "reasoning_loop": True,
            },
        )
        return avoid_duplicate(plan, ctx.asked_questions)
    except Exception as e:
        logger.info("strategist parse plan failed: %s", e)
        return None


async def reason(ctx: ReasoningContext, *, force_fallback: bool = False) -> StrategistPlan:
    """Produce structured plan: Gemini if available, else deterministic Italian fallback."""
    if ctx.session_phase == "greeting" and not ctx.last_user_text:
        return plan_greeting(domains_touched=ctx.domains_touched)

    if not force_fallback:
        gem = await reason_with_gemini(ctx)
        if gem:
            plan = enforce_mlc_on_plan(gem, ctx)
            return avoid_duplicate(plan, ctx.asked_questions)

    plan = enforce_mlc_on_plan(plan_next(ctx), ctx)
    return avoid_duplicate(plan, ctx.asked_questions)
