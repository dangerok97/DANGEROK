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
import json
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
        from agent.memory_fence import memory_result_current

        memory_snapshot = str(what_happened.get("_memory_source_snapshot") or "")
        if not await memory_result_current(self.db, owner_id, goal, memory_snapshot):
            return VisibilityDecision(goal_id=goal.id, outcome="silent", decided_by="code",
                                      quietened_by_code="le memorie di partenza non sono più attuali")

        answer = await decide_visibility(
            goal.for_ai(),
            what_happened={key: value for key, value in what_happened.items()
                           if key != "_memory_source_snapshot"},
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
            memory_source_snapshot=memory_snapshot,
            fingerprint=_fingerprint(
                goal.id, str(answer.get("about") or ""),
                str(answer.get("headline") or ""),
            ),
        )

        if not decision.is_visible:
            return decision

        if not await memory_result_current(self.db, owner_id, goal, decision.memory_source_snapshot):
            decision.outcome, decision.decided_by = "silent", "code"
            decision.quietened_by_code = "le memorie di partenza non sono più attuali"
            return decision

        if not await self._situation_decision_current(
            owner_id, goal, decision, bind=True,
            topic=str(answer.get("about") or ""),
        ):
            decision.outcome = "silent"
            decision.decided_by = "code"
            decision.quietened_by_code = "la valutazione della situazione non è più attuale"
            return decision

        if not decision.headline:
            # Something to show, and nothing to show. Whatever went wrong,
            # an empty line on a screen is worse than no line.
            decision.outcome = "silent"
            decision.decided_by = "code"
            decision.quietened_by_code = "non c'era niente da dire"
            return decision

        if memory_snapshot:
            # A corrected fact may yield useful news about the same topic.
            decision.fingerprint = _fingerprint(
                goal.id + "|" + memory_snapshot, str(answer.get("about") or ""), decision.headline,
            )

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

    async def _situation_decision_current(
        self, owner_id, goal, decision, *, bind=False, topic="",
    ) -> bool:
        """The outbox may carry only the exact current Situation judgement.

        Bind before recording, then verify the same result before each Home
        handoff. An older pending update must never borrow a newer assessment
        or replay the model's unvalidated weather recap after a restart.
        """
        watched = goal.source_kind in ("situation_initial_review", "situation_followup")
        bound_refs = [ref for ref in decision.refs
                      if ref.startswith(("situation_outcome:", "situation_revision:"))]
        if not watched and not bound_refs:
            return True

        from agent.repository import AgentRepository
        from agent.source_refresh import changed
        from situations.outcomes import current_outcome, moment, outcome_refs, situation_id

        current = await AgentRepository(self.db).get_goal(owner_id, goal.id)
        if (current is None or current.owner_id != owner_id
                or current.source_kind not in ("situation_initial_review", "situation_followup")
                or situation_id(current) != situation_id(goal)
                or current.source_situation.get("situation_revision")
                != goal.source_situation.get("situation_revision")):
            return False
        assessment = await current_outcome(self.db, owner_id, current, allow_settled=True)
        if assessment:
            refs = outcome_refs(assessment)
            # The judgement must concern the assessment it was actually shown.
            # Replays use an even stronger exact wording/reference match.
            if f"situation_outcome:{assessment['id']}" not in decision.refs:
                return False
            if not bind:
                return (set(decision.refs) == set(refs)
                        and decision.headline == assessment["headline"][:200])
            decision.headline = assessment["headline"][:200]
            decision.reasoning = assessment["action_summary"] or decision.headline
            decision.refs = refs
            # The model still recognises semantic repetition. A changed action
            # or time window cannot collide with an earlier estimate merely
            # because it used the same short topic description.
            structure = {key: assessment.get(key) for key in (
                "assessment_revision", "status", "basis", "action_reason",
            )}
            for key in ("window_start", "window_end"):
                instant = moment(assessment.get(key))
                structure[key] = instant.astimezone(timezone.utc).isoformat() if instant else None
            decision.fingerprint = _fingerprint(
                goal.id + "|" + json.dumps(structure, sort_keys=True), topic, decision.headline,
            )
            return True

        # A concrete unresolved question may be communicated without an
        # estimate, but it must stop with this exact owned attention revision.
        if (bound_refs and any(ref.startswith("situation_outcome:") for ref in bound_refs)
                or not current.is_open
                or not (current.requires_user_input or current.requires_user_authority)
                or await changed(self.db, current)):
            return False
        sid = situation_id(current)
        revision = current.source_situation.get("situation_revision")
        if not sid or not revision:
            return False
        ref = f"situation_revision:{sid}:{revision}"
        if bind:
            decision.refs = [ref, *[value for value in decision.refs if value != ref]][:8]
            decision.fingerprint = _fingerprint(goal.id + "|" + ref, topic, decision.headline)
            return True
        return ref in decision.refs

    async def recent(self, owner_id: str) -> List[Dict[str, Any]]:
        """What they have already been told, so the model can hear itself."""
        docs = await self.db[UPDATES].find(
            {"owner_id": owner_id},
            {"_id": 0, "headline": 1, "outcome": 1, "at": 1,
             "goal_id": 1, "memory_source_snapshot": 1},
        ).sort("at", -1).to_list(RECENT_SHOWN)
        from agent.memory_fence import memory_result_current, MemorySourcesUnavailable
        from agent.repository import AgentRepository

        rows = []
        for doc in docs:
            goal = await AgentRepository(self.db).get_goal(owner_id, doc.get("goal_id", ""))
            if goal is None:
                continue
            try:
                if not await memory_result_current(
                    self.db, owner_id, goal, doc.get("memory_source_snapshot", ""),
                ):
                    continue
            except MemorySourcesUnavailable:
                continue
            rows.append({"said": doc.get("headline"), "kind": doc.get("outcome"), "when": doc.get("at")})
        return rows

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
            from agent.memory_fence import memory_result_current
            if not await memory_result_current(self.db, owner_id, goal, decision.memory_source_snapshot):
                await self.db[UPDATES].update_one(
                    {"owner_id": owner_id, "fingerprint": decision.fingerprint, "home_pending": True},
                    {"$set": {"home_pending": False, "home_skipped": "memory_sources_changed"},
                     "$unset": {"home_due_at": ""}},
                )
                return False
            if not await self._situation_decision_current(owner_id, goal, decision):
                await self.db[UPDATES].update_one(
                    {"owner_id": owner_id, "fingerprint": decision.fingerprint,
                     "home_pending": True},
                    {"$set": {"home_pending": False,
                              "home_skipped": "situation_no_longer_current"},
                     "$unset": {"home_due_at": ""}},
                )
                return False
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
                    "memory_source_snapshot": decision.memory_source_snapshot,
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
                    skipped = await self.db[UPDATES].find_one(
                        {"owner_id": owner, "fingerprint": fingerprint,
                         "home_skipped": {"$in": ["situation_no_longer_current", "memory_sources_changed"]}}, {"_id": 1},
                    )
                    results["stale" if skipped else "deferred"] += 1
            except Exception as exc:
                logger.info("home outbox deferred: %s", type(exc).__name__)
                results["deferred"] += 1
        return results

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[UPDATES].delete_many({"owner_id": owner_id})
        return result.deleted_count
