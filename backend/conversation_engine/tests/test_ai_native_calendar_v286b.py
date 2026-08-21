"""V2.8.6b — AI-native Calendar capability (deterministic, A-Z).

Real MongoDB test DB throughout (matches the V2.8.6a foundation suite) —
FakeDB's dict-style collection access does not support the attribute-style
`db.calendar_event_drafts` used consistently across the existing Calendar
write path, and this suite's date-range queries exercise more Mongo
operators than the FakeDB fixture implements. No real Google/Apple call
anywhere — fake provider only.

Uses `@pytest.mark.asyncio` (module-level `async def test_x()`), the same
convention already proven to coexist with `test_ai_core_connectivity.py`'s
anyio-based TestClient fixtures elsewhere in this directory (V2.8.5's
`test_ai_native_context_graph_v285.py` uses the identical pattern) — the
manual `asyncio.get_event_loop()`/`asyncio.run()` idiom used by the
`backend/tests/` suite conflicts with anyio's BlockingPortal when both run
in the same pytest-xdist worker.
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

from conversation_engine.ai_core.governance import validate_decision  # noqa: E402
from conversation_engine.ai_core.loop import run_cognitive_loop  # noqa: E402
from conversation_engine.ai_core.tools import calendar_caps  # noqa: E402
from conversation_engine.ai_core.tools.registry import ToolRegistry  # noqa: E402
from conversation_engine.models import ConversationSession  # noqa: E402
from connectors.google_calendar.consent import ConsentDenied  # noqa: E402
from permissions.service import PermissionService  # noqa: E402

pytestmark = pytest.mark.asyncio

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _grant_write(db, user_id: str) -> None:
    """Consent only — no connected Google instance. Used by tests that must
    prove Google is never called without a working sync path."""
    await PermissionService(db).grant(
        user_id=user_id, capability_id="calendar.write", connector_id="calendar_google",
    )


async def _grant_read(db, user_id: str) -> None:
    """Consent only — no connected Google instance and no write consent."""
    await PermissionService(db).grant(
        user_id=user_id, capability_id="calendar.read", connector_id="calendar_google",
    )


async def _revoke_read(db, user_id: str) -> None:
    await PermissionService(db).revoke(
        user_id=user_id, capability_id="calendar.read", connector_id="calendar_google",
    )


async def _seed_ingestion_event(db, user_id: str, *, title: str, starts_at: str, ends_at: str) -> None:
    """A minimal Google-imported event mirror, matching the shape
    `get_calendar_events` actually queries — status active (not detached)."""
    await db.ingestion_events.insert_one({
        "id": f"ing_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "connector_id": "calendar_google",
        "source_status": "active",
        "normalized_payload": {
            "title": title, "starts_at": starts_at, "ends_at": ends_at,
            "timezone": "Europe/Rome", "all_day": False, "location": None,
        },
    })


async def _connect_fake_google(db, user_id: str):
    """Real OAuth-callback plumbing in fake mode — a `GoogleCalendarService`
    bound to the TEST db (never the app's real `.env`-configured db), real
    vault + real connector instance + real auto-granted calendar.read/write
    consent, exactly as production does. `deps.get_google_calendar_service`
    is monkeypatched (restore via the returned token) so `calendar_caps.py`'s
    unmodified production code path exercises this test-bound service
    end-to-end, never a hand-rolled shortcut."""
    import deps as deps_module
    from connectors.google_calendar import GoogleCalendarService
    from connectors.google_calendar.provider import get_fake_provider
    from security.token_vault import build_token_vault

    svc = GoogleCalendarService(
        db=db, permissions=PermissionService(db), ingestion=None,
        vault=build_token_vault(db),
    )
    original = deps_module.get_google_calendar_service
    deps_module.get_google_calendar_service = lambda: svc
    started = await svc.start_oauth(user_id=user_id)
    await svc.handle_oauth_callback(
        state=started["state"], code="fake-code",
        fake_account={"sub": f"acct_{user_id}", "email": f"{user_id}@example.test"},
    )
    fake = get_fake_provider()
    if "primary" not in fake.calendars:
        fake.seed_calendar(calendar_id="primary", summary="Primary", primary=True)
    return original


def _disconnect_fake_google(original) -> None:
    import deps as deps_module

    deps_module.get_google_calendar_service = original


def _runtime(db, user_id: str, epoch: str = "") -> dict:
    return {"user_id": user_id, "db": db, "reasoning_epoch": epoch, "session_id": "s1"}


def _sess(user_id: str) -> ConversationSession:
    return ConversationSession(user_id=user_id, meta={"ui_mode": "ai_core", "ai_core": {}})


def _decision(mode="answer", **extra):
    raw = {
        "response_mode": mode,
        "user_intent_summary": "arbitrary calendar-adjacent turn",
        "reasoning_status": "needs_user_input" if mode == "ask" else "enough_information",
        "message_to_user": "Ok." if mode not in ("ask",) else None,
        "question": "Quale evento intendi?" if mode == "ask" else None,
    }
    raw.update(extra)
    return raw


def _scripted(items):
    queue = [deepcopy(x) for x in items]

    async def decide(_system, _user):
        return queue.pop(0)

    return decide


async def _cleanup(db, user_id: str) -> None:
    await db.calendar_event_drafts.delete_many({"user_id": user_id})
    await db.ingestion_events.delete_many({"user_id": user_id})
    await db.permission_consents.delete_many({"user_id": user_id})
    await db.context_edges.delete_many({"user_id": user_id})
    await db.life_os_plans.delete_many({"user_id": user_id})


@pytest.fixture(autouse=True)
def _isolate_google_calendar_service():
    """Every write path in `calendar_caps.py` resolves its
    `GoogleCalendarSyncService` via `deps.get_google_calendar_service()`
    (the same production wiring already used at
    `documents/intelligence/service.py:600-603`) *before* the consent check
    runs — including in tests that expect a `consent_required`/`not_found`
    denial and never intend to touch Google at all. Unpatched, that call
    binds the real `.env`-configured `deps.db` Motor client to this test's
    event loop; once that loop closes, the singleton is left attached to a
    dead loop, and the next test to touch `deps.db` (e.g. `server.py`
    startup inside `test_ai_core_connectivity.py`'s TestClient fixture)
    raises `RuntimeError: Event loop is closed`. Bind the lookup to this
    test's own throwaway db for every test in this module; `_connect_fake_google`
    layers a fully OAuth-connected instance on top of this when a test needs
    one, and restores back to this stub (never to the real singleton)."""
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
# A/B/C/D — read capability
# ---------------------------------------------------------------------------
async def test_a_read_only_no_write_no_google():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        obs = await calendar_caps.get_calendar_events({}, _runtime(db, user))
        assert obs.status == "ok"
        assert obs.payload["events"] == []
        n = await db.calendar_event_drafts.count_documents({"user_id": user})
        assert n == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_b_bounded_date_window():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        now = datetime.now(timezone.utc)
        far = _iso(now + timedelta(days=400))
        obs = await calendar_caps.get_calendar_events(
            {"time_min": _iso(now), "time_max": far}, _runtime(db, user),
        )
        window = obs.payload["window"]
        span_days = (
            datetime.fromisoformat(window["time_max"])
            - datetime.fromisoformat(window["time_min"])
        ).days
        assert span_days <= calendar_caps._MAX_WINDOW_DAYS
        assert len(obs.payload["events"]) <= calendar_caps._MAX_EVENTS_RETURNED
    finally:
        await _cleanup(db, user)
        client.close()


async def test_c_user_isolation():
    client, db = _db()
    user_a = f"u_{uuid.uuid4().hex[:8]}"
    user_b = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user_a)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        await calendar_caps.create_calendar_event(
            {"title": "Evento privato A", "start_datetime": start},
            _runtime(db, user_a, "ep_c1"),
        )
        obs_b = await calendar_caps.get_calendar_events({}, _runtime(db, user_b))
        assert obs_b.payload["events"] == []
    finally:
        await _cleanup(db, user_a)
        await _cleanup(db, user_b)
        client.close()


async def test_d_timezone_resolver_used_when_unspecified():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        obs = await calendar_caps.create_calendar_event(
            {"title": "Senza timezone esplicita", "start_datetime": start},
            _runtime(db, user, "ep_d1"),
        )
        assert obs.payload["timezone"]["tz_name"]
        assert obs.payload["timezone"]["authority"] in (
            "user_confirmed", "connector_calendar", "system_fallback",
        )
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# F/I/J/K/L/N/W — write capability structural guarantees
# ---------------------------------------------------------------------------
async def test_f_create_without_consent_denied():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        obs = await calendar_caps.create_calendar_event(
            {"title": "Non autorizzato", "start_datetime": start},
            _runtime(db, user, "ep_f1"),
        )
        assert obs.status == "consent_required"
        n = await db.calendar_event_drafts.count_documents({"user_id": user})
        assert n == 0  # no Google call, no local draft either
    finally:
        await _cleanup(db, user)
        client.close()


async def test_i_retry_create_same_epoch_no_duplicate():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    original = await _connect_fake_google(db, user)
    try:
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        args = {"title": "Chiamata Luca", "start_datetime": start}
        obs1 = await calendar_caps.create_calendar_event(args, _runtime(db, user, "ep_i1"))
        obs2 = await calendar_caps.create_calendar_event(args, _runtime(db, user, "ep_i1"))
        assert obs1.status == "ok" and obs2.status == "ok"
        assert obs1.payload["calendar_ref"] == obs2.payload["calendar_ref"]
        assert obs1.payload["google_event_id"] == obs2.payload["google_event_id"]
        n = await db.calendar_event_drafts.count_documents({"user_id": user})
        assert n == 1
    finally:
        _disconnect_fake_google(original)
        await _cleanup(db, user)
        client.close()


async def test_j_update_by_canonical_ref():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    original = await _connect_fake_google(db, user)
    try:
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Notaio", "start_datetime": start}, _runtime(db, user, "ep_j1"),
        )
        assert created.status == "ok"
        ref = created.payload["calendar_ref"]
        updated = await calendar_caps.update_calendar_event(
            {"calendar_ref": ref, "title": "Notaio (confermato)"},
            _runtime(db, user, "ep_j2"),
        )
        assert updated.status == "ok"
        assert updated.payload["calendar_ref"] == ref
        stored = await db.calendar_event_drafts.find_one({"id": ref.split(":")[1]}, {"_id": 0})
        assert stored["title"] == "Notaio (confermato)"
    finally:
        _disconnect_fake_google(original)
        await _cleanup(db, user)
        client.close()


async def test_update_unsynced_reports_partial_not_failed():
    # Found live via Chrome QA: reschedule_draft() commits the local field
    # patch unconditionally before any Google-side step, even when the
    # draft was never linked to Google — so a "failed"/"not confirmed"
    # response would falsely deny a change that was actually saved locally.
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)  # consent only — never connected to Google
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Chiamata con Luca", "start_datetime": start},
            _runtime(db, user, "ep_partial1"),
        )
        assert created.status == "partial"  # not connected — local only
        ref = created.payload["calendar_ref"]
        new_start = _iso(datetime.now(timezone.utc) + timedelta(hours=2, minutes=30))
        updated = await calendar_caps.update_calendar_event(
            {"calendar_ref": ref, "start_datetime": new_start},
            _runtime(db, user, "ep_partial2"),
        )
        assert updated.status == "partial"
        assert "local" in updated.payload["reason"].lower()
        stored = await db.calendar_event_drafts.find_one(
            {"id": ref.split(":")[1]}, {"_id": 0, "start_datetime": 1},
        )
        assert stored["start_datetime"] == new_start  # local change actually applied
    finally:
        await _cleanup(db, user)
        client.close()


async def test_update_cancelled_event_rejected_not_crashed():
    # CPO hardening gate: reschedule_draft() raises ValueError("evento
    # cancellato") for a cancelled draft — update_calendar_event must
    # reject this explicitly and typed, before ever reaching that raise,
    # never crash the tool handler, never touch the DB, never reactivate.
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Evento da cancellare", "start_datetime": start},
            _runtime(db, user, "ep_cancelled1"),
        )
        assert created.status == "partial"
        ref = created.payload["calendar_ref"]
        cancelled = await calendar_caps.cancel_calendar_event(
            {"calendar_ref": ref}, _runtime(db, user, "ep_cancelled2"),
        )
        assert cancelled.status == "ok"

        # Now try to update the already-cancelled event.
        updated = await calendar_caps.update_calendar_event(
            {"calendar_ref": ref, "start_datetime": _iso(datetime.now(timezone.utc) + timedelta(hours=5))},
            _runtime(db, user, "ep_cancelled3"),
        )
        assert updated.status == "rejected"
        assert updated.payload["failure_kind"] == "event_cancelled"
        assert "moved" in updated.payload["reason"].lower() or "reactivate" in updated.payload["reason"].lower()

        # No DB mutation, no reactivation, no duplicate.
        docs = await db.calendar_event_drafts.find({"user_id": user}, {"_id": 0}).to_list(10)
        assert len(docs) == 1
        assert docs[0]["status"] == "cancelled"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_calendar_read_a_granted_google_event_visible():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_read(db, user)
        base = datetime.now(timezone.utc) + timedelta(hours=2)
        await _seed_ingestion_event(
            db, user, title="Riunione importata",
            starts_at=_iso(base), ends_at=_iso(base + timedelta(hours=1)),
        )
        obs = await calendar_caps.get_calendar_events({}, _runtime(db, user))
        assert obs.status == "ok"
        assert obs.payload["google_events_included"] is True
        sources = {e["source"] for e in obs.payload["events"]}
        assert "google_external" in sources
    finally:
        await _cleanup(db, user)
        client.close()


async def test_calendar_read_b_revoked_google_event_hidden():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_read(db, user)
        base = datetime.now(timezone.utc) + timedelta(hours=2)
        await _seed_ingestion_event(
            db, user, title="Riunione importata",
            starts_at=_iso(base), ends_at=_iso(base + timedelta(hours=1)),
        )
        await _revoke_read(db, user)
        obs = await calendar_caps.get_calendar_events({}, _runtime(db, user))
        assert obs.status == "ok"
        assert obs.payload["google_events_included"] is False
        assert obs.payload["google_events_note"]
        sources = {e["source"] for e in obs.payload["events"]}
        assert "google_external" not in sources
    finally:
        await _cleanup(db, user)
        client.close()


async def test_calendar_read_c_cross_user_never_visible():
    client, db = _db()
    user_a = f"u_{uuid.uuid4().hex[:8]}"
    user_b = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_read(db, user_a)
        await _grant_read(db, user_b)
        base = datetime.now(timezone.utc) + timedelta(hours=2)
        await _seed_ingestion_event(
            db, user_a, title="Evento privato di A",
            starts_at=_iso(base), ends_at=_iso(base + timedelta(hours=1)),
        )
        obs_b = await calendar_caps.get_calendar_events({}, _runtime(db, user_b))
        titles = {e.get("title") for e in obs_b.payload["events"]}
        assert "Evento privato di A" not in titles
    finally:
        await _cleanup(db, user_a)
        await _cleanup(db, user_b)
        client.close()


async def test_calendar_read_d_local_event_visible_regardless_of_google_consent():
    # No calendar.read consent granted at all — ORA-managed local events
    # must still be visible as ORA's own record.
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Evento locale ORA", "start_datetime": start},
            _runtime(db, user, "ep_local1"),
        )
        assert created.status == "partial"
        obs = await calendar_caps.get_calendar_events({}, _runtime(db, user))
        assert obs.payload["google_events_included"] is False  # no read consent at all
        refs = {e["calendar_ref"] for e in obs.payload["events"]}
        assert created.payload["calendar_ref"] in refs
        matching = [e for e in obs.payload["events"] if e["calendar_ref"] == created.payload["calendar_ref"]]
        assert matching[0]["source"] == "ora_managed"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_calendar_read_e_revocation_does_not_delete_cache():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_read(db, user)
        base = datetime.now(timezone.utc) + timedelta(hours=2)
        await _seed_ingestion_event(
            db, user, title="Riunione importata",
            starts_at=_iso(base), ends_at=_iso(base + timedelta(hours=1)),
        )
        await _revoke_read(db, user)
        await calendar_caps.get_calendar_events({}, _runtime(db, user))
        n = await db.ingestion_events.count_documents({"user_id": user})
        assert n == 1  # revocation never deletes the underlying cache
    finally:
        await _cleanup(db, user)
        client.close()


async def test_calendar_read_f_no_google_call_during_read():
    # No fake-Google connection at all (no _connect_fake_google) — if the
    # read path required a live Google call it would raise here; it must
    # resolve entirely from local state.
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_read(db, user)
        obs = await calendar_caps.get_calendar_events({}, _runtime(db, user))
        assert obs.status == "ok"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_k_ambiguous_ref_never_silently_chosen():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        obs = await calendar_caps.update_calendar_event(
            {"calendar_ref": "calendar:ced_does_not_exist", "title": "x"},
            _runtime(db, user, "ep_k1"),
        )
        assert obs.status == "not_found"
        assert "ask" in obs.payload["reason"].lower() or "guess" in obs.payload["reason"].lower()
    finally:
        await _cleanup(db, user)
        client.close()


async def test_l_reschedule_same_event_stable_id():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    original = await _connect_fake_google(db, user)
    try:
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Notaio", "start_datetime": start}, _runtime(db, user, "ep_l1"),
        )
        assert created.status == "ok"
        ref = created.payload["calendar_ref"]
        gid = created.payload["google_event_id"]
        new_start = _iso(datetime.now(timezone.utc) + timedelta(hours=3))
        rescheduled = await calendar_caps.update_calendar_event(
            {"calendar_ref": ref, "start_datetime": new_start},
            _runtime(db, user, "ep_l2"),
        )
        assert rescheduled.status == "ok"
        assert rescheduled.payload["calendar_ref"] == ref
        assert rescheduled.payload["google_event_id"] == gid
        n = await db.calendar_event_drafts.count_documents({"user_id": user})
        assert n == 1
    finally:
        _disconnect_fake_google(original)
        await _cleanup(db, user)
        client.close()


async def test_n_cancel_google_side_honesty():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    original = await _connect_fake_google(db, user)
    try:
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Da cancellare", "start_datetime": start}, _runtime(db, user, "ep_n1"),
        )
        assert created.status == "ok"
        ref = created.payload["calendar_ref"]
        cancelled = await calendar_caps.cancel_calendar_event(
            {"calendar_ref": ref}, _runtime(db, user, "ep_n2"),
        )
        assert cancelled.status == "ok"
        assert cancelled.payload["operation"] == "cancelled"
        # local cancel is honestly true; deleted_on_google reflects the
        # real remote outcome, never assumed.
        assert cancelled.payload["deleted_on_google"] is True
        stored = await db.calendar_event_drafts.find_one(
            {"id": ref.split(":")[1]}, {"_id": 0, "status": 1},
        )
        assert stored["status"] == "cancelled"
    finally:
        _disconnect_fake_google(original)
        await _cleanup(db, user)
        client.close()


async def test_w_observation_no_token_no_raw_payload():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    original = await _connect_fake_google(db, user)
    try:
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        obs = await calendar_caps.create_calendar_event(
            {"title": "Verifica payload", "start_datetime": start},
            _runtime(db, user, "ep_w1"),
        )
        assert obs.status == "ok"
        blob = str(obs.payload).lower()
        for forbidden in ("access_token", "refresh_token", "secret", "\"token\""):
            assert forbidden not in blob
        assert set(obs.payload.keys()) <= {
            "status", "operation", "calendar_ref", "google_event_id",
            "sync_status", "timezone",
        }
    finally:
        _disconnect_fake_google(original)
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# O/U — governance reuse (no new code)
# ---------------------------------------------------------------------------
async def test_o_blocking_uncertainty_prevents_write():
    raw = _decision(
        mode="tool",
        tool_call={
            "capability": "create_calendar_event",
            "arguments": {"title": "x", "start_datetime": "2026-09-01T10:00:00+02:00"},
        },
        uncertainty={
            "level": 0.9, "blocking": True,
            "missing_information": [{
                "ref": "which-luca", "description": "ambiguous target",
                "purpose": "safety", "importance": 0.9, "blocking": True,
                "strategy": "ask",
            }],
        },
    )
    out = validate_decision(raw, tools=ToolRegistry())
    assert out.decision.response_mode == "answer"
    assert out.decision.tool_call is None
    assert "blocking_uncertainty_for_write" in out.errors


async def test_u_legacy_decision_without_calendar_still_valid():
    raw = _decision(mode="answer", message_to_user="Nessun calendario coinvolto qui.")
    out = validate_decision(raw, tools=ToolRegistry())
    assert out.ok is True
    assert out.decision.context_graph_updates == []  # unaffected, pre-existing default


# ---------------------------------------------------------------------------
# E/G/H/M/P/T/X — full loop (scripted decision_fn)
# ---------------------------------------------------------------------------
async def test_e_create_proposal_requires_confirmation_no_write():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        sess = _sess(user)
        decide = _scripted([
            _decision(
                mode="act",
                message_to_user="Vuoi che aggiunga la chiamata con Luca domani alle 18?",
            ),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Domani alle 18 devo chiamare Luca, mettilo in calendario.",
            db=db, decision_fn=decide,
        )
        assert out.mode == "act"
        n = await db.calendar_event_drafts.count_documents({"user_id": user})
        assert n == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_g_create_after_confirmation_succeeds():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(days=1, hours=2))
        sess = _sess(user)
        decide = _scripted([
            _decision(
                mode="tool",
                tool_call={
                    "capability": "create_calendar_event",
                    "arguments": {"title": "Chiamata con Luca", "start_datetime": start},
                },
            ),
            _decision(mode="answer", message_to_user="Fatto, l'ho aggiunto al calendario."),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Sì, confermo.", db=db, decision_fn=decide,
        )
        assert out.mode == "answer"
        n = await db.calendar_event_drafts.count_documents({"user_id": user})
        assert n == 1
    finally:
        await _cleanup(db, user)
        client.close()


async def test_h_persist_before_claim_nudge_fires():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        sess = _sess(user)
        decide = _scripted([
            _decision(
                mode="answer",
                message_to_user="Ho aggiunto l'evento al calendario.",
            ),
            _decision(
                mode="answer",
                message_to_user="In realtà non sono riuscita, possiamo riprovare.",
            ),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Metti la riunione di domani alle 10 in calendario.",
            db=db, decision_fn=decide,
        )
        # nudge observability is aggregate-only; behavioral proof is that
        # the false claim never became the final answer as-is.
        assert out.ora_text != "Ho aggiunto l'evento al calendario."
        n = await db.calendar_event_drafts.count_documents({"user_id": user})
        assert n == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_m_cancel_proposal_requires_confirmation():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Da valutare", "start_datetime": start}, _runtime(db, user, "ep_m0"),
        )
        ref = created.payload["calendar_ref"]
        sess = _sess(user)
        decide = _scripted([
            _decision(
                mode="act",
                message_to_user=f"Vuoi che cancelli l'evento {ref}?",
            ),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Anzi cancella quell'evento.",
            db=db, decision_fn=decide,
        )
        assert out.mode == "act"
        stored = await db.calendar_event_drafts.find_one(
            {"id": ref.split(":")[1]}, {"_id": 0, "status": 1},
        )
        assert stored["status"] != "cancelled"
    finally:
        await _cleanup(db, user)
        client.close()


async def test_p_context_need_calendar_evidence_reasoning_reentry():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=5))
        await calendar_caps.create_calendar_event(
            {"title": "Dentista", "start_datetime": start}, _runtime(db, user, "ep_p0"),
        )
        sess = _sess(user)
        decide = _scripted([
            _decision(
                mode="context",
                context_need={
                    "query": "impegni calendario di oggi",
                    "purpose": "rispondere su cosa ha in programma",
                    "source_hints": ["calendar"],
                },
            ),
            _decision(mode="answer", message_to_user="Hai il dentista più tardi."),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Cosa ho oggi?", db=db, decision_fn=decide,
        )
        assert out.mode == "answer"
        assert out.context_calls >= 2
    finally:
        await _cleanup(db, user)
        client.close()


async def test_t_negative_control_ordinary_turn_no_event():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        sess = _sess(user)
        decide = _scripted([
            _decision(mode="answer", message_to_user="Certo, ditemi pure."),
        ])
        out = await run_cognitive_loop(
            sess=sess, user_message="Sto pensando di imparare a fare il pane in casa.",
            db=db, decision_fn=decide,
        )
        assert out.mode == "answer"
        n = await db.calendar_event_drafts.count_documents({"user_id": user})
        assert n == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_x_cross_session_calendar_retrieval():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=3))
        await calendar_caps.create_calendar_event(
            {"title": "Colloquio", "start_datetime": start}, _runtime(db, user, "ep_x0"),
        )
        # brand-new session, no prior recent_turns
        sess2 = _sess(user)
        decide = _scripted([
            _decision(
                mode="context",
                context_need={
                    "query": "impegni calendario",
                    "purpose": "continuità cross-session",
                    "source_hints": ["calendar"],
                },
            ),
            _decision(mode="answer", message_to_user="Hai il colloquio più tardi."),
        ])
        out = await run_cognitive_loop(
            sess=sess2, user_message="A che punto sono oggi?", db=db, decision_fn=decide,
        )
        assert out.mode == "answer"
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# Q/R/S — cross-module non-duplication
# ---------------------------------------------------------------------------
async def test_q_situation_calendar_ref_no_duplication():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        created = await calendar_caps.create_calendar_event(
            {"title": "Notaio", "start_datetime": start}, _runtime(db, user, "ep_q1"),
        )
        ref = created.payload["calendar_ref"]
        from context_graph.service import ContextGraphService
        from context_graph.models import ContextEdgeUpdate

        svc = ContextGraphService(db)
        results = await svc.apply(
            user_id=user, session_id="s1",
            updates=[ContextEdgeUpdate(
                operation="create", subject_ref=f"goal:goal_{uuid.uuid4().hex[:8]}",
                predicate="supported_by", object_ref=ref,
            )],
            reasoning_epoch="ep_q2",
        )
        assert results[0]["decision"] == "CREATED"
        # the edge references the ref; it never copies title/date onto itself
        edge = await db.context_edges.find_one({"id": results[0]["edge_id"]}, {"_id": 0})
        assert edge["object_ref"] == ref
        assert "title" not in edge and "start_datetime" not in edge
    finally:
        await _cleanup(db, user)
        client.close()


async def test_r_plan_creation_never_auto_creates_calendar_event():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        from life_os.service import LifeOsService

        await LifeOsService(db).create_plan(
            user, summary="Preparare presentazione",
            items=[{"title": "Bozza slide", "order": 0}],
        )
        n = await db.calendar_event_drafts.count_documents({"user_id": user})
        assert n == 0
    finally:
        await _cleanup(db, user)
        client.close()


async def test_s_create_event_never_auto_creates_graph_edge():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await _grant_write(db, user)
        start = _iso(datetime.now(timezone.utc) + timedelta(hours=2))
        await calendar_caps.create_calendar_event(
            {"title": "Evento isolato", "start_datetime": start}, _runtime(db, user, "ep_s1"),
        )
        n = await db.context_edges.count_documents({"user_id": user})
        assert n == 0
    finally:
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# Y — conflict awareness
# ---------------------------------------------------------------------------
async def test_y_overlap_detected_bounded():
    client, db = _db()
    user = f"u_{uuid.uuid4().hex[:8]}"
    original = await _connect_fake_google(db, user)
    try:
        base = datetime.now(timezone.utc) + timedelta(hours=2)
        a = await calendar_caps.create_calendar_event(
            {
                "title": "Riunione A", "start_datetime": _iso(base),
                "end_datetime": _iso(base + timedelta(hours=1)),
            },
            _runtime(db, user, "ep_y1"),
        )
        b = await calendar_caps.create_calendar_event(
            {
                "title": "Riunione B", "start_datetime": _iso(base + timedelta(minutes=30)),
                "end_datetime": _iso(base + timedelta(hours=1, minutes=30)),
            },
            _runtime(db, user, "ep_y2"),
        )
        assert a.status == "ok" and b.status == "ok"
        obs = await calendar_caps.get_calendar_events(
            {"time_min": _iso(base - timedelta(hours=1)), "time_max": _iso(base + timedelta(hours=3))},
            _runtime(db, user),
        )
        assert len(obs.payload["conflict_index_pairs"]) >= 1
    finally:
        _disconnect_fake_google(original)
        await _cleanup(db, user)
        client.close()


# ---------------------------------------------------------------------------
# V/Z — no keyword routing (static, enforced going forward)
# ---------------------------------------------------------------------------
_PRODUCTION_FILES = [
    Path(_BACKEND) / "conversation_engine" / "ai_core" / "tools" / "calendar_caps.py",
    Path(_BACKEND) / "conversation_engine" / "ai_core" / "loop.py",
    Path(_BACKEND) / "conversation_engine" / "ai_core" / "governance.py",
    Path(_BACKEND) / "conversation_engine" / "ai_core" / "prompt.py",
]


async def test_v_no_calendar_intent_keyword_branch():
    import re

    pattern = re.compile(
        r'if\s+["\']calendar["\']\s+in\s+|'
        r'if\s+["\']appointment["\']\s+in\s+|'
        r'calendar_intent\s*=='
    )
    for f in _PRODUCTION_FILES:
        text = f.read_text(encoding="utf-8")
        assert not pattern.search(text), f"keyword routing found in {f}"


async def test_z_no_reminder_keyword_branch():
    import re

    pattern = re.compile(r'if\s+["\']ricordami["\']\s+in\s+|if\s+["\']remind["\']\s+in\s+')
    for f in _PRODUCTION_FILES:
        text = f.read_text(encoding="utf-8")
        assert not pattern.search(text), f"reminder keyword routing found in {f}"
