"""HTTP API: POST /api/intent/classify"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from deps import get_current_user
from intent_engine.models import ClassifyBody
from intent_engine.service import get_intent_engine

router = APIRouter(prefix="/intent", tags=["intent_engine"])


@router.post("/classify")
async def classify_intent(body: ClassifyBody, user=Depends(get_current_user)):
    text = (body.text or "").strip()
    if not text and body.intent is None:
        raise HTTPException(status_code=400, detail="Provide text or precomputed intent")
    eng = get_intent_engine()
    result = await eng.classify_body(body)
    return {
        "intent": result.public(),
        "user_id": user.get("user_id"),
    }
