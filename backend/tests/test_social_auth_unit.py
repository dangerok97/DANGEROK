"""Unit tests for social auth — mocked provider claims (not real Google/Apple)."""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any

import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ora_social_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("EMERGENT_GOOGLE_AUTH", "0")
os.environ["GOOGLE_WEB_CLIENT_ID"] = "google-web-client-test.apps.googleusercontent.com"
os.environ["APPLE_SERVICE_ID"] = "com.ora.auth.service"
os.environ["APPLE_CLIENT_ID"] = "com.emergent.oradecisionengine.b7escs"

LIVE = os.environ.get("ORA_LIVE_URL", "http://127.0.0.1:8000").rstrip("/")
BASE = f"{LIVE}/api"
MONGO = os.environ["MONGO_URL"]
DBNAME = os.environ["DB_NAME"]


def _live_ok() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=2.0)
        return r.status_code == 200 and bool(r.json().get("database", {}).get("ok"))
    except Exception:
        return False


def _run(coro):
    return asyncio.run(coro)


# --- Pure unit (no server) -------------------------------------------
def test_google_bad_audience_unit():
    from social_auth.google import GoogleTokenError, verify_google_id_token

    with pytest.raises(GoogleTokenError) as ei:
        verify_google_id_token(
            "unused",
            audiences=["expected-aud"],
            _claims={
                "iss": "https://accounts.google.com",
                "sub": "g-sub-1",
                "aud": "wrong-aud",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
                "email": "a@example.com",
                "email_verified": True,
            },
        )
    assert ei.value.code == "bad_audience"


def test_google_expired_unit():
    from social_auth.google import GoogleTokenError, verify_google_id_token

    with pytest.raises(GoogleTokenError) as ei:
        verify_google_id_token(
            "unused",
            audiences=["aud"],
            _claims={
                "iss": "https://accounts.google.com",
                "sub": "g-sub-2",
                "aud": "aud",
                "exp": int(time.time()) - 120,
                "iat": int(time.time()) - 1000,
                "email": "b@example.com",
                "email_verified": True,
            },
        )
    assert ei.value.code == "expired"


def test_google_valid_unit():
    from social_auth.google import verify_google_id_token

    v = verify_google_id_token(
        "unused",
        audiences=["aud"],
        expected_nonce="n1",
        _claims={
            "iss": "https://accounts.google.com",
            "sub": "g-sub-ok",
            "aud": "aud",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "email": "ok@example.com",
            "email_verified": True,
            "name": "Ok User",
            "nonce": "n1",
        },
    )
    assert v.subject == "g-sub-ok"
    assert v.email_verified is True


def test_apple_bad_nonce_unit():
    from social_auth.apple import AppleTokenError, verify_apple_id_token

    with pytest.raises(AppleTokenError) as ei:
        verify_apple_id_token(
            "unused",
            expected_nonce="expected",
            audiences=["com.ora.auth.service"],
            _claims={
                "iss": "https://appleid.apple.com",
                "sub": "apple-sub-1",
                "aud": "com.ora.auth.service",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
                "email": "x@privaterelay.appleid.com",
                "email_verified": "true",
                "nonce": "wrong",
            },
        )
    assert ei.value.code == "bad_nonce"


def test_apple_valid_and_private_relay_unit():
    from social_auth.apple import verify_apple_id_token

    v = verify_apple_id_token(
        "unused",
        expected_nonce="n-apple",
        audiences=["com.ora.auth.service"],
        _claims={
            "iss": "https://appleid.apple.com",
            "sub": "apple-sub-ok",
            "aud": "com.ora.auth.service",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "email": "hide@privaterelay.appleid.com",
            "email_verified": "true",
            "nonce": "n-apple",
        },
    )
    assert v.provider == "apple"
    assert v.email.endswith("@privaterelay.appleid.com")


def test_google_not_configured_without_env(monkeypatch):
    from social_auth import google as gmod
    from social_auth.google import GoogleTokenError, verify_google_id_token

    monkeypatch.setattr(gmod, "google_configured", lambda: False)
    monkeypatch.setattr(gmod, "google_audiences", lambda: [])

    with pytest.raises(GoogleTokenError) as ei:
        verify_google_id_token("x.y.z")
    assert ei.value.code == "not_configured"


def _claims_google(sub: str, email: str, **extra: Any) -> dict:
    c = {
        "iss": "https://accounts.google.com",
        "sub": sub,
        "aud": os.environ["GOOGLE_WEB_CLIENT_ID"],
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "email": email,
        "email_verified": True,
        "name": "Social Tester",
    }
    c.update(extra)
    return c


