"""Deterministic benefit-driven question planner (fallback when Gemini absent)."""
from __future__ import annotations

from typing import List, Optional, Set

from ai_life_strategist.benefit_engine import explain_benefit, pick_best_benefit_for_gap
from ai_life_strategist.confidence_manager import plan_confidence
from ai_life_strategist.document_strategy import recommend_document, should_prefer_document
from ai_life_strategist.knowledge_gap import compute_gaps, infer_domain_from_text
from ai_life_strategist.models import DOMAIN_LABELS_IT, ReasoningContext, StrategistPlan
from ai_life_strategist.policy import filter_unsafe_plan_fields


GREETING_QUESTION = (
    "Da dove vuoi partire? Puoi raccontarmi qualcosa della tua vita quotidiana — "
    "casa, studio, auto, lavoro — oppure saltare e tornare più tardi."
)

GREETING_BENEFIT = (
    "In 10–15 minuti ORA impara il contesto che serve per aiutarti davvero: "
    "scadenze, documenti e priorità — senza questionari."
)


def plan_greeting(*, domains_touched: Optional[List[str]] = None) -> StrategistPlan:
    domain = (domains_touched or ["casa"])[0] if domains_touched else "casa"
    if domain not in DOMAIN_LABELS_IT:
        domain = "casa"
    return StrategistPlan(
        next_best_question=GREETING_QUESTION,
        question_reason=(
            "Non è un questionario: è una conversazione. Puoi saltare, "
            "posticipare un tema o uscire in qualsiasi momento."
        ),
        expected_benefit=GREETING_BENEFIT,
        user_explanation=GREETING_BENEFIT,
        information_gain=0.4,
        recommended_document=None,
        alternative_question="Se preferisci, dimmi solo: hai casa, auto o un esame in corso?",
        confidence=0.85,
        domain=domain,  # type: ignore[arg-type]
        priority=10,
        prefer_document=False,
        source="deterministic_fallback",
        meta={"phase": "greeting"},
    )


def plan_next(
    ctx: ReasoningContext,
    *,
    focus_domain: Optional[str] = None,
) -> StrategistPlan:
    known: Set[str] = set()
    for k, v in (ctx.known_facts or {}).items():
        if v is not None and v is not False and v != "" and v != []:
            known.add(k)

    asked: Set[str] = set(ctx.asked_keys or [])
    # Also treat prior question texts as asked for gap keys already recorded
    refused: Set[str] = set(ctx.refused_keys or [])
    postponed: Set[str] = set(ctx.postponed_keys or [])

    inferred = infer_domain_from_text(ctx.last_user_text or "")
    domain = focus_domain or inferred
    if not domain and ctx.domains_touched:
        domain = ctx.domains_touched[-1]

    gaps = compute_gaps(
        known,
        asked_keys=asked,
        refused_keys=refused,
        postponed_keys=postponed,
        focus_domain=domain,
        domains=None,  # all domains — benefit/gain decides order
    )

    if not gaps:
        return StrategistPlan(
            next_best_question=(
                "Per ora ho abbastanza contesto per aiutarti. "
                "Vuoi aggiungere altro, oppure concludere e lasciare che ORA lavori in background?"
            ),
            question_reason="I gap prioritari di questa conversazione sono coperti.",
            expected_benefit=(
                "ORA userà ciò che sa su Home e nei suggerimenti — "
                "senza chiederti di «completare il profilo»."
            ),
            user_explanation=(
                "Ho abbastanza contesto per iniziare ad aiutarti in concreto. "
                "Puoi aggiungere altro quando vuoi."
            ),
            information_gain=0.2,
            confidence=0.8,
            domain=(domain if domain in DOMAIN_LABELS_IT else "casa"),  # type: ignore[arg-type]
            priority=90,
            source="deterministic_fallback",
            asked_keys=list(asked),
            refused_keys=list(refused),
            postponed_keys=list(postponed),
            meta={"phase": "wrap", "gaps_remaining": 0},
        )

    gap = gaps[0]
    benefit = pick_best_benefit_for_gap(gap.key, gap.domain)
    prefer_doc = should_prefer_document(
        prefer_flag=gap.prefer_document,
        gap_key=gap.key,
        already_have_doc_types=ctx.linked_doc_types,
    )
    rec_doc = recommend_document(gap.document_type, domain=gap.domain) if prefer_doc else None

    question = gap.question_template
    if prefer_doc and rec_doc:
        question = (
            f"{rec_doc.label}: {rec_doc.reason} "
            f"Vuoi caricarlo ora, oppure preferisci rispondermi a voce?"
        )

    alt = None
    if prefer_doc:
        alt = gap.question_template
    elif gaps[1:]:
        alt = gaps[1].question_template

    expected = benefit.user_benefit or explain_benefit(gap.benefit_code)
    reason = f"Serve per «{benefit.title}»: {expected}"
    user_expl = expected
    question, reason, expected, refused_flag = filter_unsafe_plan_fields(question, reason, expected)

    coverage = min(1.0, len(known) / 12.0)
    conf = plan_confidence(
        gap_gain=gap.information_gain,
        domain_coverage=coverage,
        used_gemini=False,
        privacy_ok=not refused_flag,
    )

    return StrategistPlan(
        next_best_question=question,
        question_reason=reason,
        expected_benefit=expected,
        user_explanation=user_expl,
        information_gain=gap.information_gain,
        recommended_document=rec_doc,
        alternative_question=alt,
        confidence=conf,
        domain=gap.domain,
        priority=max(1, min(100, int(100 - gap.information_gain * 80))),
        prefer_document=bool(prefer_doc and rec_doc),
        source="deterministic_fallback",
        asked_keys=list(asked),
        refused_keys=list(refused),
        postponed_keys=list(postponed),
        gap_keys=[g.key for g in gaps[:5]],
        meta={
            "phase": "document" if prefer_doc else "active",
            "gap_key": gap.key,
            "benefit_code": benefit.code,
            "privacy_refused": refused_flag,
            "chain": benefit.chain,
            "reasoning_loop": True,
        },
    )


def avoid_duplicate(plan: StrategistPlan, asked_questions_text: List[str]) -> StrategistPlan:
    """If the same question text was already asked, try alternative — never repeat."""
    norm = {(q or "").strip().lower() for q in asked_questions_text}
    if plan.next_best_question.strip().lower() not in norm:
        return plan
    if plan.alternative_question and plan.alternative_question.strip().lower() not in norm:
        plan = plan.model_copy(deep=True)
        plan.next_best_question = plan.alternative_question
        plan.meta = {**(plan.meta or {}), "deduped": True}
        return plan
    plan = plan.model_copy(deep=True)
    plan.next_best_question = (
        "Vuoi approfondire un altro aspetto della tua vita con ORA, "
        "oppure concludere per ora?"
    )
    plan.meta = {**(plan.meta or {}), "deduped": True, "phase": "wrap"}
    return plan
