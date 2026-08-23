"""Mongo persistence for user-owned Attention Decisions.

Silent decisions are stored here too, deliberately: a decision NOT to speak is
exactly as valuable as one to speak — it is what stops the next pass
re-evaluating the same assessments and what makes "why did ORA stay quiet?"
answerable.
"""

from __future__ import annotations

from typing import List, Optional

from life_attention.models import AttentionDecision


class DuplicateDecision(Exception):
    """The same assessment batch was already evaluated (idempotent replay)."""


class AttentionDecisionRepository:
    COLLECTION = "life_attention_decisions"

    def __init__(self, db):
        self.db = db
        self.col = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("user_id", 1), ("id", 1)], unique=True)
        # Storage-level idempotency: one evaluation per assessment batch.
        await self.col.create_index(
            [("user_id", 1), ("decision_key", 1)], unique=True, sparse=True
        )
        await self.col.create_index([("user_id", 1), ("created_at", -1)])
        # "Have we already spoken about this ref?" — novelty and collision.
        await self.col.create_index([("user_id", 1), ("focal_refs", 1)])
        # Deferred decisions waiting for re-evaluation.
        await self.col.create_index([("user_id", 1), ("delivery", 1), ("defer_until", 1)])

    async def insert(self, decision: AttentionDecision) -> None:
        try:
            await self.col.insert_one(decision.model_dump())
        except Exception as e:  # pragma: no cover - driver-specific type
            if _is_duplicate_key(e):
                raise DuplicateDecision(decision.decision_key) from e
            raise

    async def get_by_decision_key(
        self, user_id: str, decision_key: str
    ) -> Optional[AttentionDecision]:
        doc = await self.col.find_one(
            {"user_id": user_id, "decision_key": decision_key}, {"_id": 0}
        )
        return AttentionDecision.model_validate(doc) if doc else None

    async def list_recent(
        self, user_id: str, *, limit: int = 10
    ) -> List[AttentionDecision]:
        capped = max(1, min(int(limit or 10), 25))
        cur = (
            self.col.find({"user_id": user_id}, {"_id": 0})
            .sort([("created_at", -1), ("id", -1)])
            .limit(capped)
        )
        docs = await cur.to_list(capped)
        return [AttentionDecision.model_validate(d) for d in docs]

    async def count_spoken_for_refs(self, user_id: str, refs: List[str]) -> int:
        """How many times ORA already surfaced something about these refs.

        Feeds novelty: repeatedly raising the same corner of someone's life is
        how an assistant becomes noise, so the system measures it rather than
        asking the model to remember.
        """
        if not refs:
            return 0
        return await self.col.count_documents({
            "user_id": user_id,
            "focal_refs": {"$in": list(refs)[:8]},
            "delivery": {"$in": ["home", "ask_user", "propose_action", "notify"]},
        })

    async def set_suggestion(
        self, user_id: str, decision_id: str, *, suggestion_id: Optional[str],
        created: bool, gate_reasons: List[str],
    ) -> None:
        await self.col.update_one(
            {"user_id": user_id, "id": decision_id},
            {"$set": {
                "suggestion_id": suggestion_id,
                "suggestion_created": bool(created),
                "gate_reasons": list(gate_reasons)[:6],
            }},
        )

    async def list_due_deferred(
        self, user_id: str, *, now_iso: str, limit: int = 10
    ) -> List[AttentionDecision]:
        """Deferrals whose moment has arrived and that are still the CURRENT
        decision of their chain.

        `superseded_by: None` is the load-bearing filter: an older revision
        that has already been reconsidered must never be reconsidered again,
        or a chain would fan out instead of advancing. Uses the
        `(user_id, delivery, defer_until)` index created in V2.9.3.
        """
        capped = max(1, min(int(limit or 10), 25))
        cur = (
            self.col.find(
                {
                    "user_id": user_id,
                    "delivery": "defer",
                    "defer_until": {"$ne": None, "$lte": now_iso},
                    "superseded_by": None,
                    "auto_re_evaluation_exhausted": {"$ne": True},
                },
                {"_id": 0},
            )
            .sort([("defer_until", 1), ("id", 1)])
            .limit(capped)
        )
        docs = await cur.to_list(capped)
        return [AttentionDecision.model_validate(d) for d in docs]

    async def latest_for_root(
        self, user_id: str, root_attention_key: str
    ) -> Optional[AttentionDecision]:
        """The current decision of a chain: the highest revision that nothing
        has superseded."""
        doc = await self.col.find_one(
            {"user_id": user_id, "root_attention_key": root_attention_key},
            {"_id": 0},
            sort=[("attention_revision", -1)],
        )
        return AttentionDecision.model_validate(doc) if doc else None

    async def chain_for_root(
        self, user_id: str, root_attention_key: str, *, limit: int = 10
    ) -> List[AttentionDecision]:
        """Full history of one attention question, oldest revision first.
        Nothing is ever deleted, so this is the audit trail."""
        capped = max(1, min(int(limit or 10), 25))
        cur = (
            self.col.find(
                {"user_id": user_id, "root_attention_key": root_attention_key},
                {"_id": 0},
            )
            .sort([("attention_revision", 1)])
            .limit(capped)
        )
        docs = await cur.to_list(capped)
        return [AttentionDecision.model_validate(d) for d in docs]

    async def mark_superseded(
        self, user_id: str, decision_id: str, *, superseded_by: str
    ) -> int:
        """Record that a newer revision replaced this one.

        Non-destructive by design: the decision keeps its delivery, its
        reasoning and its scores, and only learns what replaced it. Called
        ONLY after the replacement is durably persisted.
        """
        result = await self.col.update_one(
            {"user_id": user_id, "id": decision_id},
            {"$set": {"superseded_by": superseded_by, "defer_status": "due"}},
        )
        return int(getattr(result, "modified_count", 0))

    async def mark_budget_exhausted(self, user_id: str, decision_id: str) -> int:
        """Flag that no further AUTOMATIC re-evaluation will be spent on this
        chain. Deliberately does not touch `delivery`: the decision stays
        whatever the AI last decided."""
        result = await self.col.update_one(
            {"user_id": user_id, "id": decision_id},
            {"$set": {"auto_re_evaluation_exhausted": True}},
        )
        return int(getattr(result, "modified_count", 0))

    async def earliest_pending_defer(self, user_id: str) -> Optional[str]:
        """`defer_until` of the soonest still-current deferral — lets a single
        one-shot timer replace any need to wake up and look.

        Restricted to chains that are current and still have automatic budget,
        so an exhausted or superseded deferral never arms a timer that would
        do nothing.
        """
        doc = await self.col.find_one(
            {
                "user_id": user_id,
                "delivery": "defer",
                "defer_until": {"$ne": None},
                "superseded_by": None,
                "auto_re_evaluation_exhausted": {"$ne": True},
            },
            {"_id": 0, "defer_until": 1},
            sort=[("defer_until", 1)],
        )
        return (doc or {}).get("defer_until")

    async def count(self, user_id: str) -> int:
        return await self.col.count_documents({"user_id": user_id})


def _is_duplicate_key(error: Exception) -> bool:
    if type(error).__name__ == "DuplicateKeyError":
        return True
    return getattr(error, "code", None) == 11000
