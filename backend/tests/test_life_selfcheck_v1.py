"""Reminders that remind, and appointments that somebody looks at."""
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from memos import one_shot
from ops import selfcheck

OWNER = "usr_life_selfcheck"


def _db():
    return AsyncMongoMockClient().life_selfcheck_v1


async def _opps(db):
    return await db.opportunities.find({"owner_id": OWNER}, {"_id": 0}).to_list(20)


@pytest.mark.asyncio
async def test_a_due_reminder_becomes_one_user_decided_opportunity():
    db = _db()
    now = datetime.now(timezone.utc)
    await db.reminders.insert_many([
        {"id": "rem_now", "user_id": OWNER, "title": "Promemoria evento: Dentista", "status": "open",
         "due_at": (now - timedelta(minutes=2)).isoformat()},
        {"id": "rem_later", "user_id": OWNER, "title": "Più tardi", "status": "open",
         "due_at": (now + timedelta(hours=2)).isoformat()},
        {"id": "rem_done", "user_id": OWNER, "title": "Già fatto", "status": "done",
         "due_at": (now - timedelta(minutes=2)).isoformat()},
    ])
    out = await one_shot.fire_due(db, now=now)
    assert out["raised"] == 1
    opps = await _opps(db)
    assert len(opps) == 1
    opp = opps[0]
    assert opp["identity_key"] == "one_shot_reminder:rem_now"
    assert opp["decision_provenance"] == "user" and "Dentista" in opp["semantic_summary"]
    # Never twice.
    again = await one_shot.fire_due(db, now=now + timedelta(minutes=1))
    assert again["raised"] == 0 and len(await _opps(db)) == 1
    later = await db.reminders.find_one({"id": "rem_later"})
    assert "notified_state" not in later


@pytest.mark.asyncio
async def test_a_reminder_long_past_is_missed_not_announced_late():
    db = _db()
    now = datetime.now(timezone.utc)
    await db.reminders.insert_one({"id": "rem_old", "user_id": OWNER, "title": "Vecchio", "status": "open",
                                   "due_at": (now - timedelta(days=3)).isoformat()})
    out = await one_shot.fire_due(db, now=now)
    assert out == {"due": 1, "raised": 0, "missed": 1}
    assert not await _opps(db)
    assert (await db.reminders.find_one({"id": "rem_old"}))["notified_state"] == "missed"


@pytest.mark.asyncio
async def test_delivery_rechecks_that_the_reminder_is_still_open():
    from opportunities.models import Opportunity

    db = _db()
    now = datetime.now(timezone.utc)
    await db.reminders.insert_one({"id": "rem_x", "user_id": OWNER, "title": "X", "status": "open",
                                   "due_at": now.isoformat()})
    await one_shot.fire_due(db, now=now + timedelta(seconds=1))
    opp = Opportunity(**{k: v for k, v in (await _opps(db))[0].items()})
    assert await one_shot.reminder_opportunity_current(db, opp) is True
    await db.reminders.update_one({"id": "rem_x"}, {"$set": {"status": "done"}})
    assert await one_shot.reminder_opportunity_current(db, opp) is False
    # Anything else is not this guard's business.
    other = opp.model_copy(update={"source_context": "recurring_memo"})
    assert await one_shot.reminder_opportunity_current(db, other) is True


def test_delivery_and_runtime_use_the_guard_and_the_lane():
    import inspect
    from ambient import runtime
    from delivery import service

    assert "one_shot" in inspect.getsource(runtime._serve_recurring_memos)
    assert inspect.getsource(service).count("reminder_opportunity_current") >= 2


@pytest.mark.asyncio
async def test_an_unwatched_appointment_gets_one_review_an_hour_before(monkeypatch):
    import opportunities.snapshot as snapshot

    db = _db()
    await db.ambient_wakes.create_index("identity", unique=True)
    now = datetime.now(timezone.utc)
    events = [
        {"ref": "calendar:ev_call", "title": "Chiamata commercialista",
         "starts_at": (now + timedelta(hours=2)).isoformat(), "all_day": False},
        {"ref": "calendar:ev_far", "title": "Domani", "starts_at": (now + timedelta(hours=20)).isoformat(),
         "all_day": False},
        {"ref": "calendar:ev_day", "title": "Tutto il giorno", "starts_at": (now + timedelta(hours=1)).isoformat(),
         "all_day": True},
        {"ref": "calendar:ev_now", "title": "Tra poco", "starts_at": (now + timedelta(minutes=5)).isoformat(),
         "all_day": False},
    ]

    async def calendar(_db, _owner, _now):
        return events

    monkeypatch.setattr(snapshot, "_calendar", calendar)
    report = await selfcheck.check_owner(db, OWNER, now=now)
    found = [f for f in report["findings"] if f["code"] == "event_unattended"]
    assert [f["ref"] for f in found] == ["event:calendar:ev_call"] and found[0]["repaired"]
    wake = await db.ambient_wakes.find_one({"source_ref": "calendar_event_due:calendar:ev_call"})
    due = datetime.fromisoformat(wake["scheduled_for"])
    assert abs((due - (now + timedelta(hours=1))).total_seconds()) < 5
    assert wake["reason"] == "ambient_review"
    # Second pass: already watched.
    again = await selfcheck.check_owner(db, OWNER, now=now)
    assert not [f for f in again["findings"] if f["code"] == "event_unattended"]


