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


@pytest.mark.asyncio
async def test_booking_preview_uses_current_selection(monkeypatch):
    monkeypatch.setenv("BOOKING_DEMAND_TOKEN", "test-token")
    monkeypatch.setenv("BOOKING_AFFILIATE_ID", "123")
    client = BookingDemandClient()
    seen = {}

    async def fake_post(path, payload):
        seen["path"] = path
        seen["payload"] = payload
        return {
            "request_id": "preview-req",
            "data": {
                "order_token": "secret-order-token",
                "accommodation": {"id": 7},
                "price": {"total": {"booker_currency": 250.0}},
            },
        }

    monkeypatch.setattr(client, "_post", fake_post)
    result = await client.preview(
        accommodation_id=7,
        checkin="2026-10-23",
        checkout="2026-10-25",
        products=[{"id": "room-1", "number_of_adults": 2, "children": []}],
        currency="EUR",
        country="it",
        platform="android",
        travel_purpose="leisure",
    )
    assert seen["path"] == "orders/preview"
    assert seen["payload"]["accommodation"]["products"] == [{
        "id": "room-1",
        "allocation": {"number_of_adults": 2, "children": []},
    }]
    assert seen["payload"]["accommodation"]["booker"]["platform"] == "android"
    assert result["data"]["order_token"] == "secret-order-token"


@pytest.mark.asyncio
async def test_service_keeps_order_token_out_of_plain_preview_storage(monkeypatch):
    from accommodation.service import _strip_secret

    assert _strip_secret(
        {"order_token": "secret", "nested": {"order_token": "secret2", "ok": 1}},
        "order_token",
    ) == {"nested": {"ok": 1}}


def test_ai_core_catalogue_exposes_search_and_preview_but_not_booking_effect():
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    public = {item["capability"]: item for item in ToolRegistry(db=None).list_public()}
    assert "search_accommodations" in public
    assert "preview_accommodation" in public
    assert public["search_accommodations"]["side_effect"] == "READ_ONLY"
    assert public["preview_accommodation"]["side_effect"] == "READ_ONLY"
    assert "book_accommodation" not in public


