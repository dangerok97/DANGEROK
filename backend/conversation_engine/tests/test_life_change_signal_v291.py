"""V2.9.1 — Life Change Signal foundation (deterministic, A-Z).

Real MongoDB test DB throughout, matching the V2.8.6b calendar suite: the
signal store, the mutation subsystems and the cognitive loop all use real
collections, so a test that claims "one signal was written" really means a
document exists.

Uses `@pytest.mark.asyncio` with module-level `async def` functions — the
convention already proven to coexist with `test_ai_core_connectivity.py`'s
anyio TestClient fixtures in this directory.

The central assertion of the whole sprint is negative: V2.9.1 answers
"WHAT CHANGED?" and must never answer "SO WHAT?" or "SHOULD I SPEAK?".
Tests X/Y/Z and the generality block exist to keep that boundary honest.
"""
from __future__ import annotations

import os
import sys
import uuid
from copy import deepcopy
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

from conversation_engine.ai_core.loop import run_cognitive_loop  # noqa: E402
from conversation_engine.ai_core.tools import calendar_caps  # noqa: E402
from conversation_engine.models import ConversationSession  # noqa: E402
from context_graph.models import ContextEdgeUpdate  # noqa: E402
from context_graph.service import ContextGraphService  # noqa: E402
from life_signals import emitters as life_signals  # noqa: E402
from life_signals.repository import LifeSignalRepository  # noqa: E402
from life_signals.service import LifeSignalService  # noqa: E402
from permissions.service import PermissionService  # noqa: E402
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


def _runtime(db, user_id: str, epoch: str = "") -> dict:
    """
    The runtime a calendar capability now receives.

    `user_message` and `pending_act` say what this suite always assumed and
    could not previously state: ORA proposed the write and the person agreed.
    The runtime used to take that on the model's word; it checks now, so the
    confirmation has to be present rather than implied.
    """
    return {
        "user_id": user_id, "db": db, "reasoning_epoch": epoch, "session_id": "s1",
        "user_message": "sì, va bene",
        "pending_act": {"at": "test", "asked": "Lo segno in calendario?"},
    }


def _sess(user_id: str, *, proposed: bool = False) -> ConversationSession:
    """
    A session, optionally one in which ORA has just proposed something.

    `proposed` is what makes a confirmation a confirmation of anything: it
    records that ORA asked. It used to be implicit — the model remembered its
    own last turn and the runtime believed it — and is now written into the
    session so code can check that the question was actually put.
    """
    state = (
        {"pending_act": {"at": "test", "asked": "Lo segno in calendario?"}}
        if proposed else {}
    )
    return ConversationSession(
        user_id=user_id, meta={"ui_mode": "ai_core", "ai_core": state}
    )


def _decision(mode="answer", **extra):
    raw = {
        "response_mode": mode,
        "user_intent_summary": "arbitrary life turn",
        "reasoning_status": "needs_user_input" if mode == "ask" else "enough_information",
        "message_to_user": "Ok." if mode not in ("ask",) else None,
        "question": "Cosa intendi?" if mode == "ask" else None,
    }
    raw.update(extra)
    return raw


class _Scripted:
    """Scripted decision function that counts its own invocations, so a test
    can prove the signal layer added zero extra AI calls."""

    def __init__(self, items):
        self.queue = [deepcopy(x) for x in items]
        self.calls = 0

    async def __call__(self, _system, _user):
        self.calls += 1
        return self.queue.pop(0)


async def _grant_calendar_write(db, user_id: str) -> None:
    await PermissionService(db).grant(
        user_id=user_id, capability_id="calendar.write", connector_id="calendar_google",
    )


async def _signals(db, user_id: str):
    return await db.life_change_signals.find(
        {"user_id": user_id}, {"_id": 0},
    ).sort([("created_at", 1), ("id", 1)]).to_list(50)


async def _cleanup(db, user_id: str) -> None:
    await db.life_change_signals.delete_many({"user_id": user_id})
    await db.situations.delete_many({"user_id": user_id})
    await db.memories.delete_many({"user_id": user_id})
    await db.context_edges.delete_many({"user_id": user_id})
    await db.calendar_event_drafts.delete_many({"user_id": user_id})
    await db.permission_consents.delete_many({"user_id": user_id})
    await db.life_os_plans.delete_many({"user_id": user_id})
    await db.proactive_suggestions.delete_many({"user_id": user_id})


