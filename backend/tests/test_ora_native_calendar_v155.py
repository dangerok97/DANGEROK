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
    # This is the structured source for BOTH the month row and the detail
    # screen. The client may be in Chicago; the appointment stays in Rome.
    assert selected["events"][0]["timezone"] == "Europe/Rome"
    assert selected["events"][0]["starts_at"] == "2026-10-11T09:30:00+02:00"
    assert selected["events"][0]["ends_at"] == "2026-10-11T10:15:00+02:00"
    assert detail.json()["timezone"] == selected["events"][0]["timezone"]
    assert detail.json()["starts_at"] == selected["events"][0]["starts_at"]
    assert detail.json()["ends_at"] == selected["events"][0]["ends_at"]
    assert detail.json()["provider"] == "ORA"
    assert detail.json()["is_local"] is True
    assert detail.json()["can_be_changed"] is True
    assert await db.connector_instances.count_documents({}) == 0


@pytest.mark.asyncio
async def test_remote_viewer_still_receives_event_zone_for_agenda_and_detail(
    isolated_calendar, monkeypatch,
):
    """User requested Rome 18:00; a New York browser sees a legacy 12:00.

    API must carry original event timezone so the unified frontend formatter
    can show 18:00 consistently in the month and detail, without rewriting
    either timestamp or attaching an external calendar.
    """
    db, identity, app = isolated_calendar

    async def remote_viewer_zone(db_, user_id):
        return SimpleNamespace(tz_name="America/New_York")

    monkeypatch.setattr(agenda_service, "resolve_user_timezone", remote_viewer_zone)
    created = await manual_event.create_manual_event(
        db, identity["user_id"], title="TEST ORA timezone comparison",
        start="2026-10-20T18:00:00+02:00",
        end="2026-10-20T18:10:00+02:00",
        tz_name="Europe/Rome", request_id="tz-agenda-vs-detail",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        result = await http.get("/api/agenda/month?month=2026-10")
        detail = await http.get("/api/calendar/events/" + created["id"])
    assert result.status_code == 200
    assert detail.status_code == 200
    assert result.json()["timezone"] == "America/New_York"
    day = next(x for x in result.json()["days"] if x["date"] == "2026-10-20")
    assert len(day["events"]) == 1
    event = day["events"][0]
    assert event["time_label"] == "12:00 — 12:10", (
        "This is the legacy viewer-local label; not authoritative for event time."
    )
    assert event["starts_at"] == "2026-10-20T12:00:00-04:00"
    assert event["ends_at"] == "2026-10-20T12:10:00-04:00"
    assert event["timezone"] == "Europe/Rome"
    assert detail.json()["starts_at"] == "2026-10-20T18:00:00+02:00"
    assert detail.json()["ends_at"] == "2026-10-20T18:10:00+02:00"
    assert detail.json()["timezone"] == event["timezone"]
    assert await db.life_nodes.count_documents({"user_id": identity["user_id"], "type": "event"}) == 1


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


@pytest.mark.asyncio
async def test_ai_can_add_to_ora_without_a_google_account(isolated_calendar, monkeypatch):
    from conversation_engine.ai_core.tools import calendar_caps

    db, owner, app = isolated_calendar

    async def no_google(*args, **kwargs):
        raise AssertionError("Native ORA write must never call Google sync or consent")

    monkeypatch.setattr(calendar_caps, "_sync_service", no_google)
    monkeypatch.setattr(calendar_caps, "require_calendar_consent", no_google)
    message = "Segna la visita fittizia nel calendario ORA il 15 ottobre alle 10."
    args = {
        "title": "Visita fittizia",
        "start_datetime": "2026-10-15T10:00:00+02:00",
        "end_datetime": "2026-10-15T10:45:00+02:00",
        "timezone": "Europe/Rome",
        "calendar_target": "ora",
        "user_authority": {
            "requested_by_user": True,
            "user_words": message,
            "what_they_asked_for": "aggiungere una visita nel calendario ORA",
        },
    }
    runtime = {"db": db, "user_id": owner["user_id"], "user_message": message}
    result = await calendar_caps.create_calendar_event(args, runtime)
    assert result.status == "ok", result.payload
    assert result.payload["provider"] == "ora"
    assert result.payload["verified"] is True
    saved = await db.life_nodes.find({
        "user_id": owner["user_id"], "type": "event",
        "attributes.kind": "home_manual",
    }).to_list(10)
    assert len(saved) == 1
    assert saved[0]["label"] == "Visita fittizia"

    again = await calendar_caps.create_calendar_event(args, runtime)
    assert again.status == "ok", again.payload
    assert again.payload["operation"] == "already_created"
    assert await db.life_nodes.count_documents({"user_id": owner["user_id"]}) == 1


@pytest.mark.asyncio
async def test_apple_write_is_not_silently_redirected_to_ora(isolated_calendar):
    from conversation_engine.ai_core.tools import calendar_caps

    db, owner, app = isolated_calendar
    result = await calendar_caps.create_calendar_event({
        "title": "Evento di prova",
        "start_datetime": "2026-10-15T10:00:00+02:00",
        "timezone": "Europe/Rome",
        "calendar_target": "apple",
    }, {"db": db, "user_id": owner["user_id"], "user_message": "Segnalo su Apple"})
    assert result.status == "error"
    assert result.payload["failure_kind"] == "READ_ONLY_CALENDAR"
    assert await db.life_nodes.count_documents({}) == 0


@pytest.mark.asyncio
async def test_chat_reads_native_events_even_when_google_service_unavailable(
    isolated_calendar, monkeypatch,
):
    from conversation_engine.ai_core.tools import calendar_caps
    from home.manual_event import create_manual_event

    db, owner, app = isolated_calendar

    async def user_timezone(db_, user_id):
        return SimpleNamespace(tz_name="Europe/Rome")

    async def no_google(*args, **kwargs):
        raise AssertionError("The optional Google client must not be initialized")

    monkeypatch.setattr(calendar_caps, "resolve_user_timezone", user_timezone)
    monkeypatch.setattr(calendar_caps, "_sync_service", no_google)
    await create_manual_event(
        db, owner["user_id"], title="Giornata locale",
        start="2026-10-15T00:00:00+02:00",
        end="2026-10-16T00:00:00+02:00",
        tz_name="Europe/Rome", all_day=True,
    )

    observed = await calendar_caps.get_calendar_events(
        {
            "time_min": "2026-10-14T00:00:00+02:00",
            "time_max": "2026-10-17T00:00:00+02:00",
        },
        {"db": db, "user_id": owner["user_id"]},
    )
    assert observed.status == "ok", observed.payload
    rows = observed.payload["events"]
    assert len(rows) == 1
    assert rows[0]["source"] == "ora_local"
    assert rows[0]["title"] == "Giornata locale"
    assert rows[0]["all_day"] is True
    assert observed.payload["google_events_included"] is False


@pytest.mark.asyncio
async def test_event_zone_day_remains_in_right_month_when_viewer_is_abroad(
    isolated_calendar, monkeypatch,
):
    """Regression: event clock 00:30 Rome must not land on September 30.

    The API can project a UTC instant into New York and legitimately return a
    September starts_at for October 1 in Rome. Its calendar cell must stay on
    the *event's* date. The same applies in reverse at month's last boundary.
    """
    db, identity, app = isolated_calendar

    async def remote_zone(db_, user_id):
        return SimpleNamespace(tz_name="America/New_York")

    monkeypatch.setattr(agenda_service, "resolve_user_timezone", remote_zone)
    local = await manual_event.create_manual_event(
        db, identity["user_id"], title="Test Rome first day",
        start="2026-10-01T00:30:00+02:00",
        end="2026-10-01T00:45:00+02:00",
        tz_name="Europe/Rome", request_id="boundary-rome-oct01",
    )
    abroad = await manual_event.create_manual_event(
        db, identity["user_id"], title="Test Honolulu last day",
        start="2026-10-31T23:45:00-10:00",
        end="2026-11-01T00:15:00-10:00",
        tz_name="Pacific/Honolulu", request_id="boundary-hawaii-oct31",
    )
    outside = await manual_event.create_manual_event(
        db, identity["user_id"], title="Do not show September",
        start="2026-09-30T23:40:00+02:00",
        end="2026-10-01T00:00:00+02:00",
        tz_name="Europe/Rome", request_id="boundary-sept-excluded",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as http:
        response = await http.get("/api/agenda/month?month=2026-10")
        rome = await http.get("/api/calendar/events/" + local["id"])
        honolulu = await http.get("/api/calendar/events/" + abroad["id"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total_events"] == 2, result
    assert result["source_counts"]["ora"] == 2
    by_day = {row["date"]: row["events"] for row in result["days"]}
    first_day = by_day["2026-10-01"]
    last_day = by_day["2026-10-31"]
    assert [row["id"] for row in first_day] == [local["id"]]
    assert [row["id"] for row in last_day] == [abroad["id"]]
    assert all(
        event["id"] != outside["id"]
        for events in by_day.values() for event in events
    )
    # Viewer-local projection differs from the event's calendar date;
    # original offsets and IANA zone must survive for the native frontend.
    assert first_day[0]["starts_at"][:10] == "2026-09-30"
    assert first_day[0]["timezone"] == "Europe/Rome"
    assert rome.json()["starts_at"] == "2026-10-01T00:30:00+02:00"
    assert last_day[0]["starts_at"][:10] == "2026-11-01"
    assert last_day[0]["timezone"] == "Pacific/Honolulu"
    assert honolulu.json()["starts_at"] == "2026-10-31T23:45:00-10:00"
    assert await db.life_nodes.count_documents({
        "user_id": identity["user_id"], "type": "event",
    }) == 3, "a read must never move or remove the actual event"


def test_event_zone_day_formatter_does_not_shift_all_day_dates():
    event = agenda_service._event_display_day
    assert event({
        "starts_at": "2026-09-30T18:30:00-04:00",
        "timezone": "Europe/Rome", "all_day": False,
    }) == "2026-10-01"
    assert event({
        "starts_at": "2026-10-01T00:00:00-04:00",
        "timezone": "Pacific/Honolulu", "all_day": True,
    }) == "2026-10-01"
    assert event({
        "starts_at": "2026-10-01T00:00:00-04:00",
        "timezone": "Invalid/Unknown", "all_day": False,
    }) == "2026-10-01"
