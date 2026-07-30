"""
Iter9 — live preview smoke tests against the public preview URL.
Focus: real-mode configuration guards + registry bump + fresh-user shapes.
Runs against: EXPO_PUBLIC_BACKEND_URL (must NOT have Google creds configured).
"""
import os
import uuid
import time
import requests
import pytest

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://ora-decision-engine.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def user_token():
    """Register a fresh user for isolation."""
    email = f"iter9live_{int(time.time())}_{uuid.uuid4().hex[:6]}@ora.app"
    r = requests.post(f"{BASE}/api/auth/register",
                      json={"email": email, "password": "Passw0rd!123", "name": "Iter9 Live"},
                      timeout=15)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---- Config-guard smoke -----------------------------------------------------

def test_oauth_start_returns_503_provider_not_configured(user_token):
    r = requests.post(f"{BASE}/api/connectors/google-calendar/oauth/start",
                      headers=_h(user_token), json={}, timeout=15)
    assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
    body = r.json()
    # FastAPI wraps HTTPException.detail under 'detail'
    assert "detail" in body
    detail = body["detail"]
    # detail may be dict or string; spec requires dict shape
    assert isinstance(detail, dict), f"expected dict detail, got: {detail!r}"
    assert detail.get("error") == "provider_not_configured", f"error mismatch: {detail}"
    assert "message" in detail and isinstance(detail["message"], str)


def test_oauth_start_requires_auth():
    r = requests.post(f"{BASE}/api/connectors/google-calendar/oauth/start",
                      json={}, timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


def test_callback_fake_disabled_in_real_mode(user_token):
    # Use a well-formed payload so we test the mode guard, not Pydantic validation.
    payload = {"state": "x", "code": "y", "fake_account": {"email": "a@b.com"}}
    r = requests.post(f"{BASE}/api/connectors/google-calendar/oauth/callback-fake",
                      headers=_h(user_token), json=payload, timeout=15)
    assert r.status_code == 404, f"expected 404 in real mode, got {r.status_code}: {r.text}"
    assert "Fake callback disabled" in r.text or "disabled" in r.text.lower()


# ---- Fresh-user shapes ------------------------------------------------------

def test_instances_empty_for_fresh_user(user_token):
    r = requests.get(f"{BASE}/api/connectors/google-calendar/instances",
                     headers=_h(user_token), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"items": []}, f"unexpected body: {body}"


def test_ingestion_stats_zero_for_fresh_user(user_token):
    r = requests.get(f"{BASE}/api/ingestion/stats",
                     headers=_h(user_token), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("total") == 0
    assert body.get("by_connector") == {}


def test_ingestion_events_empty_for_fresh_user(user_token):
    r = requests.get(f"{BASE}/api/ingestion/events",
                     headers=_h(user_token), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("items") == []


# ---- Registry bump ---------------------------------------------------------

def test_registry_bumps_google_calendar_to_available(user_token):
    r = requests.get(f"{BASE}/api/connectors/registry",
                     headers=_h(user_token), timeout=15)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    gc = [it for it in items if it["id"] == "calendar_google"]
    assert len(gc) == 1, f"calendar_google not in registry: {[it['id'] for it in items]}"
    assert gc[0]["status"] == "available", f"expected 'available', got {gc[0]['status']}"


def test_registry_single_lookup(user_token):
    r = requests.get(f"{BASE}/api/connectors/registry/calendar_google",
                     headers=_h(user_token), timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "available"
