"""Provider-agnostic accommodation search for ORA."""
from __future__ import annotations

import hashlib
import json
import math
import os
import unicodedata
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from accommodation.booking import BookingDemandClient, BookingProviderError


class AccommodationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _normal(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _strip_secret(value: Any, secret_key: str) -> Any:
    """Deep-copy provider data while removing a named secret field."""
    if isinstance(value, dict):
        return {
            key: _strip_secret(child, secret_key)
            for key, child in value.items()
            if key != secret_key
        }
    if isinstance(value, list):
        return [_strip_secret(child, secret_key) for child in value]
    return value


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
    PREVIEWS = "accommodation_order_previews"
    CHECKOUTS = "accommodation_checkouts"

    def __init__(self, db=None) -> None:
        self.db = db
        self.booking = BookingDemandClient()

    async def ensure_indexes(self) -> None:
        if self.db is None:
            return
        await self.db[self.PREVIEWS].create_index(
            [("owner_id", 1), ("id", 1)], unique=True, name="owner_preview_id"
        )
        await self.db[self.PREVIEWS].create_index(
            [("status", 1), ("expires_at", 1)], name="preview_expiry"
        )
        await self.db[self.CHECKOUTS].create_index(
            [("owner_id", 1), ("id", 1)], unique=True, name="owner_checkout_id"
        )
        await self.db[self.CHECKOUTS].create_index(
            [("status", 1), ("expires_at", 1)], name="checkout_expiry"
        )

    async def cleanup_expired(self) -> int:
        """Revoke expired secrets before deleting checkout/preview metadata."""
        if self.db is None:
            return 0
        now = datetime.now(timezone.utc)
        from deps import get_token_vault
        vault = get_token_vault()
        removed = 0

        # Checkout payload may contain traveller PII. Revoke it first.
        checkouts = await self.db[self.CHECKOUTS].find(
            {"status": "ready", "expires_at": {"$lte": now}},
            {"_id": 0, "id": 1, "owner_id": 1, "payload_ref": 1},
        ).to_list(100)
        for row in checkouts:
            ref = str(row.get("payload_ref") or "")
            if ref:
                try:
                    await vault.revoke(ref)
                except Exception:
                    continue
            await self.db[self.CHECKOUTS].delete_one({
                "id": row.get("id"), "owner_id": row.get("owner_id")
            })
            removed += 1

        previews = await self.db[self.PREVIEWS].find(
            {"status": "ready", "expires_at": {"$lte": now}},
            {"_id": 0, "id": 1, "owner_id": 1, "token_ref": 1},
        ).to_list(100)
        for row in previews:
            ref = str(row.get("token_ref") or "")
            if ref:
                try:
                    await vault.revoke(ref)
                except Exception:
                    continue
            await self.db[self.PREVIEWS].delete_one({
                "id": row.get("id"), "owner_id": row.get("owner_id")
            })
            removed += 1
        return removed

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


    async def preview(
        self,
        *,
        owner_id: str,
        accommodation_id: int | str,
        checkin: str,
        checkout: str,
        products: List[Dict[str, Any]],
        currency: str = "EUR",
        country: Optional[str] = None,
        platform: Optional[str] = None,
        travel_purpose: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get current price/policies and keep the short-lived token encrypted."""
        _validate_dates(checkin, checkout)
        if self.db is None:
            raise AccommodationError(
                "storage_not_configured",
                "Il preview di prenotazione richiede lo storage server.",
            )
        if not self.booking.is_configured:
            raise AccommodationError(
                "provider_not_configured",
                "Booking.com Demand API non è configurata.",
            )

        await self.ensure_indexes()
        await self.cleanup_expired()

        try:
            result = await self.booking.preview(
                accommodation_id=accommodation_id,
                checkin=checkin,
                checkout=checkout,
                products=products,
                currency=currency,
                country=country,
                platform=platform,
                travel_purpose=travel_purpose,
            )
        except BookingProviderError as exc:
            raise AccommodationError(
                exc.code, str(exc), retryable=exc.retryable
            ) from exc

        data = result.get("data") or {}
        if not isinstance(data, dict):
            raise AccommodationError(
                "provider_invalid_response",
                "Booking.com non ha restituito un preview valido.",
                retryable=True,
            )
        order_token = str(data.get("order_token") or "").strip()
        if not order_token:
            raise AccommodationError(
                "order_token_missing",
                "Il provider non ha restituito il token necessario alla prenotazione.",
                retryable=True,
            )

        from deps import get_token_vault
        from security.token_vault import VaultError, is_configured

        vault = get_token_vault()
        if not is_configured(vault):
            raise AccommodationError(
                "secure_vault_unavailable",
                "Il vault sicuro non è disponibile: non conservo il token di prenotazione.",
            )

        preview_id = f"apv_{secrets.token_hex(8)}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        try:
            token_ref = await vault.put(
                user_id=owner_id,
                purpose="booking_order_preview",
                payload={"order_token": order_token},
                metadata={"preview_id": preview_id, "provider": "booking.com"},
            )
        except VaultError as exc:
            raise AccommodationError(
                "secure_vault_unavailable",
                "Non riesco a proteggere il token di prenotazione.",
                retryable=False,
            ) from exc

        public_data = _strip_secret(data, "order_token")
        await self.db[self.PREVIEWS].insert_one({
            "id": preview_id,
            "owner_id": owner_id,
            "provider": "booking.com",
            "request_id": str(result.get("request_id") or "")[:120],
            "token_ref": token_ref,
            "accommodation_id": str(accommodation_id)[:80],
            "checkin": checkin,
            "checkout": checkout,
            "product_ids": [str(p.get("id") or "")[:160] for p in products][:12],
            "preview": public_data,
            "created_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
            "status": "ready",
        })
        return {
            "status": "ready",
            "preview_id": preview_id,
            "expires_at": expires_at.isoformat(),
            "request_id": str(result.get("request_id") or "")[:120],
            "data": public_data,
            "payment_options": _preview_payment_options(public_data),
            "creates_reservation": False,
        }


    async def prepare_checkout(
        self,
        *,
        owner_id: str,
        preview_id: str,
        booker: Dict[str, Any],
        products: List[Dict[str, Any]],
        payment: Dict[str, Any],
        remarks: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Freeze a provider-validated, cardless checkout behind an opaque id.

        Sensitive traveller data is encrypted in the vault. The model and
        agent receive only checkout_id, terms_hash and a safe authority summary.
        Raw card data is intentionally rejected until a compliant tokenised
        payment path is configured.
        """
        if self.db is None:
            raise AccommodationError("storage_not_configured", "Checkout storage unavailable.")
        await self.ensure_indexes()
        await self.cleanup_expired()
        now = datetime.now(timezone.utc)
        preview = await self.db[self.PREVIEWS].find_one(
            {
                "id": str(preview_id),
                "owner_id": owner_id,
                "status": "ready",
                "expires_at": {"$gt": now},
            },
            {"_id": 0},
        )
        if not preview:
            raise AccommodationError(
                "preview_expired_or_missing",
                "Il preventivo non è più valido: serve un nuovo preview.",
            )

        selected_ids = [str(p.get("id") or "").strip() for p in products]
        preview_ids = [str(x or "").strip() for x in (preview.get("product_ids") or [])]
        if not selected_ids or sorted(selected_ids) != sorted(preview_ids):
            raise AccommodationError(
                "selection_changed",
                "Le camere selezionate non coincidono più con il preview.",
            )

        _validate_booker(booker)
        _validate_guests(products)

        method = str(payment.get("method") or "").strip()
        timing = str(payment.get("timing") or "").strip()
        if not timing:
            raise AccommodationError(
                "payment_choice_required",
                "Il momento del pagamento deve provenire dal preview.",
            )
        policy = _preview_payment_policy(preview.get("preview") or {}, timing)
        if policy is None:
            raise AccommodationError(
                "payment_not_in_preview",
                "Il momento del pagamento scelto non è tra quelli del preview corrente.",
            )
        if bool(policy.get("method_required")):
            # Booking.com requires a real method for this timing. ORA does not
            # accept PAN/CVC through the model or persistent JSON. Until a
            # compliant direct payment component is connected, fail closed.
            raise AccommodationError(
                "secure_payment_method_required",
                "Questo alloggio richiede un metodo di pagamento/garanzia sicuro prima della prenotazione.",
            )
        # method_required=false means no payment method is required up front.
        # Keep the timing (the provider still needs the selected schedule) and
        # omit a method rather than inventing one.
        if method:
            raise AccommodationError(
                "payment_method_not_required",
                "Il preview non richiede un metodo di pagamento anticipato: non ne invio uno arbitrario.",
            )
        payment = {
            "timing": timing,
            "include_receipt": bool(payment.get("include_receipt", True)),
        }

        from deps import get_token_vault
        from security.token_vault import VaultError, is_configured
        vault = get_token_vault()
        if not is_configured(vault):
            raise AccommodationError(
                "secure_vault_unavailable",
                "Il vault sicuro non è disponibile.",
            )

        secure_payload = {
            "booker": booker,
            "accommodation": {
                "products": products,
                **({"remarks": remarks} if remarks else {}),
            },
            "payment": payment,
        }
        checkout_id = f"aco_{secrets.token_hex(8)}"
        safe_terms = {
            "preview_id": str(preview_id),
            "request_id": str(preview.get("request_id") or ""),
            "accommodation_id": str(preview.get("accommodation_id") or ""),
            "checkin": str(preview.get("checkin") or ""),
            "checkout": str(preview.get("checkout") or ""),
            "product_ids": preview_ids,
            "payment_method": str(payment.get("method") or ""),
            "payment_timing": timing,
            "price": _preview_price(preview.get("preview") or {}),
        }
        terms_hash = hashlib.sha256(
            json.dumps(safe_terms, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        authority_summary = _authority_summary(safe_terms)

        try:
            payload_ref = await vault.put(
                user_id=owner_id,
                purpose="booking_checkout_payload",
                payload=secure_payload,
                metadata={"checkout_id": checkout_id, "terms_hash": terms_hash},
            )
        except VaultError as exc:
            raise AccommodationError(
                "secure_vault_unavailable",
                "Non riesco a proteggere i dati del checkout.",
            ) from exc

        await self.db[self.CHECKOUTS].insert_one({
            "id": checkout_id,
            "owner_id": owner_id,
            "preview_id": str(preview_id),
            "payload_ref": payload_ref,
            "terms_hash": terms_hash,
            "authority_summary": authority_summary,
            "safe_terms": safe_terms,
            "expires_at": preview.get("expires_at"),
            "created_at": now,
            "status": "ready",
        })
        return {
            "status": "ready",
            "checkout_id": checkout_id,
            "terms_hash": terms_hash,
            "authority_summary": authority_summary,
            "expires_at": _iso(preview.get("expires_at")),
            "creates_reservation": False,
        }

    async def checkout_for_authority(
        self, *, owner_id: str, checkout_id: str, terms_hash: str = ""
    ) -> Dict[str, Any]:
        if self.db is None:
            raise AccommodationError("storage_not_configured", "Checkout storage unavailable.")
        now = datetime.now(timezone.utc)
        row = await self.db[self.CHECKOUTS].find_one(
            {
                "id": checkout_id,
                "owner_id": owner_id,
                "status": "ready",
                "expires_at": {"$gt": now},
            },
            {"_id": 0, "payload_ref": 0},
        )
        if not row:
            raise AccommodationError(
                "checkout_expired_or_missing",
                "Il checkout non è più valido: serve un nuovo preview.",
            )
        if terms_hash and terms_hash != str(row.get("terms_hash") or ""):
            raise AccommodationError(
                "checkout_terms_changed",
                "I termini del checkout non corrispondono a quelli autorizzati.",
            )
        return row

    async def create_order_from_checkout(
        self, *, owner_id: str, checkout_id: str, terms_hash: str
    ) -> Dict[str, Any]:
        """Execute one frozen checkout and verify the resulting order."""
        row = await self.checkout_for_authority(
            owner_id=owner_id, checkout_id=checkout_id, terms_hash=terms_hash
        )
        preview = await self.db[self.PREVIEWS].find_one(
            {
                "id": row["preview_id"],
                "owner_id": owner_id,
                "status": "ready",
                "expires_at": {"$gt": datetime.now(timezone.utc)},
            },
            {"_id": 0},
        )
        if not preview:
            raise AccommodationError(
                "preview_expired_or_missing",
                "Il preview è scaduto prima della prenotazione.",
            )

        from deps import get_token_vault
        from security.token_vault import VaultError
        vault = get_token_vault()
        try:
            token_payload = await vault.get(str(preview["token_ref"]), user_id=owner_id)
            checkout_payload = await vault.get(str(row["payload_ref"]), user_id=owner_id)
        except VaultError as exc:
            raise AccommodationError(
                "secure_payload_missing",
                "I dati protetti del checkout non sono più disponibili.",
            ) from exc

        order_token = str(token_payload.get("order_token") or "").strip()
        if not order_token:
            raise AccommodationError("order_token_missing", "Il token ordine non è disponibile.")

        create_payload = {
            **checkout_payload,
            "order_token": order_token,
        }
        try:
            created = await self.booking.create_order(create_payload)
        except BookingProviderError as exc:
            raise AccommodationError(exc.code, str(exc), retryable=exc.retryable) from exc

        data = created.get("data") or {}
        order_id = str(data.get("order") or "").strip()
        if not order_id:
            raise AccommodationError(
                "provider_create_unconfirmed",
                "Il provider non ha restituito un ordine confermabile.",
                retryable=True,
            )

        details_data: Dict[str, Any] = {}
        try:
            details = await self.booking.accommodation_order_details(
                order_id=order_id,
                currency=str((row.get("safe_terms") or {}).get("price", {}).get("currency") or "EUR"),
            )
            candidates = details.get("data") or []
            details_data = next(
                (item for item in candidates if str(item.get("id") or "") == order_id),
                candidates[0] if candidates else {},
            )
        except BookingProviderError:
            details_data = {}

        status = str(details_data.get("status") or data.get("status") or "").strip().lower()
        observed = bool(details_data) and status not in ("", "cancelled", "failed")
        reservation = str(
            ((details_data.get("accommodation") or details_data.get("accommodations") or {})
             .get("reservation") or data.get("reservation") or "")
        )

        # Once /orders/create returned an order id, the effect may already
        # exist in the real world. Never leave this checkout retryable: a
        # read-back outage must become reconciliation work, not a duplicate
        # reservation.
        final_state = "booked" if observed else "create_accepted"
        now = datetime.now(timezone.utc)
        await self.db[self.CHECKOUTS].update_one(
            {"id": checkout_id, "owner_id": owner_id},
            {"$set": {
                "status": final_state,
                "order_id": order_id,
                "reservation_id": reservation,
                "provider_status": status,
                "create_accepted_at": now,
                **({"booked_at": now} if observed else {}),
            }},
        )
        await self.db[self.PREVIEWS].update_one(
            {"id": row["preview_id"], "owner_id": owner_id},
            {"$set": {"status": "consumed", "consumed_at": now}},
        )
        for ref in (str(row.get("payload_ref") or ""), str(preview.get("token_ref") or "")):
            if ref:
                try:
                    await vault.revoke(ref)
                except Exception:
                    pass

        return {
            "status": "booked" if observed else "accepted_not_observed",
            "provider": "booking.com",
            "order_id": order_id,
            "reservation_id": reservation,
            "provider_status": status,
            "observed": observed,
            "request_id": str(created.get("request_id") or "")[:120],
        }



def _validate_booker(booker: Dict[str, Any]) -> None:
    required = ("email", "telephone", "name", "address")
    if not isinstance(booker, dict) or any(not booker.get(key) for key in required):
        raise AccommodationError(
            "booker_incomplete",
            "Mancano dati obbligatori del titolare della prenotazione.",
        )
    name = booker.get("name") or {}
    address = booker.get("address") or {}
    if not name.get("first_name") or not name.get("last_name"):
        raise AccommodationError("booker_incomplete", "Nome e cognome del titolare sono obbligatori.")
    for key in ("address_line", "city", "country", "post_code"):
        if not address.get(key):
            raise AccommodationError("booker_incomplete", "L'indirizzo del titolare è incompleto.")


def _validate_guests(products: List[Dict[str, Any]]) -> None:
    for product in products:
        if not str(product.get("id") or "").strip():
            raise AccommodationError("guests_incomplete", "Manca l'identificativo della camera.")
        guests = product.get("guests") or []
        if not guests:
            raise AccommodationError("guests_incomplete", "Serve almeno un ospite per ogni camera.")
        for guest in guests:
            if not str(guest.get("name") or "").strip() or not str(guest.get("email") or "").strip():
                raise AccommodationError("guests_incomplete", "Nome ed email sono obbligatori per ogni ospite.")


def _preview_payment_policy(preview: Dict[str, Any], timing: str) -> Optional[Dict[str, Any]]:
    """Return exactly one payment timing from Booking's authoritative preview."""
    accommodation = preview.get("accommodation") or {}
    general = accommodation.get("general_policies") or {}
    payment = general.get("payment") or {}
    # Compatibility with early v3.2 responses documented during migration.
    if not payment and isinstance(accommodation.get("payment"), dict):
        payment = accommodation.get("payment") or {}
    option = payment.get(timing) if isinstance(payment, dict) else None
    return option if isinstance(option, dict) else None


def _preview_payment_options(preview: Dict[str, Any]) -> List[Dict[str, Any]]:
    accommodation = preview.get("accommodation") or {}
    payment = ((accommodation.get("general_policies") or {}).get("payment") or {})
    if not payment and isinstance(accommodation.get("payment"), dict):
        payment = accommodation.get("payment") or {}
    out: List[Dict[str, Any]] = []
    for timing in ("pay_online_now", "pay_online_later", "pay_at_the_property"):
        option = payment.get(timing) if isinstance(payment, dict) else None
        if not isinstance(option, dict):
            continue
        methods = option.get("methods") or {}
        out.append({
            "timing": timing,
            "method_required": bool(option.get("method_required")),
            "methods": methods if isinstance(methods, dict) else {},
            "dates": list(option.get("dates") or [])[:8],
            "can_prepare_without_payment_method": not bool(option.get("method_required")),
        })
    return out


def _preview_price(preview: Dict[str, Any]) -> Dict[str, Any]:
    accommodation = preview.get("accommodation") or {}
    price = accommodation.get("price") or {}
    currency = ""
    currencies = preview.get("currency") or preview.get("currencies") or {}
    if isinstance(currencies, str):
        currency = currencies
    elif isinstance(currencies, dict):
        currency = str(currencies.get("booker") or currencies.get("product") or "")
    return {
        "total": price.get("total"),
        "display": price.get("display"),
        "chargeable_online": price.get("chargeable_online"),
        "currency": currency,
    }


def _authority_summary(terms: Dict[str, Any]) -> str:
    price = terms.get("price") or {}
    total = price.get("display") or price.get("total")
    amount = json.dumps(total, ensure_ascii=False)[:120] if total is not None else "prezzo del preview"
    return (
        f"Prenotare l'alloggio {terms.get('accommodation_id')} dal "
        f"{terms.get('checkin')} al {terms.get('checkout')}; "
        f"pagamento {terms.get('payment_timing')}/{terms.get('payment_method')}; "
        f"totale mostrato: {amount}"
    )[:300]


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "")
