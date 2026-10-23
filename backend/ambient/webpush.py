"""
Web Push: the channel that reaches a phone without an App Store build.

ORA is used today from Safari on iPhone. Since iOS 16.4 a web app added to
the Home Screen can receive real notifications through the standard Web Push
protocol, with the app closed. This module is that channel, built only on
`cryptography`, `PyJWT` and `httpx`, which the backend already ships:

* RFC 8291 message encryption (aes128gcm) — the push service in the middle
  (Apple, Google, Mozilla) carries the notification but cannot read it.
* RFC 8292 VAPID — the push service knows the message really comes from ORA.

The subscription is stored exactly like an Expo token: as the endpoint's
`token`, written once, never logged, never returned. It is a capability —
whoever holds it can put text on that lock screen.

Like Expo, a provider's 201 means "accepted by the push service", not
"seen by the person". The return value says so.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "webpush:"
# Only the public push services real browsers use. A subscription pointing
# anywhere else would turn ORA into a client for arbitrary URLs.
PUSH_HOST_SUFFIXES = (
    "web.push.apple.com",
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
)
# What a push service says when the subscription will never work again.
PERMANENT_STATUSES = {404, 410}
DEFAULT_TTL_SECONDS = 4 * 3600
RECORD_SIZE = 4096


def _b64url_decode(value: str) -> bytes:
    value = (value or "").strip()
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


# --------------------------------------------------------------------------
# Subscriptions


def _allowed_endpoint(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return (
        parts.scheme == "https"
        and not parts.username and not parts.password
        and parts.port in (None, 443)
        and any(host == s or host.endswith("." + s) for s in PUSH_HOST_SUFFIXES)
    )


def parse_subscription(raw: Any) -> Optional[Dict[str, str]]:
    """A browser PushSubscription (object or JSON) → {endpoint, p256dh, auth}."""
    if isinstance(raw, str):
        text = raw[len(TOKEN_PREFIX):] if raw.startswith(TOKEN_PREFIX) else raw
        try:
            raw = json.loads(text)
        except (ValueError, TypeError):
            return None
    if not isinstance(raw, dict):
        return None
    endpoint = raw.get("endpoint") if "endpoint" in raw else raw.get("e")
    keys = raw.get("keys") if isinstance(raw.get("keys"), dict) else {}
    p256dh = keys.get("p256dh") if keys else raw.get("p")
    auth = keys.get("auth") if keys else raw.get("a")
    if not all(isinstance(v, str) and v for v in (endpoint, p256dh, auth)):
        return None
    if len(endpoint) > 900 or not _allowed_endpoint(endpoint):
        return None
    try:
        ua_public = _b64url_decode(p256dh)
        secret = _b64url_decode(auth)
    except (ValueError, TypeError):
        return None
    if len(ua_public) != 65 or ua_public[0] != 4 or len(secret) != 16:
        return None
    return {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}


def subscription_token(raw: Any) -> Optional[str]:
    """The canonical stored form. Same subscription → same token (idempotent)."""
    sub = parse_subscription(raw)
    if not sub:
        return None
    compact = json.dumps({"e": sub["endpoint"], "p": sub["p256dh"], "a": sub["auth"]},
                         separators=(",", ":"), sort_keys=True)
    return TOKEN_PREFIX + compact


def is_web_push_token(value: str) -> bool:
    return isinstance(value, str) and value.startswith(TOKEN_PREFIX) and parse_subscription(value) is not None


# --------------------------------------------------------------------------
# VAPID


def _vapid_private_key():
    from cryptography.hazmat.primitives.asymmetric import ec

    raw = (os.environ.get("WEBPUSH_VAPID_PRIVATE_KEY") or "").strip()
    if not raw:
        return None
    try:
        scalar = int.from_bytes(_b64url_decode(raw), "big")
        return ec.derive_private_key(scalar, ec.SECP256R1())
    except Exception:
        logger.warning("web push VAPID key unreadable")
        return None


def _public_bytes(key) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
    )


def vapid_public_key() -> Optional[str]:
    """The application server key the browser subscribes with. Not a secret."""
    key = _vapid_private_key()
    return _b64url(_public_bytes(key)) if key is not None else None


def configured() -> bool:
    return _vapid_private_key() is not None


def _subject() -> str:
    subject = (os.environ.get("WEBPUSH_SUBJECT") or "").strip()
    if subject.startswith(("mailto:", "https://")):
        return subject
    return "https://ora-web-production.up.railway.app"


def vapid_authorization(endpoint: str, *, now: Optional[float] = None) -> Optional[str]:
    import jwt as pyjwt

    key = _vapid_private_key()
    if key is None:
        return None
    parts = urlsplit(endpoint)
    issued = int(now if now is not None else time.time())
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": issued + 3600, "sub": _subject()}
    token = pyjwt.encode(claims, key, algorithm="ES256")
    return f"vapid t={token}, k={_b64url(_public_bytes(key))}"


# --------------------------------------------------------------------------
# RFC 8291 encryption


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    from cryptography.hazmat.primitives import hashes, hmac

    h = hmac.HMAC(salt, hashes.SHA256())
    h.update(ikm)
    prk = h.finalize()
    h = hmac.HMAC(prk, hashes.SHA256())
    h.update(info + b"\x01")
    return h.finalize()[:length]


def encrypt(payload: bytes, p256dh: str, auth: str, *,
            salt: Optional[bytes] = None, server_key=None) -> bytes:
    """aes128gcm body for one subscription (single record)."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ua_public = _b64url_decode(p256dh)
    auth_secret = _b64url_decode(auth)
    if len(payload) > RECORD_SIZE - 17 - 86:
        raise ValueError("payload_too_large")
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _public_bytes(server_key)
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = server_key.exchange(ec.ECDH(), peer)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!I", RECORD_SIZE) + bytes([len(as_public)]) + as_public
    return header + ciphertext