@pytest.fixture(autouse=True)
def _isolate_google_calendar_service():
    """Calendar write handlers resolve their sync service through
    `deps.get_google_calendar_service()` before the consent check, which would
    otherwise bind the app's real `.env` Motor client to this test's event
    loop. Bind it to a throwaway test-scoped service instead (same reasoning
    as the V2.8.6b suite)."""
    import deps as deps_module
    from connectors.google_calendar import GoogleCalendarService
    from security.token_vault import build_token_vault

    client, db = _db()
    original = deps_module.get_google_calendar_service
    stub = GoogleCalendarService(
        db=db, permissions=PermissionService(db), ingestion=None,
        vault=build_token_vault(db),
    )
    deps_module.get_google_calendar_service = lambda: stub
    yield
    deps_module.get_google_calendar_service = original
    client.close()


# ---------------------------------------------------------------------------
# A / B / C — Situation
# ---------------------------------------------------------------------------
async def test_a_situation_create_emits_exactly_one_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        result = await SituationService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_a1",
            update=SituationUpdate(operation="create", summary="Qualcosa è iniziato"),
        )
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_a1",
            operation="create", result=result,
        )
        rows = await _signals(db, user)
        assert len(rows) == 1
        assert rows[0]["source_system"] == "situation"
        assert rows[0]["change_kind"] == "created"
        assert rows[0]["source_ref"].startswith("situation:")
        assert rows[0]["status"] == "pending"
        assert rows[0]["revision"] == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_b_situation_retry_same_epoch_no_duplicate_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        svc = SituationService(db)
        update = SituationUpdate(operation="create", summary="Qualcosa è iniziato")
        first = await svc.apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_b1", update=update,
        )
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_b1",
            operation="create", result=first,
        )
        # Same epoch replay — the subsystem itself reports deduped=True.
        second = await svc.apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_b1", update=update,
        )
        assert second.get("deduped") is True
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_b1",
            operation="create", result=second,
        )
        assert len(await _signals(db, user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_c_situation_real_update_emits_distinguishable_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        svc = SituationService(db)
        created = await svc.apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_c1",
            update=SituationUpdate(operation="create", summary="Stato iniziale"),
        )
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_c1",
            operation="create", result=created,
        )
        sid = created["situation"]["id"]
        updated = await svc.apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_c2",
            update=SituationUpdate(
                operation="update", situation_id=sid, facts=["un fatto nuovo"],
            ),
        )
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_c2",
            operation="update", result=updated,
        )
        rows = await _signals(db, user)
        assert len(rows) == 2
        assert [r["change_kind"] for r in rows] == ["created", "updated"]
        # Same entity, different revision — the consumer can tell them apart.
        assert rows[0]["source_ref"] == rows[1]["source_ref"]
        assert rows[0]["revision"] == 1 and rows[1]["revision"] == 2
        assert rows[0]["dedupe_key"] != rows[1]["dedupe_key"]
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# D / E — Life Memory
# ---------------------------------------------------------------------------
def _durable_candidate(summary: str):
    from conversation_engine.ai_core.models import MemoryCandidate

    return MemoryCandidate(
        operation="propose", summary=summary, kind="fact",
        authority="user_stated", epistemic_status="confirmed", permanence="durable",
        confidence=0.95, reason_for_future_utility="serve nelle conversazioni future",
        user_authorized=True,
    )


async def test_d_memory_persisted_emits_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        from life_memory.governance import MemoryGovernanceService

        outcomes = await MemoryGovernanceService(db).process(
            user_id=user, session_id="s1", reasoning_epoch="ep_d1",
            candidates=[_durable_candidate("Un fatto durevole")],
        )
        assert outcomes[0].persisted is True
        await life_signals.emit_memory_signals(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_d1",
            outcomes=outcomes,
        )
        rows = await _signals(db, user)
        assert len(rows) == 1
        assert rows[0]["source_system"] == "life_memory"
        assert rows[0]["change_kind"] == "created"
        assert rows[0]["source_ref"].startswith("mem_")
    finally:
        await _cleanup(db, user)
        client.close()


