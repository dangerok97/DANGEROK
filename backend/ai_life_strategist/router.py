"""Strategist HTTP surface — authenticated / internal next-question."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_life_strategist.service import ai_life_strategist_enabled, get_strategist_service
from deps import get_current_user

router = APIRouter(prefix="/strategist", tags=["ai-life-strategist"])


class NextQuestionBody(BaseModel):
    known_facts: Dict[str, Any] = Field(default_factory=dict)
    asked_questions: List[str] = Field(default_factory=list)
    asked_keys: List[str] = Field(default_factory=list)
    linked_doc_types: List[str] = Field(default_factory=list)
    last_user_text: Optional[str] = None
    session_phase: str = "active"
    domains_touched: List[str] = Field(default_factory=list)
    force_fallback: bool = False


@router.get("/status")
async def strategist_status(user=Depends(get_current_user)):
    svc = get_strategist_service()
    return {
        "ok": True,
        "enabled": svc.enabled(),
        "engine": "ai-life-strategist-1.0",
        "domains": svc.domains(),
        "flag": "AI_LIFE_STRATEGIST_ENABLED",
    }


@router.post("/next-question")
async def next_question(body: NextQuestionBody, user=Depends(get_current_user)):
    """Internal/auth: structured next question plan (never free text dump)."""
    if not ai_life_strategist_enabled():
        raise HTTPException(status_code=503, detail="ai_life_strategist_disabled")
    svc = get_strategist_service()
    plan = await svc.next_question(
        user["user_id"],
        known_facts=body.known_facts,
        asked_questions=body.asked_questions,
        asked_keys=body.asked_keys,
        linked_doc_types=body.linked_doc_types,
        last_user_text=body.last_user_text,
        session_phase=body.session_phase,
        domains_touched=body.domains_touched,
        force_fallback=body.force_fallback,
    )
    return {"ok": True, "plan": plan.public(), "explain": svc.explain_plan(plan)}
