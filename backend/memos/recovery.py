"""Crash-safe, owner-scoped recovery of annual reminders after Memory changes.

The old Memory records a pending reconciliation in the SAME Mongo update that
supersedes/forgets it. This worker claims those pending records, never guesses a
new Memory, and retries after crashes or transient storage errors.

No model, notification, network provider, or second scheduler is used here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import uuid
from typing import Any, Optional

from memos.service import RecurringMemoService

logger = logging.getLogger("ora.memos.recovery")
LEASE_SECONDS = 120
RETRY_SECONDS = 60
MAX_CHAIN = 12
MAX_BATCH = 12


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def resolve_replacement(db, owner_id: str, memory: dict) -> tuple[str, Optional[str]]:
    """Find the final owned Memory in a bounded chain; never cross an owner."""
    if memory.get("status") == "forgotten":
        return "disable", None
    if memory.get("status") != "superseded":
        return "defer", None
    visited = {str(memory.get("id") or "")}
    current = str(memory.get("superseded_by") or "")
    for _ in range(MAX_CHAIN):
        if not current or current in visited:
            return "defer", None
        visited.add(current)
        target = await db.memories.find_one(
            {"user_id": owner_id, "id": current},
            {"_id": 0, "id": 1, "status": 1, "superseded_by": 1},
        )
        if not target:
            return "defer", None
        status = target.get("status")
        if status == "active":
            return "transfer", current
        if status == "forgotten":
            return "disable", None
        if status != "superseded":
            return "defer", None
        current = str(target.get("superseded_by") or "")
    return "defer", None


class RecurringMemoRecovery:
    def __init__(self, db):
        self.db = db

    async def _claim(self, moment: datetime) -> Optional[dict]:
        stamp = moment.isoformat()
        token = uuid.uuid4().hex
        return await self.db.memories.find_one_and_update(
            {
                "recurring_reconcile.status": "pending",
                "recurring_reconcile.next_retry_at": {"$lte": stamp},
                "$or": [
                    {"recurring_reconcile.lease_until": {"$exists": False}},
                    {"recurring_reconcile.lease_until": {"$lte": stamp}},
                ],
            },
            {"$set": {
                "recurring_reconcile.lease_until": (
                    moment + timedelta(seconds=LEASE_SECONDS)
                ).isoformat(),
                "recurring_reconcile.lease_token": token,
            }},
            sort=[("recurring_reconcile.next_retry_at", 1), ("_id", 1)],
            return_document=True,
        )

    async def _finish(self, memory: dict, *, now: datetime, completed: bool) -> bool:
        reconcile = memory.get("recurring_reconcile") or {}
        selector = {
            "_id": memory["_id"], "user_id": memory["user_id"],
            "recurring_reconcile.status": "pending",
            "recurring_reconcile.lease_token": reconcile.get("lease_token"),
        }
        if completed:
            update = {"$set": {
                "recurring_reconcile.status": "completed",
                "recurring_reconcile.completed_at": now.isoformat(),
                "recurring_reconcile.lease_until": "",
                "recurring_reconcile.lease_token": "",
                "recurring_reconcile.next_retry_at": "",
            }}
        else:
            attempts = min(6, max(0, int(reconcile.get("attempts") or 0)) + 1)
            delay = min(3600, RETRY_SECONDS * (2 ** (attempts - 1)))
            update = {"$set": {
                "recurring_reconcile.next_retry_at": (
                    now + timedelta(seconds=delay)
                ).isoformat(),
                "recurring_reconcile.lease_until": "",
                "recurring_reconcile.lease_token": "",
            }, "$inc": {"recurring_reconcile.attempts": 1}}
        result = await self.db.memories.update_one(selector, update)
        return bool(result.modified_count)

    async def run(self, *, now: Optional[datetime] = None, limit: int = MAX_BATCH) -> dict:
        """One bounded recovery pass; unfinished work stays queryable in Mongo."""
        moment = now or _utc_now()
        output: dict[str, int] = {
            "claimed": 0, "completed": 0, "deferred": 0,
            "errors": 0, "transferred": 0, "disabled": 0,
        }
        service = RecurringMemoService(self.db)
        for _ in range(max(1, min(int(limit or 1), MAX_BATCH))):
            memory = await self._claim(moment)
            if memory is None:
                break
            output["claimed"] += 1
            owner_id = str(memory.get("user_id") or "")
            old_ref = str(memory.get("id") or "")
            completed = False
            try:
                if not owner_id or not old_ref:
                    raise ValueError("pending memory missing owner/reference")
                action, final_ref = await resolve_replacement(self.db, owner_id, memory)
                if action == "defer":
                    output["deferred"] += 1
                else:
                    changes = await service.reconcile_governed_memory(
                        owner_id, old_ref=old_ref,
                        new_ref=final_ref if action == "transfer" else None,
                    )
                    output["transferred"] += changes.get("transferred", 0)
                    output["disabled"] += changes.get("disabled", 0)
                    completed = True
            except Exception as exc:
                output["errors"] += 1
                logger.warning("recurring memo recovery retry: %s", type(exc).__name__)
            if await self._finish(memory, now=moment, completed=completed):
                if completed:
                    output["completed"] += 1
        return output
