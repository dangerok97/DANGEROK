"""Native connector return, consent refusal and single-use state; no provider I/O."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from starlette.requests import Request

from connectors.google_calendar.oauth import OAuthStateInvalid, OAuthStateStore, sanitize_redirect_after


@pytest.mark.parametrize("url,expected", [
    ("ora://account/permessi", "ora://account/permessi"),
    ("ora://settings?arbitrary=discard#discard", "ora://settings"),
    ("ora://account/permessi?token=discard", "ora://account/permessi"),
    ("ora://another-screen", None),
    ("ora://settings/../../other", None),
    ("ora://user@settings", None),
    ("ora://settings:443", None),
    ("another://settings", None),
    ("https://outside.example.test/settings", None),
    ("//settings", None),
])
def test_only_registered_native_connector_return_screens_are_allowed(url, expected):
    assert sanitize_redirect_after(url) == expected


@pytest.mark.asyncio
async def test_concurrent_state_consumers_have_exactly_one_winner(monkeypatch):
    db = AsyncMongoMockClient().v162_oauth_race
    store = OAuthStateStore(db)
    created = await store.create(user_id="synthetic-owner", flow="mail_gmail")
    original_find = store.col.find_one
    both_read = asyncio.Event()
    count = 0

    async def find_together(*args, **kwargs):
        nonlocal count
        row = await original_find(*args, **kwargs)
        count += 1
        if count == 2:
            both_read.set()
        await both_read.wait()
        return row

    monkeypatch.setattr(store.col, "find_one", find_together)
    results = await asyncio.gather(
        store.consume(state=created["state"], expect_flow="mail_gmail"),
        store.consume(state=created["state"], expect_flow="mail_gmail"),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, OAuthStateInvalid) for result in results) == 1


@pytest.mark.asyncio
async def test_calendar_callback_cannot_spend_a_mailbox_state():
    from connectors.google_calendar.service import GoogleCalendarService

    db = AsyncMongoMockClient().v162_oauth_wrong_flow
    service = GoogleCalendarService(db=db, permissions=None, ingestion=None, vault=None)
    created = await service.oauth_state.create(user_id="synthetic-owner", flow="mail_gmail")
    with pytest.raises(OAuthStateInvalid, match="another flow"):
        await service.handle_oauth_callback(state=created["state"], code="synthetic", fake_account={"sub": "synthetic"})
    row = await db.google_oauth_sessions.find_one({"state": created["state"]})
    assert row["consumed"] is False
    assert await db.connector_instances.count_documents({}) == 0


def request():
    return Request({"type": "http", "method": "GET", "path": "/oauth/callback", "headers": []})


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,flow,screen", [
    ("gmail", "mail_gmail", "ora://account/permessi"),
    ("google_calendar", "calendar_google", "ora://settings"),
])
async def test_declining_consent_consumes_the_matching_state_and_returns_to_ora(monkeypatch, kind, flow, screen):
    import importlib
    module = importlib.import_module(f"connectors.{kind}.router")
    db = AsyncMongoMockClient().v162_oauth_declined
    store = OAuthStateStore(db)
    created = await store.create(user_id="synthetic-owner", flow=flow, redirect_after=screen)
    handler = AsyncMock(side_effect=AssertionError("declining must not exchange a code"))
    service = SimpleNamespace(oauth_state=store, handle_oauth_callback=handler)
    monkeypatch.setattr(module, "get_gmail_service" if kind == "gmail" else "get_google_calendar_service", lambda: service)
    if kind == "google_calendar":
        monkeypatch.setattr("social_auth.browser.maybe_handle_google_browser_callback", AsyncMock(return_value=None))
    response = await module.oauth_callback(request(), state=created["state"], code=None, error="access_denied")
    assert response.status_code == 302
    parsed = urlparse(response.headers["location"])
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == screen
    assert parse_qs(parsed.query) == {kind: ["cancelled"]}
    assert response.headers["cache-control"] == "no-store"
    handler.assert_not_awaited()
    with pytest.raises(HTTPException) as exc:
        await module.oauth_callback(request(), state=created["state"], code=None, error="access_denied")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,screen", [("gmail", "ora://account/permessi"), ("google_calendar", "ora://settings")])
async def test_connected_return_contains_only_instance_hint_for_authenticated_readback(monkeypatch, kind, screen):
    import importlib
    module = importlib.import_module(f"connectors.{kind}.router")
    service = SimpleNamespace(handle_oauth_callback=AsyncMock(return_value={
        "instance": {"id": "synthetic-instance"}, "redirect_after": screen,
    }))
    monkeypatch.setattr(module, "get_gmail_service" if kind == "gmail" else "get_google_calendar_service", lambda: service)
    if kind == "google_calendar":
        monkeypatch.setattr("social_auth.browser.maybe_handle_google_browser_callback", AsyncMock(return_value=None))
    response = await module.oauth_callback(request(), state="synthetic-state", code="synthetic-code", error=None)
    assert response.status_code == 302
    assert parse_qs(urlparse(response.headers["location"]).query) == {
        kind: ["connected"], "instance_id": ["synthetic-instance"],
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.asyncio
async def test_calendar_shared_callback_preserves_browser_login_cancellation(monkeypatch):
    import connectors.google_calendar.router as module
    expected = "https://ora.example.test/auth/google-complete?error=google_login_cancelled"
    monkeypatch.setattr("social_auth.browser.maybe_handle_google_browser_callback", AsyncMock(return_value=expected))
    unused = AsyncMock(side_effect=AssertionError("must not consume connector state for browser login"))
    monkeypatch.setattr(module, "get_google_calendar_service", unused)
    response = await module.oauth_callback(request(), state="synthetic-login", code=None, error="access_denied")
    assert response.status_code == 303
    assert response.headers["location"] == expected
    unused.assert_not_called()
