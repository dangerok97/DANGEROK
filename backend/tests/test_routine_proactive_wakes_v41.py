from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

import ambient.service as ambient_service
import places.service as places_service
from places.models import ObservedRoutine
from places.service import PlacesService, _next_routine_review_at


def test_next_routine_review_uses_local_weekday_and_model_lead():
    now = datetime.fromisoformat("2026-10-05T08:00:00+02:00")  # Monday
    due = _next_routine_review_at(now, ["lunedì"], "09:00", 30)

    assert due is not None
    assert due.isoformat() == "2026-10-05T08:30:00+02:00"


def test_next_routine_review_refuses_missing_or_unbounded_model_judgement():
    now = datetime.fromisoformat("2026-10-05T08:00:00+02:00")
    assert _next_routine_review_at(now, ["monday"], "09:00", 0) is None
    assert _next_routine_review_at(now, ["monday"], "09:00", 181) is None
    assert _next_routine_review_at(now, ["not-a-day"], "09:00", 30) is None


@pytest.mark.asyncio
async def test_model_decided_routine_review_is_a_quiet_ambient_wake(monkeypatch):
    db = AsyncMongoMockClient().test
    service = PlacesService(db)
    fixed_utc = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(places_service, "_now", lambda: fixed_utc)
    monkeypatch.setattr(ambient_service, "_now", lambda: fixed_utc)

    import timezone_service
    monkeypatch.setattr(
        timezone_service,
        "user_clock_context",
        AsyncMock(return_value={
            "local_datetime": "2026-10-05T08:00:00+02:00",
            "timezone": "Europe/Rome",
            "authority": "profile",
        }),
    )
    await db.users.insert_one({
        "user_id": "alice",
        "preferences": {"place_monitoring_enabled": True},
    })

    routine = ObservedRoutine(
        id="rtn_commute",
        user_id="alice",
        place_sequence=["home", "work"],
        weekdays=["lunedì"],
        typical_start="09:00",
        proactive_review_lead_minutes=30,
        interpretation="Di solito vai da casa al lavoro il lunedì mattina.",
    )

    assert await service._schedule_routine_review("alice", routine) is True
    wake = await db.ambient_wakes.find_one(
        {"owner_id": "alice", "status": "pending"}, {"_id": 0}
    )

    assert wake["reason"] == "ambient_review"
    assert wake["source_ref"] == "routine_review:rtn_commute"
    assert wake["provenance"] == "model"
    assert wake["scheduled_for"] == "2026-10-05T06:30:00+00:00"


@pytest.mark.asyncio
async def test_routine_review_respects_location_monitoring_consent(monkeypatch):
    db = AsyncMongoMockClient().test
    service = PlacesService(db)
    routine = ObservedRoutine(
        user_id="alice",
        place_sequence=["home", "work"],
        weekdays=["monday"],
        typical_start="09:00",
        proactive_review_lead_minutes=30,
    )

    assert await service._schedule_routine_review("alice", routine) is False
    assert await db.ambient_wakes.count_documents({}) == 0