@pytest.mark.asyncio
async def test_an_appointment_with_a_departure_alarm_is_left_alone(monkeypatch):
    import opportunities.snapshot as snapshot

    db = _db()
    now = datetime.now(timezone.utc)
    await db.ambient_wakes.insert_one({"id": "w1", "owner_id": OWNER, "status": "pending",
                                       "source_ref": "calendar_departure_due:calendar:ev_go"})

    async def calendar(_db, _owner, _now):
        return [{"ref": "calendar:ev_go", "title": "Visita", "all_day": False,
                 "starts_at": (now + timedelta(hours=2)).isoformat()}]

    monkeypatch.setattr(snapshot, "_calendar", calendar)
    report = await selfcheck.check_owner(db, OWNER, now=now)
    assert not [f for f in report["findings"] if f["code"] == "event_unattended"]


async def _due_reminder(db, now):
    from opportunities.repository import OpportunityRepository

    await OpportunityRepository(db).ensure_indexes()
    await db.reminders.insert_one({"id": "rem_push", "user_id": OWNER, "status": "open",
                                   "title": "Promemoria evento: Visita",
                                   "due_at": (now - timedelta(minutes=1)).isoformat()})
    assert (await one_shot.fire_due(db, now=now))["raised"] == 1


@pytest.mark.asyncio
async def test_a_due_reminder_reaches_the_phone_without_asking_a_model(monkeypatch):
    from ambient.push import PushEndpointService
    from delivery.admission import drain
    from test_recurring_memo_delivery_v131 import TOKEN, install_scripted_gate

    db = AsyncMongoMockClient().one_shot_push_v1
    await _due_reminder(db, datetime.now(timezone.utc))
    await PushEndpointService(db).register(OWNER, token=TOKEN, device="synthetic-ios",
                                           platform="ios", permission_state="granted")
    _, judgement, outbound = install_scripted_gate(monkeypatch, db)
    assert await drain(db, owner_id=OWNER, limit=2) == 1
    judgement.assert_not_awaited()
    outbound.assert_awaited_once()
    request = outbound.await_args.args[0][0]
    assert request["to"] == TOKEN and request["title"] == "Promemoria"
    # Lock screen stays discreet: the title of the reminder is not on it.
    assert "Visita" not in request["body"]
    assert (await db.delivery_plans.find_one({"owner_id": OWNER}))["status"] == "delivered"


@pytest.mark.asyncio
async def test_a_reminder_completed_before_sending_never_arrives(monkeypatch):
    from ambient.push import PushEndpointService
    from delivery.admission import drain
    from test_recurring_memo_delivery_v131 import TOKEN, install_scripted_gate

    db = AsyncMongoMockClient().one_shot_done_v1
    await _due_reminder(db, datetime.now(timezone.utc))
    await PushEndpointService(db).register(OWNER, token=TOKEN, device="synthetic-ios")
    _, judgement, outbound = install_scripted_gate(monkeypatch, db)
    await db.reminders.update_one({"id": "rem_push"}, {"$set": {"status": "done"}})
    assert await drain(db, owner_id=OWNER, limit=1) == 1
    outbound.assert_not_awaited() 
    judgement.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_reminder_the_person_asked_for_is_not_throttled(monkeypatch):
    from ambient.push import PushEndpointService
    from delivery.admission import drain
    from test_recurring_memo_delivery_v131 import TOKEN, install_scripted_gate

    db = AsyncMongoMockClient().one_shot_throttle_v1
    await _due_reminder(db, datetime.now(timezone.utc))
    await PushEndpointService(db).register(OWNER, token=TOKEN, device="synthetic-ios",
                                           platform="ios", permission_state="granted")
    context, _, outbound = install_scripted_gate(monkeypatch, db)
    context.return_value = {**context.return_value,
                            "recent_interruptions": [{"minutes_ago": 2}, {"minutes_ago": 30}]}
    assert await drain(db, owner_id=OWNER, limit=2) == 1
    outbound.assert_awaited_once()


@pytest.mark.asyncio
async def test_uninvited_pushes_keep_the_ceiling():
    from delivery.service import DeliveryService

    moment = {"can_be_notified": {"push": True}, "recent_interruptions": [{"minutes_ago": 2}]}
    assert await DeliveryService(_db())._may_push(OWNER, moment) == (False, "too_soon_after_last")
    assert await DeliveryService(_db())._may_push(OWNER, moment, invited=True) == (True, "")
    denied = {"can_be_notified": {"push": False}}
    assert (await DeliveryService(_db())._may_push(OWNER, denied, invited=True))[0] is False
