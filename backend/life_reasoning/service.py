"""Impact reasoning consumer (V2.9.2) — the "SO WHAT?" pass.

    pending LifeChangeSignals
        → deterministic bounded batching
        → bounded context (graph expansion + Context Broker Stage B)
        → ONE reasoning call per batch, via Provider Manager
        → ImpactAssessment persisted
        → signals marked processed

Explicitly invoked. There is no worker, no cron, no scheduler and no polling
in V2.9.2 — a user with no pending signals costs exactly nothing, because the
pass returns before any retrieval or reasoning happens.

The pass never speaks to the user: it creates no suggestion, no notification
and no message, and it executes no tool. Whether any of this is worth saying
is V2.9.3's decision.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from life_reasoning.context import (
    ContextUnavailable,
    capability_catalog,
    describe_changes,
    expand_relations,
    focal_refs_for,
    prior_conclusions,
    retrieve_evidence,
    temporal_context,
)
from life_reasoning.models import (
    AssessmentPassReport,
    Impact,
    ImpactAssessment,
    MAX_EVIDENCE_REFS,
    MAX_IMPACTS,
    MAX_REFS,
    batch_key_for,
    sanitize_refs,
)
from life_reasoning.prompt import IMPACT_SYSTEM_PROMPT, build_impact_payload
from life_reasoning.repository import DuplicateAssessment, ImpactAssessmentRepository
from life_signals.service import LifeSignalService

logger = logging.getLogger("ora.life_reasoning")

# Bounded pass budget. Deliberately small: this is a cost ceiling, not a
# throughput target.
MAX_SIGNALS_PER_PASS = 5
MAX_BATCHES_PER_PASS = 3
MAX_SIGNALS_PER_BATCH = 5


class ImpactReasoningService:
    def __init__(self, db):
        self.db = db
        self.signals = LifeSignalService(db)
        self.repo = ImpactAssessmentRepository(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    async def run_pass(
        self, user_id: str, *, limit: int = MAX_SIGNALS_PER_PASS
    ) -> AssessmentPassReport:
        """One bounded impact-reasoning pass for a single user.

        Returns a non-sensitive report. Never raises for an expected failure
        (no provider, unreadable context, storage error): those leave the
        signals pending so a later pass can retry, and are reported instead of
        being turned into a fabricated assessment.
        """
        t0 = time.perf_counter()
        report = AssessmentPassReport()
        if not user_id or self.db is None:
            return report

        pending = await self.signals.list_pending(
            user_id, limit=max(1, min(int(limit or MAX_SIGNALS_PER_PASS), MAX_SIGNALS_PER_PASS))
        )
        report.signals_seen = len(pending)
        if not pending:
            # No change ⇒ no signal ⇒ no context retrieval ⇒ no AI call.
            report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return report

        batches = await self._build_batches(user_id, pending)
        report.batches = len(batches)

        for batch in batches:
            try:
                created = await self._assess_batch(user_id, batch, report)
            except Exception as exc:  # defensive: one bad batch must not kill the pass
                logger.warning(
                    "impact batch failed user_scoped error=%s", type(exc).__name__
                )
                report.failures.append(type(exc).__name__)
                report.deferred += 1
                continue
            if not created:
                report.deferred += 1

        report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "impact pass signals=%s batches=%s ai_calls=%s created=%s deferred=%s ms=%s",
            report.signals_seen,
            report.batches,
            report.ai_calls,
            report.assessments_created,
            report.deferred,
            report.elapsed_ms,
        )
        return report

    # --- batching -------------------------------------------------------

    async def _build_batches(
        self, user_id: str, signals: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Group related signals so correlated changes cost ONE reasoning call
        instead of N.

        Two signals are related when their canonical refs overlap directly, or
        when a Context Graph edge already connects them. Unrelated signals are
        never forced into the same reasoning blob — a shared prompt would let
        one part of the user's life contaminate the conclusions about another.

        Fully deterministic: same input, same batches, same order.
        """
        ref_sets: List[set] = [set(focal_refs_for([s])) for s in signals]
        parent = list(range(len(signals)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

        # 1) direct ref overlap
        for i in range(len(signals)):
            for j in range(i + 1, len(signals)):
                if ref_sets[i] & ref_sets[j]:
                    union(i, j)

        # 2) graph-connected refs — one bounded lookup for the whole pass
        all_refs = sorted({r for s in ref_sets for r in s})
        if len(signals) > 1 and all_refs:
            try:
                from context_graph.service import ContextGraphService

                edges = await ContextGraphService(self.db).relevant_edges(
                    user_id, all_refs[:8], limit=10
                )
                for edge in edges:
                    pair = {edge.subject_ref, edge.object_ref}
                    members = [k for k, refs in enumerate(ref_sets) if refs & pair]
                    for k in members[1:]:
                        union(members[0], k)
            except Exception as exc:
                logger.info("batch graph merge soft-fail: %s", type(exc).__name__)

        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for index, signal in enumerate(signals):
            grouped.setdefault(find(index), []).append(signal)

        # Deterministic order: by the position of each cluster's first signal,
        # which `list_pending` already ordered by (created_at, id).
        batches = [grouped[key] for key in sorted(grouped)]
        return [b[:MAX_SIGNALS_PER_BATCH] for b in batches[:MAX_BATCHES_PER_PASS]]

    # --- one batch ------------------------------------------------------

    async def _assess_batch(
        self, user_id: str, batch: List[Dict[str, Any]], report: AssessmentPassReport
    ) -> bool:
        signal_ids = [str(s.get("id")) for s in batch if s.get("id")]
        batch_key = batch_key_for(user_id, signal_ids)

        # Idempotency: this exact batch was already assessed. The work exists,
        # so the signals are consumed — but no second assessment is written.
        existing = await self.repo.get_by_batch_key(user_id, batch_key)
        if existing:
            await self.signals.mark_processed(user_id, signal_ids)
            report.signals_processed += len(signal_ids)
            return True

        changes = describe_changes(batch)
        focal = focal_refs_for(batch)

        try:
            relations, discovered = await expand_relations(self.db, user_id, focal)
        except Exception as exc:
            logger.info("graph expansion failed: %s", type(exc).__name__)
            relations, discovered = [], []

        context_refs = sanitize_refs([*focal, *discovered], limit=MAX_REFS)

        try:
            evidence = await retrieve_evidence(
                self.db, user_id, changes=changes, refs=context_refs
            )
        except ContextUnavailable as exc:
            # Honest failure: we could not READ the life, which is different
            # from the life being empty. Do not conclude, do not consume.
            logger.info("impact deferred, context unavailable: %s", exc)
            report.failures.append("context_unavailable")
            return False

        report.evidence_items += len(evidence)
        priors = await prior_conclusions(self.db, user_id, focal)
        now_local, tz_name = await temporal_context(self.db, user_id)

        payload = build_impact_payload(
            changes=changes,
            evidence=evidence,
            relations=relations,
            capabilities=capability_catalog(self.db),
            prior_conclusions=priors,
            now_local=now_local,
            timezone_name=tz_name,
        )

        raw, provider, model = await self._reason(payload)
        report.ai_calls += 1
        if raw is None:
            # Provider unavailable or unparseable output — never fabricate an
            # assessment, never consume the signals.
            report.failures.append("provider_unavailable")
            return False

        assessment = self._build_assessment(
            user_id=user_id,
            raw=raw,
            signal_ids=signal_ids,
            focal=focal,
            evidence=evidence,
            batch_key=batch_key,
            provider=provider,
            model=model,
        )

        try:
            await self.repo.insert(assessment)
        except DuplicateAssessment:
            # A concurrent pass already wrote this exact batch.
            await self.signals.mark_processed(user_id, signal_ids)
            report.signals_processed += len(signal_ids)
            return True
        except Exception as exc:
            # PERSIST BEFORE CONSUME: an unpersisted conclusion must never
            # cause the signals that produced it to be marked processed, or
            # the change would be silently lost.
            logger.warning("assessment persistence failed: %s", type(exc).__name__)
            report.failures.append("assessment_persistence_failed")
            return False

        report.assessments_created += 1
        await self.signals.mark_processed(user_id, signal_ids)
        report.signals_processed += len(signal_ids)
        return True

    # --- provider -------------------------------------------------------

    async def _reason(
        self, payload: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """Exactly one reasoning call, exclusively through Provider Manager —
        never a direct vendor SDK call, so V2.8.3a failover and the circuit
        breaker both stay in force."""
        try:
            from llm.manager import get_manager

            manager = get_manager()
            result = await manager.chat(
                system=IMPACT_SYSTEM_PROMPT, user=payload, json_mode=True
            )
        except Exception as exc:
            logger.info("impact reasoning provider soft-fail: %s", type(exc).__name__)
            return None, None, None

        parsed = _parse_json(getattr(result, "text", "") or "")
        if parsed is None:
            logger.info("impact reasoning returned unparseable output")
            return None, None, None
        return parsed, getattr(result, "provider", None), getattr(result, "model", None)

    # --- validation -----------------------------------------------------

    def _build_assessment(
        self,
        *,
        user_id: str,
        raw: Dict[str, Any],
        signal_ids: List[str],
        focal: List[str],
        evidence: List[Dict[str, Any]],
        batch_key: str,
        provider: Optional[str],
        model: Optional[str],
    ) -> ImpactAssessment:
        """Coerce raw model output into the typed contract. The model proposes
        meaning; this validates shape, bounds and refs — the same division of
        labour the rest of ORA already uses."""
        known_capabilities = set(capability_catalog(self.db))
        evidence_refs = sanitize_refs(
            [e.get("ref") for e in evidence if e.get("ref")], limit=MAX_REFS
        )

        impacts: List[Impact] = []
        for item in list(raw.get("impacts") or [])[:MAX_IMPACTS]:
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement") or "").strip()
            if not statement:
                continue
            data: Dict[str, Any] = {
                "statement": statement[:300],
                "kind": item.get("kind"),
                "epistemic_status": item.get("epistemic_status") or "tentative",
                "confidence": _clamp(item.get("confidence"), 0.4),
                "affected_refs": sanitize_refs(item.get("affected_refs")),
                "evidence_refs": sanitize_refs(
                    item.get("evidence_refs"), limit=MAX_EVIDENCE_REFS
                ),
                "temporal_horizon": item.get("temporal_horizon") or "unknown",
            }
            authority = item.get("authority")
            if authority:
                data["authority"] = authority
            hint = str(item.get("capability_hint") or "").strip()
            # A hint must name a capability ORA actually has — an invented one
            # is dropped rather than persisted as if it existed.
            if hint and hint in known_capabilities:
                data["capability_hint"] = hint
            try:
                impacts.append(Impact.model_validate(data))
            except Exception:
                # A malformed impact is dropped; the rest of the assessment
                # stays usable rather than the whole batch being lost.
                continue

        requires_more = bool(raw.get("requires_more_context"))
        status = (
            "insufficient_evidence"
            if (requires_more and not evidence) or not impacts
            else "complete"
        )

        return ImpactAssessment(
            user_id=user_id,
            source_signal_ids=signal_ids[:8],
            focal_refs=focal,
            impacts=impacts,
            relevance=_clamp(raw.get("relevance"), 0.0),
            confidence=_clamp(raw.get("confidence"), 0.0),
            requires_more_context=requires_more,
            next_step_kind=_next_step(raw.get("next_step_kind")),
            reason_summary=(str(raw.get("reason_summary") or "").strip() or None),
            evidence_refs=evidence_refs,
            evidence_count=len(evidence),
            batch_key=batch_key,
            status=status,
            model_provider=(str(provider)[:40] if provider else None),
            model_name=(str(model)[:80] if model else None),
        )


_NEXT_STEPS = {
    "none",
    "gather_context",
    "ask_user",
    "propose_action",
    "compare_options",
}


def _next_step(value: Any) -> str:
    text = str(value or "none").strip()
    return text if text in _NEXT_STEPS else "none"


def _clamp(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Tolerant JSON extraction, mirroring the AI Core loop's own parser
    (kept local so this module does not import the full loop wiring)."""
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
