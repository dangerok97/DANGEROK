import pytest

from accommodation.booking import BookingDemandClient
from accommodation.service import AccommodationError, AccommodationService


@pytest.mark.asyncio
async def test_booking_search_normalises_prices_and_details(monkeypatch):
    monkeypatch.setenv("BOOKING_DEMAND_TOKEN", "test-token")
    monkeypatch.setenv("BOOKING_AFFILIATE_ID", "123")
    client = BookingDemandClient()

    async def fake_post(path, payload):
        if path == "accommodations/search":
            return {
                "request_id": "req-1",
                "data": [{
                    "id": 7,
                    "currency": {"booker": "EUR", "accommodation": "EUR"},
                    "price": {"total": {"booker_currency": 212.40}},
                    "products": [{"id": "room-rate-1"}],
                    "url": {"web": "https://example.test/hotel"},
                }],
                "metadata": {},
            }
        assert path == "accommodations/details"
        return {
            "data": [{
                "id": 7,
                "name": {"it": "Hotel Test"},
                "address": {
                    "address_line": "Via Test 1",
                    "city_name": "Milano",
                    "country_code": "it",
                },
            }]
        }

    monkeypatch.setattr(client, "_post", fake_post)
    result = await client.search(
        latitude=45.4642,
        longitude=9.1900,
        checkin="2026-10-23",
        checkout="2026-10-25",
        adults=2,
        rooms=1,
    )
    assert result["request_id"] == "req-1"
    assert result["offers"][0]["name"] == "Hotel Test"
    assert result["offers"][0]["total_price"] == pytest.approx(212.40)
    assert result["offers"][0]["product_ids"] == ["room-rate-1"]
    assert result["offers"][0]["bookable_in_app"] is True


@pytest.mark.asyncio
async def test_service_refuses_to_fake_search_without_partner_credentials(monkeypatch):
    monkeypatch.delenv("BOOKING_DEMAND_TOKEN", raising=False)
    monkeypatch.delenv("BOOKING_AFFILIATE_ID", raising=False)
    service = AccommodationService()

    with pytest.raises(AccommodationError) as caught:
        await service.search(
            destination="Milano",
            latitude=45.4642,
            longitude=9.1900,
            checkin="2026-10-23",
            checkout="2026-10-25",
        )
    assert caught.value.code == "provider_not_configured"


@pytest.mark.asyncio
async def test_service_rejects_invalid_date_order(monkeypatch):
    monkeypatch.setenv("BOOKING_DEMAND_TOKEN", "test-token")
    monkeypatch.setenv("BOOKING_AFFILIATE_ID", "123")
    service = AccommodationService()

    with pytest.raises(AccommodationError) as caught:
        await service.search(
            destination="Milano",
            latitude=45.4642,
            longitude=9.1900,
            checkin="2026-10-25",
            checkout="2026-10-23",
        )
    assert caught.value.code == "invalid_dates"


@pytest.mark.asyncio
async def test_service_rejects_half_coordinates(monkeypatch):
    monkeypatch.setenv("BOOKING_DEMAND_TOKEN", "test-token")
    monkeypatch.setenv("BOOKING_AFFILIATE_ID", "123")
    service = AccommodationService()

    with pytest.raises(AccommodationError) as caught:
        await service.search(
            destination="Milano",
            latitude=45.4642,
            longitude=None,
            checkin="2026-10-23",
            checkout="2026-10-25",
        )
    assert caught.value.code == "incomplete_coordinates"
