"""Deterministic benefit-driven question planner (fallback when Gemini absent).

Sprint 3 — Minimum Life Context: wrap only when MLC is sufficient.
Questions target uncovered nuclei; not a fixed 5-step sequence.
"""
from __future__ import annotations

from typing import List, Optional, Set

from ai_life_strategist.benefit_engine import explain_benefit, pick_best_benefit_for_gap
from ai_life_strategist.confidence_manager import plan_confidence
from ai_life_strategist.document_strategy import recommend_document, should_prefer_document
from ai_life_strategist.knowledge_gap import compute_gaps, infer_domain_from_text
from ai_life_strategist.minimum_life_context import (
    NUCLEUS_QUESTIONS,
    compute_mlc_gaps,
    evaluate_mlc_coverage,
    is_mlc_sufficient,
    wrap_plan_meta,
)
from ai_life_strategist.models import DOMAIN_LABELS_IT, ReasoningContext, StrategistPlan
from ai_life_strategist.policy import filter_unsafe_plan_fields


GREETING_QUESTION = (
    "Raccontami qualcosa di te — come preferisci che ti chiami e cosa sta "
    "riempiendo le tue giornate in questo periodo?"
)

GREETING_BENEFIT = (
    "Mi serve solo il contesto minimo per iniziare ad aiutarti in concreto — "
    "non un profilo completo della tua vita."
)


def plan_greeting(*, domains_touched: Optional[List[str]] = None) -> StrategistPlan:
    domain = (domains_touched or ["servizi"])[0] if domains_touched else "servizi"
    if domain not in DOMAIN_LABELS_IT:
        domain = "servizi"
    return StrategistPlan(
        next_best_question=GREETING_QUESTION,
        question_reason=(
            "Non è un questionario: è una conversazione. Puoi saltare un tema "
            "o uscire — ORA continua a imparare dopo la Home."
        ),
        expected_benefit=GREETING_BENEFIT,
        user_explanation=GREETING_BENEFIT,
        information_gain=0.4,
        recommended_document=None,
        alternative_question="Se preferisci, dimmi solo dove vivi e se lavori o studi.",
        confidence=0.85,
        domain=domain,  # type: ignore[arg-type]
        priority=10,
        prefer_document=False,
        source="deterministic_fallback",
        meta={"phase": "greeting", "mlc_version": "mlc-v1"},
    )


def _known_set(ctx: ReasoningContext) -> Set[str]:
    known: Set[str] = set()
    for k, v in (ctx.known_facts or {}).items():
        if v is not None and v is not False and v != "" and v != []:
            known.add(k)
    return known


def _wrap_plan(ctx: ReasoningContext, domain: Optional[str], coverage) -> StrategistPlan:
    asked: Set[str] = set(ctx.asked_keys or [])
    refused: Set[str] = set(ctx.refused_keys or [])
    postponed: Set[str] = set(ctx.postponed_keys or [])
    return StrategistPlan(
        next_best_question=(
            "Adesso conosco abbastanza della tua situazione per iniziare ad aiutarti. "
            "Vuoi aggiungere altro, oppure entrare in Home e lasciare che ORA lavori con questo contesto?"
        ),
        question_reason="Minimum Life Context raggiunto — non un profilo completo.",
        expected_benefit=(
            "Userò questo contesto minimo su Home e nei suggerimenti, "
            "e continuerò a conoscerti nel tempo."
        ),
        user_explanation=(
            "Ho il contesto minimo per iniziare ad aiutarti in concreto. "
            "Non serve «completare il profilo» — il resto emerge cammin facendo."
        ),
        information_gain=0.2,
        confidence=0.88,
        domain=(domain if domain in DOMAIN_LABELS_IT else "servizi"),  # type: ignore[arg-type]
        priority=90,
        source="deterministic_fallback",
        asked_keys=list(asked),
        refused_keys=list(refused),
        postponed_keys=list(postponed),
        meta=wrap_plan_meta(coverage),
    )


