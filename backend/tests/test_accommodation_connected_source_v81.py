from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from connected.accommodation_sensor import read_changes
from connected.service import ConnectedLifeService
from connected.sources import SourceRegistry
from opportunities.changes import ChangeLog


OWNER = "alice"


def _checkout(**overrides):
    row = {
        "id": "aco_v81",
        "owner_id": OWNER,
        "status": "booked",
        "order_id": "ord_v81",
        "reservation_id": "res_v81",
        "provider_status": "confirmed",
        "safe_terms": {
            "accommodation_id": "hotel_42",
            "checkin": "2026-10-23",
            "checkout": "2026-10-25",
            "price": {"currency": "EUR", "amount": 280.0},
        },
        "created_at": datetime.now(timezone.utc),
        "create_accepted_at": datetime.now(timezone.utc),
        "booked_at": datetime.now(timezone.utc),
    }
    row.update(overrides)
    return row


def _provider_item(*, status="confirmed", checkin="2026-10-23", checkout="2026-10-25"):
    return {
        "id": "ord_v81",
        "status": status,
        "accommodation": {
            "id": "hotel_42",
            "reservation": "res_v81",
            "checkin": checkin,
            "checkout": checkout,
        },
    }


def _configure_booking(monkeypatch):
    monkeypatch.setenv("BOOKING_DEMAND_TOKEN", "test-token")
    monkeypatch.setenv("BOOKING_AFFILIATE_ID", "test-affiliate")


@pytest.mark.asyncio
async def test_booking_source_exists_only_for_real_active_order(monkeypatch):
    db = AsyncMongoMockClient().test
    _configure_booking(monkeypatch)

    sources = await SourceRegistry(db).list(OWNER)
    assert not any(source.source_type == "travel" for source in sources)

    await db.accommodation_checkouts.insert_one(_checkout())
    sources = await SourceRegistry(db).list(OWNER)

    travel = [source for source in sources if source.source_type == "travel"]
    assert len(travel) == 1
    assert travel[0].id == "accommodation"
    assert travel[0].provider == "Booking.com"
    assert travel[0].is_readable is True
    assert travel[0].read_capabilities == ["travel.booking.read"]


@pytest.mark.asyncio
async def test_first_unchanged_booking_read_is_silent(monkeypatch):
    from accommodation.booking import BookingDemandClient

    db = AsyncMongoMockClient().test
    _configure_booking(monkeypatch)
    await db.accommodation_checkouts.insert_one(_checkout())

    async def details(self, *, order_id, currency="EUR"):
        assert order_id == "ord_v81"
        return {"data": [_provider_item()]}

    monkeypatch.setattr(BookingDemandClient, "accommodation_order_details", details)

    signals = await read_changes(db, OWNER)

    assert signals == []
    seen = await db.connected_object_state.find_one(
        {"owner_id": OWNER, "source_id": "accommodation", "object_ref": "ord_v81"},
        {"_id": 0},
    )
    assert seen is not None
    assert seen["observed"]["status"] == "confirmed"


@pytest.mark.asyncio
async def test_provider_cancellation_becomes_real_travel_signal(monkeypatch):
    from accommodation.booking import BookingDemandClient

    db = AsyncMongoMockClient().test
    _configure_booking(monkeypatch)
    await db.accommodation_checkouts.insert_one(_checkout())

    current = {"status": "confirmed"}

    async def details(self, *, order_id, currency="EUR"):
        return {"data": [_provider_item(status=current["status"])]}

    monkeypatch.setattr(BookingDemandClient, "accommodation_order_details", details)

    assert await read_changes(db, OWNER) == []

    current["status"] = "cancelled"
    signals = await read_changes(db, OWNER)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.signal_type == "travel.booking.cancelled"
    assert signal.source_type == "travel"
    assert signal.source_object_ref == "ord_v81"
    assert any(change.field == "status" for change in signal.changed_fields)
    assert "cancelled" in signal.payload_summary.lower()
    assert "test-token" not in str(signal.model_dump())

    row = await db.accommodation_checkouts.find_one(
        {"owner_id": OWNER, "id": "aco_v81"}, {"_id": 0}
    )
    assert row["status"] == "cancelled"
    assert row["provider_status"] == "cancelled"


