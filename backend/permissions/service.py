"""
PermissionService — facade over CapabilityRegistry + Consent + Audit.

This is the ONLY object callers should touch. It composes:
    - the immutable capability registry,
    - the mutable capability METADATA store (enabled/disabled, notes),
    - the ConsentService,
    - the AuditService,
    - the AccessGuard (see guard.py).

Startup: `PermissionService.sync_registry()` mirrors the frozen registry
into MongoDB so ops can flip enabled/disabled without touching code.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit import AuditService
from .capabilities import (
    CAPABILITIES,
    CAPABILITY_REGISTRY_VERSION,
    as_dict as _cap_as_dict,
    capability_by_id,
)
from .consent import CONSENT_STATUS_ACTIVE, ConsentService
from .errors import CapabilityDisabled, CapabilityUnknown, ConsentDenied
from .models import INSTANCE_WILDCARD

logger = logging.getLogger("ora.permissions")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PermissionService:
    def __init__(self, db):
        self.db = db
        self.consents = ConsentService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------
    # startup / registry sync
    # ------------------------------------------------------------------
    @property
    def meta_col(self):
        return self.db.permission_capability_meta

    async def sync_registry(self) -> Dict[str, Any]:
        """Idempotent: writes canonical registry entries to Mongo (metadata
        store) so ops can toggle `enabled`. NEVER overrides operator changes
        to `enabled`, `rollout_notes`, `admin_description`. Structural fields
        (data_categories, sensitivity, platforms, ...) are ALWAYS overwritten
        from code to prevent DB tampering."""
        now = _now_iso()
        upserted = 0
        for cap in CAPABILITIES:
            structural = _cap_as_dict(cap)
            structural.pop("id", None)
            # Snapshot the immutable structural part under a key so ops-side
            # bulk edits cannot conflict with it in the same document.
            update = {
                "$set": {
                    "structural": structural,
                    "registry_version": CAPABILITY_REGISTRY_VERSION,
                    "synced_at": now,
                },
                "$setOnInsert": {
                    "id": cap["id"],
                    "enabled": cap["default_status"] != "disabled",
                    "rollout_notes": None,
                    "admin_description": None,
                    "created_at": now,
                },
            }
            res = await self.meta_col.update_one({"id": cap["id"]}, update, upsert=True)
            if res.upserted_id is not None or res.modified_count > 0:
                upserted += 1
        # Mark orphaned capabilities (not in current registry) as unlisted.
        current_ids = [c["id"] for c in CAPABILITIES]
        await self.meta_col.update_many(
            {"id": {"$nin": current_ids}},
            {"$set": {"unlisted": True, "synced_at": now}},
        )
        return {"synced": len(CAPABILITIES), "changed": upserted, "version": CAPABILITY_REGISTRY_VERSION}

    async def get_meta(self, cap_id: str) -> Optional[Dict[str, Any]]:
        return await self.meta_col.find_one({"id": cap_id}, {"_id": 0})

    async def set_enabled(self, cap_id: str, enabled: bool, *, admin_actor: str = "system") -> Optional[Dict[str, Any]]:
        cap = capability_by_id(cap_id)
        if not cap:
            raise CapabilityUnknown(cap_id)
        res = await self.meta_col.update_one(
            {"id": cap_id},
            {"$set": {"enabled": bool(enabled), "updated_at": _now_iso(), "updated_by": admin_actor}},
        )
        if res.matched_count == 0:
            return None
        await self.audit.log(
            user_id=None,
            actor_type="admin",
            event_type="capability.toggle",
            capability_id=cap_id,
            success=True,
            reason_code="enabled" if enabled else "disabled",
            details={"admin_actor": admin_actor},
        )
        return await self.get_meta(cap_id)

    # ------------------------------------------------------------------
    # registry lookup
    # ------------------------------------------------------------------
    def list_capabilities(self) -> List[Dict[str, Any]]:
        return [_cap_as_dict(c) for c in CAPABILITIES]

    def registry_version(self) -> str:
        return CAPABILITY_REGISTRY_VERSION

    async def list_capabilities_with_meta(self) -> List[Dict[str, Any]]:
        metas = {m["id"]: m async for m in self.meta_col.find({}, {"_id": 0})}
        out: List[Dict[str, Any]] = []
        for cap in CAPABILITIES:
            meta = metas.get(cap["id"]) or {}
            data = _cap_as_dict(cap)
            data["enabled"] = bool(meta.get("enabled", cap["default_status"] != "disabled"))
            data["rollout_notes"] = meta.get("rollout_notes")
            data["admin_description"] = meta.get("admin_description")
            out.append(data)
        return out

    async def is_capability_enabled(self, cap_id: str) -> bool:
        meta = await self.get_meta(cap_id)
        if meta is None:
            cap = capability_by_id(cap_id)
            return bool(cap) and cap["default_status"] != "disabled"
        return bool(meta.get("enabled", True))

    # ------------------------------------------------------------------
    # consent lifecycle (with audit)
    # ------------------------------------------------------------------
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
        actor_type: str = "user",
        correlation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cap = capability_by_id(capability_id)
        if not cap:
            await self.audit.log(
                user_id=user_id, actor_type=actor_type,
                event_type="consent.grant",
                capability_id=capability_id, connector_id=connector_id,
                connector_instance_id=connector_instance_id,
                success=False, reason_code="capability_unknown",
                correlation_id=correlation_id, request_id=request_id,
            )
            raise CapabilityUnknown(capability_id)
        if not await self.is_capability_enabled(capability_id):
            await self.audit.log(
                user_id=user_id, actor_type=actor_type,
                event_type="consent.grant",
                capability_id=capability_id, connector_id=connector_id,
                connector_instance_id=connector_instance_id,
                success=False, reason_code="capability_disabled",
                correlation_id=correlation_id, request_id=request_id,
            )
            raise CapabilityDisabled(capability_id)

        doc = await self.consents.grant(
            user_id=user_id,
            capability_id=capability_id,
            connector_id=connector_id,
            connector_instance_id=connector_instance_id,
            purpose_id=purpose_id,
            scopes=scopes,
            expires_at=expires_at,
            metadata=metadata,
        )
        await self.audit.log(
            user_id=user_id, actor_type=actor_type,
            event_type="consent.grant",
            capability_id=capability_id, connector_id=connector_id,
            connector_instance_id=connector_instance_id,
            purpose_id=purpose_id,
            success=True, reason_code="granted",
            data_classification=cap.get("sensitivity"),
            correlation_id=correlation_id, request_id=request_id,
        )
        return doc

    async def revoke(
        self,
        *,
        user_id: str,
        capability_id: str,
        connector_id: str,
        connector_instance_id: str = INSTANCE_WILDCARD,
        reason: Optional[str] = None,
        actor_type: str = "user",
        correlation_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        cap = capability_by_id(capability_id)
        doc = await self.consents.revoke(
            user_id=user_id,
            capability_id=capability_id,
            connector_id=connector_id,
            connector_instance_id=connector_instance_id,
            reason=reason,
        )
        await self.audit.log(
            user_id=user_id, actor_type=actor_type,
            event_type="consent.revoke",
            capability_id=capability_id, connector_id=connector_id,
            connector_instance_id=connector_instance_id,
            success=bool(doc), reason_code=reason or ("revoked" if doc else "not_found"),
            data_classification=(cap or {}).get("sensitivity"),
            correlation_id=correlation_id,
        )
        return doc

    async def revoke_all_for_connector(
        self,
        user_id: str,
        connector_id: str,
        *,
        reason: Optional[str] = None,
        actor_type: str = "user",
    ) -> int:
        count = await self.consents.revoke_all_for_connector(user_id, connector_id, reason=reason)
        await self.audit.log(
            user_id=user_id, actor_type=actor_type,
            event_type="consent.revoke_all",
            connector_id=connector_id,
            success=True, reason_code=reason or "bulk_revoked",
            details={"revoked_count": count},
        )
        return count

    # ------------------------------------------------------------------
    # access check (used by AccessGuard + PermissionsContextProvider)
    # ------------------------------------------------------------------
    async def check_access(
        self,
        *,
        user_id: str,
        capability_id: str,
        connector_id: str,
        connector_instance_id: str = INSTANCE_WILDCARD,
        purpose_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        context_snapshot_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        audit: bool = True,
    ) -> bool:
        cap = capability_by_id(capability_id)
        if not cap:
            if audit:
                await self.audit.log(
                    user_id=user_id, event_type="access.check",
                    capability_id=capability_id, connector_id=connector_id,
                    connector_instance_id=connector_instance_id,
                    success=False, reason_code="capability_unknown",
                    correlation_id=correlation_id, request_id=request_id,
                )
            return False
        if not await self.is_capability_enabled(capability_id):
            if audit:
                await self.audit.log(
                    user_id=user_id, event_type="access.check",
                    capability_id=capability_id, connector_id=connector_id,
                    connector_instance_id=connector_instance_id,
                    success=False, reason_code="capability_disabled",
                    correlation_id=correlation_id, request_id=request_id,
                )
            return False
        ok = await self.consents.is_granted(
            user_id=user_id,
            capability_id=capability_id,
            connector_id=connector_id,
            connector_instance_id=connector_instance_id,
        )
        if audit:
            await self.audit.log(
                user_id=user_id, event_type="access.check",
                capability_id=capability_id, connector_id=connector_id,
                connector_instance_id=connector_instance_id,
                purpose_id=purpose_id, decision_id=decision_id,
                context_snapshot_id=context_snapshot_id,
                success=ok, reason_code="granted" if ok else "no_active_consent",
                data_classification=cap.get("sensitivity"),
                correlation_id=correlation_id, request_id=request_id,
            )
        return ok

    async def require_access(self, **kwargs) -> None:
        ok = await self.check_access(**kwargs)
        if not ok:
            raise ConsentDenied(
                capability_id=kwargs.get("capability_id"),
                connector_id=kwargs.get("connector_id"),
                connector_instance_id=kwargs.get("connector_instance_id", INSTANCE_WILDCARD),
            )
