"""Apple identity token verification via Apple JWKS."""
from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

import jwt as pyjwt
from jwt import PyJWKClient

from .config import apple_client_ids, apple_configured
from .models import VerifiedIdentity

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URI = "https://appleid.apple.com/auth/keys"

_jwk_client: Optional[PyJWKClient] = None


class AppleTokenError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(APPLE_JWKS_URI, cache_keys=True)
    return _jwk_client


def reset_jwk_cache() -> None:
    global _jwk_client
    _jwk_client = None


def _normalize_nonce(expected_nonce: Optional[str], token_nonce: Optional[str]) -> bool:
    """Apple may store SHA256(nonce) in the token depending on client."""
    if expected_nonce is None:
        return True
    if not token_nonce:
        return False
    if token_nonce == expected_nonce:
        return True
    hashed = hashlib.sha256(expected_nonce.encode("utf-8")).hexdigest()
    return token_nonce == hashed


def verify_apple_id_token(
    id_token: str,
    *,
    expected_nonce: Optional[str] = None,
    audiences: Optional[list[str]] = None,
    _claims: Optional[dict[str, Any]] = None,
) -> VerifiedIdentity:
    if not apple_configured() and _claims is None and audiences is None:
        raise AppleTokenError("not_configured", "Integrazione Apple non configurata in questo ambiente")

    auds = audiences if audiences is not None else apple_client_ids()
    if not auds and _claims is None:
        raise AppleTokenError("not_configured", "Integrazione Apple non configurata in questo ambiente")

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
        except pyjwt.ExpiredSignatureError as e:
            raise AppleTokenError("expired", "Token Apple scaduto") from e
        except pyjwt.InvalidAudienceError as e:
            raise AppleTokenError("bad_audience", "Audience Apple non valida") from e
        except pyjwt.PyJWTError as e:
            raise AppleTokenError("invalid_token", "Token Apple non valido") from e

    if claims.get("iss") != APPLE_ISSUER:
        raise AppleTokenError("bad_issuer", "Issuer Apple non valido")

    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise AppleTokenError("bad_subject", "Subject Apple mancante")

    exp = claims.get("exp")
    if exp is not None and int(exp) < int(time.time()) - 30:
        raise AppleTokenError("expired", "Token Apple scaduto")

    token_nonce = claims.get("nonce") if isinstance(claims.get("nonce"), str) else None
    if expected_nonce is not None and not _normalize_nonce(expected_nonce, token_nonce):
        raise AppleTokenError("bad_nonce", "Nonce Apple non valido")

    if _claims is not None and auds:
        aud = claims.get("aud")
        aud_ok = aud in auds if isinstance(aud, str) else any(a in (aud or []) for a in auds)
        if not aud_ok:
            raise AppleTokenError("bad_audience", "Audience Apple non valida")

    email = claims.get("email") if isinstance(claims.get("email"), str) else None
    # Apple: email_verified may be string "true"
    raw_ev = claims.get("email_verified")
    if isinstance(raw_ev, str):
        email_verified = raw_ev.lower() == "true"
    else:
        email_verified = bool(raw_ev) if email else False

    is_private_email = False
    if email and email.endswith("@privaterelay.appleid.com"):
        is_private_email = True
        # Private relay is still a valid Apple email; never treat as equal to a non-relay account.
        email_verified = True if raw_ev is None else email_verified

    return VerifiedIdentity(
        provider="apple",
        subject=sub,
        email=email,
        email_verified=email_verified or is_private_email,
        display_name=None,  # Apple JWT usually has no name; use first-login payload carefully
        avatar_url=None,
        nonce=token_nonce,
    )
