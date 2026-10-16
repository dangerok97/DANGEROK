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
    """Allow only an explicitly scoped recurring reminder template.

    A general-purpose Utility slot for arbitrary AI notices would overclaim
    the context Meta reviewed. New scopes require their own verified routing.
    """
    from whatsapp.template_provisioning import (
        TEMPLATE_NAME, TEMPLATE_LANGUAGE, TEMPLATE_SCOPE,
    )
    name = (os.environ.get("WHATSAPP_ALERT_TEMPLATE_NAME") or "").strip()
    language = (os.environ.get("WHATSAPP_ALERT_TEMPLATE_LANGUAGE") or "it").strip()
    scope = (os.environ.get("WHATSAPP_ALERT_TEMPLATE_SCOPE") or "").strip()
    if (name == TEMPLATE_NAME and language == TEMPLATE_LANGUAGE
            and scope == TEMPLATE_SCOPE
            and _TEMPLATE_NAME.fullmatch(name)
            and _TEMPLATE_LANGUAGE.fullmatch(language)):
        return name, language
    return None


def template_scope_matches(plan, subject) -> bool:
    """The only approved category is a *stored user-requested* recurring memo."""
    return (
        getattr(plan, "source_type", "") == "opportunity"
        and getattr(subject, "status", "") == "active"
        and getattr(subject, "source_context", "") == "recurring_memo"
    )


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
    if not link or not link.get("phone_hash") or not link.get("phone_enc"):
        return False
    if in_service_window(link):
        return True
    # A configured string is not evidence of Meta's template approval.
    from whatsapp.template_approval import approval_status

    return await approval_status() == "approved_dynamic"


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
            {"$set": {"notifications_enabled": False, "opted_out_at": moment,
                      "notifications_detail_enabled": False},
             "$unset": {"opted_in_at": "", "opt_in_scope": "", "opt_in_source": "",
                        "details_opted_in_at": "", "details_opt_in_source": ""}},
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


async def set_detail_preference(db, user_id: str, enabled: bool) -> dict:
    """Separate, explicit informed consent to expose expanded copy to Meta/WhatsApp.

    The normal alert opt-in alone cannot authorize private expanded copy. The
    owner may opt out independently; disabling all alerts also clears this.
    """
    link = await db.whatsapp_links.find_one(
        {"user_id": user_id}, {"_id": 0, "phone_hash": 1,
                              "notifications_enabled": 1, "opted_in_at": 1}
    )
    if not link:
        raise ValueError("whatsapp_not_linked")
    if enabled and not (link.get("notifications_enabled") is True
                        and isinstance(link.get("opted_in_at"), datetime)):
        raise ValueError("whatsapp_alerts_not_enabled")
    moment = utcnow()
    update = {"$set": {"notifications_detail_enabled": bool(enabled)}}
    if enabled:
        update["$set"].update({
            "details_opted_in_at": moment,
            "details_opt_in_source": "authenticated_ora_app",
        })
    else:
        update["$unset"] = {
            "details_opted_in_at": "", "details_opt_in_source": "",
        }
    match = {"user_id": user_id, "phone_hash": link["phone_hash"]}
    if enabled:
        # Consent may be revoked concurrently with this request.
        match.update({"notifications_enabled": True,
                      "opted_in_at": {"$exists": True}})
    result = await db.whatsapp_links.update_one(match, update)
    if result.matched_count != 1:
        raise ValueError("whatsapp_alerts_not_enabled" if enabled else "whatsapp_not_linked")
    return {"notifications_detail_enabled": bool(enabled)}


_GENERIC_COPY = frozenset({
    "ora ha un aggiornamento importante per te",
    "un aggiornamento importante", "aggiornamento importante",
    "aggiornamento", "una novità per te",
    "avviso riservato", "avviso riservato di ora", "un avviso riservato",
    "apri ora per i dettagli", "apri ora per la situazione",
    "apri ora per saperne di più", "apri ora per maggiori dettagli",
    "c'è un aggiornamento importante",
    "hai un aggiornamento importante",
})


