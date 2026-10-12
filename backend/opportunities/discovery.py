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

from opportunities.changes import CLAIM_LEASE_SECONDS, ChangeLog, MeaningfulChange, fingerprint
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
    retry_after_seconds: Optional[int] = None
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
        scheduled: bool = False,
        language: str = "it",
    ) -> DiscoveryResult:
        """
        Look at this life again, if looking again could tell us anything new.
        """
        from opportunities import snapshot as life_snapshot
        from opportunities.service import OpportunityService

        pending = await self.changes.pending(owner_id)
        state = await self._state(owner_id)
        if str(state.get("lease_until") or "") > _now().isoformat():
            return DiscoveryResult(reason=reason, skipped="una revisione è già in corso",
                                   retry_after_seconds=CLAIM_LEASE_SECONDS)
        if not pending and not force and not scheduled:
            return DiscoveryResult(reason=reason, skipped="niente è cambiato")
        if not force and self._cooling(state):
            return DiscoveryResult(reason=reason, skipped="una revisione è appena avvenuta",
                                   retry_after_seconds=COOLDOWN_SECONDS)

        scan_id = f"scn_{uuid.uuid4().hex[:20]}"
        lease = await self._claim_scan(owner_id, scan_id)
        if lease is None:
            return DiscoveryResult(reason=reason, skipped="una revisione è già in corso",
                                   retry_after_seconds=CLAIM_LEASE_SECONDS)
        batch: List[MeaningfulChange] = []
        async def current() -> bool:
            return await self._scan_current(owner_id, scan_id)
        try:
            # Reserve before building the snapshot: a change that arrives while
            # the model is thinking stays pending for the next bounded review.
            batch = await self.changes.claim(owner_id, scan_id, lease_until=lease["lease_until"])
            if not batch and not force and not scheduled:
                return DiscoveryResult(reason=reason, skipped="niente è cambiato")

            if any(change.source == "places" for change in batch):
                try:
                    from places.service import PlacesService
                    await PlacesService(self.db).review_routines(owner_id, language=language)
                except Exception as exc:
                    logger.info("routine learning soft-fail: %s", type(exc).__name__)

            snapshot = await life_snapshot.build(self.db, owner_id, changes=[c.for_ai() for c in batch])
            print_ = fingerprint(snapshot)
            same_facts = (not force and not any(c.source == "communications" for c in batch)
                          and print_ == (lease.get("fingerprint") or ""))
            if same_facts:
                if not await self._remember(owner_id, scan_id=scan_id, fingerprint=print_):
                    return self._unavailable(reason, len(batch), "la revisione non è più corrente")
                if await self.changes.acknowledge(owner_id, batch) != len(batch):
                    return self._unavailable(reason, len(batch), "la conferma della revisione non è disponibile")
                return DiscoveryResult(reason=reason, skipped="i fatti sono gli stessi già valutati",
                                       changes_reviewed=len(batch))

            scan = await OpportunityService(self.db).scan(
                owner_id, changes=[c.for_ai() for c in batch], language=language,
                source_context=reason,
                prepared_snapshot={**snapshot, "what_changed": [c.for_ai() for c in batch]},
                claim_is_current=current,
            )
            if scan.unavailable:
                return DiscoveryResult(ran=True, reason=reason, changes_reviewed=len(batch), scan=scan)
            if not await self._remember(owner_id, scan_id=scan_id, fingerprint=print_):
                return self._unavailable(reason, len(batch), "la revisione non è più corrente")
            # Decisions (including a valid silence) are durable before this
            # acknowledgement. A failed acknowledgement can safely be replayed.
            if await self.changes.acknowledge(owner_id, batch) != len(batch):
                return self._unavailable(reason, len(batch), "la conferma della revisione non è disponibile")
            logger.info("opportunity_review outcome=%s changes=%d created=%d updated=%d",
                        "silence" if scan.silence else "opportunities", len(batch),
                        len(scan.created), len(scan.updated))
            return DiscoveryResult(ran=True, reason=reason, changes_reviewed=len(batch), scan=scan)
        except Exception as exc:
            logger.info("opportunity review interrupted error=%s", type(exc).__name__)
            return self._unavailable(reason, len(batch), "la revisione non è disponibile")
        finally:
            # Cancellation releases only our own claims; a hard process crash
            # is recovered by their expiry. Never clear a replacement's token.
            await self.changes.release(owner_id, batch)
            await self.db[STATE].update_one(
                {"owner_id": owner_id, "lease_token": scan_id},
                {"$unset": {"lease_token": "", "lease_until": ""}},
            )

    # --- the little state this needs -------------------------------------

    @staticmethod
    def _unavailable(reason, count, note) -> DiscoveryResult:
        return DiscoveryResult(ran=True, reason=reason, changes_reviewed=count,
                               scan=ScanResult(silence=True, unavailable=True, reason_for_silence=note))

    async def _claim_scan(self, owner_id: str, token: str) -> Optional[Dict[str, Any]]:
        from pymongo import ReturnDocument
        await self.db[STATE].update_one({"owner_id": owner_id}, {"$setOnInsert": {
            "owner_id": owner_id,
        }}, upsert=True)
        return await self.db[STATE].find_one_and_update(
            {"owner_id": owner_id, "$or": [
                {"lease_until": {"$exists": False}}, {"lease_until": {"$lte": _now().isoformat()}},
            ]},
            {"$set": {"lease_token": token,
                      "lease_until": (_now() + timedelta(seconds=CLAIM_LEASE_SECONDS)).isoformat()}},
            return_document=ReturnDocument.AFTER,
        )

    async def _scan_current(self, owner_id: str, token: str) -> bool:
        return bool(await self.db[STATE].find_one(
            {"owner_id": owner_id, "lease_token": token, "lease_until": {"$gt": _now().isoformat()}},
            {"_id": 1},
        ))

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

    async def _remember(self, owner_id: str, *, scan_id: str, fingerprint: str) -> bool:
        try:
            saved = await self.db[STATE].update_one(
                {"owner_id": owner_id, "lease_token": scan_id, "lease_until": {"$gt": _now().isoformat()}},
                {"$set": {"last_scan_at": _now().isoformat(), "fingerprint": fingerprint}},
            )
            return bool(saved.matched_count)
        except Exception as e:
            logger.info("scan state write soft-fail: %s", type(e).__name__)
            return False

    async def forget_all(self, owner_id: str) -> Dict[str, int]:
        removed = await self.changes.forget_all(owner_id)
        try:
            await self.db[STATE].delete_many({"owner_id": owner_id})
        except Exception:
            pass
        return {"changes_deleted": removed}
