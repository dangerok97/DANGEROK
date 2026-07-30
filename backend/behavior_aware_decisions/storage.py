"""Append-only storage + audit logging for shadow evaluations (iter17)."""
from __future__ import annotations
import hashlib, json, logging, uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

EVALUATIONS = "behavior_shadow_evaluations"
logger = logging.getLogger("ora.behavior_shadow")


def make_idempotency_key(user_id: str, decision_id: str, decision_version: Optional[str],
                        profile_version: str, context_hash: Optional[str], rule_set_version: str) -> str:
    payload = f"{user_id}|{decision_id}|{decision_version or ''}|{profile_version}|{context_hash or ''}|{rule_set_version}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


class ShadowStorage:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._ready = False

    async def ensure_indexes(self):
        if self._ready:
            return
        await self.db[EVALUATIONS].create_index("evaluation_id", unique=True)
        await self.db[EVALUATIONS].create_index("idempotency_key", unique=True)
        await self.db[EVALUATIONS].create_index([("user_id", 1), ("decision_id", 1), ("created_at", -1)])
        await self.db[EVALUATIONS].create_index([("user_id", 1), ("created_at", -1)])
        self._ready = True

    async def find_by_idem(self, key: str) -> Optional[Dict[str, Any]]:
        return await self.db[EVALUATIONS].find_one({"idempotency_key": key}, {"_id": 0})

    async def insert(self, doc: Dict[str, Any]) -> bool:
        try:
            await self.db[EVALUATIONS].insert_one(doc)
            return True
        except Exception as e:
            if "duplicate key" in str(e).lower() or getattr(e, "code", None) == 11000:
                return False
            raise

    async def list_by_user(self, user_id: str, *, limit: int = 100, skip: int = 0,
                           decision_id: Optional[str] = None) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if decision_id:
            q["decision_id"] = decision_id
        cur = self.db[EVALUATIONS].find(q, {"_id": 0}).sort("created_at", -1).skip(max(0, skip)).limit(min(max(1, limit), 1000))
        return await cur.to_list(length=1000)

    async def stats(self, user_id: str) -> Dict[str, Any]:
        pipe = [{"$match": {"user_id": user_id}}, {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "positive": {"$sum": {"$cond": [{"$gt": ["$shadow_priority_delta", 0]}, 1, 0]}},
            "negative": {"$sum": {"$cond": [{"$lt": ["$shadow_priority_delta", 0]}, 1, 0]}},
            "zero": {"$sum": {"$cond": [{"$eq": ["$shadow_priority_delta", 0]}, 1, 0]}},
            "avg_delta": {"$avg": "$shadow_priority_delta"},
            "max_delta": {"$max": "$shadow_priority_delta"},
            "min_delta": {"$min": "$shadow_priority_delta"},
        }}]
        rows = await self.db[EVALUATIONS].aggregate(pipe).to_list(1)
        return rows[0] if rows else {"total": 0}


# --- audit / telemetry (sanitized) ------------------------------------------
def emit(event: str, **kv):
    """Sanitized telemetry — never logs full decision content."""
    safe = {k: v for k, v in kv.items() if k not in ("title", "description", "content", "profile_full")}
    logger.info("[shadow:%s] %s", event, json.dumps(safe, default=str, ensure_ascii=False)[:400])
