"""
Housekeeping for records that only grow.

Production census 23/10/2026, one account: 212,040 permission-audit rows and
6,521 Home snapshots after about two months. Nothing ever removed them. That
is cost and latency today and a privacy liability tomorrow — keeping more
than a purpose needs is the opposite of minimisation.

Rules, each tied to what the records are for:

* Home snapshots are a cache of the last rankings. Readers look at the latest
  one, or at the last few that mention an item. Keep 30 days, and always the
  newest SNAPSHOT_KEEP_LATEST per person so an inactive account keeps its
  last Home.
* Permission-audit rows already carry their own `retention_until`. Expired
  rows are removed; nothing younger is touched here.

Deletions are bounded per pass and idempotent; a failure just waits for the
next pass. Nothing here reads personal content.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SNAPSHOT_DAYS = int(os.environ.get("HOME_SNAPSHOT_RETENTION_DAYS", "30"))
SNAPSHOT_KEEP_LATEST = 20
MAX_OWNERS_PER_PASS = 200


async def prune_home_snapshots(db, *, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=SNAPSHOT_DAYS)).isoformat()
    owners = await db.home_snapshots.distinct("user_id", {"generated_at": {"$lt": cutoff}})
    removed = 0
    for owner in owners[:MAX_OWNERS_PER_PASS]:
        keep = await db.home_snapshots.find(
            {"user_id": owner}, {"_id": 0, "generated_at": 1},
        ).sort("generated_at", -1).skip(SNAPSHOT_KEEP_LATEST - 1).limit(1).to_list(1)
        if not keep:
            continue  # fewer than the floor: nothing to remove
        floor = str(keep[0].get("generated_at") or "")
        limit = min(cutoff, floor) if floor else cutoff
        result = await db.home_snapshots.delete_many(
            {"user_id": owner, "generated_at": {"$lt": limit}},
        )
        removed += int(getattr(result, "deleted_count", 0) or 0)
    return removed


async def prune_expired_audit(db, *, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    result = await db.permission_audit.delete_many(
        {"retention_until": {"$lt": now.isoformat()}},
    )
    return int(getattr(result, "deleted_count", 0) or 0)


async def run(db, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    report: Dict[str, Any] = {}
    for name, job in (("home_snapshots", prune_home_snapshots), ("permission_audit", prune_expired_audit)):
        try:
            report[name] = await job(db, now=now)
        except Exception as exc:
            report[name] = f"deferred:{type(exc).__name__}"
    logger.info("retention pass %s", report)
    return report
