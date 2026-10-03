"""Booking.com Demand API v3.2 adapter.

Provider plumbing only: search is read-only and booking is deliberately kept
behind the Personal Agent's authority boundary.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

import httpx

DEFAULT_BASE_URL = "https://demandapi.booking.com/3.2"


class BookingProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def configured() -> bool:
    return bool(
        (os.environ.get("BOOKING_DEMAND_TOKEN") or "").strip()
        and (os.environ.get("BOOKING_AFFILIATE_ID") or "").strip()
    )


def _first_text(value: Any, languages: Iterable[str] = ("it", "en-gb", "en")) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    for lang in languages:
        text = value.get(lang)
        if isinstance(text, str) and text.strip():
            return text.strip()
    for text in value.values():
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _amount(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict):
        return None
    for key in (
        "booker_currency", "display", "total", "book", "chargeable_online",
        "accommodation_currency", "base", "value", "amount",
    ):
        if key in value:
            found = _amount(value.get(key))
            if found is not None:
                return found
    for child in value.values():
        found = _amount(child)
        if found is not None:
            return found
    return None


def _currency(item: Dict[str, Any]) -> str:
    currency = item.get("currency")
    if isinstance(currency, str):
        return currency
    if isinstance(currency, dict):
        return str(currency.get("booker") or currency.get("accommodation") or "")
    return ""


class BookingDemandClient:
    provider = "booking.com"

    def __init__(self) -> None:
        self.base_url = (
            (os.environ.get("BOOKING_DEMAND_BASE_URL") or DEFAULT_BASE_URL)
            .strip().rstrip("/")
        )
        self.token = (os.environ.get("BOOKING_DEMAND_TOKEN") or "").strip()
        self.affiliate_id = (os.environ.get("BOOKING_AFFILIATE_ID") or "").strip()
        self.booker_country = (
            (os.environ.get("BOOKING_BOOKER_COUNTRY") or "it").strip().lower()
        )
        self.platform = (
            (os.environ.get("BOOKING_DEMAND_PLATFORM") or "mobile").strip().lower()
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.affiliate_id)

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_configured:
            raise BookingProviderError(
                "provider_not_configured",
                "Booking.com Demand API non è configurata.",
                retryable=False,
            )
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-Affiliate-Id": self.affiliate_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self.base_url}/{path.lstrip('/')}",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise BookingProviderError(
                "provider_timeout",
                "Booking.com non ha risposto in tempo.",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise BookingProviderError(
                "provider_unavailable",
                "Booking.com non è raggiungibile.",
                retryable=True,
            ) from exc

        if response.status_code in (401, 403):
            raise BookingProviderError(
                "provider_auth_failed",
                "Le credenziali Booking.com non sono accettate.",
                retryable=False,
            )
        if response.status_code == 429:
            raise BookingProviderError(
                "provider_rate_limited",
                "Booking.com ha temporaneamente limitato le richieste.",
                retryable=True,
            )
        if response.status_code >= 500:
            raise BookingProviderError(
                "provider_unavailable",
                "Booking.com ha restituito un errore temporaneo.",
                retryable=True,
            )
        if response.status_code >= 400:
            raise BookingProviderError(
                "provider_rejected_request",
                f"Booking.com ha rifiutato la richiesta ({response.status_code}).",
                retryable=False,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise BookingProviderError(
                "provider_invalid_response",
                "Booking.com ha restituito una risposta non valida.",
                retryable=True,
            ) from exc
        return body if isinstance(body, dict) else {}

    async def search(
        self,
        *,
        latitude: float,
        longitude: float,
        checkin: str,
        checkout: str,
        adults: int,
        rooms: int,
        radius_km: float = 15.0,
        currency: str = "EUR",
        rows: int = 20,
        max_price: Optional[float] = None,
        min_review_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        rows = max(10, min(100, int(rows)))
        rows = max(10, (rows // 10) * 10)
        payload: Dict[str, Any] = {
            "booker": {
                "country": self.booker_country,
                "platform": self.platform,
            },
            "checkin": checkin,
            "checkout": checkout,
            "coordinates": {
                "latitude": float(latitude),
                "longitude": float(longitude),
                "radius": max(0.5, min(100.0, float(radius_km))),
            },
            "currency": currency.upper(),
            "guests": {
                "number_of_adults": max(1, int(adults)),
                "number_of_rooms": max(1, int(rooms)),
            },
            "extras": ["products"],
            "rows": rows,
            "sort": {"by": "price", "direction": "ascending"},
        }
        filters: Dict[str, Any] = {}
        if max_price is not None:
            filters["price"] = {"maximum": max(0.0, float(max_price))}
        if min_review_score is not None:
            filters["rating"] = {
                "minimum_review_score": max(1.0, min(10.0, float(min_review_score)))
            }
        if filters:
            payload["filters"] = filters

        search = await self._post("accommodations/search", payload)
        data = search.get("data") or []
        ids = [
            row.get("id")
            for row in data
            if isinstance(row, dict) and row.get("id") is not None
        ]
        details_by_id: Dict[str, Dict[str, Any]] = {}
        if ids:
            try:
                details = await self._post(
                    "accommodations/details",
                    {"accommodations": ids[:100], "languages": ["it", "en-gb"]},
                )
                details_by_id = {
                    str(row.get("id")): row
                    for row in (details.get("data") or [])
                    if isinstance(row, dict) and row.get("id") is not None
                }
            except BookingProviderError:
                details_by_id = {}

        offers: List[Dict[str, Any]] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            property_id = str(row.get("id") or "")
            detail = details_by_id.get(property_id) or {}
            name = _first_text(detail.get("name")) or f"Alloggio {property_id}"
            address = detail.get("address") or {}
            if isinstance(address, dict):
                address_text = ", ".join(
                    str(address.get(key) or "").strip()
                    for key in ("address_line", "city_name", "post_code", "country_code")
                    if str(address.get(key) or "").strip()
                )
            else:
                address_text = str(address or "").strip()

            url = row.get("url")
            web_url = (
                str(url.get("web") or "") if isinstance(url, dict) else str(url or "")
            )
            detail_url = detail.get("url") or {}
            if not web_url and isinstance(detail_url, dict):
                web_url = str(detail_url.get("web") or "")

            products = row.get("products") or []
            product_ids = [
                str(product.get("id"))
                for product in products
                if isinstance(product, dict) and product.get("id") is not None
            ]
            offers.append({
                "provider": self.provider,
                "property_id": property_id,
                "name": name[:180],
                "address": address_text[:300],
                "total_price": _amount(row.get("price")),
                "currency": _currency(row) or currency.upper(),
                "product_ids": product_ids[:12],
                "web_url": web_url[:1000],
                "request_id": str(search.get("request_id") or "")[:120],
                "bookable_in_app": bool(product_ids),
            })

        return {
            "provider": self.provider,
            "request_id": str(search.get("request_id") or "")[:120],
            "offers": offers,
            "next_page": str(
                ((search.get("metadata") or {}).get("next_page")
                 or (search.get("metadata") or {}).get("next_page_token")
                 or "")
            )[:500],
        }

    async def preview(
        self,
        *,
        accommodation_id: int | str,
        checkin: str,
        checkout: str,
        products: List[Dict[str, Any]],
        currency: str = "EUR",
        country: Optional[str] = None,
        platform: Optional[str] = None,
        travel_purpose: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate the selected rooms and get current order terms.

        Preview does not book anything. The returned order token is short-lived
        and is handed to the secure server-side booking layer, never logged.
        """
        booker: Dict[str, Any] = {
            "country": (country or self.booker_country).strip().lower(),
            "platform": (platform or self.platform).strip().lower(),
            "user_groups": ["authenticated"],
        }
        if travel_purpose in ("business", "leisure"):
            booker["travel_purpose"] = travel_purpose

        selected = []
        for product in products:
            product_id = str(product.get("id") or "").strip()
            adults = int(product.get("number_of_adults") or 0)
            children = [int(age) for age in (product.get("children") or [])]
            if not product_id or adults < 1 or any(age < 0 or age > 17 for age in children):
                raise BookingProviderError(
                    "invalid_product_allocation",
                    "La composizione degli ospiti non è valida.",
                    retryable=False,
                )
            selected.append({
                "id": product_id,
                "allocation": {
                    "number_of_adults": adults,
                    "children": children,
                },
            })

        if not selected:
            raise BookingProviderError(
                "products_required",
                "Serve almeno una camera/prodotto da verificare.",
                retryable=False,
            )

        try:
            accommodation_number = int(accommodation_id)
        except (TypeError, ValueError) as exc:
            raise BookingProviderError(
                "invalid_accommodation_id",
                "L'identificativo dell'alloggio non è valido.",
                retryable=False,
            ) from exc

        payload = {
            "currency": currency.upper(),
            "accommodation": {
                "id": accommodation_number,
                "booker": booker,
                "checkin": checkin,
                "checkout": checkout,
                "products": selected,
            },
        }
        return await self._post("orders/preview", payload)
