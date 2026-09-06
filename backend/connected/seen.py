"""
What a thing looked like the last time we saw it.

    A SOURCE THAT REWRITES IN PLACE HAS NO PAST UNLESS SOMEBODY KEEPS ONE.

The calendar gets its "before" for free: ingestion writes a new row per
version and links it to the one it replaced, so a delta is a comparison
between two records that both still exist. Nothing else works that way. A
document is edited in place — the filename becomes the new filename and the
old one is gone — so a sensor with no memory can only ever report that a
document exists, which it already knew.

This is that memory, and it is deliberately the smallest one that answers the
question. Not a version history and not an audit log: one row per object,
holding the last observed values of the fields a person could notice, so the
next reading can say what moved. Overwritten each time, expiring with the
signals it exists to produce.

What it is careful about is the same thing everything in this package is
careful about: it stores what is needed to describe a change and nothing
else. A private note's content never lands here — only that there was one and
that it is now different.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from connected.models import FieldChange, now_iso

logger = logging.getLogger("ora.connected.seen")

SEEN = "connected_object_state"

# As long as the observations it feeds. A memory that outlived the signals
# would be a quiet archive of somebody's filing habits.
RETENTION_DAYS = 30


class SeenState:
    """The last observed shape of each object, per owner and source."""

    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[SEEN].create_index(
                [("owner_id", 1), ("source_id", 1), ("object_ref", 1)], unique=True
            )
            await self.db[SEEN].create_index("expires_at", expireAfterSeconds=0)
        except Exception:
            logger.exception("indici connected seen non creati (non fatale)")

    async def compare(
        self,
        owner_id: str,
        source_id: str,
        object_ref: str,
        *,
        observable: Dict[str, str],
        withheld: Tuple[str, ...] = (),
    ) -> Tuple[bool, List[FieldChange]]:
        """
        What is different since last time, and whether we had a last time.

        Returns `(seen_before, changes)`. The first is the honest answer to a
        question the caller must not guess at: an object we have never seen is
        new to *us*, which is not the same as new to the world, and only the
        caller knows which of those it is entitled to claim.

        Withheld fields are compared by a digest of their value rather than by
        the value, so "the note changed" is answerable without the note ever
        being written down.
        """
        row = await self._row(owner_id, source_id, object_ref)
        previous: Dict[str, str] = dict((row or {}).get("observed") or {})
        current = {
            field: (_digest(value) if field in withheld else str(value)[:160])
            for field, value in observable.items()
        }

        changes: List[FieldChange] = []
        if row is not None:
            for field, value in current.items():
                if previous.get(field, "") == value:
                    continue
                if field in withheld:
                    changes.append(FieldChange(field=field, content_withheld=True))
                else:
                    changes.append(FieldChange(
                        field=field,
                        before=previous.get(field, ""),
                        after=value,
                    ))
        return row is not None, sorted(changes, key=lambda c: c.field)

    async def remember(
        self,
        owner_id: str,
        source_id: str,
        object_ref: str,
        *,
        observable: Dict[str, str],
        withheld: Tuple[str, ...] = (),
    ) -> None:
        """Overwrite what we know this object looked like. One row, always."""
        observed = {
            field: (_digest(value) if field in withheld else str(value)[:160])
            for field, value in observable.items()
        }
        await self.db[SEEN].update_one(
            {"owner_id": owner_id, "source_id": source_id, "object_ref": object_ref},
            {"$set": {
                "owner_id": owner_id,
                "source_id": source_id,
                "object_ref": object_ref,
                "observed": observed,
                "seen_at": now_iso(),
                "expires_at": datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS),
            }},
            upsert=True,
        )

    async def _row(
        self, owner_id: str, source_id: str, object_ref: str
    ) -> Optional[Dict[str, Any]]:
        try:
            return await self.db[SEEN].find_one(
                {"owner_id": owner_id, "source_id": source_id,
                 "object_ref": object_ref},
                {"_id": 0},
            )
        except Exception as e:
            logger.info("seen read soft-fail: %s", type(e).__name__)
            return None

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[SEEN].delete_many({"owner_id": owner_id})
        return result.deleted_count


def _digest(value: Any) -> str:
    """
    Enough to tell whether something changed, not enough to reconstruct it.

    A private note becomes sixteen hex characters. Two readings of the same
    note match; a reading of a different note does not; and nobody who reads
    this collection learns what anybody wrote.
    """
    raw = str(value or "")
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
