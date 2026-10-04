"""Synthetic calendar + location, real persistence and lifecycle; provider boundaries controlled."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from location.models import PresenceContext
from opportunities.models import EvidenceRef, Opportunity
from places.departures import DepartureService, COLLECTION, WAKE_SOURCE, current_origin


@pytest_asyncio.fixture
async def world(monkeypatch):
    db = AsyncMongoMockClient().test
    now = datetime.now(timezone.utc)
    presence = PresenceContext(user_id="alice", preference="while_using", permission_state="granted_foreground",
        source="foreground_device", freshness="CURRENT", last_seen_at=now.isoformat(),
        latitude=41.9, longitude=12.5, accuracy_meters=10)
    await db.users.insert_one({"user_id": "alice", "settings": {"location_mode": "while_using"}})
    start = (now + timedelta(minutes=45)).isoformat()
    event = {"ref": "meeting_1", "title": "Ritiro documenti", "starts_at": start,
             "ends_at": (now + timedelta(minutes=75)).isoformat(), "location": "Studio", "all_day": False}
    await db.calendar_events.insert_one({"id": "meeting_1", "user_id": "alice", "title": event["title"],
        "start_at": start, "end_at": event["ends_at"], "location": "Studio", "status": "active"})
    monkeypatch.setattr("location.service.LocationService.build_presence", AsyncMock(return_value=presence))
    monkeypatch.setattr("places.routing.capabilities", lambda: {"available": True, "modes": ["drive", "walk"]})
    resolve = AsyncMock(return_value=SimpleNamespace(resolved=True, candidates=[],
        place=SimpleNamespace(coordinates=SimpleNamespace(latitude=41.92, longitude=12.51))))
    monkeypatch.setattr("places.service.PlacesService.resolve_destination", resolve)
    async def route(**kwargs):
        return {"available": True, "provider": "controlled_test_provider",
                "duration_seconds": 900 if kwargs["travel_mode"] == "drive" else 2400,
                "distance_meters": 4000, "reflects_current_traffic": kwargs["travel_mode"] == "drive"}
    routes = AsyncMock(side_effect=route)
    monkeypatch.setattr("places.routing.get_route", routes)
    svc = DepartureService(db)
    await svc.ensure_indexes()
    return SimpleNamespace(db=db, now=now, presence=presence, event=event, svc=svc, routes=routes, resolve=resolve)


async def ready_opportunity(world):
    rows = await world.svc.collect("alice", [world.event], now=world.now)
    evidence = rows[0]
    opportunity = Opportunity(owner_id="alice", identity_key="departure:test", status="active",
        surface_state="surfaced", semantic_summary="Partenza", why_it_matters="Impegno imminente",
        evidence=[EvidenceRef(ref=evidence["ref"], kind="departure")], valid_until=evidence["valid_until"])
    from opportunities.repository import OpportunityRepository
    await OpportunityRepository(world.db).save(opportunity)
    return evidence, opportunity


@pytest.mark.asyncio
async def test_routes_have_separate_modes_margin_freshness_and_precise_durable_wakes(world):
    a = (await world.svc.collect("alice", [world.event], now=world.now))[0]
    b = (await world.svc.collect("alice", [world.event], now=world.now + timedelta(seconds=20)))[0]
    assert a["ref"] == b["ref"] and world.routes.await_count == 2
    assert b["options"][0]["seconds_until_departure"] == a["options"][0]["seconds_until_departure"] - 20
    assert a["status"] == "ready" and a["mode_selected"] is False
    assert [r["mode"] for r in a["options"]] == ["drive", "walk"]
    assert datetime.fromisoformat(a["options"][0]["leave_at"]) == world.now + timedelta(minutes=20)
    assert datetime.fromisoformat(a["options"][1]["leave_at"]) == world.now - timedelta(minutes=5)
    assert datetime.fromisoformat(a["valid_until"]) <= world.now + timedelta(seconds=120)
    wakes = await world.db.ambient_wakes.find(
        {"owner_id": "alice", "status": "pending"}, {"_id": 0}
    ).to_list(10)
    assert len(wakes) == 2
    broad = next(w for w in wakes if w["source_ref"] == WAKE_SOURCE)
    precise = next(w for w in wakes if w["source_ref"].startswith("calendar_departure_due:"))
    assert datetime.fromisoformat(broad["scheduled_for"]) <= world.now + timedelta(minutes=3)
    # Drive leaves in 20m; ORA rechecks 15m before that, without a foreground request.
    assert datetime.fromisoformat(precise["scheduled_for"]) == world.now + timedelta(minutes=5)
    saved = await world.db[COLLECTION].find_one({"owner_id": "alice"})
    assert "latitude" not in str(saved) and "longitude" not in str(saved)
    assert await world.db.opportunities.count_documents({}) == 0  # Facts don't create an alert.


def test_mixed_timezones_and_one_past_mode_do_not_hide_remaining_options():
    from places.departures import with_timing
    now = datetime.fromisoformat("2026-10-03T21:26:00+02:00")
    facts = {"status": "ready", "starts_at": "2026-10-03T21:48:00+02:00", "options": [
        {"mode": "drive", "leave_at": "2026-10-03T19:30:00+00:00"},
        {"mode": "walk", "leave_at": "2026-10-03T19:15:00+00:00"},
        {"mode": "bicycle", "leave_at": "2026-10-03T19:31:00+00:00"}]}
    result = with_timing(facts, now, {"timezone": "Europe/Rome", "authority": "system_fallback"})
    drive, walk, bike = result["options"]
    assert drive["leave_local"] == "2026-10-03T21:30:00+02:00"
    assert [o["seconds_until_departure"] for o in result["options"]] == [240, -660, 300]
    assert drive["full_margin_still_available"] and bike["full_margin_still_available"]
    assert not walk["full_margin_still_available"]
    assert drive["estimated_lateness_if_leaving_now_seconds"] == 0
    assert walk["estimated_lateness_if_leaving_now_seconds"] == 60
    assert "leave_local" not in facts["options"][0]  # Cache remains the original observation.


def test_departure_arithmetic_keeps_dst_instants_distinct():
    from places.departures import with_timing
    now = datetime.fromisoformat("2026-10-25T02:50:00+02:00")
    facts = {"status": "ready", "starts_at": "2026-10-25T03:00:00+01:00", "options": [
        {"mode": "drive", "leave_at": "2026-10-25T01:10:00+00:00"}]}
    option = with_timing(facts, now, {"timezone": "Europe/Rome", "authority": "user_confirmed"})["options"][0]
    assert option["leave_local"] == "2026-10-25T02:10:00+01:00"
    assert option["seconds_until_departure"] == 1200  # Earlier local clock, later instant.


@pytest.mark.asyncio
async def test_traffic_recalculation_changes_estimate_but_not_calendar_identity(world):
    first = (await world.svc.collect("alice", [world.event], now=world.now))[0]
    world.routes.side_effect = None
    world.routes.return_value = {"available": True, "duration_seconds": 1500, "provider": "test"}
    second = (await world.svc.collect("alice", [world.event], now=world.now + timedelta(seconds=61)))[0]
    assert second["event_ref"] == first["event_ref"]
    assert second["ref"] != first["ref"]
    assert datetime.fromisoformat(second["options"][0]["leave_at"]) == world.now + timedelta(minutes=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["cancel", "move", "destination", "stale_fix", "new_fix", "revoked", "other_owner"])
async def test_changed_evidence_cannot_surface_or_send(world, monkeypatch, change):
    _, opportunity = await ready_opportunity(world)
    assert await world.svc.evidence_is_current("alice", opportunity)
    if change == "cancel":
        await world.db.calendar_events.update_one({"id": "meeting_1"}, {"$set": {"status": "cancelled"}})
    elif change == "move":
        await world.db.calendar_events.update_one({"id": "meeting_1"}, {"$set": {"start_at": (world.now + timedelta(hours=3)).isoformat()}})
    elif change == "destination":
        await world.db.calendar_events.update_one({"id": "meeting_1"}, {"$set": {"location": "Altro studio"}})
    elif change == "stale_fix":
        world.presence.last_seen_at = (world.now - timedelta(minutes=5)).isoformat()
    elif change == "new_fix":
        world.presence.latitude = 42.0
    elif change == "revoked":
        world.presence.preference = "off"
    elif change == "other_owner":
        assert not await world.svc.evidence_is_current("bob", opportunity)
        return
    assert not await world.svc.evidence_is_current("alice", opportunity)
    from opportunities.surfacing import SurfacingService
    assert await SurfacingService(world.db).visible("alice") == []
    from delivery.service import DeliveryService
    decide = AsyncMock()
    monkeypatch.setattr("delivery.reasoning.decide_delivery", decide)
    result = await DeliveryService(world.db).evaluate("alice", opportunity.id)
    assert result.blocked_by == "departure_evidence_stale"
    decide.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_boundary_checks_again_after_ai_latency(world, monkeypatch):
    _, opportunity = await ready_opportunity(world)
    from delivery.models import DeliveryPlan
    from delivery.service import DeliveryService
    provider = SimpleNamespace(send=AsyncMock(return_value={"ok": True}), cancel=AsyncMock())
    monkeypatch.setattr("delivery.provider.get_provider", lambda: provider)
    world.presence.last_seen_at = (world.now - timedelta(minutes=5)).isoformat()
    plan = DeliveryPlan(owner_id="alice", source_id=opportunity.id, source_type="opportunity", mode="push")
    await DeliveryService(world.db)._send("alice", plan)
    assert plan.status == "cancelled"
    provider.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_position_with_new_fix_keeps_the_still_fresh_estimate(world):
    _, opportunity = await ready_opportunity(world)
    # A fresh observation of the same point is not a changed origin. It must
    # not make a valid card disappear while the delivery model is deciding.
    world.presence.last_seen_at = datetime.now(timezone.utc).isoformat()
    assert await world.svc.evidence_is_current("alice", opportunity)


@pytest.mark.asyncio
async def test_new_fix_does_not_extend_an_old_estimates_deadline(world, monkeypatch):
    evidence, opportunity = await ready_opportunity(world)
    later = world.now + timedelta(seconds=121)
    monkeypatch.setattr("places.departures._now", lambda: later)
    world.presence.last_seen_at = later.isoformat()
    assert not await world.svc.evidence_is_current("alice", opportunity)
    refreshed = (await world.svc.collect("alice", [world.event], now=later))[0]
    assert refreshed["ref"] != evidence["ref"] and world.routes.await_count == 4
    assert datetime.fromisoformat(refreshed["valid_until"]) > later


@pytest.mark.asyncio
async def test_cancellation_and_revocation_stop_wakes_and_clear_derived_cache(world):
    await world.svc.collect("alice", [world.event], now=world.now)
    await world.svc.collect("alice", [], now=world.now)
    assert await world.db.ambient_wakes.count_documents({"status": "pending"}) == 0
    await world.svc.collect("alice", [world.event], now=world.now)
    from location.service import LocationService
    await LocationService(world.db).set_preference("alice", "off")
    assert await world.db[COLLECTION].count_documents({"owner_id": "alice"}) == 0
    assert await world.svc.collect("alice", [world.event], now=world.now) == []
    assert await world.db.ambient_wakes.count_documents({"status": "pending"}) == 0


@pytest.mark.asyncio
async def test_ambiguous_destination_and_outage_do_not_invent_estimates(world, monkeypatch):
    world.resolve.return_value = SimpleNamespace(resolved=False, candidates=["one", "two"])
    search = AsyncMock()
    monkeypatch.setattr("places.public_search.preview_destination", search)
    result = (await world.svc.collect("alice", [world.event], now=world.now))[0]
    assert result["status"] == "destination_unresolved" and not result["options"]
    search.assert_not_awaited()
    world.routes.assert_not_awaited()
    world.resolve.return_value = SimpleNamespace(resolved=True, candidates=[],
        place=SimpleNamespace(coordinates=SimpleNamespace(latitude=41.92, longitude=12.51)))
    world.routes.side_effect = RuntimeError("unavailable")
    result = (await world.svc.collect("alice", [world.event], now=world.now + timedelta(seconds=61)))[0]
    assert result["status"] == "routing_unavailable" and not result["options"]


@pytest.mark.asyncio
async def test_all_day_no_location_and_other_owner_have_no_route(world):
    for event in ({**world.event, "all_day": True}, {**world.event, "location": ""}):
        assert await world.svc.collect("alice", [event], now=world.now) == []
    assert await world.svc.collect("bob", [world.event], now=world.now) == []
    world.routes.assert_not_awaited()


@pytest.mark.parametrize("field,value", [("accuracy_meters", 500), ("accuracy_meters", None),
    ("permission_state", "denied"), ("acquisition_error", "timeout"), ("source", "user_stated")])
def test_unusable_fix_is_not_an_origin(field, value):
    now = datetime.now(timezone.utc)
    presence = PresenceContext(user_id="a", preference="while_using", permission_state="granted_foreground",
        source="foreground_device", last_seen_at=now.isoformat(), latitude=41.9, longitude=12.5, accuracy_meters=10)
    setattr(presence, field, value)
    assert current_origin(presence, now) is None


@pytest.mark.asyncio
async def test_ai_selected_departure_uses_provider_times_and_one_identity(world, monkeypatch):
    from opportunities.service import OpportunityService
    evidence, _ = await ready_opportunity(world)
    state = {"departures": [evidence], "clock": {"timezone": "Europe/Rome"}}
    model = AsyncMock(return_value={"opportunities": [{"identity_key": "invented_key",
        "what": "Parti ora in auto", "why_it_matters": "Arrivo garantito",
        "evidence_refs": [evidence["ref"]]}]})
    monkeypatch.setattr("opportunities.reasoning.scan", model)
    result = await OpportunityService(world.db).scan("alice", prepared_snapshot=state)
    card = result.created[0]
    assert "garantito" not in card.why_it_matters and "Parti ora" not in card.semantic_summary
    assert "in auto" in card.semantic_summary and "a piedi" in card.semantic_summary
    assert card.valid_until == evidence["valid_until"] and card.initiative == "inform"
    model.return_value["opportunities"][0]["identity_key"] = "another_key"
    second = await OpportunityService(world.db).scan("alice", prepared_snapshot=state)
    assert not second.created and second.updated[0].id == card.id


@pytest.mark.asyncio
async def test_distant_event_arranges_bounded_recheck_without_routing(world):
    future = {**world.event, "starts_at": (world.now + timedelta(days=10)).isoformat()}
    assert await world.svc.collect("alice", [future], now=world.now) == []
    wake = await world.db.ambient_wakes.find_one({"owner_id": "alice", "source_ref": WAKE_SOURCE})
    assert datetime.fromisoformat(wake["scheduled_for"]) <= datetime.now(timezone.utc) + timedelta(hours=72)
    world.routes.assert_not_awaited()


@pytest.mark.asyncio
async def test_departure_http_surface_reads_only_the_authenticated_owners_calendar(world, monkeypatch):
    from places.router import calendar_departures
    monkeypatch.setattr("deps.db", world.db)
    alice = await calendar_departures(user={"user_id": "alice"})
    bob = await calendar_departures(user={"user_id": "bob"})
    assert alice["departures"][0]["event_ref"] == world.event["ref"]
    assert alice["departures"][0]["status"] == "ready"
    assert bob == {"departures": []}


@pytest.mark.asyncio
async def test_runtime_after_restart_recalculates_without_home_or_chat(world, monkeypatch):
    import mongomock.collection
    original = mongomock.collection.Collection.find_one_and_update
    def update(self, *args, **kwargs):
        kwargs.pop("projection", None)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(mongomock.collection.Collection, "find_one_and_update", update)
    from ambient.runtime import tick
    from ambient.service import AmbientService
    from opportunities.surfacing import SurfacingService
    from opportunities.repository import OpportunityRepository

    await world.svc.collect("alice", [world.event], now=world.now)
    await world.db.ambient_wakes.update_many({"status": "pending"},
        {"$set": {"scheduled_for": (world.now - timedelta(seconds=5)).isoformat()}})
    async def judge(snapshot, **kwargs):
        assert snapshot["departures"][0]["status"] == "ready"
        return {"opportunities": [{"identity_key": "departure_model", "what": "Controlla la partenza",
                 "why_it_matters": "Impegno imminente", "evidence_refs": [snapshot["departures"][0]["ref"]]}]}
    model = AsyncMock(side_effect=judge)
    monkeypatch.setattr("opportunities.reasoning.scan", model)
    monkeypatch.setattr(AmbientService, "_note", AsyncMock())
    monkeypatch.setattr(SurfacingService, "decide", AsyncMock())
    monkeypatch.setattr("delivery.admission.drain", AsyncMock())
    monkeypatch.setattr("agent.background.consider_opportunities", AsyncMock())
    # A new runtime instance uses persisted state, with no foreground request.
    outcome = await tick(world.db, limit=1)
    assert outcome["completed"] == 1
    model.assert_awaited_once()
    assert len(await OpportunityRepository(world.db).list("alice")) == 1
    pending = await world.db.ambient_wakes.find(
        {"owner_id": "alice", "status": "pending"}, {"_id": 0, "source_ref": 1}
    ).to_list(10)
    refs = {row.get("source_ref") for row in pending}
    # The restart re-arms both layers: a broad calendar horizon check and the
    # precise pre-departure check for this concrete event.
    assert WAKE_SOURCE in refs
    assert any(str(ref or "").startswith("calendar_departure_due:") for ref in refs)
    assert len(pending) == 2


@pytest.mark.asyncio
async def test_unreadable_calendar_keeps_its_due_review_retryable(world, monkeypatch):
    from ambient.models import AmbientWake
    from ambient.service import AmbientService
    from opportunities.discovery import DiscoveryResult
    from opportunities.models import ScanResult
    monkeypatch.setattr("opportunities.discovery.OpportunityDiscovery.review", AsyncMock(return_value=
        DiscoveryResult(ran=True, scan=ScanResult(silence=True, unavailable_sources=["calendar"]))))
    result = await AmbientService(world.db).review_life(AmbientWake(owner_id="alice",
        reason="ambient_review", source_ref=WAKE_SOURCE))
    assert result.retry_after_seconds and result.error == "departure_sources_unavailable"
