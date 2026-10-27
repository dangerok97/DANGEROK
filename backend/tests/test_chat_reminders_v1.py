"""«Ricordami alle 15 di…» from chat, WhatsApp or Siri: a reminder sent by code."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from memos import one_shot
from memos.caps import cancel_reminder, list_reminders, set_reminder

ROME = ZoneInfo("Europe/Rome")
NOW = datetime(2026, 10, 26, 10, 0, tzinfo=ROME)
OWNER = "usr_chat_rem_v1"


@pytest.fixture
def runtime(monkeypatch):
    import timezone_service

    async def clock(_db, _owner, *, now=None):
        return {"local_datetime": NOW.isoformat()}

    monkeypatch.setattr(timezone_service, "user_clock_context", clock)
    return {"db": AsyncMongoMockClient().chat_rem_v1, "user_id": OWNER, "session_id": "s1"}


@pytest.mark.asyncio
async def test_set_list_fire_and_never_twice(runtime):
    out = await set_reminder({"what": "Chiamare il dentista", "at_local": "2026-10-27T09:00"}, runtime)
    assert out.status == "ok" and out.payload["at_label"] == "mar 27 ott, 09:00"
    again = await set_reminder({"what": "Chiamare il dentista", "at_local": "2026-10-27T09:00"}, runtime)
    assert again.payload["status"] == "already_set"
    soon = await set_reminder({"what": "Il forno", "delay_minutes": 30}, runtime)
    assert soon.payload["at_label"].endswith("10:30")
    listed = await list_reminders({}, runtime)
    assert [r["what"] for r in listed.payload["reminders"]] == ["Il forno", "Chiamare il dentista"]
    db = runtime["db"]
    fired = await one_shot.fire_due(db, now=(NOW + timedelta(minutes=31)).astimezone(timezone.utc))
    assert fired["raised"] == 1
    opp = await db.opportunities.find_one({})
    assert opp["semantic_summary"] == "Il forno" and opp["decision_provenance"] == "user"


@pytest.mark.asyncio
async def test_no_time_past_time_and_cancel(runtime):
    assert (await set_reminder({"what": "Qualcosa"}, runtime)).payload["error"] == "when_missing"
    assert (await set_reminder({"what": "X", "at_local": "2026-10-26T09:00"}, runtime)).payload["error"] == "in_the_past"
    assert (await set_reminder({"what": "", "delay_minutes": 5}, runtime)).payload["error"] == "what_missing"
    made = await set_reminder({"what": "Spegnere il ferro", "delay_minutes": 10}, runtime)
    rid = made.payload["reminder_id"]
    assert (await cancel_reminder({"reminder_id": rid}, runtime)).payload["status"] == "cancelled"
    assert (await cancel_reminder({"reminder_id": rid}, runtime)).payload["error"] == "not_found_or_closed"
    other = {**runtime, "user_id": "someone_else"}
    made = await set_reminder({"what": "Mio", "delay_minutes": 10}, runtime)
    assert (await cancel_reminder({"reminder_id": made.payload["reminder_id"]}, other)).status == "error"


def test_tools_are_registered_for_every_channel():
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    for name in ("set_reminder", "list_reminders", "cancel_reminder"):
        assert registry.get(name) is not None


@pytest.mark.asyncio
async def test_a_told_reminder_leaves_home_after_half_a_day(runtime):
    db = runtime["db"]
    await set_reminder({"what": "Il forno", "delay_minutes": 5}, runtime)
    told = (NOW + timedelta(minutes=6)).astimezone(timezone.utc)
    await one_shot.fire_due(db, now=told)
    assert (await db.reminders.find_one({}))["status"] == "open"
    await one_shot.fire_due(db, now=told + timedelta(hours=13))
    assert (await db.reminders.find_one({}))["status"] == "past"


@pytest.mark.asyncio
async def test_done_and_later_on_an_arrived_reminder(runtime, monkeypatch):
    from opportunities.models import Opportunity

    db = runtime["db"]
    await set_reminder({"what": "Bere un bicchiere d'acqua", "delay_minutes": 1}, runtime)
    await one_shot.fire_due(db, now=(NOW + timedelta(minutes=2)).astimezone(timezone.utc))
    opp = await db.opportunities.find_one({}, {"_id": 0})
    public = Opportunity(**opp).for_home()
    assert public["reminder"] == {"kind": "reminder"}
    later = await one_shot.act(db, OWNER, opp["id"], "snooze", 10)
    assert later["ok"] and await db.reminders.count_documents({"status": "open"}) == 1
    assert (await db.opportunities.find_one({"id": opp["id"]}))["status"] != "active"
    assert (await one_shot.act(db, OWNER, opp["id"], "snooze", 7))["reason"] == "invalid_minutes"
    assert (await one_shot.act(db, "intruder", opp["id"], "done"))["ok"] is False
