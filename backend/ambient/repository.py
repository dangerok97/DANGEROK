"""
Storage for arranged moments, devices, and whether anybody is looking.

The one thing here that is not ordinary CRUD is `claim`. Two backend
processes will race for the same due wake, and the naive shape — find the
pending ones, then update them — has a window between the read and the write
in which both processes see the same row and both act on it. The result is
two reviews, and eventually two notifications for one thing.

`find_one_and_update` closes that window inside the database: the filter and
the write are one operation, so exactly one process matches and the other
gets nothing back. That is the whole multi-instance story, and it does not
need a distributed lock service to be true.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ambient.models import AmbientWake, AppPresence, PushEndpoint

logger = logging.getLogger(__name__)

WAKES = "ambient_wakes"
ENDPOINTS = "push_endpoints"
PRESENCE = "app_presence"

# How long a worker holds a claim before the wake becomes eligible again. Long
# enough for a slow review including a model call; short enough that a process
# killed mid-flight does not strand the work for the rest of the day.
LEASE_SECONDS = 300

# A wake nobody managed to complete this many times has a problem a retry will
# not fix, and retrying for ever is how a queue becomes a fire.
MAX_ATTEMPTS = 5

# Arranged moments are working notes; they expire.
WAKE_RETENTION_DAYS = 7

OPEN = ("pending", "claimed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AmbientRepository:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[WAKES].create_index("id", unique=True)
            # The query the runtime runs constantly: what is due, and free.
            await self.db[WAKES].create_index([("status", 1), ("scheduled_for", 1)])
            await self.db[WAKES].create_index([("owner_id", 1), ("status", 1)])
            # One open alarm per identity. The database refuses the duplicate
            # so no caller has to remember not to create it.
            await self.db[WAKES].create_index(
                [("identity", 1)],
                unique=True,
                partialFilterExpression={"status": {"$in": list(OPEN)}},
            )
            await self.db[WAKES].create_index("expires_at", expireAfterSeconds=0)

            await self.db[ENDPOINTS].create_index("id", unique=True)
            await self.db[ENDPOINTS].create_index([("owner_id", 1), ("status", 1)])
            # A device belongs to one account at a time: registering it for a
            # second account has to move it, not clone it.
            await self.db[ENDPOINTS].create_index([("device_hash", 1)])
            await self.db[ENDPOINTS].create_index([("token", 1)])

            await self.db[PRESENCE].create_index("owner_id", unique=True)
        except Exception:
            logger.exception("indici ambient non creati (non fatale)")

    # --- arranged moments -------------------------------------------------

    async def schedule(self, wake: AmbientWake) -> Optional[AmbientWake]:
        """
        Set an alarm, unless the same alarm is already set.

        Returns None when an equivalent wake is already open — which is not a
        failure. Three updates to one concern should produce one moment to
        look at it again, and the caller wanting a second is the bug.
        """
        doc = wake.model_dump()
        doc["identity"] = wake.identity
        doc["expires_at"] = _now() + timedelta(days=WAKE_RETENTION_DAYS)
        try:
            await self.db[WAKES].insert_one(doc)
            return wake
        except Exception as exc:
            if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
                return None
            logger.info("wake schedule soft-fail: %s", type(exc).__name__)
            return None

    async def reschedule(self, wake_id: str, *, when: str) -> Optional[AmbientWake]:
        doc = await self.db[WAKES].find_one_and_update(
            {"id": wake_id},
            {"$set": {"scheduled_for": when, "status": "pending",
                      "claimed_at": None, "lease_until": None, "worker_id": "",
                      "updated_at": _now().isoformat()}},
            projection={"_id": 0},
            return_document=True,
        )
        return AmbientWake.model_validate(doc) if doc else None

    async def claim_due(self, *, worker_id: str, now: Optional[datetime] = None) -> Optional[AmbientWake]:
        """
        Take exactly one due wake, atomically, or nothing.

        The filter says: due, and either unclaimed or claimed by somebody
        whose lease has run out. The update stamps this worker's name on it.
        Both happen in one database operation, so two workers racing for the
        same row produce one winner and one `None` — never two winners.
        """
        moment = now or _now()
        stamp = moment.isoformat()
        lease = (moment + timedelta(seconds=LEASE_SECONDS)).isoformat()

        doc = await self.db[WAKES].find_one_and_update(
            {
                "scheduled_for": {"$lte": stamp},
                "attempts": {"$lt": MAX_ATTEMPTS},
                "$or": [
                    {"status": "pending"},
                    # A worker that died mid-review: its lease expired and the
                    # work is up for grabs again.
                    {"status": "claimed", "lease_until": {"$lt": stamp}},
                ],
            },
            {
                "$set": {
                    "status": "claimed",
                    "claimed_at": stamp,
                    "lease_until": lease,
                    "worker_id": worker_id,
                    "updated_at": stamp,
                },
                "$inc": {"attempts": 1},
            },
            sort=[("scheduled_for", 1)],
            projection={"_id": 0},
            return_document=True,
        )
        return AmbientWake.model_validate(doc) if doc else None

    async def complete(self, wake_id: str, *, result: str = "") -> None:
        await self.db[WAKES].update_one(
            {"id": wake_id},
            {"$set": {
                "status": "completed",
                "completed_at": _now().isoformat(),
                "updated_at": _now().isoformat(),
                "last_error": result[:80],
            }},
        )

    async def release(self, wake_id: str, *, when: str, error: str = "") -> None:
        """Put it back for later — a technical retry, not a new judgement."""
        await self.db[WAKES].update_one(
            {"id": wake_id},
            {"$set": {
                "status": "pending",
                "scheduled_for": when,
                "claimed_at": None,
                "lease_until": None,
                "worker_id": "",
                "provenance": "technical_retry",
                "last_error": error[:80],
                "updated_at": _now().isoformat(),
            }},
        )

    async def fail(self, wake_id: str, *, error: str) -> None:
        await self.db[WAKES].update_one(
            {"id": wake_id},
            {"$set": {"status": "failed", "last_error": error[:80],
                      "updated_at": _now().isoformat()}},
        )

    async def cancel_for(
        self, owner_id: str, *, opportunity_id: str = "", plan_id: str = ""
    ) -> int:
        query: Dict[str, Any] = {"owner_id": owner_id, "status": {"$in": list(OPEN)}}
        if opportunity_id:
            query["opportunity_id"] = opportunity_id
        if plan_id:
            query["delivery_plan_id"] = plan_id
        result = await self.db[WAKES].update_many(
            query,
            {"$set": {"status": "cancelled", "updated_at": _now().isoformat()}},
        )
        return result.modified_count

    async def open_wakes(self, owner_id: str, *, limit: int = 50) -> List[AmbientWake]:
        docs = await self.db[WAKES].find(
            {"owner_id": owner_id, "status": {"$in": list(OPEN)}}, {"_id": 0}
        ).sort("scheduled_for", 1).to_list(limit)
        return [AmbientWake.model_validate(d) for d in docs]

    async def get_wake(self, wake_id: str) -> Optional[AmbientWake]:
        doc = await self.db[WAKES].find_one({"id": wake_id}, {"_id": 0})
        return AmbientWake.model_validate(doc) if doc else None

    # --- devices ----------------------------------------------------------

    async def upsert_endpoint(self, endpoint: PushEndpoint) -> PushEndpoint:
        """
        Register a device, or recognise one already known.

        Matching on the token rather than on a generated id is what makes this
        idempotent: the same phone re-registering on every launch updates one
        row instead of accumulating a row per launch.
        """
        existing = await self.db[ENDPOINTS].find_one(
            {"token": endpoint.token}, {"_id": 0}
        )
        if existing:
            endpoint.id = existing["id"]
            endpoint.created_at = existing.get("created_at", endpoint.created_at)
        endpoint.updated_at = _now().isoformat()
        endpoint.last_seen_at = endpoint.updated_at
        await self.db[ENDPOINTS].update_one(
            {"token": endpoint.token},
            {"$set": endpoint.model_dump()},
            upsert=True,
        )
        return endpoint

    async def active_endpoints(self, owner_id: str) -> List[PushEndpoint]:
        docs = await self.db[ENDPOINTS].find(
            {"owner_id": owner_id, "status": "active"}, {"_id": 0}
        ).to_list(10)
        return [PushEndpoint.model_validate(d) for d in docs]

    async def disable_endpoint(self, *, token: str = "", endpoint_id: str = "",
                               reason: str = "") -> int:
        query = {"token": token} if token else {"id": endpoint_id}
        result = await self.db[ENDPOINTS].update_one(
            query,
            {"$set": {"status": "disabled", "disabled_reason": reason[:80],
                      "updated_at": _now().isoformat()}},
        )
        return result.modified_count

    async def revoke_device(self, *, device_hash: str, owner_id: str = "") -> int:
        """
        This device is no longer reachable for this account.

        Used on logout and when a device signs in as somebody else: a token
        left active for the previous account is how one person's notification
        arrives on another person's phone.
        """
        query: Dict[str, Any] = {"device_hash": device_hash, "status": "active"}
        if owner_id:
            query["owner_id"] = owner_id
        result = await self.db[ENDPOINTS].update_many(
            query,
            {"$set": {"status": "revoked", "disabled_reason": "device released",
                      "updated_at": _now().isoformat()}},
        )
        return result.modified_count

    # --- whether anybody is looking ---------------------------------------

    async def record_presence(self, presence: AppPresence) -> AppPresence:
        await self.db[PRESENCE].update_one(
            {"owner_id": presence.owner_id},
            {"$set": presence.model_dump()},
            upsert=True,
        )
        return presence

    async def app_presence(self, owner_id: str) -> AppPresence:
        doc = await self.db[PRESENCE].find_one({"owner_id": owner_id}, {"_id": 0})
        return AppPresence.model_validate(doc) if doc else AppPresence(owner_id=owner_id)

    async def forget_all(self, owner_id: str) -> Dict[str, int]:
        wakes = await self.db[WAKES].delete_many({"owner_id": owner_id})
        endpoints = await self.db[ENDPOINTS].delete_many({"owner_id": owner_id})
        await self.db[PRESENCE].delete_many({"owner_id": owner_id})
        return {
            "wakes_deleted": wakes.deleted_count,
            "endpoints_deleted": endpoints.deleted_count,
        }
