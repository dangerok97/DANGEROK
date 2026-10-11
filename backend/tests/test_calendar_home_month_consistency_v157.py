"""The month and Home must see the same imported appointment and source.

Synthetic owners, in-memory Mongo, real ingestion normalizer/repository.
No provider calls, OAuth tokens, real accounts or background writes.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from home.adapters.google_calendar import load_google_calendar_events
from ingestion.event_model import IngestionEventRepository
from ingestion.normalizer import GoogleCalendarNormalizer
from test_ora_native_calendar_v155 import isolated_calendar, event_node  # noqa: F401


async def connect(db, uid, iid, *, status="connected", calendars=None):
    await db.connector_instances.insert_one({
        "id": iid, "user_id": uid, "connector_id": "calendar_google",
        "status": status, "selected_resource_ids": calendars or [],
    })


async def ingest(db, uid, iid, external_id, title, when, *, calendar="primary",
                 status="confirmed", all_day=False):
    raw = {
        "id": external_id, "summary": title, "status": status,
        "start": {"date": when} if all_day else {"dateTime": when.isoformat()},
        "end": {"date": (datetime.fromisoformat(when) + timedelta(days=1)).date().isoformat()}
        if all_day else {"dateTime": (when + timedelta(hours=1)).isoformat()},
    }
    normalized = GoogleCalendarNormalizer(
        connector_id="calendar_google", connector_instance_id=iid,
    ).normalize(raw=raw, calendar_id=calendar, calendar_name=calendar)
    return await IngestionEventRepository(db).insert(
        user_id=uid, connector_id="calendar_google", connector_instance_id=iid,
        external_id=external_id, external_version=normalized.source_hash,
        source_type="calendar_google", source_record_type="calendar_event",
        raw_reference={"calendar_id": calendar}, normalized_payload=normalized.to_dict(),
        payload_hash=normalized.source_hash, source_created_at=None,
        source_updated_at=None, provenance={}, sensitivity="personal", status="processed",
    )


def tomorrow():
    return (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0,
    )


def mirror(uid, nid, iid, external_id, title, when, *, calendar="primary"):
    node = event_node(uid, nid, title, "calendar_google", when.date().isoformat())
    node["attributes"].update({
        "starts_at": when.isoformat(), "ends_at": (when + timedelta(hours=1)).isoformat(),
        "connector_instance_id": iid, "external_event_id": external_id,
        "calendar_id": calendar,
    })
    return node


@pytest.mark.asyncio
async def test_import_visible_in_home_is_also_visible_in_month_and_opens_detail(isolated_calendar):
    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    when = tomorrow()
    await connect(db, uid, "google_a")
    row = await ingest(db, uid, "google_a", "appointment", "Visita di prova", when)
    assert await db.life_nodes.count_documents({}) == 0
    home, _ = await load_google_calendar_events(db, uid)
    assert [item.title for item in home] == ["Visita di prova"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        month = (await http.get("/api/agenda/month", params={"month": when.strftime("%Y-%m")})).json()
        events = [event for day in month["days"] for event in day["events"]]
        assert [(event["id"], event["title"]) for event in events] == [(row["id"], home[0].title)]
        detail = await http.get("/api/calendar/events/" + events[0]["id"])
        assert detail.status_code == 200
        assert detail.json()["title"] == home[0].title
    assert await db.life_nodes.count_documents({}) == 0  # reads never repair by writing


@pytest.mark.asyncio
async def test_month_uses_updated_ingestion_once_and_obeys_each_account_selection(isolated_calendar):
    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    when = tomorrow()
    await connect(db, uid, "a", calendars=["selected_a"])
    await connect(db, uid, "b", calendars=["selected_b"])
    await connect(db, uid, "revoked", status="revoked")
    a = await ingest(db, uid, "a", "same_external_id", "Aggiornato A", when, calendar="selected_a")
    b = await ingest(db, uid, "b", "same_external_id", "Evento B", when, calendar="selected_b")
    await ingest(db, uid, "a", "deselected", "Calendario tolto", when, calendar="removed")
    await ingest(db, uid, "revoked", "revoked_event", "Account scollegato", when)
    await ingest(db, "owner_b", "a", "private", "Altro utente", when, calendar="selected_a")
    await db.life_nodes.insert_many([
        mirror(uid, "old_a", "a", "same_external_id", "Vecchio titolo A", when, calendar="selected_a"),
        mirror(uid, "old_b", "b", "same_external_id", "Evento B", when, calendar="selected_b"),
        mirror(uid, "old_removed", "a", "deselected", "Calendario tolto", when, calendar="removed"),
        mirror(uid, "old_revoked", "revoked", "revoked_event", "Account scollegato", when),
    ])
    home, _ = await load_google_calendar_events(db, uid)
    assert {item.title for item in home} == {"Aggiornato A", "Evento B"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        month = (await http.get("/api/agenda/month", params={"month": when.strftime("%Y-%m")})).json()
    events = [event for day in month["days"] for event in day["events"]]
    assert {event["id"] for event in events} == {a["id"], b["id"]}
    assert month["total_events"] == 2
    assert month["source_counts"]["google"] == 2


@pytest.mark.asyncio
async def test_cancelled_or_moved_import_does_not_resurrect_stale_graph_mirror(isolated_calendar):
    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    when = datetime(2026, 10, 10, 10, tzinfo=ZoneInfo("Europe/Rome"))
    await connect(db, uid, "a")
    await db.life_nodes.insert_many([
        mirror(uid, "stale_cancelled", "a", "cancelled", "Annullato", when),
        mirror(uid, "stale_moved", "a", "moved", "Spostato a novembre", when),
        mirror(uid, "stale_detached", "a", "detached", "Fonte rimossa", when),
    ])
    await ingest(db, uid, "a", "cancelled", "Annullato", when, status="cancelled")
    await ingest(db, uid, "a", "moved", "Spostato a novembre", when.replace(month=11))
    detached = await ingest(db, uid, "a", "detached", "Fonte rimossa", when)
    await db.ingestion_events.update_one({"id": detached["id"]}, {"$set": {"source_status": "detached"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        month = (await http.get("/api/agenda/month?month=2026-10")).json()
    assert month["total_events"] == 0


@pytest.mark.asyncio
async def test_empty_selection_uses_known_primary_calendar_without_reviving_old_selection(isolated_calendar):
    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    when = tomorrow()
    await connect(db, uid, "a")
    await db.connector_instances.update_one({"id": "a"}, {"$set": {
        "metadata": {"account_email": "calendar-owner@example.test"},
    }})
    await ingest(db, uid, "a", "main", "Principale", when, calendar="calendar-owner@example.test")
    await ingest(db, uid, "a", "removed", "Vecchia selezione", when, calendar="removed")
    home, _ = await load_google_calendar_events(db, uid)
    assert [item.title for item in home] == ["Principale"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        month = (await http.get("/api/agenda/month", params={"month": when.strftime("%Y-%m")})).json()
    assert month["total_events"] == 1


@pytest.mark.asyncio
async def test_all_day_keeps_calendar_date_and_timed_event_uses_viewer_timezone(isolated_calendar):
    db, identity, app = isolated_calendar
    uid = identity["user_id"]
    await connect(db, uid, "a")
    await ingest(db, uid, "a", "utc_boundary", "Mezzanotte e mezza", datetime(
        2026, 9, 30, 22, 30, tzinfo=ZoneInfo("UTC"),
    ))
    node = event_node(uid, "all_day_local", "Primo ottobre", "", "2026-10-01")
    node["attributes"].update({
        "starts_at": "2026-10-01", "ends_at": "2026-10-02",
        "all_day": True, "timezone": "Pacific/Auckland",
    })
    await db.life_nodes.insert_one(node)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        month = (await http.get("/api/agenda/month?month=2026-10")).json()
    first = month["days"][0]["events"]
    assert {event["title"] for event in first} == {"Mezzanotte e mezza", "Primo ottobre"}
    assert next(event for event in first if not event["all_day"])["time_label"] == "00:30 — 01:30"
    assert next(event for event in first if event["all_day"])["time_label"] == "Tutto il giorno"
