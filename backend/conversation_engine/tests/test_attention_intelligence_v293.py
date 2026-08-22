"""V2.9.3 — Attention & Intervention Intelligence (deterministic, A-Z).

Real MongoDB test DB throughout. The Provider Manager is stubbed per test so
the attention path runs end to end without consuming quota; the provider-real
gate lives in `test_attention_intelligence_v293_live.py`.

The load-bearing assertions here are about RESTRAINT: that silence is normal,
that the system can always overrule the model toward quiet, and that a
user-facing item appears only when the AI's judgement and the system's
permission agree.
"""
from __future__ import annotations

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

from life_attention import service as attention_service  # noqa: E402
from life_attention.gate import apply_system_gate  # noqa: E402
from life_attention.models import decision_key_for  # noqa: E402
from life_attention.repository import AttentionDecisionRepository  # noqa: E402
from life_attention.service import AttentionService  # noqa: E402
from life_reasoning.models import Impact, ImpactAssessment  # noqa: E402
from life_reasoning.repository import ImpactAssessmentRepository  # noqa: E402
from proactive_engine.learning import LearningStore  # noqa: E402

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
        self.usage = {}


class _FakeManager:
    def __init__(self, payload, *, raises=None):
        self._payload = payload
        self._raises = raises
        self.calls = 0
        self.last_system = None
        self.last_user = None

    async def chat(self, *, system, user, json_mode=False, **kwargs):
        self.calls += 1
        self.last_system = system
        self.last_user = user
        if self._raises:
            raise self._raises
        body = self._payload(user) if callable(self._payload) else self._payload
        return _FakeResult(body if isinstance(body, str) else json.dumps(body))


def _out(**overrides):
    base = {
        "delivery": "home",
        "utility": 0.8,
        "urgency": 0.7,
        "confidence": 0.85,
        "novelty": 0.8,
        "actionability": 0.7,
        "defer_hours": None,
        "proposed_title": "Un passaggio da chiarire",
        "reason_summary": "Una conseguenza concreta merita uno sguardo.",
    }
    base.update(overrides)
    return base


def _patch_manager(monkeypatch, manager):
    import llm.manager as llm_manager

    monkeypatch.setattr(llm_manager, "get_manager", lambda: manager)


@pytest.fixture(autouse=True)
def _freeze_local_hour(monkeypatch):
    """Pin the user's local clock to a free mid-afternoon hour.

    The gate legitimately downgrades everything to Home during quiet hours, so
    a suite that reads the real wall clock would pass at 15:00 and fail at
    midnight. Patching the lowest-level time source keeps every downstream
    computation real — quiet/sleep detection, interruption cost and the gate
    all still run for real, they just run against a known moment.
    `test_e`/`test_f` call the gate directly to cover the quiet-hours and
    busy-commitment paths deterministically.
    """
    import life_attention.context as ctx_mod

    async def _fixed(db, user_id):
        return datetime.now(timezone.utc), "Europe/Rome", 15

    monkeypatch.setattr(ctx_mod, "resolve_local_time", _fixed)


async def _seed_assessment(db, user_id, *, focal=None, impacts=None, relevance=0.7):
    refs = focal or [f"situation:sit_{uuid.uuid4().hex[:8]}"]
    assessment = ImpactAssessment(
        user_id=user_id,
        source_signal_ids=[f"lcs_{uuid.uuid4().hex[:12]}"],
        focal_refs=refs,
        impacts=impacts if impacts is not None else [
            Impact(
                statement="Potrebbe servire una preparazione non ancora pianificata.",
                kind="dependency", epistemic_status="inferred", confidence=0.7,
            )
        ],
        relevance=relevance,
        confidence=0.8,
        batch_key=f"batch_{uuid.uuid4().hex[:16]}",
    )
    await ImpactAssessmentRepository(db).insert(assessment)
    return assessment


async def _decisions(db, user_id):
    return await db.life_attention_decisions.find(
        {"user_id": user_id}, {"_id": 0},
    ).sort([("created_at", 1), ("id", 1)]).to_list(50)


async def _suggestions(db, user_id):
    return await db.proactive_suggestions.find(
        {"user_id": user_id}, {"_id": 0},
    ).to_list(50)


