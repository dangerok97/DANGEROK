"""Authenticated accommodation search surface."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from accommodation.service import AccommodationError, AccommodationService
from deps import get_current_user

router = APIRouter(prefix="/accommodations", tags=["accommodations"])


class AccommodationSearchIn(BaseModel):
    destination: str = Field(min_length=2, max_length=160)
    checkin: str = Field(min_length=10, max_length=10)
    checkout: str = Field(min_length=10, max_length=10)
    adults: int = Field(default=2, ge=1, le=30)
    rooms: int = Field(default=1, ge=1, le=30)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(default=15.0, ge=0.5, le=100)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    rows: int = Field(default=20, ge=10, le=100)
    max_price: float | None = Field(default=None, ge=0)
    min_review_score: float | None = Field(default=None, ge=1, le=10)


@router.get("/providers")
async def providers(user=Depends(get_current_user)):
    _ = user["user_id"]
    return AccommodationService().readiness()


@router.post("/search")
async def search(body: AccommodationSearchIn, user=Depends(get_current_user)):
    _ = user["user_id"]
    try:
        return await AccommodationService().search(**body.model_dump())
    except AccommodationError as exc:
        status = 503 if exc.retryable or exc.code == "provider_not_configured" else 422
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": str(exc), "retryable": exc.retryable},
        ) from exc
