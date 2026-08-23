"""Attention & intervention consumer (V2.9.3) — the "SHOULD I SPEAK?" pass.

    pending ImpactAssessments
        → deterministic bounded batching
        → minimal operational context
        → ONE attention call per batch, via Provider Manager
        → deterministic system gate (may only make it quieter)
        → AttentionDecision persisted (including silent)
        → if a surface is permitted: SuggestionCandidate → the EXISTING
          Proactive Engine scoring/gate/dedupe/learning/notification pipeline
        → assessments marked attention-evaluated

Explicitly invoked. No worker, no cron, no scheduler, no polling, and no push
is ever dispatched: the reused notification policy never returns send_now.

A user with no pending assessments returns before any context load or
reasoning call, so `no change ⇒ no signal ⇒ no assessment ⇒ no attention call`
holds all the way down the chain.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from life_attention.context import (
    AI_NATIVE_SOURCE,
    AI_NATIVE_TYPE,
    build_operational_context,
    notifications_allowed,
    prompt_view,
)
from life_attention.gate import apply_system_gate, creates_user_facing_item
from life_attention.models import (
    MAX_AUTOMATIC_DEFER_REEVALUATIONS,
    AttentionDecision,
    AttentionPassReport,
    DeliveryMode,
    decision_key_for,
    root_attention_key_for,
    sanitize_refs,
)
from life_attention.prompt import ATTENTION_SYSTEM_PROMPT, build_attention_payload
from life_attention.repository import AttentionDecisionRepository, DuplicateDecision
from life_reasoning.repository import ImpactAssessmentRepository

logger = logging.getLogger("ora.life_attention")

MAX_ASSESSMENTS_PER_PASS = 5
MAX_BATCHES_PER_PASS = 3
MAX_ASSESSMENTS_PER_BATCH = 5
MAX_DEFER_HOURS = 168  # a week; beyond that, re-reasoning is cheaper than waiting

_VALID_DELIVERIES = {"silent", "defer", "home", "ask_user", "propose_action", "notify"}


class AttentionService:
    def __init__(self, db):
        self.db = db
        self.repo = AttentionDecisionRepository(db)
        self.assessments = ImpactAssessmentRepository(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    async def run_pass(
        self, user_id: str, *, limit: int = MAX_ASSESSMENTS_PER_PASS
    ) -> AttentionPassReport:
        """One bounded attention pass for a single user.

        Never raises for an expected failure: a missing provider or a storage
        error leaves the assessments pending for a later pass rather than
        being turned into a fabricated decision or a lost conclusion.
        """
        t0 = time.perf_counter()
        report = AttentionPassReport()
        if not user_id or self.db is None:
            return report

        pending = await self.assessments.list_awaiting_attention(
            user_id,
            limit=max(1, min(int(limit or MAX_ASSESSMENTS_PER_PASS), MAX_ASSESSMENTS_PER_PASS)),
        )
        report.assessments_seen = len(pending)
        if not pending:
            report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return report

        batches = self._build_batches(pending)
        report.batches = len(batches)

        context = await build_operational_context(self.db, user_id)
        context["notifications_allowed"] = await notifications_allowed(self.db, user_id)

        for batch in batches:
            try:
                await self._evaluate_batch(user_id, batch, context, report)
            except Exception as exc:
                logger.warning(
                    "attention batch failed error=%s", type(exc).__name__
                )
                report.failures.append(type(exc).__name__)

        report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "attention pass seen=%s batches=%s ai=%s silent=%s home=%s ask=%s "
            "propose=%s notify_req=%s downgrades=%s gate_rejects=%s created=%s ms=%s",
            report.assessments_seen, report.batches, report.ai_calls, report.silent,
            report.home, report.ask_user, report.propose_action,
            report.notify_requested, report.system_downgrades, report.gate_rejects,
            report.suggestions_created, report.elapsed_ms,
        )
        return report

    # --- batching -------------------------------------------------------

    def _build_batches(self, assessments: List[Any]) -> List[List[Any]]:
        """Group assessments whose focal refs overlap, so correlated
        conclusions become ONE decision and one user-facing item rather than
        several competing for the same attention. Deterministic."""
        ref_sets = [set(a.focal_refs or []) for a in assessments]
        parent = list(range(len(assessments)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(assessments)):
            for j in range(i + 1, len(assessments)):
                if ref_sets[i] & ref_sets[j]:
                    ra, rb = find(i), find(j)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)

        grouped: Dict[int, List[Any]] = {}
        for index, assessment in enumerate(assessments):
            grouped.setdefault(find(index), []).append(assessment)
        batches = [grouped[key] for key in sorted(grouped)]
        return [b[:MAX_ASSESSMENTS_PER_BATCH] for b in batches[:MAX_BATCHES_PER_PASS]]

    # --- one batch ------------------------------------------------------

    async def _evaluate_batch(
        self,
        user_id: str,
        batch: List[Any],
        context: Dict[str, Any],
        report: AttentionPassReport,
    ) -> None:
        assessment_ids = [a.id for a in batch if a.id]
        decision_key = decision_key_for(user_id, assessment_ids)

        existing = await self.repo.get_by_decision_key(user_id, decision_key)
        if existing:
            # Already evaluated — consume without deciding or speaking again.
            await self.assessments.mark_attention_evaluated(user_id, assessment_ids)
            report.assessments_evaluated += len(assessment_ids)
            return

        focal = sanitize_refs([r for a in batch for r in (a.focal_refs or [])])
        times_raised = await self.repo.count_spoken_for_refs(user_id, focal)

        payload = build_attention_payload(
            assessments=[_assessment_view(a) for a in batch],
            operational_context=prompt_view(context, times_already_raised=times_raised),
        )

        raw, provider, model = await self._decide(payload)
        report.ai_calls += 1
        if raw is None:
            # No fabricated decision, and the conclusions stay pending.
            report.failures.append("provider_unavailable")
            return

        decision = self._build_decision(
            user_id=user_id,
            raw=raw,
            batch=batch,
            assessment_ids=assessment_ids,
            focal=focal,
            context=context,
            times_raised=times_raised,
            decision_key=decision_key,
            root_attention_key=root_attention_key_for(user_id, assessment_ids),
            revision=1,
            provider=provider,
            model=model,
            report=report,
        )

        try:
            await self.repo.insert(decision)
        except DuplicateDecision:
            await self.assessments.mark_attention_evaluated(user_id, assessment_ids)
            report.assessments_evaluated += len(assessment_ids)
            return
        except Exception as exc:
            # PERSIST BEFORE CONSUME: an unpersisted decision must never let
            # the assessments that produced it be marked evaluated.
            logger.warning("attention decision persistence failed: %s", type(exc).__name__)
            report.failures.append("decision_persistence_failed")
            return

        _count_delivery(report, decision.ai_delivery, decision.delivery)

        if creates_user_facing_item(decision.delivery):
            await self._maybe_create_suggestion(user_id, decision, context, report)

        await self.assessments.mark_attention_evaluated(user_id, assessment_ids)
        report.assessments_evaluated += len(assessment_ids)

    def _build_decision(
        self,
        *,
        user_id: str,
        raw: Dict[str, Any],
        batch: List[Any],
        assessment_ids: List[str],
        focal: List[str],
        context: Dict[str, Any],
        times_raised: int,
        decision_key: str,
        root_attention_key: str,
        revision: int,
        provider: Optional[str],
        model: Optional[str],
        report: AttentionPassReport,
    ) -> AttentionDecision:
        """Turn raw model output into a typed decision and apply the
        deterministic system gate. Shared by the first evaluation and every
        automatic reconsideration, so both paths apply IDENTICAL AI-vs-system
        rules."""
        ai_delivery = _delivery(raw.get("delivery"))
        confidence = _clamp(raw.get("confidence"), 0.0)
        utility = _clamp(raw.get("utility"), 0.0)

        delivery, downgrades = apply_system_gate(
            ai_delivery=ai_delivery,
            confidence=confidence,
            utility=utility,
            context=context,
            times_already_raised=times_raised,
        )
        if downgrades:
            report.system_downgrades += 1

        return AttentionDecision(
            user_id=user_id,
            assessment_refs=assessment_ids[:8],
            focal_refs=focal,
            ai_delivery=ai_delivery,
            delivery=delivery,
            utility=utility,
            urgency=_clamp(raw.get("urgency"), 0.0),
            confidence=confidence,
            novelty=_clamp(raw.get("novelty"), 0.0),
            actionability=_clamp(raw.get("actionability"), 0.0),
            interruption_cost=float(context.get("interruption_cost") or 0.0),
            downgrade_reasons=downgrades,
            reason_summary=(str(raw.get("reason_summary") or "").strip() or None),
            proposed_title=(str(raw.get("proposed_title") or "").strip()[:120] or None),
            evidence_refs=sanitize_refs(
                [r for a in batch for r in (a.evidence_refs or [])]
            ),
            defer_until=_defer_until(delivery, raw.get("defer_hours")),
            decision_key=decision_key,
            root_attention_key=root_attention_key,
            attention_revision=revision,
            model_provider=(str(provider)[:40] if provider else None),
            model_name=(str(model)[:80] if model else None),
        )

    # --- deferred reconsideration (V2.9.4 hardening) --------------------

    async def reevaluate_due_deferrals(self, user_id: str) -> AttentionPassReport:
        """Reconsider ATTENTION ONLY for deferrals whose moment has arrived.

        `existing ImpactAssessment(s) → deferred AttentionDecision revision N
        → defer_until reached → refreshed operational context → new AI
        judgement → system gate → revision N+1`.

        Impact Reasoning is never re-run here: the assessments a deferred
        decision was about already exist and are not re-derived. A NEW
        LifeChangeSignal follows the ordinary pipeline into a NEW assessment
        and a NEW (unrelated) attention chain — this method only advances
        chains that already exist.

        AI DECIDES whether a deferral is still appropriate. This method
        enforces only COST bounds (the automatic budget) and the identical
        V2.9.3 system gate — never a semantic verdict like "deferred three
        times, therefore silent".
        """
        t0 = time.perf_counter()
        report = AttentionPassReport()
        if not user_id or self.db is None:
            return report

        due = await self.repo.list_due_deferred(user_id, now_iso=_now_iso())
        report.defer_reevaluations_requested = len(due)
        if not due:
            report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return report

        context = await build_operational_context(self.db, user_id)
        context["notifications_allowed"] = await notifications_allowed(self.db, user_id)

        for previous in due:
            try:
                await self._reevaluate_one(user_id, previous, context, report)
            except Exception as exc:
                logger.warning(
                    "defer re-evaluation failed error=%s", type(exc).__name__
                )
                report.failures.append(type(exc).__name__)
                report.defer_reevaluations_failed += 1

        report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return report

    async def _reevaluate_one(
        self,
        user_id: str,
        previous: AttentionDecision,
        context: Dict[str, Any],
        report: AttentionPassReport,
    ) -> None:
        # Eligibility (re-checked here, not just in the repository query):
        # only the CURRENT decision of a chain, still delivery=defer, with
        # budget remaining, may be reconsidered.
        if previous.delivery != "defer" or not previous.defer_until:
            return
        if previous.superseded_by or previous.auto_re_evaluation_exhausted:
            return
        if previous.automatic_re_evaluations_used >= MAX_AUTOMATIC_DEFER_REEVALUATIONS:
            await self.repo.mark_budget_exhausted(user_id, previous.id)
            report.defer_budget_exhausted += 1
            return

        next_revision = previous.attention_revision + 1
        next_key = decision_key_for(
            user_id, previous.assessment_refs, revision=next_revision
        )

        # Idempotent replay: this exact reconsideration already happened.
        existing = await self.repo.get_by_decision_key(user_id, next_key)
        if existing:
            report.defer_reevaluations_completed += 1
            return

        # Fetch the same assessments this chain was about — never re-derive
        # them, never re-run Impact Reasoning.
        batch = await self._assessments_by_ids(user_id, previous.assessment_refs)
        if not batch:
            # The assessments this chain referred to are gone; nothing left
            # to reconsider. Leave the old decision exactly as it was.
            return

        times_raised = await self.repo.count_spoken_for_refs(
            user_id, previous.focal_refs
        )
        payload = build_attention_payload(
            assessments=[_assessment_view(a) for a in batch],
            operational_context=prompt_view(context, times_already_raised=times_raised),
        )

        raw, provider, model = await self._decide(payload)
        report.ai_calls += 1
        if raw is None:
            # Provider failure: old defer stays current, budget not spent.
            report.defer_reevaluations_failed += 1
            return

        new_decision = self._build_decision(
            user_id=user_id,
            raw=raw,
            batch=batch,
            assessment_ids=previous.assessment_refs,
            focal=previous.focal_refs,
            context=context,
            times_raised=times_raised,
            decision_key=next_key,
            root_attention_key=previous.root_attention_key or root_attention_key_for(
                user_id, previous.assessment_refs
            ),
            revision=next_revision,
            provider=provider,
            model=model,
            report=report,
        )
        new_decision.supersedes_decision_id = previous.id
        new_decision.automatic_re_evaluations_used = (
            previous.automatic_re_evaluations_used + 1
        )
        if new_decision.automatic_re_evaluations_used >= MAX_AUTOMATIC_DEFER_REEVALUATIONS:
            # This IS the budget-exhausting revision. If the AI chose defer
            # again, mark the new (current) decision exhausted directly —
            # there will be no revision N+2 to supersede it, and the cost
            # ceiling must live on whichever decision is actually current.
            new_decision.auto_re_evaluation_exhausted = (
                new_decision.delivery == "defer"
            )

        try:
            await self.repo.insert(new_decision)
        except DuplicateDecision:
            report.defer_reevaluations_completed += 1
            return
        except Exception as exc:
            # PERSIST BEFORE SUPERSEDE: if the new decision was not durably
            # written, the old deferral must remain fully current.
            logger.warning(
                "defer re-evaluation persistence failed: %s", type(exc).__name__
            )
            report.defer_reevaluations_failed += 1
            return

        # ONLY NOW mark the previous decision superseded — after its
        # replacement is durable. If this step fails, the chain is still
        # reconstructible: `latest_for_root` finds the highest revision
        # regardless of whether the old row's `superseded_by` was set.
        await self.repo.mark_superseded(user_id, previous.id, superseded_by=new_decision.id)

        report.defer_reevaluations_completed += 1
        _count_defer_transition(report, new_decision.delivery)

        if creates_user_facing_item(new_decision.delivery):
            await self._maybe_create_suggestion(user_id, new_decision, context, report)

    async def _assessments_by_ids(self, user_id: str, assessment_ids: List[str]) -> List[Any]:
        """Re-fetch the exact assessments a deferred chain was about — by id,
        never a fresh query for "recent" ones, so a reconsideration is always
        about the same question it was deferred from."""
        if not assessment_ids:
            return []
        try:
            docs = await self.db.life_impact_assessments.find(
                {"user_id": user_id, "id": {"$in": list(assessment_ids)[:8]}},
                {"_id": 0},
            ).to_list(8)
        except Exception as exc:
            logger.info("assessment re-fetch soft-fail: %s", type(exc).__name__)
            return []
        from life_reasoning.models import ImpactAssessment

        return [ImpactAssessment.model_validate(d) for d in docs]

    # --- proactive engine handoff ---------------------------------------

    async def _maybe_create_suggestion(
        self,
        user_id: str,
        decision: AttentionDecision,
        context: Dict[str, Any],
        report: AttentionPassReport,
    ) -> None:
        """Hand the permitted decision to the EXISTING Proactive Engine.

        Nothing here bypasses scoring, the gate, dedupe, learning or the
        notification policy — the candidate goes through the same
        `submit_candidates` path the legacy generators use, so the assistant
        test that suppresses low-value generic noise applies equally to
        AI-native items.
        """
        from proactive_engine.dedupe import make_dedupe_key, window_label
        from proactive_engine.models import SuggestionCandidate
        from proactive_engine.service import ProactiveEngineService

        if await self._collides_with_active(user_id, decision.focal_refs):
            report.dedupe_hits += 1
            await self.repo.set_suggestion(
                user_id, decision.id, suggestion_id=None, created=False,
                gate_reasons=["duplicate_active_item_for_same_refs"],
            )
            return

        title = decision.proposed_title or "Qualcosa da rivedere"
        reason = decision.reason_summary or "Un cambiamento recente potrebbe avere conseguenze."
        primary_ref = decision.focal_refs[0] if decision.focal_refs else decision.id

        candidate = SuggestionCandidate(
            title=title[:120],
            description=None,
            reason=reason[:400],
            type=AI_NATIVE_TYPE,
            source=AI_NATIVE_SOURCE,
            dedupe_key=make_dedupe_key(
                suggestion_type=AI_NATIVE_TYPE,
                source=AI_NATIVE_SOURCE,
                entity_id=primary_ref,
                action_kind=decision.delivery,
                window=window_label(),
            ),
            importance_hint=decision.utility,
            urgency_hint=decision.urgency,
            confidence=decision.confidence,
            # General-purpose quality signal: how actionable and how new this
            # is. Without it an AI-native item carrying neither a deadline nor
            # a goal link cannot reach the assistant-test floor at all.
            quality_hint=round((decision.actionability + decision.novelty) / 2.0, 3),
            # Refs only — never the reasoning text or any evidence content.
            evidence={
                "assessment_refs": list(decision.assessment_refs),
                "focal_refs": list(decision.focal_refs),
            },
            meta={
                "delivery": decision.delivery,
                "attention_decision_id": decision.id,
                "focal_refs": list(decision.focal_refs),
            },
        )

        engine = ProactiveEngineService(self.db)
        created, rejected = await engine.submit_candidates(
            user_id,
            [candidate],
            now=context.get("now_utc"),
            # Correctly resolved in the user's own timezone, instead of the
            # gate's fixed Europe/Rome approximation.
            quiet_hours_override=bool(context.get("quiet_hours")),
            likely_sleep_override=bool(context.get("likely_sleep")),
            # The legacy "is the user driving?" title-keyword guess must not
            # govern the AI-native path. Real occupancy still applies.
            infer_activity_from_titles=False,
        )

        if created:
            report.suggestions_created += len(created)
            await self.repo.set_suggestion(
                user_id, decision.id, suggestion_id=created[0].id, created=True,
                gate_reasons=[],
            )
        else:
            report.gate_rejects += 1
            reasons = (rejected[0].get("reasons") if rejected else []) or ["gate_rejected"]
            await self.repo.set_suggestion(
                user_id, decision.id, suggestion_id=None, created=False,
                gate_reasons=list(reasons)[:6],
            )

    async def _collides_with_active(self, user_id: str, refs: List[str]) -> bool:
        """Semantic, ref-based collision check against anything already
        visible — including legacy items.

        Ref overlap rather than fuzzy title matching: two suggestions about the
        same canonical entity are the same interruption to the person reading
        them, regardless of how differently they are worded.
        """
        if not refs:
            return False
        from proactive_engine.repository import SuggestionRepository

        try:
            active = await SuggestionRepository(self.db).list_for_user(
                user_id, statuses=["active", "snoozed"], limit=40
            )
        except Exception:
            return False

        wanted = set(refs)
        for item in active:
            meta_refs = set((item.meta or {}).get("focal_refs") or [])
            if meta_refs & wanted:
                return True
            # Legacy items carry entity ids in dedicated columns rather than
            # canonical refs; compare on the id portion.
            legacy_ids = {
                item.goal_id, item.project_id, item.document_id,
                item.study_plan_id, item.travel_project_id, item.calendar_event,
            }
            for ref in wanted:
                bare = ref.split(":", 1)[1] if ":" in ref else ref
                if bare and bare in legacy_ids:
                    return True
        return False

    # --- provider -------------------------------------------------------

    async def _decide(
        self, payload: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """Exactly one attention call, exclusively through Provider Manager so
        V2.8.3a failover and the circuit breaker stay in force."""
        try:
            from llm.manager import get_manager

            result = await get_manager().chat(
                system=ATTENTION_SYSTEM_PROMPT, user=payload, json_mode=True
            )
        except Exception as exc:
            logger.info("attention provider soft-fail: %s", type(exc).__name__)
            return None, None, None

        parsed = _parse_json(getattr(result, "text", "") or "")
        if parsed is None:
            logger.info("attention returned unparseable output")
            return None, None, None
        return parsed, getattr(result, "provider", None), getattr(result, "model", None)


def _assessment_view(assessment: Any) -> Dict[str, Any]:
    """Bounded projection of a V2.9.2 conclusion. Carries the reasoning that
    already happened — never re-derived, never re-retrieved."""
    return {
        "assessment_id": assessment.id,
        "focal_refs": list(assessment.focal_refs or []),
        "relevance": assessment.relevance,
        "confidence": assessment.confidence,
        "requires_more_context": assessment.requires_more_context,
        "next_step_kind": assessment.next_step_kind,
        "status": assessment.status,
        "impacts": [
            {
                "statement": i.statement,
                "kind": i.kind,
                "epistemic_status": i.epistemic_status,
                "confidence": i.confidence,
                "temporal_horizon": i.temporal_horizon,
                "capability_hint": i.capability_hint,
            }
            for i in (assessment.impacts or [])[:8]
        ],
    }


def _count_delivery(
    report: AttentionPassReport, ai_delivery: str, delivery: DeliveryMode
) -> None:
    if ai_delivery == "notify":
        report.notify_requested += 1
    if delivery == "silent":
        report.silent += 1
    elif delivery == "defer":
        report.deferred += 1
    elif delivery == "home":
        report.home += 1
    elif delivery == "ask_user":
        report.ask_user += 1
    elif delivery == "propose_action":
        report.propose_action += 1


def _count_defer_transition(report: AttentionPassReport, delivery: DeliveryMode) -> None:
    """What a reconsideration turned INTO — distinct from `_count_delivery`,
    which counts a chain's outcome, not the fact that it moved."""
    field = {
        "silent": "defer_to_silent", "defer": "defer_to_defer",
        "home": "defer_to_home", "ask_user": "defer_to_ask",
        "propose_action": "defer_to_propose", "notify": "defer_to_notify",
    }.get(delivery)
    if field:
        setattr(report, field, getattr(report, field) + 1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _delivery(value: Any) -> DeliveryMode:
    text = str(value or "silent").strip()
    return text if text in _VALID_DELIVERIES else "silent"  # type: ignore[return-value]


def _defer_until(delivery: DeliveryMode, hours: Any) -> Optional[str]:
    if delivery != "defer":
        return None
    try:
        h = float(hours)
    except (TypeError, ValueError):
        h = 24.0
    h = max(1.0, min(float(MAX_DEFER_HOURS), h))
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()


def _clamp(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    body = (text or "").strip()
    if not body:
        return None
    if body.startswith("```"):
        body = body.strip("`")
        if body.startswith("json"):
            body = body[4:].strip()
    try:
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except Exception:
        start, end = body.find("{"), body.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(body[start : end + 1])
                return data if isinstance(data, dict) else None
            except Exception:
                return None
    return None