async def test_e_memory_idempotent_replay_no_duplicate_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        from life_memory.governance import MemoryGovernanceService

        svc = MemoryGovernanceService(db)
        candidate = _durable_candidate("Un fatto durevole")
        first = await svc.process(
            user_id=user, session_id="s1", reasoning_epoch="ep_e1",
            candidates=[candidate],
        )
        await life_signals.emit_memory_signals(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_e1", outcomes=first,
        )
        second = await svc.process(
            user_id=user, session_id="s1", reasoning_epoch="ep_e1",
            candidates=[candidate],
        )
        assert second[0].code == "IDEMPOTENT_REPLAY"
        await life_signals.emit_memory_signals(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_e1", outcomes=second,
        )
        assert len(await _signals(db, user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# F / G — Context Graph
# ---------------------------------------------------------------------------
async def test_f_context_graph_edge_persisted_emits_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        subject = f"goal:goal_{uuid.uuid4().hex[:8]}"
        obj = f"plan:plan_{uuid.uuid4().hex[:8]}"
        results = await ContextGraphService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_f1",
            updates=[ContextEdgeUpdate(
                operation="create", subject_ref=subject,
                predicate="depends_on", object_ref=obj,
            )],
        )
        assert results[0]["persisted"] is True
        await life_signals.emit_context_graph_signals(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_f1", results=results,
        )
        rows = await _signals(db, user)
        assert len(rows) == 1
        assert rows[0]["source_system"] == "context_graph"
        assert rows[0]["change_kind"] == "linked"
        # The edge id is not a canonical ref: the signal points at the subject
        # whose relationships changed, with the object as a deterministic
        # affected ref — never invented graph expansion.
        assert rows[0]["source_ref"] == subject
        assert rows[0]["affected_refs"] == [obj]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_g_context_graph_replay_same_governance_key_no_duplicate():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        svc = ContextGraphService(db)
        update = ContextEdgeUpdate(
            operation="create", subject_ref=f"goal:goal_{uuid.uuid4().hex[:8]}",
            predicate="depends_on", object_ref=f"plan:plan_{uuid.uuid4().hex[:8]}",
        )
        first = await svc.apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_g1", updates=[update],
        )
        await life_signals.emit_context_graph_signals(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_g1", results=first,
        )
        second = await svc.apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_g1", updates=[update],
        )
        assert second[0]["decision"] == "IDEMPOTENT_REPLAY"
        await life_signals.emit_context_graph_signals(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_g1", results=second,
        )
        assert len(await _signals(db, user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# H / I / J / K / L / M — Calendar (V2.8.6b semantics preserved)
# ---------------------------------------------------------------------------
async def test_h_calendar_create_confirmed_emits_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_calendar_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        sess = _sess(user, proposed=True)
        decide = _Scripted([
            _decision(mode="tool", tool_call={
                "capability": "create_calendar_event",
                "arguments": {"title": "Un impegno", "start_datetime": start},
            }),
            _decision(mode="answer", message_to_user="Fatto."),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Sì, confermo.", db=db, decision_fn=decide,
        )
        assert out.mode == "answer"
        rows = await _signals(db, user)
        assert len(rows) == 1
        assert rows[0]["source_system"] == "calendar"
        assert rows[0]["change_kind"] == "created"
        assert rows[0]["source_ref"].startswith("calendar:ced_")
    finally:
        await _cleanup(db, user)
        client.close()


async def test_i_calendar_proposal_not_confirmed_emits_zero_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_calendar_write(db, user)
        sess = _sess(user)
        decide = _Scripted([
            _decision(mode="act", message_to_user="Vuoi che lo aggiunga in calendario?"),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Domani alle 18 devo fare una cosa.",
            db=db, decision_fn=decide,
        )
        assert out.mode == "act"
        assert await _signals(db, user) == []
        assert await db.calendar_event_drafts.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_j_calendar_update_emits_signal_same_ref_new_mutation():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_calendar_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Un impegno", "start_datetime": start},
            _runtime(db, user, "ep_j1"),
        )
        ref = created.payload["calendar_ref"]
        await life_signals.emit_calendar_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_j1",
            capability="create_calendar_event", observation_status=created.status,
            payload=created.payload,
        )
        new_start = _iso(datetime.now(timezone.utc) + timedelta(hours=3))
        updated = await calendar_caps.update_calendar_event(
            {"calendar_ref": ref, "start_datetime": new_start},
            _runtime(db, user, "ep_j2"),
        )
        await life_signals.emit_calendar_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_j2",
            capability="update_calendar_event", observation_status=updated.status,
            payload=updated.payload,
        )
        rows = await _signals(db, user)
        assert len(rows) == 2
        assert rows[0]["source_ref"] == rows[1]["source_ref"] == ref
        assert [r["change_kind"] for r in rows] == ["created", "updated"]
        assert rows[0]["dedupe_key"] != rows[1]["dedupe_key"]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_k_calendar_cancel_emits_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_calendar_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Un impegno", "start_datetime": start},
            _runtime(db, user, "ep_k1"),
        )
        ref = created.payload["calendar_ref"]
        cancelled = await calendar_caps.cancel_calendar_event(
            {"calendar_ref": ref}, _runtime(db, user, "ep_k2"),
        )
        assert cancelled.status == "ok"
        await life_signals.emit_calendar_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_k2",
            capability="cancel_calendar_event", observation_status=cancelled.status,
            payload=cancelled.payload,
        )
        rows = await _signals(db, user)
        assert len(rows) == 1
        assert rows[0]["change_kind"] == "cancelled"

        # An already-cancelled replay is a no-op, not a new life change.
        replay = await calendar_caps.cancel_calendar_event(
            {"calendar_ref": ref}, _runtime(db, user, "ep_k3"),
        )
        assert replay.payload["operation"] == "already_cancelled"
        await life_signals.emit_calendar_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_k3",
            capability="cancel_calendar_event", observation_status=replay.status,
            payload=replay.payload,
        )
        assert len(await _signals(db, user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_l_calendar_failure_before_persistence_emits_zero_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        # No calendar.write consent — nothing is persisted anywhere.
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        denied = await calendar_caps.create_calendar_event(
            {"title": "Non autorizzato", "start_datetime": start},
            _runtime(db, user, "ep_l1"),
        )
        assert denied.status == "consent_required"
        await life_signals.emit_calendar_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_l1",
            capability="create_calendar_event", observation_status=denied.status,
            payload=denied.payload,
        )
        assert await _signals(db, user) == []
        assert await db.calendar_event_drafts.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_m_calendar_local_success_google_partial_still_emits_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_calendar_write(db, user)  # consent, but Google not connected
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Un impegno", "start_datetime": start},
            _runtime(db, user, "ep_m1"),
        )
        # V2.8.6b contract: local state persisted, Google sync unconfirmed.
        assert created.status == "partial"
        await life_signals.emit_calendar_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_m1",
            capability="create_calendar_event", observation_status=created.status,
            payload=created.payload,
        )
        rows = await _signals(db, user)
        assert len(rows) == 1, "ORA's own state changed — the signal is legitimate"
        # ...and the consumer can still tell Google never confirmed.
        assert rows[0]["source_status"] == "partial"
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# N / O / P / Q — store semantics and consumer contract
# ---------------------------------------------------------------------------
async def test_n_cross_user_isolation():
    client, db = _db()
    user_a = f"u_{uuid.uuid4().hex[:8]}"
    user_b = f"u_{uuid.uuid4().hex[:8]}"
    try:
        result = await SituationService(db).apply(
            user_id=user_a, session_id="s1", reasoning_epoch="ep_n1",
            update=SituationUpdate(operation="create", summary="Riservato ad A"),
        )
        await life_signals.emit_situation_signal(
            db, user_id=user_a, session_id="s1", reasoning_epoch="ep_n1",
            operation="create", result=result,
        )
        svc = LifeSignalService(db)
        assert len(await svc.list_pending(user_a)) == 1
        assert await svc.list_pending(user_b) == []
        assert await svc.count_pending(user_b) == 0
        # B can never mark A's signal processed.
        a_rows = await _signals(db, user_a)
        assert await svc.mark_processed(user_b, [a_rows[0]["id"]]) == 0
        assert (await _signals(db, user_a))[0]["status"] == "pending"
    finally:
        await _cleanup(db, user_a)
        await _cleanup(db, user_b)
        client.close()


