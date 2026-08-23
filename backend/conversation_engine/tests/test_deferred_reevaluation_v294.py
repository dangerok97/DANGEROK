"""V2.9.4 — DEFERRED RE-EVALUATION FINAL HARDENING (deterministic, A-Z).

Closes the open point left by V2.9.4's first phase: a `defer` decision whose
moment arrives is now genuinely RECONSIDERED by the AI, not merely flagged.

    existing ImpactAssessment(s) → deferred AttentionDecision revision N
        → defer_until reached → refreshed operational context
        → NEW attention call → deterministic system gate → revision N+1

The load-bearing property under test throughout is "AI DECIDES. SYSTEM
GUARANTEES.": the system may only bound COST (one call per due chain, a hard
cap on automatic reconsiderations, a lease against concurrent double-spend)
and apply the identical V2.9.3 gate — it never manufactures a verdict like
"deferred three times, therefore silent", and exhausting the automatic budget
must never look like the AI changed its mind.

Real MongoDB test DB throughout. The Provider Manager is stubbed so the full
chain runs end to end without consuming quota.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import re
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

from life_attention import service as attention_service  # noqa: E402
from life_attention.models import (  # noqa: E402
    MAX_AUTOMATIC_DEFER_REEVALUATIONS,
    AttentionDecision,
    decision_key_for,
    root_attention_key_for,
)
from life_attention.repository import (  # noqa: E402
    AttentionDecisionRepository,
    DuplicateDecision,
)
from life_attention.service import AttentionService  # noqa: E402
from life_orchestration.service import OrchestrationService  # noqa: E402
from life_orchestration.state import OrchestrationStateRepository  # noqa: E402
from life_reasoning.models import Impact, ImpactAssessment  # noqa: E402
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
    """Answers both the impact and the attention prompt, counting each kind
    separately — the load-bearing assertion in this suite is often "zero
    Impact Reasoning calls", which requires telling the two apart."""

    def __init__(self, attention=None, *, raises=None, text=None):
        self._attention = attention or {
            "delivery": "defer", "utility": 0.5, "urgency": 0.4,
            "confidence": 0.7, "novelty": 0.5, "actionability": 0.4,
            "defer_hours": 6, "proposed_title": None,
            "reason_summary": "Ancora presto per disturbare.",
        }
        self._raises = raises
        self._text = text  # when set, returned verbatim (garbage-output tests)
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
            return _FakeResult(json.dumps({
                "impacts": [], "relevance": 0.5, "confidence": 0.5,
                "requires_more_context": False, "next_step_kind": "gather_context",
                "reason_summary": "n/a",
            }))
        self.attention_calls += 1
        if self._text is not None:
            return _FakeResult(self._text)
        return _FakeResult(json.dumps(self._attention))


def _patch_manager(monkeypatch, manager):
    import llm.manager as llm_manager

    monkeypatch.setattr(llm_manager, "get_manager", lambda: manager)


@pytest.fixture(autouse=True)
def _freeze_local_hour(monkeypatch):
    """Pin the attention layer's clock to a free afternoon hour, exactly like
    the V2.9.3/V2.9.4 suites, so the gate does not downgrade purely because of
    when this suite happens to run."""
    import life_attention.context as ctx_mod

    async def _fixed(db, user_id):
        return datetime.now(timezone.utc), "Europe/Rome", 15

    monkeypatch.setattr(ctx_mod, "resolve_local_time", _fixed)


async def _seed_assessment(db, user_id, *, focal=None):
    refs = focal or [f"situation:sit_{uuid.uuid4().hex[:8]}"]
    assessment = ImpactAssessment(
        user_id=user_id,
        source_signal_ids=[f"lcs_{uuid.uuid4().hex[:12]}"],
        focal_refs=refs,
        impacts=[Impact(
            statement="Potrebbe servire una preparazione non ancora pianificata.",
            kind="dependency", epistemic_status="inferred", confidence=0.7,
        )],
        relevance=0.7, confidence=0.8,
        batch_key=f"batch_{uuid.uuid4().hex[:16]}",
    )
    await ImpactAssessmentRepository(db).insert(assessment)
    return assessment


