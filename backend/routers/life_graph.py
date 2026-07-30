"""LIFE GRAPH router."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_current_user, life_graph
from life_graph import NODE_TYPES, RELATION_TYPES

router = APIRouter(prefix="/life-graph", tags=["life_graph"])


# --- Models ----------------------------------------------------------
class NodeIn(BaseModel):
    type: str = "generic"
    label: str
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class NodePatch(BaseModel):
    type: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class EdgeIn(BaseModel):
    from_node: str
    to_node: str
    type: str = "related_to"
    directed: bool = False
    attributes: Optional[Dict[str, Any]] = None


class DecisionNodesLinkIn(BaseModel):
    node_ids: List[str]


# --- Vocabulary + seed ----------------------------------------------
@router.get("/vocabulary")
async def life_graph_vocabulary():
    return {
        "node_types": sorted(NODE_TYPES),
        "relation_types": sorted(RELATION_TYPES),
    }


@router.post("/seed")
async def life_graph_seed(user=Depends(get_current_user)):
    return await life_graph.seed_demo(user["user_id"])


# --- Nodes -----------------------------------------------------------
@router.post("/nodes")
async def create_node(body: NodeIn, user=Depends(get_current_user)):
    return await life_graph.create_node(
        user["user_id"],
        type=body.type,
        label=body.label,
        description=body.description,
        attributes=body.attributes,
    )


@router.get("/nodes")
async def list_nodes(type: Optional[str] = None, include_archived: bool = False, user=Depends(get_current_user)):
    items = await life_graph.list_nodes(user["user_id"], node_type=type, include_archived=include_archived)
    return {"items": items}


@router.get("/nodes/{node_id}")
async def get_node(node_id: str, user=Depends(get_current_user)):
    node = await life_graph.get_node(user["user_id"], node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return node


@router.patch("/nodes/{node_id}")
async def patch_node(node_id: str, body: NodePatch, user=Depends(get_current_user)):
    node = await life_graph.update_node(user["user_id"], node_id, body.model_dump(exclude_none=True))
    if not node:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return node


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str, user=Depends(get_current_user)):
    ok = await life_graph.archive_node(user["user_id"], node_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return {"ok": True}


@router.get("/nodes/{node_id}/graph")
async def node_graph(node_id: str, depth: int = 2, user=Depends(get_current_user)):
    sub = await life_graph.neighborhood(user["user_id"], node_id, depth=depth)
    if sub["root"] is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return sub


@router.get("/nodes/{node_id}/decisions")
async def node_decisions(node_id: str, user=Depends(get_current_user)):
    node = await life_graph.get_node(user["user_id"], node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    items = await life_graph.decisions_for_node(user["user_id"], node_id)
    return {"items": items}


# --- Edges -----------------------------------------------------------
@router.post("/edges")
async def create_edge(body: EdgeIn, user=Depends(get_current_user)):
    try:
        return await life_graph.create_edge(
            user["user_id"],
            from_node=body.from_node,
            to_node=body.to_node,
            type=body.type,
            directed=body.directed,
            attributes=body.attributes,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/edges")
async def list_edges(node_id: Optional[str] = None, user=Depends(get_current_user)):
    items = await life_graph.list_edges(user["user_id"], node_id=node_id)
    return {"items": items}


@router.delete("/edges/{edge_id}")
async def delete_edge(edge_id: str, user=Depends(get_current_user)):
    ok = await life_graph.delete_edge(user["user_id"], edge_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Edge non trovato")
    return {"ok": True}


# --- Decision <-> node ----------------------------------------------
@router.post("/decisions/{decision_id}/nodes")
async def link_decision_to_nodes(decision_id: str, body: DecisionNodesLinkIn, user=Depends(get_current_user)):
    try:
        updated = await life_graph.link_decision(user["user_id"], decision_id, body.node_ids)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return updated


@router.delete("/decisions/{decision_id}/nodes/{node_id}")
async def unlink_decision_from_node(decision_id: str, node_id: str, user=Depends(get_current_user)):
    updated = await life_graph.unlink_decision(user["user_id"], decision_id, node_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return updated
