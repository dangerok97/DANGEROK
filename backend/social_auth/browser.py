"""First-party Google browser sign-in for iOS: Authorization Code + PKCE.

Uses the already-configured Google OAuth backend client and its already-registered
Calendar callback URL, but asks only for openid/email/profile, never Calendar
access. This is a separate, non-connector login flow with one-use state and a
browser-bound completion proof. JWTs and Google credentials never enter URLs.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import HTTPException

from connectors.google_calendar.oauth import (
    GOOGLE_AUTH_URL, get_oauth_config, new_pkce_verifier, pkce_challenge,
    sanitize_redirect_after, exchange_code_for_tokens,
)
from social_auth.google import GoogleTokenError, verify_google_id_token
from social_auth.service import SocialAuthService

STATE_SECONDS = 600
TICKET_SECONDS = 120
FLOW_SCOPES = "openid email profile"
STATE_COLLECTION = "google_browser_login_states"
TICKET_COLLECTION = "google_browser_login_tickets"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _completion_url(frontend_return: str, **params: str) -> str:
    parts = urlsplit(frontend_return)
    return urlunsplit(parts._replace(query=urlencode(params), fragment=""))


def _frontend_completion_url(requested_origin: str) -> str:
    safe = sanitize_redirect_after(requested_origin)
    if not safe:
        raise HTTPException(status_code=400, detail="Frontend ORA non autorizzato per l'accesso Google")
    url = urlsplit(safe)
    return f"{url.scheme}://{url.netloc}/google-auth-complete"


async def _ensure_indexes(db) -> None:
    # Mongo's TTL indexes delete stale state/tickets even if the user closes
    # the browser before the Google callback. A reused state is impossible.
    await db[STATE_COLLECTION].create_index("expires_at", expireAfterSeconds=0)
    await db[TICKET_COLLECTION].create_index("expires_at", expireAfterSeconds=0)
    await db[STATE_COLLECTION].create_index("state_hash", unique=True)
    await db[TICKET_COLLECTION].create_index("ticket_hash", unique=True)


async def begin_google_browser_login(db, *, frontend_origin: str) -> dict:
    config = get_oauth_config()
    return_url = _frontend_completion_url(frontend_origin)
    await _ensure_indexes(db)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24)
    verifier = new_pkce_verifier()
    proof = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(seconds=STATE_SECONDS)
    await db[STATE_COLLECTION].insert_one({
        "state_hash": _hash(state),
        "nonce": nonce,
        "code_verifier": verifier,
        "completion_proof_hash": _hash(proof),
        "redirect_uri": config["redirect_uri"],
        "return_url": return_url,
        "created_at": _now(),
        "expires_at": expires_at,
    })
    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": FLOW_SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce_challenge(verifier),
        "code_challenge_method": "S256",
        "prompt": "select_account",
        "access_type": "online",
        "include_granted_scopes": "false",
    }
    return {
        "authorize_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}",
        "proof": proof,
        "expires_at": expires_at.isoformat(),
    }


async def maybe_handle_google_browser_callback(
    db, *, state: str, code: str,
) -> str | None:
    """Return a safe frontend URL for a browser-login state, else None.

    Calendar OAuth states are unaffected. Consume the login state BEFORE any
    external token exchange; repeated callbacks cannot create extra tickets.
    """
    state_doc = await db[STATE_COLLECTION].find_one_and_delete({
        "state_hash": _hash(state),
        "expires_at": {"$gt": _now()},
    })
    if state_doc is None:
        return None

    return_url = state_doc["return_url"]
    if not code:
        return _completion_url(return_url, error="google_login_cancelled")
    try:
        tokens = await exchange_code_for_tokens(
            code=code,
            code_verifier=state_doc["code_verifier"],
            redirect_uri=state_doc["redirect_uri"],
        )
        id_token = str(tokens.get("id_token") or "")
        if not id_token:
            return _completion_url(return_url, error="google_token_missing")
        verified = verify_google_id_token(
            id_token,
            expected_nonce=state_doc["nonce"],
            # Only a token obtained with our confidential backend OAuth
            # client, PKCE and the one-time nonce may use this audience.
            audiences=[get_oauth_config()["client_id"]],
        )
        user = await SocialAuthService(db).login_with_verified(verified)
        ticket = secrets.token_urlsafe(32)
        await db[TICKET_COLLECTION].insert_one({
            "ticket_hash": _hash(ticket),
            "completion_proof_hash": state_doc["completion_proof_hash"],
            "user_id": user["user_id"],
            "created_at": _now(),
            "expires_at": _now() + timedelta(seconds=TICKET_SECONDS),
        })
        return _completion_url(return_url, ticket=ticket)
    except HTTPException as exc:
        if exc.status_code == 409:
            return _completion_url(return_url, error="account_link_required")
        return _completion_url(return_url, error="google_login_unavailable")
    except (GoogleTokenError, ValueError, KeyError):
        return _completion_url(return_url, error="google_token_invalid")
    except Exception:
        # No tokens, proof or provider response are returned or logged.
        return _completion_url(return_url, error="google_login_unavailable")


async def redeem_google_browser_ticket(db, *, ticket: str, proof: str) -> dict:
    if not ticket or not proof:
        raise HTTPException(status_code=400, detail="Accesso Google scaduto")
    doc = await db[TICKET_COLLECTION].find_one_and_delete({
        "ticket_hash": _hash(ticket),
        "completion_proof_hash": _hash(proof),
        "expires_at": {"$gt": _now()},
    })
    if not doc:
        raise HTTPException(status_code=401, detail="Accesso Google scaduto o non valido")
    user = await db.users.find_one({"user_id": doc["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Account non disponibile")
    return user
