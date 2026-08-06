"""Per-user learning — dismiss often → lower; accept often → raise."""
from __future__ import annotations

from typing import Any, Dict, Optional

from proactive_engine.models import LearningStats, now_iso


def _key(user_id: str, suggestion_type: str, source: str) -> Dict[str, str]:
    return {
        "user_id": user_id,
        "suggestion_type": suggestion_type or "generic",
        "source": source or "unknown",
    }


def compute_multiplier(accepted: int, dismissed: int, completed: int = 0) -> float:
    """Bounded multiplier from accept/dismiss history. Never random."""
    total = accepted + dismissed + completed
    if total < 3:
        return 1.0
    accept_like = accepted + completed
    rate = accept_like / float(total)
    dismiss_rate = dismissed / float(total)
    # Map: high accept → up to 1.25; high dismiss → down to 0.6
    if dismiss_rate >= 0.7:
        return max(0.55, 1.0 - (dismiss_rate - 0.5) * 0.9)
    if rate >= 0.6:
        return min(1.3, 1.0 + (rate - 0.5) * 0.6)
    return 1.0


class LearningStore:
    def __init__(self, db):
        self.col = db.proactive_learning

    async def ensure_indexes(self) -> None:
        await self.col.create_index(
            [("user_id", 1), ("suggestion_type", 1), ("source", 1)],
            unique=True,
            name="uniq_proactive_learning",
        )

    async def get_stats(
        self, user_id: str, suggestion_type: str, source: str,
    ) -> LearningStats:
        doc = await self.col.find_one(_key(user_id, suggestion_type, source), {"_id": 0})
        if not doc:
            return LearningStats(
                user_id=user_id,
                suggestion_type=suggestion_type or "generic",
                source=source or "unknown",
            )
        return LearningStats(**doc)

    async def multiplier(
        self, user_id: str, suggestion_type: str, source: str,
    ) -> float:
        st = await self.get_stats(user_id, suggestion_type, source)
        return float(st.multiplier or 1.0)

    async def dismiss_rate(
        self, user_id: str, suggestion_type: str, source: str,
    ) -> float:
        st = await self.get_stats(user_id, suggestion_type, source)
        total = st.accepted + st.dismissed + st.completed
        if total < 3:
            return 0.0
        return st.dismissed / float(total)

    async def record(
        self,
        user_id: str,
        suggestion_type: str,
        source: str,
        *,
        event: str,
    ) -> LearningStats:
        st = await self.get_stats(user_id, suggestion_type, source)
        if event == "accepted":
            st.accepted += 1
        elif event == "dismissed":
            st.dismissed += 1
        elif event == "completed":
            st.completed += 1
        st.multiplier = compute_multiplier(st.accepted, st.dismissed, st.completed)
        st.updated_at = now_iso()
        payload = st.model_dump()
        await self.col.update_one(
            _key(user_id, suggestion_type, source),
            {"$set": payload},
            upsert=True,
        )
        return st
