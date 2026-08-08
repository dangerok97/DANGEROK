"""Gemini structured reasoner via Provider Manager — never free-form dumps."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from ai_life_strategist.models import RecommendedDocument, ReasoningContext, StrategistPlan
from ai_life_strategist.policy import filter_unsafe_plan_fields
from ai_life_strategist.question_planner import (
    avoid_duplicate,
    bind_planner_intent,
    enforce_mlc_on_plan,
    plan_greeting,
    plan_next,
)
from ai_life_strategist.reasoning_loop import to_gemini_context_json

logger = logging.getLogger("ora.ai_life_strategist.reasoner")

SYSTEM_PROMPT = """Sei l'AI Life Strategist di ORA (Life Operating System).
NON sei un chatbot generico. NON produci saggi. NON fai questionari né wizard.
Il PLANNER ha già scelto COSA chiedere (question_goal / planner_gap_key).
Tu possiedi SOLO la formulazione Quiet Premium in italiano — non cambiare l'intento.

Internamente punti a un contesto minimo (identità, situazione, luoghi, impegni, priorità)
ma all'utente NON usare mai termini come MLC, coverage, Life Graph, gap, strategist, planner.

Generazione rivolte all'utente (fact-bounded):
- latest_user_message / last_user_text è EVIDENZA PRIMARIA per acknowledgement e tono del turno
  parlato: rifletti il significato importante dell'ultimo messaggio (desideri, tensioni,
  bilanci), non solo lo slot MLC strutturato (es. current_situation).
- Non inventare professioni, città o nomi assenti dal messaggio o da known facts.
- Non inventare una professione/ruolo dal testo di priorità (es. «mi prende troppo tempo» NON è un lavoro).
- Non legare città e studio/lavoro in una sola relazione («studi a X», «lavori a X»)
  se non è esplicitamente strutturato nei fatti.
- acknowledgement: UNA frase breve, naturale, prospettiva ORA→utente (parafrasi);
  preserva il significato importante di latest_user_message; SENZA giudizi
  (mai «giustamente», «ovviamente», «correttamente» o simili); senza consigli;
  senza professione inventata. Poi spoken_question per il question_goal del planner.
  Se l'utente dice che il lavoro prende troppo tempo E vuole più tempo per la famiglia,
  ENTRAMBI devono apparire nell'acknowledgement.
- Non ignorare latest_user_message a favore dei soli slot strutturati.
- spoken_question: DEVE corrispondere al meaning di question_goal fornito; la wording
  può variare, l'intento semantico NO. Rispetta required_semantics e non usare
  forbidden_interpretations. Per ask_primary_home_city / life_places.home resta
  equivalente a «Dove vivi principalmente in questo periodo? Basta la città.»
  (chiedi dove VIVE / città di casa — mai posto di lavoro, studio, dove passa la giornata, GPS).
- Italiano Quiet Premium: al massimo UNA frase breve di acknowledgement + UNA domanda.
- acknowledgement e conversational_bridge sono mutuamente esclusivi (mai entrambi).
- next_best_question resta l'obiettivo semantico / fallback (allineato a planner_next_best_question).
- Mai MLC / coverage / jargon all'utente.

