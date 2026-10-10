"""Google browser redirect auth regressions: synthetic credentials, never Google calls."""
from urllib.parse import parse_qs, urlsplit
import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from social_auth import browser


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-browser-client.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "synthetic-secret-not-usable")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "https://ora-backend.example/api/connectors/google-calendar/oauth/callback",
    )
    monkeypatch.setenv("FRONTEND_URLS", "https://ora-web.example")
    monkeypatch.setenv("ENVIRONMENT", "production")
    return AsyncMongoMockClient().google_browser_v156


@pytest.mark.asyncio
async def test_browser_login_only_asks_identity_and_never_exposes_proof_or_jwt(db):
    started = await browser.begin_google_browser_login(
        db, frontend_origin="https://ora-web.example"
    )
    url = urlsplit(started["authorize_url"])
    query = parse_qs(url.query)
    assert url.scheme == "https"
    assert url.netloc == "accounts.google.com"
    assert url.path == "/o/oauth2/v2/auth"
    assert query["scope"] == ["openid email profile"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["include_granted_scopes"] == ["false"]
    assert query["redirect_uri"] == [
        "https://ora-backend.example/api/connectors/google-calendar/oauth/callback",
    ]
    assert "calendar" not in query["scope"][0].lower()
    assert started["proof"] not in started["authorize_url"]
    assert "client_secret" not in started["authorize_url"]

    state = query["state"][0]
    doc = await db[browser.STATE_COLLECTION].find_one({"state_hash": browser._hash(state)})
    assert doc is not None
    assert doc["completion_proof_hash"] == browser._hash(started["proof"])
    assert "proof" not in doc
    assert "state" not in doc
    assert doc["nonce"] == query["nonce"][0]
    assert doc["code_verifier"] != query["code_challenge"][0]


@pytest.mark.asyncio
async def test_untrusted_frontend_redirect_rejected(db):
    for value in ("https://evil.example", "https://ora-web.example.evil.test", "javascript:alert(1)"):
        with pytest.raises(HTTPException):
            await browser.begin_google_browser_login(db, frontend_origin=value)
    assert await db[browser.STATE_COLLECTION].count_documents({}) == 0


@pytest.mark.asyncio
async def test_one_time_browser_ticket_binds_same_tab_and_cannot_be_replayed(db, monkeypatch):
    started = await browser.begin_google_browser_login(db, frontend_origin="https://ora-web.example")
    state = parse_qs(urlsplit(started["authorize_url"]).query)["state"][0]
    expected_nonce = parse_qs(urlsplit(started["authorize_url"]).query)["nonce"][0]
    seen = []

    async def fake_exchange(*, code, code_verifier, redirect_uri):
        seen.append((code, bool(code_verifier), redirect_uri))
        return {"id_token": "synthetic-jwt"}

    def fake_verification(id_token, *, audiences, expected_nonce):
        assert id_token == "synthetic-jwt"
        assert audiences == ["test-browser-client.apps.googleusercontent.com"]
        assert expected_nonce == parse_qs(urlsplit(started["authorize_url"]).query)["nonce"][0]
        return {"subject": "synthetic-person"}

    async def fake_login(self, verified):
        await db.users.insert_one({
            "user_id": "owner-synthetic", "email": "example@example.invalid",
            "provider": "google",
        })
        return {"user_id": "owner-synthetic"}

    monkeypatch.setattr(browser, "exchange_code_for_tokens", fake_exchange)
    monkeypatch.setattr(browser, "verify_google_id_token", fake_verification)
    monkeypatch.setattr(browser.SocialAuthService, "login_with_verified", fake_login)

    destination = await browser.maybe_handle_google_browser_callback(
        db, state=state, code="synthetic-authorization-code",
    )
    redirect = urlsplit(destination)
    assert redirect.scheme == "https"
    assert redirect.netloc == "ora-web.example"
    assert redirect.path == "/google-auth-complete"
    assert not redirect.query, "one-time ticket must never enter HTTP query"
    ticket = parse_qs(redirect.fragment)["ticket"][0]
    assert "synthetic-jwt" not in destination
    assert "owner-synthetic" not in destination
    assert started["proof"] not in destination
    assert len(seen) == 1

    with pytest.raises(HTTPException):
        await browser.redeem_google_browser_ticket(db, ticket=ticket, proof="incorrect-proof")
    user = await browser.redeem_google_browser_ticket(
        db, ticket=ticket, proof=started["proof"],
    )
    assert user["user_id"] == "owner-synthetic"
    with pytest.raises(HTTPException):
        await browser.redeem_google_browser_ticket(
            db, ticket=ticket, proof=started["proof"],
        )
    assert await browser.maybe_handle_google_browser_callback(
        db, state=state, code="synthetic-authorization-code",
    ) is None, "replayed browser callback must never touch an OAuth provider"
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_calendar_state_remains_separate_from_browser_login(db):
    assert await browser.maybe_handle_google_browser_callback(
        db, state="calendar-oauth-state", code="fake-code",
    ) is None


@pytest.mark.asyncio
async def test_cancelled_browser_login_never_mints_a_session_ticket(db):
    started = await browser.begin_google_browser_login(db, frontend_origin="https://ora-web.example")
    state = parse_qs(urlsplit(started["authorize_url"]).query)["state"][0]
    dest = await browser.maybe_handle_google_browser_callback(db, state=state, code="")
    assert parse_qs(urlsplit(dest).query)["error"] == ["google_login_cancelled"]
    assert await db[browser.TICKET_COLLECTION].count_documents({}) == 0