def test_service_new_user_and_repeat_no_duplicate():
    async def body():
        from social_auth.service import SocialAuthService
        from social_auth.google import verify_google_id_token

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        try:
            svc = SocialAuthService(db)
            sub = f"gsub_{uuid.uuid4().hex[:10]}"
            email = f"social.{uuid.uuid4().hex[:8]}@example.com"
            verified = verify_google_id_token(
                "x",
                audiences=[os.environ["GOOGLE_WEB_CLIENT_ID"]],
                _claims=_claims_google(sub, email),
            )
            u1 = await svc.login_with_verified(verified)
            u2 = await svc.login_with_verified(verified)
            assert u1["user_id"] == u2["user_id"]
            n = await db.user_identities.count_documents({"provider": "google", "provider_subject": sub})
            assert n == 1
            assert await db.users.count_documents({"email": email}) == 1
        finally:
            client.close()

    _run(body())


def test_service_email_conflict_with_password():
    async def body():
        import bcrypt
        from fastapi import HTTPException
        from social_auth.service import SocialAuthService
        from social_auth.google import verify_google_id_token

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        try:
            email = f"pwd.{uuid.uuid4().hex[:8]}@example.com"
            uid = f"user_{uuid.uuid4().hex[:12]}"
            pw = bcrypt.hashpw(b"Secret123!", bcrypt.gensalt()).decode()
            await db.users.insert_one({
                "user_id": uid,
                "email": email,
                "name": "Pwd",
                "provider": "email",
                "providers": ["email"],
                "password_hash": pw,
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            svc = SocialAuthService(db)
            verified = verify_google_id_token(
                "x",
                audiences=[os.environ["GOOGLE_WEB_CLIENT_ID"]],
                _claims=_claims_google(f"g_{uuid.uuid4().hex[:8]}", email),
            )
            with pytest.raises(HTTPException) as ei:
                await svc.login_with_verified(verified)
            assert ei.value.status_code == 409
        finally:
            client.close()

    _run(body())


def test_service_link_and_unlink_rules():
    async def body():
        import bcrypt
        from fastapi import HTTPException
        from social_auth.service import SocialAuthService
        from social_auth.google import verify_google_id_token
        from social_auth.store import IdentityStore

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        try:
            email = f"link.{uuid.uuid4().hex[:8]}@example.com"
            uid = f"user_{uuid.uuid4().hex[:12]}"
            pw = bcrypt.hashpw(b"Secret123!", bcrypt.gensalt()).decode()
            user = {
                "user_id": uid,
                "email": email,
                "name": "Link",
                "provider": "email",
                "providers": ["email"],
                "password_hash": pw,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
            await db.users.insert_one(dict(user))
            store = IdentityStore(db)
            await store.create(
                provider="password",
                provider_subject=uid,
                user_id=uid,
                email=email,
                email_verified=True,
                display_name="Link",
                avatar_url=None,
            )
            svc = SocialAuthService(db)
            g_sub = f"g_link_{uuid.uuid4().hex[:8]}"
            verified = verify_google_id_token(
                "x",
                audiences=[os.environ["GOOGLE_WEB_CLIENT_ID"]],
                _claims=_claims_google(g_sub, f"g.{uuid.uuid4().hex[:6]}@gmail.com"),
            )
            await svc.link_with_verified(user, verified)
            await svc.unlink(user, "google")

            only_uid = f"user_{uuid.uuid4().hex[:12]}"
            only_email = f"only.{uuid.uuid4().hex[:8]}@example.com"
            only = {
                "user_id": only_uid,
                "email": only_email,
                "name": "OnlyG",
                "provider": "google",
                "providers": ["google"],
                "password_hash": None,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
            await db.users.insert_one(dict(only))
            g2 = f"g_only_{uuid.uuid4().hex[:8]}"
            v2 = verify_google_id_token(
                "x",
                audiences=[os.environ["GOOGLE_WEB_CLIENT_ID"]],
                _claims=_claims_google(g2, only_email),
            )
            u = await svc.login_with_verified(v2)
            with pytest.raises(HTTPException) as ei:
                await svc.unlink(u, "google")
            assert ei.value.status_code == 400
        finally:
            client.close()

    _run(body())


def test_apple_second_login_preserves_name():
    async def body():
        from social_auth.service import SocialAuthService
        from social_auth.apple import verify_apple_id_token

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        try:
            svc = SocialAuthService(db)
            sub = f"asub_{uuid.uuid4().hex[:10]}"
            email = f"relay.{uuid.uuid4().hex[:8]}@privaterelay.appleid.com"
            claims = {
                "iss": "https://appleid.apple.com",
                "sub": sub,
                "aud": os.environ["APPLE_SERVICE_ID"],
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
                "email": email,
                "email_verified": "true",
            }
            v1 = verify_apple_id_token(
                "x",
                audiences=[os.environ["APPLE_SERVICE_ID"]],
                _claims=claims,
            )
            u1 = await svc.login_with_verified(v1, first_name="Ada", last_name="Lovelace")
            assert u1.get("name") == "Ada Lovelace"
            claims2 = {k: claims[k] for k in ("iss", "sub", "aud", "exp", "iat")}
            v2 = verify_apple_id_token(
                "x",
                audiences=[os.environ["APPLE_SERVICE_ID"]],
                _claims=claims2,
            )
            u2 = await svc.login_with_verified(v2)
            assert u2["user_id"] == u1["user_id"]
            refreshed = await db.users.find_one({"user_id": u1["user_id"]}, {"_id": 0})
            assert refreshed.get("name") == "Ada Lovelace"
            ident = await db.user_identities.find_one(
                {"provider": "apple", "provider_subject": sub}, {"_id": 0}
            )
            assert ident.get("email") == email
            assert ident.get("display_name") == "Ada Lovelace"
        finally:
            client.close()

    _run(body())


def test_provider_separation():
    async def body():
        from social_auth.service import SocialAuthService
        from social_auth.google import verify_google_id_token
        from social_auth.apple import verify_apple_id_token

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        try:
            svc = SocialAuthService(db)
            g = verify_google_id_token(
                "x",
                audiences=[os.environ["GOOGLE_WEB_CLIENT_ID"]],
                _claims=_claims_google(
                    f"sep_g_{uuid.uuid4().hex[:8]}",
                    f"sep.g.{uuid.uuid4().hex[:6]}@ex.com",
                ),
            )
            a = verify_apple_id_token(
                "x",
                audiences=[os.environ["APPLE_SERVICE_ID"]],
                _claims={
                    "iss": "https://appleid.apple.com",
                    "sub": f"sep_a_{uuid.uuid4().hex[:8]}",
                    "aud": os.environ["APPLE_SERVICE_ID"],
                    "exp": int(time.time()) + 3600,
                    "iat": int(time.time()),
                    "email": f"sep.a.{uuid.uuid4().hex[:6]}@privaterelay.appleid.com",
                    "email_verified": "true",
                },
            )
            ug = await svc.login_with_verified(g)
            ua = await svc.login_with_verified(a)
            assert ug["user_id"] != ua["user_id"]
        finally:
            client.close()

    _run(body())


@pytest.mark.skipif(not _live_ok(), reason="local uvicorn+Mongo not running")
def test_http_google_without_token_and_providers():
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/auth/google", json={})
        assert r.status_code == 422
        st = c.get(f"{BASE}/auth/providers")
        assert st.status_code == 200
        body = st.json()
        assert "google" in body and "apple" in body and "password" in body


@pytest.mark.skipif(not _live_ok(), reason="local uvicorn+Mongo not running")
def test_http_email_login_still_works_and_identities():
    email = f"emailkeep.{uuid.uuid4().hex[:8]}@ora.app"
    pw = "KeepEmail123!"
    with httpx.Client(timeout=20.0) as c:
        reg = c.post(f"{BASE}/auth/register", json={"email": email, "password": pw, "name": "Keep"})
        assert reg.status_code == 200, reg.text
        token = reg.json()["token"]
        me = c.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        ids = c.get(f"{BASE}/auth/identities", headers={"Authorization": f"Bearer {token}"})
        assert ids.status_code == 200
        assert ids.json()["methods"]["password"]["linked"] is True
        out = c.post(f"{BASE}/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert out.status_code == 200


@pytest.mark.skipif(not _live_ok(), reason="local uvicorn+Mongo not running")
def test_http_google_not_configured_503():
    with httpx.Client(timeout=15.0) as c:
        # Without GOOGLE_* on the live server, expect 503 not_configured
        r = c.post(
            f"{BASE}/auth/google",
            json={"id_token": "eyJhbGciOiJSUzI1NiJ9.e30.x"},
        )
        assert r.status_code in (401, 503)
