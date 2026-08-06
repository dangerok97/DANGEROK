"""Best-effort Brain / Goal / Document linking for Life Objects.

Prefer edges object↔object and object↔doc. Soft-fail; never break existing brain_links.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from life_objects.models import LifeObject, LifeObjectRelationship, now_iso

logger = logging.getLogger("ora.life_objects.linking")


async def ensure_brain_node(
    *,
    life_graph,
    obj: LifeObject,
) -> Optional[str]:
    """Create or reuse a life_graph node for this Life Object."""
    if not life_graph:
        return None
    if obj.brain_nodes:
        return obj.brain_nodes[0]
    try:
        # Prefer create_node if available
        create = getattr(life_graph, "create_node", None)
        if not create:
            return None
        res = await create(
            obj.user_id,
            type="life_object",
            label=obj.title,
            attributes={
                "life_object_id": obj.id,
                "life_object_type": obj.type,
                "origin": "life_object_engine",
            },
            origin="life_object_engine",
        )
        node_id = None
        if isinstance(res, dict):
            node_id = res.get("id") or (res.get("node") or {}).get("id")
        if node_id:
            if node_id not in obj.brain_nodes:
                obj.brain_nodes.append(node_id)
            return node_id
    except Exception as e:
        logger.info("life_object brain node soft-fail: %s", type(e).__name__)
    return None


async def ensure_object_doc_edge(
    *,
    life_graph,
    db,
    obj: LifeObject,
    document_id: str,
    doc_brain_node_id: Optional[str] = None,
) -> Optional[str]:
    """Best-effort edge between life object brain node and document node."""
    if not life_graph or not document_id:
        return None
    try:
        obj_node = await ensure_brain_node(life_graph=life_graph, obj=obj)
        if not obj_node:
            return None
        # Resolve document brain node if not provided
        to_node = doc_brain_node_id
        if not to_node and db is not None:
            try:
                doc = await db.documents.find_one(
                    {"id": document_id, "user_id": obj.user_id},
                    {"_id": 0, "brain_node_id": 1, "life_node_id": 1},
                )
                if doc:
                    to_node = doc.get("brain_node_id") or doc.get("life_node_id")
            except Exception:
                pass
        if not to_node:
            return None
        dedupe = f"lo_doc:{obj.id}:{document_id}"
        # Check existing
        if db is not None:
            existing = await db.life_edges.find_one(
                {"user_id": obj.user_id, "attributes.dedupe_key": dedupe},
                {"_id": 0, "id": 1},
            )
            if existing:
                return existing.get("id")
        create_edge = getattr(life_graph, "create_edge", None)
        if not create_edge:
            return None
        edge = await create_edge(
            obj.user_id,
            from_node=obj_node,
            to_node=to_node,
            type="documents",
            directed=False,
            attributes={
                "dedupe_key": dedupe,
                "life_object_id": obj.id,
                "document_id": document_id,
                "origin": "life_object_engine",
            },
        )
        if isinstance(edge, dict):
            return edge.get("id") or (edge.get("edge") or {}).get("id")
    except Exception as e:
        logger.info("life_object doc edge soft-fail: %s", type(e).__name__)
    return None


async def ensure_object_object_edge(
    *,
    life_graph,
    db,
    a: LifeObject,
    b: LifeObject,
    relation: str = "related_to",
) -> Optional[str]:
    if not life_graph or a.id == b.id:
        return None
    try:
        na = await ensure_brain_node(life_graph=life_graph, obj=a)
        nb = await ensure_brain_node(life_graph=life_graph, obj=b)
        if not na or not nb:
            return None
        dedupe = f"lo_lo:{min(a.id, b.id)}:{max(a.id, b.id)}:{relation}"
        if db is not None:
            existing = await db.life_edges.find_one(
                {"user_id": a.user_id, "attributes.dedupe_key": dedupe},
                {"_id": 0, "id": 1},
            )
            if existing:
                return existing.get("id")
        create_edge = getattr(life_graph, "create_edge", None)
        if not create_edge:
            return None
        edge = await create_edge(
            a.user_id,
            from_node=na,
            to_node=nb,
            type=relation,
            directed=False,
            attributes={
                "dedupe_key": dedupe,
                "life_object_ids": [a.id, b.id],
                "origin": "life_object_engine",
            },
        )
        if isinstance(edge, dict):
            return edge.get("id")
    except Exception as e:
        logger.info("life_object↔object edge soft-fail: %s", type(e).__name__)
    return None


def add_relationship(obj: LifeObject, target_id: str, relation: str, confidence: float = 0.7) -> LifeObject:
    for r in obj.relationships:
        if r.target_id == target_id and r.relation == relation:
            return obj
    obj.relationships.append(
        LifeObjectRelationship(target_id=target_id, relation=relation, confidence=confidence)
    )
    obj.updated_at = now_iso()
    return obj


def link_document(obj: LifeObject, document_id: str) -> LifeObject:
    if document_id and document_id not in obj.documents:
        obj.documents.append(document_id)
        obj.source_count = len(obj.documents) + len(obj.goals) + len(obj.projects)
    return obj


def link_goal(obj: LifeObject, goal_id: str) -> LifeObject:
    if goal_id and goal_id not in obj.goals:
        obj.goals.append(goal_id)
        obj.source_count = len(obj.documents) + len(obj.goals) + len(obj.projects)
    return obj
