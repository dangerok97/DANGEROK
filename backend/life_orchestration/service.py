"""Continuous Life Reasoning orchestration (V2.9.4).

A THIN coordinator. It owns no cognition of its own: it decides nothing about
meaning (V2.9.2), nothing about delivery (V2.9.3), executes no tool and sends
nothing. Its entire job is to run existing bounded passes, in order, for one
user, and then stop.

    pending LifeChangeSignals?   → ImpactReasoningService.run_pass
    pending ImpactAssessments?   → AttentionService.run_pass
    a deferral due right now?   → AttentionService.reevaluate_due_deferrals
    repeat at most MAX_CYCLES, then stop

The third line is deliberately NOT "re-run attention on the same batch": it
asks the AI to reconsider ATTENTION ONLY for a decision it already deferred,
never re-runs Impact Reasoning (V2.9.2) for it. See
`life_attention.service.AttentionService.reevaluate_due_deferrals`.

It lives in its own module rather than inside `life_reasoning/` because the
dependency chain is strictly one-way — `life_attention → life_reasoning →
life_signals` — and an orchestrator inside `life_reasoning` importing
`life_attention` would close that into an import cycle.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from life_orchestration.state import (
    OrchestrationStateRepository,
    orchestration_enabled,
)

logger = logging.getLogger("ora.life_orchestration")

# A pass may loop only to pick up work that appeared *while it ran*. Two
# cycles is enough for that; more would be an unbounded drain loop wearing a
# cap as a disguise.
MAX_CYCLES = 2


class PassReport:
    """Bounded, non-sensitive outcome of one orchestration pass."""

    __slots__ = (
        "user_id", "ran", "skipped_reason", "cycles", "impact_runs",
        "attention_runs", "ai_calls", "signals_processed",
        "assessments_evaluated", "suggestions_created", "silent",
        "deferred", "defer_reevaluations_requested",
        "defer_reevaluations_completed", "defer_reevaluations_failed",
        "defer_budget_exhausted", "failures", "elapsed_ms",
    )

    def __init__(self, user_id: str = ""):
        self.user_id = user_id
        self.ran = False
        self.skipped_reason: Optional[str] = None
        self.cycles = 0
        self.impact_runs = 0
        self.attention_runs = 0
        self.ai_calls = 0
        self.signals_processed = 0
        self.assessments_evaluated = 0
        self.suggestions_created = 0
        self.silent = 0
        self.deferred = 0
        # Deferral reconsideration (V2.9.4 hardening) — see
        # `AttentionService.reevaluate_due_deferrals`. These count AI-made
        # decisions on ALREADY-DEFERRED chains, never a new evaluation.
        self.defer_reevaluations_requested = 0
        self.defer_reevaluations_completed = 0
        self.defer_reevaluations_failed = 0
        self.defer_budget_exhausted = 0
        self.failures: List[str] = []
        self.elapsed_ms = 0

    def public(self) -> Dict[str, Any]:
        return {
            "ran": self.ran,
            "skipped_reason": self.skipped_reason,
            "cycles": self.cycles,
            "impact_runs": self.impact_runs,
            "attention_runs": self.attention_runs,
            "ai_calls": self.ai_calls,
            "signals_processed": self.signals_processed,
            "assessments_evaluated": self.assessments_evaluated,
            "suggestions_created": self.suggestions_created,
            "silent": self.silent,
            "deferred": self.deferred,
            "defer_reevaluations_requested": self.defer_reevaluations_requested,
            "defer_reevaluations_completed": self.defer_reevaluations_completed,
            "defer_reevaluations_failed": self.defer_reevaluations_failed,
            "defer_budget_exhausted": self.defer_budget_exhausted,
            "failures": list(self.failures),
            "elapsed_ms": self.elapsed_ms,
        }


class OrchestrationService:
    def __init__(self, db):
        self.db = db
        self.state = OrchestrationStateRepository(db)

    async def ensure_indexes(self) -> None:
        await self.state.ensure_indexes()

    # --- the pass ------------------------------------------------------

    async def run_user_pass(
        self, user_id: str, *, use_lease: bool = True, respect_backoff: bool = True
    ) -> PassReport:
        """Run the full pipeline once for one user.

        This is the manual/testable entry point (§30) as well as what the
        scheduler calls. It never raises for an expected failure: everything
        stays pending in Mongo and a later pass retries.
        """
        t0 = time.perf_counter()
        report = PassReport(user_id)
        if not user_id or self.db is None:
            report.skipped_reason = "not_configured"
            return report

        # Cheapest possible check first: an idle user must not even cost a
        # lease write. Two bounded indexed lookups, then out.
        if not await self._has_pending_work(user_id):
            report.skipped_reason = "no_pending_work"
            report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return report

        if respect_backoff and await self.state.backoff_active(user_id):
            report.skipped_reason = "backoff_active"
            report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return report

        if use_lease and not await self.state.acquire(user_id):
            # Another process is already spending the AI calls for this user.
            report.skipped_reason = "lease_held"
            report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return report

        try:
            await self._run_cycles(user_id, report)
        except Exception as exc:
            logger.warning("orchestration pass failed error=%s", type(exc).__name__)
            report.failures.append(type(exc).__name__)
        finally:
            if use_lease:
                await self.state.release(user_id)

        if report.failures:
            await self.state.record_failure(user_id, reason=report.failures[0])
        elif report.ran:
            await self.state.record_success(user_id)

        report.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if report.ran:
            logger.info(
                "orchestration pass cycles=%s impact=%s attention=%s ai=%s "
                "signals=%s assessments=%s suggestions=%s ms=%s",
                report.cycles, report.impact_runs, report.attention_runs,
                report.ai_calls, report.signals_processed,
                report.assessments_evaluated, report.suggestions_created,
                report.elapsed_ms,
            )
        return report

    async def _run_cycles(self, user_id: str, report: PassReport) -> None:
        from life_attention.service import AttentionService
        from life_reasoning.service import ImpactReasoningService
        from life_signals.service import LifeSignalService

        signals = LifeSignalService(self.db)
        impact = ImpactReasoningService(self.db)
        attention = AttentionService(self.db)

        for _ in range(MAX_CYCLES):
            progressed = False
            report.cycles += 1

            # 1. Signals → assessments. Only when there is something to do:
            #    an idle system must cost nothing.
            if await signals.count_pending(user_id):
                report.ran = True
                impact_report = await impact.run_pass(user_id)
                report.impact_runs += 1
                report.ai_calls += impact_report.ai_calls
                report.signals_processed += impact_report.signals_processed
                report.failures.extend(impact_report.failures)
                if impact_report.assessments_created or impact_report.signals_processed:
                    progressed = True

            # 2. Assessments → attention decisions. Checked independently of
            #    step 1's outcome: assessments may already be pending from an
            #    earlier pass whose attention half failed. If impact produced
            #    nothing, this is simply empty and costs nothing — attention
            #    is never invited to reason about an assessment that does not
            #    exist.
            if await self._has_pending_assessment(user_id):
                report.ran = True
                attention_report = await attention.run_pass(user_id)
                report.attention_runs += 1
                report.ai_calls += attention_report.ai_calls
                report.assessments_evaluated += attention_report.assessments_evaluated
                report.suggestions_created += attention_report.suggestions_created
                report.silent += attention_report.silent
                report.deferred += attention_report.deferred
                report.failures.extend(attention_report.failures)
                if attention_report.assessments_evaluated:
                    progressed = True

            # 3. Deferrals whose moment arrived → the AI reconsiders ATTENTION
            #    ONLY. Guarded by the same cheap existence check as steps 1-2:
            #    a user with nothing due costs one indexed lookup and no AI
            #    call. Impact Reasoning is never invoked from this branch —
            #    `reevaluate_due_deferrals` re-fetches the same assessments a
            #    deferred chain was already about; it does not derive new
            #    ones.
            if await self._has_due_deferral(user_id):
                report.ran = True
                defer_report = await attention.reevaluate_due_deferrals(user_id)
                report.ai_calls += defer_report.ai_calls
                report.suggestions_created += defer_report.suggestions_created
                report.defer_reevaluations_requested += (
                    defer_report.defer_reevaluations_requested
                )
                report.defer_reevaluations_completed += (
                    defer_report.defer_reevaluations_completed
                )
                report.defer_reevaluations_failed += (
                    defer_report.defer_reevaluations_failed
                )
                report.defer_budget_exhausted += defer_report.defer_budget_exhausted
                report.failures.extend(defer_report.failures)
                if (
                    defer_report.defer_reevaluations_completed
                    or defer_report.defer_reevaluations_failed
                ):
                    progressed = True

            if not progressed:
                break

    async def _has_pending_work(self, user_id: str) -> bool:
        """Is there anything at all to do for this user? Bounded and indexed."""
        from life_signals.service import LifeSignalService

        try:
            if await LifeSignalService(self.db).count_pending(user_id):
                return True
        except Exception as exc:
            logger.info("pending signal check soft-fail: %s", type(exc).__name__)
        if await self._has_pending_assessment(user_id):
            return True
        return await self._has_due_deferral(user_id)

    async def _has_pending_assessment(self, user_id: str) -> bool:
        """Bounded existence check — never a count over the collection."""
        from life_reasoning.repository import ImpactAssessmentRepository

        try:
            items = await ImpactAssessmentRepository(self.db).list_awaiting_attention(
                user_id, limit=1
            )
            return bool(items)
        except Exception as exc:
            logger.info("pending assessment check soft-fail: %s", type(exc).__name__)
            return False

    # --- deferred decisions --------------------------------------------

    async def _has_due_deferral(self, user_id: str) -> bool:
        """Bounded existence check — is any deferral of this user's due right
        now? One small indexed query (`limit=1`), zero AI calls. This is the
        ONLY thing that may run outside a lease: it decides nothing, it only
        looks."""
        from life_attention.repository import AttentionDecisionRepository

        try:
            due = await AttentionDecisionRepository(self.db).list_due_deferred(
                user_id, now_iso=_now_iso(), limit=1
            )
            return bool(due)
        except Exception as exc:
            logger.info("due deferral check soft-fail: %s", type(exc).__name__)
            return False

    async def has_due_deferral(self, user_id: str) -> bool:
        """Public existence check for the scheduler (§15): is there a
        deferral worth waking a pass for? Used to decide whether to queue
        `schedule_user_reasoning`, never to decide the deferral itself — the
        AI still makes that call inside `run_user_pass`."""
        return await self._has_due_deferral(user_id)

    async def next_deferral_due_at(self, user_id: str) -> Optional[str]:
        """Earliest not-yet-due deferral, so the scheduler can set one
        one-shot timer instead of waking up to look."""
        from life_attention.repository import AttentionDecisionRepository

        try:
            return await AttentionDecisionRepository(self.db).earliest_pending_defer(
                user_id
            )
        except Exception:
            return None

    # --- recovery -------------------------------------------------------

    async def users_with_pending_work(self, *, limit: int = 50) -> List[str]:
        """Bounded, indexed recovery read for startup.

        Deliberately capped and never a full-collection scan: this runs once
        per boot, not on a timer, and its only job is to re-arm work that a
        previous process had in flight when it died.
        """
        users: List[str] = []
        try:
            cur = self.db.life_change_signals.find(
                {"status": "pending"}, {"_id": 0, "user_id": 1}
            ).limit(max(1, min(int(limit or 50), 200)))
            async for doc in cur:
                uid = str(doc.get("user_id") or "")
                if uid and uid not in users:
                    users.append(uid)
        except Exception as exc:
            logger.info("pending signal recovery soft-fail: %s", type(exc).__name__)

        try:
            cur = self.db.life_impact_assessments.find(
                {"attention_status": {"$ne": "evaluated"}}, {"_id": 0, "user_id": 1}
            ).limit(max(1, min(int(limit or 50), 200)))
            async for doc in cur:
                uid = str(doc.get("user_id") or "")
                if uid and uid not in users:
                    users.append(uid)
        except Exception as exc:
            logger.info("pending assessment recovery soft-fail: %s", type(exc).__name__)

        return users[: max(1, min(int(limit or 50), 200))]

    async def users_with_due_deferrals(self, *, limit: int = 50) -> List[str]:
        """Deferrals whose moment passed while no process was alive to notice.

        Same eligibility as `AttentionDecisionRepository.list_due_deferred`:
        only chains that are still current (`superseded_by: None`) and still
        have automatic budget left are worth waking a pass for.
        """
        users: List[str] = []
        try:
            cur = self.db.life_attention_decisions.find(
                {
                    "delivery": "defer",
                    "defer_until": {"$ne": None, "$lte": _now_iso()},
                    "superseded_by": None,
                    "auto_re_evaluation_exhausted": {"$ne": True},
                },
                {"_id": 0, "user_id": 1},
            ).limit(max(1, min(int(limit or 50), 200)))
            async for doc in cur:
                uid = str(doc.get("user_id") or "")
                if uid and uid not in users:
                    users.append(uid)
        except Exception as exc:
            logger.info("due deferral recovery soft-fail: %s", type(exc).__name__)
        return users

    async def users_with_future_deferrals(self, *, limit: int = 50) -> List[str]:
        """Users whose current deferral hasn't come due yet, so a booting
        process can RECONSTRUCT their one-shot wake-up timer.

        The timer that normally arms itself is process-local and dies with
        its process. Mongo already holds the durable fact (`defer_until`);
        this is the bounded, indexed read that lets a fresh process rebuild
        the ephemeral alarm from that fact, instead of leaving a future
        deferral undiscoverable until either new activity for that user
        happens to run a pass, or the process survives long enough for the
        deferral to become due and be found by `users_with_due_deferrals`.

        Same eligibility as `users_with_due_deferrals`, just the other side
        of `now` — still current, still has automatic budget.
        """
        users: List[str] = []
        try:
            cur = self.db.life_attention_decisions.find(
                {
                    "delivery": "defer",
                    "defer_until": {"$ne": None, "$gt": _now_iso()},
                    "superseded_by": None,
                    "auto_re_evaluation_exhausted": {"$ne": True},
                },
                {"_id": 0, "user_id": 1},
            ).limit(max(1, min(int(limit or 50), 200)))
            async for doc in cur:
                uid = str(doc.get("user_id") or "")
                if uid and uid not in users:
                    users.append(uid)
        except Exception as exc:
            logger.info("future deferral recovery soft-fail: %s", type(exc).__name__)
        return users

    # --- complete (batch-paged) recovery --------------------------------
    #
    # `users_with_*` above are single bounded reads: cheap, but a hard cap on
    # *total* results — the 51st user past `limit` is silently invisible to
    # that one call. That is fine for an existence check (V.g. "is anything
    # pending at all?"), but startup recovery's job is to reconstruct
    # EVERYTHING Mongo already knows a previous process left behind, not the
    # first 50 of it. "Bounded" must describe each individual query, never
    # the total amount of recovery work performed.
    #
    # These iterators page through their collection once, in stable `_id`
    # order, yielding one bounded batch of user ids at a time until the
    # collection is exhausted. A cursor (`_id > last_seen`) makes each page
    # strictly disjoint from the last, so nothing is ever re-read within one
    # walk and the walk always terminates — never `skip`, which would get
    # slower and could re-visit documents as the collection changes under it.

    async def _iter_user_batches(
        self, collection: str, query: Dict[str, Any], *, batch_size: int = 50
    ) -> AsyncIterator[List[str]]:
        capped = max(1, min(int(batch_size or 50), 200))
        coll = self.db[collection]
        last_id = None
        while True:
            page_query = dict(query)
            if last_id is not None:
                page_query["_id"] = {"$gt": last_id}
            docs = await (
                coll.find(page_query, {"_id": 1, "user_id": 1})
                .sort("_id", 1)
                .limit(capped)
                .to_list(capped)
            )
            if not docs:
                return
            last_id = docs[-1]["_id"]
            users: List[str] = []
            for doc in docs:
                uid = str(doc.get("user_id") or "")
                if uid and uid not in users:
                    users.append(uid)
            yield users
            if len(docs) < capped:
                return

    def iter_users_with_pending_signals(
        self, *, batch_size: int = 50
    ) -> AsyncIterator[List[str]]:
        return self._iter_user_batches(
            "life_change_signals", {"status": "pending"}, batch_size=batch_size
        )

    def iter_users_with_pending_assessments(
        self, *, batch_size: int = 50
    ) -> AsyncIterator[List[str]]:
        return self._iter_user_batches(
            "life_impact_assessments",
            {"attention_status": {"$ne": "evaluated"}},
            batch_size=batch_size,
        )

    def iter_users_with_due_deferrals(
        self, *, batch_size: int = 50
    ) -> AsyncIterator[List[str]]:
        return self._iter_user_batches(
            "life_attention_decisions",
            {
                "delivery": "defer",
                "defer_until": {"$ne": None, "$lte": _now_iso()},
                "superseded_by": None,
                "auto_re_evaluation_exhausted": {"$ne": True},
            },
            batch_size=batch_size,
        )

    def iter_users_with_future_deferrals(
        self, *, batch_size: int = 50
    ) -> AsyncIterator[List[str]]:
        return self._iter_user_batches(
            "life_attention_decisions",
            {
                "delivery": "defer",
                "defer_until": {"$ne": None, "$gt": _now_iso()},
                "superseded_by": None,
                "auto_re_evaluation_exhausted": {"$ne": True},
            },
            batch_size=batch_size,
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["OrchestrationService", "PassReport", "MAX_CYCLES", "orchestration_enabled"]
