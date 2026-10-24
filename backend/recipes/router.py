"""ORA Cucina endpoints; same bearer auth and owner scoping as the app."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from deps import db, get_current_user
from . import importer
from .parser import URL_PATTERN
from .service import RecipeError, RecipeService, RecipeWrite, SourceInput


def no_cache(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/recipes", tags=["recipes"], dependencies=[Depends(no_cache)])


def service() -> RecipeService:
    return RecipeService(db)


@router.post("/preview")
async def preview_recipe(body: SourceInput, user=Depends(get_current_user)):
    """A link is read (structured page, or the post's own words); text is ordered. Never saved here."""
    source = body.source.strip()
    try:
        if URL_PATTERN.fullmatch(source):
            if not importer.allow(user["user_id"]):
                raise HTTPException(429, "Troppe importazioni nell'ultima ora. Riprova più tardi.")
            return await importer.from_link(source)
        return await importer.from_text(source)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/preview-photo")
async def preview_photo(request: Request, user=Depends(get_current_user)):
    """A photo of a book page or a screenshot. Read once, never stored."""
    from wardrobe.service import MAX_UPLOAD, WardrobeError, make_source_photo

    if request.headers.get("content-type", "").split(";")[0].lower() not in (
            "image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Carica una foto JPEG, PNG o WebP.")
    if not importer.allow(user["user_id"]):
        raise HTTPException(429, "Troppe importazioni nell'ultima ora. Riprova più tardi.")
    raw = bytearray()
    try:
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "La foto supera 5 MB.")
            raw.extend(chunk)
        from starlette.concurrency import run_in_threadpool
        # EXIF-free, bounded copy: the same normalisation the wardrobe uses.
        clean = await run_in_threadpool(make_source_photo, bytes(raw))
    except WardrobeError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    finally:
        raw.clear()
    return await importer.from_photo(clean)


@router.get("/items")
async def list_recipes(user=Depends(get_current_user)):
    return {"items": await service().list(user["user_id"])}


@router.post("/items", status_code=200)
async def save_recipe(body: RecipeWrite, user=Depends(get_current_user)):
    try:
        item, created = await service().create(user["user_id"], body)
        return {"item": item, "created": created}
    except (RecipeError, ValueError) as exc:
        raise HTTPException(getattr(exc, "status", 422), str(exc)) from None


@router.put("/items/{recipe_id}")
async def edit_recipe(recipe_id: str, body: RecipeWrite, user=Depends(get_current_user)):
    try:
        return {"item": await service().update(user["user_id"], recipe_id, body)}
    except (RecipeError, ValueError) as exc:
        raise HTTPException(getattr(exc, "status", 422), str(exc)) from None


@router.delete("/items/{recipe_id}")
async def remove_recipe(recipe_id: str, revision: int = Query(..., ge=1), user=Depends(get_current_user)):
    try:
        await service().delete(user["user_id"], recipe_id, revision)
        return {"deleted": True}
    except RecipeError as exc:
        raise HTTPException(exc.status, str(exc)) from None
