"""Bearer-authenticated wardrobe; photos never have public media URLs."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from deps import db, get_current_user
from .service import (
    MAX_UPLOAD, GarmentInput, OutfitInput, PhotoCipher,
    WardrobeError, WardrobeService, make_thumbnail,
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


@router.post("/items/{item_id}/photo")
async def save_photo(item_id: str, request: Request, revision: int = Query(..., ge=1),
                     user=Depends(get_current_user)):
    _check_id(item_id)
    if request.headers.get("content-type", "").split(";")[0].lower() not in (
        "image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Carica una foto JPEG, PNG o WebP.")
    raw = bytearray()
    try:
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "La foto supera 5 MB.")
            raw.extend(chunk)
        thumbnail = await run_in_threadpool(make_thumbnail, bytes(raw))
        return {"item": await _call(_service().save_photo(user["user_id"], item_id, revision, thumbnail))}
    except WardrobeError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    finally:
        raw.clear()


@router.post("/outfits")
async def outfits(body: OutfitInput, user=Depends(get_current_user)):
    return await _call(_service().outfits(user["user_id"], body))
