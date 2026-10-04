from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from places.models import ObservedRoutine
from places.service import PlacesService


@pytest.mark.asyncio
async def test_user_dismissed_routine_stays_dismissed_on_future_model_reread(monkeypatch):
    db = AsyncMongoMockClient().test
    service = PlacesService(db)

    existing = ObservedRoutine(
        id="rtn_home_work",
        user_id="alice",
        place_sequence=["home", "work"],
        weekdays=["lunedì"],
        typical_start="09:00",
        occurrences=7,
        interpretation="Vai spesso da casa al lavoro il lunedì mattina.",
        proactive_review_lead_minutes=30,
        state="dismissed",
    )
    await db.observed_routines.insert_one(existing.model_dump())

    monkeypatch.setattr(
        service,
        "routine_evidence",
        AsyncMock(return_value={
            "period": "last_30_days",
            "place_names": {"home": "Casa", "work": "Lavoro"},
            "days": [
                {"day": "2026-10-01", "places": ["home", "work"]},
                {"day": "2026-10-02", "places": ["home", "work"]},
            ],
            "journeys": [],
        }),
    )

    import places.reasoning as reasoning
    monkeypatch.setattr(
        reasoning,
        "read_the_shape_of_the_days",
        AsyncMock(return_value={
            "place_ids": ["home", "work"],
            "weekdays": ["lunedì"],
            "typical_start": "09:15",
            "typical_end": "10:00",
            "occurrences": 8,
            "interpretation": "Il lunedì vai spesso da casa al lavoro.",
            "worth_asking": False,
            "question": "",
            "proactive_review_lead_minutes": 45,
        }),
    )
    monkeypatch.setattr(service, "_schedule_routine_review", AsyncMock(return_value=True))

    result = await service.review_routines("alice")
    stored = await db.observed_routines.find_one(
        {"user_id": "alice", "id": "rtn_home_work"}, {"_id": 0}
    )

    assert result["routine"]["state"] == "dismissed"
    assert stored["state"] == "dismissed"
    assert stored["proactive_review_lead_minutes"] == 0
    service._schedule_routine_review.assert_not_awaited()


@pytest.mark.asyncio
async def test_accept_and_dismiss_control_only_that_routine_wake(monkeypatch):
    db = AsyncMongoMockClient().test
    service = PlacesService(db)

    first = ObservedRoutine(
        id="rtn_one",
        user_id="alice",
        place_sequence=["home", "work"],
        weekdays=["lunedì"],
        typical_start="09:00",
        proactive_review_lead_minutes=30,
    )
    second = ObservedRoutine(
        id="rtn_two",
        user_id="alice",
        place_sequence=["home", "gym"],
        weekdays=["martedì"],
        typical_start="18:00",
        proactive_review_lead_minutes=30,
    )
    await db.observed_routines.insert_many([first.model_dump(), second.model_dump()])
    await db.ambient_wakes.insert_many([
        {
            "owner_id": "alice", "status": "pending",
            "source_ref": "routine_review:rtn_one",
        },
        {
            "owner_id": "alice", "status": "pending",
            "source_ref": "routine_review:rtn_two",
        },
    ])

    monkeypatch.setattr(service, "_schedule_routine_review", AsyncMock(return_value=True))
    accepted = await service.set_routine_state("alice", "rtn_one", "accepted")
    assert accepted["state"] == "accepted"
    service._schedule_routine_review.assert_awaited_once()

    dismissed = await service.set_routine_state("alice", "rtn_one", "dismissed")
    assert dismissed["state"] == "dismissed"

    one = await db.ambient_wakes.find_one({"source_ref": "routine_review:rtn_one"})
    two = await db.ambient_wakes.find_one({"source_ref": "routine_review:rtn_two"})
    assert one["status"] == "cancelled"
    assert two["status"] == "pending"


@pytest.mark.asyncio
async def test_visible_routines_use_human_place_names_and_hide_dismissed():
    db = AsyncMongoMockClient().test
    service = PlacesService(db)

    from places.models import LifePlace
    await service.repo.save_place(LifePlace(id="home", user_id="alice", label="Casa"))
    await service.repo.save_place(LifePlace(id="work", user_id="alice", label="Lavoro"))

    await db.observed_routines.insert_many([
        ObservedRoutine(
            id="visible",
            user_id="alice",
            place_sequence=["home", "work"],
            weekdays=["lunedì"],
            typical_start="09:00",
            interpretation="Vai spesso da casa al lavoro.",
            state="candidate",
        ).model_dump(),
        ObservedRoutine(
            id="hidden",
            user_id="alice",
            place_sequence=["work", "home"],
            state="dismissed",
        ).model_dump(),
    ])

    rows = await service.list_routines("alice")
    assert [row["id"] for row in rows] == ["visible"]
    assert rows[0]["place_names"] == ["Casa", "Lavoro"]
