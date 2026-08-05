"""Unit tests: localhost ↔ 127.0.0.1 OAuth redirect allowlisting (no network)."""
from __future__ import annotations

import os

import pytest

from connectors.google_calendar.oauth import (
    allowed_frontend_origins,
    allowed_oauth_redirect_uris,
    resolve_redirect_uri,
    sanitize_redirect_after,
)


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("FRONTEND_URLS", raising=False)
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URIS", raising=False)


def test_allowed_redirect_uris_expand_loopback(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/connectors/google-calendar/oauth/callback",
    )
    uris = allowed_oauth_redirect_uris()
    assert "http://localhost:8000/api/connectors/google-calendar/oauth/callback" in uris
    assert "http://127.0.0.1:8000/api/connectors/google-calendar/oauth/callback" in uris


def test_resolve_redirect_uri_matches_request_host(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/connectors/google-calendar/oauth/callback",
    )
    chosen = resolve_redirect_uri(request_base="http://127.0.0.1:8000")
    assert chosen == "http://127.0.0.1:8000/api/connectors/google-calendar/oauth/callback"


def test_sanitize_redirect_after_accepts_both_frontend_hosts():
    origins = set(allowed_frontend_origins())
    assert "http://localhost:8081" in origins
    assert "http://127.0.0.1:8081" in origins
    assert sanitize_redirect_after("http://localhost:8081/settings") == "http://localhost:8081/settings"
    assert sanitize_redirect_after("http://127.0.0.1:8081/settings") == "http://127.0.0.1:8081/settings"
    assert sanitize_redirect_after("https://evil.example/phish") is None
    assert sanitize_redirect_after("javascript:alert(1)") is None


def test_no_loopback_expand_outside_dev(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "https://app.example.com/api/connectors/google-calendar/oauth/callback",
    )
    uris = allowed_oauth_redirect_uris()
    assert uris == ["https://app.example.com/api/connectors/google-calendar/oauth/callback"]
