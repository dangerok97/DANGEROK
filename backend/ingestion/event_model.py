"""IngestionEvent — persistence model + repository.

Every payload ingested through ORA is anchored to an IngestionEvent doc
whose lifecycle status walks the pipeline. This gives us:
  - idempotency (payload_hash, external_id+version);
  - deduplication (query on external_id/version);
  - audit trail (status transitions, error_code, retry_count);
  - superseded chain (superseded_event_id when a newer version arrives).

We DO NOT store OAuth tokens, secrets, or raw sensitive payloads here.
The `raw_reference` is a safe pointer (e.g. calendar_id/event_id) NOT
the payload. `normalized_payload` is the canonical, minimized view.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .types import (
    INGESTION_STATUS_QUARANTINED,
    INGESTION_STATUS_RECEIVED,
    INGESTION_STATUS_SUPERSEDED,
    INGESTION_STATUSES,
)


# Fields blacklisted from ever landing in `raw_reference` or `normalized_payload`.
_SENSITIVE_KEYS_BLACKLIST = {
    "access_token", "refresh_token", "id_token", "client_secret", "token",
    "password", "authorization", "cookie", "set-cookie",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _sanitize_reference(ref: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not ref:
        return {}
    return {k: v for k, v in ref.items() if k.lower() not in _SENSITIVE_KEYS_BLACKLIST}


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class IngestionEventRepository:
    def __init__(self, db, retention_days: int = 180):
        self.db = db
        self.retention_days = int(retention_days)

    @property
    def col(self):
        return self.db.ingestion_events

    async def insert(
        self,
        *,
        user_id: str,
        connector_id: str,
        connector_instance_id: str,
        external_id: str,
        external_version: Optional[str],
        source_type: str,
        source_record_type: str,
        raw_reference: Optional[Dict[str, Any]],
        normalized_payload: Optional[Dict[str, Any]],
        payload_hash: Optional[str],
        source_created_at: Optional[str],
        source_updated_at: Optional[str],
        provenance: Optional[Dict[str, Any]],
        sensitivity: str,
        status: str = INGESTION_STATUS_RECEIVED,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status not in INGESTION_STATUSES:
            raise ValueError(f"invalid ingestion status: {status!r}")
        now = _now()
        retention_until = (now + timedelta(days=self.retention_days)).isoformat()
        doc = {
            "id": f"ing_{uuid.uuid4().hex[:16]}",
            "user_id": user_id,
            "connector_id": connector_id,
            "connector_instance_id": connector_instance_id,
            "external_id": external_id,
            "external_version": external_version,
            "source_type": source_type,
            "source_record_type": source_record_type,
            "ingestion_status": status,
            "raw_reference": _sanitize_reference(raw_reference),
            "normalized_payload": normalized_payload,
            "payload_hash": payload_hash,
            "source_created_at": source_created_at,
            "source_updated_at": source_updated_at,
            "ingested_at": now.isoformat(),
            "processed_at": None,
            "error_code": None,
            "retry_count": 0,
            "provenance": provenance or {},
            "sensitivity": sensitivity,
            "retention_until": retention_until,
            "correlation_id": correlation_id,
            "supersedes_event_id": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def update_status(
        self,
        event_id: str,
        *,
        status: str,
        error_code: Optional[str] = None,
        processed_at: Optional[str] = None,
        supersedes_event_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if status not in INGESTION_STATUSES:
            raise ValueError(f"invalid ingestion status: {status!r}")
        upd: Dict[str, Any] = {"ingestion_status": status, "updated_at": _now_iso()}
        if error_code is not None:
            upd["error_code"] = error_code
        if processed_at is not None:
            upd["processed_at"] = processed_at
        if supersedes_event_id is not None:
            upd["supersedes_event_id"] = supersedes_event_id
        if extra:
            upd.update(extra)
        await self.col.update_one({"id": event_id}, {"$set": upd})
        return await self.col.find_one({"id": event_id}, {"_id": 0})

    async def find_latest_by_external(
        self,
        *,
        user_id: str,
        connector_instance_id: str,
        external_id: str,
    ) -> Optional[Dict[str, Any]]:
        cursor = self.col.find(
            {
                "user_id": user_id,
                "connector_instance_id": connector_instance_id,
                "external_id": external_id,
                "ingestion_status": {"$ne": INGESTION_STATUS_SUPERSEDED},
            },
            {"_id": 0},
        ).sort("ingested_at", -1).limit(1)
        docs = await cursor.to_list(length=1)
        return docs[0] if docs else None

    async def mark_superseded(self, event_id: str) -> None:
        await self.col.update_one(
            {"id": event_id},
            {"$set": {"ingestion_status": INGESTION_STATUS_SUPERSEDED, "updated_at": _now_iso()}},
        )

    async def list_for_user(
        self,
        user_id: str,
        *,
        connector_id: Optional[str] = None,
        connector_instance_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if connector_id:
            q["connector_id"] = connector_id
        if connector_instance_id:
            q["connector_instance_id"] = connector_instance_id
        if status:
            q["ingestion_status"] = status
        cursor = self.col.find(q, {"_id": 0}).sort("ingested_at", -1).limit(max(1, min(limit, 1000)))
        return await cursor.to_list(length=1000)

    async def get(self, user_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one({"id": event_id, "user_id": user_id}, {"_id": 0})

    async def stats(self, user_id: str) -> Dict[str, Any]:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": {"c": "$connector_id", "s": "$ingestion_status"}, "n": {"$sum": 1}}},
        ]
        raw = await self.col.aggregate(pipeline).to_list(length=1000)
        by_connector: Dict[str, Dict[str, int]] = {}
        total = 0
        for r in raw:
            c = r["_id"]["c"] or "unknown"
            s = r["_id"]["s"] or "unknown"
            by_connector.setdefault(c, {})[s] = int(r["n"])
            total += int(r["n"])
        return {"total": total, "by_connector": by_connector}

    async def quarantine(
        self,
        *,
        user_id: str,
        connector_id: str,
        connector_instance_id: str,
        external_id: str,
        error_code: str,
        raw_reference: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a QUARANTINED IngestionEvent for malformed / rejected payloads.
        Never carries the original payload — only a reference + error code."""
        return await self.insert(
            user_id=user_id,
            connector_id=connector_id,
            connector_instance_id=connector_instance_id,
            external_id=external_id,
            external_version=None,
            source_type=connector_id,
            source_record_type="malformed",
            raw_reference=raw_reference,
            normalized_payload=None,
            payload_hash=None,
            source_created_at=None,
            source_updated_at=None,
            provenance=None,
            sensitivity="personal",
            status=INGESTION_STATUS_QUARANTINED,
            correlation_id=correlation_id,
        )