async def _cleanup(db, user_id):
    for col in (
        "life_attention_decisions", "life_impact_assessments", "life_change_signals",
        "proactive_suggestions", "proactive_learning", "calendar_event_drafts",
        "situations", "memories", "context_edges", "life_os_plans",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _free_context(db, user_id):
    """Baseline operational context: nothing competing for attention."""
    return {
        "now_utc": datetime.now(timezone.utc),
        "timezone": "Europe/Rome", "local_hour": 15,
        "quiet_hours": False, "likely_sleep": False,
        "busy_in_commitment_now": False, "commitments_next_2h": 0,
        "suggestions_shown_last_hour": 0, "suggestions_currently_visible": 0,
        "user_dismiss_rate": 0.0, "learning_multiplier": 1.0,
        "interruption_cost": 0.0, "notifications_allowed": True,
    }


# ---------------------------------------------------------------------------
# A / B / C / D — the AI judgement
# ---------------------------------------------------------------------------
async def test_a_high_value_assessment_creates_decision(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out())
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)

        assert report.assessments_seen == 1
        assert report.ai_calls == 1
        rows = await _decisions(db, user)
        assert len(rows) == 1
        assert rows[0]["delivery"] == "home"
        assert rows[0]["ai_delivery"] == "home"
        assert report.assessments_evaluated == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_b_low_value_assessment_stays_silent(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(
        delivery="silent", utility=0.1, urgency=0.1, proposed_title=None,
        reason_summary="Nulla che valga la pena dire ora.",
    ))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user, relevance=0.2)
        report = await AttentionService(db).run_pass(user)

        assert report.silent == 1
        rows = await _decisions(db, user)
        assert len(rows) == 1, "a decision to stay quiet is still recorded"
        assert rows[0]["delivery"] == "silent"
        # Silence produces nothing user-facing.
        assert await _suggestions(db, user) == []
        assert report.suggestions_created == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_c_low_confidence_never_reaches_the_user(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    # The model wants to speak, but is not confident enough.
    manager = _FakeManager(_out(delivery="notify", confidence=0.2))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)

        row = (await _decisions(db, user))[0]
        assert row["ai_delivery"] == "notify"
        assert row["delivery"] == "silent"
        assert "confidence_below_floor" in row["downgrade_reasons"]
        assert report.system_downgrades == 1
        assert await _suggestions(db, user) == []
    finally:
        await _cleanup(db, user)
        client.close()


async def test_d_urgent_actionable_is_eligible_for_a_surface(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(
        delivery="propose_action", utility=0.9, urgency=0.85,
        confidence=0.9, actionability=0.9,
    ))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        await AttentionService(db).run_pass(user)
        row = (await _decisions(db, user))[0]
        assert row["delivery"] == "propose_action"
        assert row["downgrade_reasons"] == []
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# E / F / G / H / I — the system gate (pure, no DB)
# ---------------------------------------------------------------------------
async def test_e_quiet_hours_downgrade_notify():
    free = {"interruption_cost": 0.35, "user_dismiss_rate": 0.0,
            "notifications_allowed": True, "quiet_hours": True, "likely_sleep": False}
    delivery, reasons = apply_system_gate(
        ai_delivery="notify", confidence=0.95, utility=0.95,
        context=free, times_already_raised=0,
    )
    assert delivery == "home"
    assert "quiet_hours" in reasons


async def test_f_active_commitment_downgrades():
    ctx = {"interruption_cost": 0.3, "user_dismiss_rate": 0.0,
           "notifications_allowed": True, "busy_in_commitment_now": True}
    delivery, reasons = apply_system_gate(
        ai_delivery="notify", confidence=0.95, utility=0.95,
        context=ctx, times_already_raised=0,
    )
    assert delivery == "home"
    assert "busy_in_commitment" in reasons


async def test_g_free_context_applies_no_artificial_downgrade():
    ctx = {"interruption_cost": 0.0, "user_dismiss_rate": 0.0,
           "notifications_allowed": True, "quiet_hours": False,
           "likely_sleep": False, "busy_in_commitment_now": False}
    delivery, reasons = apply_system_gate(
        ai_delivery="notify", confidence=0.95, utility=0.95,
        context=ctx, times_already_raised=0,
    )
    assert delivery == "notify"
    assert reasons == []


async def test_h_repetition_raises_then_closes_the_bar():
    ctx = {"interruption_cost": 0.0, "user_dismiss_rate": 0.0,
           "notifications_allowed": True}
    # Raised twice already: quieter, but still shown.
    soft, soft_reasons = apply_system_gate(
        ai_delivery="notify", confidence=0.95, utility=0.95,
        context=ctx, times_already_raised=2,
    )
    assert soft == "home"
    assert "recently_raised" in soft_reasons
    # Raised persistently: silent.
    hard, hard_reasons = apply_system_gate(
        ai_delivery="notify", confidence=0.95, utility=0.95,
        context=ctx, times_already_raised=5,
    )
    assert hard == "silent"
    assert "repeated_too_often" in hard_reasons


