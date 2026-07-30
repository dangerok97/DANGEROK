"""AUTO-LINK router."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auto_link import MATCHER_VERSION as AUTOLINK_MATCHER_VERSION
from deps import auto_link, db, get_current_user

router = APIRouter(prefix="/auto-link", tags=["auto_link"])


class AutoLinkReasonIn(BaseModel):
    reason: Optional[str] = None


@router.post("/decisions/{decision_id}/analyze")
async def auto_link_analyze(decision_id: str, user=Depends(get_current_user)):
    result = await auto_link.analyze(user["user_id"], decision_id, force=False)
    if result.get("error") == "decision_not_found":
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return result


@router.post("/decisions/{decision_id}/reanalyze")
async def auto_link_reanalyze(decision_id: str, user=Depends(get_current_user)):
    result = await auto_link.reanalyze(user["user_id"], decision_id)
    if result.get("error") == "decision_not_found":
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return result


@router.get("/decisions/{decision_id}/proposals")
async def auto_link_list_proposals(
    decision_id: str,
    include_all: bool = False,
    user=Depends(get_current_user),
):
    d = await db.decisions.find_one({"id": decision_id, "user_id": user["user_id"]}, {"_id": 0, "id": 1})
    if not d:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    items = await auto_link.list_proposals(user["user_id"], decision_id, include_all=include_all)
    return {"items": items, "matcher_version": AUTOLINK_MATCHER_VERSION}


@router.get("/proposals/{proposal_id}")
async def auto_link_get_proposal(proposal_id: str, user=Depends(get_current_user)):
    doc = await auto_link.get_proposal(user["user_id"], proposal_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    return doc


@router.post("/proposals/{proposal_id}/accept")
async def auto_link_accept(proposal_id: str, body: Optional[AutoLinkReasonIn] = None, user=Depends(get_current_user)):
    reason = body.reason if body else None
    doc = await auto_link.accept(user["user_id"], proposal_id, reason=reason)
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta non trovata o in stato non accettabile")
    return doc


@router.post("/proposals/{proposal_id}/reject")
async def auto_link_reject(proposal_id: str, body: Optional[AutoLinkReasonIn] = None, user=Depends(get_current_user)):
    reason = body.reason if body else None
    doc = await auto_link.reject(user["user_id"], proposal_id, reason=reason)
    if not doc:
        raise HTTPException(status_code=404, detail="Proposta non trovata o in stato non rifiutabile")
    return doc
