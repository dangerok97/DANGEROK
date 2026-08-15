"""Connectivity / CORS / auth regression for AI-Core HTTP surface.

Ensures browser origins used in local Expo web can preflight, and that
missing auth is a real HTTP 401 (not a silent network failure).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Avoid requiring a live Mongo for route registration checks where possible.
os.environ.setdefault("MONGO_URL", os.environ.get("MONGO_URL") or "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME") or "ora_local")
os.environ.setdefault("JWT_SECRET", os.environ.get("JWT_SECRET") or "test-secret-for-connectivity")


@pytest.fixture(scope="module")
def client():
    from server import app

    with TestClient(app) as c:
        yield c


def test_ai_core_start_route_registered_unauth_is_401(client):
    """Request reaches FastAPI — missing bearer → 401, not connection failure."""
    res = client.post(
        "/api/conversation/ai-core/start",
        json={"text": "Come mi chiamo?", "origin": "text"},
    )
    assert res.status_code == 401
    detail = res.json().get("detail")
    assert detail


@pytest.mark.parametrize(
    "origin",
    ["http://127.0.0.1:8081", "http://localhost:8081"],
)
def test_ai_core_cors_preflight_local_web_origins(client, origin):
    res = client.options(
        "/api/conversation/ai-core/start",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert res.status_code in (200, 204)
    allow_origin = res.headers.get("access-control-allow-origin")
    # Starlette may echo the request Origin when credentials are enabled
    assert allow_origin in (origin, "*")
    allow_headers = (res.headers.get("access-control-allow-headers") or "").lower()
    assert "authorization" in allow_headers or allow_headers == "*"


def test_context_broker_db_none_safe():
    """Motor Database is not bool()-able — broker must use `is None`."""
    import asyncio
    from conversation_engine.ai_core.context_broker import ContextBroker

    async def _run():
        b = ContextBroker(db=None)
        facts = await b.retrieve(user_id="u", user_message="hi")
        assert facts == []

    asyncio.run(_run())


def test_health_ok(client):
    res = client.get("/api/")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"