async def test_h2_dismissive_user_is_downgraded_not_silenced_forever():
    ctx = {"interruption_cost": 0.0, "user_dismiss_rate": 0.95,
           "notifications_allowed": True}
    delivery, reasons = apply_system_gate(
        ai_delivery="notify", confidence=0.95, utility=0.95,
        context=ctx, times_already_raised=0,
    )
    # Bounded learning: quieter, never a permanent blacklist.
    assert delivery == "home"
    assert "user_dismisses_often" in reasons


async def test_i_first_time_user_gets_neutral_learning(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        store = LearningStore(db)
        assert await store.multiplier(user, "generic", "life_reasoning") == 1.0
        assert await store.dismiss_rate(user, "generic", "life_reasoning") == 0.0
        # ...and a couple of dismissals are still not enough to learn from.
        for _ in range(2):
            await store.record(user, "generic", "life_reasoning", event="dismissed")
        assert await store.multiplier(user, "generic", "life_reasoning") == 1.0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_u_no_notification_permission_downgrades():
    ctx = {"interruption_cost": 0.0, "user_dismiss_rate": 0.0,
           "notifications_allowed": False}
    delivery, reasons = apply_system_gate(
        ai_delivery="notify", confidence=0.95, utility=0.95,
        context=ctx, times_already_raised=0,
    )
    assert delivery == "home"
    assert "no_notification_permission" in reasons


async def test_gate_never_raises_the_ai_choice():
    """The one-way property: no context can make the system louder than the
    model asked for."""
    from life_attention.models import DELIVERY_ORDER

    ctx = {"interruption_cost": 0.0, "user_dismiss_rate": 0.0,
           "notifications_allowed": True}
    for ai_choice in DELIVERY_ORDER:
        delivery, _ = apply_system_gate(
            ai_delivery=ai_choice, confidence=1.0, utility=1.0,
            context=ctx, times_already_raised=0,
        )
        assert DELIVERY_ORDER.index(delivery) <= DELIVERY_ORDER.index(ai_choice)


# ---------------------------------------------------------------------------
# J / K / L — idempotency and lifecycle
# ---------------------------------------------------------------------------
async def test_j_replayed_pass_creates_no_duplicate_decision(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out())
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        svc = AttentionService(db)
        await svc.run_pass(user)
        calls_after_first = manager.calls

        second = await svc.run_pass(user)
        assert second.assessments_seen == 0, "evaluated assessments are not re-read"
        assert second.ai_calls == 0
        assert manager.calls == calls_after_first
        assert len(await _decisions(db, user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_j2_decision_key_is_order_independent_and_enforced(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        from life_attention.models import AttentionDecision
        from life_attention.repository import DuplicateDecision

        repo = AttentionDecisionRepository(db)
        await repo.ensure_indexes()
        key = decision_key_for(user, ["lia_a", "lia_b"])
        assert key == decision_key_for(user, ["lia_b", "lia_a"])
        await repo.insert(AttentionDecision(user_id=user, decision_key=key))
        with pytest.raises(DuplicateDecision):
            await repo.insert(AttentionDecision(user_id=user, decision_key=key))
        assert await repo.count(user) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_k_provider_failure_leaves_assessment_pending(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    from llm.errors import LLMProviderUnavailable

    manager = _FakeManager(None, raises=LLMProviderUnavailable([
        {"provider": "gemini", "failure_kind": "quota", "retryable": True},
    ]))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)

        assert "provider_unavailable" in report.failures
        assert await _decisions(db, user) == []
        # The conclusion is not lost: still awaiting attention.
        pending = await ImpactAssessmentRepository(db).list_awaiting_attention(user)
        assert len(pending) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_k2_unparseable_output_is_not_a_fake_decision(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager("not json at all")
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)
        assert await _decisions(db, user) == []
        assert len(await ImpactAssessmentRepository(db).list_awaiting_attention(user)) == 1
        assert report.assessments_evaluated == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_l_decision_persistence_failure_does_not_consume(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out())
    _patch_manager(monkeypatch, manager)

    async def _boom(self, decision):
        raise RuntimeError("attention store unavailable")

    monkeypatch.setattr(AttentionDecisionRepository, "insert", _boom)
    try:
        await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)

        assert "decision_persistence_failed" in report.failures
        assert report.assessments_evaluated == 0
        # PERSIST BEFORE CONSUME.
        assert len(await ImpactAssessmentRepository(db).list_awaiting_attention(user)) == 1
        assert await _suggestions(db, user) == []
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# M / N / O / P — Proactive Engine integration
# ---------------------------------------------------------------------------
async def test_m_silent_creates_zero_proactive_suggestion(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(delivery="silent", proposed_title=None))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        await AttentionService(db).run_pass(user)
        assert await _suggestions(db, user) == []
        assert (await _decisions(db, user))[0]["suggestion_created"] is False
    finally:
        await _cleanup(db, user)
        client.close()


async def test_n_home_decision_enters_the_existing_gate(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(delivery="home", utility=0.9, urgency=0.85, confidence=0.9))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        await AttentionService(db).run_pass(user)
        row = (await _decisions(db, user))[0]
        # Whether or not the gate accepted, the decision records the outcome —
        # the AI-native path never persists a suggestion by itself.
        assert "suggestion_created" in row
        sugs = await _suggestions(db, user)
        if row["suggestion_created"]:
            assert len(sugs) == 1
            assert sugs[0]["source"] == "life_reasoning"
            assert sugs[0]["type"] == "generic"
            # It went through real scoring, not a bypass.
            assert sugs[0]["score"] > 0
            assert sugs[0]["explain"] is not None
        else:
            assert sugs == []
            assert row["gate_reasons"]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_o_gate_reject_persists_zero_suggestion(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    # Passes the attention floor but is weak enough that the Proactive
    # Engine's own "would an assistant speak?" test rejects it.
    manager = _FakeManager(_out(
        delivery="home", utility=0.05, urgency=0.05, confidence=0.5,
    ))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)
        assert report.gate_rejects == 1
        assert await _suggestions(db, user) == []
        row = (await _decisions(db, user))[0]
        assert row["suggestion_created"] is False
        assert row["gate_reasons"]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_p_gate_accept_persists_exactly_one_suggestion(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(
        delivery="home", utility=0.95, urgency=0.95, confidence=0.95,
    ))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)
        sugs = await _suggestions(db, user)
        assert report.suggestions_created == 1
        assert len(sugs) == 1
        assert sugs[0]["source"] == "life_reasoning"
        # The reused notification policy never pushes.
        assert sugs[0]["meta"]["notification_policy"]["send_now"] is False
        row = (await _decisions(db, user))[0]
        assert row["suggestion_created"] is True
        assert row["suggestion_id"] == sugs[0]["id"]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_q_legacy_and_ai_native_collision_yields_one_item(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(
        delivery="home", utility=0.95, urgency=0.95, confidence=0.95,
    ))
    _patch_manager(monkeypatch, manager)
    try:
        goal_id = f"goal_{uuid.uuid4().hex[:8]}"
        # A legacy generator already surfaced something about this entity.
        from proactive_engine.models import Suggestion
        from proactive_engine.repository import SuggestionRepository

        await SuggestionRepository(db).insert(Suggestion(
            user_id=user, title="Voce legacy", reason="Da un generatore esistente",
            type="projects", source="goal_engine", goal_id=goal_id,
            status="active", dedupe_key=f"legacy_{uuid.uuid4().hex[:8]}",
        ))
        await _seed_assessment(db, user, focal=[f"goal:{goal_id}"])

        report = await AttentionService(db).run_pass(user)
        assert report.dedupe_hits == 1
        # Still exactly one user-facing item about that entity.
        assert len(await _suggestions(db, user)) == 1
        row = (await _decisions(db, user))[0]
        assert row["suggestion_created"] is False
        assert "duplicate_active_item_for_same_refs" in row["gate_reasons"]
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# R / S / T — no execution, no dispatch
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["ask_user", "propose_action"])
async def test_rs_ask_and_propose_execute_no_tool(monkeypatch, mode):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(
        delivery=mode, utility=0.95, urgency=0.9, confidence=0.95,
    ))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user, impacts=[Impact(
            statement="Un evento potrebbe aiutare.", kind="opportunity",
            epistemic_status="tentative", confidence=0.6,
            capability_hint="create_calendar_event",
        )])
        await AttentionService(db).run_pass(user)
        assert (await _decisions(db, user))[0]["delivery"] == mode
        # Nothing was written to any life subsystem.
        assert await db.calendar_event_drafts.count_documents({"user_id": user}) == 0
        assert await db.life_os_plans.count_documents({"user_id": user}) == 0
        assert await db.context_edges.count_documents({"user_id": user}) == 0
        assert await db.memories.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_t_notify_never_dispatches_a_push(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(
        delivery="notify", utility=0.98, urgency=0.98, confidence=0.98,
    ))
    _patch_manager(monkeypatch, manager)

    async def _allowed(db_, uid):
        return True

    monkeypatch.setattr(attention_service, "notifications_allowed", _allowed)
    try:
        await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)
        assert report.notify_requested == 1
        for sug in await _suggestions(db, user):
            # The reused foundation policy structurally never sends now.
            assert sug["meta"]["notification_policy"]["send_now"] is False
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# V / W — isolation and bounds
# ---------------------------------------------------------------------------
async def test_v_user_isolation(monkeypatch):
    client, db = _db()
    user_a = f"u_{uuid.uuid4().hex[:8]}"
    user_b = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out())
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user_a)
        svc = AttentionService(db)

        report_b = await svc.run_pass(user_b)
        assert report_b.assessments_seen == 0
        assert report_b.ai_calls == 0, "no pending assessments costs nothing"

        await svc.run_pass(user_a)
        assert len(await _decisions(db, user_a)) == 1
        assert await _decisions(db, user_b) == []
        assert await AttentionDecisionRepository(db).count(user_b) == 0
    finally:
        await _cleanup(db, user_a)
        await _cleanup(db, user_b)
        client.close()