def plan_next(
    ctx: ReasoningContext,
    *,
    focus_domain: Optional[str] = None,
) -> StrategistPlan:
    known_facts = dict(ctx.known_facts or {})
    asked: Set[str] = set(ctx.asked_keys or [])
    refused: Set[str] = set(ctx.refused_keys or [])
    postponed: Set[str] = set(ctx.postponed_keys or [])

    inferred = infer_domain_from_text(ctx.last_user_text or "")
    domain = focus_domain or inferred
    if not domain and ctx.domains_touched:
        domain = ctx.domains_touched[-1]

    coverage = evaluate_mlc_coverage(
        known_facts, refused_keys=refused, postponed_keys=postponed
    )

    from ai_life_strategist.minimum_life_context import NUCLEUS_GAP_KEY

    # mlc-v1: priority strongly preferred — if only implicitly addressed via rich
    # core context, ask once before wrap (asked ≠ addressed; skip/refuse still OK).
    if coverage.sufficient:
        pri = next((n for n in coverage.nuclei if n.nucleus == "immediate_priority"), None)
        pri_key = NUCLEUS_GAP_KEY["immediate_priority"]
        if (
            pri
            and pri.status == "implicit"
            and pri_key not in asked
            and pri_key not in refused
            and pri_key not in postponed
        ):
            nmeta = NUCLEUS_QUESTIONS["immediate_priority"]
            question, reason, expected, refused_flag = filter_unsafe_plan_fields(
                nmeta["question"], nmeta["benefit"], nmeta["benefit"]
            )
            return StrategistPlan(
                next_best_question=question,
                question_reason=reason,
                expected_benefit=expected,
                user_explanation=expected,
                information_gain=float(nmeta["gain"]),
                recommended_document=None,
                alternative_question=None,
                confidence=plan_confidence(
                    gap_gain=0.97,
                    domain_coverage=min(1.0, coverage.covered_count / 5.0),
                    used_gemini=False,
                    privacy_ok=not refused_flag,
                ),
                domain=nmeta["domain"],  # type: ignore[arg-type]
                priority=15,
                prefer_document=False,
                source="deterministic_fallback",
                asked_keys=list(asked),
                refused_keys=list(refused),
                postponed_keys=list(postponed),
                gap_keys=[pri_key],
                meta={
                    "phase": "active",
                    "gap_key": pri_key,
                    "benefit_code": "mlc_immediate_priority",
                    "mlc_nucleus": "immediate_priority",
                    "mlc": coverage.public(),
                    "mlc_version": "mlc-v1",
                    "mlc_priority_preferred_ask": True,
                    "privacy_refused": refused_flag,
                    "reasoning_loop": True,
                },
            )
        return _wrap_plan(ctx, domain, coverage)

    mlc_gaps = compute_mlc_gaps(
        known_facts,
        asked_keys=asked,
        refused_keys=refused,
        postponed_keys=postponed,
    )

    if mlc_gaps:
        gap = mlc_gaps[0]
        nucleus = next((nid for nid, key in NUCLEUS_GAP_KEY.items() if key == gap.key), None)
        nmeta = NUCLEUS_QUESTIONS.get(nucleus or "", {})
        benefit_text = nmeta.get("benefit") or explain_benefit(gap.benefit_code)
        question = gap.question_template
        alt = mlc_gaps[1].question_template if len(mlc_gaps) > 1 else None
        question, reason, expected, refused_flag = filter_unsafe_plan_fields(
            question, benefit_text, benefit_text
        )
        conf = plan_confidence(
            gap_gain=gap.information_gain,
            domain_coverage=min(1.0, coverage.covered_count / 5.0),
            used_gemini=False,
            privacy_ok=not refused_flag,
        )
        return StrategistPlan(
            next_best_question=question,
            question_reason=reason,
            expected_benefit=expected,
            user_explanation=expected,
            information_gain=gap.information_gain,
            recommended_document=None,
            alternative_question=alt,
            confidence=conf,
            domain=gap.domain,
            priority=max(1, min(100, int(100 - gap.information_gain * 80))),
            prefer_document=False,
            source="deterministic_fallback",
            asked_keys=list(asked),
            refused_keys=list(refused),
            postponed_keys=list(postponed),
            gap_keys=[g.key for g in mlc_gaps[:5]],
            meta={
                "phase": "active",
                "gap_key": gap.key,
                "benefit_code": gap.benefit_code,
                "mlc_nucleus": nucleus,
                "mlc": coverage.public(),
                "mlc_version": "mlc-v1",
                "privacy_refused": refused_flag,
                "reasoning_loop": True,
            },
        )

    # MLC gaps empty but not sufficient (edge: all skipped with little evidence)
    # Soft prompt for priority / open share — still not DOMAIN_GAPS wizard.
    if not is_mlc_sufficient(known_facts, refused_keys=refused, postponed_keys=postponed):
        question = (
            "C’è qualcosa di pratico su cui posso iniziare ad aiutarti, "
            "anche piccolo — oppure preferisci raccontarmi un altro pezzo del tuo contesto?"
        )
        question, reason, expected, refused_flag = filter_unsafe_plan_fields(
            question,
            "Serve a chiudere il contesto minimo senza moduli.",
            "Così la Home ha un punto di partenza concreto.",
        )
        return StrategistPlan(
            next_best_question=question,
            question_reason=reason,
            expected_benefit=expected,
            user_explanation=expected,
            information_gain=0.85,
            confidence=0.7,
            domain=(domain if domain in DOMAIN_LABELS_IT else "servizi"),  # type: ignore[arg-type]
            priority=20,
            prefer_document=False,
            source="deterministic_fallback",
            asked_keys=list(asked),
            refused_keys=list(refused),
            postponed_keys=list(postponed),
            gap_keys=["mlc.immediate_priority"],
            meta={
                "phase": "active",
                "gap_key": "mlc.immediate_priority",
                "mlc": coverage.public(),
                "mlc_version": "mlc-v1",
                "privacy_refused": refused_flag,
            },
        )

    return _wrap_plan(ctx, domain, coverage)


