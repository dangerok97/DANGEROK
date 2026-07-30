"""Behavior Shadow read-only router (iter17)."""
from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query

from deps import db, get_current_user
from behavior_aware_decisions import BehaviorShadowService
from behavior_aware_decisions.rules import ALL_RULES
from behavior_aware_decisions.types import (
    RULE_SET_VERSION, DELTA_MIN_TOTAL, DELTA_MAX_TOTAL, DELTA_MAX_PER_RULE,
)
from behavior_aware_decisions.comparison import compare_rankings

router = APIRouter(prefix="/behavior-shadow", tags=["behavior-shadow"])
_svc: Optional[BehaviorShadowService] = None


def _get() -> BehaviorShadowService:
    global _svc
    if _svc is None:
        _svc = BehaviorShadowService(db)
    return _svc


@router.get("/rules")
async def list_rules(user=Depends(get_current_user)) -> Dict[str, Any]:
    return {
        "rule_set_version": RULE_SET_VERSION,
        "caps": {"delta_min_total": DELTA_MIN_TOTAL, "delta_max_total": DELTA_MAX_TOTAL, "per_rule": DELTA_MAX_PER_RULE},
        "confidence_multipliers": {"low": 0.0, "medium": 0.5, "high": 1.0},
        "rules": [{"rule_id": fn.__name__.replace("rule_", ""), "callable": fn.__name__} for fn in ALL_RULES],
    }


@router.get("/decisions/{decision_id}")
async def get_for_decision(decision_id: str, user=Depends(get_current_user)) -> Dict[str, Any]:
    svc = _get(); await svc.ensure_ready()
    items = await svc.storage.list_by_user(user["user_id"], decision_id=decision_id, limit=20)
    latest = items[0] if items else None
    return {"decision_id": decision_id, "latest": latest, "history": items}


@router.get("/evaluations")
async def list_evaluations(
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    decision_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    svc = _get(); await svc.ensure_ready()
    items = await svc.storage.list_by_user(user["user_id"], limit=limit, skip=skip, decision_id=decision_id)
    return {"items": items, "count": len(items)}


@router.get("/stats")
async def stats(user=Depends(get_current_user)) -> Dict[str, Any]:
    svc = _get(); await svc.ensure_ready()
    return await svc.storage.stats(user["user_id"])


@router.get("/comparison")
async def comparison(user=Depends(get_current_user)) -> Dict[str, Any]:
    """Compare real ranking vs shadow ranking using latest evaluations."""
    svc = _get(); await svc.ensure_ready()
    uid = user["user_id"]
    # Load real ranking directly from decisions collection (score desc).
    cur = db["decisions"].find({"user_id": uid, "status": {"$in": ["open", "in_progress"]}},
                                {"_id": 0, "id": 1, "score": 1, "category": 1,
                                 "priority": 1, "deadline": 1, "updated_at": 1,
                                 "time_required_min": 1}).sort("score", -1).limit(100)
    real_items = await cur.to_list(length=100)
    real_list = [{"id": d.get("id"), "score": d.get("score", 0)} for d in real_items]
    # Kick off evaluations (idempotent + gated).
    await svc.evaluate_batch(uid, real_items)
    latest_by_id: Dict[str, float] = {}
    for did in [r["id"] for r in real_list]:
        rows = await svc.storage.list_by_user(uid, decision_id=did, limit=1)
        if rows:
            latest_by_id[did] = float(rows[0].get("shadow_priority_delta", 0.0))
    return compare_rankings(real_list, latest_by_id)
