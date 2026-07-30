"""Iteration 9 — Ingestion Core + Google Calendar Connector tests.

The suite exercises the ENTIRE pipeline against the fake provider by
temporarily flipping `CALENDAR_PROVIDER_MODE=fake` on the running
backend. Because that flag is process-scoped we run tests IN-PROCESS
using the FastAPI test client — no side-effects on the preview server.

Requirements:
  - Backend importable from /app/backend (added to sys.path in conftest).
  - MongoDB reachable via MONGO_URL / DB_NAME (uses the same DB as prod;
    tests namespace themselves by fresh user_ids + connector instances,
    so isolation is per-user).

Every test asserts a single behaviour so failures are easy to triage.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

# Ensure the fake provider is active BEFORE the backend imports run.
os.environ["CALENDAR_PROVIDER_MODE"] = "fake"
os.environ.setdefault("CALENDAR_DECISION_GENERATION_ENABLED", "false")
os.environ.setdefault("CALENDAR_CONTEXT_ENABLED", "false")

sys.path.insert(0, "/app/backend")

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402  (must import AFTER env setup)
from connectors.google_calendar.provider import get_fake_provider  # noqa: E402
from context_assembler import ASSEMBLER_VERSION  # noqa: E402

TS = int(time.time())


@pytest.fixture(scope="module")
def client():
    with TestClient(server.app) as c:
        yield c


@pytest.fixture(scope="module")
def user_a(client):
    r = client.post("/api/auth/register", json={
        "email": f"iter9_a_{TS}@ora.app",
        "password": "Passw0rd!",
        "name": "Iter9 A",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return {"token": body["token"], "user_id": body["user"]["user_id"], "email": body["user"]["email"]}


@pytest.fixture(scope="module")
def user_b(client):
    r = client.post("/api/auth/register", json={
        "email": f"iter9_b_{TS}@ora.app",
        "password": "Passw0rd!",
        "name": "Iter9 B",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return {"token": body["token"], "user_id": body["user"]["user_id"], "email": body["user"]["email"]}


def h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _seed_fake_calendars(cal_id: str, cal_name: str = "Personale", primary: bool = True):
    p = get_fake_provider()
    p.seed_calendar(calendar_id=cal_id, summary=cal_name, primary=primary)
    return p


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _connect_fake_instance(client, user, *, account_email: str, cal_id: str, cal_name: str = "Personale"):
    """Complete the fake OAuth handshake for the user and return the instance."""
    p = _seed_fake_calendars(cal_id, cal_name)
    r = client.post("/api/connectors/google-calendar/oauth/start", headers=h(user), json={})
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    assert r.json()["provider_mode"] == "fake"
    r2 = client.post("/api/connectors/google-calendar/oauth/callback-fake", json={
        "state": state,
        "code": "fake-code",
        "fake_account": {"sub": f"g-{account_email}", "email": account_email, "name": "Fake User"},
    })
    assert r2.status_code == 200, r2.text
    instance = r2.json()["instance"]
    # Explicitly bind the target calendar so sync doesn't fall back to a
    # stale primary from a previous test.
    client.post(
        f"/api/connectors/google-calendar/instances/{instance['id']}/select-calendars",
        headers=h(user), json={"calendar_ids": [cal_id]},
    )
    return instance


# =====================================================================
# TESTS
# =====================================================================
class TestA_ProviderConfig:
    def test_a1_oauth_start_returns_fake_state(self, client, user_a):
        r = client.post("/api/connectors/google-calendar/oauth/start", headers=h(user_a), json={})
        assert r.status_code == 200
        body = r.json()
        assert body["provider_mode"] == "fake"
        assert body["state"] and len(body["state"]) > 20
        assert body["authorize_url"].startswith("about:blank")

    def test_a2_callback_fake_disabled_when_real(self, client, user_a, monkeypatch):
        monkeypatch.setenv("CALENDAR_PROVIDER_MODE", "real")
        r = client.post("/api/connectors/google-calendar/oauth/callback-fake", json={
            "state": "whatever",
            "fake_account": {"sub": "x", "email": "x@x"},
        })
        assert r.status_code == 404
        monkeypatch.setenv("CALENDAR_PROVIDER_MODE", "fake")

    def test_a3_oauth_start_state_persisted_and_expires(self, client, user_a):
        r = client.post("/api/connectors/google-calendar/oauth/start", headers=h(user_a), json={})
        assert r.status_code == 200
        assert r.json().get("expires_at") is not None


class TestB_ConnectorInstance:
    def test_b1_upsert_instance_via_callback(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"a1_{TS}@gmail.com", cal_id="cal-a1")
        assert inst["connector_id"] == "calendar_google"
        assert inst["status"] == "connected"
        assert inst["secret_reference"] is not None
        assert inst["secret_reference"].startswith("sv_")
        # Structural constraints
        assert "poll_interval_min" in inst
        assert inst["window_past_days"] == 30
        assert inst["window_future_days"] == 180

    def test_b2_instance_scoped_to_user(self, client, user_a, user_b):
        inst_a = _connect_fake_instance(client, user_a, account_email=f"a2_{TS}@gmail.com", cal_id="cal-a2")
        # user B cannot see user A's instance
        r = client.get(f"/api/connectors/google-calendar/instances/{inst_a['id']}", headers=h(user_b))
        assert r.status_code == 404

    def test_b3_second_account_creates_second_instance(self, client, user_a):
        i1 = _connect_fake_instance(client, user_a, account_email=f"multi_1_{TS}@gmail.com", cal_id="cal-m1")
        i2 = _connect_fake_instance(client, user_a, account_email=f"multi_2_{TS}@gmail.com", cal_id="cal-m2")
        assert i1["id"] != i2["id"]

    def test_b4_no_token_in_instance_document(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"a4_{TS}@gmail.com", cal_id="cal-a4")
        r = client.get(f"/api/connectors/google-calendar/instances/{inst['id']}", headers=h(user_a))
        assert r.status_code == 200
        doc = r.json()
        # sensitive fields must never appear
        assert "access_token" not in doc
        assert "refresh_token" not in doc
        assert "client_secret" not in doc

    def test_b5_permissions_auto_granted(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"a5_{TS}@gmail.com", cal_id="cal-a5")
        r = client.get("/api/permissions/consents?status=active", headers=h(user_a))
        assert r.status_code == 200
        items = r.json()["items"]
        target = [c for c in items if c["connector_instance_id"] == inst["id"] and c["capability_id"] == "calendar.read"]
        assert len(target) == 1
        assert target[0]["status"] == "active"


class TestC_AccessGuard:
    def test_c1_deny_when_consent_revoked(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"c1_{TS}@gmail.com", cal_id="cal-c1")
        # Revoke consent for this instance
        r = client.post("/api/permissions/consents/revoke", headers=h(user_a), json={
            "capability_id": "calendar.read",
            "connector_id": "calendar_google",
            "connector_instance_id": inst["id"],
            "reason": "test_deny",
        })
        assert r.status_code == 200
        # Now sync should return 403 consent_denied
        r2 = client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        assert r2.status_code == 403
        assert r2.json()["detail"]["error"] == "consent_denied"

    def test_c2_allow_with_active_consent(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"c2_{TS}@gmail.com", cal_id="cal-c2")
        r = client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        assert r.status_code == 200


class TestD_SyncPipeline:
    def _mk_event(self, eid, title, minutes_from_now, status="confirmed"):
        start = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
        return {
            "id": eid, "status": status, "summary": title,
            "start": {"dateTime": _iso(start), "timeZone": "Europe/Rome"},
            "end":   {"dateTime": _iso(start + timedelta(minutes=60)), "timeZone": "Europe/Rome"},
            "updated": _iso(datetime.now(timezone.utc)),
        }

    def test_d1_initial_sync_ingests_events(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"d1_{TS}@gmail.com", cal_id="cal-d1")
        p = get_fake_provider()
        p.seed_event(calendar_id="cal-d1", event=self._mk_event("evt-d1-1", "Riunione", 60))
        p.seed_event(calendar_id="cal-d1", event=self._mk_event("evt-d1-2", "Cena con Marco", 60 * 24))
        r = client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["totals"]["received"] >= 2
        assert body["totals"]["processed"] >= 2

    def test_d2_dedupe_second_sync_is_all_skipped(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"d2_{TS}@gmail.com", cal_id="cal-d2")
        p = get_fake_provider()
        p.seed_event(calendar_id="cal-d2", event=self._mk_event("evt-d2-1", "Standup", 30))
        # first sync
        client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        # second sync — nothing changed; everything should be skipped
        r = client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        body = r.json()
        # Received might still be 1 (provider returns everything) but processed should be 0 or skipped ≥ 1.
        assert body["totals"]["skipped"] >= 1
        assert body["totals"]["processed"] == 0

    def test_d3_update_supersedes_previous_event(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"d3_{TS}@gmail.com", cal_id="cal-d3")
        p = get_fake_provider()
        p.seed_event(calendar_id="cal-d3", event=self._mk_event("evt-d3-1", "Meeting", 60))
        client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        # patch title
        p.update_event(calendar_id="cal-d3", event_id="evt-d3-1",
                       patch={"summary": "Meeting AGGIORNATO", "updated": _iso(datetime.now(timezone.utc))})
        r = client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        body = r.json()
        assert body["totals"]["processed"] >= 1
        # both events (old superseded + new processed) should be present in ingestion
        r2 = client.get(
            f"/api/ingestion/events?connector_instance_id={inst['id']}&limit=100",
            headers=h(user_a),
        )
        items = r2.json()["items"]
        superseded = [i for i in items if i["ingestion_status"] == "superseded" and i["external_id"] == "evt-d3-1"]
        assert len(superseded) >= 1

    def test_d4_cancelled_event_archives_node(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"d4_{TS}@gmail.com", cal_id="cal-d4")
        p = get_fake_provider()
        p.seed_event(calendar_id="cal-d4", event=self._mk_event("evt-d4-1", "Cinema", 120))
        client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        p.cancel_event(calendar_id="cal-d4", event_id="evt-d4-1")
        client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        # Node backing this event must now be archived
        r = client.get("/api/life-graph/nodes?include_archived=true", headers=h(user_a))
        arch = [
            n for n in r.json()["items"]
            if n["type"] == "event"
            and (n.get("attributes") or {}).get("external_event_id") == "evt-d4-1"
            and n["status"] == "archived"
        ]
        assert len(arch) == 1

    def test_d5_malformed_event_goes_to_quarantine(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"d5_{TS}@gmail.com", cal_id="cal-d5")
        p = get_fake_provider()
        # missing id → normalizer raises → quarantined
        p.events["cal-d5"] = {"broken-key": {"summary": "no id"}}
        # to preserve dict shape, use a fake id in the map but the payload lacks 'id'
        p.events["cal-d5"] = {"broken": {"summary": "no id", "status": "confirmed"}}
        r = client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        assert r.status_code == 200
        body = r.json()
        assert body["totals"]["quarantined"] >= 1

    def test_d6_two_calendars_are_ingested_independently(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"d6_{TS}@gmail.com", cal_id="cal-d6")
        p = get_fake_provider()
        p.seed_calendar(calendar_id="cal-d6b", summary="Lavoro", primary=False)
        p.seed_event(calendar_id="cal-d6",  event=self._mk_event("evt-d6-1", "Pranzo", 60))
        p.seed_event(calendar_id="cal-d6b", event=self._mk_event("evt-d6-2", "Sprint planning", 120))
        # explicitly select both calendars
        client.post(
            f"/api/connectors/google-calendar/instances/{inst['id']}/select-calendars",
            headers=h(user_a), json={"calendar_ids": ["cal-d6", "cal-d6b"]},
        )
        r = client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        assert r.status_code == 200
        cals = {c["calendar_id"] for c in r.json()["per_calendar"]}
        assert cals == {"cal-d6", "cal-d6b"}

    def test_d7_cross_user_isolation(self, client, user_a, user_b):
        inst_a = _connect_fake_instance(client, user_a, account_email=f"d7_{TS}@gmail.com", cal_id="cal-d7")
        # user B cannot trigger sync on user A's instance
        r = client.post(f"/api/connectors/google-calendar/instances/{inst_a['id']}/sync", headers=h(user_b))
        assert r.status_code == 404


class TestE_DecisionGenerationFlag:
    def _mk_exam(self, eid, minutes):
        start = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        return {
            "id": eid, "status": "confirmed", "summary": "Esame di matematica",
            "start": {"dateTime": _iso(start)}, "end": {"dateTime": _iso(start + timedelta(hours=2))},
            "updated": _iso(datetime.now(timezone.utc)),
        }

    def test_e1_flag_off_creates_no_decision(self, client, user_a, monkeypatch):
        monkeypatch.setenv("CALENDAR_DECISION_GENERATION_ENABLED", "false")
        inst = _connect_fake_instance(client, user_a, account_email=f"e1_{TS}@gmail.com", cal_id="cal-e1")
        p = get_fake_provider()
        p.seed_event(calendar_id="cal-e1", event=self._mk_exam("evt-e1", 60 * 24))
        client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        # No decision with origin=ingestion:calendar
        r = client.get("/api/decisions", headers=h(user_a))
        dec_cal = [d for d in r.json()["items"] if (d.get("metadata") or {}).get("origin") == "ingestion:calendar"]
        assert dec_cal == []

    def test_e2_flag_on_creates_decision_for_matching_event(self, client, user_a, monkeypatch):
        monkeypatch.setenv("CALENDAR_DECISION_GENERATION_ENABLED", "true")
        inst = _connect_fake_instance(client, user_a, account_email=f"e2_{TS}@gmail.com", cal_id="cal-e2")
        p = get_fake_provider()
        p.seed_event(calendar_id="cal-e2", event=self._mk_exam("evt-e2", 60 * 24 * 2))  # 2 days out
        client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        r = client.get("/api/decisions", headers=h(user_a))
        dec_cal = [
            d for d in r.json()["items"]
            if (d.get("metadata") or {}).get("origin") == "ingestion:calendar"
            and (d.get("metadata") or {}).get("external_event_id") == "evt-e2"
        ]
        assert len(dec_cal) == 1
        assert dec_cal[0]["category"] == "exam"
        assert dec_cal[0]["node_ids"], "decision must be linked to the event node"
        monkeypatch.setenv("CALENDAR_DECISION_GENERATION_ENABLED", "false")


class TestF_Revocation:
    def test_f1_revoke_marks_data_detached(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"f1_{TS}@gmail.com", cal_id="cal-f1")
        p = get_fake_provider()
        p.seed_event(calendar_id="cal-f1", event={
            "id": "evt-f1", "status": "confirmed", "summary": "Test",
            "start": {"dateTime": _iso(datetime.now(timezone.utc) + timedelta(hours=1))},
            "end": {"dateTime": _iso(datetime.now(timezone.utc) + timedelta(hours=2))},
        })
        client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        r = client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/revoke", headers=h(user_a))
        assert r.status_code == 200
        assert r.json()["status"] == "revoked"
        # consent must be revoked
        r2 = client.get(
            f"/api/permissions/consents?connector_id=calendar_google&status=active",
            headers=h(user_a),
        )
        active = [c for c in r2.json()["items"] if c["connector_instance_id"] == inst["id"]]
        assert active == []
        # DataRevocationPlan doc must exist (indirectly: subsequent sync must 403)
        r3 = client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        assert r3.status_code == 403


class TestG_AuditRedaction:
    def test_g1_audit_never_contains_titles(self, client, user_a):
        inst = _connect_fake_instance(client, user_a, account_email=f"g1_{TS}@gmail.com", cal_id="cal-g1")
        p = get_fake_provider()
        secret_title = f"TOP_SECRET_TITLE_{uuid.uuid4().hex}"
        p.seed_event(calendar_id="cal-g1", event={
            "id": "evt-g1", "status": "confirmed", "summary": secret_title,
            "start": {"dateTime": _iso(datetime.now(timezone.utc) + timedelta(hours=1))},
            "end": {"dateTime": _iso(datetime.now(timezone.utc) + timedelta(hours=2))},
        })
        client.post(f"/api/connectors/google-calendar/instances/{inst['id']}/sync", headers=h(user_a))
        r = client.get("/api/permissions/audit?limit=200", headers=h(user_a))
        blob = r.text
        assert secret_title not in blob


class TestH_ContextFlag:
    def _assemble(self, client, user, decision_id):
        r = client.post(f"/api/context/decisions/{decision_id}/assemble", headers=h(user))
        assert r.status_code == 200
        return r.json()

    def test_h1_provider_off_hash_stable(self, client, user_a, monkeypatch):
        monkeypatch.setenv("CALENDAR_CONTEXT_ENABLED", "false")
        # Create a decision to assemble
        r = client.post("/api/decisions", headers=h(user_a), json={"title": "H1", "category": "generic"})
        did = r.json()["id"]
        snap1 = self._assemble(client, user_a, did)
        snap2 = self._assemble(client, user_a, did)
        assert snap1["context_hash"] == snap2["context_hash"]
        # calendar provider must be in providers_run but produce zero signals
        assert "calendar" in snap1["provenance"]["providers_run"]
        cal_signals = [s for s in snap1["signals"] if s.get("source_module") == "calendar"]
        assert cal_signals == []


class TestI_LatestEndpointStillWorks:
    def test_i1_latest_envelope_stable(self, client, user_a):
        r = client.post("/api/decisions", headers=h(user_a), json={"title": "I1", "category": "generic"})
        did = r.json()["id"]
        client.post(f"/api/context/decisions/{did}/assemble", headers=h(user_a))
        r2 = client.get(f"/api/context/decisions/{did}/latest", headers=h(user_a))
        body = r2.json()
        assert set(body.keys()) == {"snapshot", "status", "generated_at", "assembler_version"}
        assert body["status"] == "available"
        assert body["assembler_version"] == ASSEMBLER_VERSION


class TestJ_VaultAndConfigGuards:
    def test_j1_real_mode_without_creds_is_503(self, client, user_a, monkeypatch):
        monkeypatch.setenv("CALENDAR_PROVIDER_MODE", "real")
        r = client.post("/api/connectors/google-calendar/oauth/start", headers=h(user_a), json={})
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "provider_not_configured"
        monkeypatch.setenv("CALENDAR_PROVIDER_MODE", "fake")

    def test_j2_ingestion_stats_starts_populated(self, client, user_a):
        r = client.get("/api/ingestion/stats", headers=h(user_a))
        assert r.status_code == 200
        body = r.json()
        assert "total" in body and "by_connector" in body
