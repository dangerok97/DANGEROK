"""
What was found out, kept apart from what was pretended.

    EVIDENCE PRECEDES BELIEF.
    SIMULATED IS NOT OBSERVED.

The debt Sprint 1 closed with was that a stub returning success is
indistinguishable, to a verifier, from the world having changed. The fix is
not a better prompt. It is that the question "may this goal be called done"
gets asked of code, on facts the code owns, before the model's judgement is
allowed to matter.

So this file holds two things. A store, which is ordinary. And
`real_support`, which is the gate: a deterministic function that looks at
where each piece of evidence came from and answers whether anything here says
the actual world is different. A model cannot argue with it, because it is
never shown to one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.models import AgentEvidence

logger = logging.getLogger(__name__)

EVIDENCE = "agent_evidence"

# How long what was found out is kept. Evidence outliving the goal it was
# gathered for is a research cache, and there is already one of those.
EVIDENCE_RETENTION_DAYS = 30

# How old a piece of evidence may be before the model is told it is stale.
# Stale is a fact reported to the reasoning, never a reason code throws
# something away: yesterday's opening hours are usually still right, and that
# judgement belongs to whoever is reasoning about the case.
FRESH_HOURS = 6
RECENT_HOURS = 72

# Where a result has to have come from for it to say anything about the world.
# `simulated` is absent by construction, and `user_statement` is absent for a
# subtler reason: somebody saying they will do a thing is not the thing being
# done, and a goal closed on it would be closed on an intention.
REAL_SOURCES = (
    "internal_observation",
    "connected_provider",
    "external_research",
    "deterministic_computation",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def freshness_of(observed_at: str) -> str:
    """How old this is, in words. A fact for the model, not a filter."""
    try:
        seen = datetime.fromisoformat(observed_at)
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
    except Exception:
        return "unknown"
    age = (_now() - seen).total_seconds() / 3600.0
    if age <= FRESH_HOURS:
        return "fresh"
    if age <= RECENT_HOURS:
        return "recent"
    return "stale"


def real_support(evidence: List[AgentEvidence]) -> bool:
    """
    Does anything here say the actual world is a particular way?

        A GOAL MAY NOT BE COMPLETED ON SIMULATED EVIDENCE.

    Deterministic on purpose. The whole value of this check is that no
    prompt, no model outage and no unusually confident answer can move it —
    it reads the source class that the executing code wrote down, and
    nothing else.
    """
    return any(e.provenance.source_class in REAL_SOURCES for e in evidence)


def simulated_only(evidence: List[AgentEvidence]) -> bool:
    """Something was done, and none of it was real."""
    return bool(evidence) and not real_support(evidence)


class EvidenceStore:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[EVIDENCE].create_index("id", unique=True)
            await self.db[EVIDENCE].create_index([("owner_id", 1), ("goal_id", 1)])
            await self.db[EVIDENCE].create_index("expires_at", expireAfterSeconds=0)
        except Exception:
            logger.exception("indici evidenza non creati (non fatale)")

    async def record(self, evidence: AgentEvidence) -> AgentEvidence:
        doc = evidence.model_dump()
        doc["expires_at"] = _now() + timedelta(days=EVIDENCE_RETENTION_DAYS)
        try:
            await self.db[EVIDENCE].insert_one(doc)
        except Exception as e:
            logger.info("evidence record soft-fail: %s", type(e).__name__)
        return evidence

    async def for_goal(
        self, owner_id: str, goal_id: str, *, limit: int = 40
    ) -> List[AgentEvidence]:
        docs = await self.db[EVIDENCE].find(
            {"owner_id": owner_id, "goal_id": goal_id}, {"_id": 0, "expires_at": 0}
        ).sort("observed_at", 1).to_list(limit)
        out: List[AgentEvidence] = []
        for doc in docs:
            try:
                out.append(AgentEvidence.model_validate(doc))
            except Exception:
                continue
        return out

    async def research_refs(self, owner_id: str, goal_id: str) -> List[str]:
        """
        Which research runs this goal already has behind it.

        Used both to feed a comparison and to avoid asking the world
        something it has already been asked.
        """
        refs: List[str] = []
        for evidence in await self.for_goal(owner_id, goal_id):
            if evidence.provenance.capability == "web.research":
                refs.extend(
                    r for r in evidence.provenance.source_refs if r and r not in refs
                )
        return refs

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[EVIDENCE].delete_many({"owner_id": owner_id})
        return result.deleted_count


def for_verification(
    evidence: List[AgentEvidence], *, limit: int = 12
) -> List[Dict[str, Any]]:
    """
    What the verifier is shown, with the simulated part clearly marked.

    Not filtered — the model gets to see that a stand-in was used, because
    hiding it would leave it wondering why a step it can see finished has no
    evidence behind it. Marked, so that leaning on it is a choice it makes
    visibly rather than a mistake it makes silently. And the gate that
    actually decides sits in code either way.
    """
    out: List[Dict[str, Any]] = []
    for item in evidence[:limit]:
        row = item.for_ai()
        row["how_old"] = freshness_of(item.observed_at)
        if not item.is_real:
            row["warning"] = (
                "Questo non e successo davvero: e una simulazione, e non prova niente "
                "sul mondo reale."
            )
        out.append(row)
    return out
