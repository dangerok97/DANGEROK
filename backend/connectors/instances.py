"""ConnectorInstance service — per-user, per-connector, per-account.

Stores instance metadata + a `secret_reference` pointing at the vault.
Never persists tokens directly.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

CONNECTOR_INSTANCE_STATUSES = (
    "pending",
    "connected",
    "syncing",
    "degraded",
    "reauthorization_required",
    "revoked",
    "disabled",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def hash_provider_account_id(provider_account_id: str) -> str:
    return "acct_" + hashlib.sha256(provider_account_id.encode("utf-8")).hexdigest()[:24]


class ConnectorInstanceService:
    def __init__(self, db):
        self.db = db

    @property
    def col(self):
        return self.db.connector_instances

    async def upsert(
        self,
        *,
        user_id: str,
        connector_id: str,
        provider_account_id: str,
        display_label: str,
        platform: Optional[str] = None,
        authorized_scopes: Optional[List[str]] = None,
        selected_resource_ids: Optional[List[str]] = None,
        sync_mode: str = "polling",
        secret_reference: Optional[str] = None,
        status: str = "connected",
        webhook_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        poll_interval_min: int = 15,
        window_past_days: int = 30,
        window_future_days: int = 180,
    ) -> Dict[str, Any]:
        assert status in CONNECTOR_INSTANCE_STATUSES
        acct_hash = hash_provider_account_id(provider_account_id)
        now = _now_iso()
        next_sync_at = (_now() + timedelta(minutes=poll_interval_min)).isoformat()
        existing = await self.col.find_one(
            {"user_id": user_id, "connector_id": connector_id, "provider_account_id_hash": acct_hash},
            {"_id": 0},
        )
        if existing:
            update: Dict[str, Any] = {
                "$set": {
                    "display_label": display_label,
                    "platform": platform or existing.get("platform"),
                    "authorized_scopes": authorized_scopes if authorized_scopes is not None else existing.get("authorized_scopes") or [],
                    "sync_mode": sync_mode,
                    "webhook_status": webhook_status or existing.get("webhook_status"),
                    "status": status,
                    "reauthorization_required": status == "reauthorization_required",
                    "poll_interval_min": poll_interval_min,
                    "window_past_days": window_past_days,
                    "window_future_days": window_future_days,
                    "next_sync_at": next_sync_at,
                    "updated_at": now,
                },
            }
            if selected_resource_ids is not None:
                update["$set"]["selected_resource_ids"] = selected_resource_ids
            if secret_reference is not None:
                update["$set"]["secret_reference"] = secret_reference
            if metadata is not None:
                update["$set"]["metadata"] = {**(existing.get("metadata") or {}), **metadata}
            await self.col.update_one({"id": existing["id"]}, update)
            return await self.col.find_one({"id": existing["id"]}, {"_id": 0})

        doc = {
            "id": f"ci_{uuid.uuid4().hex[:16]}",
            "user_id": user_id,
            "connector_id": connector_id,
            "provider_account_id_hash": acct_hash,
            "display_label": display_label,
            "platform": platform,
            "status": status,
            "authorized_scopes": authorized_scopes or [],
            "selected_resource_ids": selected_resource_ids or [],
            "sync_mode": sync_mode,
            "last_sync_at": None,
            "next_sync_at": next_sync_at,
            "cursor": None,
            "webhook_status": webhook_status,
            "reauthorization_required": status == "reauthorization_required",
            "secret_reference": secret_reference,
            "poll_interval_min": poll_interval_min,
            "window_past_days": window_past_days,
            "window_future_days": window_future_days,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get(self, user_id: str, instance_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one({"id": instance_id, "user_id": user_id}, {"_id": 0})

    async def list(self, user_id: str, connector_id: Optional[str] = None) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if connector_id:
            q["connector_id"] = connector_id
        cursor = self.col.find(q, {"_id": 0}).sort("created_at", -1)
        return await cursor.to_list(length=200)

    async def update(self, user_id: str, instance_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        fields = dict(fields)
        fields["updated_at"] = _now_iso()
        res = await self.col.update_one({"id": instance_id, "user_id": user_id}, {"$set": fields})
        if res.matched_count == 0:
            return None
        return await self.get(user_id, instance_id)

    async def mark_status(self, user_id: str, instance_id: str, status: str, extra: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        assert status in CONNECTOR_INSTANCE_STATUSES
        upd = {"status": status, "updated_at": _now_iso(), "reauthorization_required": status == "reauthorization_required"}
        if extra:
            upd.update(extra)
        res = await self.col.update_one({"id": instance_id, "user_id": user_id}, {"$set": upd})
        if res.matched_count == 0:
            return None
        return await self.get(user_id, instance_id)

    async def set_cursor(
        self,
        user_id: str,
        instance_id: str,
        *,
        calendar_id: str,
        sync_token: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        doc = await self.get(user_id, instance_id)
        if not doc:
            return None
        cursor = dict(doc.get("cursor") or {})
        cursor[calendar_id] = {"sync_token": sync_token, "updated_at": _now_iso()}
        await self.col.update_one(
            {"id": instance_id, "user_id": user_id},
            {"$set": {"cursor": cursor, "last_sync_at": _now_iso(), "updated_at": _now_iso()}},
        )
        return await self.get(user_id, instance_id)
