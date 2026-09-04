"""
Storage for goals, plans and what happened to them.

Owner-scoped throughout. The uniqueness that matters is one open goal per
opportunity: two goals chasing the same concern is duplicated work nobody
asked for, and a rule the database enforces cannot be forgotten by a caller.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.models import ActionPlan, AutonomousGoal

logger = logging.getLogger(__name__)

GOALS = "agent_goals"
PLANS = "agent_plans"
JOURNAL = "agent_journal"
RUNS = "agent_runs"
UPDATES = "agent_updates"

# How long one worker holds a goal before another may pick it up. Long
# enough that an ordinary run finishes inside it; short enough that a
# process killed mid-run does not strand the goal for an afternoon.
RUN_LEASE_SECONDS = 300

OPEN = ("proposed", "active", "waiting")

# How long the record of what the agent did is kept. Long enough to explain a
# question somebody was asked this morning; not a permanent account of every
# intention ORA ever formed.
JOURNAL_RETENTION_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AgentRepository:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[GOALS].create_index("id", unique=True)
            await self.db[GOALS].create_index([("owner_id", 1), ("status", 1)])
            # One open goal per concern. Two would be the same work twice.
            await self.db[GOALS].create_index(
                [("owner_id", 1), ("opportunity_id", 1)],
                unique=True,
                partialFilterExpression={
                    "opportunity_id": {"$gt": ""},
                    "status": {"$in": list(OPEN)},
                },
            )
            await self.db[PLANS].create_index("id", unique=True)
            await self.db[PLANS].create_index([("owner_id", 1), ("goal_id", 1)])
            await self.db[JOURNAL].create_index([("owner_id", 1), ("goal_id", 1)])
            await self.db[JOURNAL].create_index("expires_at", expireAfterSeconds=0)
            # One run per goal, enforced by the database. This is what
            # makes the claim below atomic rather than hopeful.
            await self.db[RUNS].create_index("goal_id", unique=True)
            await self.db[RUNS].create_index([("owner_id", 1), ("updated_at", -1)])
        except Exception:
            logger.exception("indici agent non creati (non fatale)")

    # --- goals ------------------------------------------------------------

    async def save_goal(self, goal: AutonomousGoal) -> AutonomousGoal:
        goal.touch()
        await self.db[GOALS].update_one(
            {"id": goal.id}, {"$set": goal.model_dump()}, upsert=True
        )
        return goal

    async def create_goal(self, goal: AutonomousGoal) -> Optional[AutonomousGoal]:
        """
        Write a new goal, unless one is already open for the same concern.

        Returns None when the index refuses it — which is not a failure. The
        second attempt is the bug, and the database is the place to catch it.
        """
        try:
            await self.db[GOALS].insert_one(goal.model_dump())
            return goal
        except Exception as exc:
            if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
                return None
            logger.info("goal create soft-fail: %s", type(exc).__name__)
            return None

    async def get_goal(self, owner_id: str, goal_id: str) -> Optional[AutonomousGoal]:
        doc = await self.db[GOALS].find_one(
            {"id": goal_id, "owner_id": owner_id}, {"_id": 0}
        )
        return AutonomousGoal.model_validate(doc) if doc else None

    async def open_goals(self, owner_id: str, *, limit: int = 20) -> List[AutonomousGoal]:
        docs = await self.db[GOALS].find(
            {"owner_id": owner_id, "status": {"$in": list(OPEN)}}, {"_id": 0}
        ).sort("created_at", 1).to_list(limit)
        return [AutonomousGoal.model_validate(d) for d in docs]

    async def goal_for_opportunity(
        self, owner_id: str, opportunity_id: str
    ) -> Optional[AutonomousGoal]:
        doc = await self.db[GOALS].find_one(
            {
                "owner_id": owner_id,
                "opportunity_id": opportunity_id,
                "status": {"$in": list(OPEN)},
            },
            {"_id": 0},
        )
        return AutonomousGoal.model_validate(doc) if doc else None

    # --- plans ------------------------------------------------------------

    async def save_plan(self, plan: ActionPlan) -> ActionPlan:
        plan.touch()
        await self.db[PLANS].update_one(
            {"id": plan.id}, {"$set": plan.model_dump()}, upsert=True
        )
        return plan

    async def plan_for(self, owner_id: str, goal_id: str) -> Optional[ActionPlan]:
        doc = await self.db[PLANS].find_one(
            {"owner_id": owner_id, "goal_id": goal_id, "status": {"$ne": "cancelled"}},
            {"_id": 0},
        )
        return ActionPlan.model_validate(doc) if doc else None


    # --- who is working on it ---------------------------------------------

    async def claim(
        self, owner_id: str, goal_id: str, *, worker_id: str,
        now: Optional[datetime] = None,
    ) -> bool:
        """
        Take this goal, atomically, or get nothing.

            TWO WORKERS, ONE EXECUTION.

        Two backend processes will reach the same goal — a wake fires while a
        request is already advancing it, or two instances sweep at once. The
        naive shape, read then write, has a window in which both see it free
        and both proceed, and the result is the same research run twice and
        eventually the same effect twice.

        Both branches below close that window inside the database. The insert
        succeeds for exactly one process because the index says so; the
        update matches only a lease that has genuinely run out, and matches
        it for exactly one process for the same reason. There is no third
        path, and no lock service is needed for this to be true.
        """
        moment = now or _now()
        lease = (moment + timedelta(seconds=RUN_LEASE_SECONDS)).isoformat()
        row = {
            "goal_id": goal_id,
            "owner_id": owner_id,
            "worker_id": worker_id,
            "lease_until": lease,
            "started_at": moment.isoformat(),
            "updated_at": moment.isoformat(),
        }
        try:
            await self.db[RUNS].insert_one(dict(row))
            return True
        except Exception as exc:
            if "duplicate key" not in str(exc).lower() and "E11000" not in str(exc):
                logger.info("run claim soft-fail: %s", type(exc).__name__)
                return False

        taken = await self.db[RUNS].find_one_and_update(
            {"goal_id": goal_id, "lease_until": {"$lte": moment.isoformat()}},
            {"$set": {"worker_id": worker_id, "lease_until": lease,
                      "updated_at": moment.isoformat()}},
            projection={"_id": 0, "goal_id": 1},
        )
        return taken is not None

    async def release(self, goal_id: str, *, stopped_because: str = "") -> None:
        """Let go, so the next wake does not have to wait out the lease."""
        try:
            await self.db[RUNS].update_one(
                {"goal_id": goal_id},
                {"$set": {"lease_until": _now().isoformat(),
                          "stopped_because": stopped_because[:120],
                          "updated_at": _now().isoformat()}},
            )
        except Exception as e:
            logger.info("run release soft-fail: %s", type(e).__name__)

    async def run_row(self, goal_id: str) -> Optional[Dict[str, Any]]:
        return await self.db[RUNS].find_one({"goal_id": goal_id}, {"_id": 0})

    # --- what happened ----------------------------------------------------

    async def journal(
        self, owner_id: str, goal_id: str, *, kind: str, note: str = "",
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        One line about what the agent did, for an audit and nothing else.

        Never shown to anybody: it holds step ids and capability names, which
        are exactly the implementation state a person should never meet.
        """
        try:
            await self.db[JOURNAL].insert_one({
                "owner_id": owner_id,
                "goal_id": goal_id,
                "kind": kind[:40],
                "note": note[:300],
                "detail": detail or {},
                "at": _now().isoformat(),
                "expires_at": _now() + timedelta(days=JOURNAL_RETENTION_DAYS),
            })
        except Exception as e:
            logger.info("journal soft-fail: %s", type(e).__name__)

    async def history(self, owner_id: str, goal_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
        return await self.db[JOURNAL].find(
            {"owner_id": owner_id, "goal_id": goal_id}, {"_id": 0}
        ).sort("at", 1).to_list(limit)

    async def forget_all(self, owner_id: str) -> Dict[str, int]:
        goals = await self.db[GOALS].delete_many({"owner_id": owner_id})
        plans = await self.db[PLANS].delete_many({"owner_id": owner_id})
        await self.db[JOURNAL].delete_many({"owner_id": owner_id})
        await self.db[RUNS].delete_many({"owner_id": owner_id})
        # What was said goes too. A record of «already told them this» that
        # outlives the goal it was about would silence a genuinely new update
        # later on, and nobody would ever find out why.
        await self.db[UPDATES].delete_many({"owner_id": owner_id})
        return {"goals_deleted": goals.deleted_count, "plans_deleted": plans.deleted_count}