@pytest.mark.asyncio
async def test_provider_date_change_keeps_all_delta_fields(monkeypatch):
    from accommodation.booking import BookingDemandClient

    db = AsyncMongoMockClient().test
    _configure_booking(monkeypatch)
    await db.accommodation_checkouts.insert_one(_checkout())

    current = {"checkin": "2026-10-23", "checkout": "2026-10-25"}

    async def details(self, *, order_id, currency="EUR"):
        return {
            "data": [_provider_item(
                checkin=current["checkin"],
                checkout=current["checkout"],
            )]
        }

    monkeypatch.setattr(BookingDemandClient, "accommodation_order_details", details)
    assert await read_changes(db, OWNER) == []

    current["checkin"] = "2026-10-24"
    current["checkout"] = "2026-10-26"
    signals = await read_changes(db, OWNER)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.signal_type == "travel.booking.changed"
    fields = {change.field for change in signal.changed_fields}
    assert fields == {"checkin", "checkout"}
    assert "2026-10-24" in signal.payload_summary
    assert "2026-10-26" in signal.payload_summary


@pytest.mark.asyncio
async def test_connected_life_records_booking_cancellation(monkeypatch):
    from accommodation.booking import BookingDemandClient

    db = AsyncMongoMockClient().test
    _configure_booking(monkeypatch)
    await db.accommodation_checkouts.insert_one(_checkout())

    current = {"status": "confirmed"}

    async def details(self, *, order_id, currency="EUR"):
        return {"data": [_provider_item(status=current["status"])]}

    monkeypatch.setattr(BookingDemandClient, "accommodation_order_details", details)

    service = ConnectedLifeService(db)
    await service.ensure_indexes()

    first = await service.sync(OWNER, "accommodation")
    assert first["ok"] is True
    assert first["recorded"] == 0

    current["status"] = "cancelled"
    second = await service.sync(OWNER, "accommodation")
    assert second["ok"] is True
    assert second["recorded"] == 1

    signal = await db.connected_signals.find_one(
        {"owner_id": OWNER, "source_id": "accommodation"}, {"_id": 0}
    )
    assert signal is not None
    assert signal["signal_type"] == "travel.booking.cancelled"


@pytest.mark.asyncio
async def test_travel_signal_translates_into_admissible_meaningful_change():
    from connected.models import ConnectedSignal, FieldChange

    db = AsyncMongoMockClient().test
    signal = ConnectedSignal(
        owner_id=OWNER,
        source_id="accommodation",
        source_type="travel",
        signal_type="travel.booking.cancelled",
        source_object_ref="ord_v81",
        payload_summary="Prenotazione Booking.com: stato cancelled.",
        after="cancelled",
        changed_fields=[
            FieldChange(field="status", before="confirmed", after="cancelled")
        ],
        relationship="own",
    )

    change = signal.as_change()
    assert change["source"] == "travel"
    assert change["kind"] == "booking.cancelled"

    admitted = await ChangeLog(db).record(OWNER, **{
        "source": change["source"],
        "kind": change["kind"],
        "entity_ref": change["entity_ref"],
        "entity_kind": change["entity_kind"],
        "before": change["before"],
        "after": change["after"],
        "occurred_at": change["occurred_at"],
    })
    assert admitted.admitted is True


def test_travel_booking_polling_is_bounded_not_live_traffic():
    from connected.polling import POLL_SECONDS

    assert POLL_SECONDS["travel"] == 300
    assert POLL_SECONDS["travel"] > POLL_SECONDS["calendar"]
