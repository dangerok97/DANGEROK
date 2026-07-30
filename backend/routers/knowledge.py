"""KNOWLEDGE LAYER router."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_current_user, knowledge
from knowledge import (
    NormalizationError as KnowledgeNormalizationError,
    SCHEMAS as KNOWLEDGE_SCHEMAS,
    VersionConflict as KnowledgeVersionConflict,
    schema_for as knowledge_schema_for,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# --- Models ----------------------------------------------------------
class KnowledgeMeta(BaseModel):
    expected_version: Optional[int] = None
    reason: Optional[str] = None
    source_type: Optional[str] = None
    actor_type: Optional[str] = None


class KnowledgeReplaceIn(KnowledgeMeta):
    properties: Dict[str, Any]


class KnowledgeMergeIn(KnowledgeMeta):
    properties: Dict[str, Any]


class KnowledgePropertyIn(KnowledgeMeta):
    value: Any = None


class KnowledgeArchiveIn(BaseModel):
    reason: Optional[str] = None


# --- Helpers ---------------------------------------------------------
def _knowledge_write_kwargs(body: KnowledgeMeta, user: dict) -> Dict[str, Any]:
    return {
        "expected_version": body.expected_version,
        "reason": body.reason,
        "source_type": body.source_type or "user_input",
        "actor_type": body.actor_type or "user",
        "actor_id": user["user_id"],
    }


def _map_knowledge_error(e: Exception) -> HTTPException:
    if isinstance(e, KnowledgeVersionConflict):
        return HTTPException(status_code=409, detail={"error": "version_conflict", "expected": e.expected, "current": e.current})
    if isinstance(e, KnowledgeNormalizationError):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=500, detail="Errore interno")


# --- Routes ----------------------------------------------------------
@router.get("/schemas")
async def knowledge_schemas():
    return {"schemas": KNOWLEDGE_SCHEMAS, "types": sorted(KNOWLEDGE_SCHEMAS.keys())}


@router.get("/schemas/{node_type}")
async def knowledge_schema(node_type: str):
    return {"node_type": node_type, "schema": knowledge_schema_for(node_type)}


@router.get("/nodes/{node_id}")
async def get_node_knowledge(node_id: str, include_archived: bool = False, user=Depends(get_current_user)):
    doc = await knowledge.get(user["user_id"], node_id, include_archived=include_archived)
    if doc is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return doc


@router.get("/nodes/{node_id}/history")
async def get_node_knowledge_history(node_id: str, limit: int = 200, user=Depends(get_current_user)):
    events = await knowledge.history(user["user_id"], node_id, limit=limit)
    if events is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return {"items": events}


@router.get("/nodes/{node_id}/properties/{key}")
async def get_node_property(node_id: str, key: str, user=Depends(get_current_user)):
    try:
        result = await knowledge.get_property(user["user_id"], node_id, key)
    except KnowledgeNormalizationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return result


@router.put("/nodes/{node_id}")
async def replace_node_knowledge(node_id: str, body: KnowledgeReplaceIn, user=Depends(get_current_user)):
    try:
        doc = await knowledge.replace(user["user_id"], node_id, body.properties, **_knowledge_write_kwargs(body, user))
    except (KnowledgeVersionConflict, KnowledgeNormalizationError) as e:
        raise _map_knowledge_error(e)
    if doc is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return doc


@router.patch("/nodes/{node_id}")
async def merge_node_knowledge(node_id: str, body: KnowledgeMergeIn, user=Depends(get_current_user)):
    try:
        doc = await knowledge.merge(user["user_id"], node_id, body.properties, **_knowledge_write_kwargs(body, user))
    except (KnowledgeVersionConflict, KnowledgeNormalizationError) as e:
        raise _map_knowledge_error(e)
    if doc is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return doc


@router.delete("/nodes/{node_id}")
async def archive_node_knowledge(node_id: str, reason: Optional[str] = None, user=Depends(get_current_user)):
    doc = await knowledge.archive(user["user_id"], node_id, reason=reason, actor_id=user["user_id"])
    if doc is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return doc


@router.post("/nodes/{node_id}/restore")
async def restore_node_knowledge(node_id: str, body: Optional[KnowledgeArchiveIn] = None, user=Depends(get_current_user)):
    reason = body.reason if body else None
    doc = await knowledge.restore(user["user_id"], node_id, reason=reason, actor_id=user["user_id"])
    if doc is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return doc


@router.put("/nodes/{node_id}/properties/{key}")
async def set_node_property(node_id: str, key: str, body: KnowledgePropertyIn, user=Depends(get_current_user)):
    try:
        doc = await knowledge.set_property(user["user_id"], node_id, key, body.value, **_knowledge_write_kwargs(body, user))
    except (KnowledgeVersionConflict, KnowledgeNormalizationError) as e:
        raise _map_knowledge_error(e)
    if doc is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return doc


@router.delete("/nodes/{node_id}/properties/{key}")
async def remove_node_property(node_id: str, key: str, reason: Optional[str] = None, user=Depends(get_current_user)):
    try:
        doc = await knowledge.remove_property(user["user_id"], node_id, key, reason=reason, actor_id=user["user_id"])
    except (KnowledgeVersionConflict, KnowledgeNormalizationError) as e:
        raise _map_knowledge_error(e)
    if doc is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return doc


@router.get("")
async def list_all_knowledge(include_archived: bool = False, user=Depends(get_current_user)):
    items = await knowledge.list_for_user(user["user_id"], include_archived=include_archived)
    return {"items": items}