async def test_o_pending_list_is_bounded():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        svc = LifeSignalService(db)
        for i in range(25):
            await svc.emit(
                user_id=user, source_ref=f"plan:plan_{i:04d}",
                source_system="life_os", change_kind="created",
                dedupe_key=f"life_os:plan_{i:04d}:ep_o:create_plan",
            )
        assert await svc.count_pending(user) == 25
        assert len(await svc.list_pending(user)) == 20  # module cap
        assert len(await svc.list_pending(user, limit=5)) == 5
        assert len(await svc.list_pending(user, limit=999)) == 20  # cap wins
    finally:
        await _cleanup(db, user)
        client.close()


async def test_p_ordering_is_deterministic():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        svc = LifeSignalService(db)
        for i in range(8):
            await svc.emit(
                user_id=user, source_ref=f"plan:plan_{i:04d}",
                source_system="life_os", change_kind="created",
                dedupe_key=f"life_os:plan_{i:04d}:ep_p:create_plan",
            )
        first = [s["id"] for s in await svc.list_pending(user)]
        second = [s["id"] for s in await svc.list_pending(user)]
        third = [s["id"] for s in await svc.list_pending(user)]
        assert first == second == third
        assert len(set(first)) == 8
    finally:
        await _cleanup(db, user)
        client.close()


