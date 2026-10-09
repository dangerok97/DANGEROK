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
            await self.db[UPDATES].create_index([("home_pending", 1), ("home_due_at", 1)])
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
            moment_type=(
                answer.get("moment_type")
                if answer.get("moment_type") in ("action_now", "outcome_estimate")
                else "status_only"
            ),
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

        # The preliminary read is only an optimisation. Two workers may both
        # pass it before either one records the update. Only the successful
        # atomic insert owns the right to surface and offer this news.
        if not await self._record(owner_id, decision):
            decision.outcome = "silent"
            decision.decided_by = "code"
            decision.quietened_by_code = "aggiornamento già registrato o archivio non disponibile"
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

    async def _record(self, owner_id: str, decision: VisibilityDecision) -> bool:
        """Only the insert winner may create an activity or delivery need.

        Under concurrent workers both may read 'not said yet'. The unique
        owner/fingerprint index is the atomic decision, not the earlier read.
        On a database failure do not claim to have delivered an update.
        """
        row = decision.model_dump()
        row["owner_id"] = owner_id
        row["expires_at"] = _now() + timedelta(days=SAID_RETENTION_DAYS)
        # A visibility judgement is not yet evidence that Home can show it.
        # Store the Home handoff in the same atomic insert as the decision.
        # Older rows lack this field and are deliberately not backfilled.
        row["home_pending"] = True
        row["home_due_at"] = _now().isoformat()
        try:
            await self.db[UPDATES].insert_one(row)
            return True
        except Exception as exc:
            logger.info("visibility record deferred: %s", type(exc).__name__)
            return False

    async def show(self, owner_id: str, goal, decision: VisibilityDecision) -> bool:
        """Materialise an already persisted visibility decision exactly once.

        The update ledger is an outbox: if this process stops between its
        insert and the Home activity insert, the existing Ambient delivery
        lane can replay it. Activity identity is stable across retries.
        No AI call, push notification, or world-changing effect happens here.
        """
        if (not decision.is_visible or not decision.headline or not decision.refs
                or not decision.fingerprint or goal.owner_id != owner_id
                or goal.id != decision.goal_id):
            return False
        # A stable owner-scoped id makes the write safe if acknowledgement
        # fails after Mongo has already inserted the Activity.
        activity_id = "ambv_" + hashlib.sha256(
            f"{owner_id}|{decision.fingerprint}".encode("utf-8")
        ).hexdigest()[:24]
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
                activity_id=activity_id,
            )
            # This may fail after the Activity insert. Pending stays durable;
            # a future pass repeats the same idempotent write.
            await self.db[UPDATES].update_one(
                {"owner_id": owner_id, "fingerprint": decision.fingerprint,
                 "home_pending": True},
                {"$set": {"home_pending": False,
                          "home_delivered_at": _now().isoformat()},
                 "$unset": {"home_due_at": ""}},
            )
            return True
        except Exception as exc:
            logger.info("visibility surface recoverable: %s", type(exc).__name__)
            try:
                await self.db[UPDATES].update_one(
                    {"owner_id": owner_id, "fingerprint": decision.fingerprint,
                     "home_pending": True},
                    {"$set": {"home_due_at": (_now() + timedelta(minutes=2)).isoformat()}},
                )
            except Exception:
                pass  # DB outage: the original pending outbox entry remains.
            return False

    async def recover_pending_home(self, *, limit: int = 4) -> Dict[str, int]:
        """Bounded, owner-scoped Home outbox recovery in the existing lane.

        Reconstruct only a previously accepted visible decision. No model
        generates new claims during recovery, and no external delivery occurs.
        """
        limit = max(1, min(8, int(limit or 1)))
        stamp = _now().isoformat()
        rows = await self.db[UPDATES].find({
            "home_pending": True,
            "home_due_at": {"$type": "string", "$lte": stamp},
            "outcome": {"$ne": "silent"},
        }, {"_id": 0}).sort([("home_due_at", 1), ("at", 1)]).limit(limit).to_list(limit)
        results = {"checked": len(rows), "shown": 0, "deferred": 0, "stale": 0}
        from agent.models import AutonomousGoal

        for row in rows:
            owner = str(row.get("owner_id") or "")
            goal_id = str(row.get("goal_id") or "")
            fingerprint = str(row.get("fingerprint") or "")
            goal_doc = await self.db.agent_goals.find_one(
                {"id": goal_id, "owner_id": owner}, {"_id": 0},
            ) if owner and goal_id else None
            if not goal_doc or goal_doc.get("status") in ("cancelled", "abandoned"):
                await self.db[UPDATES].update_one(
                    {"owner_id": owner, "fingerprint": fingerprint, "home_pending": True},
                    {"$set": {"home_pending": False, "home_skipped": "goal_no_longer_valid"},
                     "$unset": {"home_due_at": ""}},
                )
                results["stale"] += 1
                continue
            try:
                decision = VisibilityDecision.model_validate(row)
                if (not decision.is_visible or not decision.headline or not decision.refs
                        or not decision.fingerprint):
                    raise ValueError("unusable_visibility_record")
                goal = AutonomousGoal.model_validate(goal_doc)
                if await self.show(owner, goal, decision):
                    results["shown"] += 1
                else:
                    results["deferred"] += 1
            except Exception as exc:
                logger.info("home outbox deferred: %s", type(exc).__name__)
                results["deferred"] += 1
        return results

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[UPDATES].delete_many({"owner_id": owner_id})
        return result.deleted_count
