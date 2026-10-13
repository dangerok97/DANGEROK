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


def as_utc(value: datetime | None) -> datetime | None:
    """Mongo returns UTC-naive datetimes by default even for aware writes."""
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


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


class AlertWorker:
    """One bounded queue consumer. Do not retry an uncertain provider send."""

    def __init__(self, db, config: CloudConfig | None = None):
        self.db = db
        self.config = config or CloudConfig.load()

    async def _claim(self):
        moment = utcnow()
        return await self.db.whatsapp_alert_outbox.find_one_and_update(
            {"status": {"$in": ["ready", "held_template"]},
             "next_attempt_at": {"$lte": moment}},
            {"$set": {"status": "sending", "started_at": moment},
             "$inc": {"attempts": 1}},
            sort=[("created_at", 1)], return_document=ReturnDocument.AFTER,
        )

    async def process_one(self) -> bool:
        item = await self._claim()
        if not item:
            return False
        owner = item["owner_id"]
        moment = utcnow()
        expires = as_utc(item.get("valid_until"))
        if expires is None or expires <= moment:
            await cancel(self.db, item, "stale")
            return True

        link = await self.db.whatsapp_links.find_one(
            {"user_id": owner, "phone_hash": item["phone_hash"],
             "notifications_enabled": True, "opted_in_at": {"$exists": True}},
            {"_id": 0, "phone_enc": 1, "last_inbound_at": 1},
        )
        if not link or not link.get("phone_enc"):
            await cancel(self.db, item, "unlinked_or_opted_out")
            return True

        from delivery.models import DeliveryPlan
        from delivery.service import DeliveryService

        row = await self.db.delivery_plans.find_one(
            {"owner_id": owner, "id": item["plan_id"]}, {"_id": 0}
        )
        if not row or row.get("status") in ("cancelled", "expired"):
            await cancel(self.db, item, "plan_inactive")
            return True
        plan = DeliveryPlan.model_validate(row)
        delivery = DeliveryService(self.db)
        try:
            subject = await delivery._current_subject_for_plan(owner, plan)
            muted = await delivery._muted(owner, plan.source_id)
        except Exception:
            # Unknown validity must never turn into a sent notification.
            await self.db.whatsapp_alert_outbox.update_one(
                {"_id": item["_id"], "status": "sending"},
                {"$set": {"status": "held_source",
                          "failure_code": "source_verification_unavailable"}},
            )
            return True
        if subject is None or muted:
            await cancel(self.db, item, "source_closed_or_muted")
            return True

        template = template_settings()
        if not in_service_window(link, moment) and not template:
            await self.db.whatsapp_alert_outbox.update_one(
                {"_id": item["_id"], "status": "sending"},
                {"$set": {"status": "held_template",
                          "next_attempt_at": moment + timedelta(minutes=15),
                          "failure_code": "approved_template_missing"}},
            )
            return True

        # Consent can be revoked while a verification is being performed.
        latest = await self.db.whatsapp_links.find_one(
            {"user_id": owner, "phone_hash": item["phone_hash"],
             "notifications_enabled": True, "opted_in_at": {"$exists": True}},
            {"_id": 0, "phone_enc": 1, "last_inbound_at": 1},
        )
        if not latest or latest.get("phone_enc") != link["phone_enc"]:
            await cancel(self.db, item, "consent_changed")
            return True
        fresh_window = in_service_window(latest)
        if not fresh_window and not template:
            await cancel(self.db, item, "customer_window_closed")
            return True
        recipient = self.config.decrypt(latest["phone_enc"])
        try:
            wamid = await self.config.send_proactive(
                recipient, message=item["copy"] if fresh_window else "",
                template=None if fresh_window else template,
            )
        except CloudSendError as exc:
            if exc.status == 429 and item.get("attempts", 0) < 3:
                await self.db.whatsapp_alert_outbox.update_one(
                    {"_id": item["_id"], "status": "sending"},
                    {"$set": {"status": "ready",
                              "next_attempt_at": moment + timedelta(minutes=5),
                              "failure_code": "rate_limited"}},
                )
            elif 400 <= exc.status < 500:
                await self.db.whatsapp_alert_outbox.update_one(
                    {"_id": item["_id"], "status": "sending"},
                    {"$set": {"status": "failed",
                              "failure_code": f"meta_{exc.code or exc.status}",
                              "finished_at": utcnow()}},
                )
            else:
                await self.db.whatsapp_alert_outbox.update_one(
                    {"_id": item["_id"], "status": "sending"},
                    {"$set": {"status": "acceptance_unknown",
                              "failure_code": "ambiguous_provider_result"}},
                )
            return True
        except Exception as exc:
            log.warning("WhatsApp alert acceptance unknown: category=%s", type(exc).__name__)
            await self.db.whatsapp_alert_outbox.update_one(
                {"_id": item["_id"], "status": "sending"},
                {"$set": {"status": "acceptance_unknown",
                          "failure_code": "transport_uncertain"}},
            )
            return True

        await self.db.whatsapp_alert_outbox.update_one(
            {"_id": item["_id"], "status": "sending"},
            {"$set": {"status": "accepted", "wamid": wamid,
                      "accepted_at": utcnow(),
                      "kind": "text" if fresh_window else "approved_template",
                      "failure_code": None}},
        )
        return True


_ALLOWED_PREVIOUS = {
    "sent": ["accepted", "sent"],
    "delivered": ["accepted", "sent", "delivered"],
    "read": ["accepted", "sent", "delivered", "read"],
    "failed": ["accepted", "sent", "failed"],
}


async def record_status(db, config: CloudConfig, item: dict) -> bool:
    """Observe Meta's signed receipt. Acceptance is not successful delivery."""
    new = item.get("status")
    wamid = item.get("id")
    number = item.get("recipient_id")
    if new not in _ALLOWED_PREVIOUS:
        return False
    if not isinstance(wamid, str) or not wamid.startswith("wamid.") or len(wamid) > 220:
        return False
    if not isinstance(number, str) or not re.fullmatch(r"[1-9][0-9]{6,14}", number):
        return False
    result = await db.whatsapp_alert_outbox.update_one(
        {"wamid": wamid, "phone_hash": config.fingerprint("phone", number),
         "status": {"$in": _ALLOWED_PREVIOUS[new]}},
        {"$set": {"status": new, "meta_status_at": utcnow()}},
    )
    return bool(result.modified_count)
