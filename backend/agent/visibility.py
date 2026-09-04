"""
Whether the work ORA just did is worth showing, and saying it only once.

    ORA SHOULD SPEAK WHEN SPEAKING IS USEFUL.
    ORA SHOULD STAY SILENT ONLY WHEN SILENCE IS BETTER.
    THE AGENT SHOULD NOT HIDE USEFUL WORK.

V3.8 answered whether to interrupt somebody. This answers a question that had
quietly been folded into that one: whether it is worth them knowing at all.
The two come apart in the case that matters most — ORA did something genuinely
useful and there is no reason to buzz anybody's phone about it. Under one
question that work vanishes; under two it appears quietly on a screen the
person looks at when they choose to.

The model decides worth. Code guarantees four things, and all four only ever
make ORA say *less*:

**Nothing visible without proof.** An update that cannot point back at a
journal line or a piece of evidence is refused, because a system that can say
"I looked into it" with nothing behind it will eventually say it with nothing
behind it.

**Nothing said twice.** The same news, recognised by what it is about rather
than by how it was worded, is said once.

**No status shortcut.** There is no branch here from a goal's state to a
visibility. A completed goal is not automatically worth mentioning and a
waiting one is not automatically a question — that is exactly the judgement
being bought.

**No channel.** Nothing here decides push, or in-app, or timing. It records
that something is worth seeing and leaves the interrupting to the policy that
already owns it.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.models import VisibilityDecision

logger = logging.getLogger(__name__)

UPDATES = "agent_updates"

# How long a said thing counts as already said. Long enough that a goal
# revisited three times in an afternoon does not announce itself three times;
# short enough that genuinely recurring news is allowed to recur.
SAID_RETENTION_DAYS = 14

# How many previous updates the model is shown. Enough to recognise itself
# repeating; not a transcript of the relationship.
RECENT_SHOWN = 6


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(goal_id: str, about: str, headline: str) -> str:
    """
    What this update is *about*, reduced to something comparable.

    Deliberately not a hash of the sentence: the same news phrased two ways
    is the same news, and a model asked twice will phrase it twice. Built
    from the goal and the model's own short description of the subject, with
    the wording as a fallback when it declined to give one.
    """
    basis = (about or headline or "").lower()
    basis = re.sub(r"[^\w\s]", " ", basis)
    basis = " ".join(sorted(set(basis.split())))[:200]
    return hashlib.sha256(f"{goal_id}|{basis}".encode("utf-8")).hexdigest()[:32]


class VisibilityService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[UPDATES].create_index([("owner_id", 1), ("at", -1)])
            await self.db[UPDATES].create_index(
                [("owner_id", 1), ("fingerprint", 1)], unique=True
            )
            await self.db[UPDATES].create_index("expires_at", expireAfterSeconds=0)
        except Exception:
            logger.exception("indici visibilità non creati (non fatale)")

    async def consider(
        self, owner_id: str, goal, *, what_happened: Dict[str, Any],
        language: str = "it",
    ) -> VisibilityDecision:
        """
        Ask whether this is worth showing, then hold the answer to its word.

        Returns `silent` for every kind of not-showing there is, including
        the ones code decided: no answer, no proof, already said. The caller
        does not need to tell them apart, and a surface certainly does not.
        """
        from agent.reasoning import decide_visibility

        answer = await decide_visibility(
            goal.for_ai(),
            what_happened=what_happened,
            already_said=await self.recent(owner_id),
            language=language,
        )
        if answer is None:
            # No judgement. Saying nothing is the safe direction, and it is
            # not recorded as a decision that there was nothing to say.
            return VisibilityDecision(
                goal_id=goal.id, outcome="silent", decided_by="code",
                quietened_by_code="il giudizio non era disponibile",
            )

        decision = VisibilityDecision(
            goal_id=goal.id,
            outcome=answer["outcome"],
            headline=str(answer.get("headline") or "")[:200].strip(),
            reasoning=str(answer.get("reasoning") or "")[:400],
            refs=[str(r)[:120] for r in (what_happened.get("refs") or [])][:8],
            fingerprint=_fingerprint(
                goal.id, str(answer.get("about") or ""),
                str(answer.get("headline") or ""),
            ),
        )

        if not decision.is_visible:
            return decision

        if not decision.headline:
            # Something to show, and nothing to show. Whatever went wrong,
            # an empty line on a screen is worse than no line.
            decision.outcome = "silent"
            decision.decided_by = "code"
            decision.quietened_by_code = "non c'era niente da dire"
            return decision

        if not decision.refs:
            # No proof of work. This is the guard that stops «me ne sto
            # occupando» from ever being generated by a system that was not.
            decision.outcome = "silent"
            decision.decided_by = "code"
            decision.quietened_by_code = "nessuna prova dietro l'aggiornamento"
            logger.info("visibility refused: no proof goal=%s", goal.id)
            return decision

        if await self._already_said(owner_id, decision.fingerprint):
            decision.outcome = "silent"
            decision.decided_by = "code"
            decision.quietened_by_code = "questa cosa era già stata detta"
            return decision

        await self._record(owner_id, decision)
        return decision

    async def recent(self, owner_id: str) -> List[Dict[str, Any]]:
        """What they have already been told, so the model can hear itself."""
        docs = await self.db[UPDATES].find(
            {"owner_id": owner_id},
            {"_id": 0, "headline": 1, "outcome": 1, "at": 1},
        ).sort("at", -1).to_list(RECENT_SHOWN)
        return [
            {"said": d.get("headline"), "kind": d.get("outcome"), "when": d.get("at")}
            for d in docs
        ]

    async def _already_said(self, owner_id: str, fingerprint: str) -> bool:
        found = await self.db[UPDATES].find_one(
            {"owner_id": owner_id, "fingerprint": fingerprint}, {"_id": 0, "at": 1}
        )
        return found is not None

    async def _record(self, owner_id: str, decision: VisibilityDecision) -> None:
        row = decision.model_dump()
        row["owner_id"] = owner_id
        row["expires_at"] = _now() + timedelta(days=SAID_RETENTION_DAYS)
        try:
            await self.db[UPDATES].insert_one(row)
        except Exception as e:
            # A duplicate here is the fingerprint working under a race, which
            # is what it is for.
            logger.info("visibility record: %s", type(e).__name__)

    async def show(self, owner_id: str, goal, decision: VisibilityDecision) -> bool:
        """
        Hand a visible update to the channel that already exists.

            VISIBILITY IS NOT A DELIVERY MODE.

        The quiet channel — the line on Home that somebody finds when they
        look — is V3.8's `AmbientActivity`, used as it stands. Nothing here
        sends, schedules, or pushes: whether anything interrupts is decided
        by the delivery policy, on its own terms, and there is deliberately
        no argument to this function that could ask it to.
        """
        if not decision.is_visible or not decision.headline:
            return False
        try:
            from delivery.service import DeliveryService

            await DeliveryService(self.db).note_activity(
                owner_id,
                kind="review_completed",
                summary=decision.headline,
                source_refs=[goal.id] + list(decision.refs)[:6],
                provenance={
                    "agent": "visibility",
                    "visibility": decision.outcome,
                    "goal": goal.id,
                },
                visible=True,
            )
            return True
        except Exception as e:
            logger.info("visibility surface soft-fail: %s", type(e).__name__)
            return False

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[UPDATES].delete_many({"owner_id": owner_id})
        return result.deleted_count
