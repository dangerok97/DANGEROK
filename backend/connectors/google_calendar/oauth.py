"""OAuth 2.0 (Authorization Code + PKCE) helpers for Google Calendar.

State + PKCE verifier are stored in Mongo (`google_oauth_sessions`) for
the short life of the flow; they never touch the client. Everything is
read from env variables — no in-code fallback.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

from .scopes import GOOGLE_CALENDAR_SCOPES

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

STATE_TTL_MINUTES = 10


class OAuthConfigError(Exception):
    """Real-provider credentials are missing/misconfigured."""


class OAuthStateInvalid(Exception):
    """State token unknown, expired, or already used."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def new_pkce_verifier() -> str:
    return _b64url(secrets.token_bytes(48))


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)


def get_oauth_config() -> Dict[str, str]:
    cid = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    redirect = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if not cid or not secret or not redirect:
        raise OAuthConfigError(
            "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / GOOGLE_OAUTH_REDIRECT_URI missing"
        )
    return {"client_id": cid, "client_secret": secret, "redirect_uri": redirect}


class OAuthStateStore:
    """Persistent, one-shot store for OAuth state + PKCE + user_id."""

    def __init__(self, db):
        self.db = db

    @property
    def col(self):
        return self.db.google_oauth_sessions

    async def create(
        self,
        *,
        user_id: str,
        redirect_after: Optional[str] = None,
    ) -> Dict[str, str]:
        state = secrets.token_urlsafe(32)
        verifier = new_pkce_verifier()
        challenge = pkce_challenge(verifier)
        expires_at = (_now() + timedelta(minutes=STATE_TTL_MINUTES)).isoformat()
        doc = {
            "id": f"oas_{uuid.uuid4().hex[:16]}",
            "user_id": user_id,
            "state": state,
            "code_verifier": verifier,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "expires_at": expires_at,
            "consumed": False,
            "created_at": _now().isoformat(),
            "redirect_after": redirect_after,
        }
        await self.col.insert_one(doc)
        return {
            "state": state,
            "code_verifier": verifier,
            "code_challenge": challenge,
            "expires_at": expires_at,
        }

    async def consume(self, *, state: str) -> Dict[str, Any]:
        doc = await self.col.find_one({"state": state, "consumed": False}, {"_id": 0})
        if not doc:
            raise OAuthStateInvalid("state unknown or already consumed")
        if doc["expires_at"] < _now().isoformat():
            raise OAuthStateInvalid("state expired")
        await self.col.update_one(
            {"state": state, "consumed": False},
            {"$set": {"consumed": True, "consumed_at": _now().isoformat()}},
        )
        return doc


def build_authorize_url(*, state: str, code_challenge: str) -> str:
    cfg = get_oauth_config()
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_tokens(
    *,
    code: str,
    code_verifier: str,
) -> Dict[str, Any]:
    cfg = get_oauth_config()
    data = {
        "code": code,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": cfg["redirect_uri"],
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=20) as h:
        r = await h.post(GOOGLE_TOKEN_URL, data=data, headers={"Accept": "application/json"})
        if r.status_code != 200:
            raise OAuthConfigError(f"token exchange failed: {r.status_code} {r.text[:200]}")
        return r.json()


async def refresh_access_token(*, refresh_token: str) -> Dict[str, Any]:
    cfg = get_oauth_config()
    data = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=20) as h:
        r = await h.post(GOOGLE_TOKEN_URL, data=data, headers={"Accept": "application/json"})
        if r.status_code != 200:
            raise OAuthConfigError(f"refresh failed: {r.status_code} {r.text[:200]}")
        return r.json()


async def fetch_userinfo(access_token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code != 200:
            raise OAuthConfigError(f"userinfo failed: {r.status_code}")
        return r.json()


async def revoke_token(token: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.post(GOOGLE_REVOKE_URL, data={"token": token}, headers={"Content-Type": "application/x-www-form-urlencoded"})
        return r.status_code in (200, 400)  # Google returns 400 if already revoked
