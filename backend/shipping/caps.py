"""Shipment competency for ORA.

No shipment screen and no Amazon account fiction. This capability reuses the
connected Gmail sensor as evidence, lets cognition inspect one exact message
when necessary, and returns active temporary situations for continuity.

The AI decides which message/situation is about the shipment. Code only:
- refreshes connected mailboxes,
- returns bounded owner-scoped evidence,
- reads one exact user-owned message body when explicitly requested.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from conversation_engine.ai_core.models import Observation

logger = logging.getLogger("ora.shipping")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _refresh_mail(db, user_id: str) -> Dict[str, Any]:
    """Best-effort fresh mailbox read through the existing Connected Life door."""
    try:
        from deps import get_gmail_service
        from connected.service import ConnectedLifeService

        mail = get_gmail_service()
        instances = await mail.list_instances(user_id)
        readable = [
            row for row in instances
            if str(row.get("status") or "") in ("connected", "active", "authorized")
        ]
        outcomes: List[Dict[str, Any]] = []
        life = ConnectedLifeService(db)
        for row in readable[:3]:
            iid = str(row.get("id") or "")
            if not iid:
                continue
            try:
                result = await life.sync(user_id, iid)
                outcomes.append({
                    "instance_id": iid,
                    "ok": bool(result.get("ok")),
                    "reason": result.get("reason"),
                })
            except Exception as exc:
                logger.info("shipment mailbox refresh soft-fail: %s", type(exc).__name__)
                outcomes.append({"instance_id": iid, "ok": False, "reason": "sync_failed"})
        return {
            "connected": bool(readable),
            "instances": [str(x.get("id") or "") for x in readable[:3]],
            "refresh": outcomes,
        }
    except Exception as exc:
        logger.info("shipment mailbox connection read soft-fail: %s", type(exc).__name__)
        return {"connected": False, "instances": [], "refresh": []}


async def _recent_mail_evidence(db, user_id: str) -> List[Dict[str, Any]]:
    since = (_now() - timedelta(days=30)).isoformat()
    try:
        rows = await db.ingestion_events.find(
            {
                "user_id": user_id,
                "source_record_type": "email_message",
                "ingestion_status": {"$ne": "superseded"},
                "ingested_at": {"$gte": since},
            },
            {
                "_id": 0,
                "external_id": 1,
                "connector_instance_id": 1,
                "normalized_payload": 1,
                "ingested_at": 1,
            },
        ).sort("ingested_at", -1).to_list(24)
    except Exception as exc:
        logger.info("shipment recent mail read soft-fail: %s", type(exc).__name__)
        return []

    from ingestion.reading import plain

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        ref = str(row.get("external_id") or "")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        payload = plain(row.get("normalized_payload"))
        subject = str(payload.get("subject") or "").strip()
        if not subject:
            continue
        out.append({
            "message_ref": ref,
            "thread_ref": str(payload.get("thread_ref") or "")[:200],
            "subject": subject[:240],
            "received_at": payload.get("received_at") or row.get("ingested_at"),
            "sender_relationship": str(payload.get("sender_relationship") or "")[:40],
            "content_available": bool(payload.get("content_available")),
            "source": "gmail",
        })
    return out[:16]


async def _active_situations(db, user_id: str) -> List[Dict[str, Any]]:
    try:
        rows = await db.situations.find(
            {"user_id": user_id, "status": {"$in": ["active", "changed"]}},
            {
                "_id": 0,
                "id": 1,
                "summary": 1,
                "semantic_kind": 1,
                "current_state_summary": 1,
                "expected_outcome_summary": 1,
                "updated_at": 1,
            },
        ).sort("updated_at", -1).to_list(8)
    except Exception:
        return []
    return [{
        "situation_ref": f"situation:{row.get('id')}",
        "summary": str(row.get("summary") or "")[:300],
        "kind": str(row.get("semantic_kind") or "")[:80],
        "current_state": str(row.get("current_state_summary") or "")[:300],
        "expected_outcome": str(row.get("expected_outcome_summary") or "")[:300],
        "updated_at": row.get("updated_at"),
    } for row in rows if row.get("id")]


async def _read_exact_message(
    db, user_id: str, message_ref: str,
) -> Dict[str, Any]:
    """Read one exact owner-scoped message body, audited by GmailReadService."""
    try:
        row = await db.ingestion_events.find_one(
            {
                "user_id": user_id,
                "source_record_type": "email_message",
                "external_id": message_ref,
                "ingestion_status": {"$ne": "superseded"},
            },
            {"_id": 0, "connector_instance_id": 1, "normalized_payload": 1},
            sort=[("ingested_at", -1)],
        )
    except Exception:
        row = None
    if not row:
        return {"status": "not_found"}

    instance_id = str(row.get("connector_instance_id") or "")
    if not instance_id:
        return {"status": "unavailable"}

    try:
        from deps import get_gmail_service
        body = await get_gmail_service().body_for(
            user_id=user_id,
            instance_id=instance_id,
            message_id=message_ref,
        )
    except Exception as exc:
        logger.info("shipment exact mail read soft-fail: %s", type(exc).__name__)
        return {"status": "unavailable"}

    from ingestion.reading import plain
    payload = plain(row.get("normalized_payload"))
    return {
        "status": "ok",
        "message_ref": message_ref,
        "subject": str(payload.get("subject") or "")[:240],
        "received_at": payload.get("received_at"),
        "body_excerpt": str(body or "")[:1200],
        "source": "gmail",
    }


async def get_shipment_status(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    """Evidence surface used by cognition for delivery/shipment questions."""
    db = runtime.get("db")
    user_id = str(runtime.get("user_id") or "")
    if db is None or not user_id:
        return Observation(
            kind="tool", name="get_shipment_status", status="error",
            payload={"status": "unavailable"},
        )

    message_ref = str(arguments.get("message_ref") or "").strip()
    if message_ref:
        exact = await _read_exact_message(db, user_id, message_ref)
        return Observation(
            kind="tool",
            name="get_shipment_status",
            status="ok" if exact.get("status") == "ok" else "partial",
            payload={
                "status": exact.get("status"),
                "exact_message": exact,
                "grounding": "PERSONAL_CONTEXT",
                "live_carrier_tracking": False,
                "instruction": (
                    "Use only what this exact connected message establishes. "
                    "Do not turn 'shipped' into 'out for delivery' or 'delivered'."
                ),
            },
            provenance=[f"mail:{message_ref}"] if exact.get("status") == "ok" else [],
        )

    source = await _refresh_mail(db, user_id)
    messages = await _recent_mail_evidence(db, user_id)
    situations = await _active_situations(db, user_id)
    status = "ok" if source.get("connected") else "requires_connection"
    return Observation(
        kind="tool",
        name="get_shipment_status",
        status="ok" if source.get("connected") else "partial",
        payload={
            "status": status,
            "mail_connected": bool(source.get("connected")),
            "mail_refresh": source.get("refresh") or [],
            "recent_message_candidates": messages,
            "active_situations": situations,
            "grounding": "PERSONAL_CONTEXT",
            "live_carrier_tracking": False,
            "instruction": (
                "These are candidates, not pre-classified shipments. Cognition must decide "
                "which evidence is about the user's package. If a candidate subject is not "
                "enough to establish the current state, call get_shipment_status again with "
                "that exact message_ref to inspect its bounded body."
            ),
        },
        provenance=[f"mail:{m['message_ref']}" for m in messages[:12]],
    )
