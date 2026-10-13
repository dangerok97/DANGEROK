"""Notification channel for the existing ORA alert decisions."""
from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from whatsapp.cloud import CloudConfig, CloudSendError

log = logging.getLogger("ora.whatsapp.alerts")
MAX_NOTICE_AGE = timedelta(hours=2)
SERVICE_WINDOW = timedelta(hours=23, minutes=30)
_TEMPLATE_NAME = re.compile(r"[a-z][a-z0-9_]{0,120}\Z")
_TEMPLATE_LANGUAGE = re.compile(r"[a-z]{2}(?:_[A-Z]{2})?\Z")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def template_settings() -> tuple[str, str] | None:
    name = (os.environ.get("WHATSAPP_ALERT_TEMPLATE_NAME") or "").strip()
    language = (os.environ.get("WHATSAPP_ALERT_TEMPLATE_LANGUAGE") or "it").strip()
    if _TEMPLATE_NAME.fullmatch(name) and _TEMPLATE_LANGUAGE.fullmatch(language):
        return name, language
    return None


def in_service_window(link: dict, now: datetime | None = None) -> bool:
    seen = link.get("last_inbound_at")
    if not isinstance(seen, datetime):
        return False
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    age = (now or utcnow()) - seen
    return timedelta(0) <= age < SERVICE_WINDOW


async def may_notify(db, user_id: str) -> bool:
    if not CloudConfig.available():
        return False
    link = await db.whatsapp_links.find_one(
        {"user_id": user_id, "notifications_enabled": True,
         "opted_in_at": {"$exists": True}},
        {"_id": 0, "last_inbound_at": 1, "phone_hash": 1, "phone_enc": 1},
    )
    return bool(
        link and link.get("phone_hash") and link.get("phone_enc")
        and (in_service_window(link) or template_settings())
    )


async def ensure_indexes(db) -> None:
    await db.whatsapp_alert_outbox.create_index(
        [("status", 1), ("next_attempt_at", 1), ("created_at", 1)]
    )
    await db.whatsapp_alert_outbox.create_index(
        [("owner_id", 1), ("created_at", -1)]
    )
    await db.whatsapp_alert_outbox.create_index("wamid", unique=True, sparse=True)
    await db.whatsapp_alert_outbox.create_index("discard_after", expireAfterSeconds=0)


async def set_opt_in(db, user_id: str, enabled: bool) -> dict:
    link = await db.whatsapp_links.find_one(
        {"user_id": user_id}, {"_id": 0, "phone_hash": 1}
    )
    if not link:
        raise ValueError("whatsapp_not_linked")
    moment = utcnow()
    if enabled:
        await db.whatsapp_links.update_one(
            {"user_id": user_id, "phone_hash": link["phone_hash"]},
            {"$set": {
                "notifications_enabled": True,
                "opted_in_at": moment,
                "opt_in_scope": "important_ora_updates",
                "opt_in_source": "authenticated_ora_app",
            }},
        )
    else:
        await db.whatsapp_links.update_one(
            {"user_id": user_id, "phone_hash": link["phone_hash"]},
            {"$set": {"notifications_enabled": False, "opted_out_at": moment},
             "$unset": {"opted_in_at": "", "opt_in_scope": "", "opt_in_source": ""}},
        )
        await db.whatsapp_alert_outbox.update_many(
            {"owner_id": user_id, "status": {"$in": ["ready", "held_template"]}},
            {"$set": {"status": "cancelled", "finished_at": moment,
                      "failure_code": "consent_revoked"}},
        )
    return {
        "notifications_enabled": bool(enabled),
        "template_configured": bool(template_settings()),
    }


def public_copy(plan) -> str:
    """Read only expressly public lock-screen copy, never expanded details."""
    if str(getattr(plan, "sensitivity", "ordinary")) != "ordinary":
        return "ORA ha un aggiornamento importante per te. Apri ORA per i dettagli."
    title = str(getattr(plan.words, "public_title", "") or "").strip()
    body = str(getattr(plan.words, "public_body", "") or "").strip()
    if not title and not body:
        return "ORA ha un aggiornamento importante per te. Apri ORA per i dettagli."
    return ". ".join(x.rstrip(" .") for x in (title, body) if x)[:500]


def alert_id(user_id: str, plan_id: str) -> str:
    return hashlib.sha256(f"ora-wa-alert-v1:{user_id}:{plan_id}".encode()).hexdigest()


async def enqueue(db, user_id: str, plan) -> bool:
    """Called only after the canonical delivery service verified the source."""
    if getattr(plan, "owner_id", "") != user_id or getattr(plan, "mode", "") != "push":
        return False
    if not await may_notify(db, user_id):
        return False
    link = await db.whatsapp_links.find_one(
        {"user_id": user_id, "notifications_enabled": True,
         "opted_in_at": {"$exists": True}},
        {"_id": 0, "phone_hash": 1},
    )
    if not link:
        return False
    moment = utcnow()
    row = {
        "_id": alert_id(user_id, plan.id),
        "owner_id": user_id, "plan_id": plan.id,
        "phone_hash": link["phone_hash"],
        "copy": public_copy(plan),
        "status": "ready", "attempts": 0,
        "next_attempt_at": moment, "created_at": moment,
        "valid_until": moment + MAX_NOTICE_AGE,
        "discard_after": moment + timedelta(days=30),
    }
    try:
        result = await db.whatsapp_alert_outbox.update_one(
            {"_id": row["_id"]}, {"$setOnInsert": row}, upsert=True
        )
        return bool(result.upserted_id)
    except DuplicateKeyError:
        return False


async def cancel(db, item: dict, reason: str) -> None:
    await db.whatsapp_alert_outbox.update_one(
        {"_id": item["_id"], "status": "sending"},
        {"$set": {"status": "cancelled", "failure_code": reason,
                  "finished_at": utcnow()}},
    )
