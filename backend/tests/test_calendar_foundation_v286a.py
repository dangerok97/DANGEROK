"""ORA V2.8.6a — Calendar Foundation Hardening.

Deterministic/integration tests (fake provider or mocked httpx transport —
never real Google/Apple). Covers: Context Broker calendar-source fix,
general-purpose timezone resolver, real-provider create idempotency,
canonical update/reschedule, calendar consent helper, index initialization,
and confirmation that zero Calendar tools exist in the AI Core tool
registry (V2.8.6a is foundation-only; V2.8.6b adds capabilities).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

os.environ["CALENDAR_PROVIDER_MODE"] = "fake"
os.environ.setdefault("TOKEN_VAULT_BACKEND", "local")
os.environ.setdefault(
    "TOKEN_VAULT_KEY", "change-me-token-vault-key-32bytes-min!!!!!!!!"
)

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import connectors.google_calendar.provider as provider_module  # noqa: E402
from connectors.google_calendar.provider import (  # noqa: E402
    GoogleCalendarAPIError,
    RealGoogleCalendarProvider,
)
from connectors.google_calendar.consent import (  # noqa: E402
    calendar_consent_granted,
    require_calendar_consent,
)
from permissions.errors import ConsentDenied  # noqa: E402
from permissions.service import PermissionService  # noqa: E402
from documents.intelligence.google_sync import GoogleCalendarSyncService  # noqa: E402
from documents.intelligence.service import IntelligenceService  # noqa: E402
from conversation_engine.ai_core.context_sources import ContextSourceRegistry  # noqa: E402
from conversation_engine.ai_core.models import ContextNeed  # noqa: E402
from conversation_engine.ai_core.tools.registry import ToolRegistry  # noqa: E402
from timezone_service import (  # noqa: E402
    DEFAULT_SYSTEM_TIMEZONE,
    is_valid_iana_timezone,
    localize_naive_datetime,
    resolve_user_timezone,
)

# Reuse the existing fake-provider write-sync test fixtures rather than
# duplicating them.
from tests.test_google_calendar_write_sync import (  # noqa: E402
    FakeGoogleCalendarProvider,
    _FakeGcalService,
    _base_instance,
    _insert_draft,
)

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


class _MockGoogleTransport(httpx.AsyncBaseTransport):
    """Deterministic, in-memory Google Calendar HTTP surface — no network."""

    def __init__(self):
        self.post_count = 0
        self.get_count = 0
        self.events_by_ora_id: dict[str, dict] = {}
        self.force_post_status: int | None = None
        self.raise_network_error_on_post = False
        self._seq = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET" and "/events" in url:
            self.get_count += 1
            q = request.url.params.get("privateExtendedProperty") or ""
            ora_id = q.split("=", 1)[1] if "=" in q else None
            existing = self.events_by_ora_id.get(ora_id) if ora_id else None
            items = [existing] if existing else []
            return httpx.Response(200, json={"items": items})
        if request.method == "POST" and url.endswith("/events"):
            self.post_count += 1
            if self.raise_network_error_on_post:
                raise httpx.ConnectError("simulated network failure")
            if self.force_post_status is not None:
                return httpx.Response(self.force_post_status, text="mock error")
            body = json.loads(request.content or b"{}")
            ora_id = (
                (body.get("extendedProperties") or {}).get("private") or {}
            ).get("ora_event_id")
            self._seq += 1
            eid = f"gcal_{self._seq}"
            event = {
                **body,
                "id": eid,
                "etag": f"etag-{self._seq}",
                "htmlLink": f"https://calendar.google.com/event?eid={eid}",
                "status": "confirmed",
            }
            if ora_id:
                self.events_by_ora_id[ora_id] = event
            return httpx.Response(200, json=event)
        if request.method == "PATCH":
            self.post_count += 1
            if self.force_post_status is not None:
                return httpx.Response(self.force_post_status, text="mock error")
            body = json.loads(request.content or b"{}")
            return httpx.Response(200, json={**body, "id": "gcal_updated", "etag": "etag-2"})
        return httpx.Response(404, json={"error": "unhandled_in_mock"})


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patch_httpx(transport: httpx.BaseTransport):
    original = provider_module.httpx.AsyncClient

    def _factory(*args, **kwargs):
        return _REAL_ASYNC_CLIENT(transport=transport)

    provider_module.httpx.AsyncClient = _factory
    return original


def _unpatch_httpx(original) -> None:
    provider_module.httpx.AsyncClient = original


def _basic_body(ora_event_id: str) -> dict:
    return {
        "summary": "Evento ORA",
        "start": {"dateTime": "2026-09-15T10:00:00+02:00"},
        "end": {"dateTime": "2026-09-15T11:00:00+02:00"},
        "extendedProperties": {"private": {"ora_event_id": ora_event_id}},
    }


# ---------------------------------------------------------------------------
# A/B — Context Broker calendar source
# ---------------------------------------------------------------------------
class TestA_ContextBrokerFix:
    def test_a_field_bug_fixed_real_start_end_surfaced(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                await _insert_draft(
                    db,
                    user_id=user,
                    draft_id=f"ced_{uuid.uuid4().hex[:8]}",
                    title="Riunione progetto",
                    start_datetime="2026-09-15T10:00:00+02:00",
                    end_datetime="2026-09-15T11:00:00+02:00",
                    timezone="Europe/Rome",
                    provider="google",
                    status="confirmed",
                )
                registry = ContextSourceRegistry(db)
                facts = await registry._calendar(
                    user, ContextNeed(query="calendario"), None
                )
                assert len(facts) == 1
                f = facts[0]
                assert "start=2026-09-15T10:00:00+02:00" in f.statement
                assert "end=2026-09-15T11:00:00+02:00" in f.statement
                assert "unspecified" not in f.statement
                assert f.ref.startswith("calendar:ced_")
                assert f.status == "confirmed"
                assert f.provenance == ["google"]
            finally:
                await db.calendar_event_drafts.delete_many({"user_id": user})
                client.close()

        _run(body())

    def test_b_bounded_to_twelve(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                for i in range(15):
                    await _insert_draft(
                        db,
                        user_id=user,
                        draft_id=f"ced_{uuid.uuid4().hex[:8]}",
                        title=f"Evento {i}",
                        start_datetime=f"2026-09-{10 + i:02d}T10:00:00+02:00",
                    )
                registry = ContextSourceRegistry(db)
                facts = await registry._calendar(
                    user, ContextNeed(query="calendario"), None
                )
                assert len(facts) <= 12
            finally:
                await db.calendar_event_drafts.delete_many({"user_id": user})
                client.close()

        _run(body())


# ---------------------------------------------------------------------------
# C-F — Timezone resolver
# ---------------------------------------------------------------------------
class TestB_TimezoneResolver:
    def test_c_user_confirmed_wins(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                await db.users.update_one(
                    {"id": user},
                    {"$set": {"id": user, "settings.timezone": "America/New_York"}},
                    upsert=True,
                )
                resolved = await resolve_user_timezone(db, user)
                assert resolved.tz_name == "America/New_York"
                assert resolved.authority == "user_confirmed"
                assert resolved.is_confirmed() is True
            finally:
                await db.users.delete_many({"id": user})
                client.close()

        _run(body())

    def test_d_fallback_when_no_signal(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                resolved = await resolve_user_timezone(db, user)
                assert resolved.tz_name == DEFAULT_SYSTEM_TIMEZONE
                assert resolved.authority == "system_fallback"
                assert resolved.is_confirmed() is False
            finally:
                client.close()

        _run(body())

    def test_e_dst_awareness(self):
        resolved = type(
            "R", (), {"tz_name": "Europe/Rome"}
        )()
        summer = localize_naive_datetime(
            datetime(2026, 7, 15, 15, 0, 0), resolved
        )
        winter = localize_naive_datetime(
            datetime(2026, 1, 15, 15, 0, 0), resolved
        )
        assert summer.utcoffset().total_seconds() == 2 * 3600
        assert winter.utcoffset().total_seconds() == 1 * 3600

    def test_f_invalid_timezone_skipped_not_crashed(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                await db.users.update_one(
                    {"id": user},
                    {"$set": {"id": user, "settings.timezone": "Not/AZone"}},
                    upsert=True,
                )
                resolved = await resolve_user_timezone(db, user)
                # Invalid value must never be honored as user_confirmed.
                assert resolved.authority != "user_confirmed"
                assert is_valid_iana_timezone("Not/AZone") is False
                assert is_valid_iana_timezone("Europe/Rome") is True
            finally:
                await db.users.delete_many({"id": user})
                client.close()

        _run(body())

    def test_connector_calendar_tier(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                await db.life_nodes.insert_one({
                    "id": f"node_{uuid.uuid4().hex[:8]}",
                    "user_id": user,
                    "type": "event",
                    "attributes": {"timezone": "Asia/Tokyo"},
                    "updated_at": _now(),
                })
                resolved = await resolve_user_timezone(db, user)
                assert resolved.tz_name == "Asia/Tokyo"
                assert resolved.authority == "connector_calendar"
            finally:
                await db.life_nodes.delete_many({"user_id": user})
                client.close()

        _run(body())


# ---------------------------------------------------------------------------
# G-J — Real-provider create idempotency
# ---------------------------------------------------------------------------
class TestC_RealProviderIdempotency:
    def test_g_happy_path_single_create(self):
        async def body():
            transport = _MockGoogleTransport()
            original = _patch_httpx(transport)
            try:
                p = RealGoogleCalendarProvider()
                created = await p.create_event(
                    access_token="t", calendar_id="primary",
                    body=_basic_body("ced_g1"),
                )
                assert created["id"]
                assert transport.post_count == 1
            finally:
                _unpatch_httpx(original)

        _run(body())

    def test_h_network_after_create_retry_no_duplicate(self):
        """Create succeeds server-side; caller never records google_event_id
        (simulating a crash/network drop after Google accepted). A retry —
        the same create_event call again — must NOT create a second event.
        """
        async def body():
            transport = _MockGoogleTransport()
            original = _patch_httpx(transport)
            try:
                p = RealGoogleCalendarProvider()
                body_ev = _basic_body("ced_h1")
                first = await p.create_event(
                    access_token="t", calendar_id="primary", body=body_ev
                )
                # "retry" — identical call, as if the local write-back never
                # happened and the caller is retrying from scratch.
                second = await p.create_event(
                    access_token="t", calendar_id="primary", body=body_ev
                )
                assert first["id"] == second["id"]
                assert transport.post_count == 1  # only ONE real create
                assert len(transport.events_by_ora_id) == 1
            finally:
                _unpatch_httpx(original)

        _run(body())

    def test_i_repeated_operation_same_event_id(self):
        async def body():
            transport = _MockGoogleTransport()
            original = _patch_httpx(transport)
            try:
                p = RealGoogleCalendarProvider()
                ids = set()
                for _ in range(3):
                    ev = await p.create_event(
                        access_token="t", calendar_id="primary",
                        body=_basic_body("ced_i1"),
                    )
                    ids.add(ev["id"])
                assert len(ids) == 1
                assert transport.post_count == 1
            finally:
                _unpatch_httpx(original)

        _run(body())

    def test_j_different_ora_id_different_event(self):
        async def body():
            transport = _MockGoogleTransport()
            original = _patch_httpx(transport)
            try:
                p = RealGoogleCalendarProvider()
                a = await p.create_event(
                    access_token="t", calendar_id="primary",
                    body=_basic_body("ced_j1"),
                )
                b = await p.create_event(
                    access_token="t", calendar_id="primary",
                    body=_basic_body("ced_j2"),
                )
                assert a["id"] != b["id"]
                assert transport.post_count == 2
            finally:
                _unpatch_httpx(original)

        _run(body())


# ---------------------------------------------------------------------------
# K/L — Canonical update/reschedule
# ---------------------------------------------------------------------------
class TestD_RescheduleCanonical:
    def test_k_reschedule_success(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                p = FakeGoogleCalendarProvider()
                p.seed_calendar(calendar_id="primary", summary="P", primary=True)
                inst = _base_instance(user)
                gcal = _FakeGcalService(p, inst)
                sync = GoogleCalendarSyncService(db=db, google_calendar_service=gcal)

                draft_id = f"ced_{uuid.uuid4().hex[:8]}"
                await _insert_draft(db, user_id=user, draft_id=draft_id)
                created = await sync.sync_draft(user_id=user, draft_id=draft_id)
                gid = created["google_event_id"]

                rescheduled = await sync.reschedule_draft(
                    user_id=user, draft_id=draft_id,
                    fields={
                        "title": "Riunione spostata",
                        "start_datetime": "2026-09-16T14:00:00+02:00",
                        "end_datetime": "2026-09-16T15:00:00+02:00",
                    },
                )
                assert rescheduled["sync_status"] == "synced"
                assert rescheduled["google_event_id"] == gid  # stable, no new draft
                stored = await db.calendar_event_drafts.find_one(
                    {"id": draft_id}, {"_id": 0}
                )
                assert stored["title"] == "Riunione spostata"
                assert stored["start_datetime"] == "2026-09-16T14:00:00+02:00"
                assert stored["google_event_id"] == gid
            finally:
                await db.calendar_event_drafts.delete_many({"user_id": user})
                client.close()

        _run(body())

    def test_l_reschedule_failure_no_false_success(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                p = FakeGoogleCalendarProvider()
                p.seed_calendar(calendar_id="primary", summary="P", primary=True)
                inst = _base_instance(user)
                gcal = _FakeGcalService(p, inst)
                sync = GoogleCalendarSyncService(db=db, google_calendar_service=gcal)

                draft_id = f"ced_{uuid.uuid4().hex[:8]}"
                await _insert_draft(db, user_id=user, draft_id=draft_id)
                created = await sync.sync_draft(user_id=user, draft_id=draft_id)
                gid = created["google_event_id"]

                # Force the underlying provider update to fail.
                async def _boom(*args, **kwargs):
                    raise GoogleCalendarAPIError(500, "simulated failure")

                p.update_event = _boom  # type: ignore[method-assign]

                with pytest.raises(GoogleCalendarAPIError):
                    await sync.reschedule_draft(
                        user_id=user, draft_id=draft_id,
                        fields={"title": "Titolo che non arriva a Google"},
                    )
                stored = await db.calendar_event_drafts.find_one(
                    {"id": draft_id}, {"_id": 0}
                )
                assert stored["sync_status"] == "failed"
                assert stored["sync_error"]
                assert stored["google_event_id"] == gid  # unchanged, not corrupted
            finally:
                await db.calendar_event_drafts.delete_many({"user_id": user})
                client.close()

        _run(body())


# ---------------------------------------------------------------------------
# M-P — Permission / consent
# ---------------------------------------------------------------------------
class TestE_Consent:
    def test_m_write_allowed_when_granted(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                await PermissionService(db).grant(
                    user_id=user, capability_id="calendar.write",
                    connector_id="calendar_google",
                )
                ok = await calendar_consent_granted(db, user_id=user, write=True)
                assert ok is True
                await require_calendar_consent(db, user_id=user, write=True)  # no raise
            finally:
                await db.permission_consents.delete_many({"user_id": user})
                client.close()

        _run(body())

    def test_n_write_denied_when_not_granted(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                ok = await calendar_consent_granted(db, user_id=user, write=True)
                assert ok is False
                with pytest.raises(ConsentDenied):
                    await require_calendar_consent(db, user_id=user, write=True)
            finally:
                client.close()

        _run(body())

    def test_o_revoked_denied(self):
        async def body():
            client, db = _db()
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                perms = PermissionService(db)
                await perms.grant(
                    user_id=user, capability_id="calendar.write",
                    connector_id="calendar_google",
                )
                assert await calendar_consent_granted(db, user_id=user, write=True)
                await perms.revoke(
                    user_id=user, capability_id="calendar.write",
                    connector_id="calendar_google", reason="test",
                )
                ok = await calendar_consent_granted(db, user_id=user, write=True)
                assert ok is False
            finally:
                await db.permission_consents.delete_many({"user_id": user})
                client.close()

        _run(body())

    def test_p_user_isolation(self):
        async def body():
            client, db = _db()
            try:
                user_a = f"u_{uuid.uuid4().hex[:8]}"
                user_b = f"u_{uuid.uuid4().hex[:8]}"
                await PermissionService(db).grant(
                    user_id=user_a, capability_id="calendar.write",
                    connector_id="calendar_google",
                )
                assert await calendar_consent_granted(db, user_id=user_a, write=True)
                assert not await calendar_consent_granted(db, user_id=user_b, write=True)
            finally:
                await db.permission_consents.delete_many({"user_id": {"$in": [user_a, user_b]}})
                client.close()

        _run(body())


# ---------------------------------------------------------------------------
# Q/R — Provider failure classification
# ---------------------------------------------------------------------------
class TestF_ProviderFailures:
    def test_q_auth_failure_surfaced_typed(self):
        async def body():
            transport = _MockGoogleTransport()
            transport.force_post_status = 401
            original = _patch_httpx(transport)
            try:
                p = RealGoogleCalendarProvider()
                with pytest.raises(GoogleCalendarAPIError) as exc:
                    await p.create_event(
                        access_token="t", calendar_id="primary",
                        body=_basic_body("ced_q1"),
                    )
                assert exc.value.status_code == 401
            finally:
                _unpatch_httpx(original)

        _run(body())

    def test_r_network_failure_on_create_propagates(self):
        async def body():
            transport = _MockGoogleTransport()
            transport.raise_network_error_on_post = True
            original = _patch_httpx(transport)
            try:
                p = RealGoogleCalendarProvider()
                with pytest.raises(httpx.HTTPError):
                    await p.create_event(
                        access_token="t", calendar_id="primary",
                        body=_basic_body("ced_r1"),
                    )
            finally:
                _unpatch_httpx(original)

        _run(body())

    def test_r2_network_failure_on_idempotency_lookup_falls_through(self):
        """A transient failure on the GET idempotency check must not block
        create() entirely — it should fall through to attempting create."""
        async def body():
            transport = _MockGoogleTransport()
            original_handle = transport.handle_async_request

            async def _flaky(request):
                if request.method == "GET":
                    raise httpx.ConnectError("simulated lookup failure")
                return await original_handle(request)

            transport.handle_async_request = _flaky  # type: ignore[method-assign]
            original = _patch_httpx(transport)
            try:
                p = RealGoogleCalendarProvider()
                created = await p.create_event(
                    access_token="t", calendar_id="primary",
                    body=_basic_body("ced_r2"),
                )
                assert created["id"]
            finally:
                _unpatch_httpx(original)

        _run(body())


# ---------------------------------------------------------------------------
# S — Index initialization
# ---------------------------------------------------------------------------
class TestG_Indexes:
    def test_s_calendar_status_index_created(self):
        async def body():
            client, db = _db()
            try:
                await IntelligenceService(db, None).ensure_ready()
                idx = await db.calendar_event_drafts.index_information()
                assert "user_cal_status" in idx
                assert "user_cal_start" in idx
            finally:
                client.close()

        _run(body())


# ---------------------------------------------------------------------------
# T — Tool registry unchanged
# ---------------------------------------------------------------------------
class TestH_ToolRegistryUnchanged:
    def test_t_v286a_scope_superseded_by_v286b(self):
        """V2.8.6a's own report explicitly deferred Calendar capabilities to
        V2.8.6b ("V2.8.6b li aggiungerà dopo il gate di questa foundation").
        This test now asserts the V2.8.6b invariant instead: exactly the
        four documented capabilities exist, nothing extra."""
        registry = ToolRegistry(db=None)
        public = registry.list_public()
        names = {str(t.get("name") or t.get("capability") or "") for t in public}
        calendar_names = {n for n in names if "calendar" in n.lower()}
        assert calendar_names == {
            "get_calendar_events",
            "create_calendar_event",
            "update_calendar_event",
            "cancel_calendar_event",
        }
