"""Resume only the communication owed by one already completed piece of work.

The private checkpoint lives on the owned goal, before its terminal write.
Delivery admission gives a recovery one of its existing bounded review slots.
It never reopens a goal, executes its plan, or substitutes a visibility choice.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

from agent.models import AgentBudget, AgentRun, AutonomousGoal

FIELD = "completion_visibility"
logger = logging.getLogger(__name__)


class HandoffUnavailable(Exception):
    """The technical handoff, rather than the result, needs another check."""


class VisibilityUnavailable(HandoffUnavailable):
    """No model judgement was returned; this is not model-chosen silence."""


class HandoffSuperseded(HandoffUnavailable):
    """The same lease no longer names the completed result it was given."""


def _now():
    return datetime.now(timezone.utc)


def _binding(goal):
    from agent.prepared_review import prepared_result_ref

    material = {
        "owner_id": goal.owner_id, "goal_id": goal.id,
        "completed_at": goal.completed_at,
        "prepared_result": prepared_result_ref(goal),
        "situation_outcome": goal.situation_outcome.model_dump() if goal.situation_outcome else None,
        "source_kind": goal.source_kind, "source_refs": goal.source_refs,
        "source_situation": goal.source_situation,
        "opportunity_id": goal.opportunity_id, "opportunity_revision": goal.opportunity_revision,
        "objective": goal.objective, "desired_outcome": goal.desired_outcome,
        "success_criteria": goal.success_criteria,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def stage(db, owner, goal, run, budget, *, language="it"):
    """A failed or superseded terminal CAS cannot activate this checkpoint."""
    from agent.visibility import SAID_RETENTION_DAYS

    binding = _binding(goal)
    identity = hashlib.sha256(f"{owner}:{goal.id}:{run.id}:{binding}".encode()).hexdigest()[:24]
    now = _now()
    state = {
        "id": identity, "pending": True, "due_at": now.isoformat(),
        "expires_at": (now + timedelta(days=SAID_RETENTION_DAYS)).isoformat(),
        "completed_at": goal.completed_at, "binding": binding,
        "run": run.model_dump(), "language": language[:12], "attempts": 0,
        "visibility_limit": max(0, min(1, budget.max_visibility_calls - budget.visibility_calls)),
        "state": "pending",
    }
    result = await db.agent_goals.update_one({
        "id": goal.id, "owner_id": owner, "status": {"$in": ["active", "waiting", "proposed"]},
    }, {"$set": {FIELD: state}})
    return bool(result.matched_count)


def _query(moment, *, owners_seen=None, candidate=None):
    query = {
        "status": "completed", f"{FIELD}.pending": True,
        f"{FIELD}.due_at": {"$type": "string", "$lte": moment.isoformat()},
        "$or": [{f"{FIELD}.lease_until": {"$exists": False}},
                {f"{FIELD}.lease_until": {"$lte": moment.isoformat()}}],
    }
    if owners_seen:
        query["owner_id"] = {"$nin": sorted(owners_seen)}
    if candidate is not None:
        query.update(id=candidate["id"], owner_id=candidate["owner_id"])
        query[f"{FIELD}.due_at"] = {"$eq": candidate["due_at"], "$lte": moment.isoformat(), "$type": "string"}
    return query


async def next_due(db, *, now=None, owners_seen=None, allow_owner_fallback=True):
    moment = now or _now()
    projection = {"_id": 0, "id": 1, "owner_id": 1, f"{FIELD}.due_at": 1}
    row = await db.agent_goals.find_one(
        _query(moment, owners_seen=owners_seen), projection,
        sort=[(f"{FIELD}.due_at", 1), ("id", 1)],
    )
    if row is None and owners_seen and allow_owner_fallback:
        row = await db.agent_goals.find_one(_query(moment), projection,
            sort=[(f"{FIELD}.due_at", 1), ("id", 1)])
    return {"id": row["id"], "owner_id": row["owner_id"],
            "due_at": row[FIELD]["due_at"]} if row else None


class CompletionHandoff:
    def __init__(self, db, row):
        self.db, self.owner, self.goal_id = db, row["owner_id"], row["id"]
        self.state = row[FIELD]
        self.id, self.token = self.state["id"], self.state["token"]

    def query(self):
        return {"id": self.goal_id, "owner_id": self.owner,
                f"{FIELD}.id": self.id, f"{FIELD}.token": self.token,
                f"{FIELD}.pending": True,
                f"{FIELD}.lease_until": {"$gt": _now().isoformat()}}

    async def _checked_row(self):
        row = await self.db.agent_goals.find_one(self.query(), {"_id": 0})
        if row is None:
            raise HandoffUnavailable("completion_handoff_lease_changed")
        goal = AutonomousGoal.model_validate(row)
        if (goal.status != "completed" or goal.completed_at != self.state["completed_at"]
                or _binding(goal) != self.state["binding"]):
            raise HandoffSuperseded("completion_result_changed")
        return row, goal

    async def check(self):
        await self._checked_row()

    async def save(self, **values):
        query = self.query()
        if not (values.get("pending") is False and values.get("state") == "stale"):
            from agent.prepared_review import capture_prepared_result

            row, goal = await self._checked_row()
            snapshot = capture_prepared_result(goal)
            fields = {
                "status", "completed_at", "situation_outcome", "source_kind", "source_refs",
                "source_situation", "opportunity_id", "opportunity_revision", "objective",
                "desired_outcome", "success_criteria", "prepared_text", "prepared_sources",
                "prepared_result_id", *(snapshot.context if snapshot else ()),
            }
            # The read proves the digest; this exact-field CAS also closes
            # the interval before the candidate/ack is persisted. A missing
            # legacy field remains missing, not an inferred default.
            query["$and"] = [{field: row[field] if field in row else {"$exists": False}}
                             for field in sorted(fields)]
        result = await self.db.agent_goals.update_one(
            query, {"$set": {f"{FIELD}.{key}": value for key, value in values.items()}},
        )
        if not result.matched_count:
            raise HandoffUnavailable("completion_handoff_lease_changed")
        self.state.update(values)

    async def current(self):
        from agent.memory_fence import inspect_memory_sources
        from agent.result_sources import opportunity_result_current
        from agent.visibility import prepared_communication_current
        from agent.prepared_review import prepared_result_ref
        from situations.outcomes import current_outcome, moment

        _, goal = await self._checked_row()
        retained_until = moment(self.state.get("expires_at"))
        if retained_until is None or retained_until <= _now():
            return None
        expiry = moment(goal.valid_until)
        if goal.valid_until and (expiry is None or expiry <= _now()):
            return None
        if (await inspect_memory_sources(self.db, self.owner, goal)).status != "current":
            return None
        if not await opportunity_result_current(self.db, self.owner, goal, now=_now()):
            return None
        if not await prepared_communication_current(
            self.db, self.owner, goal.id, prepared_result_ref(goal), question=False,
        ):
            return None
        if goal.source_kind in ("situation_initial_review", "situation_followup"):
            if not await current_outcome(self.db, self.owner, goal, allow_settled=True):
                return None
        return goal

    async def defer(self):
        from delivery.admission import MAX_ATTEMPTS

        attempts = self.state["attempts"]
        replayable = bool(self.state.get("candidate") or self.state.get("decision"))
        pending = attempts < MAX_ATTEMPTS or replayable
        await self.save(pending=pending, state="pending" if pending else "paused",
            due_at=(_now() + timedelta(seconds=60 if attempts <= 1 else 300)).isoformat() if pending else None,
            error_kind="temporarily_unavailable")


async def _claim(db, candidate, moment):
    from delivery.admission import LEASE_SECONDS, MAX_ATTEMPTS

    query = _query(moment, candidate=candidate)
    # The nested lease/token is on the same document as the checkpoint. A
    # worker whose lease expires cannot overwrite a later handoff or its ack.
    return await db.agent_goals.find_one_and_update(query, [{"$set": {
        f"{FIELD}.token": uuid.uuid4().hex,
        f"{FIELD}.lease_until": (moment + timedelta(seconds=LEASE_SECONDS)).isoformat(),
        f"{FIELD}.recovery_only": {"$gte": [f"${FIELD}.attempts", MAX_ATTEMPTS]},
        f"{FIELD}.attempts": {"$min": [MAX_ATTEMPTS, {"$add": [f"${FIELD}.attempts", 1]}]},
    }}], return_document=ReturnDocument.AFTER)


async def _process(db, row, *, service=None, budget=None, offer_delivery=False):
    from agent.service import AgentService

    handoff = CompletionHandoff(db, row)
    try:
        goal = await handoff.current()
        if goal is None:
            await handoff.save(pending=False, due_at=None, state="stale")
            return None
        if ((handoff.state.get("recovery_only") or not handoff.state["visibility_limit"])
                and not handoff.state.get("candidate") and not handoff.state.get("decision")):
            await handoff.save(pending=False, due_at=None, state="paused")
            return None
        service = service or AgentService(db)
        allowance = budget or AgentBudget(max_visibility_calls=handoff.state["visibility_limit"])
        result = await service._consider_visibility(
            handoff.owner, handoff.goal_id, AgentRun.model_validate(handoff.state["run"]),
            allowance, language=handoff.state["language"],
            _handoff=handoff, offer_delivery=offer_delivery,
        )
        await handoff.save(pending=False, due_at=None, state="settled", error_kind="")
        return result
    except HandoffSuperseded:
        await handoff.save(pending=False, due_at=None, state="stale")
        return None
    except asyncio.CancelledError:
        try:
            await handoff.defer()
        except Exception:
            pass
        raise  # The durable due/attempt survives; its lease can be reclaimed.
    except Exception as exc:
        logger.info("completion visibility deferred: %s", type(exc).__name__)
        try:
            await handoff.defer()
        except Exception:
            pass  # The original due and expiring lease remain recoverable.
        return None
    finally:
        try:
            await db.agent_goals.update_one({
                "id": handoff.goal_id, "owner_id": handoff.owner,
                f"{FIELD}.id": handoff.id, f"{FIELD}.token": handoff.token,
            }, {"$unset": {f"{FIELD}.lease_until": "", f"{FIELD}.token": ""}})
        except Exception:
            pass


async def resume_initial(service, owner, goal_id, budget):
    moment = _now()
    row = await service.db.agent_goals.find_one({
        **_query(moment), "id": goal_id, "owner_id": owner,
    }, {"_id": 0, "id": 1, "owner_id": 1, f"{FIELD}.due_at": 1})
    if row is None:
        return None
    claimed = await _claim(service.db, {"id": goal_id, "owner_id": owner,
                                      "due_at": row[FIELD]["due_at"]}, moment)
    if claimed:
        return await _process(service.db, claimed, service=service, budget=budget, offer_delivery=True)
    return None


async def drain(db, *, now=None, limit=1, owners_seen=None, allow_owner_fallback=True, candidate=None):
    """Consume at most one existing 60-second Delivery admission slot."""
    from delivery.admission import TIMEOUT_SECONDS

    if limit < 1:
        return 0
    moment = now or _now()
    candidate = candidate or await next_due(db, now=moment, owners_seen=owners_seen,
                                           allow_owner_fallback=allow_owner_fallback)
    if candidate is None:
        return 0
    claimed = await _claim(db, candidate, moment)
    if claimed is None:
        return 0
    if owners_seen is not None:
        owners_seen.add(claimed["owner_id"])
    try:
        await asyncio.wait_for(_process(db, claimed), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        # No second judgement in this slot; the persisted attempt/lease wins.
        pass
    return 1
