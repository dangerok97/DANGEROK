"""
LifeGraphService — the single facade for all Life Graph operations.

Contract with the rest of the app:
- Owns the `life_nodes` and `life_edges` collections.
- Owns the WRITE-side of the `decisions.node_ids` field (link/unlink). Reads
  from `decisions` for listing purposes only. This lets the Decision Engine
  remain 100% untouched.
- Never ranks, never decides. Pure knowledge representation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .traversal import bfs_expand
from .types import (
    NodeType,
    RelationType,
    normalize_node_type,
    normalize_relation_type,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _node_id() -> str:
    return f"node_{uuid.uuid4().hex[:12]}"


def _edge_id() -> str:
    return f"edge_{uuid.uuid4().hex[:12]}"


class LifeGraphService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # collections
    # ------------------------------------------------------------------
    @property
    def nodes_col(self):
        return self.db.life_nodes

    @property
    def edges_col(self):
        return self.db.life_edges

    @property
    def decisions_col(self):
        return self.db.decisions

    # ------------------------------------------------------------------
    # nodes
    # ------------------------------------------------------------------
    async def create_node(
        self,
        user_id: str,
        *,
        type: str,
        label: str,
        description: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        origin: str = "user",
    ) -> Dict[str, Any]:
        doc = {
            "id": _node_id(),
            "user_id": user_id,
            "type": normalize_node_type(type),
            "label": label.strip() or "Senza nome",
            "description": description,
            "attributes": attributes or {},
            "status": "active",
            "origin": origin,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await self.nodes_col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get_node(self, user_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        return await self.nodes_col.find_one({"id": node_id, "user_id": user_id}, {"_id": 0})

    async def list_nodes(self, user_id: str, node_type: Optional[str] = None, include_archived: bool = False) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if node_type:
            q["type"] = normalize_node_type(node_type)
        if not include_archived:
            q["status"] = "active"
        cursor = self.nodes_col.find(q, {"_id": 0}).sort("created_at", -1)
        return await cursor.to_list(length=1000)

    async def update_node(self, user_id: str, node_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"label", "description", "attributes", "type", "status"}
        set_doc: Dict[str, Any] = {}
        for k, v in updates.items():
            if k in allowed and v is not None:
                if k == "type":
                    set_doc[k] = normalize_node_type(v)
                else:
                    set_doc[k] = v
        if not set_doc:
            return await self.get_node(user_id, node_id)
        set_doc["updated_at"] = _now()
        res = await self.nodes_col.update_one({"id": node_id, "user_id": user_id}, {"$set": set_doc})
        if res.matched_count == 0:
            return None
        return await self.get_node(user_id, node_id)

    async def archive_node(self, user_id: str, node_id: str) -> bool:
        """Soft delete. Also removes edges touching this node and unlinks decisions."""
        res = await self.nodes_col.update_one(
            {"id": node_id, "user_id": user_id},
            {"$set": {"status": "archived", "updated_at": _now()}},
        )
        if res.matched_count == 0:
            return False
        await self.edges_col.delete_many({
            "user_id": user_id,
            "$or": [{"from_node": node_id}, {"to_node": node_id}],
        })
        await self.decisions_col.update_many(
            {"user_id": user_id, "node_ids": node_id},
            {"$pull": {"node_ids": node_id}},
        )
        return True

    # ------------------------------------------------------------------
    # edges
    # ------------------------------------------------------------------
    async def create_edge(
        self,
        user_id: str,
        *,
        from_node: str,
        to_node: str,
        type: str = RelationType.RELATED_TO.value,
        directed: bool = False,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if from_node == to_node:
            raise ValueError("from_node e to_node non possono coincidere")
        # Sanity: both endpoints must exist for this user.
        a = await self.get_node(user_id, from_node)
        b = await self.get_node(user_id, to_node)
        if not a or not b:
            raise LookupError("Uno dei nodi non esiste per questo utente")

        doc = {
            "id": _edge_id(),
            "user_id": user_id,
            "from_node": from_node,
            "to_node": to_node,
            "type": normalize_relation_type(type),
            "directed": bool(directed),
            "attributes": attributes or {},
            "created_at": _now(),
        }
        await self.edges_col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def list_edges(self, user_id: str, node_id: Optional[str] = None) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if node_id:
            q["$or"] = [{"from_node": node_id}, {"to_node": node_id}]
        cursor = self.edges_col.find(q, {"_id": 0}).sort("created_at", -1)
        return await cursor.to_list(length=5000)

    async def delete_edge(self, user_id: str, edge_id: str) -> bool:
        res = await self.edges_col.delete_one({"id": edge_id, "user_id": user_id})
        return res.deleted_count > 0

    # ------------------------------------------------------------------
    # traversal
    # ------------------------------------------------------------------
    async def neighborhood(self, user_id: str, node_id: str, depth: int = 2) -> Dict[str, Any]:
        nodes = await self.list_nodes(user_id)
        edges = await self.list_edges(user_id)
        sub = bfs_expand(node_id, nodes, edges, depth=depth)
        # Attach decisions linked to any node in the sub-graph.
        node_ids = [n["id"] for n in sub["nodes"]]
        decisions: List[Dict[str, Any]] = []
        if node_ids:
            cur = self.decisions_col.find(
                {"user_id": user_id, "node_ids": {"$in": node_ids}},
                {"_id": 0},
            )
            decisions = await cur.to_list(length=1000)
        sub["decisions"] = decisions
        return sub

    # ------------------------------------------------------------------
    # decisions <-> nodes
    # ------------------------------------------------------------------
    async def link_decision(self, user_id: str, decision_id: str, node_ids: List[str]) -> Optional[Dict[str, Any]]:
        """Add the given nodes to `decisions.node_ids`. Idempotent. Returns updated decision.

        Does NOT modify the Decision Engine's code — it just writes an extra
        field on the decision document. The engine already carries dict
        payloads through unchanged."""
        # Validate node existence.
        found = await self.nodes_col.count_documents({"user_id": user_id, "id": {"$in": node_ids}})
        if found != len(set(node_ids)):
            raise LookupError("Uno o più nodi non esistono per questo utente")

        res = await self.decisions_col.update_one(
            {"id": decision_id, "user_id": user_id},
            {"$addToSet": {"node_ids": {"$each": node_ids}}, "$push": {"history": {
                "at": _now(), "event": "life_graph.linked", "data": {"node_ids": node_ids},
            }}},
        )
        if res.matched_count == 0:
            return None
        return await self.decisions_col.find_one({"id": decision_id, "user_id": user_id}, {"_id": 0})

    async def unlink_decision(self, user_id: str, decision_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        res = await self.decisions_col.update_one(
            {"id": decision_id, "user_id": user_id},
            {"$pull": {"node_ids": node_id}, "$push": {"history": {
                "at": _now(), "event": "life_graph.unlinked", "data": {"node_id": node_id},
            }}},
        )
        if res.matched_count == 0:
            return None
        return await self.decisions_col.find_one({"id": decision_id, "user_id": user_id}, {"_id": 0})

    async def decisions_for_node(self, user_id: str, node_id: str) -> List[Dict[str, Any]]:
        cursor = self.decisions_col.find(
            {"user_id": user_id, "node_ids": node_id},
            {"_id": 0},
        ).sort("created_at", -1)
        return await cursor.to_list(length=1000)

    # ------------------------------------------------------------------
    # seed: idempotent demo graph
    # ------------------------------------------------------------------
    async def seed_demo(self, user_id: str) -> Dict[str, Any]:
        """Create a small illustrative graph if the user has no nodes yet.

        Nodes: Persona (Me), Casa, Auto, Salute, Università, Lavoro, Bolletta Luce
               (as a Subscription/Contract), Assicurazione Auto.
        Edges: Me lives_at Casa, Casa parent_of Bolletta, Me owns Auto,
               Auto assigned_to Assicurazione, Me has_member Lavoro,
               Me related_to Salute, Me related_to Università.

        Idempotent: if any node exists for user, this is a no-op.
        """
        existing = await self.nodes_col.count_documents({"user_id": user_id})
        if existing > 0:
            return {"created": 0, "reason": "already_seeded"}

        me = await self.create_node(user_id, type=NodeType.PERSON.value, label="Io", origin="seed")
        casa = await self.create_node(user_id, type=NodeType.HOME.value, label="Casa", description="La tua abitazione principale", origin="seed")
        auto = await self.create_node(user_id, type=NodeType.CAR.value, label="Auto", origin="seed")
        salute = await self.create_node(user_id, type=NodeType.HEALTH.value, label="Salute", origin="seed")
        uni = await self.create_node(user_id, type=NodeType.UNIVERSITY.value, label="Università", origin="seed")
        lavoro = await self.create_node(user_id, type=NodeType.JOB.value, label="Lavoro", origin="seed")
        bolletta = await self.create_node(user_id, type=NodeType.SUBSCRIPTION.value, label="Bolletta Luce", description="Enel Energia · fattura ricorrente", attributes={"provider": "Enel"}, origin="seed")
        assic = await self.create_node(user_id, type=NodeType.CONTRACT.value, label="Assicurazione Auto", origin="seed")

        await self.create_edge(user_id, from_node=me["id"], to_node=casa["id"], type=RelationType.LIVES_AT.value, directed=True)
        await self.create_edge(user_id, from_node=casa["id"], to_node=bolletta["id"], type=RelationType.PARENT_OF.value, directed=True)
        await self.create_edge(user_id, from_node=me["id"], to_node=auto["id"], type=RelationType.OWNS.value, directed=True)
        await self.create_edge(user_id, from_node=auto["id"], to_node=assic["id"], type=RelationType.ASSIGNED_TO.value, directed=True)
        await self.create_edge(user_id, from_node=me["id"], to_node=lavoro["id"], type=RelationType.HAS_MEMBER.value, directed=True)
        await self.create_edge(user_id, from_node=me["id"], to_node=salute["id"], type=RelationType.RELATED_TO.value)
        await self.create_edge(user_id, from_node=me["id"], to_node=uni["id"], type=RelationType.RELATED_TO.value)

        return {
            "created": 8,
            "root": me["id"],
            "nodes": {"me": me["id"], "casa": casa["id"], "auto": auto["id"], "salute": salute["id"], "uni": uni["id"], "lavoro": lavoro["id"], "bolletta": bolletta["id"], "assic": assic["id"]},
        }