async def test_q_mark_processed_does_not_touch_source_entity():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        result = await SituationService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_q1",
            update=SituationUpdate(operation="create", summary="Stato invariato"),
        )
        sid = result["situation"]["id"]
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_q1",
            operation="create", result=result,
        )
        before = await db.situations.find_one({"user_id": user, "id": sid}, {"_id": 0})

        svc = LifeSignalService(db)
        rows = await _signals(db, user)
        assert await svc.mark_processed(user, [rows[0]["id"]]) == 1
        assert (await _signals(db, user))[0]["status"] == "processed"
        assert await svc.list_pending(user) == []

        after = await db.situations.find_one({"user_id": user, "id": sid}, {"_id": 0})
        assert after == before, "consuming a signal must never mutate the life entity"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_r_signal_failure_does_not_corrupt_primary_mutation(monkeypatch):
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        async def _boom(self, signal):
            raise RuntimeError("signal store unavailable")

        monkeypatch.setattr(LifeSignalRepository, "insert", _boom)

        await _grant_calendar_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        sess = _sess(user, proposed=True)
        decide = _Scripted([
            _decision(mode="tool", tool_call={
                "capability": "create_calendar_event",
                "arguments": {"title": "Un impegno", "start_datetime": start},
            }),
            _decision(mode="answer", message_to_user="Fatto."),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Sì, confermo.", db=db, decision_fn=decide,
        )
        # The turn completed and the real life state is intact...
        assert out.ok is True
        assert await db.calendar_event_drafts.count_documents({"user_id": user}) == 1
        # ...only the derived event was lost, and it is not silently swallowed.
        assert await _signals(db, user) == []
    finally:
        await _cleanup(db, user)
        client.close()


async def test_s_no_new_llm_calls():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_calendar_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        sess = _sess(user, proposed=True)
        decide = _Scripted([
            _decision(mode="tool", tool_call={
                "capability": "create_calendar_event",
                "arguments": {"title": "Un impegno", "start_datetime": start},
            }),
            _decision(mode="answer", message_to_user="Fatto."),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Sì, confermo.", db=db, decision_fn=decide,
        )
        # A signal really was produced this turn...
        assert len(await _signals(db, user)) == 1
        # ...and it cost exactly the reasoning calls the turn already needed.
        assert decide.calls == 2
        assert out.ai_calls == 2
    finally:
        await _cleanup(db, user)
        client.close()


async def test_t_read_only_retrieval_emits_zero_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_calendar_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        await calendar_caps.create_calendar_event(
            {"title": "Un impegno", "start_datetime": start},
            _runtime(db, user, "ep_t0"),
        )
        await db.life_change_signals.delete_many({"user_id": user})

        sess = _sess(user)
        decide = _Scripted([
            _decision(mode="tool", tool_call={
                "capability": "get_calendar_events", "arguments": {},
            }),
            _decision(mode="context", context_need={
                "query": "impegni", "purpose": "rispondere",
                "source_hints": ["calendar"],
            }),
            _decision(mode="answer", message_to_user="Ecco cosa hai."),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Cosa ho in programma?", db=db, decision_fn=decide,
        )
        assert out.mode == "answer"
        assert await _signals(db, user) == [], "reads never change life state"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_u_life_os_plan_creation_emits_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        sess = _sess(user)
        decide = _Scripted([
            _decision(mode="tool", tool_call={
                "capability": "create_plan",
                "arguments": {
                    "summary": "Un percorso personale",
                    "items": [{"title": "Primo passo", "order": 0}],
                },
            }),
            _decision(mode="answer", message_to_user="Fatto."),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Aiutami a organizzarmi.", db=db, decision_fn=decide,
        )
        assert out.mode == "answer"
        rows = await _signals(db, user)
        assert len(rows) == 1
        assert rows[0]["source_system"] == "life_os"
        assert rows[0]["change_kind"] == "created"
        assert rows[0]["source_ref"].startswith("plan:")
    finally:
        await _cleanup(db, user)
        client.close()


async def test_v_noop_update_emits_zero_signal():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        # operation="none" is the subsystem's own explicit no-op.
        result = await SituationService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_v1",
            update=SituationUpdate(operation="none"),
        )
        assert result == {"status": "noop"}
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_v1",
            operation="none", result=result,
        )
        # A graph proposal that resolves to NOOP likewise changed nothing.
        graph = await ContextGraphService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_v2",
            updates=[ContextEdgeUpdate(operation="none")],
        )
        assert graph[0]["decision"] == "NOOP"
        await life_signals.emit_context_graph_signals(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_v2", results=graph,
        )
        assert await _signals(db, user) == []
    finally:
        await _cleanup(db, user)
        client.close()


async def test_w_signal_payload_carries_no_raw_conversation_text():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    secret = "Sto attraversando un momento personale molto delicato e riservato"
    try:
        result = await SituationService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_w1",
            update=SituationUpdate(
                operation="create", summary=secret, facts=[secret],
            ),
        )
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_w1",
            operation="create", result=result,
        )
        rows = await _signals(db, user)
        assert len(rows) == 1
        blob = str(rows[0]).lower()
        assert "delicato" not in blob and "riservato" not in blob
        # The stored shape is refs + technical metadata only.
        assert set(rows[0].keys()) == {
            "id", "user_id", "source_ref", "source_system", "change_kind",
            "affected_refs", "revision", "authority", "source_status",
            "provenance", "occurred_at", "dedupe_key", "session_id",
            "reasoning_epoch", "status", "attempts", "last_error_code",
            "created_at", "processed_at",
        }
    finally:
        await _cleanup(db, user)
        client.close()


