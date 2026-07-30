"""Read-only DAO + write layer for `context_snapshots`."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContextRepository:
    def __init__(self, db):
        self.db = db

    @property
    def col(self):
        return self.db.context_snapshots

    # ---- read: dependencies ------------------------------------------
    async def get_decision(self, user_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.decisions.find_one({"id": decision_id, "user_id": user_id}, {"_id": 0})

    async def list_nodes(self, user_id: str, node_ids: List[str]) -> List[Dict[str, Any]]:
        if not node_ids:
            return []
        cursor = self.db.life_nodes.find(
            {"user_id": user_id, "id": {"$in": node_ids}, "status": "active"}, {"_id": 0},
        )
        return await cursor.to_list(length=200)

    async def get_knowledge_bulk(self, user_id: str, node_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not node_ids:
            return {}
        cursor = self.db.node_knowledge.find(
            {"user_id": user_id, "node_id": {"$in": node_ids}, "status": {"$ne": "archived"}}, {"_id": 0},
        )
        out: Dict[str, Dict[str, Any]] = {}
        async for d in cursor:
            out[d["node_id"]] = d
        return out

    async def graph_neighbors(self, user_id: str, node_ids: List[str], depth: int) -> Dict[str, Dict[str, Any]]:
        """Bounded BFS. Returns {node_id: {"neighbors":[...], "distance":n}}."""
        depth = max(1, min(depth, 2))
        if not node_ids:
            return {}
        seen = {nid: 0 for nid in node_ids}
        frontier = set(node_ids)
        edges_seen: List[Dict[str, Any]] = []
        for d in range(1, depth + 1):
            if not frontier:
                break
            cursor = self.db.life_edges.find(
                {"user_id": user_id,
                 "$or": [{"from_node": {"$in": list(frontier)}}, {"to_node": {"$in": list(frontier)}}]},
                {"_id": 0},
            )
            next_frontier = set()
            async for e in cursor:
                edges_seen.append(e)
                for src, other in ((e["from_node"], e["to_node"]), (e["to_node"], e["from_node"])):
                    if src in frontier and other not in seen:
                        seen[other] = d
                        next_frontier.add(other)
            frontier = next_frontier
        return {"distances": seen, "edges": edges_seen}

    async def accepted_proposals(self, user_id: str, decision_id: str) -> List[Dict[str, Any]]:
        cursor = self.db.link_proposals.find(
            {"user_id": user_id, "decision_id": decision_id, "status": "accepted"}, {"_id": 0},
        )
        return await cursor.to_list(length=100)

    # ---- write: snapshots --------------------------------------------
    async def find_latest_active(self, user_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one(
            {"user_id": user_id, "decision_id": decision_id, "status": "active"},
            {"_id": 0},
            sort=[("generated_at", -1)],
        )

    async def find_by_hash(self, user_id: str, decision_id: str, context_hash: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one(
            {"user_id": user_id, "decision_id": decision_id, "context_hash": context_hash, "status": "active"},
            {"_id": 0},
        )

    async def get_snapshot(self, user_id: str, snapshot_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one({"id": snapshot_id, "user_id": user_id}, {"_id": 0})

    async def list_history(self, user_id: str, decision_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 200))
        cursor = self.col.find(
            {"user_id": user_id, "decision_id": decision_id}, {"_id": 0},
        ).sort("generated_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def insert(self, doc: Dict[str, Any]) -> None:
        await self.col.insert_one(doc)

    async def supersede_others(self, user_id: str, decision_id: str, keep_id: str) -> int:
        res = await self.col.update_many(
            {"user_id": user_id, "decision_id": decision_id, "status": "active", "id": {"$ne": keep_id}},
            {"$set": {"status": "superseded", "superseded_at": _now()}},
        )
        return res.modified_count
