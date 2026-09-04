"""
When ORA needs a person, and what happens to that need afterwards.

    THE AGENT DECIDES THAT COMMUNICATION MAY BE NEEDED.
    DELIVERY DECIDES WHETHER, WHEN AND HOW TO REACH THE PERSON.
    A WAKE-UP IS NOT PERMISSION TO INTERRUPT.

The gap this closes is narrow and it matters. Until now an agent that got
stuck could only be *seen* — by somebody who happened to open the app. That is
right for "I found something useful" and wrong for "everything is ready and I
need one word from you": a person who does not come back never learns that ORA
is waiting on them, and the agent that manages the work ends up managed by the
user's habits.

Three things this file will not do.

It will not **invent an opportunity**. That was the three-line version — raise
a fake concern so the existing path carries it — and it is a lie: an
opportunity is something ORA noticed about a life, and being stuck is not
that. Delivery learned to weigh two kinds of subject instead.

It will not **choose a channel**. There is no push here, no in-app, no timing.
A need says somebody may be wanted; V3.8 decides whether that is worth an
interruption, and is free to decide never.

And it will not **forget**. A delivery held, silenced or cancelled changes
nothing about whether the agent is still blocked. `no push` is not `resolved`,
and the day those two collapse into one is the day ORA quietly stops asking
for things it needs.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.models import CommunicationNeed

logger = logging.getLogger(__name__)

NEEDS = "agent_needs"

# How long a need that nobody settled stays open before it is stale. Long
# enough for a question asked on Friday to still be waiting on Monday; short
# enough that a goal nobody will ever answer stops asking.
NEED_HORIZON_DAYS = 21

# Which needs are actually asking for something back.
_ASKING = {"needs_information", "needs_authority"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(goal_id: str, kind: str, blocker: str) -> str:
    """
    The same blocker, recognised again.

    Built from what is blocked rather than from how it was worded: asked
    twice, a model phrases it twice, and «mi serve il comune» five times in an
    afternoon is the failure this exists to prevent. Word order and
    punctuation are dropped for the same reason.
    """
    basis = re.sub(r"[^\w\s]", " ", (blocker or "").lower())
    basis = " ".join(sorted(set(basis.split())))[:200]
    return hashlib.sha256(f"{goal_id}|{kind}|{basis}".encode("utf-8")).hexdigest()[:32]


class NeedService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[NEEDS].create_index("id", unique=True)
            await self.db[NEEDS].create_index([("owner_id", 1), ("status", 1)])
            await self.db[NEEDS].create_index([("owner_id", 1), ("goal_id", 1)])
            # One open need per blocker, enforced by the database. Two workers
            # reaching the same blocked goal at the same moment is ordinary,
            # and the loser has to lose in the storage rather than in a check
            # that races.
            await self.db[NEEDS].create_index(
                [("owner_id", 1), ("fingerprint", 1)],
                unique=True,
                partialFilterExpression={"status": "open"},
            )
        except Exception:
            logger.exception("indici needs non creati (non fatale)")

    # --- raising ----------------------------------------------------------

    async def raise_need(self, need: CommunicationNeed) -> CommunicationNeed:
        """
        Record that somebody may be wanted, unless that is already recorded.

        Returns the existing need when there is one, updated with the newest
        wording — the blocker has not changed, so it is not news, but the way
        ORA would put it now is the way it should be put.
        """
        if not need.fingerprint:
            need.fingerprint = fingerprint(
                need.goal_id, need.kind, need.what_is_missing or need.summary
            )
        if need.valid_until is None:
            need.valid_until = (
                _now() + timedelta(days=NEED_HORIZON_DAYS)
            ).isoformat()
        need.requires_response = need.requires_response or need.kind in _ASKING

        existing = await self.open_by_fingerprint(need.owner_id, need.fingerprint)
        if existing is not None:
            existing.summary = need.summary or existing.summary
            existing.reason = need.reason or existing.reason
            existing.work_already_done = (
                need.work_already_done or existing.work_already_done
            )
            existing.what_is_missing = need.what_is_missing or existing.what_is_missing
            existing.touch()
            await self._save(existing)
            return existing

        try:
            await self.db[NEEDS].insert_one(need.model_dump())
        except Exception as exc:
            if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
                # Somebody else got there first, which is what the index is
                # for. Theirs is the need; this one never existed.
                found = await self.open_by_fingerprint(need.owner_id, need.fingerprint)
                if found is not None:
                    return found
            logger.info("need create soft-fail: %s", type(exc).__name__)
        return need

    # --- reading ----------------------------------------------------------

    async def get(self, owner_id: str, need_id: str) -> Optional[CommunicationNeed]:
        doc = await self.db[NEEDS].find_one(
            {"id": need_id, "owner_id": owner_id}, {"_id": 0}
        )
        return CommunicationNeed.model_validate(doc) if doc else None

    async def open_by_fingerprint(
        self, owner_id: str, fp: str
    ) -> Optional[CommunicationNeed]:
        doc = await self.db[NEEDS].find_one(
            {"owner_id": owner_id, "fingerprint": fp, "status": "open"}, {"_id": 0}
        )
        return CommunicationNeed.model_validate(doc) if doc else None

    async def open_for_goal(
        self, owner_id: str, goal_id: str
    ) -> List[CommunicationNeed]:
        docs = await self.db[NEEDS].find(
            {"owner_id": owner_id, "goal_id": goal_id, "status": "open"}, {"_id": 0}
        ).sort("created_at", 1).to_list(10)
        return [CommunicationNeed.model_validate(d) for d in docs]

    async def open_needs(self, owner_id: str, *, limit: int = 10) -> List[CommunicationNeed]:
        docs = await self.db[NEEDS].find(
            {"owner_id": owner_id, "status": "open"}, {"_id": 0}
        ).sort("created_at", 1).to_list(limit)
        return [CommunicationNeed.model_validate(d) for d in docs]

    # --- settling ---------------------------------------------------------

    async def satisfy(
        self, owner_id: str, need_id: str, *, how: str = "", by: str = "user"
    ) -> Optional[CommunicationNeed]:
        """
        Somebody dealt with it.

            OPENING A NOTIFICATION IS NOT ANSWERING ONE.

        Reached from a reply, a grant, a refusal, or the agent no longer
        needing the thing. Deliberately not reachable from anything delivery
        does — a message being sent, delivered or opened says something about
        the message and nothing about the work.
        """
        return await self._settle(
            owner_id, need_id, status="satisfied", how=how, by=by
        )

    async def cancel(
        self, owner_id: str, need_id: str, *, how: str = "", by: str = "code"
    ) -> Optional[CommunicationNeed]:
        """Nobody has to answer this any more — which is not the same as an answer."""
        return await self._settle(
            owner_id, need_id, status="cancelled", how=how, by=by
        )

    async def _settle(
        self, owner_id: str, need_id: str, *, status: str, how: str, by: str
    ) -> Optional[CommunicationNeed]:
        need = await self.get(owner_id, need_id)
        if need is None or not need.is_open:
            return need

        need.status = status  # type: ignore[assignment]
        need.resolution = how[:200]
        need.provenance = by  # type: ignore[assignment]
        need.resolved_at = _now().isoformat()
        need.touch()
        await self._save(need)

        # The intention to say something about it goes; the record of what
        # happened stays. A plan for a question nobody is asking any more is a
        # notification that would arrive about nothing.
        await self._drop_plans(owner_id, need.id, why=how or "non serve più")
        return need

    async def close_for_goal(
        self, owner_id: str, goal_id: str, *, why: str, kinds: Optional[set] = None
    ) -> int:
        """
        A goal that ended, or moved on, takes the needs it raised with it.

        `kinds` narrows it to the ones that went stale rather than all of
        them: a goal that finished has no use for the question it was going to
        ask, but the result it already reported is history and stays.
        """
        closed = 0
        for need in await self.open_for_goal(owner_id, goal_id):
            if kinds is not None and need.kind not in kinds:
                continue
            await self.cancel(owner_id, need.id, how=why, by="code")
            closed += 1
        return closed

    async def _save(self, need: CommunicationNeed) -> None:
        await self.db[NEEDS].update_one(
            {"id": need.id}, {"$set": need.model_dump()}, upsert=True
        )

    async def _drop_plans(self, owner_id: str, need_id: str, *, why: str) -> None:
        try:
            from delivery.service import DeliveryService

            await DeliveryService(self.db).cancel_for_source(
                owner_id, need_id, source_type="agent_need", reason=why
            )
        except Exception as e:
            logger.info("need plan cancel soft-fail: %s", type(e).__name__)

    # --- handing it to the layer that decides -----------------------------

    async def offer_to_delivery(
        self, owner_id: str, need: CommunicationNeed, *, app_state: str = "unknown",
        language: str = "it",
    ) -> Optional[Any]:
        """
        Ask V3.8 whether this is worth reaching somebody about.

            REQUIRES_ATTENTION IS NOT PUSH.

        The answer is delivery's alone and every one of them is acceptable
        here, silence included. What is not acceptable is this function
        caring: there is no branch below on what came back, because the moment
        one exists somebody will add `if requires_attention: push()` beneath
        it.

        The need does not depend on the answer. It was open before and it is
        open after, however quiet delivery decides to be.
        """
        if not need.is_open:
            return None
        try:
            from delivery.models import DeliverySubject
            from delivery.service import DeliveryService

            # The goal travels with the subject so a tap can land on the
            # blocker rather than on the goal or, worse, on Home.
            subject = DeliverySubject.model_validate(need.as_subject())
            return await DeliveryService(self.db).evaluate_subject(
                owner_id, subject, app_state=app_state, language=language
            )
        except Exception as e:
            logger.info("need delivery soft-fail: %s", type(e).__name__)
            return None

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[NEEDS].delete_many({"owner_id": owner_id})
        return result.deleted_count
