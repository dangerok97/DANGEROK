"""AI Core accommodation capabilities.

Search and preview are read-only provider calls. Neither creates a reservation.
Booking remains a separate world-changing effect behind the Personal Agent.
"""
from __future__ import annotations

from typing import Any, Dict

from conversation_engine.ai_core.models import Observation
from accommodation.service import AccommodationError, AccommodationService


def _failed(name: str, exc: AccommodationError) -> Observation:
    return Observation(
        kind="tool",
        name=name,
        status="failed",
        payload={
            "status": "failed",
            "reason": exc.code,
            "message": str(exc),
            "retryable": exc.retryable,
        },
    )


async def search_accommodations(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    uid = str(runtime.get("user_id") or "")
    if not uid:
        return Observation(
            kind="tool", name="search_accommodations", status="failed",
            payload={"status": "failed", "reason": "NOT_CONFIGURED"},
        )
    service = AccommodationService(runtime.get("db"))
    try:
        result = await service.search(
            destination=str(arguments.get("destination") or ""),
            checkin=str(arguments.get("checkin") or ""),
            checkout=str(arguments.get("checkout") or ""),
            adults=int(arguments.get("adults") or 2),
            rooms=int(arguments.get("rooms") or 1),
            radius_km=float(arguments.get("radius_km") or 15),
            currency=str(arguments.get("currency") or "EUR"),
            rows=int(arguments.get("rows") or 20),
            max_price=(
                float(arguments["max_price"])
                if arguments.get("max_price") is not None else None
            ),
            min_review_score=(
                float(arguments["min_review_score"])
                if arguments.get("min_review_score") is not None else None
            ),
        )
    except AccommodationError as exc:
        return _failed("search_accommodations", exc)

    offers = list(result.get("offers") or [])[:10]
    return Observation(
        kind="tool",
        name="search_accommodations",
        status="ok",
        payload={
            "status": "ok",
            "destination": result.get("destination"),
            "checkin": result.get("checkin"),
            "checkout": result.get("checkout"),
            "offers": offers,
            "providers_checked": result.get("providers_checked") or [],
            "coverage_note": result.get("coverage_note"),
            "how_to_say_it": (
                "Queste sono disponibilità osservate adesso dal provider indicato. "
                "Non dire che rappresentano tutto il web. Prezzi e condizioni "
                "devono essere verificati di nuovo con preview prima di prenotare."
            ),
        },
    )


async def preview_accommodation(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    uid = str(runtime.get("user_id") or "")
    db = runtime.get("db")
    if not uid or db is None:
        return Observation(
            kind="tool", name="preview_accommodation", status="failed",
            payload={"status": "failed", "reason": "NOT_CONFIGURED"},
        )
    products = list(arguments.get("products") or [])
    service = AccommodationService(db)
    try:
        result = await service.preview(
            owner_id=uid,
            accommodation_id=arguments.get("accommodation_id"),
            checkin=str(arguments.get("checkin") or ""),
            checkout=str(arguments.get("checkout") or ""),
            products=products,
            currency=str(arguments.get("currency") or "EUR"),
            country=str(arguments.get("country") or "") or None,
            platform=str(arguments.get("platform") or "") or None,
            travel_purpose=str(arguments.get("travel_purpose") or "") or None,
        )
    except AccommodationError as exc:
        return _failed("preview_accommodation", exc)

    data = result.get("data") or {}
    accommodation = data.get("accommodation") if isinstance(data, dict) else {}
    return Observation(
        kind="tool",
        name="preview_accommodation",
        status="ok",
        payload={
            "status": "ready",
            "preview_id": result.get("preview_id"),
            "expires_at": result.get("expires_at"),
            "request_id": result.get("request_id"),
            "price": data.get("price") if isinstance(data, dict) else None,
            "accommodation": accommodation,
            "payment_options": result.get("payment_options") or [],
            "creates_reservation": False,
            "how_to_say_it": (
                "Questo è il preview corrente del provider: mostra prezzo, "
                "condizioni e modalità di pagamento attuali. Non è una "
                "prenotazione. Prima di creare l'ordine serve il consenso "
                "esplicito sulla spesa e sui termini mostrati."
            ),
        },
    )
