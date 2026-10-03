"""Provider-agnostic accommodation search for ORA."""
from __future__ import annotations

import math
import os
import unicodedata
from datetime import date
from typing import Any, Dict, Optional

import httpx

from accommodation.booking import BookingDemandClient, BookingProviderError


class AccommodationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _normal(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _validate_dates(checkin: str, checkout: str) -> None:
    try:
        start, end = date.fromisoformat(checkin), date.fromisoformat(checkout)
    except ValueError as exc:
        raise AccommodationError("invalid_dates", "Le date non sono valide.") from exc
    if end <= start:
        raise AccommodationError(
            "invalid_dates", "Il check-out deve essere successivo al check-in."
        )
    if (end - start).days > 90:
        raise AccommodationError(
            "stay_too_long", "La ricerca alloggi può coprire al massimo 90 notti."
        )


async def _resolve_destination(name: str) -> Optional[Dict[str, Any]]:
    """Resolve a public destination without persisting it as a Life Place."""
    key = (os.environ.get("ROUTING_API_KEY") or "").strip()
    if (os.environ.get("ROUTING_PROVIDER") or "").strip().lower() != "mapbox" or not key:
        return None
    try:
        params = {
            "q": name.strip(), "access_token": key, "language": "it",
            "limit": 5, "auto_complete": "false",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.mapbox.com/search/searchbox/v1/forward", params=params
            )
        if response.status_code != 200:
            return None
        features = (response.json() or {}).get("features") or []
    except Exception:
        return None

    query = _normal(name)
    exact = []
    for feature in features:
        props = feature.get("properties") or {}
        labels = (props.get("name"), props.get("name_preferred"), props.get("full_address"))
        if not any(_normal(str(value or "")) == query for value in labels):
            continue
        point = props.get("coordinates") or {}
        coords = feature.get("geometry", {}).get("coordinates") or []
        try:
            lat = float(point.get("latitude") if point else coords[1])
            lon = float(point.get("longitude") if point else coords[0])
        except (TypeError, ValueError, IndexError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            exact.append((feature, lat, lon))

    if not exact:
        return None
    first, lat, lon = exact[0]
    if any(
        math.hypot(
            (other_lat - lat) * 111_000,
            (other_lon - lon) * 111_000 * math.cos(math.radians(lat)),
        ) > 5_000
        for _, other_lat, other_lon in exact[1:]
    ):
        return None

    props = first.get("properties") or {}
    return {
        "latitude": lat,
        "longitude": lon,
        "label": str(props.get("name") or name)[:120],
        "context": str(props.get("place_formatted") or "")[:180],
    }


class AccommodationService:
    def __init__(self) -> None:
        self.booking = BookingDemandClient()

    def readiness(self) -> Dict[str, Any]:
        return {
            "providers": {
                "booking.com": {
                    "search": self.booking.is_configured,
                    "book_provider_ready": self.booking.is_configured,
                    "book_exposed": False,
                    "mode": "sandbox" if "sandbox" in self.booking.base_url.lower() else "production",
                }
            },
            "destination_resolution": bool(
                (os.environ.get("ROUTING_PROVIDER") or "").strip().lower() == "mapbox"
                and (os.environ.get("ROUTING_API_KEY") or "").strip()
            ),
        }

    async def search(
        self, *, destination: str, checkin: str, checkout: str, adults: int = 2,
        rooms: int = 1, latitude: Optional[float] = None,
        longitude: Optional[float] = None, radius_km: float = 15.0,
        currency: str = "EUR", rows: int = 20,
        max_price: Optional[float] = None,
        min_review_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        _validate_dates(checkin, checkout)
        if not self.booking.is_configured:
            raise AccommodationError(
                "provider_not_configured",
                "La ricerca Booking.com è pronta nel codice ma mancano le credenziali partner.",
            )
        if (latitude is None) != (longitude is None):
            raise AccommodationError(
                "incomplete_coordinates", "Servono sia latitudine sia longitudine."
            )

        if latitude is not None and longitude is not None:
            lat, lon = float(latitude), float(longitude)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise AccommodationError("invalid_coordinates", "Coordinate non valide.")
            resolved: Optional[Dict[str, Any]] = {
                "latitude": lat, "longitude": lon,
                "label": destination.strip()[:120], "context": "",
            }
        else:
            resolved = await _resolve_destination(destination)

        if not resolved:
            raise AccommodationError(
                "destination_unresolved",
                "Non riesco a risolvere la destinazione in modo univoco.",
            )

        try:
            result = await self.booking.search(
                latitude=resolved["latitude"], longitude=resolved["longitude"],
                checkin=checkin, checkout=checkout, adults=adults, rooms=rooms,
                radius_km=radius_km, currency=currency, rows=rows,
                max_price=max_price, min_review_score=min_review_score,
            )
        except BookingProviderError as exc:
            raise AccommodationError(exc.code, str(exc), retryable=exc.retryable) from exc

        offers = list(result.get("offers") or [])
        offers.sort(key=lambda item: (
            item.get("total_price") is None,
            float(item.get("total_price") or 0),
            item.get("name") or "",
        ))
        return {
            "status": "ok",
            "destination": resolved,
            "checkin": checkin,
            "checkout": checkout,
            "adults": max(1, int(adults)),
            "rooms": max(1, int(rooms)),
            "providers_checked": ["booking.com"],
            "offers": offers,
            "provider_requests": {"booking.com": result.get("request_id") or ""},
            "coverage_note": (
                "Risultati reali del provider configurato; non viene dichiarata "
                "copertura dell'intero web."
            ),
        }
