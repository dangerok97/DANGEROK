"""Behavioral Intelligence read-only router (Iterazione 15).

* Only GET endpoints. No POST/PUT/DELETE (contract).
* All endpoints require authentication.
* Cross-user isolation is guaranteed because the service filters by
  ``user_id`` extracted from the JWT.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import db, get_current_user
from behavioral_intelligence import BehavioralIntelligenceService
from behavioral_intelligence.types import BehavioralEventType

router = APIRouter(prefix="/behavior", tags=["behavior"])

# Single, lazily-initialized service instance shared across requests.
_service: Optional[BehavioralIntelligenceService] = None


def _get_service() -> BehavioralIntelligenceService:
    global _service
    if _service is None:
        _service = BehavioralIntelligenceService(db)
    return _service


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ISO datetime")


# ------------------------ GET /profile ------------------------
@router.get("/profile")
async def get_profile(user=Depends(get_current_user)) -> Dict[str, Any]:
    svc = _get_service()
    profile = await svc.get_profile(user["user_id"], persist=True)
    return profile.model_dump()


# ------------------------ GET /metrics ------------------------
@router.get("/metrics")
async def get_metrics(
    window_days: int = Query(60, ge=1, le=365),
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    svc = _get_service()
    metrics = await svc.get_metrics(user["user_id"], persist=True)
    # Note: window_days is metadata for the caller; the builder currently
    # uses a fixed window. Kept as query parameter for forward compatibility.
    payload = metrics.model_dump()
    payload["requested_window_days"] = window_days
    return payload


# ------------------------ GET /patterns ------------------------
@router.get("/patterns")
async def get_patterns(user=Depends(get_current_user)) -> Dict[str, Any]:
    svc = _get_service()
    patterns = await svc.get_patterns(user["user_id"], persist=True)
    return {
        "items": [p.model_dump() for p in patterns],
        "count": len(patterns),
    }


# ------------------------ GET /timeline ------------------------
@router.get("/timeline")
async def get_timeline(
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    event_types: Optional[str] = Query(None, description="Comma-separated list"),
    limit: int = Query(200, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    user=Depends(get_current_user),
) -> Dict[str, Any]:
    svc = _get_service()
    since_dt = _parse_iso(since)
    until_dt = _parse_iso(until)
    types: Optional[List[BehavioralEventType]] = None
    if event_types:
        types = []
        for t in event_types.split(","):
            t = t.strip()
            if not t:
                continue
            try:
                types.append(BehavioralEventType(t))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Unknown event_type: {t}")
    page = await svc.timeline_page(
        user["user_id"],
        since=since_dt,
        until=until_dt,
        event_types=types,
        limit=limit,
        skip=skip,
    )
    return page.model_dump()


# ------------------------ GET /confidence ------------------------
@router.get("/confidence")
async def get_confidence(user=Depends(get_current_user)) -> Dict[str, Any]:
    svc = _get_service()
    report = await svc.confidence_report(user["user_id"])
    return report.model_dump()
