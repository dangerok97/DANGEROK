"""Process-local wake-up scheduler for Continuous Life Reasoning (V2.9.4).

Event-driven, never polling. The distinction is structural, not stylistic:

* The worker blocks on `asyncio.Queue.get()`. While nothing changes it consumes
  no CPU, opens no cursor, and touches Mongo zero times. An idle ORA costs
  exactly nothing — which is the whole point of the signal chain.
* Deferred decisions get ONE `asyncio.sleep` scheduled for their own moment.
  That is a one-shot alarm, not a loop that wakes up to look around.
* Recovery runs once, after boot. There is no periodic re-scan.

Reuses the shape already proven by `documents/intelligence/worker.py` — module
level queue, a task started at FastAPI startup, an in-flight set for dedupe,
Mongo as the source of truth — but deliberately NOT its `_recovery_loop`,
which re-scans every 120 seconds. That pattern is exactly what this pipeline
must not become.

DURABILITY: everything here is an accelerator, never the queue of record.
A signal stays `pending` in Mongo until an assessment consumes it. If this
process dies with a full queue, nothing is lost — the work is simply picked up
by the next wake-up or by startup recovery. That is why every function here is
best-effort and none of them can fail the caller.

The durable fact and its ephemeral alarm are NOT one atomic operation — they
are two separate writes to two separate places (Mongo `defer_until`, and this
process's `_deferred_tasks`), and there is a real gap between them. A process
that dies between persisting a `defer` decision and this module arming its
timer, or that dies later and takes the timer down with it, leaves a fully
durable deferral with no live alarm. `recover_pending` closes that gap at
every boot: it rebuilds the one-shot timer for any still-current deferral
that Mongo already knows about, whether it is already due or still in the
future, from that persisted state alone.

BOUNDED QUERY IS NOT TRUNCATED RECOVERY. Each read `recover_pending` issues
is capped (never a full-collection scan), but the sweep as a whole walks
every matching record to exhaustion, one bounded page at a time, via
`OrchestrationService.iter_*`. The 51st user behind a batch of 50 is not
silently left without a timer — recovery just needs one more page to reach
them. Paging yields to the event loop between pages (`await
asyncio.sleep(0)`) so a large backlog costs time, never a blocked loop or a
polling cron: the walk is still finite, still runs exactly once per boot,
and still touches Mongo only in bounded batches.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("ora.life_orchestration.scheduler")

# Bounded so a pathological burst cannot grow memory without limit. Dropping a
# wake-up is safe: the signal is still pending in Mongo.
MAX_QUEUE_SIZE = 1000
# How long after boot recovery runs, so it never competes with startup.
RECOVERY_DELAY_SECONDS = 3
# A deferral further out than this is left to a future boot rather than held
# as a live timer for days.
MAX_DEFER_TIMER_SECONDS = 6 * 3600

_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_recovery_task: Optional[asyncio.Task] = None
_deferred_tasks: Dict[str, asyncio.Task] = {}
_started = False
_stopping = False

# Coalescing state — user ids only, never user content.
_scheduled: Set[str] = set()   # queued, waiting for a worker
_active: Set[str] = set()      # currently being processed
_redo: Set[str] = set()        # changed again while their pass was running

_stats: Dict[str, int] = {
    "wakeups_requested": 0,
    "wakeups_coalesced": 0,
    "wakeups_dropped": 0,
    "passes_started": 0,
    "passes_completed": 0,
    "passes_failed": 0,
    "passes_skipped_lease": 0,
    "passes_skipped_backoff": 0,
    "impact_runs": 0,
    "attention_runs": 0,
    "ai_calls": 0,
    "signals_processed": 0,
    "assessments_evaluated": 0,
    "suggestions_created": 0,
    "silent_decisions": 0,
    "deferred_decisions": 0,
    "deferred_scheduled": 0,
    "deferred_recovered": 0,
    "defer_reevaluations_requested": 0,
    "defer_reevaluations_completed": 0,
    "defer_reevaluations_failed": 0,
    "defer_budget_exhausted": 0,
    "retry_scheduled": 0,
    "recovery_users": 0,
    "recovery_batches": 0,
    "future_deferrals_rearmed": 0,
    "redo_requeued": 0,
    "total_latency_ms": 0,
}


def _get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    return _queue


async def schedule_user_reasoning(user_id: str, *, reason: str = "signal") -> bool:
    """Best-effort request to process this user's pending changes soon.

    NEVER blocks the caller and NEVER raises: it is called from the request
    path immediately after a life mutation, and a mutation must not fail — or
    slow down — because the reasoning pipeline is busy, disabled, or absent.

    Returns True when a pass was actually queued. False means coalesced,
    dropped or unavailable — all safe, because the signal that triggered this
    is already durable in Mongo.
    """
    from life_orchestration.state import orchestration_enabled

    if not user_id or not orchestration_enabled() or _stopping:
        return False

    _stats["wakeups_requested"] += 1

    # Coalescing (§12): one pending pass per user, never five for five
    # near-simultaneous mutations. A user already running gets a redo flag so
    # changes arriving mid-pass are picked up rather than lost.
    if user_id in _scheduled:
        _stats["wakeups_coalesced"] += 1
        return False
    if user_id in _active:
        _redo.add(user_id)
        _stats["wakeups_coalesced"] += 1
        return False

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No event loop (sync context / some tests). The signal stays pending.
        return False

    try:
        _get_queue().put_nowait({"user_id": user_id, "reason": reason})
    except asyncio.QueueFull:
        _stats["wakeups_dropped"] += 1
        logger.warning("orchestration queue full; wake-up dropped (work stays pending)")
        return False
    except Exception as exc:
        logger.info("schedule soft-fail: %s", type(exc).__name__)
        return False

    _scheduled.add(user_id)
    return True


async def _run_one(user_id: str) -> None:
    """Process one user, then arm whatever follow-up their state implies."""
    from deps import db
    from life_orchestration.service import OrchestrationService

    svc = OrchestrationService(db)
    _stats["passes_started"] += 1
    try:
        report = await svc.run_user_pass(user_id)
    except Exception as exc:
        _stats["passes_failed"] += 1
        logger.warning("orchestration run failed error=%s", type(exc).__name__)
        return

    if report.skipped_reason == "lease_held":
        _stats["passes_skipped_lease"] += 1
    elif report.skipped_reason == "backoff_active":
        _stats["passes_skipped_backoff"] += 1

    if report.failures:
        _stats["passes_failed"] += 1
        _stats["retry_scheduled"] += 1
    else:
        _stats["passes_completed"] += 1

    _stats["impact_runs"] += report.impact_runs
    _stats["attention_runs"] += report.attention_runs
    _stats["ai_calls"] += report.ai_calls
    _stats["signals_processed"] += report.signals_processed
    _stats["assessments_evaluated"] += report.assessments_evaluated
    _stats["suggestions_created"] += report.suggestions_created
    _stats["silent_decisions"] += report.silent
    _stats["deferred_decisions"] += report.deferred
    _stats["defer_reevaluations_requested"] += report.defer_reevaluations_requested
    _stats["defer_reevaluations_completed"] += report.defer_reevaluations_completed
    _stats["defer_reevaluations_failed"] += report.defer_reevaluations_failed
    _stats["defer_budget_exhausted"] += report.defer_budget_exhausted
    _stats["total_latency_ms"] += report.elapsed_ms

    # A pass ran because this life moved, which is exactly when it is worth
    # asking whether any of it is worth saying. Reusing this wake-up rather
    # than running a second worker is the whole integration: one queue, one
    # coalescing rule, one place that knows a user is busy.
    try:
        await _review_opportunities(user_id)
    except Exception as exc:
        logger.info("opportunity review soft-fail: %s", type(exc).__name__)

    # Arm a one-shot alarm for the soonest deferral, if any.
    try:
        await arm_deferred_timer(user_id, svc)
    except Exception as exc:
        logger.info("deferred arm soft-fail: %s", type(exc).__name__)


async def _review_opportunities(user_id: str) -> None:
    """
    Ask whether anything that moved was worth saying. Usually: no.

    Deliberately not a trigger. This does not know what changed, cannot see a
    calendar or a front door, and has no way to turn either into a card — it
    starts a review, and the review is free to decide there is nothing here,
    which is what it decides most of the time. Its own guards (nothing
    pending, a cooldown, an unchanged fingerprint) mean the common case costs
    no model call at all.
    """
    from deps import db
    from opportunities.discovery import OpportunityDiscovery
    from opportunities.surfacing import SurfacingService

    outcome = await OpportunityDiscovery(db).review(user_id, reason="state_changed")
    if not outcome.ran or outcome.unavailable:
        return

    scan = outcome.scan
    # A review ran. That is a real thing to have done, and it is the only
    # thing that entitles anybody to say so later — the record is written by
    # the work, never by a surface that wants a line.
    await _note_review(user_id, outcome, scan)

    if scan is None or (not scan.created and not scan.updated):
        # Nothing new to consider showing. What is already on their home was
        # decided before and is not re-litigated because a document arrived.
        return
    await SurfacingService(db).decide(user_id)

    # Something was raised or changed. Whether it is worth reaching them
    # where they are is a separate judgement again, and usually the answer is
    # that it is not.
    await _consider_delivery(user_id, scan)


async def _note_review(user_id: str, outcome: Any, scan: Any) -> None:
    """
    Write down what the review actually did, with what it could see.

    `sources_unavailable` is the field that keeps "tutto tranquillo" honest: a
    review that could not reach half of somebody's life has not established
    that nothing is happening, and the copy written from this record has to be
    able to tell the difference.
    """
    from deps import db
    from delivery.service import DeliveryService

    try:
        created = len(getattr(scan, "created", []) or [])
        updated = len(getattr(scan, "updated", []) or [])
        kind = "opportunity_created" if created else "review_completed"
        await DeliveryService(db).note_activity(
            user_id,
            kind=kind,
            source_refs=[o.id for o in (getattr(scan, "created", None) or [])][:4],
            provenance={
                "changes_reviewed": getattr(outcome, "changes_reviewed", 0),
                "raised": created,
                "updated": updated,
                "reason": getattr(outcome, "reason", ""),
                "sources_unavailable": list(
                    getattr(scan, "unavailable_sources", None) or []
                ),
            },
        )
        # And, at most every few hours, put it into words. The line is written
        # from the record of what ran, never from a wish to have something to
        # show.
        await DeliveryService(db).summarise_recent(user_id)
    except Exception as exc:
        logger.info("ambient note soft-fail: %s", type(exc).__name__)


async def _consider_delivery(user_id: str, scan: Any) -> None:
    """
    Ask, for each thing just raised, whether it is worth reaching them.

    Deliberately not derived from surfacing: something can belong on Home and
    have no business buzzing in a pocket, and reading the second decision off
    the first would throw away the only judgement that protects a person's
    attention.
    """
    from deps import db
    from delivery.service import DeliveryService

    service = DeliveryService(db)
    for opportunity in list(getattr(scan, "created", []) or [])[:2]:
        try:
            await service.evaluate(user_id, opportunity.id)
        except Exception as exc:
            logger.info("delivery evaluate soft-fail: %s", type(exc).__name__)

    await _consider_goals(user_id, scan)


async def _consider_goals(user_id: str, scan: Any) -> None:
    """
    Ask whether any of this is worth doing something about.

        OPPORTUNITY != GOAL.

    Deliberately a question and not a conversion. Something can be true, and
    worth knowing, and still not be worth pursuing — most of the time the
    answer is no, and there is no branch here that could make it yes.
    """
    from deps import db
    from agent.service import AgentService

    service = AgentService(db)
    for opportunity in list(getattr(scan, "created", []) or [])[:2]:
        try:
            await service.consider(
                user_id,
                situation={
                    "what": opportunity.semantic_summary,
                    "why_it_matters": opportunity.why_it_matters,
                    "why_now": opportunity.why_now or None,
                    "waiting_on_an_answer": opportunity.requires_clarification,
                    "the_question": opportunity.clarifying_question or None,
                },
                origin="agent_initiated",
                opportunity_id=opportunity.id,
                source_kind="opportunity",
                source_refs=[e.ref for e in opportunity.evidence][:4],
            )
        except Exception as exc:
            logger.info("agent consider soft-fail: %s", type(exc).__name__)


async def _worker_loop() -> None:
    """Consume wake-ups. Blocks on the queue — no timer, no scan, no Mongo
    access while idle."""
    queue = _get_queue()
    logger.info("life orchestration worker started")
    while not _stopping:
        job = await queue.get()
        user_id = str(job.get("user_id") or "")
        _scheduled.discard(user_id)
        if not user_id:
            queue.task_done()
            continue
        _active.add(user_id)
        try:
            await _run_one(user_id)
        finally:
            _active.discard(user_id)
            queue.task_done()
            # Something changed while this pass ran — give it one more turn.
            if user_id in _redo:
                _redo.discard(user_id)
                _stats["redo_requeued"] += 1
                await schedule_user_reasoning(user_id, reason="redo")


async def arm_deferred_timer(user_id: str, svc: Any = None) -> bool:
    """Schedule ONE alarm for this user's soonest deferral.

    A single `asyncio.sleep` for a known moment — not a loop that wakes up to
    check whether the moment has arrived. If the process dies the timer dies
    with it, and startup recovery finds the deferral because `defer_until` is
    persisted.
    """
    if _stopping:
        return False
    from deps import db
    from life_orchestration.service import OrchestrationService

    svc = svc or OrchestrationService(db)
    when = await svc.next_deferral_due_at(user_id)
    if not when:
        return False

    delay = _seconds_until(when)
    if delay is None or delay > MAX_DEFER_TIMER_SECONDS:
        # Too far out to hold a live timer; a future boot will recover it.
        return False

    existing = _deferred_tasks.get(user_id)
    if existing and not existing.done():
        return False

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    _deferred_tasks[user_id] = loop.create_task(
        _deferred_wake(user_id, max(0.0, delay)), name=f"ora-defer-{user_id[:12]}"
    )
    _stats["deferred_scheduled"] += 1
    return True


async def _deferred_wake(user_id: str, delay: float) -> None:
    """One-shot: sleep until the deferral's own moment, then request a pass.

    Deliberately does NOT reconsider the deferral itself here — that would be
    an AI call running outside any lease. This only confirms the deferral is
    still there (cheap, no AI) and queues `schedule_user_reasoning`; the
    actual reconsideration happens inside `run_user_pass`, lease-protected
    exactly like every other AI call in this pipeline. No loop.
    """
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    _deferred_tasks.pop(user_id, None)
    if _stopping:
        return
    try:
        from deps import db
        from life_orchestration.service import OrchestrationService

        if await OrchestrationService(db).has_due_deferral(user_id):
            _stats["deferred_recovered"] += 1
            await schedule_user_reasoning(user_id, reason="deferred")
    except Exception as exc:
        logger.info("deferred wake soft-fail: %s", type(exc).__name__)


async def recover_pending(*, batch_size: int = 50) -> int:
    """A COMPLETE, batch-paged sweep for work a previous process left behind.

    Runs ONCE after boot, never on a timer. Schedules wake-ups rather than
    reasoning inline, so recovery itself spends no AI call.

    "Bounded" describes each individual query, never the total amount of
    work recovered: every matching record — pending signals/assessments,
    deferrals already due, deferrals still in the future whose one-shot
    timer died with the previous process — is walked to exhaustion, one
    `batch_size`-sized page at a time, via `OrchestrationService.iter_*`. A
    99th user waiting behind the first 50 is not left invisible; recovery
    just takes one more page to reach them, yielding to the event loop
    between pages (`asyncio.sleep(0)`) so this stays cooperative scheduling,
    never a blocking scan. This is still a FINITE walk — it stops the moment
    a page comes back short of `batch_size` — never a loop that re-polls.
    """
    from deps import db
    from life_orchestration.service import OrchestrationService

    svc = OrchestrationService(db)
    scheduled = 0
    seen_pending: set = set()

    # Pending signals and pending assessments both mean "this user has real
    # unfinished work"; a user appearing in both must still be scheduled
    # only once, exactly like the single-call version did.
    for iterator, label in (
        (svc.iter_users_with_pending_signals(batch_size=batch_size), "signal"),
        (svc.iter_users_with_pending_assessments(batch_size=batch_size), "assessment"),
    ):
        try:
            async for batch in iterator:
                _stats["recovery_batches"] += 1
                for user_id in batch:
                    if user_id in seen_pending:
                        continue
                    seen_pending.add(user_id)
                    _stats["recovery_users"] += 1
                    if await schedule_user_reasoning(user_id, reason="startup_recovery"):
                        scheduled += 1
                await asyncio.sleep(0)
        except Exception as exc:
            logger.info("pending %s recovery soft-fail: %s", label, type(exc).__name__)

    try:
        async for batch in svc.iter_users_with_due_deferrals(batch_size=batch_size):
            _stats["recovery_batches"] += 1
            for user_id in batch:
                # Existence check only (no AI call here either) — the same
                # lease-protected pass that handles ordinary recovery also
                # reconsiders any deferral it finds due.
                _stats["deferred_recovered"] += 1
                await schedule_user_reasoning(user_id, reason="deferred_recovery")
            await asyncio.sleep(0)
    except Exception as exc:
        logger.info("deferred recovery soft-fail: %s", type(exc).__name__)

    # A deferral that hasn't come due yet has no queue entry to recover —
    # its only trace is the persisted `defer_until`. The one-shot timer that
    # would normally watch it is process-local and died with the previous
    # process, so it must be REBUILT here from that durable fact, or it stays
    # undiscoverable until unrelated activity for the same user happens to
    # run a pass. This costs bounded queries and zero AI calls; arming
    # itself is idempotent per user (`arm_deferred_timer` already refuses to
    # duplicate a live timer, so a user reachable from more than one page
    # still ends up with exactly one).
    try:
        async for batch in svc.iter_users_with_future_deferrals(batch_size=batch_size):
            _stats["recovery_batches"] += 1
            for user_id in batch:
                if await arm_deferred_timer(user_id, svc):
                    _stats["future_deferrals_rearmed"] += 1
            await asyncio.sleep(0)
    except Exception as exc:
        logger.info("future deferral timer rebuild soft-fail: %s", type(exc).__name__)

    if scheduled:
        logger.info("orchestration recovered %s users with pending work", scheduled)
    return scheduled


async def _recovery_once() -> None:
    """Delay past startup, then sweep once. Deliberately not a loop."""
    try:
        await asyncio.sleep(RECOVERY_DELAY_SECONDS)
        await recover_pending()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("orchestration startup recovery failed (non-fatal)")


def start_orchestrator() -> bool:
    """Start the worker once per process, from FastAPI startup.

    Never blocks boot and never performs an AI call: it only creates the
    consumer task and a single delayed recovery sweep.
    """
    global _worker_task, _recovery_task, _started, _stopping
    from life_orchestration.state import orchestration_enabled

    if _started or not orchestration_enabled():
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    _stopping = False
    _worker_task = loop.create_task(_worker_loop(), name="ora-life-orchestrator")
    _recovery_task = loop.create_task(_recovery_once(), name="ora-life-orch-recovery")
    _started = True
    return True


async def stop_orchestrator() -> None:
    """Graceful shutdown. Nothing is drained on purpose: whatever is queued is
    still pending in Mongo, so cancelling loses no work."""
    global _started, _stopping, _queue, _worker_task, _recovery_task
    _stopping = True
    for task in [_worker_task, _recovery_task, *_deferred_tasks.values()]:
        if task and not task.done():
            task.cancel()
    _deferred_tasks.clear()
    _scheduled.clear()
    _active.clear()
    _redo.clear()
    _worker_task = None
    _recovery_task = None
    # The queue is bound to the loop it was created on, like every asyncio
    # primitive. Keeping it past shutdown would hand the next worker — running
    # on a new loop — a queue that belongs to a loop nobody runs any more.
    # Dropping it loses nothing: as the docstring says, queued work is still
    # pending in Mongo, and the next start builds a queue on its own loop.
    _queue = None
    _started = False


def orchestrator_stats() -> Dict[str, Any]:
    """Bounded counters — ids and totals only, never user content."""
    queue = _queue
    passes = max(1, _stats["passes_completed"] + _stats["passes_failed"])
    signals = max(1, _stats["signals_processed"])
    return {
        **_stats,
        "started": _started,
        "stopping": _stopping,
        "queue_size": queue.qsize() if queue is not None else 0,
        "users_scheduled": len(_scheduled),
        "users_active": len(_active),
        "deferred_timers": len(_deferred_tasks),
        "mode": "in_process_event_driven",
        # Cost accounting (§32): what a mutation actually buys.
        "ai_calls_per_100_signals": round(
            (_stats["ai_calls"] / signals) * 100, 2
        ),
        "suggestions_per_100_signals": round(
            (_stats["suggestions_created"] / signals) * 100, 2
        ),
        "coalesce_ratio": round(
            _stats["wakeups_coalesced"] / max(1, _stats["wakeups_requested"]), 3
        ),
        "avg_pass_latency_ms": round(_stats["total_latency_ms"] / passes, 1),
    }


def reset_stats_for_test() -> None:
    """Test-only: clear counters and coalescing state between cases."""
    for key in _stats:
        _stats[key] = 0
    _scheduled.clear()
    _active.clear()
    _redo.clear()


def _seconds_until(when_iso: str) -> Optional[float]:
    try:
        when = datetime.fromisoformat(str(when_iso).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return (when - datetime.now(timezone.utc)).total_seconds()
    except Exception:
        return None
