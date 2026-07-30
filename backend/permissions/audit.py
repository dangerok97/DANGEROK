"""
Append-only permission audit log.

Every consent lifecycle event (grant, revoke, expire) AND every
access check (allowed/denied) MUST be written here. Records are
IMMUTABLE — never patched, never deleted (a TTL policy is applied
at the index level but individual updates are forbidden).

The audit log NEVER stores sensitive payloads (email bodies, IBANs,
OAuth tokens, message contents, etc.) — only IDs, classifications
and outcomes.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.permissions.audit")

# Default retention: 365 days. Tunable via env.
_DEFAULT_RETENTION_DAYS = int(os.environ.get("PERMISSION_AUDIT_RETENTION_DAYS", "365"))

# Fields that are actively blacklisted from ever entering the audit log.
_SENSITIVE_BLACKLIST = {
    "token", "access_token", "refresh_token", "password", "iban",
    "card_number", "cvv", "otp", "message_body", "email_body",
    "note", "notes_body",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _sanitize(details: Dict[str, Any]) -> Dict[str, Any]:
    """Remove any keys that look like they hold sensitive content."""
    if not details:
        return {}
    clean: Dict[str, Any] = {}
    for k, v in details.items():
        if k.lower() in _SENSITIVE_BLACKLIST:
            continue
        clean[k] = v
    return clean


class AuditService:
    def __init__(self, db, retention_days: int = _DEFAULT_RETENTION_DAYS):
        self.db = db
        self.retention_days = int(retention_days)

    @property
    def col(self):
        return self.db.permission_audit

    async def log(
        self,
        *,
        user_id: Optional[str],
        event_type: str,
        actor_type: str = "user",
        capability_id: Optional[str] = None,
        connector_id: Optional[str] = None,
        connector_instance_id: Optional[str] = None,
        purpose_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        context_snapshot_id: Optional[str] = None,
        success: bool = True,
        reason_code: Optional[str] = None,
        duration_ms: Optional[float] = None,
        records_requested: Optional[int] = None,
        records_returned: Optional[int] = None,
        data_classification: Optional[str] = None,
        correlation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = _now()
        retention_until = (now + timedelta(days=self.retention_days)).isoformat()
        doc = {
            "event_id": f"aud_{uuid.uuid4().hex[:16]}",
            "correlation_id": correlation_id,
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "actor_type": actor_type,
            "event_type": event_type,
            "capability_id": capability_id,
            "connector_id": connector_id,
            "connector_instance_id": connector_instance_id,
            "purpose_id": purpose_id,
            "decision_id": decision_id,
            "context_snapshot_id": context_snapshot_id,
            "success": bool(success),
            "reason_code": reason_code,
            "timestamp": now.isoformat(),
            "duration_ms": duration_ms,
            "records_requested": records_requested,
            "records_returned": records_returned,
            "data_classification": data_classification,
            "retention_until": retention_until,
            "details": _sanitize(details or {}),
            # Append-only marker: any UPDATE must never touch this doc.
            "immutable": True,
        }
        try:
            await self.col.insert_one(doc)
        except Exception:
            logger.exception("audit insert failed (event_type=%s)", event_type)
        doc.pop("_id", None)
        return doc

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 200,
        capability_id: Optional[str] = None,
        connector_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if capability_id:
            q["capability_id"] = capability_id
        if connector_id:
            q["connector_id"] = connector_id
        if event_type:
            q["event_type"] = event_type
        cursor = self.col.find(q, {"_id": 0}).sort("timestamp", -1).limit(max(1, min(limit, 1000)))
        return await cursor.to_list(length=1000)