def _meaningful_fragment(value: str) -> str:
    """Never mistake a generic 'open the app' instruction for an actual fact."""
    clean = " ".join(str(value or "").split()).strip(" .!…")
    if not clean:
        return ""
    low = clean.casefold().replace("’", "'")
    if low in _GENERIC_COPY or low.startswith(
        ("apri ora per ", "consulta ora per ", "vai nell'app per ")
    ):
        return ""
    return clean


def public_copy(plan, *, detailed: bool = False) -> str | None:
    """Send informative, source-governed plan copy; never invent the missing fact.

    Public title/body were authored for a lock screen, and may be used even
    when the whole plan is classified as personal. Expanded title/body require
    separate opt-in; no raw subject/mail/bank data is copied into this channel.
    """
    words = getattr(plan, "words", None)
    if words is None:
        return None
    # "private" is stricter than "personal". Even words labelled public by
    # a model cannot override the private classification by default.
    if getattr(plan, "sensitivity", "ordinary") == "private" and not detailed:
        return None
    title = _meaningful_fragment(
        getattr(words, "title", "") if detailed else getattr(words, "public_title", "")
    )
    body = _meaningful_fragment(
        getattr(words, "body", "") if detailed else getattr(words, "public_body", "")
    )
    if detailed:
        title = title or _meaningful_fragment(getattr(words, "public_title", ""))
        body = body or _meaningful_fragment(getattr(words, "public_body", ""))
    if not title and not body:
        return None
    if title and body and title.casefold() == body.casefold():
        body = ""
    # Never invent a date, amount, action, assessment, or source label here.
    content = "\n".join(x for x in (title, body) if x)
    return ("*ORA — aggiornamento*\n" + content)[:500]


def recurring_template_detail(copy: str) -> str | None:
    """One truthful bounded Meta BODY parameter; fixed template supplies context.

    Remove only ORA's presentational heading, never infer a date or edit the
    verified fact. This also prevents a missing/invalid value from being
    mislabeled as an uncertain network send.
    """
    if not isinstance(copy, str):
        return None
    parts = [part.strip().strip("*. ").strip() for part in copy.splitlines()]
    parts = [part for part in parts if part]
    if parts and parts[0] == "ORA — aggiornamento":
        parts.pop(0)
    detail = ". ".join(parts).strip()[:450]
    if (not detail or "{{" in detail or "}}" in detail
            or any(ord(ch) < 32 for ch in detail)):
        return None
    return detail


def alert_id(user_id: str, plan_id: str) -> str:
    return hashlib.sha256(f"ora-wa-alert-v1:{user_id}:{plan_id}".encode()).hexdigest()