async def test_w_assessment_batch_is_bounded(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(delivery="silent", proposed_title=None))
    _patch_manager(monkeypatch, manager)
    try:
        for _ in range(12):
            await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)
        assert report.assessments_seen <= attention_service.MAX_ASSESSMENTS_PER_PASS
        assert report.batches <= attention_service.MAX_BATCHES_PER_PASS
        assert report.ai_calls <= attention_service.MAX_BATCHES_PER_PASS
    finally:
        await _cleanup(db, user)
        client.close()


async def test_w2_correlated_assessments_share_one_decision(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(delivery="silent", proposed_title=None))
    _patch_manager(monkeypatch, manager)
    try:
        shared = f"situation:sit_{uuid.uuid4().hex[:8]}"
        await _seed_assessment(db, user, focal=[shared])
        await _seed_assessment(db, user, focal=[shared, f"plan:plan_{uuid.uuid4().hex[:8]}"])

        report = await AttentionService(db).run_pass(user)
        assert report.assessments_seen == 2
        assert report.batches == 1, "correlated conclusions are one interruption"
        assert report.ai_calls == 1
        rows = await _decisions(db, user)
        assert len(rows) == 1
        assert len(rows[0]["assessment_refs"]) == 2
    finally:
        await _cleanup(db, user)
        client.close()


