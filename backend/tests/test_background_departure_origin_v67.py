from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mongomock_motor import AsyncMongoMockClient

from location.models import PresenceContext
from places.departures import DepartureService
from places.models import Coordinates, PresenceObservation
from places.repository import PlacesRepository


OWNER = "alice"


def event(now):
    return {
        "ref": "calendar:bg:1",
        "title": "Appuntamento",
        "starts_at": (now + timedelta(minutes=45)).isoformat(),
        "ends_at": (now + timedelta(minutes=75)).isoformat(),
        "location": "Studio",
        "all_day": False,
    }


async def configured_world(monkeypatch, *, monitoring=True, source="background_device"):
    db = AsyncMongoMockClient().test
    now = datetime.now(timezone.utc)
    await db.users.insert_one({
        "user_id": OWNER,
        "settings": {"location_mode": "while_using"},
        "preferences": {"place_monitoring_enabled": monitoring},
    })

    stale = PresenceContext(
        user_id=OWNER,
        preference="while_using",
        permission_state="granted_foreground",
        freshness="STALE",
        last_seen_at=(now - timedelta(hours=1)).isoformat(),
        latitude=40.0,
        longitude=10.0,
        accuracy_meters=10,
        source="foreground_device",
    )
    monkeypatch.setattr(
        "location.service.LocationService.build_presence",
        AsyncMock(return_value=stale),
    )

    await PlacesRepository(db).add_observation(PresenceObservation(
        user_id=OWNER,
        coordinates=Coordinates(
            latitude=41.901,
            longitude=12.501,
            accuracy_meters=15,
        ),
        observed_at=(now - timedelta(seconds=20)).isoformat(),
        source=source,
        event_id="evt_background_1",
    ))

    monkeypatch.setattr(
        "places.routing.capabilities",
        lambda: {"available": True, "modes": ["drive"]},
    )
    monkeypatch.setattr(
        "places.service.PlacesService.resolve_destination",
        AsyncMock(return_value=SimpleNamespace(
            resolved=True,
            candidates=[],
            place=SimpleNamespace(
                coordinates=SimpleNamespace(latitude=41.95, longitude=12.55)
            ),
        )),
    )

    route = AsyncMock(return_value={
        "available": True,
        "provider": "controlled",
        "duration_seconds": 900,
        "distance_meters": 5000,
        "reflects_current_traffic": True,
        "alternatives": [],
    })
    monkeypatch.setattr("places.routing.get_route", route)
    return db, now, route


@pytest.mark.asyncio
async def test_fresh_background_fix_drives_departure_when_foreground_is_stale(monkeypatch):
    db, now, route = await configured_world(monkeypatch)

    rows = await DepartureService(db).collect(OWNER, [event(now)], now=now)

    assert len(rows) == 1
    assert rows[0]["status"] == "ready"
    assert rows[0]["origin_source"] == "background_device"
    assert route.await_count == 1
    assert route.await_args.kwargs["origin"] == {
        "latitude": 41.901,
        "longitude": 12.501,
    }


@pytest.mark.asyncio
async def test_background_fix_is_ignored_when_monitoring_is_off(monkeypatch):
    db, now, route = await configured_world(monkeypatch, monitoring=False)

    rows = await DepartureService(db).collect(OWNER, [event(now)], now=now)

    assert rows[0]["status"] == "needs_current_location"
    route.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreground_label_cannot_masquerade_as_background_fallback(monkeypatch):
    db, now, route = await configured_world(
        monkeypatch, monitoring=True, source="foreground_device"
    )

    rows = await DepartureService(db).collect(OWNER, [event(now)], now=now)

    assert rows[0]["status"] == "needs_current_location"
    route.assert_not_awaited()


def test_places_observation_contract_accepts_only_bounded_device_sources():
    from places.router import ObservationIn

    assert ObservationIn(
        latitude=41.9,
        longitude=12.5,
        source="background_device",
    ).source == "background_device"

    with pytest.raises(Exception):
        ObservationIn(
            latitude=41.9,
            longitude=12.5,
            source="invented_source",
        )
