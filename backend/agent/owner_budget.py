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

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError


COLLECTION = "agent_owner_background_budgets"
DEFAULT_DAILY_BACKGROUND_RUNS = 12
MAX_CONFIGURED_DAILY_BACKGROUND_RUNS = 96
RETENTION_DAYS = 7

# Same-process workers do not need to race the database for the same person's
# daily counter. Mongo's unique key/upsert remains the cross-process guard.
_CLAIM_LOCKS: dict[str, asyncio.Lock] = {}
_CLAIM_LOCK_DAY = ""
_CLAIM_LOCK_LOOP_ID = 0


def _claim_lock(owner_id: str, day: str) -> asyncio.Lock:
    global _CLAIM_LOCK_DAY, _CLAIM_LOCK_LOOP_ID
    loop_id = id(asyncio.get_running_loop())
    if _CLAIM_LOCK_DAY != day or _CLAIM_LOCK_LOOP_ID != loop_id:
        _CLAIM_LOCKS.clear()
        _CLAIM_LOCK_DAY = day
        _CLAIM_LOCK_LOOP_ID = loop_id
    return _CLAIM_LOCKS.setdefault(owner_id, asyncio.Lock())


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

        Same-process workers serialize per owner/day. Across processes, a
        conditional Mongo update increments only while used is below limit.
        The first row is created under a unique owner/day key; if another
        process wins that insert, we retry the same bounded increment.

        We use modified_count rather than relying on return-document semantics:
        the fact we need is whether this claim consumed a credit.
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
        }

        async def increment_existing() -> Optional[int]:
            result = await self.db[COLLECTION].update_one(
                query,
                update,
                upsert=False,
            )
            if int(result.modified_count or 0) != 1:
                return None
            row = await self.db[COLLECTION].find_one(
                {"owner_id": owner_id, "day": day},
                {"_id": 0, "used": 1},
            )
            return int((row or {}).get("used") or 0)

        async with _claim_lock(owner_id, day):
            try:
                used = await increment_existing()
                if used is not None:
                    return OwnerBudgetClaim(
                        allowed=True,
                        used=used,
                        limit=self.daily_limit,
                        reset_at=reset_at,
                    )

                existing = await self.db[COLLECTION].find_one(
                    {"owner_id": owner_id, "day": day},
                    {"_id": 0, "used": 1},
                )
                if existing is not None:
                    return OwnerBudgetClaim(
                        allowed=False,
                        used=int(existing.get("used") or self.daily_limit),
                        limit=self.daily_limit,
                        reset_at=reset_at,
                    )

                try:
                    await self.db[COLLECTION].insert_one({
                        "owner_id": owner_id,
                        "day": day,
                        "used": 1,
                        "limit": self.daily_limit,
                        "created_at": moment.isoformat(),
                        "updated_at": moment.isoformat(),
                        "reset_at": reset_at,
                        "expires_at": expires,
                    })
                    return OwnerBudgetClaim(
                        allowed=True,
                        used=1,
                        limit=self.daily_limit,
                        reset_at=reset_at,
                    )
                except DuplicateKeyError:
                    used = await increment_existing()
                    if used is not None:
                        return OwnerBudgetClaim(
                            allowed=True,
                            used=used,
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