Una sola domanda principale per turno — mai liste «nome, città, lavoro, obiettivi».
Non richiedere informazioni già presenti in known o già dette semanticamente.
I documenti sono acceleratori opzionali, non obblighi per iniziare.
expected_benefit e user_explanation: beneficio concreto per l'utente, non gergo tecnico.
Mai chiedere password, PIN, OTP, IBAN, CVV o credenziali bancarie.
Mai proporre eliminazioni o azioni irreversibili senza consenso esplicito.
Tutte le stringhe rivolte all'utente in italiano semplice e umano.
Rispondi SOLO con JSON valido secondo lo schema. Nessun testo fuori dal JSON.
Nessuna catena di pensiero interna nell'output.
"""

GEMINI_TASK_QUESTION = (
    "Qual è la prossima domanda (una sola) che produce il maggior beneficio concreto "
    "per il question_goal del planner (intent fisso; wording Quiet Premium)? "
    "Includi acknowledgement e spoken_question per il bubble ORA. "
    "Allinea next_best_question a planner_next_best_question quando presente."
)


def strategist_gemini_enabled() -> bool:
    raw = (os.environ.get("AI_LIFE_STRATEGIST_GEMINI") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _schema_hint() -> Dict[str, Any]:
    return {
        "next_best_question": (
            "string (obiettivo semantico / fallback — allinea a planner_next_best_question)"
        ),
        "spoken_question": (
            "string (domanda naturale Quiet Premium, UNA sola; DEVE matchare question_goal.meaning)"
        ),
        "acknowledgement": (
            "string|null (max una frase breve che riflette il significato importante di "
            "latest_user_message — desideri/tensioni, non solo lo slot MLC; naturale, "
            "senza giudizi tipo giustamente/ovviamente/correttamente; senza consigli; "
            "null solo se usi conversational_bridge o messaggio vuoto)"
        ),
        "conversational_bridge": "string|null (progresso soft; null se c'è acknowledgement)",
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


def _clean_spoken(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _planner_binding(planner: StrategistPlan) -> Dict[str, Any]:
    meta = planner.meta or {}
    return {
        "question_goal": meta.get("question_goal"),
        "planner_gap_key": meta.get("gap_key"),
        "planner_next_best_question": planner.next_best_question,
        "mlc_nucleus": meta.get("mlc_nucleus"),
    }


async def reason_with_gemini(
    ctx: ReasoningContext,
    *,
    planner_plan: Optional[StrategistPlan] = None,
) -> Optional[StrategistPlan]:
    if not strategist_gemini_enabled():
        return None
    try:
        from llm.manager import ProviderManager
    except Exception as e:
        logger.info("ProviderManager unavailable: %s", e)
        return None

    binding = _planner_binding(planner_plan) if planner_plan else {}
    context_json = to_gemini_context_json(
        ctx,
        question_goal=binding.get("question_goal"),
        planner_gap_key=binding.get("planner_gap_key"),
        planner_next_best_question=binding.get("planner_next_best_question"),
        mlc_nucleus=binding.get("mlc_nucleus"),
    )
    user_payload = {
        "context": context_json,
        "output_schema": _schema_hint(),
        "regole": [
            "Il planner possiede l'intento (question_goal). Tu solo la wording.",
            "spoken_question DEVE matchare question_goal.meaning; non cambiare intento.",
            "Per life_places / ask_primary_home_city: equivalente a "
            "«Dove vivi principalmente in questo periodo? Basta la città.» "
            "— mai lavoro/studio/dove passa la giornata/GPS.",
            "Una sola domanda in next_best_question / spoken_question — mai due domande insieme.",
            "acknowledgement: UNA frase breve; usa latest_user_message come evidenza primaria "
            "(desideri/tensioni), con known facts come vincolo — non inventare.",
            "acknowledgement naturale; MAI giudizi: giustamente, ovviamente, correttamente.",
            "Niente consigli e niente professione inventata nell'acknowledgement.",
            "Se latest_user_message menziona lavoro che prende troppo tempo E famiglia/tempo "
            "insieme, l'acknowledgement deve riflettere ENTRAMBI (parafrasi ORA→utente).",
            "Non ridurre l'acknowledgement al solo slot mlc.current_situation ignorando il resto del messaggio.",
            "Mai acknowledgement e conversational_bridge insieme.",
            "Non inventare professione da priorità o frasi libere.",
            "Non dire «lavori come …» se non hai un ruolo strutturato corto in known_facts.",
            "Se l'utente ha già detto molto, chiedi solo ciò che manca davvero.",
            "Documento: proponilo come acceleratore opzionale («se vuoi…»), mai come upload obbligatorio.",
            "expected_benefit: beneficio per l'utente (es. proposte realistiche), mai termini interni.",
            "Non ripetere asked_questions, asked_keys, refused_keys, postponed_keys.",
            "Tutte le stringhe utente in italiano.",
            "Non chiedere password, PIN, OTP o dati bancari.",
            "Non dire «completa il profilo», «setup», «questionario», «step», percentuali.",
        ],
        "latest_user_message": (ctx.last_user_text or "")[:500],
        "acknowledgement_instruction": (
            "Reflect important meaning from latest_user_message (desires, tensions, "
            "balances) in acknowledgement; keep fact-bounded; natural; NO judgment "
            "(giustamente/ovviamente/correttamente); no advice; no invented profession; "
            "one short sentence; then spoken_question matching question_goal."
        ),
        "question_goal": binding.get("question_goal"),
        "planner_gap_key": binding.get("planner_gap_key"),
        "planner_next_best_question": binding.get("planner_next_best_question"),
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
        spoken_q = _clean_spoken(data.get("spoken_question"))
        if not q and spoken_q:
            q = spoken_q
        # Prefer planner semantic template when binding is active
        if planner_plan and (planner_plan.meta or {}).get("gap_key"):
            q = planner_plan.next_best_question or q
        reason = str(data.get("question_reason") or "").strip()
        benefit = str(data.get("expected_benefit") or "").strip()
        user_expl = str(data.get("user_explanation") or "").strip() or None
        if not q or not benefit:
            return None
        # Reject multi-question dumps (heuristic)
        if q.count("?") > 1 or q.count("？") > 1:
            logger.info("gemini returned multiple questions — discard")
            return None
        if spoken_q and (spoken_q.count("?") > 1 or spoken_q.count("？") > 1):
            spoken_q = None
        q, reason, benefit, refused = filter_unsafe_plan_fields(q, reason, benefit)
        if user_expl:
            _, _, user_expl, _ = filter_unsafe_plan_fields(user_expl, user_expl, user_expl)
        if spoken_q:
            spoken_q, _, _, _ = filter_unsafe_plan_fields(spoken_q, spoken_q, spoken_q)

        ack = _clean_spoken(data.get("acknowledgement"))
        bridge = _clean_spoken(data.get("conversational_bridge"))
        # Mutual exclusion: ack wins over bridge
        if ack and bridge:
            bridge = None
        if ack:
            ack, _, _, _ = filter_unsafe_plan_fields(ack, ack, ack)
        if bridge:
            bridge, _, _, _ = filter_unsafe_plan_fields(bridge, bridge, bridge)

        domain = str(data.get("domain") or "casa")
        gap_keys = list(data.get("gap_keys") or [])
        if planner_plan and planner_plan.gap_keys:
            gap_keys = list(planner_plan.gap_keys)
        meta: Dict[str, Any] = {
            "privacy_refused": refused,
            "phase": (planner_plan.meta or {}).get("phase")
            if planner_plan
            else ctx.session_phase,
            "highest_benefit_code": ctx.highest_benefit_code,
            "reasoning_loop": True,
            "conversational_bridge": bridge,
            "spoken_from_gemini": True,
        }
        if planner_plan and (planner_plan.meta or {}).get("gap_key"):
            meta["gap_key"] = (planner_plan.meta or {}).get("gap_key")
            meta["mlc_nucleus"] = (planner_plan.meta or {}).get("mlc_nucleus")
            meta["question_goal"] = (planner_plan.meta or {}).get("question_goal")
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
            gap_keys=gap_keys,
            acknowledgement=ack,
            spoken_question=spoken_q,
            conversational_bridge=bridge,
            meta=meta,
        )
        if planner_plan:
            plan = bind_planner_intent(plan, planner_plan)
        return avoid_duplicate(plan, ctx.asked_questions)
    except Exception as e:
        logger.info("strategist parse plan failed: %s", e)
        return None


async def reason(ctx: ReasoningContext, *, force_fallback: bool = False) -> StrategistPlan:
    """Produce structured plan: Gemini if available, else deterministic Italian fallback.

    Planner intent is computed first (deterministic, no LLM). Gemini may only word
    acknowledgement / spoken_question for that intent (Architecture A — one LLM call).
    """
    if ctx.session_phase == "greeting" and not ctx.last_user_text:
        return plan_greeting(domains_touched=ctx.domains_touched)

    planner_plan = plan_next(ctx)

    if not force_fallback:
        gem = await reason_with_gemini(ctx, planner_plan=planner_plan)
        if gem:
            plan = enforce_mlc_on_plan(gem, ctx)
            return avoid_duplicate(plan, ctx.asked_questions)

    plan = enforce_mlc_on_plan(planner_plan, ctx)
    return avoid_duplicate(plan, ctx.asked_questions)
