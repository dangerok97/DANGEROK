"""
From "something moved" to "there is nothing to say", most of the time.

    A CHANGE EARNS A REVIEW, NOT ATTENTION.

This is the join between the domains and the judgement. A domain records that
a fact moved; this decides whether that is worth the cost of asking, hands the
question over, and takes whatever comes back — usually silence.

Everything expensive is guarded before the model is reached, and every guard
is mechanical:

* nothing pending, nothing to review;
* a batch, not a review per change;
* a cooldown, so a burst cannot become a burst of questions;
* a fingerprint of the facts, so the same question is not asked twice.

None of those is a relevance judgement, and none of them can become one. They
answer "would the model be asked something it has already answered?" — never
"does this matter?", which is not a question code is allowed to have an
opinion about.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from opportunities.changes import ChangeLog, MeaningfulChange, fingerprint
from opportunities.models import ScanResult

logger = logging.getLogger(__name__)

# Why a review ran. Technical, every one of them: none of these means there is
# something to say, and a scan started for any of them usually ends in silence.
ScanReason = Literal[
    "initial_review",
    "state_changed",
    "opportunity_recheck",
    "user_requested",
]

# Two reviews closer together than this are one review. Deliberately short —
# this exists to absorb bursts, not to make ORA slow to notice things.
COOLDOWN_SECONDS = 120

STATE = "opportunity_scan_state"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DiscoveryResult(BaseModel):
    """What a review attempt did, including deciding not to be one."""

    ran: bool = False
    reason: ScanReason = "state_changed"
    skipped: str = ""
    changes_reviewed: int = 0
    scan: Optional[ScanResult] = None

    @property
    def unavailable(self) -> bool:
        return bool(self.scan and self.scan.unavailable)


class OpportunityDiscovery:
    """Continuous review, without a second orchestrator to run it."""

    def __init__(self, db):
        self.db = db
        self.changes = ChangeLog(db)

    async def ensure_indexes(self) -> None:
        await self.changes.ensure_indexes()
        try:
            await self.db[STATE].create_index("owner_id", unique=True)
        except Exception:
            logger.exception("indice opportunity_scan_state non creato (non fatale)")

    async def note(
        self,
        owner_id: str,
        *,
        source: str,
        kind: str,
        entity_ref: str = "",
        entity_kind: str = "",
        before: str = "",
        after: str = "",
        occurred_at: Optional[str] = None,
        wake: bool = True,
    ) -> Dict[str, Any]:
        """
        A domain saying that something moved.

        Never raises and never blocks anything: it is called from the request
        path right after a life mutation, and saving a document must not fail
        because the reasoning pipeline is busy. Recording the change is the
        durable part; the wake-up that follows is only an accelerator.
        """
        admission = await self.changes.record(
            owner_id,
            source=source,
            kind=kind,
            entity_ref=entity_ref,
            entity_kind=entity_kind,
            before=before,
            after=after,
            occurred_at=occurred_at,
        )

        if wake and admission.outcome in ("accepted", "coalesced"):
            try:
                from life_orchestration.scheduler import schedule_user_reasoning

                # The existing wake-up, not a second one. It already coalesces
                # per user, and a life change worth a reasoning pass is a life
                # change worth an opportunity review.
                await schedule_user_reasoning(owner_id, reason="opportunity_change")
            except Exception as e:
                logger.info("wake soft-fail: %s", type(e).__name__)

        return {"outcome": admission.outcome, "reason": admission.reason}

    async def review(
        self,
        owner_id: str,
        *,
        reason: ScanReason = "state_changed",
        force: bool = False,
        language: str = "it",
    ) -> DiscoveryResult:
        """
        Look at this life again, if looking again could tell us anything new.
        """
        from opportunities import snapshot as life_snapshot
        from opportunities.service import OpportunityService

        pending = await self.changes.pending(owner_id)
        if not pending and not force:
            return DiscoveryResult(reason=reason, skipped="niente è cambiato")

        state = await self._state(owner_id)

        if not force and self._cooling(state):
            # The changes stay pending: the next review takes them.
            return DiscoveryResult(
                reason=reason, skipped="una revisione è appena avvenuta"
            )

        snapshot = await life_snapshot.build(self.db, owner_id)
        print_ = fingerprint(snapshot)
        if not force and print_ == (state.get("fingerprint") or ""):
            # The facts are the ones the model has already read. Asking again
            # would buy a second copy of an answer we have.
            await self.changes.claim(owner_id, "no_semantic_delta")
            await self._remember(owner_id, fingerprint=print_)
            return DiscoveryResult(
                reason=reason,
                skipped="i fatti sono gli stessi già valutati",
                changes_reviewed=len(pending),
            )

        scan_id = f"scn_{uuid.uuid4().hex[:12]}"
        batch = await self.changes.claim(owner_id, scan_id)

        scan = await OpportunityService(self.db).scan(
            owner_id,
            changes=[c.for_ai() for c in batch],
            language=language,
            source_context=reason,
        )

        if scan.unavailable:
            # Nothing was read, so nothing has been reviewed. Putting the batch
            # back is the difference between "we looked and there was nothing"
            # and "we never looked" — and only one of those is true.
            await self.changes.release(owner_id, batch)
            return DiscoveryResult(
                ran=True, reason=reason, changes_reviewed=len(batch), scan=scan
            )

        await self._remember(owner_id, fingerprint=print_)
        return DiscoveryResult(
            ran=True, reason=reason, changes_reviewed=len(batch), scan=scan
        )

    # --- the little state this needs -------------------------------------

    async def _state(self, owner_id: str) -> Dict[str, Any]:
        try:
            return await self.db[STATE].find_one({"owner_id": owner_id}, {"_id": 0}) or {}
        except Exception:
            return {}

    def _cooling(self, state: Dict[str, Any]) -> bool:
        last = state.get("last_scan_at")
        if not last:
            return False
        try:
            when = datetime.fromisoformat(str(last))
        except ValueError:
            return False
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return (_now() - when) < timedelta(seconds=COOLDOWN_SECONDS)

    async def _remember(self, owner_id: str, *, fingerprint: str) -> None:
        try:
            await self.db[STATE].update_one(
                {"owner_id": owner_id},
                {"$set": {"last_scan_at": _now().isoformat(), "fingerprint": fingerprint}},
                upsert=True,
            )
        except Exception as e:
            logger.info("scan state write soft-fail: %s", type(e).__name__)

    async def forget_all(self, owner_id: str) -> Dict[str, int]:
        removed = await self.changes.forget_all(owner_id)
        try:
            await self.db[STATE].delete_many({"owner_id": owner_id})
        except Exception:
            pass
        return {"changes_deleted": removed}
