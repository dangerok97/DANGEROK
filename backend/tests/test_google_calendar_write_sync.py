"""Google Calendar WRITE sync tests (fake provider — not real Google verification).

Covers: connect status, scopes, create/update/delete, idempotency, conflict,
privacy sanitization, ambiguous date, user isolation, medical title.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ["CALENDAR_PROVIDER_MODE"] = "fake"
os.environ.setdefault("TOKEN_VAULT_BACKEND", "local")
os.environ.setdefault(
    "TOKEN_VAULT_KEY",
    "change-me-token-vault-key-32bytes-min!!!!!!!!",
)

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

from connectors.google_calendar.provider import (  # noqa: E402
    FakeGoogleCalendarProvider,
    GoogleCalendarAPIError,
    get_fake_provider,
)
from documents.intelligence.google_sync import (  # noqa: E402
    GoogleCalendarSyncService,
    DEFAULT_EVENT_MINUTES,
    build_google_event_body,
    sanitize_google_description,
)


MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _run(coro):
    # The session's own loop, not whatever the policy currently points at:
    # a suite that used asyncio.run() before this one has cleared that slot.
    return _loop_harness.run(coro)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Unit: privacy / body builder
# ---------------------------------------------------------------------------
class TestSanitizeAndBody:
    def test_medical_title_and_no_full_doc(self):
        draft = {
            "id": "ced_1",
            "title": "Referto completo paziente Rossi codice fiscale ABC",
            "description": "TESTO COMPLETO DEL REFERTO " * 20,
            "start_datetime": "2026-09-01T10:00:00+02:00",
            "end_datetime": "2026-09-01T11:00:00+02:00",
            "timezone": "Europe/Rome",
            "location": "Ospedale",
            "source_document_id": "doc_x",
            "priority": "high",
            "urgency": "soon",
        }
        body = build_google_event_body(draft, macro_category="medical")
        assert body["summary"] == "Visita specialistica"
        desc = body["description"]
        assert "TESTO COMPLETO" not in desc
        assert "codice fiscale" not in desc.lower()
        assert "Creato da ORA" in desc
        assert body["extendedProperties"]["private"]["ora_event_id"] == "ced_1"

    def test_all_day_uses_date(self):
        draft = {
            "id": "ced_2",
            "title": "Ferie",
            "start_datetime": "2026-08-10T00:00:00+02:00",
            "end_datetime": "2026-08-11T00:00:00+02:00",
            "timezone": "Europe/Rome",
            "all_day": True,
            "source_document_id": "doc_y",
        }
        body = build_google_event_body(draft)
        assert "date" in body["start"]
        assert body["start"]["date"] == "2026-08-10"

    def test_timed_event_rfc3339(self):
        draft = {
            "id": "ced_3",
            "title": "Meeting",
            "start_datetime": "2026-08-10T15:30:00",
            "end_datetime": "2026-08-10T16:30:00",
            "timezone": "Europe/Rome",
            "all_day": False,
            "source_document_id": "doc_z",
        }
        body = build_google_event_body(draft)
        assert "dateTime" in body["start"]
        assert "Europe/Rome" in body["start"]["timeZone"]

    # --- an event that has a beginning and no end --------------------------
    #
    # `end or start` produced an event that ended when it began. The provider
    # accepted it, the read-back confirmed it, and what landed in somebody's
    # calendar was a sliver they could not read — every check green, the
    # outcome wrong. These six pin down the whole rule: derive only when
    # nothing was said, and never over something that was.

    def test_start_only_gets_a_default_length(self):
        body = build_google_event_body({
            "id": "ced_len", "title": "Ritiro", "source_document_id": "d",
            "start_datetime": "2026-09-05T08:30:00", "timezone": "Europe/Rome",
        })
        start = datetime.fromisoformat(body["start"]["dateTime"])
        end = datetime.fromisoformat(body["end"]["dateTime"])
        assert end > start, "un evento che finisce quando comincia"
        assert end - start == timedelta(minutes=DEFAULT_EVENT_MINUTES)

    def test_an_explicit_end_is_never_recomputed(self):
        body = build_google_event_body({
            "id": "ced_end", "title": "Visita", "source_document_id": "d",
            "start_datetime": "2026-09-05T08:30:00",
            "end_datetime": "2026-09-05T08:45:00",
            "timezone": "Europe/Rome",
        })
        assert body["end"]["dateTime"].startswith("2026-09-05T08:45:00")

    def test_a_stated_duration_wins_over_the_default(self):
        body = build_google_event_body({
            "id": "ced_dur", "title": "Corso", "source_document_id": "d",
            "start_datetime": "2026-09-05T08:30:00", "duration_minutes": 150,
            "timezone": "Europe/Rome",
        })
        start = datetime.fromisoformat(body["start"]["dateTime"])
        end = datetime.fromisoformat(body["end"]["dateTime"])
        assert end - start == timedelta(minutes=150)

    def test_an_end_outranks_a_duration(self):
        body = build_google_event_body({
            "id": "ced_both", "title": "Corso", "source_document_id": "d",
            "start_datetime": "2026-09-05T08:30:00",
            "end_datetime": "2026-09-05T09:00:00",
            "duration_minutes": 150, "timezone": "Europe/Rome",
        })
        assert body["end"]["dateTime"].startswith("2026-09-05T09:00:00")

    def test_all_day_keeps_its_own_unit(self):
        """
        All-day is days, not hours, and Google reads its end as exclusive.

        So a single day ends on the next one — sending the same date twice is
        not a short event, it is a malformed one. Deliberately not routed
        through the hourly path: adding sixty minutes to a date is nonsense.
        """
        body = build_google_event_body({
            "id": "ced_day", "title": "Ferie", "source_document_id": "d",
            "start_datetime": "2026-08-10T00:00:00+02:00",
            "timezone": "Europe/Rome", "all_day": True,
        })
        assert body["start"]["date"] == "2026-08-10"
        assert body["end"]["date"] == "2026-08-11"
        assert "dateTime" not in body["start"] and "dateTime" not in body["end"]

    def test_the_timezone_survives_the_derivation(self):
        body = build_google_event_body({
            "id": "ced_tz", "title": "Riunione", "source_document_id": "d",
            "start_datetime": "2026-12-05T08:30:00", "timezone": "America/New_York",
        })
        assert body["start"]["timeZone"] == "America/New_York"
        assert body["end"]["timeZone"] == "America/New_York"
        # Derived in the person's own zone, not in UTC and not naively.
        assert body["end"]["dateTime"].startswith("2026-12-05T09:30:00-05:00")

    def test_missing_start_raises(self):
        with pytest.raises(ValueError):
            build_google_event_body({"id": "x", "title": "No date", "source_document_id": "d"})

    def test_sanitize_truncates(self):
        draft = {"description": "x" * 500, "id": "c", "source_document_id": "d"}
        out = sanitize_google_description(draft=draft)
        assert len(out) < 500
        assert "Creato da ORA" in out


# ---------------------------------------------------------------------------
# Fake provider write primitives
# ---------------------------------------------------------------------------
class TestFakeProviderWrite:
    def test_create_idempotent_by_ora_event_id(self):
        async def body():
            p = FakeGoogleCalendarProvider()
            p.seed_calendar(calendar_id="cal1", summary="P", primary=True)
            body_ev = {
                "summary": "A",
                "start": {"dateTime": "2026-08-10T10:00:00+02:00"},
                "end": {"dateTime": "2026-08-10T11:00:00+02:00"},
                "extendedProperties": {"private": {"ora_event_id": "ced_dup"}},
            }
            a = await p.create_event(access_token="t", calendar_id="cal1", body=body_ev)
            b = await p.create_event(access_token="t", calendar_id="cal1", body=body_ev)
            assert a["id"] == b["id"]

        _run(body())

    def test_etag_conflict_on_update(self):
        async def body():
            p = FakeGoogleCalendarProvider()
            p.seed_calendar(calendar_id="cal1", summary="P", primary=True)
            created = await p.create_event(
                access_token="t",
                calendar_id="cal1",
                body={
                    "summary": "A",
                    "start": {"dateTime": "2026-08-10T10:00:00+02:00"},
                    "end": {"dateTime": "2026-08-10T11:00:00+02:00"},
                },
            )
            # bump etag externally
            p.events["cal1"][created["id"]]["etag"] = "etag-external"
            with pytest.raises(GoogleCalendarAPIError) as ei:
                await p.update_event(
                    access_token="t",
                    calendar_id="cal1",
                    event_id=created["id"],
                    body={"summary": "B"},
                    etag=created["etag"],
                )
            assert ei.value.etag_conflict is True

        _run(body())

    def test_delete_missing_ok(self):
        async def body():
            p = FakeGoogleCalendarProvider()
            p.seed_calendar(calendar_id="cal1", summary="P", primary=True)
            ok = await p.delete_event(access_token="t", calendar_id="cal1", event_id="gone")
            assert ok is True

        _run(body())


# ---------------------------------------------------------------------------
# Sync service + Mongo (fake gcal wrapper)
# ---------------------------------------------------------------------------
class _FakeInstances:
    def __init__(self, store: dict):
        self.store = store

    async def update(self, user_id, instance_id, patch):
        inst = self.store.get(instance_id)
        if not inst or inst["user_id"] != user_id:
            raise LookupError("instance")
        inst.update(patch)
        return inst


class _FakeGcalService:
    def __init__(self, provider: FakeGoogleCalendarProvider, instance: dict):
        self.provider = provider
        self._instance = instance
        self.instances = _FakeInstances({instance["id"]: instance})

    async def list_instances(self, user_id: str):
        if self._instance.get("user_id") == user_id and self._instance.get("status") != "revoked":
            return [self._instance]
        return []

    async def list_calendars_for_instance(self, *, user_id: str, instance_id: str):
        cals = await self.provider.list_calendars(access_token="t")
        return [
            {"id": c.id, "summary": c.summary, "primary": c.primary, "access_role": c.access_role}
            for c in cals
        ]

    async def _get_access_token(self, *, user_id: str, instance: dict):
        if instance.get("status") == "revoked":
            raise RuntimeError("revoked")
        return "fake-access"


def _base_instance(user_id: str, cal_id: str = "primary"):
    return {
        "id": f"inst_{uuid.uuid4().hex[:8]}",
        "user_id": user_id,
        "status": "connected",
        "connector_id": "calendar_google",
        "display_label": "user@gmail.com",
        "authorized_scopes": [
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
        ],
        "selected_resource_ids": [cal_id],
        "metadata": {
            "account_email": "user@gmail.com",
            "default_calendar_id": cal_id,
        },
        "last_sync_at": None,
        "secret_reference": "sv_fake",
    }


async def _insert_draft(db, *, user_id: str, draft_id: str, **extra):
    doc = {
        "id": draft_id,
        "user_id": user_id,
        "provider": "internal",
        "title": "Evento sintetico ORA",
        "description": "Dettaglio breve",
        "start_datetime": "2026-09-15T10:00:00+02:00",
        "end_datetime": "2026-09-15T11:00:00+02:00",
        "timezone": "Europe/Rome",
        "all_day": False,
        "location": "Milano",
        "source_document_id": f"doc_{uuid.uuid4().hex[:8]}",
        "source_event_candidate_id": f"evc_{uuid.uuid4().hex[:8]}",
        "status": "confirmed",
        "created_at": _now(),
        "updated_at": _now(),
        "sync_provider": "internal",
        "sync_status": "local_only",
        "sync_version": 0,
        **extra,
    }
    await db.calendar_event_drafts.insert_one(doc)
    return doc


class TestSyncService:
    def test_status_write_capable_and_reconnect(self):
        async def body():
            from motor.motor_asyncio import AsyncIOMotorClient

            client = AsyncIOMotorClient(MONGO)
            db = client[DBNAME]
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                p = FakeGoogleCalendarProvider()
                p.seed_calendar(calendar_id="primary", summary="Primary", primary=True)
                inst = _base_instance(user)
                sync = GoogleCalendarSyncService(db=db, google_calendar_service=_FakeGcalService(p, inst))
                st = await sync.connection_status(user)
                assert st["connected"] is True
                assert st["write_capable"] is True
                assert st["needs_reconnect"] is False

                inst["authorized_scopes"] = [
                    "https://www.googleapis.com/auth/calendar.readonly",
                ]
                st2 = await sync.connection_status(user)
                assert st2["write_capable"] is False
                assert st2["needs_reconnect"] is True
            finally:
                client.close()

        _run(body())

    def test_create_update_delete_idempotent_conflict(self):
        async def body():
            from motor.motor_asyncio import AsyncIOMotorClient

            client = AsyncIOMotorClient(MONGO)
            db = client[DBNAME]
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                other = f"u_{uuid.uuid4().hex[:8]}"
                p = FakeGoogleCalendarProvider()
                p.seed_calendar(calendar_id="primary", summary="Primary", primary=True)
                inst = _base_instance(user)
                gcal = _FakeGcalService(p, inst)
                sync = GoogleCalendarSyncService(db=db, google_calendar_service=gcal)

                draft_id = f"ced_{uuid.uuid4().hex[:10]}"
                await _insert_draft(db, user_id=user, draft_id=draft_id)

                # isolation: other user cannot access draft
                with pytest.raises(LookupError):
                    await sync.sync_draft(user_id=other, draft_id=draft_id)

                # create
                out = await sync.sync_draft(user_id=user, draft_id=draft_id)
                assert out["sync_status"] == "synced"
                assert out["google_event_id"]
                gid = out["google_event_id"]
                assert out["google_event_html_link"]

                # double sync = update (no duplicate)
                out2 = await sync.sync_draft(user_id=user, draft_id=draft_id)
                assert out2["google_event_id"] == gid
                assert len(p.events["primary"]) == 1

                # conflict when remote etag changes
                p.events["primary"][gid]["etag"] = "etag-from-google-ui"
                await db.calendar_event_drafts.update_one(
                    {"id": draft_id},
                    {"$set": {"title": "Titolo ORA aggiornato", "sync_status": "synced"}},
                )
                conflicted = await sync.sync_draft(user_id=user, draft_id=draft_id)
                assert conflicted["sync_status"] == "conflict"

                # resolve overwrite
                resolved = await sync.resolve_conflict(
                    user_id=user, draft_id=draft_id, resolution="overwrite_ora",
                )
                assert resolved["sync_status"] == "synced"

                # delete google with confirmation
                deleted = await sync.delete_remote(
                    user_id=user, draft_id=draft_id, also_delete_google=True,
                )
                assert deleted["ok"] is True
                assert p.events["primary"][gid]["status"] == "cancelled"

                await db.calendar_event_drafts.delete_many({"user_id": user})
            finally:
                client.close()

        _run(body())

    def test_set_default_calendar(self):
        async def body():
            from motor.motor_asyncio import AsyncIOMotorClient

            client = AsyncIOMotorClient(MONGO)
            db = client[DBNAME]
            try:
                user = f"u_{uuid.uuid4().hex[:8]}"
                p = FakeGoogleCalendarProvider()
                p.seed_calendar(calendar_id="primary", summary="Primary", primary=True)
                p.seed_calendar(calendar_id="work", summary="Lavoro", primary=False)
                inst = _base_instance(user)
                sync = GoogleCalendarSyncService(db=db, google_calendar_service=_FakeGcalService(p, inst))
                st = await sync.set_default_calendar(user_id=user, calendar_id="work")
                assert st["default_calendar_id"] == "work"
            finally:
                client.close()

        _run(body())

    def test_confirm_rejects_ambiguous_without_override(self):
        async def body():
            from motor.motor_asyncio import AsyncIOMotorClient
            from documents.intelligence.service import IntelligenceService
            from documents.service import DocumentService
            from documents.storage import LocalFilesystemStorage
            import tempfile

            client = AsyncIOMotorClient(MONGO)
            db = client[DBNAME]
            try:
                tmp = tempfile.mkdtemp(prefix="ora_gcal_")
                dsvc = DocumentService(
                    db=db, storage=LocalFilesystemStorage(base_dir=tmp),
                    life_graph=None, knowledge=None,
                )
                intel = IntelligenceService(db, dsvc)
                user = f"u_{uuid.uuid4().hex[:8]}"
                up = await dsvc.upload(
                    user_id=user,
                    content=b"Appuntamento senza data chiara",
                    original_filename="amb.txt",
                    mime_type="text/plain",
                )
                doc_id = up["document"]["id"]
                ev_id = f"evc_{uuid.uuid4().hex[:8]}"
                await db.documents.update_one(
                    {"id": doc_id},
                    {"$set": {
                        "event_candidates": [{
                            "id": ev_id,
                            "source_document_id": doc_id,
                            "title": "Senza data",
                            "status": "proposed",
                            "ambiguous_date": True,
                            "start_datetime": None,
                            "timezone": "Europe/Rome",
                        }],
                    }},
                )
                with pytest.raises(ValueError):
                    await intel.confirm_event(user_id=user, doc_id=doc_id, event_id=ev_id)
                # with override ok (local only)
                conf = await intel.confirm_event(
                    user_id=user,
                    doc_id=doc_id,
                    event_id=ev_id,
                    overrides={"start_datetime": "2026-10-01T09:00:00+02:00"},
                    sync_to_google=False,
                )
                assert conf["ok"] is True
                assert conf["calendar_event"]["sync_status"] == "local_only"
                await dsvc.delete(user_id=user, doc_id=doc_id)
            finally:
                client.close()

        _run(body())


# ---------------------------------------------------------------------------
# HTTP smoke (fake OAuth) — uses shared TestClient when available
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client(shared_client):
    return shared_client


@pytest.fixture(scope="module")
def user_w(client):
    ts = uuid.uuid4().hex[:8]
    r = client.post("/api/auth/register", json={
        "email": f"gcal_w_{ts}@ora.app",
        "password": "Passw0rd!",
        "name": "GCal Write",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return {"token": body["token"], "user_id": body["user"]["user_id"]}


def _h(user):
    return {"Authorization": f"Bearer {user['token']}"}


class TestHttpWritePath:
    def test_oauth_start_and_status_and_calendars(self, client, user_w):
        p = get_fake_provider()
        cal_id = f"cal_w_{uuid.uuid4().hex[:6]}"
        p.seed_calendar(calendar_id=cal_id, summary="Test Write", primary=True)

        r = client.post(
            "/api/connectors/google-calendar/oauth/start",
            headers=_h(user_w),
            json={},
        )
        assert r.status_code == 200
        state = r.json()["state"]
        r2 = client.post("/api/connectors/google-calendar/oauth/callback-fake", json={
            "state": state,
            "code": "fake-code",
            "fake_account": {
                "sub": f"g-{user_w['user_id']}",
                "email": f"{user_w['user_id']}@gmail.com",
                "name": "Write User",
            },
        })
        assert r2.status_code == 200, r2.text
        inst = r2.json()["instance"]
        assert "access_token" not in inst
        assert "refresh_token" not in inst

        # write status
        st = client.get("/api/documents/calendar/google/status", headers=_h(user_w))
        assert st.status_code == 200
        body = st.json()
        assert body["connected"] is True
        assert body["write_capable"] is True

        # list calendars via documents API
        cals = client.get("/api/documents/calendar/google/calendars", headers=_h(user_w))
        assert cals.status_code == 200
        assert isinstance(cals.json().get("items"), list)

        # set default
        # pick first calendar id from connector list
        r_list = client.get(
            f"/api/connectors/google-calendar/instances/{inst['id']}/calendars",
            headers=_h(user_w),
        )
        assert r_list.status_code == 200
        items = r_list.json().get("items") or []
        if items:
            cid = items[0]["id"]
            patch = client.patch(
                "/api/documents/calendar/google/default",
                headers=_h(user_w),
                json={"calendar_id": cid},
            )
            assert patch.status_code == 200
            assert patch.json().get("default_calendar_id") == cid

    def test_callback_bad_state(self, client, user_w):
        r = client.post("/api/connectors/google-calendar/oauth/callback-fake", json={
            "state": "invalid-state-xyz",
            "code": "x",
            "fake_account": {"sub": "x", "email": "x@x"},
        })
        assert r.status_code in (400, 404, 410, 422)

    def test_unauthenticated_status(self, client):
        r = client.get("/api/documents/calendar/google/status")
        assert r.status_code in (401, 403)
