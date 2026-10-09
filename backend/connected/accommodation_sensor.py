"""Booking/accommodation orders as a Connected Life sensor.

Code observes provider state and reports deltas. It never decides whether a
cancellation, date change or reservation update matters to the person's trip;
that judgement belongs to Connected Life reasoning downstream.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from connected.models import ConnectedSignal, now_iso
from connected.seen import SeenState

SOURCE_ID = "accommodation"
ACTIVE_LOCAL_STATES = ("booked", "create_accepted")
_CANCELLED = {"cancelled", "canceled"}
_TERMINAL_FAILURE = {"failed", "rejected"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _accommodation_part(item: Dict[str, Any]) -> Dict[str, Any]:
    raw = item.get("accommodation") or item.get("accommodations") or {}
    if isinstance(raw, list):
        return next((row for row in raw if isinstance(row, dict)), {})
    return raw if isinstance(raw, dict) else {}


def _baseline(row: Dict[str, Any]) -> Dict[str, str]:
    terms = row.get("safe_terms") or {}
    return {
        "status": _text(row.get("provider_status")) or (
            "accepted_not_observed"
            if row.get("status") == "create_accepted"
            else "booked"
        ),
        "reservation_id": _text(row.get("reservation_id")),
        "checkin": _text(terms.get("checkin")),
        "checkout": _text(terms.get("checkout")),
        "accommodation_id": _text(terms.get("accommodation_id")),
    }


def _current(item: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, str]:
    terms = row.get("safe_terms") or {}
    stay = _accommodation_part(item)
    return {
        "status": _text(item.get("status")).lower(),
        "reservation_id": _text(
            stay.get("reservation") or item.get("reservation")
            or row.get("reservation_id")
        ),
        "checkin": _text(
            stay.get("checkin") or item.get("checkin") or terms.get("checkin")
        ),
        "checkout": _text(
            stay.get("checkout") or item.get("checkout") or terms.get("checkout")
        ),
        "accommodation_id": _text(
            stay.get("id") or item.get("accommodation_id")
            or terms.get("accommodation_id")
        ),
    }


def _summary(current: Dict[str, str], changes) -> str:
    status = current.get("status") or "stato non indicato"
    checkin = current.get("checkin") or ""
    checkout = current.get("checkout") or ""
    changed = ", ".join(change.field for change in changes)
    stay = f"; soggiorno {checkin}–{checkout}" if checkin and checkout else ""
    return (
        f"Prenotazione Booking.com: stato {status}{stay}; "
        f"sono cambiati: {changed}."
    )[:300]


def _compact_from_to(changes, current: Dict[str, str]) -> tuple[str, str]:
    """Preserve the material delta when the signal becomes a MeaningfulChange."""
    status = next((change for change in changes if change.field == "status"), None)
    if status is not None:
        return status.before[:160], status.after[:160]

    date_fields = {
        change.field: change
        for change in changes
        if change.field in ("checkin", "checkout")
    }
    if date_fields:
        old_in = date_fields.get("checkin").before if date_fields.get("checkin") else current.get("checkin", "")
        old_out = date_fields.get("checkout").before if date_fields.get("checkout") else current.get("checkout", "")
        new_in = current.get("checkin") or ""
        new_out = current.get("checkout") or ""
        before = f"soggiorno {old_in}–{old_out}".strip()
        after = f"soggiorno {new_in}–{new_out}".strip()
        return before[:160], after[:160]

    fields = ", ".join(change.field for change in changes)
    return "", f"prenotazione aggiornata: {fields}"[:160]


async def read_changes(db, owner_id: str) -> List[ConnectedSignal]:
    """Read every real active order owned by this person and emit only deltas."""
    from accommodation.service import AccommodationService
    from accommodation.booking import BookingProviderError

    rows = await db[AccommodationService.CHECKOUTS].find(
        {
            "owner_id": owner_id,
            "status": {"$in": list(ACTIVE_LOCAL_STATES)},
            "order_id": {"$exists": True, "$nin": ["", None]},
        },
        {
            "_id": 0,
            "id": 1,
            "order_id": 1,
            "reservation_id": 1,
            "provider_status": 1,
            "status": 1,
            "safe_terms": 1,
        },
    ).to_list(50)

    if not rows:
        return []

    service = AccommodationService(db)
    if not service.booking.is_configured:
        raise RuntimeError("booking_provider_not_configured")

    seen = SeenState(db)
    signals: List[ConnectedSignal] = []

    for row in rows:
        order_id = _text(row.get("order_id"))
        currency = _text(((row.get("safe_terms") or {}).get("price") or {}).get("currency")) or "EUR"
        try:
            response = await service.booking.accommodation_order_details(
                order_id=order_id,
                currency=currency,
            )
        except BookingProviderError:
            raise

        raw = response.get("data") or []
        if isinstance(raw, dict):
            candidates = [raw]
        else:
            candidates = [item for item in raw if isinstance(item, dict)]
        item = next(
            (candidate for candidate in candidates
             if _text(candidate.get("id") or candidate.get("order")) == order_id),
            candidates[0] if candidates else None,
        )
        if not item:
            raise RuntimeError("booking_order_readback_empty")

        baseline = _baseline(row)
        current = _current(item, row)

        known, _ = await seen.compare(
            owner_id,
            SOURCE_ID,
            order_id,
            observable=current,
        )
        if not known:
            # The checkout already contains the last state ORA actually
            # observed. Seed from that fact so a first polling pass is silent
            # when the provider merely confirms the same world.
            await seen.remember(
                owner_id,
                SOURCE_ID,
                order_id,
                observable=baseline,
            )

        _known, changes = await seen.compare(
            owner_id,
            SOURCE_ID,
            order_id,
            observable=current,
        )
        await seen.remember(
            owner_id,
            SOURCE_ID,
            order_id,
            observable=current,
        )

        provider_status = current.get("status") or _text(row.get("provider_status"))
        local_status = str(row.get("status") or "")
        if provider_status in _CANCELLED:
            local_status = "cancelled"
        elif provider_status in _TERMINAL_FAILURE:
            local_status = "failed"
        elif provider_status and local_status == "create_accepted":
            local_status = "booked"

        await db[AccommodationService.CHECKOUTS].update_one(
            {"owner_id": owner_id, "id": row.get("id")},
            {"$set": {
                "provider_status": provider_status,
                "reservation_id": current.get("reservation_id") or "",
                "status": local_status,
                "last_provider_observed_at": datetime.now(timezone.utc),
            }},
        )

        if not changes:
            continue

        cancelled = provider_status in _CANCELLED
        signal_type = (
            "travel.booking.cancelled"
            if cancelled
            else "travel.booking.changed"
        )
        before_text, after_text = _compact_from_to(changes, current)
        signals.append(ConnectedSignal(
            owner_id=owner_id,
            source_id=SOURCE_ID,
            source_type="travel",
            signal_type=signal_type,
            observed_at=now_iso(),
            effective_at=None,
            source_object_ref=order_id,
            payload_summary=_summary(current, changes),
            before=before_text,
            after=after_text,
            changed_fields=changes,
            origin="external",
            relationship="own",
            provenance={
                "provider": "booking.com",
                "checkout_id": _text(row.get("id"))[:80],
                "checkin": current.get("checkin") or "",
                "checkout": current.get("checkout") or "",
            },
            confidence="certain",
            raw_ref=order_id[:120],
        ))

    return signals
