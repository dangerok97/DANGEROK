"""Local smoke tests — no Emergent preview URL required.

Uses Starlette TestClient for pure app checks, and optional live HTTP
checks against a running local uvicorn when available.
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

# Ensure required env before importing the app (deps loads at import time).
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ora_local_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("EMERGENT_GOOGLE_AUTH", "0")

from server import app  # noqa: E402

client = TestClient(app)
LIVE = os.environ.get("ORA_LIVE_URL", "http://127.0.0.1:8000").rstrip("/")


def test_root_ok():
    r = client.get("/api/")
    assert r.status_code == 200
    body = r.json()
    assert body.get("app") == "ORA"
    assert body.get("status") == "ok"


def test_health_shape():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("app") == "ORA"
    assert "database" in body
    assert "llm" in body
    assert body["llm"]["configured"] is False
    assert body["integrations"]["emergent_google_auth"] is False
    dumped = r.text.lower()
    assert "jwt_secret" not in dumped
    assert "password" not in dumped


def test_google_session_disabled():
    r = client.post("/api/auth/google-session", json={"session_token": "x"})
    assert r.status_code == 503
    detail = str(r.json().get("detail", "")).lower()
    assert "google" in detail or "non configurato" in detail


def test_live_register_login_roundtrip():
    """Exercise real uvicorn+Mongo when local server is up."""
    try:
        ping = httpx.get(f"{LIVE}/api/health", timeout=2.0)
    except Exception:
        pytest.skip("local uvicorn not running")
    if ping.status_code != 200 or not ping.json().get("database", {}).get("ok"):
        pytest.skip("local database not healthy")

    email = f"local.smoke.{uuid.uuid4().hex[:10]}@ora.app"
    password = "TestPass123!"
    reg = httpx.post(
        f"{LIVE}/api/auth/register",
        json={"email": email, "password": password, "name": "Local Smoke"},
        timeout=10.0,
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["token"]
    me = httpx.get(
        f"{LIVE}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    assert me.status_code == 200
    assert me.json()["email"] == email
    login = httpx.post(
        f"{LIVE}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10.0,
    )
    assert login.status_code == 200
    assert login.json()["token"]


def test_llm_not_configured_status():
    from llm import llm_status

    status = llm_status()
    assert status["configured"] is False
    assert status["provider"] == "none"
