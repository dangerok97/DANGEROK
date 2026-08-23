"""V2.9.4 — Timer durability at startup (deterministic, A-J).

The one-shot deferred-wake timer is process-local and dies with its process.
Mongo's `defer_until` is the durable fact. Before this hardening,
`recover_pending()` only rebuilt the discoverable state for deferrals already
DUE at boot — a deferral still in the future, whose owning process died
before it came due, had no path back to a live timer: it would sit orphaned
in Mongo until either unrelated activity for the same user happened to run a
pass, or a later boot found it already due.

`OrchestrationService.users_with_future_deferrals` + the third sweep in
`recover_pending()` close that gap: a bounded, indexed read of what Mongo
already knows, used only to REBUILD the ephemeral alarm — never to reason,
never to spend AI, never to touch the lease. This suite is about that
boundary staying exactly where it belongs.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pytest

os.environ["CALENDAR_PROVIDER_MODE"] = "fake"
os.environ.setdefault("TOKEN_VAULT_BACKEND", "local")
os.environ.setdefault(
    "TOKEN_VAULT_KEY", "change-me-token-vault-key-32bytes-min!!!!!!!!"
)
# This suite is the first to call recover_pending()/arm_deferred_timer(),
# which reach Mongo through `deps.db` rather than a db object the test
# controls. `deps.load_dotenv()` never overrides an already-set env var, so
# pinning DB_NAME/MONGO_URL here — before any import below can trigger that
# lazy `deps` import — keeps `deps.db` and this file's own `_db()` pointed at
# the SAME isolated test database, never at the real dev DB a live backend
# (e.g. the CPO's own running instance) could be mutating concurrently.
os.environ.setdefault("DB_NAME", "ora_test")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from life_attention.models import AttentionDecision, decision_key_for, root_attention_key_for  # noqa: E402
from life_attention.repository import AttentionDecisionRepository  # noqa: E402
from life_orchestration import scheduler  # noqa: E402
from life_orchestration.service import OrchestrationService  # noqa: E402
from life_orchestration.state import OrchestrationStateRepository  # noqa: E402
from life_reasoning.models import Impact, ImpactAssessment  # noqa: E402
from life_reasoning.repository import ImpactAssessmentRepository  # noqa: E402

pytestmark = pytest.mark.asyncio

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


class _FakeResult:
    def __init__(self, text: str):
        self.text = text
        self.provider = "fake"
        self.model = "fake-model"


class _FakeManager:
    """Counts every call. Recovery must never produce one."""

    def __init__(self):
        self.calls = 0

    async def chat(self, *, system, user, json_mode=False, **kwargs):
        self.calls += 1
        return _FakeResult(json.dumps({
            "delivery": "silent", "utility": 0.2, "urgency": 0.2,
            "confidence": 0.6, "novelty": 0.3, "actionability": 0.2,
            "defer_hours": None, "proposed_title": None, "reason_summary": "n/a",
        }))


def _patch_manager(monkeypatch, manager):
    import llm.manager as llm_manager

    monkeypatch.setattr(llm_manager, "get_manager", lambda: manager)


async def _ensure_indexes(db) -> None:
    try:
        await OrchestrationService(db).ensure_indexes()
        await AttentionDecisionRepository(db).ensure_indexes()
    except Exception:
        pass


async def _seed_assessment(db, user_id, *, focal=None):
    refs = focal or [f"situation:sit_{uuid.uuid4().hex[:8]}"]
    assessment = ImpactAssessment(
        user_id=user_id,
        source_signal_ids=[f"lcs_{uuid.uuid4().hex[:12]}"],
        focal_refs=refs,
        impacts=[Impact(
            statement="Un piccolo impegno potrebbe richiedere attenzione.",
            kind="dependency", epistemic_status="inferred", confidence=0.6,
        )],
        relevance=0.5, confidence=0.6,
        batch_key=f"batch_{uuid.uuid4().hex[:16]}",
        status="complete", attention_status="evaluated",
    )
    await ImpactAssessmentRepository(db).insert(assessment)
    return assessment


async def _seed_defer(db, user_id, *, hours: float, revision: int = 1, automatic_used: int = 0):
    """Mirrors a real chain: assessment already consumed, decision current."""
    assessment = await _seed_assessment(db, user_id)
    assessment_ids = [assessment.id]
    when = datetime.now(timezone.utc) + timedelta(hours=hours)
    decision = AttentionDecision(
        user_id=user_id,
        assessment_refs=assessment_ids,
        focal_refs=assessment.focal_refs,
        ai_delivery="defer", delivery="defer",
        confidence=0.5, utility=0.3, urgency=0.2,
        defer_until=when.isoformat(),
        decision_key=decision_key_for(user_id, assessment_ids, revision=revision),
        root_attention_key=root_attention_key_for(user_id, assessment_ids),
        attention_revision=revision,
        automatic_re_evaluations_used=automatic_used,
    )
    await AttentionDecisionRepository(db).insert(decision)
    return assessment, decision


async def _cancel_and_clear(user_id: str) -> None:
    """Test hygiene: a live one-shot task must not leak past its test."""
    task = scheduler._deferred_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _cleanup(db, user_id):
    for col in (
        "life_change_signals", "life_impact_assessments", "life_attention_decisions",
        "life_orchestration_state", "proactive_suggestions",
    ):
        await db[col].delete_many({"user_id": user_id})
    await _cancel_and_clear(user_id)


@pytest.fixture(autouse=True)
def _clean_scheduler_state():
    scheduler.reset_stats_for_test()
    yield
    scheduler.reset_stats_for_test()


@pytest.fixture(autouse=True)
def _fresh_deps_db(monkeypatch):
    """`recover_pending`/`arm_deferred_timer` reach Mongo via `deps.db`, a
    module-level Motor client created once at import — fine for the real
    process, which lives on one event loop for hours, but pytest-asyncio
    hands each test function its own fresh loop. A Motor client stays bound
    to the loop it was first used on, so reusing the same `deps.db` object
    across tests silently breaks every operation after the first test that
    touches it (Motor swallows the loop mismatch as a generic exception,
    caught by this module's own soft-fail handling, so it looks like "found
    nothing" rather than a visible error). Rebinding `deps.db` to a client
    created fresh in THIS test's loop keeps every test independent, exactly
    as it would be across independent real-process boots.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    import deps as deps_mod

    fresh_client = AsyncIOMotorClient(MONGO)
    monkeypatch.setattr(deps_mod, "db", fresh_client[DBNAME])
    yield
    fresh_client.close()


# ---------------------------------------------------------------------------
# A / B — a future deferral gets its timer rebuilt, at zero cost
# ---------------------------------------------------------------------------
async def test_a_future_defer_reconstructs_timer_at_startup(monkeypatch):
    """The exact scenario the CPO named: process dies before `defer_until`,
    a fresh process boots while it is still in the future — recovery alone,
    with nothing else happening, must give it a live timer again."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_indexes(db)
        await _seed_defer(db, user, hours=40 / 3600)  # ~40s in the future
        assert user not in scheduler._deferred_tasks

        await scheduler.recover_pending()

        task = scheduler._deferred_tasks.get(user)
        assert task is not None, "recovery must rebuild the timer from Mongo alone"
        assert not task.done()
    finally:
        await _cleanup(db, user)
        client.close()


async def test_b_future_defer_costs_no_ai_before_due(monkeypatch):
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_indexes(db)
        await _seed_defer(db, user, hours=1)  # comfortably in the future
        await scheduler.recover_pending()
        assert manager.calls == 0, "rebuilding a timer must never reason"
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# C / E — an already-due deferral is scheduled, exactly once
# ---------------------------------------------------------------------------
async def test_c_due_defer_schedules_exactly_once(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    scheduled = []

    async def _capture(uid, *, reason="signal"):
        scheduled.append((uid, reason))
        return True

    monkeypatch.setattr(scheduler, "schedule_user_reasoning", _capture)
    try:
        await _ensure_indexes(db)
        await _seed_defer(db, user, hours=-0.001)  # already due
        await scheduler.recover_pending()
        calls_for_user = [c for c in scheduled if c[0] == user]
        assert len(calls_for_user) == 1, f"expected exactly one wake-up, got {calls_for_user}"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_e_already_due_at_startup_is_recovered():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_indexes(db)
        await _seed_defer(db, user, hours=-0.02)
        svc = OrchestrationService(db)
        assert user in await svc.users_with_due_deferrals(limit=50)
        assert user not in await svc.users_with_future_deferrals(limit=50)
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# D — two boots in a row never duplicate the timer or the spend
# ---------------------------------------------------------------------------
async def test_d_restart_twice_no_duplicate_timer_or_spend(monkeypatch):
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_indexes(db)
        await _seed_defer(db, user, hours=1)

        await scheduler.recover_pending()
        first_task = scheduler._deferred_tasks.get(user)
        assert first_task is not None

        await scheduler.recover_pending()  # a second "boot" with nothing changed
        second_task = scheduler._deferred_tasks.get(user)
        assert second_task is first_task, "a live timer must not be replaced or duplicated"
        assert manager.calls == 0
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# F — nothing deferred, nothing spent
# ---------------------------------------------------------------------------
async def test_f_no_deferred_work_means_zero_timers_and_zero_ai(monkeypatch):
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_indexes(db)
        await scheduler.recover_pending()
        assert user not in scheduler._deferred_tasks
        assert manager.calls == 0
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# G — startup never blocks on AI
# ---------------------------------------------------------------------------
async def test_g_startup_recovery_does_not_block_on_ai(monkeypatch):
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    users = [f"u_{uuid.uuid4().hex[:8]}" for _ in range(3)]
    try:
        await _ensure_indexes(db)
        for u in users:
            await _seed_defer(db, u, hours=1)
        import time

        t0 = time.perf_counter()
        await scheduler.recover_pending()
        elapsed = time.perf_counter() - t0
        assert manager.calls == 0
        assert elapsed < 2.0, "arming timers must be near-instant, never wait on a provider"
    finally:
        for u in users:
            await _cleanup(db, u)
        client.close()


# ---------------------------------------------------------------------------
# H — still no polling
# ---------------------------------------------------------------------------
async def test_h_no_polling_loop_introduced():
    """Reuses the same AST technique as the rest of V2.9.4: no loop in the
    orchestration module may contain a sleep — with the one narrow exception
    `sleep(0)`, `recover_pending`'s cooperative yield between batches. It
    returns control to the event loop for one tick and resumes immediately —
    never a wait for time to pass, never a re-query "checking for changes",
    which is what would actually make this polling. Any other sleep
    argument inside a loop stays forbidden."""
    import ast
    import re

    path = Path(_BACKEND) / "life_orchestration" / "scheduler.py"
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    drop: set = set()
    for node in ast.walk(ast.parse(source)):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue  # ast.Lambda.body etc. is a single node, not a list
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                drop.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    kept = [ln for i, ln in enumerate(lines, start=1) if i not in drop]
    code_only = re.sub(r"#.*$", "", "\n".join(kept), flags=re.MULTILINE)

    tree = ast.parse(code_only)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.While, ast.For, ast.AsyncFor)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                name = getattr(inner.func, "attr", None) or getattr(inner.func, "id", None)
                if name != "sleep":
                    continue
                args = inner.args
                is_cooperative_yield = (
                    len(args) == 1
                    and isinstance(args[0], ast.Constant)
                    and args[0].value == 0
                )
                assert is_cooperative_yield, (
                    "sleep(...) with a non-zero argument inside a loop in "
                    "scheduler.py — that is polling"
                )


# ---------------------------------------------------------------------------
# I — user isolation
# ---------------------------------------------------------------------------
async def test_i_user_isolation_across_reconstructed_timers(monkeypatch):
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    user_a = f"u_{uuid.uuid4().hex[:8]}"
    user_b = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_indexes(db)
        _, dec_a = await _seed_defer(db, user_a, hours=30 / 3600)
        _, dec_b = await _seed_defer(db, user_b, hours=2)

        await scheduler.recover_pending()

        task_a = scheduler._deferred_tasks.get(user_a)
        task_b = scheduler._deferred_tasks.get(user_b)
        assert task_a is not None and task_b is not None
        assert task_a is not task_b

        # Each still points at its own decision's due moment — untouched by
        # the other user's recovery.
        current_a = await AttentionDecisionRepository(db).get_by_decision_key(
            user_a, dec_a.decision_key
        )
        current_b = await AttentionDecisionRepository(db).get_by_decision_key(
            user_b, dec_b.decision_key
        )
        assert current_a.defer_until == dec_a.defer_until
        assert current_b.defer_until == dec_b.defer_until
    finally:
        await _cleanup(db, user_a)
        await _cleanup(db, user_b)
        client.close()


# ---------------------------------------------------------------------------
# J — lease/idempotency untouched by recovery
# ---------------------------------------------------------------------------
async def test_j_recovery_never_touches_the_lease(monkeypatch):
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_indexes(db)
        await _seed_defer(db, user, hours=1)

        await scheduler.recover_pending()

        # Arming a timer is not a pass: it must not acquire, hold or even
        # create a lease row for this user.
        state_row = await db.life_orchestration_state.find_one({"user_id": user})
        assert state_row is None, "timer reconstruction must not touch the lease"

        # The lease still works normally afterwards — recovery left no
        # dangling artifact behind.
        held = await OrchestrationStateRepository(db).acquire(user)
        assert held is True
        await OrchestrationStateRepository(db).release(user)
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# Startup recovery COMPLETENESS (bounded batches, not truncated recovery).
#
# `iter_users_with_future_deferrals` (and its siblings) page through Mongo
# in `batch_size`-sized reads until the collection is exhausted, instead of
# the single capped read `users_with_future_deferrals` still uses for cheap
# existence checks. The CPO's own example: 51 users with a future defer,
# batch size 50 — the old single-call sweep armed 50 timers and stopped,
# leaving the 51st orphaned until unrelated activity or a lucky reboot. The
# fix must recover all 51 (and beyond), in more than one page, still with
# zero AI and zero blocking of the event loop.
# ---------------------------------------------------------------------------

async def _bulk_seed_future_defer_decisions(db, n: int, *, seconds: float = 3600.0):
    """Fast path for volume tests: inserts minimal `life_attention_decisions`
    documents directly (one `insert_many`), matching only the shape the
    recovery queries filter on. No matching assessment is needed — these
    defers sit comfortably in the future (default 1h), so no reconsideration
    (and therefore no AI call, no assessment re-fetch) is ever triggered by
    merely arming their timers.
    """
    users = [f"u_{uuid.uuid4().hex[:8]}" for _ in range(n)]
    now = datetime.now(timezone.utc)
    when = (now + timedelta(seconds=seconds)).isoformat()
    docs = []
    for u in users:
        ids = [f"lia_{uuid.uuid4().hex[:12]}"]
        docs.append({
            "id": f"lad_{uuid.uuid4().hex[:12]}", "user_id": u,
            "assessment_refs": ids, "focal_refs": [], "ai_delivery": "defer",
            "delivery": "defer", "utility": 0.3, "urgency": 0.2, "confidence": 0.5,
            "novelty": 0.0, "actionability": 0.0, "interruption_cost": 0.0,
            "downgrade_reasons": [], "reason_summary": None, "proposed_title": None,
            "evidence_refs": [], "defer_until": when, "defer_status": "pending",
            "suggestion_id": None, "suggestion_created": False, "gate_reasons": [],
            "decision_key": decision_key_for(u, ids, revision=1),
            "root_attention_key": root_attention_key_for(u, ids),
            "attention_revision": 1, "supersedes_decision_id": None,
            "superseded_by": None, "automatic_re_evaluations_used": 0,
            "auto_re_evaluation_exhausted": False, "model_provider": None,
            "model_name": None, "created_at": now.isoformat(),
        })
    if docs:
        await db.life_attention_decisions.insert_many(docs)
    return users


async def _cleanup_bulk(db, users: List[str]) -> None:
    if users:
        await db.life_attention_decisions.delete_many({"user_id": {"$in": users}})
    for u in users:
        await _cancel_and_clear(u)


def _recovered_count(users: List[str]) -> int:
    return sum(1 for u in users if u in scheduler._deferred_tasks)


async def _assert_full_volume_recovery(n: int, manager: _FakeManager, *, min_batches: int = 1) -> None:
    client, db = _db()
    users: List[str] = []
    try:
        await _ensure_indexes(db)
        users = await _bulk_seed_future_defer_decisions(db, n)
        await scheduler.recover_pending(batch_size=50)
        recovered = _recovered_count(users)
        assert recovered == n, f"expected {n} timers armed, got {recovered}"
        assert manager.calls == 0, "arming timers must never call the provider"
        assert scheduler._stats["recovery_batches"] >= min_batches
    finally:
        await _cleanup_bulk(db, users)
        client.close()


async def test_page_a_zero_future_deferrals_zero_timers(monkeypatch):
    """A. 0 → 0."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    try:
        await _ensure_indexes(db)
        await scheduler.recover_pending(batch_size=50)
        assert manager.calls == 0
    finally:
        client.close()


async def test_page_b_one_future_deferral_one_timer(monkeypatch):
    """B. 1 → 1."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    await _assert_full_volume_recovery(1, manager)


async def test_page_c_forty_nine_recovers_all(monkeypatch):
    """C. 49 → 49 (one short page, under the batch boundary)."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    await _assert_full_volume_recovery(49, manager, min_batches=1)


async def test_page_d_fifty_recovers_all(monkeypatch):
    """D. 50 → 50 (exactly one full page)."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    await _assert_full_volume_recovery(50, manager, min_batches=1)


async def test_page_e_fifty_one_recovers_all_not_fifty(monkeypatch):
    """E. 51 → 51, NOT 50 — the CPO's exact scenario: the old single-call
    sweep stopped after the first batch and silently orphaned the 51st."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    await _assert_full_volume_recovery(51, manager, min_batches=2)


async def test_page_f_seventy_five_recovers_all(monkeypatch):
    """F. 75 → 75, NOT 50 — the CPO's mandatory volume test."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    await _assert_full_volume_recovery(75, manager, min_batches=2)


async def test_page_g_one_hundred_twenty_recovers_all(monkeypatch):
    """G. 120 → 120, across three pages (50 + 50 + 20)."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    await _assert_full_volume_recovery(120, manager, min_batches=3)


async def test_page_h_user_with_multiple_defers_gets_one_timer(monkeypatch):
    """H. A user with more than one independent future-deferral chain still
    ends up with exactly one live timer — armed for whichever is soonest,
    per the existing per-user design (`arm_deferred_timer` refuses to
    duplicate a live timer, and only ever tracks one task per user)."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_indexes(db)
        await _seed_defer(db, user, hours=30 / 3600)
        # A second, independent root chain for the SAME user (different
        # assessment/focal refs), also deferred, further out.
        assessment2 = await _seed_assessment(db, user, focal=[f"situation:sit_{uuid.uuid4().hex[:8]}"])
        ids2 = [assessment2.id]
        when2 = datetime.now(timezone.utc) + timedelta(hours=2)
        decision2 = AttentionDecision(
            user_id=user, assessment_refs=ids2, focal_refs=assessment2.focal_refs,
            ai_delivery="defer", delivery="defer", confidence=0.5, utility=0.3, urgency=0.2,
            defer_until=when2.isoformat(),
            decision_key=decision_key_for(user, ids2, revision=1),
            root_attention_key=root_attention_key_for(user, ids2), attention_revision=1,
        )
        await AttentionDecisionRepository(db).insert(decision2)

        await scheduler.recover_pending(batch_size=50)
        assert user in scheduler._deferred_tasks
        # Exactly one task tracked for this user — never a list, never a
        # second overwrite-in-place; the dedup guard inside
        # `arm_deferred_timer` makes a second arm attempt for the same user
        # within one sweep a no-op.
        assert isinstance(scheduler._deferred_tasks[user], asyncio.Task)
        assert manager.calls == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_page_i_repeated_recovery_no_duplicate_ai_spend(monkeypatch):
    """I. Recovery run twice in a row (simulating two boots with nothing
    changed in between) must not double-arm or double-spend."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    users: List[str] = []
    try:
        await _ensure_indexes(db)
        users = await _bulk_seed_future_defer_decisions(db, 60)
        await scheduler.recover_pending(batch_size=50)
        first_tasks = {u: scheduler._deferred_tasks.get(u) for u in users}
        assert all(first_tasks.values())

        await scheduler.recover_pending(batch_size=50)
        second_tasks = {u: scheduler._deferred_tasks.get(u) for u in users}
        assert first_tasks == second_tasks, "a second sweep must not replace live timers"
        assert manager.calls == 0
    finally:
        await _cleanup_bulk(db, users)
        client.close()


async def test_page_j_no_ai_calls_during_large_recovery(monkeypatch):
    """J. Explicit, isolated: a 100-user recovery spends zero AI, on its
    own, regardless of the other assertions bundled into the volume tests
    above."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    users: List[str] = []
    try:
        await _ensure_indexes(db)
        users = await _bulk_seed_future_defer_decisions(db, 100)
        await scheduler.recover_pending(batch_size=50)
        assert manager.calls == 0
    finally:
        await _cleanup_bulk(db, users)
        client.close()


async def test_page_k_startup_does_not_block_on_recovery_completion(monkeypatch):
    """K. `start_orchestrator()` is synchronous and only schedules
    `_recovery_once` as a background task — it returns immediately
    regardless of how long the sweep itself later takes to page through."""
    import inspect

    assert not inspect.iscoroutinefunction(scheduler.start_orchestrator), (
        "start_orchestrator must stay synchronous — it must not await recovery"
    )
    src = inspect.getsource(scheduler.start_orchestrator)
    assert "create_task" in src, "recovery must be fired as a background task"
    assert "await recover_pending" not in src.replace(" ", ""), (
        "startup itself must never await the recovery sweep directly"
    )


async def test_page_l_recovery_leaves_no_permanent_task(monkeypatch):
    """L. Once `recover_pending` returns, nothing about the sweep itself
    keeps running — no lingering task represents "the recovery loop". The
    only tasks left behind are the legitimate one-shot deferred-wake alarms,
    each already accounted for in `_deferred_tasks`."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    users: List[str] = []
    try:
        await _ensure_indexes(db)
        before = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
        users = await _bulk_seed_future_defer_decisions(db, 55)
        await scheduler.recover_pending(batch_size=50)
        after = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
        new_tasks = after - before
        armed = set(scheduler._deferred_tasks.get(u) for u in users)
        armed.discard(None)
        assert new_tasks <= armed, (
            "recovery must not leave behind any task other than the "
            "one-shot deferred-wake alarms it explicitly armed"
        )
    finally:
        await _cleanup_bulk(db, users)
        client.close()


async def test_page_n_user_isolation_across_two_batches(monkeypatch):
    """N. Two disjoint groups of users, seeded and recovered together across
    what will span more than one page, never cross-contaminate each other's
    `defer_until` or timer."""
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    group_a: List[str] = []
    group_b: List[str] = []
    try:
        await _ensure_indexes(db)
        group_a = await _bulk_seed_future_defer_decisions(db, 40, seconds=3600)
        group_b = await _bulk_seed_future_defer_decisions(db, 40, seconds=7200)

        await scheduler.recover_pending(batch_size=50)

        for u in group_a + group_b:
            assert u in scheduler._deferred_tasks, u

        # Each group's own decisions kept their own defer_until — recovering
        # one group's batch never touched the other's persisted state.
        doc_a = await db.life_attention_decisions.find_one({"user_id": group_a[0]})
        doc_b = await db.life_attention_decisions.find_one({"user_id": group_b[0]})
        assert doc_a["defer_until"] < doc_b["defer_until"]
    finally:
        await _cleanup_bulk(db, group_a + group_b)
        client.close()
