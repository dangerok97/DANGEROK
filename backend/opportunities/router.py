"""
A debug surface, and deliberately nothing more.

    OPPORTUNITY != NOTIFICATION.

Sprint 2 gave an opportunity a quiet place on Home — inside Aggiornamenti,
never a tab of its own and never a notification. These endpoints are still
the debug surface: they let the reasoning be run and inspected. What a person
actually sees arrives with their Home, in human words, through the surfacing
decision rather than through anything here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user
from opportunities.service import OpportunityService

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _svc() -> OpportunityService:
    from deps import db

    return OpportunityService(db)


class ScanIn(BaseModel):
    # What moved, when the caller knows. It focuses attention; it never means
    # that a change is an opportunity.
    changes: list = Field(default_factory=list, max_length=6)
    source_context: str = Field(default="manual_scan", max_length=120)


class DismissIn(BaseModel):
    # "Not now" and "never again" are different answers.
    suppress: bool = False


class ChangeIn(BaseModel):
    """
    A domain saying something moved. Facts only — there is deliberately no
    field here for saying that it matters.
    """

    source: str = Field(max_length=40)
    kind: str = Field(max_length=60)
    entity_ref: str = Field(default="", max_length=120)
    entity_kind: str = Field(default="", max_length=40)
    before: str = Field(default="", max_length=160)
    after: str = Field(default="", max_length=160)
    occurred_at: str = Field(default="", max_length=40)


class ReviewIn(BaseModel):
    # Skip the cost guards. For inspection, never for the request path.
    force: bool = False


class DeferIn(BaseModel):
    """
    Nothing to fill in.

    "Più tardi" used to carry a number of hours, which put the judgement in
    the caller's hands — and a screen has no idea how long later should be.
    Kept as a body so the shape of the endpoint does not change.
    """


@router.get("")
async def list_opportunities(user=Depends(get_current_user)):
    svc = _svc()
    await svc.expire_past(user["user_id"])
    return {"opportunities": [o.public() for o in await svc.list_active(user["user_id"])]}


@router.post("/scan")
async def scan(body: ScanIn, user=Depends(get_current_user)):
    """Ask whether anything deserves attention. Usually the answer is nothing."""
    result = await _svc().scan(
        user["user_id"],
        changes=list(body.changes or []),
        source_context=body.source_context,
    )
    return result.public()


@router.post("/{opportunity_id}/review")
async def review(opportunity_id: str, user=Depends(get_current_user)):
    result = await _svc().review(user["user_id"], opportunity_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason") or "non trovata")
    return result


@router.post("/{opportunity_id}/dismiss")
async def dismiss(opportunity_id: str, body: DismissIn, user=Depends(get_current_user)):
    result = await _svc().dismiss(
        user["user_id"], opportunity_id, suppress=body.suppress
    )
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="non trovata")
    return result


@router.post("/{opportunity_id}/resolve")
async def resolve(opportunity_id: str, user=Depends(get_current_user)):
    result = await _svc().resolve(user["user_id"], opportunity_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="non trovata")
    return result


@router.post("/changes")
async def record_change(body: ChangeIn, user=Depends(get_current_user)):
    """
    Note that something moved. It earns a review, never attention.

    The response says what admission did with it — accepted, duplicate,
    coalesced, stale — and none of those words is about importance.
    """
    from opportunities.discovery import OpportunityDiscovery
    from deps import db

    return await OpportunityDiscovery(db).note(
        user["user_id"],
        source=body.source,
        kind=body.kind,
        entity_ref=body.entity_ref,
        entity_kind=body.entity_kind,
        before=body.before,
        after=body.after,
        occurred_at=body.occurred_at or None,
    )


@router.post("/review")
async def review_now(body: ReviewIn, user=Depends(get_current_user)):
    """Run the continuous review by hand, guards and all."""
    from opportunities.discovery import OpportunityDiscovery
    from deps import db

    outcome = await OpportunityDiscovery(db).review(
        user["user_id"], reason="user_requested", force=body.force
    )
    return {
        "ran": outcome.ran,
        "skipped": outcome.skipped or None,
        "changes_reviewed": outcome.changes_reviewed,
        "scan": outcome.scan.public() if outcome.scan else None,
    }


@router.post("/surface")
async def decide_surface(user=Depends(get_current_user)):
    """Ask whether any of what we believe belongs on screen right now."""
    from opportunities.surfacing import SurfacingService
    from deps import db

    return await SurfacingService(db).decide(user["user_id"])


@router.get("/surface")
async def what_is_visible(user=Depends(get_current_user)):
    """What Home would show, in the words a person reads."""
    from opportunities.surfacing import SurfacingService
    from deps import db

    return {"opportunities": await SurfacingService(db).for_home(user["user_id"])}


@router.post("/{opportunity_id}/defer")
async def defer(opportunity_id: str, body: DeferIn, user=Depends(get_current_user)):
    """"Più tardi" — off the screen, still true, nothing scheduled."""
    from opportunities.surfacing import SurfacingService
    from deps import db

    result = await SurfacingService(db).defer(user["user_id"], opportunity_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason"))
    return result


@router.post("/{opportunity_id}/seen")
async def seen(opportunity_id: str, user=Depends(get_current_user)):
    """It has been in front of them. Not that they did anything about it."""
    from opportunities.surfacing import SurfacingService
    from deps import db

    result = await SurfacingService(db).mark_seen(user["user_id"], opportunity_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason"))
    return result


@router.get("/{opportunity_id}")
async def one(opportunity_id: str, user=Depends(get_current_user)):
    """
    One opportunity, in the words a person reads.

    What a conversation opened from a card needs in order to say why it was
    raised, without the screen having to hold state across a navigation.
    """
    from opportunities.service import OpportunityService
    from deps import db

    found = await OpportunityService(db).repo.get(user["user_id"], opportunity_id)
    if found is None:
        raise HTTPException(status_code=404, detail="unknown_opportunity")
    return found.for_home()
