"""HTTP API for Life Objects — auth required; unused by main UI (shadow / tests)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import db, get_current_user, knowledge, life_graph
from life_objects.models import (
    LifeObjectCreateBody,
    LifeObjectLinkBody,
    LifeObjectMergeBody,
    LifeObjectPatchBody,
    LifeObjectReasonBody,
    LifeObjectSearchBody,
)
from life_objects.service import (
    LifeObjectService,
    life_object_engine_enabled,
    life_object_home_ui_enabled,
)

router = APIRouter(prefix="/life-objects", tags=["life_objects"])


def _svc() -> LifeObjectService:
    return LifeObjectService(db, life_graph=life_graph, knowledge=knowledge)


@router.get("/status")
async def life_objects_status(user=Depends(get_current_user)):
    return {
        "enabled": life_object_engine_enabled(),
        "home_ui_enabled": life_object_home_ui_enabled(),
        "mode": "shadow",
        "user_id": user["user_id"],
    }


@router.get("")
async def list_life_objects(
    type: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = Query("active"),
    limit: int = Query(40, ge=1, le=100),
    user=Depends(get_current_user),
):
    objs = await _svc().list_objects(
        user["user_id"], object_type=type, status=status, limit=limit,
    )
    return {
        "objects": objs,
        "count": len(objs),
        "enabled": life_object_engine_enabled(),
        "home_ui_enabled": life_object_home_ui_enabled(),
    }


@router.post("")
async def create_life_object(body: LifeObjectCreateBody, user=Depends(get_current_user)):
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="title required")
    res = await _svc().create(user["user_id"], body)
    if res.get("skipped"):
        raise HTTPException(status_code=503, detail="life_object_engine_disabled")
    return res


@router.post("/search")
async def search_life_objects(body: LifeObjectSearchBody, user=Depends(get_current_user)):
    objs = await _svc().search(
        user["user_id"],
        q=body.q,
        object_type=body.type,
        status=body.status,
        limit=body.limit,
    )
    return {"objects": objs, "count": len(objs)}


@router.post("/merge")
async def merge_life_objects(body: LifeObjectMergeBody, user=Depends(get_current_user)):
    res = await _svc().merge(
        user["user_id"],
        source_id=body.source_id,
        target_id=body.target_id,
        prefer_target_title=body.prefer_target_title,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error") or "merge_failed")
    return res


@router.post("/reason")
async def reason_life_object(body: LifeObjectReasonBody, user=Depends(get_current_user)):
    res = await _svc().reason(
        user["user_id"],
        document_id=body.document_id,
        force=body.force,
        context=body.context,
    )
    if not res.get("ok") and res.get("error"):
        code = 404 if "not_found" in str(res.get("error")) else 400
        raise HTTPException(status_code=code, detail=res.get("error"))
    return res


@router.get("/{object_id}")
async def get_life_object(object_id: str, user=Depends(get_current_user)):
    obj = await _svc().get(user["user_id"], object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="not_found")
    return {"object": obj}


@router.patch("/{object_id}")
async def patch_life_object(
    object_id: str, body: LifeObjectPatchBody, user=Depends(get_current_user),
):
    res = await _svc().patch(user["user_id"], object_id, body)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.delete("/{object_id}")
async def delete_life_object(
    object_id: str,
    hard: bool = Query(False),
    user=Depends(get_current_user),
):
    res = await _svc().delete(user["user_id"], object_id, soft=not hard)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{object_id}/link")
async def link_life_object(
    object_id: str, body: LifeObjectLinkBody, user=Depends(get_current_user),
):
    res = await _svc().link(
        user["user_id"],
        object_id,
        target_id=body.target_id,
        relation=body.relation,
        confidence=body.confidence,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error") or "link_failed")
    return res


@router.get("/{object_id}/trend")
async def life_object_trend(
    object_id: str,
    utility_type: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    res = await _svc().trend(user["user_id"], object_id, utility_type=utility_type)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res
