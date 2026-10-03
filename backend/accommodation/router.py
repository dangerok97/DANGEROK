"""Authenticated accommodation search surface."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from accommodation.service import AccommodationError, AccommodationService
from deps import get_current_user

router = APIRouter(prefix="/accommodations", tags=["accommodations"])


class AccommodationProductSelection(BaseModel):
    id: str = Field(min_length=1, max_length=180)
    number_of_adults: int = Field(ge=1, le=30)
    children: list[int] = Field(default_factory=list, max_length=30)


class AccommodationPreviewIn(BaseModel):
    accommodation_id: int | str
    checkin: str = Field(min_length=10, max_length=10)
    checkout: str = Field(min_length=10, max_length=10)
    products: list[AccommodationProductSelection] = Field(min_length=1, max_length=12)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    platform: str | None = Field(default=None, max_length=20)
    travel_purpose: str | None = Field(default=None, max_length=20)


class BookerNameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)


class BookerAddressIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_line: str = Field(min_length=1, max_length=180)
    city: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=2, max_length=2)
    post_code: str = Field(min_length=1, max_length=30)


class BookerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: BookerNameIn
    address: BookerAddressIn
    email: str = Field(min_length=3, max_length=254)
    telephone: str = Field(min_length=3, max_length=40)
    language: str = Field(default="it", min_length=2, max_length=10)
    company: str | None = Field(default=None, max_length=120)


class BookingGuestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254)


class BookingProductIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=180)
    guests: list[BookingGuestIn] = Field(min_length=1, max_length=30)
    bed_configuration: str | None = Field(default=None, max_length=180)


class CardlessPaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: str = Field(min_length=1, max_length=40)
    timing: str = Field(min_length=1, max_length=40)
    include_receipt: bool = True


class BookingRemarksIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    special_requests: str | None = Field(default=None, max_length=500)
    estimated_arrival_time: dict | None = None


class BookingCheckoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=1, max_length=80)
    booker: BookerIn
    products: list[BookingProductIn] = Field(min_length=1, max_length=12)
    payment: CardlessPaymentIn
    remarks: BookingRemarksIn | None = None


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


@router.post("/preview")
async def preview(body: AccommodationPreviewIn, user=Depends(get_current_user)):
    from deps import db

    service = AccommodationService(db)
    try:
        return await service.preview(
            owner_id=user["user_id"],
            accommodation_id=body.accommodation_id,
            checkin=body.checkin,
            checkout=body.checkout,
            products=[p.model_dump() for p in body.products],
            currency=body.currency,
            country=body.country,
            platform=body.platform,
            travel_purpose=body.travel_purpose,
        )
    except AccommodationError as exc:
        status = 503 if exc.retryable or exc.code in (
            "provider_not_configured", "secure_vault_unavailable"
        ) else 422
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": str(exc), "retryable": exc.retryable},
        ) from exc


@router.post("/checkout")
async def prepare_checkout(body: BookingCheckoutIn, user=Depends(get_current_user)):
    """Freeze traveller details securely. Does not create a reservation."""
    from deps import db

    service = AccommodationService(db)
    try:
        return await service.prepare_checkout(
            owner_id=user["user_id"],
            preview_id=body.preview_id,
            booker=body.booker.model_dump(exclude_none=True),
            products=[p.model_dump(exclude_none=True) for p in body.products],
            payment=body.payment.model_dump(),
            remarks=body.remarks.model_dump(exclude_none=True) if body.remarks else None,
        )
    except AccommodationError as exc:
        status = 503 if exc.retryable or exc.code == "secure_vault_unavailable" else 422
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": str(exc), "retryable": exc.retryable},
        ) from exc