async def _seed_deferred_chain(
    db, user_id, *, hours=-1.0, revision=1, automatic_used=0, focal=None,
):
    """A deferred AttentionDecision plus the ImpactAssessment it is about,
    linked exactly like a real chain: reconsideration re-fetches the
    assessment by id rather than deriving a new one, so the two must agree."""
    assessment = await _seed_assessment(db, user_id, focal=focal)
    assessment_ids = [assessment.id]
    when = datetime.now(timezone.utc) + timedelta(hours=hours)
    decision = AttentionDecision(
        user_id=user_id,
        assessment_refs=assessment_ids,
        focal_refs=assessment.focal_refs,
        ai_delivery="defer", delivery="defer",
        defer_until=when.isoformat(),
        decision_key=decision_key_for(user_id, assessment_ids, revision=revision),
        root_attention_key=root_attention_key_for(user_id, assessment_ids),
        attention_revision=revision,
        automatic_re_evaluations_used=automatic_used,
    )
    await AttentionDecisionRepository(db).insert(decision)
    # Mirror the real flow: a first-evaluation decision always marks its
    # source assessment(s) consumed. Without this the assessment would look
    # like it is STILL awaiting its first attention pass — an artifact of
    # seeding a chain directly rather than through `_evaluate_batch`, not a
    # state a real deferred chain could ever be in.
    await ImpactAssessmentRepository(db).mark_attention_evaluated(
        user_id, assessment_ids
    )
    return assessment, decision


async def _force_due(db, decision_id, *, hours=-1.0):
    """Simulate time passing without sleeping: rewrite one decision's
    `defer_until` into the past."""
    when = datetime.now(timezone.utc) + timedelta(hours=hours)
    await db.life_attention_decisions.update_one(
        {"id": decision_id}, {"$set": {"defer_until": when.isoformat()}}
    )


async def _current(db, user_id, root_key):
    return await AttentionDecisionRepository(db).latest_for_root(user_id, root_key)


async def _chain(db, user_id, root_key):
    return await AttentionDecisionRepository(db).chain_for_root(user_id, root_key)


