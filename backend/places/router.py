"""
HTTP surface for Vita → Luoghi.

What the screen needs: the places somebody keeps, the ones waiting to be
named, and what ORA is currently allowed to observe. Permission lives in
`location` and is only read here — Vita shows what ORA *knows*, Profilo shows
what ORA *may see*, and one screen owning both would blur a distinction that
matters.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user
from places.service import PlacesService

router = APIRouter(prefix="/places", tags=["places"])


def _svc() -> PlacesService:
    from deps import db

    return PlacesService(db)


class PlaceIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    role: Literal["home", "work", "other"] = "other"
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    accuracy_meters: Optional[float] = Field(None, ge=0, le=100000)
    address: str = Field(default="", max_length=240)
    locality: str = Field(default="", max_length=160)
    source: Literal["user_stated", "current_position"] = "user_stated"


class RenameIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)


class ObservationIn(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_meters: Optional[float] = Field(None, ge=0, le=100000)
    dwell_seconds: Optional[int] = Field(None, ge=0, le=86400)
    # When the fix was taken. Absent means now; a queued batch says when.
    observed_at: Optional[str] = Field(None, max_length=40)


class CandidateAnswerIn(BaseModel):
    answer: str = Field(..., min_length=1, max_length=400)


class ZoneIn(BaseModel):
    """How big a place is. Leaving is always the wider circle."""

    entry_radius_m: float = Field(..., ge=25, le=2000)
    exit_radius_m: float = Field(..., ge=25, le=2000)


@router.get("")
async def list_places(user=Depends(get_current_user)):
    """
    Everything Vita → Luoghi renders.

    Permission state comes along because the screen has to be able to say
    "location is off" without guessing from an empty list — no places and no
    permission are different situations and read differently to a person.
    """
    svc = _svc()
    uid = user["user_id"]
    places = await svc.list_places(uid)
    candidates = [
        c for c in await svc.repo.list_candidates(uid, outcomes=["asked"]) if not c.muted
    ]

    permission = {"preference": "off", "state": "not_requested"}
    try:
        from deps import db
        from location.service import LocationService

        location = LocationService(db)
        presence = await location.build_presence(uid)
        permission = {
            "preference": presence.preference,
            "state": presence.permission_state or "not_requested",
            "freshness": presence.freshness,
        }
    except Exception:
        pass

    presence = await svc.presence_summary(uid)
    # One figure per place, not a dashboard: how much of this week it has had.
    # The list is a list of places, and a place that needs a chart to be
    # understood is not being shown, it is being analysed at somebody.
    week = {p.id: await svc.time_at(uid, p.id, period="this_week") for p in places}
    return {
        "places": [
            {
                **p.public(),
                "presence": presence.get(p.id),
                "this_week": {
                    "visits": week[p.id].get("visits", 0),
                    "total_seconds": week[p.id].get("total_seconds", 0),
                },
            }
            for p in places
        ],
        "candidates": [
            {
                "id": c.id,
                "locality": c.locality or None,
                "address_hint": c.address_hint or None,
                "times_seen": c.observation_count,
                "last_seen": c.last_seen,
                "question_id": c.question_id,
            }
            for c in candidates
        ],
        "permission": permission,
    }


@router.post("")
async def create_place(body: PlaceIn, user=Depends(get_current_user)):
    from places.models import Coordinates

    coordinates = None
    if body.latitude is not None and body.longitude is not None:
        coordinates = Coordinates(
            latitude=body.latitude,
            longitude=body.longitude,
            accuracy_meters=body.accuracy_meters,
            precision="exact",
        )
    place = await _svc().save_place(
        user["user_id"],
        label=body.label,
        role=body.role,
        coordinates=coordinates,
        address=body.address,
        locality=body.locality,
        source=body.source,
    )
    return {"place": place.public()}


@router.delete("/history")
async def forget_all_history(user=Depends(get_current_user)):
    """Every stay, everywhere. The places themselves survive."""
    return await _svc().forget_presence(user["user_id"])


@router.patch("/{place_id}")
async def rename_place(place_id: str, body: RenameIn, user=Depends(get_current_user)):
    place = await _svc().rename_place(user["user_id"], place_id, body.label)
    if place is None:
        raise HTTPException(status_code=404, detail="luogo non trovato")
    return {"place": place.public()}


@router.delete("/{place_id}")
async def remove_place(place_id: str, user=Depends(get_current_user)):
    if not await _svc().remove_place(user["user_id"], place_id):
        raise HTTPException(status_code=404, detail="luogo non trovato")
    return {"removed": True}


@router.get("/{place_id}")
async def place_detail(place_id: str, user=Depends(get_current_user)):
    """
    One place, and what ORA knows about being in it.

    Coordinates are not here. A detail screen needs a name, a state and some
    times; the numbers only leave the server when something is being routed to.
    """
    svc = _svc()
    uid = user["user_id"]
    place = await svc.get_place(uid, place_id)
    if place is None or place.state == "deleted":
        raise HTTPException(status_code=404, detail="luogo non trovato")

    summary = (await svc.presence_summary(uid)).get(place_id) or {}
    sessions = await svc.repo.sessions_for(uid, place_id=place_id, limit=10)
    zone = place.zone
    return {
        "place": place.public(),
        "presence": summary,
        # The size is shown as words, not metres: a person tuning a radius by
        # hand is not the experience, and "managed automatically" is the truth
        # until they say otherwise.
        "zone": {
            "managed": zone is None or zone.source == "default",
            "entry_radius_m": zone.entry_radius_m if zone else None,
            "exit_radius_m": zone.exit_radius_m if zone else None,
        },
        "recent_sessions": [x.public() for x in sessions],
        # The micro-summary the detail screen shows. Two numbers, because two
        # numbers are what somebody actually wants to know about a place.
        "this_week": await svc.time_at(uid, place_id, period="this_week"),
    }


@router.put("/{place_id}/zone")
async def set_zone(place_id: str, body: ZoneIn, user=Depends(get_current_user)):
    place = await _svc().set_zone(
        user["user_id"],
        place_id,
        entry_radius_m=body.entry_radius_m,
        exit_radius_m=body.exit_radius_m,
    )
    if place is None:
        raise HTTPException(
            status_code=404, detail="luogo non trovato o senza coordinate"
        )
    return {"place": place.public()}


@router.delete("/{place_id}/history")
async def forget_place_history(place_id: str, user=Depends(get_current_user)):
    """
    Forget having been there, keep the place.

    The common request: somebody wants ORA to know where they live without
    keeping a record of every night they slept in it.
    """
    return await _svc().forget_presence(user["user_id"], place_id=place_id)


@router.post("/observations")
async def record_observation(body: ObservationIn, user=Depends(get_current_user)):
    """
    One sighting from the device.

    Called when the app has a fix and permission, not on a timer. There is no
    continuous sampling here and nothing in this endpoint asks for any.
    """
    result = await _svc().record_observation(
        user["user_id"],
        latitude=body.latitude,
        longitude=body.longitude,
        accuracy_meters=body.accuracy_meters,
        dwell_seconds=body.dwell_seconds,
        observed_at=body.observed_at,
    )
    return result


@router.post("/candidates/{candidate_id}/answer")
async def answer_candidate(
    candidate_id: str, body: CandidateAnswerIn, user=Depends(get_current_user)
):
    """The person says what a repeated spot is — the only way one becomes a place."""
    result = await _svc().answer_candidate(user["user_id"], candidate_id, body.answer)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason") or "non chiaro")
    return result


@router.post("/candidates/review")
async def review_candidates(user=Depends(get_current_user)):
    """Ask the model whether any repeated spot is worth a question."""
    return {"raised": await _svc().review_candidates(user["user_id"])}


@router.delete("/observations/all")
async def forget_observations(user=Depends(get_current_user)):
    """Erase what the device noticed. Places the person named stay."""
    return await _svc().forget_observations(user["user_id"])
