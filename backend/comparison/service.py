"""
Making a decision, once there is something to decide between.

The order of operations is the argument of this phase:

    the model frames it     what matters, what is absolute, what to work out,
                            what is missing and from whom
    the code answers        the arithmetic, and whether each stated condition
                            holds for each option
    the model reads back    what each option is good and bad at, what trades
                            off, and what it would say — or that it cannot

Nothing here weighs anything. There is no score, no weight, no ordering
function: an option is better because the model said why, in a sentence, and
the only thing the code contributes to that sentence is the numbers in it.

Evidence is V3.4's and is referenced, never copied. When framing finds the
world has not been asked yet, the research service is called with the same work
refs and the framing is done again once — inside the same decision, in the same
session, without a second plan appearing anywhere.

And a comparison produces a decision, not a task. Nothing in this module writes
a card, an item or a reminder: what was concluded goes back to the reasoning
that asked, which decides through the paths that already exist whether anything
about the person's day changed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from comparison.arithmetic import compute_all
from comparison.constraints import breaches, check_all, unverifiable
from comparison.models import (
    Alternative,
    AlternativeAssessment,
    ComparisonCriterion,
    ComparisonNeed,
    ComparisonRun,
    Computation,
    Constraint,
    TradeOff,
)
from comparison.reasoning import (
    assess_alternatives,
    explain_change,
    frame_decision,
    recommend,
)
from comparison.repository import ComparisonRepository

logger = logging.getLogger("ora.comparison.service")

# Guardrails. Cost and time, never strategy.
MAX_ALTERNATIVES = 8
MAX_RESEARCH_ROUNDS = 1
MAX_PERSONAL_CONTEXT = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _looks_numeric(token: str) -> bool:
    """Whether an operand is a plain number the model wrote in itself."""
    try:
        float(str(token).replace(",", "."))
        return True
    except (TypeError, ValueError):
        return False


class ComparisonService:
    def __init__(self, db):
        self.db = db
        self.repo = ComparisonRepository(db)

    async def run(
        self,
        user_id: str,
        need: ComparisonNeed,
        alternatives: List[Alternative],
        *,
        session_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        plan_item_id: Optional[str] = None,
        situation_ref: Optional[str] = None,
        personal_context: Optional[List[str]] = None,
        research_run_ids: Optional[List[str]] = None,
        allow_research: bool = True,
    ) -> ComparisonRun:
        run = ComparisonRun(
            user_id=user_id,
            need=need,
            alternatives=list(alternatives)[:MAX_ALTERNATIVES],
            session_id=session_id,
            plan_id=plan_id,
            plan_item_id=plan_item_id,
            situation_ref=situation_ref,
            personal_context_used=list(personal_context or [])[:MAX_PERSONAL_CONTEXT],
            research_run_ids=list(research_run_ids or []),
        )

        if not run.alternatives:
            run.status = "insufficient"
            run.outcome_note = "Non ho alternative da confrontare."
            return await self._finish(run)

        # Identity first, before anything is shown to the model: from here on
        # every reference is an id, and no label is ever read again.
        run.assign_attribute_identity()

        evidence = await self._evidence(user_id, run.research_run_ids)
        framing = await frame_decision(
            need,
            alternatives=run.alternatives,
            evidence=evidence,
            personal_context=run.personal_context_used,
        )
        if framing is None:
            run.status = "failed"
            run.outcome_note = "Non sono riuscita a impostare il confronto."
            run.failures.append("no_framing")
            return await self._finish(run)

        # The world has not been asked yet. Ask it, in the same decision.
        missing_outside = [str(x) for x in (framing.get("missing_from_the_world") or []) if x]
        if missing_outside and allow_research:
            gathered = await self._research(run, missing_outside)
            if gathered:
                evidence = await self._evidence(user_id, run.research_run_ids)
                again = await frame_decision(
                    need,
                    alternatives=run.alternatives,
                    evidence=evidence,
                    personal_context=run.personal_context_used,
                )
                framing = again or framing

        self._absorb_framing(run, framing)

        # Only they can supply this, and without it the answer would change.
        missing_personal = [str(x) for x in (framing.get("missing_from_them") or []) if x]
        if missing_personal:
            from comparison.models import Recommendation

            run.recommendation = Recommendation(
                verdict="insufficient",
                confidence="weak",
                message="",
                needed_to_decide=missing_personal[:5],
            )
            run.status = "insufficient"
            run.outcome_note = "Mi manca qualcosa che solo tu puoi dirmi."
            return await self._finish(run)

        # The deterministic half.
        run.computations = compute_all(run.computations, run.alternatives)
        run.checks = check_all(run.constraints, run.alternatives)

        assessed = await assess_alternatives(
            need=need,
            alternatives=run.alternatives,
            criteria=run.criteria,
            computations=run.computations,
            checks=[
                {
                    "alternative": (run.alternative(c.alternative_id) or Alternative(name="?")).name,
                    "constraint": c.constraint_name,
                    "satisfied": c.satisfied,
                    "observed": c.observed,
                    "not_checkable_because": c.reason or None,
                    "from": c.source_ids or (["la persona"] if c.stated_by_user else []),
                }
                for c in run.checks
            ],
        )
        if assessed is None:
            run.status = "failed"
            run.outcome_note = "Ho raccolto i dati ma non sono riuscita a valutarli."
            run.failures.append("no_assessment")
            return await self._finish(run)
        self._absorb_assessment(run, assessed)

        run.recommendation = await recommend(run=run)
        if run.recommendation is None:
            run.status = "failed"
            run.outcome_note = "Non sono riuscita a tirare le somme."
            run.failures.append("no_recommendation")
            return await self._finish(run)

        run.status = (
            "insufficient" if run.recommendation.verdict == "insufficient" else "completed"
        )
        run.outcome_note = (
            "Quello che ho non basta per consigliarti."
            if run.status == "insufficient"
            else ""
        )
        return await self._finish(run)

    # -- pieces ---------------------------------------------------------

    def _absorb_framing(self, run: ComparisonRun, framing: Dict[str, Any]) -> None:
        """Take what the model decided, keeping only what validates."""
        for raw in framing.get("criteria") or []:
            try:
                criterion = ComparisonCriterion.model_validate(raw)
            except Exception:
                continue
            # A criterion may legitimately point at nothing — not everything
            # that matters is a field — but if it points somewhere, it has to
            # be somewhere that exists.
            if criterion.attribute_id and criterion.attribute_id not in {
                a.id for alt in run.alternatives for a in alt.attributes
            }:
                criterion.attribute_id = ""
            run.criteria.append(criterion)
        known_attribute_ids = {
            attribute.id for alternative in run.alternatives for attribute in alternative.attributes
        }
        for raw in framing.get("constraints") or []:
            try:
                constraint = Constraint.model_validate(raw)
            except Exception:
                continue
            if constraint.attribute_id not in known_attribute_ids:
                # Fail closed. A requirement about a field nobody has is not a
                # requirement that can be checked, and pretending to check it
                # would be the most expensive kind of wrong.
                logger.info("constraint dropped: unknown attribute reference")
                run.failures.append("constraint_unresolved_reference")
                continue
            run.constraints.append(constraint)
        for raw in framing.get("computations") or []:
            try:
                computation = Computation.model_validate(raw)
            except Exception:
                continue
            # Operands are attribute ids or literal numbers. Anything else is
            # a reference that will not resolve, and it is better to notice
            # that here than to report a figure that was never worked out.
            unresolved = [
                token for token in computation.operands
                if token not in known_attribute_ids and not _looks_numeric(token)
            ]
            if unresolved:
                logger.info("computation dropped: unresolved operands")
                run.failures.append("computation_unresolved_reference")
                continue
            run.computations.append(computation)
        # Something the model says is not really comparable stops being one of
        # the things being chosen between.
        not_comparable = {str(x) for x in (framing.get("not_comparable") or [])}
        if not_comparable:
            run.alternatives = [a for a in run.alternatives if a.id not in not_comparable] or run.alternatives

    def _absorb_assessment(self, run: ComparisonRun, assessed: Dict[str, Any]) -> None:
        known = {a.id for a in run.alternatives}
        for raw in assessed.get("assessments") or []:
            try:
                item = AlternativeAssessment.model_validate(raw)
            except Exception:
                continue
            if item.alternative_id not in known:
                continue
            # An exclusion has to rest on a condition that was actually found
            # to be breached. The model may read the results; it may not
            # overrule them.
            if item.excluded and not breaches(run.checks, item.alternative_id):
                unchecked = unverifiable(run.checks, item.alternative_id)
                logger.info(
                    "exclusion without a breach for %s (%s unverifiable)",
                    item.alternative_id, len(unchecked),
                )
                item.excluded = False
                if item.excluded_because:
                    item.missing = (item.missing + [item.excluded_because])[:5]
                    item.excluded_because = ""
            run.assessments.append(item)
        for raw in assessed.get("trade_offs") or []:
            try:
                run.trade_offs.append(TradeOff.model_validate(raw))
            except Exception:
                continue

    async def _evidence(self, user_id: str, run_ids: List[str]) -> List[Dict[str, Any]]:
        """What V3.4 found, referenced rather than copied."""
        if not run_ids:
            return []
        try:
            from research.repository import ResearchRepository

            repo = ResearchRepository(self.db)
        except Exception as e:
            logger.info("evidence unavailable: %s", type(e).__name__)
            return []
        out: List[Dict[str, Any]] = []
        for run_id in run_ids[:8]:
            try:
                found = await repo.get(user_id, run_id)
            except Exception:
                continue
            if found is None:
                continue
            out.append(found.to_reasoning_payload())
        return out

    async def _research(self, run: ComparisonRun, questions: List[str]) -> bool:
        """
        Go and find what framing said was missing — inside this decision.

        Same session, same plan: research happens for the comparison that asked
        for it and never becomes a goal of its own.
        """
        try:
            from research.models import ResearchNeed
            from research.service import get_research_service, research_available
        except Exception as e:
            logger.info("research unavailable: %s", type(e).__name__)
            return False
        if not research_available():
            return False

        service = get_research_service(self.db)
        gathered = False
        for question in questions[:MAX_RESEARCH_ROUNDS]:
            try:
                found = await service.run(
                    run.user_id,
                    ResearchNeed(
                        question=question,
                        purpose=f"serve per decidere: {run.need.decision}"[:300],
                        already_known=list(run.personal_context_used)[:12],
                    ),
                    session_id=run.session_id,
                    plan_id=run.plan_id,
                    plan_item_id=run.plan_item_id,
                    situation_ref=run.situation_ref,
                    locale_hint="it-IT",
                )
            except Exception as e:
                run.failures.append(f"research_error:{type(e).__name__}")
                continue
            if found.id not in run.research_run_ids:
                run.research_run_ids.append(found.id)
            if found.sources:
                gathered = True
        return gathered

    async def _finish(self, run: ComparisonRun) -> ComparisonRun:
        """Record it, as a revision when this conversation already decided once."""
        if run.session_id:
            try:
                previous = await self.repo.latest_for_session(run.user_id, run.session_id)
            except Exception:
                previous = None
            if previous is not None and previous.id != run.id and previous.recommendation:
                run.supersedes_run_id = previous.id
                run.revision = previous.revision + 1
                if run.recommendation:
                    changed = await explain_change(previous=previous, current=run)
                    if changed:
                        run.changed_because = changed
        run.completed_at = _now().isoformat()
        await self.repo.save(run)
        return run


_service: Dict[int, ComparisonService] = {}


def get_comparison_service(db) -> ComparisonService:
    key = id(db)
    if key not in _service:
        _service[key] = ComparisonService(db)
    return _service[key]


def public_comparison_payload(run: ComparisonRun) -> Dict[str, Any]:
    """
    What may be shown to a person.

    No internal state: no criteria weights, no confidence value, no provider,
    no run ids. What reaches them is the sentence, the few things that decided
    it, the trade-off, the options, and what is still open.
    """
    recommendation = run.recommendation
    return {
        "message": recommendation.message if recommendation else "",
        "deciding_factors": recommendation.deciding_factors if recommendation else [],
        "conditional": [
            {
                "condition": choice.condition,
                "alternative": (
                    run.alternative(choice.alternative_id) or Alternative(name="")
                ).name,
                "because": choice.because,
            }
            for choice in (recommendation.conditional if recommendation else [])
        ],
        "trade_offs": [{"about": t.about, "detail": t.detail} for t in run.trade_offs],
        "alternatives": [
            {
                "name": a.name,
                "excluded": next(
                    (x.excluded for x in run.assessments if x.alternative_id == a.id), False
                ),
                "why_excluded": next(
                    (x.excluded_because for x in run.assessments if x.alternative_id == a.id), ""
                ),
            }
            for a in run.alternatives
        ],
        "unresolved": recommendation.unresolved if recommendation else [],
        "needed_to_decide": recommendation.needed_to_decide if recommendation else [],
        "changed_because": run.changed_because,
    }
