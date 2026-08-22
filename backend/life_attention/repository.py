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

    async def count(self, user_id: str) -> int:
        return await self.col.count_documents({"user_id": user_id})


def _is_duplicate_key(error: Exception) -> bool:
    if type(error).__name__ == "DuplicateKeyError":
        return True
    return getattr(error, "code", None) == 11000
