"""Direct WhatsApp delivery for user-authorized annual reminders.

An annual reminder is an explicit instruction, not a speculative opportunity
that needs another model to decide whether to interrupt. This channel remains
independently opt-in, source-verified, owner-scoped and Meta-template-gated.

Both the memo scheduler and a bounded recovery scan can admit an event. A
deterministic outbox id makes these attempts one logical notification.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from delivery.models import DeliveryPlan, PushCopy
from memos.delivery_guard import memo_opportunity_current
from opportunities.models import Opportunity
from whatsapp.cloud import CloudConfig

_RECOVER_AGE = timedelta(hours=26)
_RECOVERY_LIMIT = 60
_DIRECT_MAX_AGE = timedelta(hours=2)


def recurring_key(opportunity_id: str) -> str:
    return "recurring_due:" + opportunity_id


def direct_plan(opportunity: Opportunity) -> DeliveryPlan:
    """A bounded view of the reminder, not a new AI decision or an Expo plan."""
    title = str(opportunity.semantic_summary or "").strip()
    why = str(opportunity.why_now or "").strip()
    return DeliveryPlan(
        id="dp_" + hashlib.sha256(recurring_key(opportunity.id).encode()).hexdigest()[:20],
        owner_id=opportunity.owner_id,
        source_type="opportunity",
        source_id=opportunity.id,
        mode="push",
        status="pending",
        sensitivity="private",
        words=PushCopy(
            title=title[:80],
            body=why[:200],
            public_title="",
            public_body="",
        ),
    )


async def enqueue_due_recurring(db, raw: Opportunity | dict) -> bool:
    """Persist one owner-authorized reminder with no dependence on Expo push.

    The annual occurrence must be current and its Memory source still valid.
    Only users who enabled both WhatsApp alerts and detailed content receive
    the full event name; other accounts get no unexpected personal disclosure.
    """
    if not CloudConfig.available():
        return False
    try:
        event = raw if isinstance(raw, Opportunity) else Opportunity.model_validate(raw)
    except (TypeError, ValueError):
        return False
    if (not event.id or not event.owner_id
            or event.status != "active"
            or event.source_context != "recurring_memo"
            or not await memo_opportunity_current(db, event)):
        return False

    link = await db.whatsapp_links.find_one({
        "user_id": event.owner_id,
        "notifications_enabled": True,
        "opted_in_at": {"$exists": True},
        "notifications_detail_enabled": True,
        "details_opted_in_at": {"$exists": True},
    }, {"_id": 0, "phone_hash": 1})
    if not link or not link.get("phone_hash"):
        return False

    from whatsapp.alerts import alert_id, public_copy
    notice = public_copy(direct_plan(event), detailed=True)
    if not notice:
        return False

    key = alert_id(event.owner_id, recurring_key(event.id))
    # Avoid a one-time duplicate when a legacy canonical Delivery plan already
    # generated an alert under the old plan-based id.
    previous = await db.delivery_plans.find_one({
        "owner_id": event.owner_id, "source_type": "opportunity",
        "source_id": event.id,
    }, {"_id": 0, "id": 1})
    if previous and previous.get("id"):
        old_key = alert_id(event.owner_id, str(previous["id"]))
        if old_key != key and await db.whatsapp_alert_outbox.find_one({"_id": old_key}, {"_id": 1}):
            return False

    moment = datetime.now(timezone.utc)
    expires = datetime.fromisoformat(str(event.valid_until or "").replace("Z", "+00:00"))
    if expires.tzinfo is None or expires <= moment:
        return False
    discard_at = moment + timedelta(days=30)
    row = {
        "_id": key,
        "owner_id": event.owner_id,
        "source_kind": "recurring_due",
        "source_id": event.id,
        "phone_hash": link["phone_hash"],
        "copy_enc": CloudConfig.load().encrypt(notice),
        "status": "ready",
        "attempts": 0,
        "next_attempt_at": moment,
        "created_at": moment,
        "valid_until": min(expires.astimezone(timezone.utc), moment + _DIRECT_MAX_AGE),
        "discard_after": discard_at,
    }
    from pymongo.errors import DuplicateKeyError
    try:
        inserted = await db.whatsapp_alert_outbox.update_one(
            {"_id": key}, {"$setOnInsert": row}, upsert=True,
        )
    except DuplicateKeyError:
        return False
    return bool(inserted.upserted_id)


async def reconcile_recent_recurring(db, *, limit: int = _RECOVERY_LIMIT) -> int:
    """Recover today's due reminders missed by an older build or a restart.

    Query only recent current opportunities; never send yesterday's event
    or replay a settled outbox row. Every individual event rechecks Memory.
    """
    if not CloudConfig.available():
        return 0
    cutoff = (datetime.now(timezone.utc) - _RECOVER_AGE).isoformat()
    cursor = db.opportunities.find(
        {"source_context": "recurring_memo", "status": "active",
         "created_at": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("created_at", -1).limit(max(1, min(int(limit), _RECOVERY_LIMIT)))
    inserted = 0
    async for row in cursor:
        if await enqueue_due_recurring(db, row):
            inserted += 1
    return inserted

async def retry_failed_recurring_once(db, owner_id: str) -> dict:
    """Owner-triggered, one-time repeat of a signed FAILED template receipt.

    Never retry an unknown/accepted result. Retain the original failed row
    unchanged for diagnosis; a separate deterministic row preserves both
    attempts and blocks duplicate taps across workers.
    """
    from pymongo.errors import DuplicateKeyError
    from whatsapp.alerts import alert_id, public_copy, template_settings
    from whatsapp.template_approval import approval_status

    if not CloudConfig.available() or not template_settings():
        return {"queued": False, "reason": "template_not_ready"}
    original = await db.whatsapp_alert_outbox.find_one(
        {"owner_id": owner_id, "source_kind": "recurring_due",
         "status": "failed", "kind": "approved_template",
         "meta_status_at": {"$exists": True}},
        {"_id": 1, "source_id": 1, "phone_hash": 1, "created_at": 1},
        sort=[("created_at", -1)],
    )
    if not original:
        return {"queued": False, "reason": "no_confirmed_failed_reminder"}

    raw = await db.opportunities.find_one(
        {"owner_id": owner_id, "id": original.get("source_id"),
         "status": "active", "source_context": "recurring_memo"}, {"_id": 0},
    )
    if not raw:
        return {"queued": False, "reason": "reminder_not_current"}
    try:
        event = Opportunity.model_validate(raw)
    except (TypeError, ValueError):
        return {"queued": False, "reason": "reminder_not_current"}
    if not await memo_opportunity_current(db, event):
        return {"queued": False, "reason": "reminder_not_current"}

    link = await db.whatsapp_links.find_one({
        "user_id": owner_id, "phone_hash": original.get("phone_hash"),
        "notifications_enabled": True, "opted_in_at": {"$exists": True},
        "notifications_detail_enabled": True,
        "details_opted_in_at": {"$exists": True},
    }, {"_id": 0, "phone_hash": 1})
    if not link:
        return {"queued": False, "reason": "consent_or_link_changed"}

    cfg = CloudConfig.load()
    if await approval_status(cfg, use_cache=False) != "approved_dynamic":
        return {"queued": False, "reason": "template_not_approved"}
    text = public_copy(direct_plan(event), detailed=True)
    if not text:
        return {"queued": False, "reason": "reminder_without_valid_copy"}

    now = datetime.now(timezone.utc)
    try:
        expires = datetime.fromisoformat(
            str(event.valid_until or "").replace("Z", "+00:00")
        )
    except ValueError:
        return {"queued": False, "reason": "reminder_not_current"}
    if expires.tzinfo is None or expires <= now:
        return {"queued": False, "reason": "reminder_not_current"}

    attempt_id = alert_id(owner_id, recurring_key(event.id) + ":manual_retry_once")
    row = {
        "_id": attempt_id,
        "owner_id": owner_id,
        "source_kind": "recurring_due",
        "source_id": event.id,
        "retry_kind": "owner_confirmed_failed_once",
        # Preserve the original failure as its own row without copying WAMID.
        "phone_hash": link["phone_hash"],
        "copy_enc": cfg.encrypt(text),
        "force_template": True,
        "status": "ready",
        "attempts": 0,
        "next_attempt_at": now,
        "created_at": now,
        "valid_until": min(expires.astimezone(timezone.utc), now + _DIRECT_MAX_AGE),
        "discard_after": now + timedelta(days=30),
    }
    try:
        inserted = await db.whatsapp_alert_outbox.update_one(
            {"_id": attempt_id}, {"$setOnInsert": row}, upsert=True,
        )
    except DuplicateKeyError:
        return {"queued": False, "reason": "retry_already_requested"}
    if not inserted.upserted_id:
        return {"queued": False, "reason": "retry_already_requested"}
    return {"queued": True, "status": "queued"}
