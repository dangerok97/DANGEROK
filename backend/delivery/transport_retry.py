"""Bounded, durable retry alarms for unambiguously rejected push requests.

No provider, AI decision or actual send is reached from this module. A failed
Expo request is retried ONLY if transport explicitly proves zero acceptance
(e.g. a full HTTP 429 response), never after a timeout, missing tickets or
partial success. Every alarm runs through the existing Ambient delivery
recheck, so source, permissions and user preferences are re-evaluated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional

from ambient.models import AmbientWake
from ambient.repository import AmbientRepository

logger = logging.getLogger("ora.delivery.transport_retry")
MAX_TRANSPORT_RETRIES = 3
INITIAL_RETRY_SECONDS = 300
MAX_RETRY_SECONDS = 1200
MAX_RECOVERY_BATCH = 8


def backoff_seconds(attempt: int) -> int:
    """A small bounded sequence: 5, 10, 20 minutes."""
    attempt = max(1, min(int(attempt), MAX_TRANSPORT_RETRIES))
    return min(MAX_RETRY_SECONDS, INITIAL_RETRY_SECONDS * (2 ** (attempt - 1)))


def next_retry_time(plan, *, now: Optional[datetime] = None) -> Optional[str]:
    """Return a retry moment only while the original delivery window is valid."""
    count = int(getattr(plan, "transport_retry_attempts", 0) or 0)
    if count < 1 or count > MAX_TRANSPORT_RETRIES:
        return None
    moment = (now or datetime.now(timezone.utc)) + timedelta(
        seconds=backoff_seconds(count)
    )
    expiry = getattr(plan, "not_after", None)
    if expiry:
        try:
            until = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
            if until.tzinfo is None or moment >= until:
                return None
        except (TypeError, ValueError):
            return None
    return moment.isoformat()


async def ensure_retry_wake(db, plan) -> bool:
    """Durably link exactly one Ambient wake to this recorded retry deadline.

    If a concurrent worker already inserted the identical wake, that is a
    success. The stable time bucket comes from the plan, not this worker's
    wall clock. Conditional ack avoids stamping a newer retry as scheduled.
    """
    when = getattr(plan, "transport_retry_due", None)
    count = int(getattr(plan, "transport_retry_attempts", 0) or 0)
    if (
        not when or getattr(plan, "status", "") != "held"
        or count < 1 or count > MAX_TRANSPORT_RETRIES
    ):
        return False
    owner_id = str(getattr(plan, "owner_id", "") or "")
    plan_id = str(getattr(plan, "id", "") or "")
    if not owner_id or not plan_id:
        return False
    wake = AmbientWake(
        owner_id=owner_id,
        reason="retry",
        delivery_plan_id=plan_id,
        opportunity_id=str(getattr(plan, "opportunity_id", "") or ""),
        source_ref=(
            f"{plan.source_type}:{plan.source_id}"
            if getattr(plan, "source_id", "") else ""
        ),
        scheduled_for=str(when),
        provenance="technical_retry",
    )
    scheduled = await AmbientRepository(db).schedule(wake)
    if scheduled is None:
        # Duplicate wake is harmless; a failed Mongo insert must remain
        # recoverable, not be acknowledged as scheduled.
        existing = await db.ambient_wakes.find_one({
            "owner_id": owner_id,
            "identity": wake.identity,
            "status": {"$in": ["pending", "claimed"]},
        }, {"_id": 0, "id": 1})
        if not existing:
            return False
    await db.delivery_plans.update_one(
        {
            "id": plan_id, "owner_id": owner_id,
            "status": "held",
            "transport_retry_due": when,
            "transport_retry_attempts": count,
        },
        {"$set": {"transport_retry_alarm_queued": True}},
    )
    return True


async def recover_unscheduled_retries(
    db, *, now: Optional[datetime] = None, limit: int = MAX_RECOVERY_BATCH,
) -> dict[str, int]:
    """Restore alarms omitted by a crash after storing a held delivery plan.

    This is an indexed, no-AI/no-push scan, run in the existing delivery
    admission lane. A real wake owns the later judgement and delivery.
    """
    from delivery.models import DeliveryPlan

    stamp = (now or datetime.now(timezone.utc)).isoformat()
    entries = await db.delivery_plans.find({
        "status": "held",
        "transport_retry_alarm_queued": {"$ne": True},
        "transport_retry_due": {"$type": "string", "$lte": stamp},
        "transport_retry_attempts": {"$gte": 1, "$lte": MAX_TRANSPORT_RETRIES},
    }, {"_id": 0}).sort("transport_retry_due", 1).limit(
        max(1, min(int(limit or 1), MAX_RECOVERY_BATCH))
    ).to_list(MAX_RECOVERY_BATCH)
    result = {"due": len(entries), "scheduled": 0, "deferred": 0}
    for doc in entries:
        try:
            if await ensure_retry_wake(db, DeliveryPlan.model_validate(doc)):
                result["scheduled"] += 1
            else:
                result["deferred"] += 1
        except Exception as exc:
            result["deferred"] += 1
            logger.info("transport retry wake recovery: %s", type(exc).__name__)
    return result