async def _cleanup(db, user_id):
    for col in (
        "life_attention_decisions", "life_impact_assessments", "life_change_signals",
        "life_orchestration_state", "proactive_suggestions", "proactive_learning",
        "situations", "memories", "context_edges", "calendar_event_drafts",
        "life_os_plans",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _ensure_indexes(db) -> None:
    """The decision_key/lease unique indexes are load-bearing for the
    idempotency and concurrency guarantees under test — same inline pattern
    the V2.9.2/V2.9.3/V2.9.4 suites all use (an async autouse fixture does not
    fit this repo's pytest-asyncio setup, so this is called explicitly)."""
    try:
        await OrchestrationService(db).ensure_indexes()
        await AttentionDecisionRepository(db).ensure_indexes()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# A / B / C — eligibility and cost
# ---------------------------------------------------------------------------
async def test_a_defer_not_due_costs_nothing(monkeypatch):
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_deferred_chain(db, user, hours=6.0)
        report = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report.defer_reevaluations_requested == 0
        assert report.ai_calls == 0
        assert manager.calls == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_b_defer_due_triggers_exactly_one_attention_call(monkeypatch):
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager({
        "delivery": "defer", "utility": 0.4, "urgency": 0.3, "confidence": 0.7,
        "novelty": 0.4, "actionability": 0.3, "defer_hours": 6,
        "proposed_title": None, "reason_summary": "Ancora presto.",
    })
    _patch_manager(monkeypatch, manager)
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        report = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report.defer_reevaluations_requested == 1
        assert report.defer_reevaluations_completed == 1
        assert report.ai_calls == 1
        assert manager.attention_calls == 1
        current = await _current(db, user, previous.root_attention_key)
        assert current.attention_revision == 2
        assert current.supersedes_decision_id == previous.id
    finally:
        await _cleanup(db, user)
        client.close()


async def test_c_reevaluation_never_calls_impact_reasoning(monkeypatch):
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _seed_deferred_chain(db, user, hours=-1.0)
        await AttentionService(db).reevaluate_due_deferrals(user)
        assert manager.impact_calls == 0
        assert manager.attention_calls == 1
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# D / E / F — AI-chosen outcomes on reconsideration
# ---------------------------------------------------------------------------
async def test_d_defer_to_home_supersedes_with_one_suggestion(monkeypatch):
    # High enough to clear the Proactive Engine's own real "would an
    # assistant speak?" gate (score >= 0.55 for a generic candidate) —
    # exactly the values V2.9.3's own guaranteed-acceptance test uses.
    manager = _FakeManager({
        "delivery": "home", "utility": 0.95, "urgency": 0.95, "confidence": 0.95,
        "novelty": 0.9, "actionability": 0.85,
        "defer_hours": None,
        "proposed_title": "Da rivedere ora", "reason_summary": "Ora conviene.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        report = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report.suggestions_created == 1
        chain = await _chain(db, user, previous.root_attention_key)
        assert len(chain) == 2
        assert chain[0].superseded_by == chain[1].id
        assert chain[1].delivery == "home"
        suggestions = await db.proactive_suggestions.find(
            {"user_id": user}, {"_id": 0}
        ).to_list(10)
        assert len(suggestions) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_e_defer_to_silent_terminates_chain_with_no_suggestion(monkeypatch):
    manager = _FakeManager({
        "delivery": "silent", "utility": 0.2, "urgency": 0.1, "confidence": 0.6,
        "novelty": 0.2, "actionability": 0.1, "defer_hours": None,
        "proposed_title": None, "reason_summary": "Non serve più.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        report = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report.suggestions_created == 0
        current = await _current(db, user, previous.root_attention_key)
        assert current.delivery == "silent"
        assert current.defer_until is None
        assert (await db.proactive_suggestions.count_documents({"user_id": user})) == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_f_defer_to_defer_persists_new_future_defer_until(monkeypatch):
    manager = _FakeManager({
        "delivery": "defer", "utility": 0.4, "urgency": 0.3, "confidence": 0.7,
        "novelty": 0.3, "actionability": 0.3, "defer_hours": 12,
        "proposed_title": None, "reason_summary": "Ancora prematuro.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        await AttentionService(db).reevaluate_due_deferrals(user)
        current = await _current(db, user, previous.root_attention_key)
        assert current.delivery == "defer"
        assert current.defer_until is not None
        assert current.defer_until > previous.defer_until
        assert current.automatic_re_evaluations_used == 1
        # Not due again immediately — a re-scan right now finds nothing.
        report2 = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report2.defer_reevaluations_requested == 0
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# G — concurrency-safety of a single reconsideration
# ---------------------------------------------------------------------------
async def test_g_stale_concurrent_retry_is_idempotent(monkeypatch):
    """Two callers racing on the exact same due snapshot (e.g. two processes
    that both listed the deferral before either wrote) must not fork the
    chain into two revision-2 decisions."""
    manager = _FakeManager({
        "delivery": "home", "utility": 0.8, "urgency": 0.6, "confidence": 0.85,
        "novelty": 0.6, "actionability": 0.6, "defer_hours": None,
        "proposed_title": "Da rivedere", "reason_summary": "Ora conviene.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        svc = AttentionService(db)
        context = {
            "now_utc": datetime.now(timezone.utc), "timezone": "Europe/Rome",
            "local_hour": 15, "quiet_hours": False, "likely_sleep": False,
            "busy_in_commitment_now": False, "commitments_next_2h": 0,
            "suggestions_shown_last_hour": 0, "suggestions_currently_visible": 0,
            "user_dismiss_rate": 0.0, "learning_multiplier": 1.0,
            "interruption_cost": 0.0, "notifications_allowed": True,
        }
        report = attention_service.AttentionPassReport()
        await svc._reevaluate_one(user, previous, context, report)
        await svc._reevaluate_one(user, previous, context, report)  # stale retry
        chain = await _chain(db, user, previous.root_attention_key)
        assert len(chain) == 2, "a stale retry must not fork a second revision-2"
        assert report.defer_reevaluations_completed == 2
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# H / I — deterministic identity
# ---------------------------------------------------------------------------
async def test_h_decision_key_stable_and_revision_scoped():
    user = f"u_{uuid.uuid4().hex[:8]}"
    refs = [f"lia_{uuid.uuid4().hex[:12]}", f"lia_{uuid.uuid4().hex[:12]}"]
    rev1 = decision_key_for(user, refs, revision=1)
    rev1_again = decision_key_for(user, refs)  # default revision=1
    rev2 = decision_key_for(user, refs, revision=2)
    rev2_again = decision_key_for(user, refs, revision=2)
    assert rev1 == rev1_again == root_attention_key_for(user, refs)
    assert rev2 == rev2_again
    assert rev2 != rev1
    assert rev2.startswith(rev1 + ":r2")


async def test_i_root_attention_key_order_independent():
    user = f"u_{uuid.uuid4().hex[:8]}"
    a, b = f"lia_{uuid.uuid4().hex[:12]}", f"lia_{uuid.uuid4().hex[:12]}"
    assert root_attention_key_for(user, [a, b]) == root_attention_key_for(user, [b, a])
    other_user = f"u_{uuid.uuid4().hex[:8]}"
    assert root_attention_key_for(user, [a, b]) != root_attention_key_for(other_user, [a, b])


# ---------------------------------------------------------------------------
# J / K / L — failure honesty
# ---------------------------------------------------------------------------
async def test_j_provider_failure_leaves_old_defer_current(monkeypatch):
    manager = _FakeManager(raises=RuntimeError("provider down"))
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        report = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report.defer_reevaluations_failed == 1
        assert report.defer_reevaluations_completed == 0
        chain = await _chain(db, user, previous.root_attention_key)
        assert len(chain) == 1
        assert chain[0].superseded_by is None
        assert chain[0].automatic_re_evaluations_used == 0
        assert chain[0].delivery == "defer"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_k_invalid_model_output_leaves_old_defer_current(monkeypatch):
    manager = _FakeManager(text="not json at all, sorry")
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        report = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report.defer_reevaluations_failed == 1
        chain = await _chain(db, user, previous.root_attention_key)
        assert len(chain) == 1
        assert chain[0].superseded_by is None
        assert chain[0].automatic_re_evaluations_used == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_l_persistence_failure_leaves_old_defer_current(monkeypatch):
    manager = _FakeManager({
        "delivery": "home", "utility": 0.8, "urgency": 0.6, "confidence": 0.85,
        "novelty": 0.6, "actionability": 0.6, "defer_hours": None,
        "proposed_title": "Da rivedere", "reason_summary": "Ora conviene.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)

        async def _boom(self, decision):
            raise RuntimeError("mongo write failed")

        monkeypatch.setattr(AttentionDecisionRepository, "insert", _boom)
        report = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report.defer_reevaluations_failed == 1
        assert report.defer_reevaluations_completed == 0
    finally:
        # Undo the monkeypatch's effect before reading back with a clean repo.
        monkeypatch.undo()
        chain = await _chain(db, user, previous.root_attention_key)
        assert len(chain) == 1, "no partially-written revision must survive a persist failure"
        assert chain[0].superseded_by is None
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# M / N — timer loss and recovery
# ---------------------------------------------------------------------------
async def test_m_lost_timer_recovered_via_run_user_pass(monkeypatch):
    """No one-shot timer was ever armed for this deferral (simulating a
    process restart). The next lease-protected pass — exactly what recovery's
    `schedule_user_reasoning` eventually triggers — still finds and
    reconsiders it, from Mongo state alone."""
    manager = _FakeManager({
        "delivery": "home", "utility": 0.8, "urgency": 0.6, "confidence": 0.85,
        "novelty": 0.6, "actionability": 0.6, "defer_hours": None,
        "proposed_title": "Da rivedere", "reason_summary": "Ora conviene.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-2.0)
        assert user in await OrchestrationService(db).users_with_due_deferrals(limit=50)
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.ai_calls == 1
        assert report.defer_reevaluations_completed == 1
        current = await _current(db, user, previous.root_attention_key)
        assert current.attention_revision == 2
    finally:
        await _cleanup(db, user)
        client.close()


async def test_n_future_defer_costs_nothing_via_recovery_path(monkeypatch):
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _seed_deferred_chain(db, user, hours=6.0)
        assert user not in await OrchestrationService(db).users_with_due_deferrals(limit=50)
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.skipped_reason == "no_pending_work"
        assert report.ai_calls == 0
        assert manager.calls == 0
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# O / P / Q — the automatic-reconsideration budget is a COST ceiling
# ---------------------------------------------------------------------------
async def test_o_three_automatic_reevaluations_exhaust_budget(monkeypatch):
    manager = _FakeManager({
        "delivery": "defer", "utility": 0.4, "urgency": 0.3, "confidence": 0.7,
        "novelty": 0.3, "actionability": 0.3, "defer_hours": 6,
        "proposed_title": None, "reason_summary": "Ancora prematuro.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        assert MAX_AUTOMATIC_DEFER_REEVALUATIONS == 3
        _, rev1 = await _seed_deferred_chain(db, user, hours=-1.0)
        root = rev1.root_attention_key

        for expected_used in (1, 2, 3):
            report = await AttentionService(db).reevaluate_due_deferrals(user)
            assert report.defer_reevaluations_completed == 1
            current = await _current(db, user, root)
            assert current.automatic_re_evaluations_used == expected_used
            if expected_used < MAX_AUTOMATIC_DEFER_REEVALUATIONS:
                await _force_due(db, current.id)

        exhausted = await _current(db, user, root)
        assert exhausted.attention_revision == 4
        assert exhausted.auto_re_evaluation_exhausted is True
        # The AI's own last choice — not a system-manufactured silence.
        assert exhausted.delivery == "defer"
        assert manager.attention_calls == 3
    finally:
        await _cleanup(db, user)
        client.close()


async def test_p_fourth_automatic_call_is_blocked_after_exhaustion(monkeypatch):
    manager = _FakeManager({
        "delivery": "defer", "utility": 0.4, "urgency": 0.3, "confidence": 0.7,
        "novelty": 0.3, "actionability": 0.3, "defer_hours": 6,
        "proposed_title": None, "reason_summary": "Ancora prematuro.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, rev1 = await _seed_deferred_chain(db, user, hours=-1.0)
        root = rev1.root_attention_key
        for _ in range(MAX_AUTOMATIC_DEFER_REEVALUATIONS):
            await AttentionService(db).reevaluate_due_deferrals(user)
            current = await _current(db, user, root)
            if not current.auto_re_evaluation_exhausted:
                await _force_due(db, current.id)
        assert manager.attention_calls == MAX_AUTOMATIC_DEFER_REEVALUATIONS

        exhausted = await _current(db, user, root)
        await _force_due(db, exhausted.id)  # due again, but budget is gone
        report = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report.defer_reevaluations_requested == 0
        assert manager.attention_calls == MAX_AUTOMATIC_DEFER_REEVALUATIONS, (
            "a 4th automatic call must never reach the provider"
        )
        still_current = await _current(db, user, root)
        assert still_current.id == exhausted.id
        assert still_current.delivery == "defer"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_q_new_signal_after_exhaustion_is_not_blocked(monkeypatch):
    """The automatic budget is per ROOT QUESTION, never per user: an
    unrelated new LifeChangeSignal must flow through the ordinary pipeline
    untouched by another chain's exhaustion."""
    manager = _FakeManager({
        "delivery": "defer", "utility": 0.4, "urgency": 0.3, "confidence": 0.7,
        "novelty": 0.3, "actionability": 0.3, "defer_hours": 6,
        "proposed_title": None, "reason_summary": "Ancora prematuro.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, rev1 = await _seed_deferred_chain(db, user, hours=-1.0)
        root = rev1.root_attention_key
        for _ in range(MAX_AUTOMATIC_DEFER_REEVALUATIONS):
            await AttentionService(db).reevaluate_due_deferrals(user)
            current = await _current(db, user, root)
            if not current.auto_re_evaluation_exhausted:
                await _force_due(db, current.id)
        assert (await _current(db, user, root)).auto_re_evaluation_exhausted is True

        # A brand-new, unrelated assessment for the same user.
        other = await _seed_assessment(db, user)
        new_report = await AttentionService(db).run_pass(user)
        assert new_report.ai_calls == 1
        other_root = root_attention_key_for(user, [other.id])
        assert other_root != root
        other_current = await _current(db, user, other_root)
        assert other_current is not None
        assert other_current.attention_revision == 1
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# R / S / T — surfaces stay decisions, never actions
# ---------------------------------------------------------------------------
async def test_r_defer_to_ask_user_creates_no_tool_execution(monkeypatch):
    manager = _FakeManager({
        "delivery": "ask_user", "utility": 0.95, "urgency": 0.9, "confidence": 0.95,
        "novelty": 0.9, "actionability": 0.85,
        "defer_hours": None,
        "proposed_title": "Confermi questo?", "reason_summary": "Serve una conferma.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        before_plans = await db.life_os_plans.count_documents({"user_id": user})
        before_cal = await db.calendar_event_drafts.count_documents({"user_id": user})
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        report = await AttentionService(db).reevaluate_due_deferrals(user)
        current = await _current(db, user, previous.root_attention_key)
        assert current.delivery == "ask_user"
        assert report.suggestions_created == 1
        assert await db.life_os_plans.count_documents({"user_id": user}) == before_plans
        assert (
            await db.calendar_event_drafts.count_documents({"user_id": user})
            == before_cal
        )
    finally:
        await _cleanup(db, user)
        client.close()


async def test_s_defer_to_notify_never_dispatches_a_push(monkeypatch):
    manager = _FakeManager({
        "delivery": "notify", "utility": 0.98, "urgency": 0.98, "confidence": 0.98,
        "novelty": 0.9, "actionability": 0.9, "defer_hours": None,
        "proposed_title": "Importante ora", "reason_summary": "Non può aspettare.",
    })
    _patch_manager(monkeypatch, manager)

    async def _allowed(db_, uid):
        return True

    monkeypatch.setattr(attention_service, "notifications_allowed", _allowed)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        await AttentionService(db).reevaluate_due_deferrals(user)
        current = await _current(db, user, previous.root_attention_key)
        assert current.delivery == "notify"
        sugg = await db.proactive_suggestions.find_one({"user_id": user}, {"_id": 0})
        assert sugg is not None
        assert sugg["meta"]["notification_policy"]["send_now"] is False
    finally:
        await _cleanup(db, user)
        client.close()


async def test_t_legacy_collision_yields_a_single_suggestion(monkeypatch):
    manager = _FakeManager({
        "delivery": "home", "utility": 0.8, "urgency": 0.6, "confidence": 0.85,
        "novelty": 0.6, "actionability": 0.6, "defer_hours": None,
        "proposed_title": "Da rivedere", "reason_summary": "Ora conviene.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        entity_id = f"sit_{uuid.uuid4().hex[:8]}"
        focal = [f"situation:{entity_id}"]
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0, focal=focal)
        from proactive_engine.models import Suggestion

        legacy = Suggestion(
            user_id=user, title="Legacy item", reason="preesistente",
            type="life", source="legacy_generator",
            status="active", meta={"focal_refs": list(focal)},
        )
        await db.proactive_suggestions.insert_one(legacy.model_dump())

        report = await AttentionService(db).reevaluate_due_deferrals(user)
        assert report.suggestions_created == 0
        current = await _current(db, user, previous.root_attention_key)
        assert current.suggestion_created is False
        assert "duplicate_active_item_for_same_refs" in current.gate_reasons
        total = await db.proactive_suggestions.count_documents({"user_id": user})
        assert total == 1
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# U — concurrency: the existing lease also protects reconsideration
# ---------------------------------------------------------------------------
async def test_u_lease_blocks_concurrent_reevaluation(monkeypatch):
    manager = _FakeManager()
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _seed_deferred_chain(db, user, hours=-1.0)
        state = OrchestrationStateRepository(db)
        held = await state.acquire(user)
        assert held is True
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.skipped_reason == "lease_held"
        assert report.ai_calls == 0
        assert manager.calls == 0
    finally:
        await OrchestrationStateRepository(db).release(user)
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# V / W — reconsideration produces NOTHING else
# ---------------------------------------------------------------------------
async def test_v_reevaluation_creates_no_new_signal_or_assessment(monkeypatch):
    manager = _FakeManager({
        "delivery": "defer", "utility": 0.4, "urgency": 0.3, "confidence": 0.7,
        "novelty": 0.3, "actionability": 0.3, "defer_hours": 6,
        "proposed_title": None, "reason_summary": "Ancora prematuro.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _seed_deferred_chain(db, user, hours=-1.0)
        signals_before = await db.life_change_signals.count_documents({"user_id": user})
        assessments_before = await db.life_impact_assessments.count_documents(
            {"user_id": user}
        )
        await AttentionService(db).reevaluate_due_deferrals(user)
        assert (
            await db.life_change_signals.count_documents({"user_id": user})
            == signals_before
        )
        assert (
            await db.life_impact_assessments.count_documents({"user_id": user})
            == assessments_before
        )
    finally:
        await _cleanup(db, user)
        client.close()


async def test_w_reevaluation_mutates_no_other_life_os_surface(monkeypatch):
    manager = _FakeManager({
        "delivery": "home", "utility": 0.8, "urgency": 0.6, "confidence": 0.85,
        "novelty": 0.6, "actionability": 0.6, "defer_hours": None,
        "proposed_title": "Da rivedere", "reason_summary": "Ora conviene.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _seed_deferred_chain(db, user, hours=-1.0)
        cols = ("context_edges", "memories", "situations", "life_os_plans",
                 "calendar_event_drafts")
        before = {c: await db[c].count_documents({"user_id": user}) for c in cols}
        await AttentionService(db).reevaluate_due_deferrals(user)
        for c in cols:
            assert await db[c].count_documents({"user_id": user}) == before[c], c
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# X — storage-level idempotency
# ---------------------------------------------------------------------------
async def test_x_duplicate_decision_key_rejected_at_storage_level():
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        repo = AttentionDecisionRepository(db)
        refs = [f"lia_{uuid.uuid4().hex[:12]}"]
        key = decision_key_for(user, refs, revision=2)
        first = AttentionDecision(
            user_id=user, assessment_refs=refs, decision_key=key,
            root_attention_key=root_attention_key_for(user, refs),
            attention_revision=2,
        )
        await repo.insert(first)
        second = AttentionDecision(
            user_id=user, assessment_refs=refs, decision_key=key,
            root_attention_key=root_attention_key_for(user, refs),
            attention_revision=2,
        )
        with pytest.raises(DuplicateDecision):
            await repo.insert(second)
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# Y — hardcoding audit, scoped to the new reconsideration code
# ---------------------------------------------------------------------------
_FORBIDDEN_DOMAIN_TERMS = (
    "house", "mortgage", "mutuo", "notaio", "notary", "insurance", "travel",
    "study", "medical", "car", "bonsai", "party", "exhibition", "mostra",
    "festa", "work",
)


def _source_without_docstrings(func) -> str:
    import textwrap

    src = textwrap.dedent(inspect.getsource(func))
    tree = ast.parse(src)
    lines = src.splitlines()
    drop: set = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                drop.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    kept = [ln for i, ln in enumerate(lines, start=1) if i not in drop]
    return re.sub(r"#.*$", "", "\n".join(kept), flags=re.MULTILINE)


async def test_y_no_domain_routing_in_reevaluation_code():
    funcs = [
        AttentionService.reevaluate_due_deferrals,
        AttentionService._reevaluate_one,
        AttentionService._assessments_by_ids,
        OrchestrationService._run_cycles,
        OrchestrationService._has_due_deferral,
    ]
    for func in funcs:
        code = _source_without_docstrings(func).lower()
        for term in _FORBIDDEN_DOMAIN_TERMS:
            assert not re.search(rf"\b{re.escape(term)}\b", code), (
                f"{term} leaked into {func.__qualname__}"
            )
        assert "sleep" not in code, f"blocking sleep found in {func.__qualname__}"


# ---------------------------------------------------------------------------
# Z — full-pipeline integration through the orchestrator
# ---------------------------------------------------------------------------
async def test_z_full_pass_integration_surfaces_defer_counters(monkeypatch):
    manager = _FakeManager({
        "delivery": "home", "utility": 0.95, "urgency": 0.95, "confidence": 0.95,
        "novelty": 0.9, "actionability": 0.85,
        "defer_hours": None,
        "proposed_title": "Da rivedere", "reason_summary": "Ora conviene.",
    })
    _patch_manager(monkeypatch, manager)
    client, db = _db()
    await _ensure_indexes(db)
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        _, previous = await _seed_deferred_chain(db, user, hours=-1.0)
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.ran is True
        assert report.impact_runs == 0
        assert report.attention_runs == 0
        assert report.ai_calls == 1
        assert report.defer_reevaluations_requested == 1
        assert report.defer_reevaluations_completed == 1
        assert report.suggestions_created == 1
        current = await _current(db, user, previous.root_attention_key)
        assert current.attention_revision == 2
        assert current.delivery == "home"
    finally:
        await _cleanup(db, user)
        client.close()
