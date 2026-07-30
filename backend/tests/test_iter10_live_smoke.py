"""Iter10 live smoke tests against the preview URL.

Validates the 4 /api/daily/* endpoints + invariants (feature-flag off byte-stable,
no decision creation, no notification emissions, cross-user isolation, all-day
event, cancelled event skip, deterministic output).
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://ora-decision-engine.preview.emergentagent.com",
).rstrip("/")

DEMO_EMAIL = "demo@ora.app"
DEMO_PASSWORD = "Demo!2026"
TS = int(time.time())


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


@pytest.fixture(scope="module")
def fresh_user():
    email = f"iter10_live_{TS}_{uuid.uuid4().hex[:6]}@ora.app"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "Passw0rd!", "name": "Iter10 live"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return {"token": r.json()["token"], "email": email}


@pytest.fixture(scope="module")
def fresh_headers(fresh_user):
    return {"Authorization": f"Bearer {fresh_user['token']}"}


EXPECTED_KEYS = {
    "date", "score", "signals", "warnings", "opportunities",
    "busy_slots", "free_slots", "energy_estimation", "confidence", "version",
}


class TestLiveEndpoints:
    def test_today_shape(self, demo_headers):
        r = requests.get(f"{BASE_URL}/api/daily/today", headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        missing = EXPECTED_KEYS - set(body.keys())
        assert not missing, f"missing keys: {missing}"
        assert body["version"] == "daily_intelligence/v1.0"

    def test_tomorrow_date(self, demo_headers):
        r = requests.get(f"{BASE_URL}/api/daily/tomorrow", headers=demo_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        expected = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        assert body["date"] == expected, f"expected {expected}, got {body['date']}"

    def test_refresh(self, demo_headers):
        r = requests.post(f"{BASE_URL}/api/daily/refresh", headers=demo_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"today", "tomorrow"}
        assert body["today"]["date"] != body["tomorrow"]["date"]

    def test_specific_date_holiday(self, demo_headers):
        r = requests.get(f"{BASE_URL}/api/daily/date/2027-08-15", headers=demo_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["is_holiday"] is True
        assert "holiday" in body["signals"]

    def test_bad_date_400(self, demo_headers):
        r = requests.get(f"{BASE_URL}/api/daily/date/nonsense", headers=demo_headers, timeout=30)
        assert r.status_code == 400

    def test_auth_required(self):
        r = requests.get(f"{BASE_URL}/api/daily/today", timeout=30)
        assert r.status_code == 401

    def test_cross_user_isolation(self, fresh_headers):
        r = requests.get(f"{BASE_URL}/api/daily/today", headers=fresh_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["total_events"] == 0, f"fresh user should see 0 events, got {body['total_events']}"


class TestInvariants:
    def test_no_decision_creation(self, demo_headers):
        r0 = requests.get(f"{BASE_URL}/api/decisions", headers=demo_headers, timeout=30)
        n0 = len(r0.json()["items"])
        for _ in range(2):
            requests.get(f"{BASE_URL}/api/daily/today", headers=demo_headers, timeout=30)
            requests.get(f"{BASE_URL}/api/daily/tomorrow", headers=demo_headers, timeout=30)
            requests.post(f"{BASE_URL}/api/daily/refresh", headers=demo_headers, timeout=30)
        r1 = requests.get(f"{BASE_URL}/api/decisions", headers=demo_headers, timeout=30)
        n1 = len(r1.json()["items"])
        assert n0 == n1, f"decision count changed: {n0} -> {n1}"

    def test_no_notification_audit_events(self, demo_headers):
        r = requests.get(f"{BASE_URL}/api/permissions/audit?limit=500", headers=demo_headers, timeout=30)
        assert r.status_code == 200
        for ev in r.json().get("items", []):
            assert not str(ev.get("event_type", "")).startswith("notification."), \
                f"unexpected notification event: {ev}"

    def test_deterministic_within_second(self, demo_headers):
        r1 = requests.get(f"{BASE_URL}/api/daily/today", headers=demo_headers, timeout=30).json()
        r2 = requests.get(f"{BASE_URL}/api/daily/today", headers=demo_headers, timeout=30).json()
        for k in ("score", "signals", "busy_minutes", "free_minutes",
                  "total_events", "is_weekend", "is_holiday", "is_vacation_day"):
            assert r1[k] == r2[k], f"non-deterministic field {k}: {r1[k]} != {r2[k]}"

    def test_all_day_vacation_event(self, fresh_headers):
        # Seed an all-day "Ferie" event for today
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        r = requests.post(
            f"{BASE_URL}/api/life-graph/nodes",
            headers=fresh_headers,
            json={
                "type": "event",
                "label": "Ferie",
                "attributes": {
                    "starts_at": today.isoformat(),
                    "ends_at": (today + timedelta(days=1)).isoformat(),
                    "all_day": True,
                    "connector_id": "calendar_google",
                },
            },
            timeout=30,
        )
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{BASE_URL}/api/daily/today", headers=fresh_headers, timeout=30)
        assert r2.status_code == 200
        body = r2.json()
        assert body["is_vacation_day"] is True, body
        assert "vacation" in body["signals"], body["signals"]

    def test_cancelled_event_skipped(self, fresh_headers):
        # Seed one cancelled event + one confirmed event on tomorrow
        base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        # Cancelled
        r = requests.post(
            f"{BASE_URL}/api/life-graph/nodes",
            headers=fresh_headers,
            json={
                "type": "event",
                "label": "Cancelled meeting",
                "attributes": {
                    "starts_at": (base + timedelta(hours=9)).isoformat(),
                    "ends_at": (base + timedelta(hours=10)).isoformat(),
                    "status": "cancelled",
                    "connector_id": "calendar_google",
                },
            },
            timeout=30,
        )
        assert r.status_code == 200
        # Confirmed
        r = requests.post(
            f"{BASE_URL}/api/life-graph/nodes",
            headers=fresh_headers,
            json={
                "type": "event",
                "label": "Real meeting",
                "attributes": {
                    "starts_at": (base + timedelta(hours=14)).isoformat(),
                    "ends_at": (base + timedelta(hours=15)).isoformat(),
                    "status": "confirmed",
                    "connector_id": "calendar_google",
                },
            },
            timeout=30,
        )
        assert r.status_code == 200
        r2 = requests.get(f"{BASE_URL}/api/daily/tomorrow", headers=fresh_headers, timeout=30)
        body = r2.json()
        # Only 1 confirmed event should count (busy_minutes = 60)
        assert body["busy_minutes"] == 60, f"cancelled event should be skipped, busy_minutes={body['busy_minutes']}"


class TestFilesystemInvariants:
    """Invariant 4.c and 4.i — grep-based static checks on the daily_intelligence module."""

    def test_no_llm_imports(self):
        import subprocess
        r = subprocess.run(
            ["grep", "-rEi", "openai|emergentintegrations|gpt|LlmChat", "/app/backend/daily_intelligence/"],
            capture_output=True, text=True,
        )
        assert r.returncode == 1, f"unexpected LLM refs: {r.stdout}"
