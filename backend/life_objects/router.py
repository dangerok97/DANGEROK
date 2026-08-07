"""HTTP API for Life Objects — auth required; unused by main UI (shadow / tests)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import db, get_current_user, knowledge, life_graph
from life_objects.knowledge_model.models import (
    ConfirmHypothesisBody,
    DecisionOutcomeBody,
    ProposeDecisionBody,
    ProposeHypothesisBody,
    RejectHypothesisBody,
)
from life_objects.models import (
    LifeObjectCreateBody,
    LifeObjectEnrichBody,
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
        "enrichment": "narrative|questions|insights|temporal|health",
        "user_id": user["user_id"],
    }


@router.get("/home-v3-feed")
async def life_objects_home_v3_feed(
    limit: int = Query(20, ge=1, le=50),
    user=Depends(get_current_user),
):
    """Internal DTO for future Home V3 — default OFF, no FE branding."""
    return await _svc().home_v3_feed(user["user_id"], limit=limit)


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


@router.get("/{object_id}/narrative")
async def life_object_narrative(
    object_id: str,
    refresh: bool = Query(False),
    user=Depends(get_current_user),
):
    res = await _svc().get_narrative(user["user_id"], object_id, refresh=refresh)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{object_id}/narrative/refresh")
async def life_object_narrative_refresh(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_narrative(user["user_id"], object_id, refresh=True)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/questions")
async def life_object_questions(
    object_id: str,
    refresh: bool = Query(False),
    user=Depends(get_current_user),
):
    res = await _svc().get_questions(user["user_id"], object_id, refresh=refresh)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{object_id}/questions/refresh")
async def life_object_questions_refresh(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_questions(user["user_id"], object_id, refresh=True)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/insights")
async def life_object_insights(
    object_id: str,
    refresh: bool = Query(False),
    user=Depends(get_current_user),
):
    res = await _svc().get_insights(user["user_id"], object_id, refresh=refresh)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{object_id}/insights/refresh")
async def life_object_insights_refresh(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_insights(user["user_id"], object_id, refresh=True)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/health")
async def life_object_health(
    object_id: str,
    refresh: bool = Query(False),
    user=Depends(get_current_user),
):
    res = await _svc().get_health(user["user_id"], object_id, refresh=refresh)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{object_id}/health/refresh")
async def life_object_health_refresh(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_health(user["user_id"], object_id, refresh=True)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/history")
async def life_object_history(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_history(user["user_id"], object_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/relationships")
async def life_object_relationships(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_relationships(user["user_id"], object_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/temporal")
async def life_object_temporal(
    object_id: str,
    refresh: bool = Query(True),
    user=Depends(get_current_user),
):
    res = await _svc().refresh_section(
        user["user_id"], object_id, sections=["temporal"],
    ) if refresh else None
    if refresh:
        if not res or not res.get("ok"):
            raise HTTPException(status_code=404, detail=(res or {}).get("error") or "not_found")
        obj = res["object"]
        return {
            "ok": True,
            "object_id": object_id,
            "temporal": obj.get("temporal"),
        }
    obj = await _svc().get(user["user_id"], object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="not_found")
    return {"ok": True, "object_id": object_id, "temporal": obj.get("temporal")}


@router.post("/{object_id}/enrich")
async def life_object_enrich(
    object_id: str,
    body: Optional[LifeObjectEnrichBody] = None,
    user=Depends(get_current_user),
):
    """Re-run AI/fallback enrichment for selected sections."""
    payload = body or LifeObjectEnrichBody()
    res = await _svc().refresh_section(
        user["user_id"], object_id, sections=payload.sections,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


# --- Digital Twin Knowledge Model (read-only + minimal write for tests) ---


@router.get("/{object_id}/facts")
async def life_object_facts(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_facts(user["user_id"], object_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/hypotheses")
async def life_object_hypotheses(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_hypotheses(user["user_id"], object_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/decisions")
async def life_object_decisions(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_decisions_km(user["user_id"], object_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/timeline")
async def life_object_timeline(object_id: str, user=Depends(get_current_user)):
    res = await _svc().get_timeline_km(user["user_id"], object_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.get("/{object_id}/knowledge")
async def life_object_knowledge(object_id: str, user=Depends(get_current_user)):
    """Aggregate Digital Twin: facts | hypotheses | decisions | goals | memory | timeline."""
    res = await _svc().get_knowledge_bundle(user["user_id"], object_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{object_id}/hypotheses")
async def life_object_propose_hypothesis(
    object_id: str, body: ProposeHypothesisBody, user=Depends(get_current_user),
):
    """Internal/test write: seed Hypothesis (never written as Fact)."""
    res = await _svc().propose_hypothesis(
        user["user_id"], object_id,
        type=body.type,
        value=body.value,
        confidence=body.confidence,
        reason=body.reason,
        question_to_confirm=body.question_to_confirm,
        evidence=body.evidence,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{object_id}/hypotheses/confirm")
async def life_object_confirm_hypothesis(
    object_id: str, body: ConfirmHypothesisBody, user=Depends(get_current_user),
):
    """Internal/test write: user confirms hypothesis → Fact (never auto)."""
    res = await _svc().confirm_hypothesis(
        user["user_id"], object_id,
        hypothesis_id=body.hypothesis_id, verified_by=body.verified_by or "user",
    )
    if not res.get("ok"):
        code = 404 if res.get("error") in ("not_found", "hypothesis_not_found") else 400
        raise HTTPException(status_code=code, detail=res.get("error") or "confirm_failed")
    return res


@router.post("/{object_id}/hypotheses/reject")
async def life_object_reject_hypothesis(
    object_id: str, body: RejectHypothesisBody, user=Depends(get_current_user),
):
    """Internal/test write: user rejects hypothesis."""
    res = await _svc().reject_hypothesis(
        user["user_id"], object_id,
        hypothesis_id=body.hypothesis_id, reason=body.reason or "",
    )
    if not res.get("ok"):
        code = 404 if res.get("error") in ("not_found", "hypothesis_not_found") else 400
        raise HTTPException(status_code=code, detail=res.get("error") or "reject_failed")
    return res


@router.post("/{object_id}/decisions")
async def life_object_propose_decision(
    object_id: str, body: ProposeDecisionBody, user=Depends(get_current_user),
):
    """Internal/test write: propose Decision (suppressed if never_ask_again)."""
    res = await _svc().propose_knowledge_decision(
        user["user_id"], object_id,
        title=body.title,
        reason=body.reason,
        benefit=body.benefit,
        risk=body.risk,
        alternatives=body.alternatives,
        ai_reasoning=body.ai_reasoning,
        kind=body.kind,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error") or "not_found")
    return res


@router.post("/{object_id}/decisions/outcome")
async def life_object_decision_outcome(
    object_id: str, body: DecisionOutcomeBody, user=Depends(get_current_user),
):
    """Internal/test write: set decision outcome (incl. never_ask_again)."""
    res = await _svc().set_knowledge_decision_outcome(
        user["user_id"], object_id,
        decision_id=body.decision_id,
        outcome=body.outcome,
        user_choice=body.user_choice,
    )
    if not res.get("ok"):
        code = 404 if res.get("error") in ("not_found", "decision_not_found") else 400
        raise HTTPException(status_code=code, detail=res.get("error") or "outcome_failed")
    return res