async def test_x_signal_never_creates_context_graph_edge():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_calendar_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Un impegno", "start_datetime": start},
            _runtime(db, user, "ep_x1"),
        )
        await life_signals.emit_calendar_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_x1",
            capability="create_calendar_event", observation_status=created.status,
            payload=created.payload,
        )
        assert len(await _signals(db, user)) == 1
        assert await db.context_edges.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_y_signal_never_creates_proactive_suggestion():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        result = await SituationService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_y1",
            update=SituationUpdate(operation="create", summary="Qualcosa è cambiato"),
        )
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_y1",
            operation="create", result=result,
        )
        assert len(await _signals(db, user)) == 1
        # V2.9.1 answers "WHAT CHANGED?" only — never "SHOULD I SPEAK?".
        assert await db.proactive_suggestions.count_documents({"user_id": user}) == 0
        # ...and emitting is terminal: no second signal, no cascade.
        assert len(await _signals(db, user)) == 1
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# Z — no domain routing in production code
# ---------------------------------------------------------------------------
_PRODUCTION_FILES = [
    Path(_BACKEND) / "life_signals" / "models.py",
    Path(_BACKEND) / "life_signals" / "service.py",
    Path(_BACKEND) / "life_signals" / "repository.py",
    Path(_BACKEND) / "life_signals" / "emitters.py",
]

