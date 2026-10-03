"""Immutable outbound email drafts for authority-safe sending."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any, Dict, Optional, Tuple

COLLECTION = "agent_outbound_drafts"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_recipient(raw: str) -> str:
    _, address = parseaddr(str(raw or "").strip())
    address = address.strip().lower()
    if (
        not address or "@" not in address or "\n" in address or "\r" in address
        or "," in address
    ):
        return ""
    return address[:254]


def _clean_subject(raw: str) -> str:
    return re.sub(r"[\r\n]+", " ", str(raw or "")).strip()[:240]


def _hash(to: str, subject: str, body: str) -> str:
    raw = "\0".join([to, subject, body])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def freeze_for_send(
    db, owner_id: str, goal, step
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Freeze exactly what a mail.send step would transmit.

    The draft is content-addressed and written only once. A later rewrite of
    the goal's prepared text creates another hash and therefore another
    authority fingerprint; an earlier approval cannot follow the changed text.
    """
    params = dict(step.parameters or {})
    to = _clean_recipient(params.get("to") or "")
    subject = _clean_subject(params.get("subject") or "")
    body = str(params.get("body") or "").strip()
    if not body:
        body = str(getattr(goal, "prepared_text", "") or "").strip()
    if not to:
        return None, "mail_recipient_missing"
    if not subject:
        return None, "mail_subject_missing"
    if not body:
        return None, "mail_draft_missing"
    if len(body) > 12000:
        return None, "mail_draft_too_large"

    digest = _hash(to, subject, body)
    draft_id = f"maildraft_{digest[:24]}"
    existing = await db[COLLECTION].find_one(
        {"id": draft_id, "owner_id": owner_id}, {"_id": 0}
    )
    if existing:
        if (
            str(existing.get("content_hash") or "") != digest
            or str(existing.get("to") or "") != to
            or str(existing.get("subject") or "") != subject
            or str(existing.get("body") or "") != body
        ):
            return None, "mail_draft_hash_collision"
        return existing, ""

    doc = {
        "id": draft_id,
        "owner_id": owner_id,
        "goal_id": str(getattr(goal, "id", "") or ""),
        "step_id": str(getattr(step, "id", "") or ""),
        "to": to,
        "subject": subject,
        "body": body,
        "content_hash": digest,
        "source_refs": list(getattr(goal, "prepared_sources", None) or [])[:12],
        "status": "prepared",
        "created_at": _now(),
    }
    try:
        await db[COLLECTION].insert_one(dict(doc))
    except Exception:
        # Content addressing makes a concurrent insert harmless. Re-read and
        # validate instead of inventing a second draft id.
        existing = await db[COLLECTION].find_one(
            {"id": draft_id, "owner_id": owner_id}, {"_id": 0}
        )
        if not existing:
            raise
        if (
            str(existing.get("content_hash") or "") != digest
            or str(existing.get("body") or "") != body
        ):
            return None, "mail_draft_hash_collision"
        return existing, ""
    return doc, ""


async def load_frozen(
    db, owner_id: str, *, draft_id: str, expected_hash: str = ""
) -> Tuple[Optional[Dict[str, Any]], str]:
    row = await db[COLLECTION].find_one(
        {"id": str(draft_id or ""), "owner_id": owner_id}, {"_id": 0}
    )
    if not row:
        return None, "mail_draft_not_found"
    digest = str(row.get("content_hash") or "")
    recomputed = _hash(
        str(row.get("to") or ""),
        str(row.get("subject") or ""),
        str(row.get("body") or ""),
    )
    if not digest or digest != recomputed:
        return None, "mail_draft_changed"
    if expected_hash and digest != str(expected_hash):
        return None, "mail_draft_changed"
    if row.get("status") not in ("prepared", "sent"):
        return None, "mail_draft_unavailable"
    return row, ""
