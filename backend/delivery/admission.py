"""Durable, bounded delivery review for changed opportunity records.

The scan result only accelerates this work. The opportunity itself carries the
due time, lease and revision fence, so batch limits and worker restarts do not
silently discard a concern before delivery has considered it.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

COLLECTION = "opportunities"
LEASE_SECONDS = 120
TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
logger = logging.getLogger(__name__)


def _expiry_state(row, moment):
    raw = row.get("valid_until")
    if not raw:
        return ""
    try:
        until = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return "invalid_expiry"
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return "expired" if until <= moment else ""


async def drain(db, *, owner_id=None, now=None, limit=2) -> int:
    from delivery.service import DeliveryService

    moment = now or datetime.now(timezone.utc)
    stamp = moment.isoformat()
    handled = 0
    for _ in range(limit):
        query = {
            "status": {"$in": ["active", "dismissed", "suppressed", "resolved", "expired"]},
            "delivery_review_due": {"$type": "string", "$lte": stamp},
            "$or": [{"delivery_review_lease_until": {"$exists": False}},
                    {"delivery_review_lease_until": {"$lte": stamp}}],
        }
        if owner_id is not None:
            query["owner_id"] = owner_id
        token = uuid.uuid4().hex
        row = await db[COLLECTION].find_one_and_update(
            query,
            {"$set": {"delivery_review_token": token,
                      "delivery_review_lease_until": (moment + timedelta(seconds=LEASE_SECONDS)).isoformat()},
             "$inc": {"delivery_review_attempts": 1}},
            sort=[("delivery_review_due", 1), ("id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if row is None:
            break

        outcome = "unavailable"
        error_kind = ""
        try:
            service = DeliveryService(db)
            expiry_state = _expiry_state(row, moment)
            if row["status"] != "active":
                await service.cancel_for_opportunity(
                    row["owner_id"], row["id"], reason="la questione non è più aperta"
                )
                outcome = "closed"
            elif expiry_state == "expired":
                await service.cancel_for_opportunity(
                    row["owner_id"], row["id"], reason="il momento utile è passato"
                )
                outcome = "expired"
            elif expiry_state == "invalid_expiry":
                error_kind = "invalid_valid_until"
            else:
                result = await asyncio.wait_for(
                    service.evaluate(row["owner_id"], row["id"]), TIMEOUT_SECONDS
                )
                if not result.unavailable:
                    outcome = result.mode or result.blocked_by or "in_app"
        except Exception as exc:
            # The due field stays on the record; an expired lease is reclaimable.
            error_kind = type(exc).__name__

        attempts = int(row["delivery_review_attempts"])
        due = None
        if outcome == "unavailable" and attempts < MAX_ATTEMPTS:
            due = (moment + timedelta(seconds=60 * (5 ** (attempts - 1)))).isoformat()
        state = "pending" if due else ("paused" if outcome == "unavailable" else "settled")
        fence = {"id": row["id"], "owner_id": row["owner_id"],
                 "delivery_review_token": token,
                 "delivery_review_revision": row["delivery_review_revision"]}
        await db[COLLECTION].update_one(fence, {"$set": {
            "delivery_review_due": due,
            "delivery_review_state": state,
            "delivery_review_outcome": outcome,
            "delivery_review_error_kind": error_kind,
            "delivery_review_finished_at": datetime.now(timezone.utc).isoformat(),
        }})
        # Do not remove another worker's lease; a new source revision stays due.
        await db[COLLECTION].update_one(
            {"id": row["id"], "owner_id": row["owner_id"], "delivery_review_token": token},
            {"$unset": {"delivery_review_token": "", "delivery_review_lease_until": ""}},
        )
        logger.info("delivery_admission outcome=%s state=%s attempt=%d", outcome, state, attempts)
        handled += 1
    return handled

async def drain_with_receipts(db) -> int:
    """Run bounded admission and check Expo receipts without adding a lane.

    This module owns the provider boundary. Ambient only schedules a generic
    delivery pass and cannot gain direct access to notification transport.
    """
    handled = await drain(db)
    # Reconstruct a technical retry alarm if a process was killed between
    # writing a held delivery plan and scheduling its wake. The actual
    # decision and send still belong to the Ambient delivery recheck.
    try:
        from delivery.transport_retry import recover_unscheduled_retries

        await recover_unscheduled_retries(db)
    except Exception as exc:
        logger.info("delivery retry recovery deferred: %s", type(exc).__name__)
    from ambient.push import ExpoNotificationProvider
    from delivery.provider import get_provider

    if isinstance(get_provider(), ExpoNotificationProvider):
        from delivery.expo_receipts import ExpoReceiptAudit

        try:
            await ExpoReceiptAudit(db).run_due()
        except Exception as exc:
            # Receipt claims remain durable for another pass.
            logger.info("expo receipt audit deferred: %s", type(exc).__name__)
    return handled