@pytest.mark.asyncio
async def test_expired_preview_revokes_vault_secret_before_deleting(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient().test_accommodation_cleanup
    vault_calls = []

    class Vault:
        async def revoke(self, ref):
            vault_calls.append(ref)
            return True

    monkeypatch.setattr("deps.get_token_vault", lambda: Vault())
    service = AccommodationService(db)
    await service.ensure_indexes()
    await db[service.PREVIEWS].insert_one({
        "id": "apv_old",
        "owner_id": "u1",
        "status": "ready",
        "token_ref": "sv_old",
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
    })

    assert await service.cleanup_expired() == 1
    assert vault_calls == ["sv_old"]
    assert await db[service.PREVIEWS].count_documents({}) == 0


@pytest.mark.asyncio
async def test_checkout_keeps_sensitive_traveller_data_in_vault(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient().checkout_secure
    stored = {}
    revoked = []

    class Vault:
        async def put(self, *, user_id, purpose, payload, metadata=None):
            ref = f"sv_{len(stored) + 1}"
            stored[ref] = {"user_id": user_id, "purpose": purpose, "payload": payload}
            return ref

        async def get(self, ref, *, user_id):
            row = stored[ref]
            assert row["user_id"] == user_id
            return row["payload"]

        async def revoke(self, ref):
            revoked.append(ref)
            stored.pop(ref, None)
            return True

    monkeypatch.setattr("deps.get_token_vault", lambda: Vault())
    monkeypatch.setenv("BOOKING_DEMAND_TOKEN", "test-token")
    monkeypatch.setenv("BOOKING_AFFILIATE_ID", "123")
    service = AccommodationService(db)
    await service.ensure_indexes()
    await db[service.PREVIEWS].insert_one({
        "id": "apv_1",
        "owner_id": "u1",
        "provider": "booking.com",
        "request_id": "req",
        "token_ref": "sv_preview",
        "accommodation_id": "7",
        "checkin": "2026-10-23",
        "checkout": "2026-10-25",
        "product_ids": ["room-1"],
        "preview": {
            "accommodation": {
                "price": {"total": {"booker_currency": 250}},
                "payment": {"methods": ["pay_at_property"]},
            }
        },
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        "status": "ready",
    })
    stored["sv_preview"] = {
        "user_id": "u1",
        "purpose": "booking_order_preview",
        "payload": {"order_token": "secret-order-token"},
    }

    result = await service.prepare_checkout(
        owner_id="u1",
        preview_id="apv_1",
        booker={
            "name": {"first_name": "Test", "last_name": "User"},
            "address": {
                "address_line": "Via Test 1",
                "city": "Milano",
                "country": "it",
                "post_code": "20100",
            },
            "email": "test@example.com",
            "telephone": "+3900000000",
            "language": "it",
        },
        products=[{
            "id": "room-1",
            "guests": [{"name": "Test User", "email": "test@example.com"}],
        }],
        payment={
            "method": "pay_at_property",
            "timing": "pay_at_the_property",
            "include_receipt": True,
        },
    )

    assert result["creates_reservation"] is False
    checkout = await db[service.CHECKOUTS].find_one(
        {"id": result["checkout_id"]}, {"_id": 0}
    )
    assert checkout["terms_hash"] == result["terms_hash"]
    assert "test@example.com" not in str(checkout)
    assert "+3900000000" not in str(checkout)
    secure = stored[checkout["payload_ref"]]["payload"]
    assert secure["booker"]["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_booking_effect_is_never_autonomous_and_requires_frozen_terms(monkeypatch):
    from agent.authority import _NEVER_AUTONOMOUS
    from agent.models import ActionIntent
    from agent.effects import accommodation_booking

    assert "external.booking" in _NEVER_AUTONOMOUS

    intent = ActionIntent(
        owner_id="u1",
        goal_id="g1",
        step_id="s1",
        capability="external.booking",
        effect_summary="Prenota",
        parameters={},
    )
    outcome = await accommodation_booking(object(), "u1", intent)
    assert outcome.observed is False
    assert outcome.receipt.provider_status == "failed"
    assert outcome.receipt.error_type == "booking_checkout_not_frozen"


def test_checkout_schema_refuses_raw_card_data():
    from pydantic import ValidationError
    from accommodation.router import BookingCheckoutIn

    with pytest.raises(ValidationError):
        BookingCheckoutIn.model_validate({
            "preview_id": "apv_1",
            "booker": {
                "name": {"first_name": "A", "last_name": "B"},
                "address": {
                    "address_line": "Via A",
                    "city": "Roma",
                    "country": "it",
                    "post_code": "00100",
                },
                "email": "a@b.it",
                "telephone": "123",
            },
            "products": [{
                "id": "room",
                "guests": [{"name": "A B", "email": "a@b.it"}],
            }],
            "payment": {
                "method": "card",
                "timing": "pay_online_now",
                "card": {"number": "4111111111111111", "cvc": "123"},
            },
        })


@pytest.mark.asyncio
async def test_create_accepted_without_readback_never_retries_as_failure(monkeypatch):
    from agent.models import ActionIntent
    from agent import effects

    class Service:
        async def create_order_from_checkout(self, **kwargs):
            return {
                "status": "accepted_not_observed",
                "provider": "booking.com",
                "order_id": "ord_1",
                "reservation_id": "",
                "provider_status": "",
                "observed": False,
                "request_id": "req_1",
            }

    monkeypatch.setattr("accommodation.service.AccommodationService", lambda db: Service())
    intent = ActionIntent(
        owner_id="u1",
        goal_id="g1",
        step_id="s1",
        capability="external.booking",
        effect_summary="Prenota l'alloggio",
        parameters={"checkout_id": "aco_1", "terms_hash": "abc"},
    )
    outcome = await effects.accommodation_booking(object(), "u1", intent)
    assert outcome.receipt.provider_status == "accepted"
    assert outcome.receipt.retryable is False
    assert outcome.observed is False
    assert "non ripeto" in outcome.observation.lower()
