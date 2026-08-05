"""
Token Vault — abstract interface + Fernet dev implementation.

Design goals:
  - Tokens (OAuth access/refresh), client secrets, and any long-lived
    credential MUST NEVER be stored in plaintext in the ordinary DB.
  - Callers (connectors) refer to a vault entry via `secret_reference`,
    an opaque id. The plaintext material is materialized ONLY inside
    the connector at request time and never surfaced through the API.
  - The interface is deliberately KMS-shaped so the Fernet impl can be
    swapped for AWS KMS / GCP Secret Manager / Vault without touching
    callers. Production must NOT ship with the Fernet impl.
  - If configuration is missing, the factory returns a `DisabledVault`
    that raises `VaultNotConfigured` on any operation — connectors that
    depend on the vault will then surface a clean `provider_not_configured`
    error rather than silently degrading.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("ora.security.token_vault")


class VaultError(Exception):
    """Base vault error."""


class VaultNotConfigured(VaultError):
    """Raised when the vault is required but not configured."""


class VaultMissingEntry(VaultError):
    """Raised when a secret_reference cannot be resolved."""


class VaultTampered(VaultError):
    """Raised when payload integrity fails (bad key, tampered ciphertext)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TokenVault(Protocol):
    """Abstract async vault. Implementations must be safe to share."""

    backend_name: str

    async def put(self, *, user_id: str, purpose: str, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str: ...
    async def get(self, secret_reference: str, *, user_id: Optional[str] = None) -> Dict[str, Any]: ...
    async def rotate(self, secret_reference: str, *, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str: ...
    async def revoke(self, secret_reference: str) -> bool: ...
    async def health_check(self) -> Dict[str, Any]: ...


class DisabledVault:
    """Sentinel vault used when TOKEN_VAULT_BACKEND is missing/misconfigured.
    Every operation raises `VaultNotConfigured` with a clear message."""

    backend_name = "disabled"

    def __init__(self, reason: str):
        self.reason = reason

    def _fail(self):
        raise VaultNotConfigured(f"Token vault disabled: {self.reason}")

    async def put(self, **kwargs):  # noqa: D401
        self._fail()

    async def get(self, *args, **kwargs):
        self._fail()

    async def rotate(self, *args, **kwargs):
        self._fail()

    async def revoke(self, *args, **kwargs):
        self._fail()

    async def health_check(self) -> Dict[str, Any]:
        return {"backend": "disabled", "healthy": False, "reason": self.reason}


class FernetTokenVault:
    """Development/preview implementation.

    Ciphertext is stored in Mongo (`secret_vault`), keyed by an opaque
    id (`sv_<hex>`). The Fernet key is loaded from `TOKEN_VAULT_KEY` in
    the environment; there is no in-code fallback.

    WARNING: this backend is acceptable for preview / on-box deployments.
    Production must migrate to a KMS-backed implementation.
    """

    backend_name = "fernet"

    def __init__(self, db, key: bytes):
        self.db = db
        try:
            self._fernet = Fernet(key)
        except Exception as e:
            raise VaultNotConfigured(f"Invalid Fernet key: {e}") from e

    @property
    def col(self):
        return self.db.secret_vault

    async def put(
        self,
        *,
        user_id: str,
        purpose: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        blob = self._encrypt(payload)
        secret_id = f"sv_{uuid.uuid4().hex[:16]}"
        doc = {
            "id": secret_id,
            "user_id": user_id,
            "purpose": purpose,
            "backend": self.backend_name,
            "ciphertext": blob,
            "metadata": metadata or {},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "status": "active",
        }
        await self.col.insert_one(doc)
        return secret_id

    async def get(self, secret_reference: str, *, user_id: Optional[str] = None) -> Dict[str, Any]:
        q: Dict[str, Any] = {"id": secret_reference, "status": "active"}
        if user_id:
            q["user_id"] = user_id
        doc = await self.col.find_one(q, {"_id": 0})
        if not doc:
            raise VaultMissingEntry(secret_reference)
        return self._decrypt(doc["ciphertext"])

    async def rotate(
        self,
        secret_reference: str,
        *,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        blob = self._encrypt(payload)
        update: Dict[str, Any] = {
            "$set": {
                "ciphertext": blob,
                "updated_at": _now_iso(),
            },
        }
        if metadata is not None:
            update["$set"]["metadata"] = metadata
        res = await self.col.update_one({"id": secret_reference, "status": "active"}, update)
        if res.matched_count == 0:
            raise VaultMissingEntry(secret_reference)
        return secret_reference

    async def revoke(self, secret_reference: str) -> bool:
        res = await self.col.update_one(
            {"id": secret_reference, "status": "active"},
            {"$set": {"status": "revoked", "revoked_at": _now_iso(), "ciphertext": None}},
        )
        return res.matched_count > 0

    async def health_check(self) -> Dict[str, Any]:
        return {"backend": self.backend_name, "healthy": True}

    # ------------------------------------------------------------------
    def _encrypt(self, payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(raw).decode("ascii")

    def _decrypt(self, ct: str) -> Dict[str, Any]:
        if not ct:
            raise VaultMissingEntry("<empty ciphertext>")
        try:
            raw = self._fernet.decrypt(ct.encode("ascii"))
        except InvalidToken as e:
            raise VaultTampered(str(e)) from e
        return json.loads(raw.decode("utf-8"))


def _fernet_key_bytes(raw: str) -> bytes:
    """Accept a Fernet key or derive one from a passphrase (local/dev).

    Prefer `Fernet.generate_key()` output in production. Passphrases are
    hashed with SHA-256 and urlsafe-base64-encoded to 32 bytes.
    """
    import hashlib

    raw_b = raw.strip().encode("utf-8")
    try:
        Fernet(raw_b)
        return raw_b
    except Exception:
        digest = hashlib.sha256(raw_b).digest()
        return base64.urlsafe_b64encode(digest)


def build_token_vault(db) -> "TokenVault | DisabledVault":
    """Factory. Reads TOKEN_VAULT_BACKEND + TOKEN_VAULT_KEY from env.

    `local` is accepted as an alias of `fernet` for local/dev (same cipher).
    Encryption key: TOKEN_VAULT_KEY or OAUTH_TOKEN_ENCRYPTION_KEY.
    """
    backend = os.environ.get("TOKEN_VAULT_BACKEND", "").strip().lower()
    if backend in ("fernet", "local"):
        key = (
            os.environ.get("TOKEN_VAULT_KEY", "").strip()
            or os.environ.get("OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()
        )
        if not key:
            logger.error("TOKEN_VAULT_KEY / OAUTH_TOKEN_ENCRYPTION_KEY missing")
            return DisabledVault(reason="TOKEN_VAULT_KEY missing")
        try:
            return FernetTokenVault(db, _fernet_key_bytes(key))
        except VaultNotConfigured as e:
            logger.error("FernetTokenVault init failed: %s", e)
            return DisabledVault(reason=str(e))
    if backend in ("", "disabled"):
        return DisabledVault(reason="TOKEN_VAULT_BACKEND not set")
    return DisabledVault(reason=f"Unsupported backend: {backend}")

# convenience for callers
def is_configured(vault) -> bool:
    return not isinstance(vault, DisabledVault)
