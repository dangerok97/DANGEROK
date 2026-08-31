"""
Is there any concrete reason ORA should look at this life again?

    ORA DOES NOT NEED THE USER TO WAKE IT UP.
    BUT ORA ALSO DOES NOT WAKE ITSELF WITHOUT A REASON.

Everything upstream is event-driven, and event-driven systems lose things: a
source stops emitting, a wake is lost to a restart, a change arrives while the
worker is down. This is the safety net, and the whole difficulty is building
one that does not become the thing it exists to avoid — an hourly job that
builds a snapshot for everybody and asks a model what it thinks.

So this asks a much smaller question, and answers it with indexed counts. Is
there an active concern with a clock on it? A plan still intending to arrive?
A wake that was due an hour ago and never ran? An unprocessed change? Each is
a fact, none is a judgement, and the answer is a boolean that costs a handful
of queries.

What it produces when the answer is yes is a wake — not a review, not a
conclusion, and certainly not a notification. The existing runtime does the
rest, exactly as it would for any other alarm.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Two different things that were one setting, and should not have been.
#
# The sweep cadence bounds how long a lost event can go unnoticed: it is about
# the system noticing. The per-person interval bounds how often any one life
# is looked at again: it is about not arranging a review for somebody every
# few minutes just because they are permanently eligible. Turning one down
# should not silently change the other.
#
# Both are infrastructure. Neither says anything about how often anybody hears
# from ORA — that is decided much later, by a judgement.
SWEEP_INTERVAL_HOURS = float(
    os.environ.get("AMBIENT_FALLBACK_SWEEP_INTERVAL_HOURS", "1")
)
PER_USER_INTERVAL_HOURS = float(
    os.environ.get("AMBIENT_FALLBACK_USER_INTERVAL_HOURS", "12")
)

# How far ahead a closing window counts as worth looking at. Derived from the
# per-person interval, because the question it answers is "will this still be
# open the next time we look at this person?".
def horizon_hours() -> float:
    return PER_USER_INTERVAL_HOURS * 2

# A wake this far past its moment was missed rather than merely late.
OVERDUE_MINUTES = 30

# How many people one sweep looks at. A backlog is drained over several
# sweeps rather than in one pass that walks everybody.
MAX_USERS_PER_SWEEP = 200

# The lease that stops two backends from sweeping at once.
SWEEP_LEASE_SECONDS = 600
SWEEP_LOCK = "ambient_sweep"
LOCKS = "ambient_locks"
FALLBACK_STATE = "ambient_fallback_state"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EligibilityService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[LOCKS].create_index("name", unique=True)
            await self.db[FALLBACK_STATE].create_index("owner_id", unique=True)
        except Exception:
            logger.exception("indici fallback non creati (non fatale)")

    # --- the small question ------------------------------------------------

    async def reasons_to_look_again(self, owner_id: str) -> List[str]:
        """
        Every concrete reason there is, named. Empty means there is none.

        Counts and existence checks only — no snapshot is built, no model is
        reached, and nothing here decides what any of it means. A life with
        nothing in it costs a handful of indexed queries and produces an empty
        list, which is the case this whole design is shaped around.
        """
        now = _now()
        reasons: List[str] = []

        # Something still intending to arrive.
        try:
            if await self.db.delivery_plans.count_documents(
                {"owner_id": owner_id, "status": {"$in": ["pending", "held"]}}, limit=1
            ):
                reasons.append("delivery_pending")
        except Exception as e:
            logger.info("eligibility plans soft-fail: %s", type(e).__name__)

        # An alarm that was due and never ran. This is the lost-wake case.
        try:
            overdue = (now - timedelta(minutes=OVERDUE_MINUTES)).isoformat()
            if await self.db.ambient_wakes.count_documents(
                {
                    "owner_id": owner_id,
                    "status": {"$in": ["pending", "claimed"]},
                    "scheduled_for": {"$lte": overdue},
                },
                limit=1,
            ):
                reasons.append("wake_overdue")
        except Exception as e:
            logger.info("eligibility wakes soft-fail: %s", type(e).__name__)

        # Something moved and nobody has read it.
        try:
            if await self.db.meaningful_changes.count_documents(
                {"owner_id": owner_id, "status": "pending"}, limit=1
            ):
                reasons.append("changes_unprocessed")
        except Exception as e:
            logger.info("eligibility changes soft-fail: %s", type(e).__name__)

        # An open concern with a clock on it. Time alone can make a review
        # worth running: nothing stored has to change for `valid_until` to
        # stop being far away.
        try:
            soon = (now + timedelta(hours=horizon_hours())).isoformat()
            if await self.db.opportunities.count_documents(
                {
                    "owner_id": owner_id,
                    "status": "active",
                    "valid_until": {"$ne": None, "$lte": soon},
                },
                limit=1,
            ):
                reasons.append("temporal_window")
        except Exception as e:
            logger.info("eligibility opportunities soft-fail: %s", type(e).__name__)

        # Something the person put off, whose moment has arrived.
        try:
            if await self.db.opportunities.count_documents(
                {
                    "owner_id": owner_id,
                    "status": "active",
                    "surface_state": "deferred",
                    "deferred_until": {"$ne": None, "$lte": now.isoformat()},
                },
                limit=1,
            ):
                reasons.append("revisit_due")
        except Exception as e:
            logger.info("eligibility deferred soft-fail: %s", type(e).__name__)

        return reasons

    async def eligible(self, owner_id: str) -> bool:
        return bool(await self.reasons_to_look_again(owner_id))

    # --- casting the net ---------------------------------------------------

    async def sweep(self, *, now: Optional[datetime] = None, limit: int = MAX_USERS_PER_SWEEP) -> Dict[str, Any]:
        """
        Look for people something has been forgotten about, and arrange a wake.

        Never a full scan: the candidate set comes from the collections that
        already say somebody has state worth looking at, so a database full of
        people with nothing pending contributes nothing to the cost.
        """
        moment = now or _now()
        if not await self._claim_sweep(moment):
            # Another instance is already doing this. Two sweeps in parallel
            # would produce the same wakes twice, which the identity index
            # would refuse — but paying for the queries anyway is pointless.
            return {"ran": False, "reason": "another_instance"}

        checked, eligible, scheduled, skipped = 0, 0, 0, 0
        for owner_id in await self._candidates(moment, limit):
            checked += 1
            if not await self._due_for_fallback(owner_id, moment):
                skipped += 1
                continue

            reasons = await self.reasons_to_look_again(owner_id)
            await self._remember(owner_id, moment, reasons)
            if not reasons:
                # Nothing to look at. No wake, no activity, no inference, and
                # nothing that could later be mistaken for ORA having worked.
                continue

            eligible += 1
            if await self._arrange(owner_id, moment, reasons):
                scheduled += 1

        logger.info(
            "ambient_fallback checked=%s eligible=%s scheduled=%s", checked, eligible, scheduled
        )
        return {
            "ran": True,
            "checked": checked,
            "eligible": eligible,
            "scheduled": scheduled,
            "skipped": skipped,
        }

    async def _candidates(self, now: datetime, limit: int) -> List[str]:
        """
        Who might have something waiting — asked of the state, not of everybody.

            NO FULL-TABLE COGNITIVE SCAN.

        Three cheap distinct queries against indexed collections. Somebody who
        has never had an opportunity, a plan or a change never appears here.
        """
        owners: set[str] = set()
        overdue = (now - timedelta(minutes=OVERDUE_MINUTES)).isoformat()

        for collection, query in (
            ("delivery_plans", {"status": {"$in": ["pending", "held"]}}),
            (
                "ambient_wakes",
                {"status": {"$in": ["pending", "claimed"]}, "scheduled_for": {"$lte": overdue}},
            ),
            ("meaningful_changes", {"status": "pending"}),
            ("opportunities", {"status": "active"}),
        ):
            if len(owners) >= limit:
                break
            try:
                found = await self.db[collection].distinct("owner_id", query)
                owners.update(str(o) for o in found if o)
            except Exception as e:
                logger.info("candidates %s soft-fail: %s", collection, type(e).__name__)

        return sorted(owners)[:limit]

    async def _due_for_fallback(self, owner_id: str, now: datetime) -> bool:
        """
        Rare, per person.

            NO CRON EXPLOSION.

        Without this, a sweep every few minutes would arrange a review every
        few minutes for anybody who is permanently eligible.
        """
        try:
            state = await self.db[FALLBACK_STATE].find_one(
                {"owner_id": owner_id}, {"_id": 0, "last_checked_at": 1}
            )
        except Exception:
            return True
        last = (state or {}).get("last_checked_at")
        if not last:
            return True
        try:
            when = datetime.fromisoformat(str(last))
        except ValueError:
            return True
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return (now - when) >= timedelta(hours=PER_USER_INTERVAL_HOURS)

    async def _arrange(self, owner_id: str, now: datetime, reasons: List[str]) -> bool:
        """
        Ask for a review. Not a review — a request for one.

        The wake goes through the same identity rule as every other: if the
        runtime already has an equivalent one open, this adds nothing and the
        database says so.
        """
        from ambient.service import AmbientService

        wake = await AmbientService(self.db).schedule(
            owner_id,
            reason="ambient_review",
            when=now + timedelta(minutes=1),
            source_ref=",".join(reasons)[:120],
            provenance="code_schedule",
        )
        return wake is not None

    async def _remember(self, owner_id: str, now: datetime, reasons: List[str]) -> None:
        try:
            await self.db[FALLBACK_STATE].update_one(
                {"owner_id": owner_id},
                {"$set": {
                    "owner_id": owner_id,
                    "last_checked_at": now.isoformat(),
                    "last_reasons": reasons[:6],
                }},
                upsert=True,
            )
        except Exception as e:
            logger.info("fallback state soft-fail: %s", type(e).__name__)

    async def _claim_sweep(self, now: datetime) -> bool:
        """
        One sweep at a time across every instance.

        Same shape as the wake claim and for the same reason: the filter and
        the write are one operation, so a second process finds nothing to
        match rather than racing through the same work.
        """
        expiry = (now - timedelta(seconds=SWEEP_LEASE_SECONDS)).isoformat()
        try:
            claimed = await self.db[LOCKS].find_one_and_update(
                {
                    "name": SWEEP_LOCK,
                    "$or": [
                        {"held_until": {"$lt": now.isoformat()}},
                        {"held_until": {"$exists": False}},
                    ],
                },
                {"$set": {
                    "name": SWEEP_LOCK,
                    "held_until": (now + timedelta(seconds=SWEEP_LEASE_SECONDS)).isoformat(),
                    "claimed_at": now.isoformat(),
                }},
                upsert=True,
                return_document=True,
            )
            return claimed is not None
        except Exception as exc:
            if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
                # Somebody else holds it and the upsert lost the race.
                return False
            logger.info("sweep lock soft-fail: %s", type(exc).__name__)
            return False


async def recover_after_downtime(db, *, now: Optional[datetime] = None) -> Dict[str, int]:
    """
    Put the world back in order after the process was away.

        NO CATCH-UP SPAM.

    Nothing here sends anything and nothing here asks a model. Leases held by
    workers that no longer exist are released so their wakes become eligible
    again, and plans whose moment has passed are expired rather than fired
    late. What survives is re-examined by the ordinary path, one at a time,
    under the same rate limits as any other day — which is what stops four
    hours of downtime from becoming four notifications in one minute.
    """
    moment = now or _now()
    stamp = moment.isoformat()
    released, expired = 0, 0

    try:
        result = await db.ambient_wakes.update_many(
            {"status": "claimed", "lease_until": {"$lt": stamp}},
            {"$set": {"status": "pending", "worker_id": "", "lease_until": None,
                      "claimed_at": None, "updated_at": stamp}},
        )
        released = result.modified_count
    except Exception as e:
        logger.info("recovery lease soft-fail: %s", type(e).__name__)

    try:
        result = await db.delivery_plans.update_many(
            {"status": {"$in": ["pending", "held"]}, "not_after": {"$ne": None, "$lt": stamp}},
            {"$set": {"status": "expired", "decision_provenance": "code_expiry",
                      "rationale": "il momento utile è passato mentre ORA era ferma",
                      "updated_at": stamp}},
        )
        expired = result.modified_count
    except Exception as e:
        logger.info("recovery expiry soft-fail: %s", type(e).__name__)

    if released or expired:
        logger.info("ambient_recovery released=%s expired=%s", released, expired)
    return {"leases_released": released, "plans_expired": expired}