async def enqueue(db, user_id: str, plan) -> bool:
    """Called only after the canonical delivery service verified the source."""
    if getattr(plan, "owner_id", "") != user_id or getattr(plan, "mode", "") != "push":
        return False
    link = await db.whatsapp_links.find_one(
        {"user_id": user_id, "notifications_enabled": True,
         "opted_in_at": {"$exists": True}},
        {"_id": 0, "phone_hash": 1, "last_inbound_at": 1,
         "notifications_detail_enabled": 1},
    )
    if not link:
        return False
    recurring = False
    if getattr(plan, "source_type", "") == "opportunity":
        known = await db.opportunities.find_one(
            {"owner_id": user_id, "id": plan.source_id,
             "status": "active", "source_context": "recurring_memo"},
            {"_id": 1},
        )
        recurring = bool(known)
    if not in_service_window(link) and not recurring:
        # Only a user-requested annual reminder is covered by this approved
        # Utility template. Other topics remain inside the service window.
        return False
    # Only after source/scope admission check may we spend a Meta approval
    # read. Unsupported categories must not even query provider readiness.
    if not await may_notify(db, user_id):
        return False
    copy = public_copy(plan, detailed=link.get("notifications_detail_enabled") is True)
    if not copy:
        # A buzz without a usable fact is not a proactive notification.
        return False
    moment = utcnow()
    row = {
        "_id": alert_id(
            user_id,
            "recurring_due:" + str(plan.source_id) if recurring else plan.id,
        ),
        "owner_id": user_id, "plan_id": plan.id,
        "phone_hash": link["phone_hash"],
        # Encrypt even the public-facing copy at rest; decrypt only at the
        # Meta provider boundary, as already done for WhatsApp inbox text.
        "copy_enc": CloudConfig.load().encrypt(copy),
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
        self._last_recurring_scan = None

    async def _claim(self):
        moment = utcnow()
        # Recover a reminder that the calendar had already raised, even if
        # the old backend never enqueued WhatsApp or restarted mid-handoff.
        # No AI decision, no new recurrence, and a stable outbox dedupe key.
        if (self._last_recurring_scan is None
                or moment - self._last_recurring_scan >= timedelta(seconds=60)):
            self._last_recurring_scan = moment
            from whatsapp.recurring_delivery import reconcile_recent_recurring
            try:
                await reconcile_recent_recurring(self.db)
            except Exception as exc:
                log.warning("WhatsApp recurring admission failed: category=%s",
                            type(exc).__name__)
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

        if item.get("source_kind") == "recurring_due":
            # Annual Memo due is itself the user's explicit request, not an
            # LLM-selected Expo notification. Reconstruct a bounded plan view
            # only for source/consent validation; do not fabricate a push plan.
            from opportunities.models import Opportunity
            from whatsapp.recurring_delivery import direct_plan

            row = await self.db.opportunities.find_one(
                {"owner_id": owner, "id": item.get("source_id"),
                 "status": "active", "source_context": "recurring_memo"},
                {"_id": 0},
            )
            if not row:
                await cancel(self.db, item, "recurring_source_inactive")
                return True
            plan = direct_plan(Opportunity.model_validate(row))
        else:
            row = await self.db.delivery_plans.find_one(
                {"owner_id": owner, "id": item.get("plan_id")}, {"_id": 0}
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
        template_approval = None
        if not in_service_window(link, moment):
            if not template_scope_matches(plan, subject):
                await cancel(self.db, item, "template_scope_unsupported")
                return True
            from whatsapp.template_approval import approval_status

            template_approval = await approval_status(self.config)
            if template_approval != "approved_dynamic":
                await self.db.whatsapp_alert_outbox.update_one(
                    {"_id": item["_id"], "status": "sending"},
                    {"$set": {"status": "held_template",
                              "next_attempt_at": moment + timedelta(minutes=15),
                              "failure_code": "template_" + template_approval}},
                )
                return True

        # Consent can be revoked while a verification is being performed.
        latest = await self.db.whatsapp_links.find_one(
            {"user_id": owner, "phone_hash": item["phone_hash"],
             "notifications_enabled": True, "opted_in_at": {"$exists": True}},
            {"_id": 0, "phone_enc": 1, "last_inbound_at": 1,
             "notifications_detail_enabled": 1},
        )
        if not latest or latest.get("phone_enc") != link["phone_enc"]:
            await cancel(self.db, item, "consent_changed")
            return True
        copy = public_copy(plan, detailed=latest.get("notifications_detail_enabled") is True)
        if not copy:
            await cancel(self.db, item, "no_informative_copy")
            return True
        fresh_window = in_service_window(latest)
        if not fresh_window and not template:
            await cancel(self.db, item, "customer_window_closed")
            return True
        if not fresh_window and template_approval != "approved_dynamic":
            # The safe-side branch above must have established approval.
            await cancel(self.db, item, "template_not_verified")
            return True
        detail = recurring_template_detail(copy) if not fresh_window else None
        if not fresh_window and not detail:
            await cancel(self.db, item, "template_detail_invalid")
            return True
        recipient = self.config.decrypt(latest["phone_enc"])
        try:
            wamid = await self.config.send_proactive(
                recipient, message=copy if fresh_window else "",
                template=None if fresh_window else (*template, detail),
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
    values = {"status": new, "meta_status_at": utcnow()}
    if new == "failed":
        code = item.get("error_code")
        # Never persist Meta's freeform error description or phone number.
        values["failure_code"] = (
            f"meta_{code}" if type(code) is int and 0 <= code <= 9999999
            else "meta_delivery_failed"
        )
    result = await db.whatsapp_alert_outbox.update_one(
        {"wamid": wamid, "phone_hash": config.fingerprint("phone", number),
         "status": {"$in": _ALLOWED_PREVIOUS[new]}},
        {"$set": values},
    )
    return bool(result.modified_count)