async def test_defer_is_real_and_bounded(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(delivery="defer", defer_hours=6))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        report = await AttentionService(db).run_pass(user)
        row = (await _decisions(db, user))[0]
        assert report.deferred == 1
        assert row["delivery"] == "defer"
        # Defer is a real future time, not a silent drop.
        assert row["defer_until"]
        when = datetime.fromisoformat(row["defer_until"])
        assert when > datetime.now(timezone.utc)
        assert when < datetime.now(timezone.utc) + timedelta(days=8)
        # ...and nothing user-facing was produced.
        assert await _suggestions(db, user) == []
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# X / Y — privacy and contract hygiene
# ---------------------------------------------------------------------------
async def test_x_decision_carries_no_raw_user_text(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out())
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        await AttentionService(db).run_pass(user)
        row = (await _decisions(db, user))[0]
        assert set(row.keys()) == {
            "id", "user_id", "assessment_refs", "focal_refs", "ai_delivery",
            "delivery", "utility", "urgency", "confidence", "novelty",
            "actionability", "interruption_cost", "downgrade_reasons",
            "reason_summary", "proposed_title", "evidence_refs", "defer_until",
            "suggestion_id", "suggestion_created", "gate_reasons",
            "decision_key", "model_provider", "model_name", "created_at",
        }
        # Evidence by ref only.
        assert isinstance(row["evidence_refs"], list)
    finally:
        await _cleanup(db, user)
        client.close()


