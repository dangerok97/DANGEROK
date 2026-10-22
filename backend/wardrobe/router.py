"""Bearer-authenticated wardrobe; photos never have public media URLs."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from deps import db, get_current_user
from .classify import analyze_photo, enforce_owner_quota
from .appearance import AppearanceConfirmation
from .preferences import OutfitFeedbackInput
from .cutout import CutoutApproval, CutoutRemove, cutout_ready
from .service import (
    MAX_UPLOAD, GarmentInput, OutfitInput, PhotoCipher,
    WardrobeError, WardrobeService, make_thumbnail, make_source_photo,
)


def _private(response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


router = APIRouter(prefix="/wardrobe", tags=["wardrobe"], dependencies=[Depends(_private)])


def _service() -> WardrobeService:
    try:
        return WardrobeService(db, PhotoCipher.configured())
    except WardrobeError as exc:
        raise HTTPException(exc.status, str(exc)) from None


async def _call(task):
    try:
        return await task
    except WardrobeError as exc:
        raise HTTPException(exc.status, str(exc)) from None


def _check_id(item_id: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", item_id):
        raise HTTPException(422, "Identificativo capo non valido.")


@router.get("/items")
async def list_items(user=Depends(get_current_user)):
    return {"items": await _call(_service().list_items(user["user_id"]))}


@router.put("/items")
async def save_item(body: GarmentInput, user=Depends(get_current_user)):
    return {"item": await _call(_service().save(user["user_id"], body))}


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, revision: int = Query(..., ge=1), user=Depends(get_current_user)):
    _check_id(item_id)
    await _call(_service().delete(user["user_id"], item_id, revision))
    return {"deleted": True}


async def _read_photo(request: Request) -> tuple[bytes, bytes]:
    if request.headers.get("content-type", "").split(";")[0].lower() not in (
        "image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Carica una foto JPEG, PNG o WebP.")
    raw = bytearray()
    try:
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "La foto supera 5 MB.")
            raw.extend(chunk)
        # Preserve the user-supplied view in an EXIF-free, size-bounded reference
        # plus a thumbnail. Full upload bytes never enter persistent storage.
        thumb = await run_in_threadpool(make_thumbnail, bytes(raw))
        source = await run_in_threadpool(make_source_photo, bytes(raw))
        return thumb, source
    except WardrobeError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    finally:
        raw.clear()


@router.post("/items/{item_id}/photo")
@router.post("/items/{item_id}/photo/front")
async def save_photo(item_id: str, request: Request, revision: int = Query(..., ge=1),
                     user=Depends(get_current_user)):
    _check_id(item_id)
    thumbnail, source = await _read_photo(request)
    return {"item": await _call(_service().save_photo(
        user["user_id"], item_id, revision, thumbnail, source))}


@router.post("/items/{item_id}/photo/back")
async def save_back_photo(item_id: str, request: Request, revision: int = Query(..., ge=1),
                          user=Depends(get_current_user)):
    _check_id(item_id)
    thumbnail, source = await _read_photo(request)
    return {"item": await _call(_service().save_back_photo(
        user["user_id"], item_id, revision, thumbnail, source))}


@router.delete("/items/{item_id}/photo/back")
async def remove_back_photo(item_id: str, revision: int = Query(..., ge=1),
                            user=Depends(get_current_user)):
    _check_id(item_id)
    return {"item": await _call(_service().delete_back_photo(
        user["user_id"], item_id, revision))}


@router.post("/outfits")
async def outfits(body: OutfitInput, user=Depends(get_current_user)):
    return await _call(_service().outfits(user["user_id"], body))


@router.post("/analyze")
async def analyze_garment(request: Request, user=Depends(get_current_user)):
    """Explicit, non-persistent draft. One image only; never save AI guesses."""
    if request.headers.get("content-type", "").split(";")[0].lower() not in (
        "image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Carica una foto JPEG, PNG o WebP.")

    # Check the account-scoped cost cap before reading and forwarding the photo.
    await _call(enforce_owner_quota(db, user["user_id"]))
    raw = bytearray()
    try:
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "La foto supera 5 MB.")
            raw.extend(chunk)
        clean = await run_in_threadpool(make_thumbnail, bytes(raw))
    except WardrobeError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    finally:
        raw.clear()
    # No insertion into MongoDB, no persistent photo, no raw provider output.
    return await _call(analyze_photo(clean))



@router.post("/items/{item_id}/appearance/analyze")
async def analyze_saved_appearance(
    item_id: str, revision: int = Query(..., ge=1),
    user=Depends(get_current_user),
):
    """Only the authenticated owner can explicitly send their stored photo to AI."""
    _check_id(item_id)
    return await _call(_service().analyze_saved_photo(
        user["user_id"], item_id, revision))


@router.put("/items/{item_id}/appearance")
async def confirm_saved_appearance(
    item_id: str, body: AppearanceConfirmation,
    user=Depends(get_current_user),
):
    """A second, explicit confirmation stores validated visual attributes."""
    _check_id(item_id)
    return {"item": await _call(_service().confirm_appearance(
        user["user_id"], item_id, body))}


@router.delete("/items/{item_id}/appearance")
async def clear_saved_appearance(
    item_id: str, revision: int = Query(..., ge=1),
    user=Depends(get_current_user),
):
    _check_id(item_id)
    return {"item": await _call(_service().clear_appearance(
        user["user_id"], item_id, revision))}


@router.post("/outfits/feedback")
async def outfit_feedback(body: OutfitFeedbackInput, user=Depends(get_current_user)):
    """Owner-bound, confirmed like/dislike on an existing complete outfit."""
    return await _call(_service().record_outfit_feedback(user["user_id"], body))



@router.get("/showcase/availability")
async def showcase_availability(user=Depends(get_current_user)):
    return {"enabled": cutout_ready()}


@router.post("/items/{item_id}/showcase/preview")
async def showcase_preview(
    item_id: str, revision: int = Query(..., ge=1),
    view: str = Query("front", pattern=r"^(front|back)$"),
    user=Depends(get_current_user),
):
    _check_id(item_id)
    return await _call(_service().cutout_preview(
        user["user_id"], item_id, revision, view))


@router.put("/items/{item_id}/showcase")
async def showcase_accept(item_id: str, body: CutoutApproval,
                           user=Depends(get_current_user)):
    _check_id(item_id)
    return {"item": await _call(_service().cutout_accept(
        user["user_id"], item_id, body))}


@router.delete("/items/{item_id}/showcase")
async def showcase_remove(item_id: str, body: CutoutRemove,
                           user=Depends(get_current_user)):
    _check_id(item_id)
    return {"item": await _call(_service().cutout_remove(
        user["user_id"], item_id, body))}
