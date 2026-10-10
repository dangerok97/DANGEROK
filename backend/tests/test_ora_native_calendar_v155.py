"""Native ORA calendar: owner-scoped month and optional external overlays.

No OAuth, device Calendar API, network provider, real account or external writes.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from agenda import router as agenda_routes
from agenda import service as agenda_service
from home import manual_event
from routers import calendar_events as calendar_routes


@pytest.fixture
def isolated_calendar(monkeypatch):
    mongo = AsyncMongoMockClient()
    db = mongo.ora_native_calendar_v155
    identity = {"user_id": "owner_a"}

    async def timezone(db_, user_id):
        return SimpleNamespace(tz_name="Europe/Rome")

    async def quiet_wake(*args, **kwargs):
        return None

    monkeypatch.setattr(agenda_routes, "db", db)
    monkeypatch.setattr(calendar_routes, "db", db)
    monkeypatch.setattr(agenda_service, "resolve_user_timezone", timezone)
    monkeypatch.setattr(manual_event, "_wake", quiet_wake)

    app = FastAPI()
    app.include_router(agenda_routes.router, prefix="/api")
    app.include_router(calendar_routes.router, prefix="/api")
    app.dependency_overrides[agenda_routes.get_current_user] = lambda: identity
    return db, identity, app


def event_node(uid, eid, title, source, day="2026-10-11"):
    return {
        "id": eid, "user_id": uid, "type": "event", "label": title,
        "status": "active", "description": "Solo un test",
        "attributes": {
            "starts_at": day + "T10:00:00+02:00",
            "ends_at": day + "T11:00:00+02:00",
            "timezone": "Europe/Rome",
            "connector_id": source,
        },
    }


@pytest.mark.asyncio
async def test_empty_account_has_usable_month_without_google_or_apple(isolated_calendar):
    db, owner, app = isolated_calendar
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/agenda/month?month=2026-10")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["month"] == "2026-10"
    assert result["timezone"] == "Europe/Rome"
    assert len(result["days"]) == 31
    assert result["total_events"] == 0
    assert result["calendar_connected"] is False
    assert result["connected_sources"] == []
    assert result["source_counts"] == {
        "ora": 0, "google": 0, "apple": 0, "other": 0,
    }
    assert await db.connector_instances.count_documents({}) == 0


@pytest.mark.asyncio
async def test_native_event_create_and_read_without_oauth(isolated_calendar):
    db, owner, app = isolated_calendar
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        created = await http.post("/api/calendar/events/home", json={
            "title": "Prova calendario ORA",
            "day": "2026-10-11", "time": "09:30",
            "duration_minutes": 45, "timezone": "Europe/Rome",
            "request_id": "native-event-test-001",
        })
        assert created.status_code == 200, created.text
        own_id = created.json()["id"]
        response = await http.get("/api/agenda/month?month=2026-10")
        detail = await http.get("/api/calendar/events/" + own_id)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total_events"] == 1
    assert result["source_counts"]["ora"] == 1
    selected = next(day for day in result["days"] if day["date"] == "2026-10-11")
    assert selected["events"][0]["id"] == own_id
    assert selected["events"][0]["source_type"] == "ora"
    assert selected["events"][0]["source_label"] == "Calendario ORA"
    assert detail.json()["provider"] == "ORA"
    assert detail.json()["is_local"] is True
    assert detail.json()["can_be_changed"] is True
    assert await db.connector_instances.count_documents({}) == 0


@pytest.mark.asyncio
async def test_connected_calendar_overlay_is_optional_and_disconnected_mirrors_hidden(isolated_calendar):
    db, owner, app = isolated_calendar
    await db.life_nodes.insert_many([
        event_node("owner_a", "google_a", "Prova Google", "calendar_google"),
        event_node("owner_a", "apple_a", "Prova Apple", "calendar_apple"),
        event_node("owner_b", "google_other", "Segreto altro account", "calendar_google"),
    ])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        first = (await http.get("/api/agenda/month?month=2026-10")).json()
        assert first["total_events"] == 0  # connection is opt-in
        await db.connector_instances.insert_many([
            {"user_id": "owner_a", "connector_id": "calendar_google", "status": "connected"},
            {"user_id": "owner_a", "connector_id": "calendar_apple", "status": "connected"},
        ])
        result = (await http.get("/api/agenda/month?month=2026-10")).json()
        events = [event for day in result["days"] for event in day["events"]]
        assert {e["id"] for e in events} == {"google_a", "apple_a"}
        assert result["source_counts"]["google"] == 1
        assert result["source_counts"]["apple"] == 1
        assert sorted(result["connected_sources"]) == ["apple", "google"]
        apple_detail = await http.get("/api/calendar/events/apple_a")
        assert apple_detail.status_code == 200
        assert apple_detail.json()["provider"] == "Calendario Apple"
        assert apple_detail.json()["can_be_changed"] is False
        rejected = await http.post("/api/calendar/events/apple_a/delete", json={"confirmed_title": "Prova Apple"})
        assert rejected.status_code == 409
        assert await db.life_nodes.count_documents({"id": "apple_a", "status": "active"}) == 1
        owner["user_id"] = "owner_b"
        another = (await http.get("/api/agenda/month?month=2026-10")).json()
        assert another["total_events"] == 0
        assert (await http.get("/api/calendar/events/apple_a")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("month", ["2026-00", "2026-13", "2026-1", "bad-date"])
async def test_reject_invalid_month(isolated_calendar, month):
    db, owner, app = isolated_calendar
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        result = await http.get("/api/agenda/month", params={"month": month})
    assert result.status_code == 422
