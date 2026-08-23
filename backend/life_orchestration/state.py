"""Durable orchestration state: per-user lease and retry backoff (V2.9.4).

ONE collection, ONE lease granularity: the whole user pass. The alternative —
leasing signals, assessments and decisions separately — would triple the
bookkeeping to protect the same thing, because the expensive resource is not
any single record but the pair of AI calls a pass makes. Leasing the pass
covers both with a single atomic operation.

The lease exists only to prevent DOUBLE AI SPEND when two processes wake for
the same user. It is NOT a correctness mechanism: the unique indexes on
`life_change_signals.dedupe_key`, `life_impact_assessments.batch_key` and
`life_attention_decisions.decision_key` already make duplicate persistence
impossible. So a lost, expired or never-acquired lease costs money, never
consistency — which is why it is safe for it to be short, reclaimable and
best-effort.

Mongo is the source of truth. Nothing here is required for the work to be
recoverable: a signal stays `pending` until an assessment consumes it,
regardless of what any process believes about leases.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.life_orchestration.state")

# Long enough to cover two bounded AI calls, short enough that a crashed
# process does not block the user for long.
LEASE_TTL_SECONDS = 120

# Per-user, per-pipeline backoff. Deliberately NOT a provider circuit breaker —
# the Provider Manager already owns that, globally and per-vendor. This one
# stops a single user's pass from being retried in a tight loop.
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 3600
MAX_TRACKED_FAILURES = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


# Opaque, process-scoped owner id. Deliberately NOT a hostname, pid or any
# user identifier — a lease owner should not be a way to learn about the
# machine or the person.
_OWNER_ID = f"proc_{uuid.uuid4().hex[:12]}"


def owner_id() -> str:
    return _OWNER_ID


class OrchestrationStateRepository:
    COLLECTION = "life_orchestration_state"

    def __init__(self, db):
        self.db = db
        self.col = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("user_id", 1)], unique=True)
        # Recovery read path: users whose backoff has elapsed.
        await self.col.create_index([("next_retry_at", 1)])

    async def acquire(self, user_id: str, *, ttl_seconds: int = LEASE_TTL_SECONDS) -> bool:
        """Atomically take the user's pass lease.

        Succeeds when no lease exists or the existing one has expired, so a
        process that crashed mid-pass never blocks the user permanently.
        Returns False when another process holds a live lease.
        """
        now = _now()
        now_s = _iso(now)
        until = _iso(now + timedelta(seconds=ttl_seconds))
        free = [
            {"lease_until": None},
            {"lease_until": {"$exists": False}},
            {"lease_until": {"$lte": now_s}},
        ]
        try:
            # 1. Take over an existing lease that is free or expired.
            result = await self.col.update_one(
                {"user_id": user_id, "$or": free},
                {
                    "$set": {
                        "lease_owner": _OWNER_ID,
                        "lease_until": until,
                        "lease_acquired_at": now_s,
                    }
                },
            )
            if getattr(result, "matched_count", 0):
                return True

            # 2. A document exists but its lease is live, so someone else has
            #    it. Checked EXPLICITLY rather than by provoking a unique-index
            #    violation: if that index were ever missing, an upsert would
            #    silently insert a second row and hand out a second lease —
            #    a lease that quietly stops working is worse than no lease,
            #    because it looks like protection.
            if await self.col.find_one({"user_id": user_id}, {"_id": 1}):
                return False

            # 3. First time we have seen this user. A concurrent creator loses
            #    the race on the unique index, which is the one place that
            #    index is load-bearing.
            await self.col.insert_one({
                "user_id": user_id,
                "failure_count": 0,
                "lease_owner": _OWNER_ID,
                "lease_until": until,
                "lease_acquired_at": now_s,
            })
            return True
        except Exception as exc:
            if _is_duplicate_key(exc):
                return False
            logger.info("lease acquire soft-fail: %s", type(exc).__name__)
            return False

    async def release(self, user_id: str) -> None:
        """Release only if still ours — never steal another owner's lease."""
        try:
            await self.col.update_one(
                {"user_id": user_id, "lease_owner": _OWNER_ID},
                {"$set": {"lease_until": None, "lease_released_at": _iso(_now())}},
            )
        except Exception as exc:
            logger.info("lease release soft-fail: %s", type(exc).__name__)

    async def backoff_active(self, user_id: str) -> bool:
        """Whether this user's pipeline is still inside a retry backoff."""
        try:
            doc = await self.col.find_one(
                {"user_id": user_id}, {"_id": 0, "next_retry_at": 1}
            )
        except Exception:
            return False
        retry_at = _parse((doc or {}).get("next_retry_at"))
        return bool(retry_at and retry_at > _now())

    async def record_failure(self, user_id: str, *, reason: str = "unknown") -> str:
        """Bounded exponential backoff for THIS user's pipeline."""
        now = _now()
        try:
            doc = await self.col.find_one(
                {"user_id": user_id}, {"_id": 0, "failure_count": 1}
            )
            failures = min(int((doc or {}).get("failure_count") or 0) + 1, MAX_TRACKED_FAILURES)
            delay = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** (failures - 1)))
            next_retry = _iso(now + timedelta(seconds=delay))
            await self.col.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "failure_count": failures,
                        "next_retry_at": next_retry,
                        "last_failure_reason": str(reason)[:64],
                        "last_failure_at": _iso(now),
                    },
                    "$setOnInsert": {"user_id": user_id},
                },
                upsert=True,
            )
            return next_retry
        except Exception as exc:
            logger.info("record_failure soft-fail: %s", type(exc).__name__)
            return ""

    async def record_success(self, user_id: str) -> None:
        try:
            await self.col.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "failure_count": 0,
                        "next_retry_at": None,
                        "last_success_at": _iso(_now()),
                    },
                    "$setOnInsert": {"user_id": user_id},
                },
                upsert=True,
            )
        except Exception as exc:
            logger.info("record_success soft-fail: %s", type(exc).__name__)

    async def get(self, user_id: str) -> Dict[str, Any]:
        try:
            return await self.col.find_one({"user_id": user_id}, {"_id": 0}) or {}
        except Exception:
            return {}


def _is_duplicate_key(error: Exception) -> bool:
    if type(error).__name__ == "DuplicateKeyError":
        return True
    return getattr(error, "code", None) == 11000


def orchestration_enabled() -> bool:
    """Automatic orchestration can be switched off without touching the
    explicit `run_user_pass` entry point, so tests and operators keep a
    manual path even when the wake-up machinery is disabled."""
    raw = (os.environ.get("ORA_ORCHESTRATION_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")
