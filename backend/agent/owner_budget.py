"""Persistent per-person budget for autonomous background work.

One goal already has a hard per-run budget. This layer answers the missing
cross-goal question: how many such bounded bursts may ORA spend on one person
in one technical day?

The counter is deliberately expressed in background runs, not guessed tokens
or provider euros. A run already has hard ceilings on cognitive calls,
capability calls, research, steps and wall time; multiplying those ceilings by
this owner-scoped run limit gives a deterministic worst-case daily bound.

Explicit user-driven runs never come through this budget. It exists only to
bound unsolicited/background autonomy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


COLLECTION = "agent_owner_background_budgets"
DEFAULT_DAILY_BACKGROUND_RUNS = 12
MAX_CONFIGURED_DAILY_BACKGROUND_RUNS = 96
RETENTION_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def configured_daily_limit() -> int:
    raw = os.getenv(
        "ORA_OWNER_BACKGROUND_RUNS_PER_DAY",
        str(DEFAULT_DAILY_BACKGROUND_RUNS),
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_DAILY_BACKGROUND_RUNS
    return max(1, min(MAX_CONFIGURED_DAILY_BACKGROUND_RUNS, value))


def _window(moment: datetime) -> tuple[str, datetime, datetime]:
    current = moment.astimezone(timezone.utc)
    day = current.date().isoformat()
    reset = datetime(
        current.year,
        current.month,
        current.day,
        tzinfo=timezone.utc,
    ) + timedelta(days=1)
    expires = reset + timedelta(days=RETENTION_DAYS)
    return day, reset, expires


@dataclass(frozen=True)
class OwnerBudgetClaim:
    allowed: bool
    used: int
    limit: int
    reset_at: str

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


class OwnerBackgroundBudget:
    def __init__(self, db, *, daily_limit: Optional[int] = None):
        self.db = db
        self.daily_limit = (
            configured_daily_limit()
            if daily_limit is None
            else max(1, min(MAX_CONFIGURED_DAILY_BACKGROUND_RUNS, int(daily_limit)))
        )

    async def ensure_indexes(self) -> None:
        try:
            await self.db[COLLECTION].create_index(
                [("owner_id", 1), ("day", 1)],
                unique=True,
            )
            await self.db[COLLECTION].create_index(
                "expires_at",
                expireAfterSeconds=0,
            )
        except Exception:
            # Budget storage is a guard, not a reason to take the whole
            # application down. Claim() still fails closed on storage errors.
            pass

    async def claim(
        self,
        owner_id: str,
        *,
        now: Optional[datetime] = None,
    ) -> OwnerBudgetClaim:
        """Atomically consume one owner-scoped background burst.

        The unique (owner_id, day) row is also the counter. upsert=True
        handles the first claim without a read-before-write race; the
        used < limit predicate handles every later claim. Once the existing
        row is full, Mongo attempts an insert that collides with the unique
        owner/day key; that duplicate-key is the atomic full-budget signal.

        A first-row race can surface as DuplicateKeyError while capacity still
        remains, so retry one bounded non-upsert increment before deciding the
        budget is exhausted. Storage uncertainty fails closed.
        """
        moment = (now or _now()).astimezone(timezone.utc)
        day, reset, expires = _window(moment)
        reset_at = reset.isoformat()
        query = {
            "owner_id": owner_id,
            "day": day,
            "used": {"$lt": self.daily_limit},
        }
        update = {
            "$inc": {"used": 1},
            "$set": {
                "updated_at": moment.isoformat(),
                "limit": self.daily_limit,
                "reset_at": reset_at,
                "expires_at": expires,
            },
            "$setOnInsert": {
                "owner_id": owner_id,
                "day": day,
                "created_at": moment.isoformat(),
            },
        }

        async def bounded_increment(*, upsert: bool):
            return await self.db[COLLECTION].find_one_and_update(
                query,
                update,
                upsert=upsert,
                projection={"_id": 0, "used": 1},
                return_document=ReturnDocument.AFTER,
            )

        try:
            try:
                row = await bounded_increment(upsert=True)
            except DuplicateKeyError:
                # Another worker won the first insert race, or the row is
                # already full. A bounded non-upsert retry distinguishes them.
                row = await bounded_increment(upsert=False)

            if row is not None:
                return OwnerBudgetClaim(
                    allowed=True,
                    used=int(row.get("used") or 0),
                    limit=self.daily_limit,
                    reset_at=reset_at,
                )

            existing = await self.db[COLLECTION].find_one(
                {"owner_id": owner_id, "day": day},
                {"_id": 0, "used": 1},
            )
            return OwnerBudgetClaim(
                allowed=False,
                used=int((existing or {}).get("used") or self.daily_limit),
                limit=self.daily_limit,
                reset_at=reset_at,
            )
        except Exception:
            return OwnerBudgetClaim(
                allowed=False,
                used=self.daily_limit,
                limit=self.daily_limit,
                reset_at=reset_at,
            )

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[COLLECTION].delete_many({"owner_id": owner_id})
        return int(result.deleted_count or 0)