async def test_x2_prompt_receives_no_profile_memory_or_transcript(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out())
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        await AttentionService(db).run_pass(user)
        payload = json.loads(manager.last_user)
        assert set(payload.keys()) == {"conclusions", "situation"}
        # The attention layer never re-loads the life V2.9.2 already read.
        blob = json.dumps(payload).lower()
        for forbidden in ("profile", "memories", "document", "transcript", "user_message"):
            assert forbidden not in blob
        # ...and it is not told the permission facts it must not reason around.
        for withheld in ("notifications_allowed", "quiet_hours", "likely_sleep",
                         "interruption_cost", "user_dismiss_rate"):
            assert withheld not in payload["situation"]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_y_no_chain_of_thought_requested_or_stored(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(
        chain_of_thought="Prima ho pensato...", thinking="passaggio interno",
    ))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        await AttentionService(db).run_pass(user)
        row = (await _decisions(db, user))[0]
        for forbidden in ("chain_of_thought", "thinking", "reasoning_trace", "scratchpad"):
            assert forbidden not in row
        assert "not how you thought" in (manager.last_system or "")
    finally:
        await _cleanup(db, user)
        client.close()


async def test_arbitrary_delivery_value_falls_back_to_silence(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_out(delivery="SHOUT_AT_THE_USER"))
    _patch_manager(monkeypatch, manager)
    try:
        await _seed_assessment(db, user)
        await AttentionService(db).run_pass(user)
        row = (await _decisions(db, user))[0]
        # An unrecognised surface degrades to silence, never to noise.
        assert row["delivery"] == "silent"
        assert await _suggestions(db, user) == []
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# Z — static guarantees
# ---------------------------------------------------------------------------
_PRODUCTION_FILES = [
    Path(_BACKEND) / "life_attention" / "models.py",
    Path(_BACKEND) / "life_attention" / "service.py",
    Path(_BACKEND) / "life_attention" / "repository.py",
    Path(_BACKEND) / "life_attention" / "context.py",
    Path(_BACKEND) / "life_attention" / "gate.py",
]

_FORBIDDEN_DOMAIN_TERMS = (
    "house", "mortgage", "mutuo", "notary", "notaio", "insurance",
    "assicurazione", "car", "auto", "travel", "viaggio", "study", "medical",
    "medico", "bonsai", "party", "festa", "exhibition", "mostra",
)


def _code_only(path: Path) -> str:
    """Source with docstrings and comments removed — the audit must judge
    code, not documentation that states the rule."""
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


async def test_z_no_domain_router_in_production_code():
    import re

    for path in _PRODUCTION_FILES:
        code = _code_only(path).lower()
        for term in _FORBIDDEN_DOMAIN_TERMS:
            assert not re.search(rf"\b{re.escape(term)}\b", code), (
                f"{term} leaked into executable code of {path.name}"
            )


async def test_z2_no_keyword_branch_and_no_direct_vendor():
    import re

    keyword_branch = re.compile(r'if\s+["\'][a-z_ ]+["\']\s+in\s+(?!\w*(?:_VALID|known))')
    vendor = re.compile(
        r"(?:^|\s)(?:import|from)\s+\S*\b(?:google|genai|openai|anthropic|ollama)\b"
        r"|GenerativeModel|generativelanguage",
        re.MULTILINE,
    )
    for path in _PRODUCTION_FILES:
        code = _code_only(path)
        assert not keyword_branch.search(code), f"keyword routing in {path.name}"
        assert not vendor.search(code), f"direct vendor access in {path.name}"
    service_text = (Path(_BACKEND) / "life_attention" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "from llm.manager import get_manager" in service_text


async def test_z3_no_polling_worker_or_push_dispatch():
    for path in _PRODUCTION_FILES:
        code = _code_only(path).lower()
        for term in ("cron", "scheduler", "asyncio.sleep", "while true",
                     "create_task", "send_push", "fcm", "apns"):
            assert term not in code, f"{term} introduced in {path.name}"


async def test_z4_prompt_makes_silence_first_class_and_withholds_safety():
    from life_attention.prompt import ATTENTION_SYSTEM_PROMPT

    lowered = " ".join(ATTENTION_SYSTEM_PROMPT.lower().split())
    assert "silence is the default, not the failure" in lowered
    assert "interruption has a cost" in lowered
    assert "do not speak from speculation" in lowered
    assert "do not repeat yourself" in lowered
    assert "you do not execute anything" in lowered
    assert "optimise for the user's interest alone" in lowered
    assert "never name a company, product, vendor, brand or offer" in lowered
    assert "judge the substance, not the subject" in lowered
    # Safety is NOT delegated to the prompt.
    assert "the system decides whether it is allowed" in lowered
