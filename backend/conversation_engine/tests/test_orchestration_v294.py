"""V2.9.4 — Continuous Life Reasoning orchestration (deterministic, A-Z).

Real MongoDB test DB throughout. Both AI layers are stubbed via the Provider
Manager so the full pipeline runs end to end without consuming quota.

The assertions that matter most here are about COST and DURABILITY: that an
idle system spends nothing, that a burst coalesces instead of multiplying, and
that no in-process loss can destroy work Mongo already holds.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ["CALENDAR_PROVIDER_MODE"] = "fake"
os.environ.setdefault("TOKEN_VAULT_BACKEND", "local")
os.environ.setdefault(
    "TOKEN_VAULT_KEY", "change-me-token-vault-key-32bytes-min!!!!!!!!"
)

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from life_attention.models import AttentionDecision, decision_key_for  # noqa: E402
from life_attention.repository import AttentionDecisionRepository  # noqa: E402
from life_orchestration import scheduler  # noqa: E402
from life_orchestration.service import MAX_CYCLES, OrchestrationService  # noqa: E402
from life_orchestration.state import OrchestrationStateRepository  # noqa: E402
from life_reasoning.repository import ImpactAssessmentRepository  # noqa: E402
from life_signals.service import LifeSignalService  # noqa: E402

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
    """Answers both the impact and the attention prompt, counting calls so a
    test can assert exactly what a mutation cost."""

    def __init__(self, *, impact=None, attention=None, raises=None):
        self._impact = impact or {
            "impacts": [{
                "statement": "Potrebbe servire una preparazione non ancora pianificata.",
                "kind": "dependency", "epistemic_status": "tentative",
                "confidence": 0.5, "temporal_horizon": "near_term",
            }],
            "relevance": 0.6, "confidence": 0.5,
            "requires_more_context": False, "next_step_kind": "gather_context",
            "reason_summary": "Un cambiamento con dipendenze aperte.",
        }
        self._attention = attention or {
            "delivery": "silent", "utility": 0.2, "urgency": 0.2,
            "confidence": 0.6, "novelty": 0.5, "actionability": 0.3,
            "defer_hours": None, "proposed_title": None,
            "reason_summary": "Non serve disturbare.",
        }
        self._raises = raises
        self.impact_calls = 0
        self.attention_calls = 0

    @property
    def calls(self) -> int:
        return self.impact_calls + self.attention_calls

    async def chat(self, *, system, user, json_mode=False, **kwargs):
        if self._raises:
            raise self._raises
        if "impact-reasoning" in system:
            self.impact_calls += 1
            return _FakeResult(json.dumps(self._impact))
        self.attention_calls += 1
        return _FakeResult(json.dumps(self._attention))


def _patch_manager(monkeypatch, manager):
    import llm.manager as llm_manager

    monkeypatch.setattr(llm_manager, "get_manager", lambda: manager)


@pytest.fixture(autouse=True)
def _clean_scheduler_state():
    """Counters and coalescing sets are module-level; reset between cases."""
    scheduler.reset_stats_for_test()
    yield
    scheduler.reset_stats_for_test()


async def _ensure_lease_index(db) -> None:
    """Create the orchestration indexes in the DB this suite actually resolves
    to, for the tests that depend on them.

    `DBNAME` is read at import time, but importing the pipeline transitively
    imports `deps`, which calls `load_dotenv()` and sets `DB_NAME` — so the
    suite can run against the configured database rather than the default.
    The lease's concurrent-create race is index-backed, so creating it here is
    what makes these assertions exercise production behaviour instead of an
    accidentally index-less collection. Same inline pattern the V2.9.2/V2.9.3
    idempotency tests already use.
    """
    try:
        await OrchestrationService(db).ensure_indexes()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _freeze_local_hour(monkeypatch):
    """Pin the attention layer's clock to a free afternoon hour so the gate
    does not downgrade purely because the suite happens to run at night."""
    import life_attention.context as ctx_mod

    async def _fixed(db, user_id):
        return datetime.now(timezone.utc), "Europe/Rome", 15

    monkeypatch.setattr(ctx_mod, "resolve_local_time", _fixed)


async def _emit_signal(db, user_id, *, ref=None):
    return await LifeSignalService(db).emit(
        user_id=user_id,
        source_ref=ref or f"situation:sit_{uuid.uuid4().hex[:8]}",
        source_system="situation", change_kind="created",
        dedupe_key=f"situation:{uuid.uuid4().hex[:12]}",
    )


async def _cleanup(db, user_id):
    for col in (
        "life_change_signals", "life_impact_assessments", "life_attention_decisions",
        "life_orchestration_state", "proactive_suggestions", "proactive_learning",
        "situations", "memories", "context_edges", "calendar_event_drafts",
        "life_os_plans",
    ):
        await db[col].delete_many({"user_id": user_id})


# ---------------------------------------------------------------------------
# A / B / C / D — the wake-up model
# ---------------------------------------------------------------------------
async def test_a_signal_emission_schedules_user_processing(monkeypatch):
    """Emitting a signal asks for a pass — without running one inline."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    scheduled = []

    async def _capture(uid, *, reason="signal"):
        scheduled.append((uid, reason))
        return True

    import conversation_engine.ai_core.loop as loop_mod
    import life_orchestration.scheduler as sched_mod

    monkeypatch.setattr(sched_mod, "schedule_user_reasoning", _capture)
    try:
        trace = {}
        await loop_mod._emit_life_change(
            trace, "situation",
            lambda: _emit_signal(db, user),
            user_id=user,
        )
        assert trace.get("life_change_signals") == 1
        assert scheduled == [(user, "signal")]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_a2_no_signal_means_no_wakeup(monkeypatch):
    """The event-driven guarantee at its source: an emission that produces
    nothing must not ask for a pass."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    scheduled = []

    async def _capture(uid, *, reason="signal"):
        scheduled.append(uid)
        return True

    import conversation_engine.ai_core.loop as loop_mod
    import life_orchestration.scheduler as sched_mod

    monkeypatch.setattr(sched_mod, "schedule_user_reasoning", _capture)
    try:
        trace = {}
        # Emitter returns None — no signal was written.
        await loop_mod._emit_life_change(trace, "situation", lambda: _noop(), user_id=user)
        assert "life_change_signals" not in trace
        assert scheduled == []
    finally:
        await _cleanup(db, user)
        client.close()


async def _noop():
    return None


async def test_b_scheduling_does_not_block_the_mutation(monkeypatch):
    """The request path must never wait on reasoning. Even with a scheduler
    that would take a second, the emission returns immediately."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    import conversation_engine.ai_core.loop as loop_mod
    import life_orchestration.scheduler as sched_mod

    slow_ran = {"v": False}

    async def _slow(uid, *, reason="signal"):
        # Simulates a scheduler that hands off to a background task rather
        # than doing work inline. The real one is put_nowait.
        async def _bg():
            await asyncio.sleep(0.3)
            slow_ran["v"] = True

        asyncio.get_running_loop().create_task(_bg())
        return True

    monkeypatch.setattr(sched_mod, "schedule_user_reasoning", _slow)
    try:
        import time

        t0 = time.perf_counter()
        await loop_mod._emit_life_change(
            {}, "situation", lambda: _emit_signal(db, user), user_id=user,
        )
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.25, f"mutation waited {elapsed:.3f}s on the pipeline"
        assert slow_ran["v"] is False, "reasoning ran inline instead of in background"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_c_rapid_signals_same_user_coalesce_to_one_pass():
    """Five near-simultaneous mutations must not become five pipelines."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        results = [await scheduler.schedule_user_reasoning(user) for _ in range(5)]
        assert results[0] is True
        assert all(r is False for r in results[1:]), "burst was not coalesced"
        stats = scheduler.orchestrator_stats()
        assert stats["wakeups_requested"] == 5
        assert stats["wakeups_coalesced"] == 4
        assert stats["users_scheduled"] == 1
    finally:
        scheduler._scheduled.discard(user)
        await _cleanup(db, user)
        client.close()


async def test_d_different_users_get_independent_passes():
    client, db = _db()
    users = [f"u_{uuid.uuid4().hex[:8]}" for _ in range(3)]
    try:
        for u in users:
            assert await scheduler.schedule_user_reasoning(u) is True
        assert scheduler.orchestrator_stats()["users_scheduled"] == 3
    finally:
        for u in users:
            scheduler._scheduled.discard(u)
            await _cleanup(db, u)
        client.close()


# ---------------------------------------------------------------------------
# E / F — the pass itself
# ---------------------------------------------------------------------------
async def test_e_pass_runs_impact_then_attention(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        await _emit_signal(db, user)
        report = await OrchestrationService(db).run_user_pass(user)

        assert report.ran is True
        assert report.impact_runs == 1
        assert report.attention_runs == 1
        assert manager.impact_calls == 1
        assert manager.attention_calls == 1
        # The whole chain completed: signal consumed, assessment evaluated.
        assert await LifeSignalService(db).list_pending(user) == []
        assert await ImpactAssessmentRepository(db).list_awaiting_attention(user) == []
        assert await db.life_attention_decisions.count_documents({"user_id": user}) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_f_no_pending_work_costs_zero_ai_calls(monkeypatch):
    """The cost principle: an idle user is free."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.ran is False
        assert report.ai_calls == 0
        assert manager.calls == 0
        assert report.impact_runs == 0 and report.attention_runs == 0
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# G / H / I — failure isolation
# ---------------------------------------------------------------------------
async def test_g_impact_failure_does_not_fabricate_attention(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    from llm.errors import LLMProviderUnavailable

    manager = _FakeManager(raises=LLMProviderUnavailable([
        {"provider": "gemini", "failure_kind": "quota", "retryable": True},
    ]))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit_signal(db, user)
        report = await OrchestrationService(db).run_user_pass(user)

        assert report.impact_runs == 1
        # No assessment exists, so attention was never invited to reason
        # about one that does not exist.
        assert report.attention_runs == 0
        assert await db.life_attention_decisions.count_documents({"user_id": user}) == 0
        # The signal is not lost.
        assert len(await LifeSignalService(db).list_pending(user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_h_attention_failure_leaves_assessment_recoverable(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"

    class _ImpactOnly(_FakeManager):
        async def chat(self, *, system, user, json_mode=False, **kwargs):
            if "impact-reasoning" in system:
                self.impact_calls += 1
                return _FakeResult(json.dumps(self._impact))
            self.attention_calls += 1
            raise RuntimeError("attention provider down")

    manager = _ImpactOnly()
    _patch_manager(monkeypatch, manager)
    try:
        await _emit_signal(db, user)
        await OrchestrationService(db).run_user_pass(user)

        # Impact succeeded and consumed its signal...
        assert await LifeSignalService(db).list_pending(user) == []
        assert await db.life_impact_assessments.count_documents({"user_id": user}) == 1
        # ...attention failed, so the assessment stays recoverable.
        pending = await ImpactAssessmentRepository(db).list_awaiting_attention(user)
        assert len(pending) == 1
        assert await db.life_attention_decisions.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_i_provider_failure_records_retryable_backoff(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    from llm.errors import LLMProviderUnavailable

    manager = _FakeManager(raises=LLMProviderUnavailable([
        {"provider": "gemini", "failure_kind": "quota", "retryable": True},
    ]))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit_signal(db, user)
        state = OrchestrationStateRepository(db)

        report = await OrchestrationService(db).run_user_pass(user)
        assert report.failures
        assert await state.backoff_active(user) is True

        # A second pass is skipped rather than hammering the provider...
        second = await OrchestrationService(db).run_user_pass(user)
        assert second.skipped_reason == "backoff_active"
        assert second.ai_calls == 0
        # ...and the work is still there when the backoff elapses.
        assert len(await LifeSignalService(db).list_pending(user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_i2_success_clears_backoff(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        state = OrchestrationStateRepository(db)
        await state.record_failure(user, reason="test")
        assert await state.backoff_active(user) is True

        await _emit_signal(db, user)
        await OrchestrationService(db).run_user_pass(user, respect_backoff=False)
        assert await state.backoff_active(user) is False
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# J / K — lease
# ---------------------------------------------------------------------------
async def test_j_concurrent_passes_do_not_double_spend(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        await _ensure_lease_index(db)
        await _emit_signal(db, user)
        svc = OrchestrationService(db)
        first, second = await asyncio.gather(
            svc.run_user_pass(user), svc.run_user_pass(user)
        )
        ran = [r for r in (first, second) if r.ran]
        blocked = [r for r in (first, second) if r.skipped_reason == "lease_held"]
        assert len(ran) == 1, "both passes ran — the lease did not hold"
        assert len(blocked) == 1
        # Exactly one pipeline's worth of AI spend.
        assert manager.impact_calls == 1
        assert manager.attention_calls == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_k_expired_lease_is_reclaimable():
    """A process that died mid-pass must not block the user forever."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_lease_index(db)
        state = OrchestrationStateRepository(db)
        assert await state.acquire(user) is True
        # A second acquire while live is refused...
        assert await state.acquire(user) is False
        # ...but an expired lease (simulating a crash) is reclaimable.
        await db.life_orchestration_state.update_one(
            {"user_id": user},
            {"$set": {"lease_until": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()}},
        )
        assert await state.acquire(user) is True
    finally:
        await _cleanup(db, user)
        client.close()


async def test_k2_release_only_affects_own_lease():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _ensure_lease_index(db)
        state = OrchestrationStateRepository(db)
        await state.acquire(user)
        # Another process owns it now.
        await db.life_orchestration_state.update_one(
            {"user_id": user}, {"$set": {"lease_owner": "proc_someone_else"}},
        )
        await state.release(user)
        doc = await db.life_orchestration_state.find_one({"user_id": user}, {"_id": 0})
        assert doc["lease_until"] is not None, "released a lease we did not own"
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# L / Q — durability
# ---------------------------------------------------------------------------
async def test_l_lost_local_schedule_still_recoverable(monkeypatch):
    """The durability principle: an in-process wake-up is an accelerator, not
    the queue of record."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        # Signal persisted, but the local schedule "fails" (no loop / dropped).
        await _emit_signal(db, user)
        assert len(await LifeSignalService(db).list_pending(user)) == 1

        # Startup recovery finds it purely from Mongo.
        users = await OrchestrationService(db).users_with_pending_work(limit=50)
        assert user in users

        # And a manual pass still processes it.
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.ran is True
        assert await LifeSignalService(db).list_pending(user) == []
    finally:
        await _cleanup(db, user)
        client.close()


async def test_q_signal_arriving_during_pass_is_not_lost(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        # Simulate the user being mid-pass when a new change arrives.
        scheduler._active.add(user)
        queued = await scheduler.schedule_user_reasoning(user)
        assert queued is False, "should coalesce into a redo, not a second pass"
        assert user in scheduler._redo, "the change was dropped instead of deferred"

        scheduler._active.discard(user)
        # Independently of the in-process flag, the signal itself is durable.
        await _emit_signal(db, user)
        assert len(await LifeSignalService(db).list_pending(user)) == 1
    finally:
        scheduler._redo.discard(user)
        scheduler._active.discard(user)
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# M / N / O — deferred decisions
# ---------------------------------------------------------------------------
async def _seed_deferred(db, user_id, *, hours: float):
    when = datetime.now(timezone.utc) + timedelta(hours=hours)
    decision = AttentionDecision(
        user_id=user_id,
        assessment_refs=[f"lia_{uuid.uuid4().hex[:12]}"],
        focal_refs=[f"situation:sit_{uuid.uuid4().hex[:8]}"],
        ai_delivery="defer", delivery="defer",
        defer_until=when.isoformat(),
        decision_key=decision_key_for(user_id, [uuid.uuid4().hex]),
    )
    await AttentionDecisionRepository(db).insert(decision)
    return decision


async def test_m_deferred_before_due_is_not_processed():
    """A deferral in the future is invisible to the orchestrator: no pass is
    worth waking for it, and it costs zero AI calls (V2.9.4 hardening)."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _seed_deferred(db, user, hours=6)
        svc = OrchestrationService(db)
        assert await svc.has_due_deferral(user) is False
        row = await db.life_attention_decisions.find_one({"user_id": user}, {"_id": 0})
        assert row["defer_status"] == "pending"
        # ...and it is not in the recovery set either.
        assert user not in await svc.users_with_due_deferrals(limit=50)
    finally:
        await _cleanup(db, user)
        client.close()


async def test_n_deferred_after_due_becomes_eligible():
    """A deferral whose moment has passed becomes visible to the existence
    check the scheduler uses to decide whether to wake a pass.

    The check itself is read-only (V2.9.4 hardening): unlike the old
    flag-marking behaviour, merely detecting a due deferral must not consume
    it or spend an AI call — only `AttentionService.reevaluate_due_deferrals`,
    run inside a leased pass, may actually reconsider it.
    """
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _seed_deferred(db, user, hours=-1)  # its moment has passed
        svc = OrchestrationService(db)
        assert await svc.has_due_deferral(user) is True
        # Read-only: checking again changes nothing and still finds it.
        assert await svc.has_due_deferral(user) is True
        row = await db.life_attention_decisions.find_one({"user_id": user}, {"_id": 0})
        assert row["defer_status"] == "pending"
        assert row["superseded_by"] is None
    finally:
        await _cleanup(db, user)
        client.close()


async def test_o_lost_timer_still_recovered_from_mongo():
    """A process-local timer dying must not strand a deferral."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _seed_deferred(db, user, hours=-2)
        # No timer ever fired; recovery finds it from persisted state alone.
        users = await OrchestrationService(db).users_with_due_deferrals(limit=50)
        assert user in users
    finally:
        await _cleanup(db, user)
        client.close()


async def test_o2_earliest_pending_defer_drives_one_shot_timer():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _seed_deferred(db, user, hours=10)
        await _seed_deferred(db, user, hours=2)
        when = await OrchestrationService(db).next_deferral_due_at(user)
        assert when is not None
        delta = datetime.fromisoformat(when) - datetime.now(timezone.utc)
        # The soonest one, so a single alarm suffices.
        assert timedelta(hours=1) < delta < timedelta(hours=3)
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# P — cycle bounds
# ---------------------------------------------------------------------------
async def test_p_hard_cycle_cap_respected(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        # More signals than one pass can drain, so the cap is what stops it.
        for _ in range(15):
            await _emit_signal(db, user)
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.cycles <= MAX_CYCLES
        assert report.impact_runs <= MAX_CYCLES
        assert report.attention_runs <= MAX_CYCLES
        # Whatever is left stays pending rather than being drained in a loop.
        assert len(await LifeSignalService(db).list_pending(user)) > 0
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# R / S / T — no self-trigger recursion
# ---------------------------------------------------------------------------
async def test_rst_pipeline_output_never_emits_new_signals(monkeypatch):
    """The recursion guard: nothing the pipeline produces may feed it again."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(attention={
        "delivery": "home", "utility": 0.95, "urgency": 0.95, "confidence": 0.95,
        "novelty": 0.9, "actionability": 0.9, "defer_hours": None,
        "proposed_title": "Qualcosa da rivedere",
        "reason_summary": "Vale uno sguardo.",
    })
    _patch_manager(monkeypatch, manager)
    try:
        await _emit_signal(db, user)
        await OrchestrationService(db).run_user_pass(user)

        # The pass produced real downstream records...
        assert await db.life_impact_assessments.count_documents({"user_id": user}) == 1
        assert await db.life_attention_decisions.count_documents({"user_id": user}) == 1
        # ...and consumed the only signal, creating none.
        signals = await db.life_change_signals.find(
            {"user_id": user}, {"_id": 0, "status": 1},
        ).to_list(50)
        assert len(signals) == 1, "the pipeline fed itself a new signal"
        assert signals[0]["status"] == "processed"
        assert await LifeSignalService(db).list_pending(user) == []
    finally:
        await _cleanup(db, user)
        client.close()


async def test_r2_suggestion_creation_emits_no_signal(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        from proactive_engine.dedupe import make_dedupe_key, window_label
        from proactive_engine.models import SuggestionCandidate
        from proactive_engine.service import ProactiveEngineService

        created, _ = await ProactiveEngineService(db).submit_candidates(user, [
            SuggestionCandidate(
                title="Voce di prova", reason="Motivo di prova",
                type="generic", source="life_reasoning",
                dedupe_key=make_dedupe_key(
                    suggestion_type="generic", source="life_reasoning",
                    entity_id="situation:sit_demo", window=window_label(),
                ),
                importance_hint=0.95, urgency_hint=0.95, confidence=0.95,
                quality_hint=0.9,
            ),
        ])
        assert len(created) == 1
        # Creating a user-facing item is not a life change.
        assert await db.life_change_signals.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# U / V — isolation and hot-path discipline
# ---------------------------------------------------------------------------
async def test_u_user_isolation(monkeypatch):
    client, db = _db()
    user_a = f"u_{uuid.uuid4().hex[:8]}"
    user_b = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        await _emit_signal(db, user_a)
        svc = OrchestrationService(db)

        report_b = await svc.run_user_pass(user_b)
        assert report_b.ran is False and report_b.ai_calls == 0

        await svc.run_user_pass(user_a)
        assert await db.life_attention_decisions.count_documents({"user_id": user_b}) == 0
        assert await db.life_impact_assessments.count_documents({"user_id": user_b}) == 0
        # A's lease never touched B.
        assert await db.life_orchestration_state.count_documents({"user_id": user_b}) == 0
    finally:
        await _cleanup(db, user_a)
        await _cleanup(db, user_b)
        client.close()


async def test_v_hot_path_queries_are_user_scoped_and_bounded():
    """The per-pass path never scans a collection; only the once-per-boot
    recovery reads across users, and it is capped."""
    import inspect

    from life_orchestration import service as svc_mod

    src = inspect.getsource(svc_mod.OrchestrationService._run_cycles)
    src += inspect.getsource(svc_mod.OrchestrationService._has_pending_assessment)
    # The hot path delegates to user-scoped services only.
    assert "find(" not in src, "hot path queries the collection directly"

    recovery = inspect.getsource(svc_mod.OrchestrationService.users_with_pending_work)
    assert ".limit(" in recovery, "recovery read is unbounded"


# ---------------------------------------------------------------------------
# Scale / cost properties
# ---------------------------------------------------------------------------
async def test_scale_burst_same_user_is_coalesced():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        accepted = 0
        for _ in range(20):
            if await scheduler.schedule_user_reasoning(user):
                accepted += 1
        assert accepted == 1, "a 20-mutation burst produced more than one pass"
        stats = scheduler.orchestrator_stats()
        assert stats["wakeups_coalesced"] == 19
        assert stats["coalesce_ratio"] > 0.9
    finally:
        scheduler._scheduled.discard(user)
        await _cleanup(db, user)
        client.close()


async def test_scale_twenty_signals_across_ten_users():
    client, db = _db()
    users = [f"u_{uuid.uuid4().hex[:8]}" for _ in range(10)]
    try:
        accepted = 0
        for _ in range(2):
            for u in users:
                if await scheduler.schedule_user_reasoning(u):
                    accepted += 1
        # One pass per user, not per mutation.
        assert accepted == 10
        stats = scheduler.orchestrator_stats()
        assert stats["wakeups_requested"] == 20
        assert stats["wakeups_coalesced"] == 10
        assert stats["users_scheduled"] == 10
    finally:
        for u in users:
            scheduler._scheduled.discard(u)
            await _cleanup(db, u)
        client.close()


async def test_cost_correlated_signals_stay_within_budget(monkeypatch):
    """Five correlated changes must cost one pipeline, not five."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        shared = f"situation:sit_{uuid.uuid4().hex[:8]}"
        for _ in range(5):
            await _emit_signal(db, user, ref=shared)

        report = await OrchestrationService(db).run_user_pass(user)
        # V2.9.2 batches correlated signals into one reasoning call, V2.9.3
        # batches the resulting assessments into one attention call.
        assert manager.impact_calls == 1
        assert manager.attention_calls == 1
        assert report.ai_calls == 2
    finally:
        await _cleanup(db, user)
        client.close()


async def test_cost_deferred_not_due_costs_nothing(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_deferred(db, user, hours=6)
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.ran is False
        assert manager.calls == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_silent_pipeline_creates_no_home_item(monkeypatch):
    """Autonomy is not chattiness: a trivial change must reach `silent` and
    surface nothing."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()  # default attention output is silent
    _patch_manager(monkeypatch, manager)
    try:
        await _emit_signal(db, user)
        report = await OrchestrationService(db).run_user_pass(user)

        assert report.silent == 1
        assert report.suggestions_created == 0
        assert await db.proactive_suggestions.count_documents({"user_id": user}) == 0
        # The decision itself is still recorded and auditable.
        row = await db.life_attention_decisions.find_one({"user_id": user}, {"_id": 0})
        assert row["delivery"] == "silent"
    finally:
        await _cleanup(db, user)
        client.close()


@pytest.mark.parametrize(
    "summary_ref",
    [
        "situation:sit_mostra",
        "situation:sit_bonsai",
        "plan:plan_festa",
    ],
)
async def test_generality_arbitrary_domains_take_the_same_path(monkeypatch, summary_ref):
    """Unanticipated life areas traverse the identical orchestration path."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        await _emit_signal(db, user, ref=summary_ref)
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.impact_runs == 1 and report.attention_runs == 1
        assert manager.impact_calls == 1 and manager.attention_calls == 1
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# W / X / Y / Z — static guarantees
# ---------------------------------------------------------------------------
_PRODUCTION_FILES = [
    Path(_BACKEND) / "life_orchestration" / "scheduler.py",
    Path(_BACKEND) / "life_orchestration" / "service.py",
    Path(_BACKEND) / "life_orchestration" / "state.py",
]

_FORBIDDEN_DOMAIN_TERMS = (
    "house", "mortgage", "mutuo", "notaio", "notary", "insurance", "travel",
    "study", "medical", "car", "bonsai", "party", "exhibition", "mostra",
    "festa",
)


def _code_only(path: Path) -> str:
    """Source with docstrings and comments removed — the audit judges code,
    not documentation that states the rule."""
    import ast
    import re as _re

    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    drop: set = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                drop.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    kept = [ln for i, ln in enumerate(lines, start=1) if i not in drop]
    return _re.sub(r"#.*$", "", "\n".join(kept), flags=_re.MULTILINE)


async def test_w_no_polling_loop_in_production_code():
    """The structural difference between event-driven and polling: no loop in
    this module may contain a sleep — with one narrow, explicit exception.

    `asyncio.sleep(0)` is a cooperative yield, not a wait: it returns control
    to the event loop for one tick and resumes immediately, used by
    `recover_pending`'s batch-paged startup walk so a large backlog cannot
    monopolize the loop. That is structurally nothing like polling — it
    never waits for time to pass, never re-queries to "check for changes".
    Any OTHER sleep argument inside a loop (a duration, a variable, a
    computed backoff) stays exactly what it always meant here: polling.
    """
    import ast

    for path in _PRODUCTION_FILES:
        tree = ast.parse(_code_only(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.While, ast.For, ast.AsyncFor)):
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    target = inner.func
                    name = getattr(target, "attr", None) or getattr(target, "id", None)
                    if name != "sleep":
                        continue
                    args = inner.args
                    is_cooperative_yield = (
                        len(args) == 1
                        and isinstance(args[0], ast.Constant)
                        and args[0].value == 0
                    )
                    assert is_cooperative_yield, (
                        f"sleep({ast.dump(inner.args[0]) if inner.args else ''}) "
                        f"inside a loop in {path.name} — that is polling"
                    )


async def test_x_no_cron_or_external_scheduler():
    for path in _PRODUCTION_FILES:
        code = _code_only(path).lower()
        for term in ("crontab", "apscheduler", "celery", "schedule.every", "cron("):
            assert term not in code, f"{term} introduced in {path.name}"


async def test_y_no_new_external_calls_outside_provider_manager():
    import re

    vendor = re.compile(
        r"(?:^|\s)(?:import|from)\s+\S*\b(?:google|genai|openai|anthropic|ollama|"
        r"httpx|aiohttp|requests)\b|GenerativeModel|generativelanguage",
        re.MULTILINE,
    )
    for path in _PRODUCTION_FILES:
        code = _code_only(path)
        assert not vendor.search(code), f"external call surface in {path.name}"
        # The orchestrator never calls a provider itself — the layers it
        # coordinates already do, through the Provider Manager.
        assert "get_manager" not in code, f"{path.name} calls a provider directly"


async def test_z_no_domain_router_in_production_code():
    import re

    for path in _PRODUCTION_FILES:
        code = _code_only(path).lower()
        for term in _FORBIDDEN_DOMAIN_TERMS:
            assert not re.search(rf"\b{re.escape(term)}\b", code), (
                f"{term} leaked into executable code of {path.name}"
            )


async def test_z2_no_push_dispatch_or_tool_execution():
    for path in _PRODUCTION_FILES:
        code = _code_only(path).lower()
        for term in ("send_push", "fcm", "apns", "sendgrid", "smtp",
                     "tools.execute", "toolregistry"):
            assert term not in code, f"{term} introduced in {path.name}"


async def test_z3_scheduler_state_holds_no_user_content():
    """The in-process coordinator keeps ids and counters — never context."""
    assert all(isinstance(u, str) for u in scheduler._scheduled)
    assert all(isinstance(u, str) for u in scheduler._active)
    stats = scheduler.orchestrator_stats()
    for key, value in stats.items():
        assert isinstance(value, (int, float, str, bool)), f"{key} holds a structure"
