"""
Consent Service — grant / revoke / query.

Model:
    consents := {user_id, capability_id, connector_id, connector_instance_id}
Uniqueness constraint on (user_id, capability_id, connector_id,
connector_instance_id) — only one ACTIVE consent per tuple; revoked
consents keep their history via `status="revoked"`.

Wildcard convention: `connector_instance_id="*"` means "all instances of
this connector". The guard checks the exact instance first, then the
wildcard. Wildcard is never elevated to a different semantic model.

Data Revocation Plan:
    - `revoke()` performs a SOFT revoke: status flips to "revoked" and
      `revoked_at` is stamped. The record STAYS (audit trail).
    - Downstream consumers (connectors, providers) MUST re-check
      `is_granted()` before every read. There is no cached authority.
    - A future purge worker can delete data derived from revoked
      consents; this iteration marks the intent (`purge_after`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .capabilities import CAPABILITY_REGISTRY_VERSION
from .models import INSTANCE_WILDCARD

CONSENT_STATUS_ACTIVE = "active"
CONSENT_STATUS_REVOKED = "revoked"
CONSENT_STATUS_EXPIRED = "expired"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConsentService:
    def __init__(self, db):
        self.db = db

    @property
    def col(self):
        return self.db.permission_consents

    async def grant(
        self,
        *,
        user_id: str,
        capability_id: str,
        connector_id: str,
        connector_instance_id: str = INSTANCE_WILDCARD,
        purpose_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Idempotent: re-granting an already-active consent bumps `version`
        and refreshes `granted_at`. If a revoked consent exists for the same
        tuple, it is reactivated (fresh id kept, but `previous_id` recorded)."""
        now = _now_iso()
        query = {
            "user_id": user_id,
            "capability_id": capability_id,
            "connector_id": connector_id,
            "connector_instance_id": connector_instance_id,
        }
        existing = await self.col.find_one(query, {"_id": 0})
        if existing:
            update = {
                "$set": {
                    "status": CONSENT_STATUS_ACTIVE,
                    "granted_at": now,
                    "revoked_at": None,
                    "expires_at": expires_at,
                    "purpose_id": purpose_id or existing.get("purpose_id"),
                    "scopes": scopes if scopes is not None else existing.get("scopes") or [],
                    "metadata": metadata if metadata is not None else existing.get("metadata") or {},
                    "capability_registry_version": CAPABILITY_REGISTRY_VERSION,
                },
                "$inc": {"version": 1},
            }
            await self.col.update_one(query, update)
            return await self.col.find_one(query, {"_id": 0})

        doc = {
            "id": f"con_{uuid.uuid4().hex[:16]}",
            "user_id": user_id,
            "capability_id": capability_id,
            "connector_id": connector_id,
            "connector_instance_id": connector_instance_id,
            "purpose_id": purpose_id,
            "scopes": scopes or [],
            "status": CONSENT_STATUS_ACTIVE,
            "granted_at": now,
            "revoked_at": None,
            "expires_at": expires_at,
            "version": 1,
            "capability_registry_version": CAPABILITY_REGISTRY_VERSION,
            "metadata": metadata or {},
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def revoke(
        self,
        *,
        user_id: str,
        capability_id: str,
        connector_id: str,
        connector_instance_id: str = INSTANCE_WILDCARD,
        reason: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        now = _now_iso()
        query = {
            "user_id": user_id,
            "capability_id": capability_id,
            "connector_id": connector_id,
            "connector_instance_id": connector_instance_id,
            "status": CONSENT_STATUS_ACTIVE,
        }
        res = await self.col.update_one(
            query,
            {"$set": {
                "status": CONSENT_STATUS_REVOKED,
                "revoked_at": now,
                "revoke_reason": reason,
            }},
        )
        if res.matched_count == 0:
            return None
        return await self.col.find_one({
            "user_id": user_id,
            "capability_id": capability_id,
            "connector_id": connector_id,
            "connector_instance_id": connector_instance_id,
        }, {"_id": 0})

    async def revoke_all_for_connector(self, user_id: str, connector_id: str, reason: Optional[str] = None) -> int:
        """Bulk revoke every active consent tied to a connector (any capability, any instance)."""
        now = _now_iso()
        res = await self.col.update_many(
            {"user_id": user_id, "connector_id": connector_id, "status": CONSENT_STATUS_ACTIVE},
            {"$set": {
                "status": CONSENT_STATUS_REVOKED,
                "revoked_at": now,
                "revoke_reason": reason,
            }},
        )
        return res.modified_count

    async def get(self, *, user_id: str, capability_id: str, connector_id: str, connector_instance_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one({
            "user_id": user_id,
            "capability_id": capability_id,
            "connector_id": connector_id,
            "connector_instance_id": connector_instance_id,
        }, {"_id": 0})

    async def is_granted(
        self,
        *,
        user_id: str,
        capability_id: str,
        connector_id: str,
        connector_instance_id: str = INSTANCE_WILDCARD,
    ) -> bool:
        """Guard-side check with wildcard fallback:
          1. exact match on (capability, connector, instance),
          2. wildcard (instance_id == '*') for the same capability + connector.
        Also enforces the expiry timestamp (best-effort).
        """
        now = _now_iso()
        # exact first
        candidates = []
        if connector_instance_id and connector_instance_id != INSTANCE_WILDCARD:
            exact = await self.get(
                user_id=user_id,
                capability_id=capability_id,
                connector_id=connector_id,
                connector_instance_id=connector_instance_id,
            )
            if exact:
                candidates.append(exact)
        wildcard = await self.get(
            user_id=user_id,
            capability_id=capability_id,
            connector_id=connector_id,
            connector_instance_id=INSTANCE_WILDCARD,
        )
        if wildcard:
            candidates.append(wildcard)

        for c in candidates:
            if c.get("status") != CONSENT_STATUS_ACTIVE:
                continue
            exp = c.get("expires_at")
            if exp and exp < now:
                continue
            return True
        return False

    async def list_for_user(
        self,
        user_id: str,
        *,
        status: Optional[str] = None,
        connector_id: Optional[str] = None,
        capability_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if status:
            q["status"] = status
        if connector_id:
            q["connector_id"] = connector_id
        if capability_id:
            q["capability_id"] = capability_id
        cursor = self.col.find(q, {"_id": 0}).sort("granted_at", -1)
        return await cursor.to_list(length=1000)

    async def active_capability_ids(self, user_id: str, connector_id: Optional[str] = None) -> List[str]:
        q: Dict[str, Any] = {"user_id": user_id, "status": CONSENT_STATUS_ACTIVE}
        if connector_id:
            q["connector_id"] = connector_id
        cursor = self.col.find(q, {"_id": 0, "capability_id": 1})
        docs = await cursor.to_list(length=1000)
        return sorted({d["capability_id"] for d in docs})
