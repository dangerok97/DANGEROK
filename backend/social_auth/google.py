"""Google ID token verification via Google JWKS (no Emergent)."""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx
import jwt as pyjwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from .config import google_audiences, google_configured
from .models import VerifiedIdentity

GOOGLE_ISSUERS = frozenset({
    "https://accounts.google.com",
    "accounts.google.com",
})
GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"

_jwk_client: Optional[PyJWKClient] = None


class GoogleTokenError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(GOOGLE_JWKS_URI, cache_keys=True)
    return _jwk_client


def reset_jwk_cache() -> None:
    """Test helper."""
    global _jwk_client
    _jwk_client = None


def verify_google_id_token(
    id_token: str,
    *,
    expected_nonce: Optional[str] = None,
    audiences: Optional[list[str]] = None,
    # Injected for unit tests — claims already decoded & signature-trusted by mock
    _claims: Optional[dict[str, Any]] = None,
) -> VerifiedIdentity:
    if not google_configured() and _claims is None and audiences is None:
        raise GoogleTokenError("not_configured", "Integrazione Google non configurata in questo ambiente")

    auds = audiences if audiences is not None else google_audiences()
    if not auds and _claims is None:
        raise GoogleTokenError("not_configured", "Integrazione Google non configurata in questo ambiente")

    if _claims is not None:
        claims = _claims
    else:
        try:
            signing_key = _client().get_signing_key_from_jwt(id_token)
            claims = pyjwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=auds,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except PyJWKClientConnectionError as e:
            raise GoogleTokenError(
                "provider_unavailable",
                "Verifica Google temporaneamente non disponibile",
            ) from e
        except pyjwt.ExpiredSignatureError as e:
            raise GoogleTokenError("expired", "Token Google scaduto") from e
        except pyjwt.InvalidAudienceError as e:
            raise GoogleTokenError("bad_audience", "Audience Google non valida") from e
        except pyjwt.PyJWTError as e:
            raise GoogleTokenError("invalid_token", "Token Google non valido") from e

    iss = claims.get("iss")
    if iss not in GOOGLE_ISSUERS:
        raise GoogleTokenError("bad_issuer", "Issuer Google non valido")

    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise GoogleTokenError("bad_subject", "Subject Google mancante")

    exp = claims.get("exp")
    if exp is not None and int(exp) < int(time.time()) - 30:
        raise GoogleTokenError("expired", "Token Google scaduto")

    if expected_nonce is not None:
        token_nonce = claims.get("nonce")
        if not token_nonce or token_nonce != expected_nonce:
            raise GoogleTokenError("bad_nonce", "Nonce Google non valido")

    # When audiences injected via _claims path, still check aud
    if _claims is not None and auds:
        aud = claims.get("aud")
        aud_ok = aud in auds if isinstance(aud, str) else any(a in (aud or []) for a in auds)
        if not aud_ok:
            raise GoogleTokenError("bad_audience", "Audience Google non valida")

    email = claims.get("email")
    raw_email_verified = claims.get("email_verified")
    email_verified = raw_email_verified is True or (
        isinstance(raw_email_verified, str)
        and raw_email_verified.strip().lower() == "true"
    )
    name = claims.get("name")
    picture = claims.get("picture")

    return VerifiedIdentity(
        provider="google",
        subject=sub,
        email=email if isinstance(email, str) else None,
        email_verified=email_verified,
        display_name=name if isinstance(name, str) else None,
        avatar_url=picture if isinstance(picture, str) else None,
        nonce=claims.get("nonce") if isinstance(claims.get("nonce"), str) else None,
    )


async def fetch_google_certs_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as h:
            r = await h.get(GOOGLE_JWKS_URI)
            return r.status_code == 200
    except Exception:
        return False
