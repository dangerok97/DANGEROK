"""V2.9.2 — AI-native Impact Reasoning (deterministic, A-Z).

Real MongoDB test DB throughout. The Provider Manager is stubbed per test via
a fake `chat` so the reasoning path is exercised end to end without consuming
quota; the provider-real gate lives in `test_impact_reasoning_v292_live.py`.

The load-bearing assertions of this sprint are the negative ones: V2.9.2
answers "SO WHAT?" and must never answer "SHOULD I SPEAK?". Tests M/N/O and
the attention-field checks exist to keep that boundary honest.
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

from context_graph.models import ContextEdgeUpdate  # noqa: E402
from context_graph.service import ContextGraphService  # noqa: E402
from life_reasoning import service as reasoning_service  # noqa: E402
from life_reasoning.models import ImpactAssessment, batch_key_for  # noqa: E402
from life_reasoning.repository import ImpactAssessmentRepository  # noqa: E402
from life_reasoning.service import ImpactReasoningService  # noqa: E402
from life_signals.service import LifeSignalService  # noqa: E402
from situations.models import SituationUpdate  # noqa: E402
from situations.service import SituationService  # noqa: E402

pytestmark = pytest.mark.asyncio

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class _FakeResult:
    def __init__(self, text: str):
        self.text = text
        self.provider = "fake"
        self.model = "fake-model"
        self.usage = {}


class _FakeManager:
    """Counts calls so a test can prove the batching policy really collapses
    correlated signals into one reasoning call."""

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


def _ok_output(**overrides):
    base = {
        "impacts": [
            {
                "statement": "Potrebbe servire una preparazione non ancora pianificata.",
                "kind": "dependency",
                "epistemic_status": "tentative",
                "confidence": 0.5,
                "affected_refs": [],
                "evidence_refs": [],
                "temporal_horizon": "near_term",
                "capability_hint": None,
            }
        ],
        "relevance": 0.6,
        "confidence": 0.5,
        "requires_more_context": False,
        "next_step_kind": "gather_context",
        "reason_summary": "Un cambiamento con possibili dipendenze aperte.",
    }
    base.update(overrides)
    return base


def _patch_manager(monkeypatch, manager):
    monkeypatch.setattr(
        reasoning_service, "get_manager", lambda: manager, raising=False
    )
    import llm.manager as llm_manager

    monkeypatch.setattr(llm_manager, "get_manager", lambda: manager)


async def _emit(db, user_id: str, ref: str, *, kind="created", system="situation",
                affected=None, dedupe=None):
    return await LifeSignalService(db).emit(
        user_id=user_id, source_ref=ref, source_system=system, change_kind=kind,
        dedupe_key=dedupe or f"{system}:{ref}:{uuid.uuid4().hex[:8]}",
        affected_refs=affected or [],
    )


async def _assessments(db, user_id: str):
    return await db.life_impact_assessments.find(
        {"user_id": user_id}, {"_id": 0},
    ).sort([("created_at", 1), ("id", 1)]).to_list(50)


async def _cleanup(db, user_id: str) -> None:
    await db.life_change_signals.delete_many({"user_id": user_id})
    await db.life_impact_assessments.delete_many({"user_id": user_id})
    await db.situations.delete_many({"user_id": user_id})
    await db.memories.delete_many({"user_id": user_id})
    await db.context_edges.delete_many({"user_id": user_id})
    await db.calendar_event_drafts.delete_many({"user_id": user_id})
    await db.life_os_plans.delete_many({"user_id": user_id})
    await db.proactive_suggestions.delete_many({"user_id": user_id})


# ---------------------------------------------------------------------------
# A / B — one signal, one assessment; replay is idempotent
# ---------------------------------------------------------------------------
async def test_a_single_pending_signal_produces_one_assessment(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        report = await ImpactReasoningService(db).run_pass(user)

        assert report.signals_seen == 1
        assert report.batches == 1
        assert report.ai_calls == 1
        assert report.assessments_created == 1
        rows = await _assessments(db, user)
        assert len(rows) == 1
        assert rows[0]["status"] in ("complete", "insufficient_evidence")
        assert len(rows[0]["impacts"]) == 1
        # The signal is consumed only now.
        assert await LifeSignalService(db).list_pending(user) == []
    finally:
        await _cleanup(db, user)
        client.close()


async def test_b_replayed_pass_creates_no_duplicate_assessment(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        ref = f"situation:sit_{uuid.uuid4().hex[:8]}"
        await _emit(db, user, ref)
        svc = ImpactReasoningService(db)
        await svc.run_pass(user)
        first_calls = manager.calls

        # Second pass: nothing pending, so no retrieval and no AI call at all.
        second = await svc.run_pass(user)
        assert second.signals_seen == 0
        assert second.ai_calls == 0
        assert manager.calls == first_calls
        assert len(await _assessments(db, user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_b2_same_batch_key_is_refused_by_storage(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        repo = ImpactAssessmentRepository(db)
        await repo.ensure_indexes()
        key = batch_key_for(user, ["lcs_a", "lcs_b"])
        # Batch identity is order-independent and stable.
        assert key == batch_key_for(user, ["lcs_b", "lcs_a"])
        await repo.insert(ImpactAssessment(user_id=user, batch_key=key))
        from life_reasoning.repository import DuplicateAssessment

        with pytest.raises(DuplicateAssessment):
            await repo.insert(ImpactAssessment(user_id=user, batch_key=key))
        assert await repo.count(user) == 1
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# C / D — batching policy
# ---------------------------------------------------------------------------
async def test_c_related_signals_collapse_into_one_reasoning_call(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        sid = f"situation:sit_{uuid.uuid4().hex[:8]}"
        plan = f"plan:plan_{uuid.uuid4().hex[:8]}"
        # Three signals sharing refs — one cluster.
        await _emit(db, user, sid, kind="created")
        await _emit(db, user, sid, kind="updated")
        await _emit(db, user, plan, system="life_os", affected=[sid])

        report = await ImpactReasoningService(db).run_pass(user)
        assert report.signals_seen == 3
        assert report.batches == 1, "correlated signals must share one batch"
        assert report.ai_calls == 1, "3 related signals must not cost 3 AI calls"
        assert report.signals_processed == 3
        rows = await _assessments(db, user)
        assert len(rows) == 1
        assert len(rows[0]["source_signal_ids"]) == 3
    finally:
        await _cleanup(db, user)
        client.close()


async def test_d_unrelated_signals_are_not_collapsed(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        await _emit(db, user, f"plan:plan_{uuid.uuid4().hex[:8]}", system="life_os")

        report = await ImpactReasoningService(db).run_pass(user)
        assert report.signals_seen == 2
        assert report.batches == 2, "unrelated lives must not contaminate each other"
        assert report.ai_calls == 2
        assert len(await _assessments(db, user)) == 2
    finally:
        await _cleanup(db, user)
        client.close()


async def test_r_signal_batch_is_bounded(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        for _ in range(12):
            await _emit(db, user, f"plan:plan_{uuid.uuid4().hex[:8]}", system="life_os")
        report = await ImpactReasoningService(db).run_pass(user)
        assert report.signals_seen <= reasoning_service.MAX_SIGNALS_PER_PASS
        assert report.batches <= reasoning_service.MAX_BATCHES_PER_PASS
        assert report.ai_calls <= reasoning_service.MAX_BATCHES_PER_PASS
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# E / F / H — context resolution and graph expansion
# ---------------------------------------------------------------------------
async def test_e_situation_and_linked_plan_both_reach_the_reasoning(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        created = await SituationService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_e",
            update=SituationUpdate(
                operation="create", summary="Un percorso personale in corso",
                linked_plan_id=plan_id,
            ),
        )
        sid = created["situation"]["id"]
        await _emit(db, user, f"situation:{sid}", affected=[f"plan:{plan_id}"])

        await ImpactReasoningService(db).run_pass(user)
        sent = manager.last_user or ""
        assert f"situation:{sid}" in sent
        assert f"plan:{plan_id}" in sent
        rows = await _assessments(db, user)
        assert f"situation:{sid}" in rows[0]["focal_refs"]
        assert f"plan:{plan_id}" in rows[0]["focal_refs"]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_f_calendar_change_reaches_linked_situation_via_graph(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        sid = f"situation:sit_{uuid.uuid4().hex[:8]}"
        cal = f"calendar:ced_{uuid.uuid4().hex[:8]}"
        await ContextGraphService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_f",
            updates=[ContextEdgeUpdate(
                operation="create", subject_ref=sid,
                predicate="scheduled_as", object_ref=cal,
            )],
        )
        await db.life_change_signals.delete_many({"user_id": user})
        await _emit(db, user, cal, kind="updated", system="calendar")

        await ImpactReasoningService(db).run_pass(user)
        sent = manager.last_user or ""
        # Bounded graph expansion pulled the linked Situation into view.
        assert cal in sent
        assert sid in sent
        assert "scheduled_as" in sent
    finally:
        await _cleanup(db, user)
        client.close()


async def test_h_graph_related_ref_enters_bounded_context(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        goal = f"goal:goal_{uuid.uuid4().hex[:8]}"
        plan = f"plan:plan_{uuid.uuid4().hex[:8]}"
        await ContextGraphService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_h",
            updates=[ContextEdgeUpdate(
                operation="create", subject_ref=goal,
                predicate="depends_on", object_ref=plan,
            )],
        )
        await db.life_change_signals.delete_many({"user_id": user})
        await _emit(db, user, goal, system="life_os")

        await ImpactReasoningService(db).run_pass(user)
        payload = json.loads(manager.last_user)
        relations = payload.get("known_relations") or []
        assert any(plan in r for r in relations)
        # ...and expansion stays bounded, never a global traversal.
        assert len(relations) <= 10
    finally:
        await _cleanup(db, user)
        client.close()


async def test_g_new_signals_after_correction_allow_a_new_assessment(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        ref = f"mem_{uuid.uuid4().hex[:12]}"
        await _emit(db, user, ref, kind="created", system="life_memory")
        svc = ImpactReasoningService(db)
        await svc.run_pass(user)
        first = await _assessments(db, user)
        assert len(first) == 1

        # A later correction is a NEW signal → a new, distinguishable assessment.
        await _emit(db, user, ref, kind="superseded", system="life_memory")
        await svc.run_pass(user)
        rows = await _assessments(db, user)
        assert len(rows) == 2
        assert rows[0]["batch_key"] != rows[1]["batch_key"]
        assert rows[0]["id"] != rows[1]["id"]
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# I / J / K / L — failure honesty and lifecycle
# ---------------------------------------------------------------------------
async def test_i_provider_failure_leaves_signal_pending(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    from llm.errors import LLMProviderUnavailable

    manager = _FakeManager(None, raises=LLMProviderUnavailable([
        {"provider": "gemini", "failure_kind": "quota", "retryable": True},
    ]))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        report = await ImpactReasoningService(db).run_pass(user)

        assert report.assessments_created == 0
        assert "provider_unavailable" in report.failures
        assert await _assessments(db, user) == []
        # The change is NOT lost: the signal stays pending for a later pass.
        assert len(await LifeSignalService(db).list_pending(user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_i2_unparseable_output_is_not_a_fake_assessment(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager("this is not json at all")
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        report = await ImpactReasoningService(db).run_pass(user)
        assert report.assessments_created == 0
        assert await _assessments(db, user) == []
        assert len(await LifeSignalService(db).list_pending(user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_j_context_failure_produces_no_false_complete_assessment(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)

    async def _boom(*args, **kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr(reasoning_service, "retrieve_evidence", _boom)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        report = await ImpactReasoningService(db).run_pass(user)

        # An unreadable life is not an empty life: no conclusion, no AI call.
        assert report.assessments_created == 0
        assert report.ai_calls == 0
        assert await _assessments(db, user) == []
        assert len(await LifeSignalService(db).list_pending(user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_k_assessment_persistence_failure_leaves_signal_pending(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)

    async def _boom(self, assessment):
        raise RuntimeError("assessment store unavailable")

    monkeypatch.setattr(ImpactAssessmentRepository, "insert", _boom)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        report = await ImpactReasoningService(db).run_pass(user)

        assert report.assessments_created == 0
        assert "assessment_persistence_failed" in report.failures
        # PERSIST BEFORE CONSUME.
        assert len(await LifeSignalService(db).list_pending(user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_l_signal_processed_only_after_assessment_persisted(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    observed = {}

    class _WatchingManager(_FakeManager):
        async def chat(self, **kwargs):
            # At reasoning time nothing is persisted and nothing is consumed.
            observed["assessments_at_ai_time"] = await db.life_impact_assessments.count_documents(
                {"user_id": user}
            )
            observed["pending_at_ai_time"] = await db.life_change_signals.count_documents(
                {"user_id": user, "status": "pending"}
            )
            return await super().chat(**kwargs)

    manager = _WatchingManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        await ImpactReasoningService(db).run_pass(user)

        assert observed["assessments_at_ai_time"] == 0
        assert observed["pending_at_ai_time"] == 1
        assert len(await _assessments(db, user)) == 1
        assert await db.life_change_signals.count_documents(
            {"user_id": user, "status": "processed"}
        ) == 1
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# M / N / O — no intervention in V2.9.2
# ---------------------------------------------------------------------------
async def test_m_no_proactive_suggestion_created(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output(relevance=1.0, confidence=1.0))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        await ImpactReasoningService(db).run_pass(user)
        assert len(await _assessments(db, user)) == 1
        # Even at maximum relevance, V2.9.2 stays silent.
        assert await db.proactive_suggestions.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_n_no_notification_and_no_attention_decision(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    # Even if the model tries to smuggle in an attention decision, the typed
    # contract has nowhere to put it.
    manager = _FakeManager(_ok_output(
        notify=True, send_now=True, surface_home=True, interrupt=True,
        notification_text="Dovresti saperlo subito",
    ))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        await ImpactReasoningService(db).run_pass(user)
        row = (await _assessments(db, user))[0]
        for forbidden in (
            "notify", "send_now", "surface_home", "interrupt",
            "notification_text", "batch_notification",
        ):
            assert forbidden not in row
        assert "Dovresti saperlo subito" not in json.dumps(row, ensure_ascii=False)
    finally:
        await _cleanup(db, user)
        client.close()


async def test_o_no_tool_write_executed(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output(impacts=[{
        "statement": "Un evento potrebbe essere utile.",
        "kind": "opportunity", "epistemic_status": "tentative", "confidence": 0.5,
        "capability_hint": "create_calendar_event",
    }]))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        await ImpactReasoningService(db).run_pass(user)
        row = (await _assessments(db, user))[0]
        # The capability may be POINTED AT...
        assert row["impacts"][0]["capability_hint"] == "create_calendar_event"
        # ...but nothing was written anywhere.
        assert await db.calendar_event_drafts.count_documents({"user_id": user}) == 0
        assert await db.life_os_plans.count_documents({"user_id": user}) == 0
        assert await db.context_edges.count_documents({"user_id": user}) == 0
        assert await db.memories.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_o2_invented_capability_hint_is_dropped(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output(impacts=[{
        "statement": "Servirebbe un confronto.",
        "kind": "opportunity", "epistemic_status": "tentative", "confidence": 0.5,
        "capability_hint": "compare_mortgage_offers",
    }]))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        await ImpactReasoningService(db).run_pass(user)
        row = (await _assessments(db, user))[0]
        assert row["impacts"][0]["capability_hint"] is None
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# P / Q — isolation and bounds
# ---------------------------------------------------------------------------
async def test_p_user_isolation(monkeypatch):
    client, db = _db()
    user_a = f"u_{uuid.uuid4().hex[:8]}"
    user_b = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user_a, f"situation:sit_{uuid.uuid4().hex[:8]}")
        svc = ImpactReasoningService(db)

        report_b = await svc.run_pass(user_b)
        assert report_b.signals_seen == 0
        assert report_b.ai_calls == 0, "a user with no pending signals costs nothing"

        await svc.run_pass(user_a)
        assert len(await _assessments(db, user_a)) == 1
        assert await _assessments(db, user_b) == []
        assert await ImpactAssessmentRepository(db).count(user_b) == 0
    finally:
        await _cleanup(db, user_a)
        await _cleanup(db, user_b)
        client.close()


async def test_q_evidence_and_impacts_are_bounded(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output(impacts=[
        {
            "statement": f"Conseguenza numero {i}",
            "kind": "dependency", "epistemic_status": "tentative", "confidence": 0.3,
        }
        for i in range(30)
    ]))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        await ImpactReasoningService(db).run_pass(user)
        row = (await _assessments(db, user))[0]
        from life_reasoning.models import MAX_IMPACTS

        assert len(row["impacts"]) <= MAX_IMPACTS
        payload = json.loads(manager.last_user)
        assert len(payload.get("evidence") or []) <= 8
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# S / T / U — privacy and contract hygiene
# ---------------------------------------------------------------------------
async def test_s_assessment_carries_no_raw_conversation_text(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        await SituationService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_s",
            update=SituationUpdate(
                operation="create",
                summary="Sto affrontando una questione personale molto riservata",
            ),
        )
        await db.life_change_signals.delete_many({"user_id": user})
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")

        await ImpactReasoningService(db).run_pass(user)
        row = (await _assessments(db, user))[0]
        assert set(row.keys()) == {
            "id", "user_id", "source_signal_ids", "focal_refs", "impacts",
            "relevance", "confidence", "requires_more_context", "next_step_kind",
            "reason_summary", "evidence_refs", "evidence_count", "batch_key",
            "status", "model_provider", "model_name", "created_at",
            # V2.9.3 downstream lifecycle marker — a flag, not content.
            "attention_status",
        }
        # Evidence is referenced, never copied into the store.
        assert isinstance(row["evidence_refs"], list)
        assert isinstance(row["evidence_count"], int)
    finally:
        await _cleanup(db, user)
        client.close()


async def test_t_assessment_carries_no_raw_document_content(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"document:doc_{uuid.uuid4().hex[:8]}", system="life_os")
        await ImpactReasoningService(db).run_pass(user)
        row = (await _assessments(db, user))[0]
        blob = json.dumps(row, ensure_ascii=False)
        for forbidden in ("content", "raw_text", "body", "file_bytes", "blob"):
            assert f'"{forbidden}"' not in blob
    finally:
        await _cleanup(db, user)
        client.close()


async def test_u_no_chain_of_thought_field_requested_or_stored(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output(
        chain_of_thought="Prima ho pensato... poi ho dedotto...",
        thinking="passaggio interno",
    ))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        await ImpactReasoningService(db).run_pass(user)
        row = (await _assessments(db, user))[0]
        for forbidden in ("chain_of_thought", "thinking", "reasoning_trace", "scratchpad"):
            assert forbidden not in row
        # The prompt asks for conclusions, explicitly not for the process.
        assert "chain of thought" not in (manager.last_system or "").lower()
        assert "not how you thought" in (manager.last_system or "")
    finally:
        await _cleanup(db, user)
        client.close()


async def test_v_facts_and_hypotheses_are_distinguishable(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output(impacts=[
        {
            "statement": "Un fatto supportato dall'evidenza.",
            "kind": "constraint", "epistemic_status": "confirmed", "confidence": 0.9,
        },
        {
            "statement": "Una possibilità non ancora verificata.",
            "kind": "dependency", "epistemic_status": "tentative", "confidence": 0.35,
        },
    ]))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"situation:sit_{uuid.uuid4().hex[:8]}")
        await ImpactReasoningService(db).run_pass(user)
        impacts = (await _assessments(db, user))[0]["impacts"]
        statuses = {i["epistemic_status"] for i in impacts}
        assert "confirmed" in statuses and "tentative" in statuses
        confirmed = next(i for i in impacts if i["epistemic_status"] == "confirmed")
        tentative = next(i for i in impacts if i["epistemic_status"] == "tentative")
        assert confirmed["confidence"] > tentative["confidence"]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_w_possible_need_discovery_is_representable(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output(
        impacts=[
            {
                "statement": "Potrebbe servire una risorsa non ancora individuata.",
                "kind": "dependency", "epistemic_status": "tentative", "confidence": 0.4,
            },
            {
                "statement": "Manca un'informazione per procedere.",
                "kind": "missing_information", "epistemic_status": "inferred",
                "confidence": 0.5,
            },
            {
                "statement": "Potrebbe valere la pena confrontare le opzioni disponibili.",
                "kind": "opportunity", "epistemic_status": "tentative", "confidence": 0.4,
            },
        ],
        requires_more_context=True, next_step_kind="compare_options",
    ))
    _patch_manager(monkeypatch, manager)
    try:
        await _emit(db, user, f"goal:goal_{uuid.uuid4().hex[:8]}", system="life_os")
        await ImpactReasoningService(db).run_pass(user)
        row = (await _assessments(db, user))[0]
        kinds = {i["kind"] for i in row["impacts"]}
        assert {"dependency", "missing_information", "opportunity"} <= kinds
        assert row["requires_more_context"] is True
        assert row["next_step_kind"] == "compare_options"
        # A discovered need stays possible — nothing was auto-created.
        assert await db.life_os_plans.count_documents({"user_id": user}) == 0
        assert await db.calendar_event_drafts.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# X — arbitrary life scenarios
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "summary",
    [
        "Sto organizzando una mostra fotografica",
        "Ho iniziato a prendermi cura di un bonsai",
        "Sto valutando di acquistare qualcosa di importante",
        "Stiamo organizzando una festa di quartiere",
    ],
)
async def test_x_arbitrary_life_scenarios_take_the_same_path(monkeypatch, summary):
    """The pipeline is domain-blind: an unanticipated life area traverses the
    identical code path, with no branch anywhere reacting to its subject."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    manager = _FakeManager(_ok_output())
    _patch_manager(monkeypatch, manager)
    try:
        created = await SituationService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_x",
            update=SituationUpdate(operation="create", summary=summary),
        )
        await db.life_change_signals.delete_many({"user_id": user})
        await _emit(db, user, f"situation:{created['situation']['id']}")

        report = await ImpactReasoningService(db).run_pass(user)
        assert report.batches == 1
        assert report.ai_calls == 1
        assert report.assessments_created == 1
        row = (await _assessments(db, user))[0]
        assert "domain" not in row
        assert "category" not in row
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# Y / Z — static guarantees
# ---------------------------------------------------------------------------
_PRODUCTION_FILES = [
    Path(_BACKEND) / "life_reasoning" / "models.py",
    Path(_BACKEND) / "life_reasoning" / "service.py",
    Path(_BACKEND) / "life_reasoning" / "repository.py",
    Path(_BACKEND) / "life_reasoning" / "context.py",
]

