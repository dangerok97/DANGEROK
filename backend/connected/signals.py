"""
Observations, kept once.

    THE SAME NEWS TWICE IS ONE PIECE OF NEWS.

Everything expensive downstream — a model call, a wake, a goal, a sentence in
somebody's pocket — starts here, so this is where a duplicate has to die. A
re-sync that sees an unchanged world must cost one indexed lookup and
nothing else, or an autonomous runtime is unaffordable and a person's phone
buzzes twice about one appointment.

Two guards, and they answer different questions. The **fingerprint** answers
"have we already seen exactly this?" — same object, same resulting state,
however many times the provider hands it to us. **Superseding** answers "is
this the same story, moved on?" — the appointment that went 10 → 15 and then
15 → 16 is one thing changing twice, and the pending signal about the first
move is no longer what is true.

History is kept, briefly. Not event sourcing: enough to answer "what was it
before" when a judgement asks, and no more, because an archive of everything
that ever moved in somebody's calendar is a liability nobody asked us to
hold.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from connected.models import ConnectedSignal, now_iso

logger = logging.getLogger("ora.connected.signals")

SIGNALS = "connected_signals"

# How long an observation is kept. Long enough to answer "what changed since
# yesterday" and to survive a weekend of downtime; short enough that this is a
# working set rather than a diary of somebody's life.
RETENTION_DAYS = 30

# How many pending signals one pass will look at. A bound, not a preference:
# a person returning from a fortnight offline should not produce a hundred
# model calls in one wake.
MAX_PENDING = 12


class SignalService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[SIGNALS].create_index(
                [("owner_id", 1), ("fingerprint", 1)], unique=True
            )
            await self.db[SIGNALS].create_index([("owner_id", 1), ("status", 1)])
            await self.db[SIGNALS].create_index(
                [("owner_id", 1), ("source_object_ref", 1)]
            )
            await self.db[SIGNALS].create_index("expires_at", expireAfterSeconds=0)
        except Exception:
            logger.exception("indici connected signals non creati (non fatale)")

    # --- taking note -----------------------------------------------------

    async def record(self, signal: ConnectedSignal) -> Tuple[Optional[ConnectedSignal], str]:
        """
        Keep this observation, unless we already have it.

        Returns the signal and what happened to it, in a word the caller can
        act on: `recorded`, `duplicate`, or `superseded_previous`. Every
        refusal is mechanical. None of them is a judgement about importance —
        this function never sees enough to make one, and the day it does the
        layer above stops being able to decide anything.
        """
        if not signal.owner_id:
            return None, "no_owner"
        signal.fingerprint = signal.compute_fingerprint()

        existing = await self.db[SIGNALS].find_one(
            {"owner_id": signal.owner_id, "fingerprint": signal.fingerprint},
            {"_id": 0, "id": 1, "status": 1},
        )
        if existing is not None:
            return None, "duplicate"

        # The same object moving again. What was pending about the earlier
        # move is not wrong, it is simply no longer the news — and leaving it
        # pending would have the agent reason about an appointment that has
        # since moved on.
        superseded = ""
        if signal.source_object_ref:
            prior = await self.db[SIGNALS].find_one(
                {
                    "owner_id": signal.owner_id,
                    "source_object_ref": signal.source_object_ref,
                    "status": "pending",
                },
                {"_id": 0, "id": 1},
                sort=[("observed_at", -1)],
            )
            if prior is not None:
                superseded = str(prior["id"])
                signal.supersedes = superseded
                await self.db[SIGNALS].update_one(
                    {"owner_id": signal.owner_id, "id": superseded},
                    {"$set": {"status": "superseded"}},
                )

        doc = signal.model_dump()
        doc["expires_at"] = datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)
        try:
            await self.db[SIGNALS].insert_one(doc)
        except Exception as e:
            # A duplicate key here means two workers saw the same change at
            # once, which is exactly what the unique index is for.
            logger.info("signal insert: %s", type(e).__name__)
            return None, "duplicate"

        return signal, "superseded_previous" if superseded else "recorded"

    # --- reading it back --------------------------------------------------

    async def pending(self, owner_id: str, *, limit: int = MAX_PENDING) -> List[ConnectedSignal]:
        docs = await self.db[SIGNALS].find(
            {"owner_id": owner_id, "status": "pending"}, {"_id": 0}
        ).sort("observed_at", 1).to_list(limit)
        return [ConnectedSignal.model_validate(d) for d in docs]

    async def get(self, owner_id: str, signal_id: str) -> Optional[ConnectedSignal]:
        doc = await self.db[SIGNALS].find_one(
            {"owner_id": owner_id, "id": signal_id}, {"_id": 0}
        )
        return ConnectedSignal.model_validate(doc) if doc else None

    async def history(
        self, owner_id: str, source_object_ref: str, *, limit: int = 6
    ) -> List[ConnectedSignal]:
        """
        What this thing has done lately.

        Enough to say "prima era così, adesso è così" when somebody asks, and
        bounded so that an appointment somebody keeps moving does not become
        an unbounded record of their indecision.
        """
        docs = await self.db[SIGNALS].find(
            {"owner_id": owner_id, "source_object_ref": source_object_ref}, {"_id": 0}
        ).sort("observed_at", -1).to_list(limit)
        return [ConnectedSignal.model_validate(d) for d in docs]

    async def settle(self, owner_id: str, signal_id: str, *, outcome: str) -> None:
        """This one has been looked at, and here is what came of it."""
        await self.db[SIGNALS].update_one(
            {"owner_id": owner_id, "id": signal_id},
            {"$set": {"status": "interpreted", "interpreted_at": now_iso(),
                      "outcome": str(outcome)[:60]}},
        )

    async def skip(self, owner_id: str, signal_id: str, *, why: str) -> None:
        await self.db[SIGNALS].update_one(
            {"owner_id": owner_id, "id": signal_id},
            {"$set": {"status": "skipped", "interpreted_at": now_iso(),
                      "outcome": str(why)[:60]}},
        )

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[SIGNALS].delete_many({"owner_id": owner_id})
        return result.deleted_count
