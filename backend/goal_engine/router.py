"""HTTP API for Goals — backend only; unused by UI in foundation phase."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_current_user, db, life_graph, knowledge
from goal_engine.models import GoalCreateBody, GoalMergeBody, GoalPatchBody, GoalSearchBody
from goal_engine.service import GoalService, goal_engine_enabled

router = APIRouter(prefix="/goals", tags=["goal_engine"])


def _svc() -> GoalService:
    return GoalService(db, life_graph=life_graph, knowledge=knowledge)


@router.get("")
async def list_goals(
    status: Optional[str] = Query(None),
    goal_type: Optional[str] = Query(None),
    limit: int = Query(40, ge=1, le=100),
    user=Depends(get_current_user),
):
    svc = _svc()
    goals = await svc.list_goals(
        user["user_id"], status=status, goal_type=goal_type, limit=limit,
    )
    return {
        "goals": goals,
        "enabled": goal_engine_enabled(),
        "count": len(goals),
    }


@router.post("")
async def create_goal(body: GoalCreateBody, user=Depends(get_current_user)):
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="title required")
    res = await _svc().create(user["user_id"], body)
    if res.get("skipped"):
        raise HTTPException(status_code=503, detail="goal_engine_disabled")
    return res


@router.post("/search")
async def search_goals(body: GoalSearchBody, user=Depends(get_current_user)):
    goals = await _svc().search(
        user["user_id"],
        q=body.q,
        goal_type=body.goal_type,
        status=body.status,
        limit=body.limit,
    )
    return {"goals": goals, "count": len(goals)}


@router.post("/merge")
async def merge_goals(body: GoalMergeBody, user=Depends(get_current_user)):
    res = await _svc().merge(
        user["user_id"],
        source_goal_id=body.source_goal_id,
        target_goal_id=body.target_goal_id,
        prefer_target_title=body.prefer_target_title,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error") or "merge_failed")
    return res


@router.get("/{goal_id}")
async def get_goal(goal_id: str, user=Depends(get_current_user)):
    g = await _svc().get(user["user_id"], goal_id)
    if not g:
        raise HTTPException(status_code=404, detail="not_found")
    return {"goal": g}


@router.patch("/{goal_id}")
async def patch_goal(goal_id: str, body: GoalPatchBody, user=Depends(get_current_user)):
    res = await _svc().patch(user["user_id"], goal_id, body)
    if not res.get("ok"):
        code = 404 if res.get("error") == "not_found" else 400
        raise HTTPException(status_code=code, detail=res.get("error"))
    return res


@router.delete("/{goal_id}")
async def delete_goal(
    goal_id: str,
    hard: bool = Query(False),
    user=Depends(get_current_user),
):
    res = await _svc().delete(user["user_id"], goal_id, soft=not hard)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{goal_id}/archive")
async def archive_goal(goal_id: str, user=Depends(get_current_user)):
    res = await _svc().archive(user["user_id"], goal_id)
    if not res.get("ok"):
        code = 404 if res.get("error") == "not_found" else 400
        raise HTTPException(status_code=code, detail=res.get("error"))
    return res


@router.get("/{goal_id}/timeline")
async def goal_timeline(goal_id: str, user=Depends(get_current_user)):
    res = await _svc().timeline(user["user_id"], goal_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res