_FORBIDDEN_DOMAIN_TERMS = (
    "house", "home purchase", "mortgage", "mutuo", "notary", "notaio",
    "insurance", "assicurazione", "car", "auto", "travel", "viaggio",
    "study", "medical", "medico", "bonsai", "party", "festa", "exhibition",
    "mostra",
)


def _code_only(path: Path) -> str:
    """Source with docstrings and comments removed.

    The audit must judge CODE, not documentation: a docstring saying "there is
    no house/travel/study member here" is the architecture being stated, not
    violated. A naive substring scan flags exactly the comments that promise
    the rule, which is the opposite of what the gate is for.
    """
    import ast
    import re as _re

    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    drop: set = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
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


async def test_y_no_domain_router_in_production_code():
    import re

    for path in _PRODUCTION_FILES:
        code = _code_only(path).lower()
        for term in _FORBIDDEN_DOMAIN_TERMS:
            assert not re.search(rf"\b{re.escape(term)}\b", code), (
                f"{term} leaked into executable code of {path.name}"
            )


async def test_y2_no_keyword_branch_in_production_code():
    import re

    keyword_branch = re.compile(r'if\s+["\'][a-z_ ]+["\']\s+in\s+(?!\w*(?:_NEXT_STEPS|known))')
    for path in _PRODUCTION_FILES:
        assert not keyword_branch.search(_code_only(path)), (
            f"keyword routing in {path.name}"
        )


