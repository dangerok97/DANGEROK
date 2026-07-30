"""Append-only DecisionActionHistory."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActionHistoryRepository:
    def __init__(self, db):
        self.db = db

    @property
    def col(self):
        return self.db.decision_action_history

    async def append(
        self,
        *,
        user_id: str,
        decision_id: str,
        old_status: Optional[str],
        new_status: str,
        user_action: str,
        completion_percentage: Optional[int] = None,
        remaining_minutes: Optional[int] = None,
        postponed_until: Optional[str] = None,
        reason: Optional[str] = None,
        note: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        doc = {
            "id": f"ah_{uuid.uuid4().hex[:16]}",
            "user_id": user_id,
            "decision_id": decision_id,
            "timestamp": _now_iso(),
            "old_status": old_status,
            "new_status": new_status,
            "user_action": user_action,  # start | complete | partial | postpone | dismiss | block
            "completion_percentage": completion_percentage,
            "remaining_minutes": remaining_minutes,
            "postponed_until": postponed_until,
            "reason": reason,
            "note": note,
            "correlation_id": correlation_id,
            # Immutable marker: any UPDATE must never touch this doc.
            "immutable": True,
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def list_for_decision(self, user_id: str, decision_id: str, *, limit: int = 200) -> List[Dict[str, Any]]:
        cursor = self.col.find(
            {"user_id": user_id, "decision_id": decision_id},
            {"_id": 0},
        ).sort("timestamp", 1).limit(max(1, min(limit, 1000)))
        return await cursor.to_list(length=1000)
