"""ORA Cucina endpoints; same bearer auth and owner scoping as the app."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from deps import db, get_current_user
from .parser import preview
from .service import RecipeError, RecipeService, RecipeWrite, SourceInput


def no_cache(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/recipes", tags=["recipes"], dependencies=[Depends(no_cache)])


def service() -> RecipeService:
    return RecipeService(db)


@router.post("/preview")
async def preview_recipe(body: SourceInput, user=Depends(get_current_user)):
    try:
        return preview(body.source)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


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
