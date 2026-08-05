"""OAuth 2.0 (Authorization Code + PKCE) helpers for Google Calendar.

State + PKCE verifier are stored in Mongo (`google_oauth_sessions`) for
the short life of the flow; they never touch the client. Everything is
read from env variables — no in-code fallback.

Local/dev: `localhost` and `127.0.0.1` are treated as interchangeable for
redirect URIs and post-OAuth frontend return URLs (Google Console must
still list both explicitly).
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from .scopes import GOOGLE_CALENDAR_SCOPES

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

STATE_TTL_MINUTES = 30

# Default Expo web origins accepted as post-OAuth return targets in local/dev.
_DEFAULT_FRONTEND_ORIGINS = (
    "http://localhost:8081",
    "http://127.0.0.1:8081",
)


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


def _is_local_dev() -> bool:
    env = (os.environ.get("ENVIRONMENT") or "development").strip().lower()
    return env in ("", "development", "dev", "local", "test")


def _loopback_twin(uri: str) -> Optional[str]:
    """Return the localhost ↔ 127.0.0.1 twin of a URI, if applicable."""
    if "://localhost" in uri:
        return uri.replace("://localhost", "://127.0.0.1", 1)
    if "://127.0.0.1" in uri:
        return uri.replace("://127.0.0.1", "://localhost", 1)
    return None


def _dedupe(uris: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for u in uris:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _expand_loopback(uris: List[str]) -> List[str]:
    if not _is_local_dev():
        return _dedupe(uris)
    expanded: List[str] = []
    for u in uris:
        expanded.append(u)
        twin = _loopback_twin(u)
        if twin:
            expanded.append(twin)
    return _dedupe(expanded)


def allowed_oauth_redirect_uris() -> List[str]:
    """Backend callback URIs accepted for Google Calendar OAuth."""
    primary = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    extras_raw = os.environ.get("GOOGLE_OAUTH_REDIRECT_URIS", "").strip()
    uris: List[str] = []
    if primary:
        uris.append(primary)
    if extras_raw:
        uris.extend(u.strip() for u in extras_raw.split(",") if u.strip())
    return _expand_loopback(uris)


def get_oauth_config() -> Dict[str, str]:
    cid = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    allowed = allowed_oauth_redirect_uris()
    if not cid or not secret or not allowed:
        raise OAuthConfigError(
            "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / GOOGLE_OAUTH_REDIRECT_URI missing"
        )
    return {
        "client_id": cid,
        "client_secret": secret,
        "redirect_uri": allowed[0],
        "redirect_uris": ",".join(allowed),
    }


def resolve_redirect_uri(
    *,
    preferred: Optional[str] = None,
    request_base: Optional[str] = None,
) -> str:
    """Pick a registered callback URI for this OAuth start.

    Preference order: explicit preferred → same host as request_base → primary.
    """
    allowed = allowed_oauth_redirect_uris()
    if not allowed:
        raise OAuthConfigError(
            "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / GOOGLE_OAUTH_REDIRECT_URI missing"
        )
    if preferred:
        pref = preferred.strip().rstrip("/")
        for u in allowed:
            if u.rstrip("/") == pref:
                return u
    if request_base:
        try:
            host = (urlparse(request_base).hostname or "").lower()
        except Exception:
            host = ""
        if host:
            for u in allowed:
                if (urlparse(u).hostname or "").lower() == host:
                    return u
    return allowed[0]


def allowed_frontend_origins() -> List[str]:
    """Origins allowed for post-OAuth browser return (`redirect_after`)."""
    raw = os.environ.get("FRONTEND_URLS", "").strip()
    origins: List[str] = []
    if raw:
        origins.extend(o.strip().rstrip("/") for o in raw.split(",") if o.strip())
    single = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")
    if single:
        origins.append(single)
    if _is_local_dev() or not origins:
        origins.extend(_DEFAULT_FRONTEND_ORIGINS)
    return _expand_loopback(origins)


def sanitize_redirect_after(url: Optional[str]) -> Optional[str]:
    """Return a safe same-app return URL, or None if not allowlisted."""
    if not url or not isinstance(url, str):
        return None
    candidate = url.strip()
    if not candidate or candidate.startswith("//"):
        return None
    try:
        parsed = urlparse(candidate)
    except Exception:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.username or parsed.password:
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    allowed = {o.rstrip("/") for o in allowed_frontend_origins()}
    if origin not in allowed:
        return None
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    # Drop query/fragment from untrusted input; append oauth flag ourselves later.
    return f"{origin}{path}"


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
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, str]:
        state = secrets.token_urlsafe(32)
        verifier = new_pkce_verifier()
        challenge = pkce_challenge(verifier)
        expires_at = (_now() + timedelta(minutes=STATE_TTL_MINUTES)).isoformat()
        # redirect_uri may be None in fake/test mode (no Google credentials).
        safe_after = sanitize_redirect_after(redirect_after)
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
            "redirect_after": safe_after,
            "redirect_uri": redirect_uri,
        }
        await self.col.insert_one(doc)
        return {
            "state": state,
            "code_verifier": verifier,
            "code_challenge": challenge,
            "expires_at": expires_at,
            "redirect_uri": redirect_uri or "",
            "redirect_after": safe_after or "",
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


def build_authorize_url(
    *,
    state: str,
    code_challenge: str,
    redirect_uri: Optional[str] = None,
) -> str:
    cfg = get_oauth_config()
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri or cfg["redirect_uri"],
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
    redirect_uri: Optional[str] = None,
) -> Dict[str, Any]:
    cfg = get_oauth_config()
    data = {
        "code": code,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": redirect_uri or cfg["redirect_uri"],
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
        r = await h.post(
            GOOGLE_REVOKE_URL,
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return r.status_code in (200, 400)  # Google returns 400 if already revoked