def plan_domain_gap_legacy(
    ctx: ReasoningContext,
    *,
    focus_domain: Optional[str] = None,
) -> Optional[StrategistPlan]:
    """Optional progressive domain gap (post-MLC / tests). Not used for wrap gating."""
    known = _known_set(ctx)
    asked: Set[str] = set(ctx.asked_keys or [])
    refused: Set[str] = set(ctx.refused_keys or [])
    postponed: Set[str] = set(ctx.postponed_keys or [])
    inferred = infer_domain_from_text(ctx.last_user_text or "")
    domain = focus_domain or inferred
    gaps = compute_gaps(
        known,
        asked_keys=asked,
        refused_keys=refused,
        postponed_keys=postponed,
        focus_domain=domain,
        domains=None,
    )
    if not gaps:
        return None
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
    expected = benefit.user_benefit or explain_benefit(gap.benefit_code)
    reason = f"Serve per «{benefit.title}»: {expected}"
    question, reason, expected, refused_flag = filter_unsafe_plan_fields(question, reason, expected)
    return StrategistPlan(
        next_best_question=question,
        question_reason=reason,
        expected_benefit=expected,
        user_explanation=expected,
        information_gain=gap.information_gain,
        recommended_document=rec_doc,
        alternative_question=gaps[1].question_template if gaps[1:] else None,
        confidence=0.75,
        domain=gap.domain,
        priority=50,
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
            "legacy_domain_gap": True,
            "privacy_refused": refused_flag,
        },
    )


def avoid_duplicate(plan: StrategistPlan, asked_questions_text: List[str]) -> StrategistPlan:
    """If the same question text was already asked, try alternative — never repeat.

    Does NOT wrap unless MLC already marked wrap (completion_reason / phase).
    """
    norm = {(q or "").strip().lower() for q in asked_questions_text}
    if plan.next_best_question.strip().lower() not in norm:
        return plan
    if plan.alternative_question and plan.alternative_question.strip().lower() not in norm:
        plan = plan.model_copy(deep=True)
        plan.next_best_question = plan.alternative_question
        plan.meta = {**(plan.meta or {}), "deduped": True}
        return plan
    plan = plan.model_copy(deep=True)
    # Never force Home via dedupe alone
    if (plan.meta or {}).get("phase") == "wrap":
        return plan
    plan.next_best_question = (
        "C’è un altro pezzo della tua situazione che vuoi raccontarmi, "
        "anche in una frase sola?"
    )
    plan.meta = {**(plan.meta or {}), "deduped": True, "phase": "active"}
    return plan


def enforce_mlc_on_plan(plan: StrategistPlan, ctx: ReasoningContext) -> StrategistPlan:
    """Gate Gemini/deterministic plans: wrap iff MLC sufficient."""
    coverage = evaluate_mlc_coverage(
        dict(ctx.known_facts or {}),
        refused_keys=set(ctx.refused_keys or []),
        postponed_keys=set(ctx.postponed_keys or []),
    )
    if coverage.sufficient:
        if (plan.meta or {}).get("phase") == "wrap":
            plan = plan.model_copy(deep=True)
            plan.meta = {**(plan.meta or {}), **wrap_plan_meta(coverage)}
            return plan
        return _wrap_plan(ctx, plan.domain, coverage)
    if (plan.meta or {}).get("phase") == "wrap":
        return plan_next(ctx)
    plan = plan.model_copy(deep=True)
    plan.meta = {**(plan.meta or {}), "mlc": coverage.public(), "mlc_version": "mlc-v1"}
    return plan
