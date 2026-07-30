"""LEGACY tasks + priorities routes (backward compatible with Home v1)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import decisions, get_current_user

from .decisions import resolve_decision

router = APIRouter(tags=["legacy"])


class TaskIn(BaseModel):
    title: str
    context: Optional[str] = None
    urgency: int = 5
    importance: int = 5
    risk: int = 3
    time_required_min: int = 15
    place: Optional[str] = None
    energy: int = 3
    economic_impact: int = 3
    personal_impact: int = 5
    kind: Optional[str] = "generic"
    metadata: Optional[dict] = None


def decision_as_task(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return a task-shaped dict for old clients (frontend v1)."""
    return {
        "id": d.get("id"),
        "user_id": d.get("user_id"),
        "title": d.get("title"),
        "context": d.get("description"),
        "urgency": d.get("urgency"),
        "importance": d.get("importance"),
        "risk": d.get("risk"),
        "time_required_min": d.get("time_required_min"),
        "energy": d.get("energy"),
        "economic_impact": d.get("economic_impact"),
        "personal_impact": d.get("personal_impact"),
        "kind": d.get("category"),
        "metadata": d.get("metadata"),
        "score": d.get("score"),
        "reason": d.get("reason"),
        "reason_tags": d.get("reason_tags"),
        "status": d.get("status"),
        "created_at": d.get("created_at"),
        "starts_at": d.get("starts_at"),
        "deadline": d.get("deadline"),
    }


@router.get("/priorities")
async def get_priorities(limit: int = 3, user=Depends(get_current_user)):
    """Top decisions in the legacy task-shape (Home v1 uses this)."""
    limit = max(1, min(limit, 20))
    ranked = await decisions.top(user["user_id"], limit=limit)
    return {"items": [decision_as_task(d) for d in ranked]}


@router.get("/tasks")
async def list_tasks(user=Depends(get_current_user)):
    ranked = await decisions.ranked(user["user_id"])
    all_docs = await decisions.list_all(user["user_id"])
    ranked_ids = {d["id"] for d in ranked}
    tail = [d for d in all_docs if d["id"] not in ranked_ids]
    return {"items": [decision_as_task(d) for d in ranked + tail]}


@router.post("/tasks")
async def create_task_legacy(body: TaskIn, user=Depends(get_current_user)):
    payload = body.model_dump()
    payload["description"] = payload.pop("context", None)
    payload["category"] = payload.pop("kind", "generic")
    doc = await decisions.create(user["user_id"], payload, origin="user:legacy_task")
    return decision_as_task(doc)


@router.post("/tasks/{task_id}/dismiss")
async def dismiss_task_legacy(task_id: str, user=Depends(get_current_user)):
    ok = await decisions.dismiss(user["user_id"], task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task non trovato")
    return {"ok": True}


@router.post("/tasks/{task_id}/complete")
async def complete_task_legacy(task_id: str, user=Depends(get_current_user)):
    ok = await decisions.complete(user["user_id"], task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task non trovato")
    return {"ok": True}


@router.post("/tasks/{task_id}/resolve")
async def resolve_task_legacy(task_id: str, user=Depends(get_current_user)):
    return await resolve_decision(task_id, user)