_FORBIDDEN_DOMAIN_TERMS = (
    "house", "mortgage", "mutuo", "notaio", "insurance", "assicurazione",
    "travel", "viaggio", "study", "studio", "medical", "medico",
    "bonsai", "mostra", "festa",
)


async def test_z_no_domain_routing_in_production_code():
    import re

    for path in _PRODUCTION_FILES:
        text = path.read_text(encoding="utf-8").lower()
        for term in _FORBIDDEN_DOMAIN_TERMS:
            assert not re.search(rf"\b{term}\b", text), f"{term} leaked into {path.name}"


async def test_z2_no_keyword_branch_and_no_llm_import():
    import re

    keyword_branch = re.compile(r'if\s+["\'][a-z_]+["\']\s+in\s+(?:user_message|text|message)')
    # Word-boundary matching, not substring: a naive `"llm" in text` also hits
    # `fullmatch`, which would make this assertion meaningless.
    llm_reach = re.compile(
        r"(?:^|\s)(?:import|from)\s+\S*\b(?:llm|gemini)\b|\bget_manager\b|\b_call_ai\b",
        re.MULTILINE,
    )
    for path in _PRODUCTION_FILES:
        text = path.read_text(encoding="utf-8")
        assert not keyword_branch.search(text), f"keyword routing in {path.name}"
        # The signal layer is deterministic: it must not reach an LLM at all.
        assert not llm_reach.search(text), f"LLM reachable from {path.name}"


async def test_z3_no_polling_or_scheduler_introduced():
    for path in _PRODUCTION_FILES:
        text = path.read_text(encoding="utf-8").lower()
        for term in ("cron", "scheduler", "asyncio.sleep", "while true", "create_task"):
            assert term not in text, f"{term} introduced in {path.name}"


# ---------------------------------------------------------------------------
# Generality — arbitrary life domains the runtime has never heard of
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "summary",
    [
        "Sto organizzando una mostra di fotografia nel quartiere",
        "Ho iniziato a prendermi cura di un bonsai ereditato da mio nonno",
        "Stiamo preparando una festa di quartiere per l'estate",
    ],
)
async def test_generality_arbitrary_life_domains_behave_identically(summary):
    """The signal is deterministic, so this does not test comprehension — it
    proves the pipeline treats an unanticipated life domain exactly like any
    other, with no domain branch anywhere in the path."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        result = await SituationService(db).apply(
            user_id=user, session_id="s1", reasoning_epoch="ep_gen",
            update=SituationUpdate(operation="create", summary=summary),
        )
        await life_signals.emit_situation_signal(
            db, user_id=user, session_id="s1", reasoning_epoch="ep_gen",
            operation="create", result=result,
        )
        rows = await _signals(db, user)
        assert len(rows) == 1
        assert rows[0]["source_system"] == "situation"
        assert rows[0]["change_kind"] == "created"
        # No domain label anywhere in the stored signal.
        assert "domain" not in rows[0]
    finally:
        await _cleanup(db, user)
        client.close()


async def test_invalid_ref_or_unstable_dedupe_key_is_refused():
    """Guards the two ways this store could silently degrade: an ad-hoc ref
    namespace, or a dedupe key that disables idempotency."""
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        svc = LifeSignalService(db)
        assert await svc.emit(
            user_id=user, source_ref="not_a_canonical_ref",
            source_system="life_os", change_kind="created", dedupe_key="k:1",
        ) is None
        assert await svc.emit(
            user_id=user, source_ref="plan:plan_1",
            source_system="life_os", change_kind="created", dedupe_key="",
        ) is None
        assert await _signals(db, user) == []
    finally:
        await _cleanup(db, user)
        client.close()
