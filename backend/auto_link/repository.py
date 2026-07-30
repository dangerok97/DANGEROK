"""
Read-only data-access facade used by the Auto-Link Engine.

Everything the engine needs from other modules flows through this class.
That way we can swap the persistence layer later without touching the
matchers, and we keep the coupling to `db.decisions`, `db.life_nodes`,
`db.node_knowledge` narrow and reviewable.

Writes are limited to the `link_proposals` collection (own data) and the
`decisions.node_ids` field (via the injected `LifeGraphService`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutoLinkRepository:
    def __init__(self, db, life_graph):
        self.db = db
        self.life_graph = life_graph  # injected LifeGraphService

    # -------- proposals collection --------------------------------------
    @property
    def col(self):
        return self.db.link_proposals

    # -------- read: decisions -------------------------------------------
    async def get_decision(self, user_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.decisions.find_one(
            {"id": decision_id, "user_id": user_id},
            {"_id": 0},
        )

    # -------- read: life graph nodes ------------------------------------
    async def list_nodes(self, user_id: str, node_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id, "status": "active"}
        if node_types:
            q["type"] = {"$in": list(node_types)}
        cursor = self.db.life_nodes.find(q, {"_id": 0}).limit(500)
        return await cursor.to_list(length=500)

    async def get_node(self, user_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.life_nodes.find_one(
            {"id": node_id, "user_id": user_id, "status": "active"},
            {"_id": 0},
        )

    async def neighbors(self, user_id: str, node_ids: List[str], depth: int = 1) -> Dict[str, Any]:
        """Return {node_id -> set of neighbor node ids} within `depth` hops."""
        depth = max(1, min(depth, 2))  # bounded traversal
        if not node_ids:
            return {}
        current = set(node_ids)
        seen = set(node_ids)
        out: Dict[str, set] = {nid: set() for nid in node_ids}
        for _ in range(depth):
            if not current:
                break
            cursor = self.db.life_edges.find(
                {"user_id": user_id, "$or": [{"from_node": {"$in": list(current)}}, {"to_node": {"$in": list(current)}}]},
                {"_id": 0, "from_node": 1, "to_node": 1},
            )
            next_frontier: set = set()
            async for e in cursor:
                a, b = e["from_node"], e["to_node"]
                for src in (a, b):
                    if src in out or src in seen:
                        other = b if src == a else a
                        out.setdefault(src, set()).add(other)
                        if other not in seen:
                            next_frontier.add(other)
                            seen.add(other)
            current = next_frontier
        return {k: list(v) for k, v in out.items()}

    # -------- read: knowledge (read-only) -------------------------------
    async def get_knowledge(self, user_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.node_knowledge.find_one(
            {"user_id": user_id, "node_id": node_id, "status": {"$ne": "archived"}},
            {"_id": 0},
        )

    async def get_knowledge_bulk(self, user_id: str, node_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not node_ids:
            return {}
        cursor = self.db.node_knowledge.find(
            {"user_id": user_id, "node_id": {"$in": node_ids}, "status": {"$ne": "archived"}},
            {"_id": 0},
        )
        out: Dict[str, Dict[str, Any]] = {}
        async for d in cursor:
            out[d["node_id"]] = d
        return out

    # -------- write: proposals (own collection) -------------------------
    async def find_active(self, user_id: str, decision_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one(
            {
                "user_id": user_id,
                "decision_id": decision_id,
                "node_id": node_id,
                "status": {"$in": ["proposed", "accepted"]},
            },
            {"_id": 0},
        )

    async def find_rejected_still_valid(self, user_id: str, decision_id: str, node_id: str, decision_signature: str) -> Optional[Dict[str, Any]]:
        """Return a rejected proposal whose Decision signature is UNCHANGED.
        Used to suppress instant re-proposal after a user reject."""
        return await self.col.find_one(
            {
                "user_id": user_id,
                "decision_id": decision_id,
                "node_id": node_id,
                "status": "rejected",
                "decision_signature": decision_signature,
            },
            {"_id": 0},
        )

    async def list_by_decision(self, user_id: str, decision_id: str, include_all_statuses: bool = False) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id, "decision_id": decision_id}
        if not include_all_statuses:
            q["status"] = {"$in": ["proposed", "accepted"]}
        cursor = self.col.find(q, {"_id": 0}).sort([("confidence", -1), ("created_at", -1)])
        return await cursor.to_list(length=200)

    async def get_proposal(self, user_id: str, proposal_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one({"id": proposal_id, "user_id": user_id}, {"_id": 0})

    async def insert_proposal(self, doc: Dict[str, Any]) -> None:
        await self.col.insert_one(doc)

    async def update_proposal(self, user_id: str, proposal_id: str, updates: Dict[str, Any]) -> bool:
        updates["updated_at"] = _now()
        res = await self.col.update_one(
            {"id": proposal_id, "user_id": user_id},
            {"$set": updates},
        )
        return res.matched_count > 0

    async def supersede_others(self, user_id: str, decision_id: str, keep_ids: List[str], reason: str) -> int:
        """Mark previously-proposed proposals as superseded when analysis re-runs.
        Only touches status=proposed; accepted/rejected stay intact for audit."""
        res = await self.col.update_many(
            {
                "user_id": user_id,
                "decision_id": decision_id,
                "status": "proposed",
                "id": {"$nin": keep_ids},
            },
            {
                "$set": {
                    "status": "superseded",
                    "superseded_at": _now(),
                    "superseded_reason": reason,
                    "updated_at": _now(),
                }
            },
        )
        return res.modified_count