async def test_z_no_direct_vendor_call_outside_provider_manager():
    import re

    vendor = re.compile(
        r"(?:^|\s)(?:import|from)\s+\S*\b(?:google|genai|openai|anthropic|ollama)\b"
        r"|GenerativeModel|generativelanguage|api\.openai\.com",
        re.MULTILINE,
    )
    for path in _PRODUCTION_FILES:
        text = path.read_text(encoding="utf-8")
        assert not vendor.search(text), f"direct vendor access in {path.name}"
    # ...and the one provider entry point really is the manager.
    service_text = (Path(_BACKEND) / "life_reasoning" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "from llm.manager import get_manager" in service_text


async def test_z2_no_polling_or_worker_introduced():
    for path in _PRODUCTION_FILES:
        code = _code_only(path).lower()
        for term in ("cron", "scheduler", "asyncio.sleep", "while true", "create_task"):
            assert term not in code, f"{term} introduced in {path.name}"


async def test_z3_prompt_forbids_intervention_and_protects_user_interest():
    from life_reasoning.prompt import IMPACT_SYSTEM_PROMPT

    # Normalise wrapping: the prompt is hard-wrapped, so a phrase can straddle
    # a newline and a naive substring check would miss it.
    lowered = " ".join(IMPACT_SYSTEM_PROMPT.lower().split())
    # No intervention decision.
    assert "do not decide whether to tell the user" in lowered
    assert "notification" in lowered and "do not produce" in lowered
    # No invention.
    assert "never invent" in lowered
    # Commercial neutrality / user interest.
    assert "optimise for the user's interest" in lowered
    assert "never for whoever might be selling" in lowered
    assert "never name a specific company, product, vendor, brand or offer" in lowered
    # No domain taxonomy smuggled into the prompt's routing.
    assert "reason from this user's evidence" in lowered