# --------------------------------------------------------------------------
# Provider


class WebPushNotificationProvider:
    name = "webpush"

    def __init__(self, db, *, timeout: float = 10.0):
        from ambient.repository import AmbientRepository

        self.db = db
        self.timeout = timeout
        self.repo = AmbientRepository(db)

    async def send(self, *, owner_id: str, plan_id: str, title: str, body: str,
                   deep_link: str, public_title: str = "", public_body: str = "") -> Dict[str, Any]:
        endpoints = [
            row for row in await self.repo.active_endpoints(owner_id)
            if row.provider == "webpush" and row.permission_state == "granted"
        ]
        if not endpoints:
            return {"ok": False, "provider": self.name, "reason": "no_endpoint"}
        if not configured():
            return {"ok": False, "provider": self.name, "reason": "not_configured"}

        # Lock-screen words only: the full text stays inside ORA.
        message = json.dumps({
            "title": (public_title or title)[:120],
            "body": (public_body or body)[:300],
            "plan_id": plan_id,
            "deep_link": deep_link,
        }, ensure_ascii=False).encode("utf-8")

        accepted, failed, throttled_only = 0, [], True
        for endpoint in endpoints:
            sub = parse_subscription(endpoint.token)
            if not sub:
                await self.repo.disable_endpoint(endpoint_id=endpoint.id, reason="invalid_subscription")
                failed.append({"endpoint": endpoint.id, "error": "invalid_subscription"})
                continue
            status, sent = await self._post(sub, message)
            if status is not None and 200 <= status < 300:
                accepted += 1
                continue
            failed.append({"endpoint": endpoint.id, "error": f"http_{status}" if status else "transport"})
            if status in PERMANENT_STATUSES:
                await self.repo.disable_endpoint(endpoint_id=endpoint.id, reason=f"webpush_{status}")
                logger.info("web push endpoint disabled status=%s", status)
            # Only a request that never left, or an explicit 429, is a proof
            # that nothing was accepted.
            if not (status == 429 or (status is None and not sent)):
                throttled_only = False

        transient = accepted == 0 and any(
            f["error"] == "transport" or f["error"] in ("http_429",) or f["error"].startswith("http_5")
            for f in failed
        )
        return {
            "ok": accepted > 0,
            "provider": self.name,
            "provider_accepted": accepted,
            "failures": failed,
            "external_id": f"webpush:{plan_id}",
            "transient": transient,
            "safe_to_retry": accepted == 0 and bool(failed) and throttled_only,
            "reason": None if accepted else "webpush_not_accepted",
        }

    async def _post(self, sub: Dict[str, str], message: bytes) -> Tuple[Optional[int], bool]:
        """(HTTP status or None, whether the request may have reached the service)."""
        import httpx

        try:
            payload = encrypt(message, sub["p256dh"], sub["auth"])
            authorization = vapid_authorization(sub["endpoint"])
        except Exception as exc:
            logger.info("web push encode failed kind=%s", type(exc).__name__)
            return None, False
        headers = {
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(DEFAULT_TTL_SECONDS),
            "Urgency": "high",
            "Authorization": authorization or "",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                response = await http.post(sub["endpoint"], content=payload, headers=headers)
            return response.status_code, True
        except httpx.ConnectError:
            return None, False
        except Exception as exc:
            logger.info("web push unavailable kind=%s", type(exc).__name__)
            return None, True

    async def cancel(self, *, owner_id: str, plan_id: str) -> Dict[str, Any]:
        return {"ok": True, "provider": self.name, "retracted": False}


class CompositeNotificationProvider:
    """
    One decision, every reachable channel.

    Delivery decides once whether to interrupt; this hands the same words to
    each channel the person enabled. Accepted by any channel is delivered.
    Nothing is re-sent on a channel that already accepted.
    """

    def __init__(self, providers: List[Any]):
        self.providers = providers
        self.name = "+".join(p.name for p in providers)

    def includes(self, cls) -> bool:
        return any(isinstance(p, cls) for p in self.providers)

    async def send(self, **kwargs) -> Dict[str, Any]:
        results = []
        for provider in self.providers:
            try:
                results.append(await provider.send(**kwargs))
            except Exception as exc:
                logger.info("push channel failed provider=%s kind=%s", provider.name, type(exc).__name__)
                results.append({"ok": False, "provider": provider.name, "transient": True,
                                "safe_to_retry": False, "reason": "channel_error"})
        attempted = [r for r in results if r.get("reason") not in ("no_endpoint", "not_configured")]
        accepted = [r for r in results if r.get("ok")]
        merged: Dict[str, Any] = {
            "ok": bool(accepted),
            "provider": self.name,
            "channels": [{"provider": r.get("provider"), "ok": bool(r.get("ok")),
                          "reason": r.get("reason")} for r in results],
            "provider_accepted": sum(int(r.get("provider_accepted") or 0) for r in results),
        }
        expo = next((r for r in results if r.get("provider") == "expo"), None)
        if expo:
            for key in ("receipt_audit_tracked", "receipt_audit_untracked"):
                if key in expo:
                    merged[key] = expo[key]
        if accepted:
            merged["external_id"] = accepted[0].get("external_id")
            return merged
        merged["reason"] = "no_endpoint" if not attempted else (attempted[0].get("reason") or "not_accepted")
        merged["transient"] = any(r.get("transient") for r in attempted)
        merged["safe_to_retry"] = bool(attempted) and all(r.get("safe_to_retry") is True for r in attempted)
        return merged

    async def cancel(self, **kwargs) -> Dict[str, Any]:
        for provider in self.providers:
            try:
                await provider.cancel(**kwargs)
            except Exception:
                pass
        return {"ok": True, "provider": self.name, "retracted": False}
