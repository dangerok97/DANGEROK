"""Mongo persistence for user-owned Life Context Graph edges."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from context_graph.models import ContextEdge


class ContextGraphRepository:
    COLLECTION = "context_edges"

    def __init__(self, db):
        self.db = db
        self.col = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("user_id", 1), ("id", 1)], unique=True)
        await self.col.create_index(
            [("user_id", 1), ("governance_key", 1)], unique=True, sparse=True
        )
        await self.col.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
        await self.col.create_index([("user_id", 1), ("subject_ref", 1), ("status", 1)])
        await self.col.create_index([("user_id", 1), ("object_ref", 1), ("status", 1)])

    async def insert(self, edge: ContextEdge) -> None:
        await self.col.insert_one(edge.model_dump())

    async def get(self, user_id: str, edge_id: str) -> Optional[ContextEdge]:
        doc = await self.col.find_one({"user_id": user_id, "id": edge_id}, {"_id": 0})
        return ContextEdge.model_validate(doc) if doc else None

    async def get_by_governance_key(
        self, user_id: str, governance_key: str
    ) -> Optional[ContextEdge]:
        doc = await self.col.find_one(
            {"user_id": user_id, "governance_key": governance_key}, {"_id": 0}
        )
        return ContextEdge.model_validate(doc) if doc else None

    async def find_active_by_identity(
        self, user_id: str, *, subject_ref: str, predicate: str
    ) -> Optional[ContextEdge]:
        doc = await self.col.find_one(
            {
                "user_id": user_id,
                "subject_ref": subject_ref,
                "predicate": predicate,
                "status": "active",
            },
            {"_id": 0},
        )
        return ContextEdge.model_validate(doc) if doc else None

    async def save(self, edge: ContextEdge, *, previous_revision: int) -> bool:
        result = await self.col.update_one(
            {"user_id": edge.user_id, "id": edge.id, "revision": previous_revision},
            {"$set": edge.model_dump()},
        )
        return bool(getattr(result, "modified_count", 0))

    async def find_touching(
        self, user_id: str, refs: List[str], *, limit: int = 20
    ) -> List[ContextEdge]:
        if not refs:
            return []
        query: Dict[str, Any] = {
            "user_id": user_id,
            "status": "active",
            "$or": [{"subject_ref": {"$in": refs}}, {"object_ref": {"$in": refs}}],
        }
        cur = self.col.find(query, {"_id": 0}).sort("updated_at", -1).limit(limit)
        docs = await cur.to_list(limit)
        return [ContextEdge.model_validate(d) for d in docs]
