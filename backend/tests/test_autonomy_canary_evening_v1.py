"""Daily canary, evening-before notice, and «what I did on my own»."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from mongomock_motor import AsyncMongoMockClient

from brief import evening, morning
from ops import canary

ROME = ZoneInfo("Europe/Rome")
OWNER = "usr_evening_v1"


def test_evening_says_tomorrow_only_when_there_is_something():
    assert evening.compose([], [], "Pioggia 70%: serve l'ombrello") == ""
    text = evening.compose(["9:00 Medico (Viterbo), parti verso le 8:15 da casa (35 min in auto)"], ["F24"],
                           "Pioggia 70%: serve l'ombrello")
    assert text == ("Domani: 9:00 Medico (Viterbo), parti verso le 8:15 da casa (35 min in auto). "
                    "Scade domani: F24. Pioggia 70%: serve l'ombrello.")
    assert evening.compose([], ["Bollo auto"], "").startswith("Domani scade: Bollo auto.")


@pytest.mark.asyncio
async def test_evening_fires_once_at_its_hour(monkeypatch):
    import timezone_service
    clock = {"now": datetime(2026, 10, 31, 20, 35, tzinfo=ROME)}

    async def user_clock(_db, _owner, *, now=None):
        return {"local_datetime": clock["now"].isoformat()}

    async def tomorrow(db, owner, local_now):
        return {"events": ["9:00 Medico"], "deadlines": []}

    async def no_rain(db, owner):
        return ""

    monkeypatch.setattr(timezone_service, "user_clock_context", user_clock)
    monkeypatch.setattr(evening, "_tomorrow", tomorrow)
    monkeypatch.setattr(evening, "_rain_tomorrow", no_rain)
    db = AsyncMongoMockClient().evening_v1
    await db.push_endpoints.insert_one({"owner_id": OWNER, "status": "active"})
    await db.users.insert_one({"user_id": OWNER})
    assert (await evening.fire_due(db))["queued"] == 1
    assert (await evening.fire_due(db))["queued"] == 0
    row = await db.reminders.find_one({"origin": "evening_brief"})
    assert row["title"] == "Domani: 9:00 Medico."
    clock["now"] = datetime(2026, 11, 1, 19, 0, tzinfo=ROME)
    assert (await evening.fire_due(db))["checked"] == 0  # before its hour
    await evening.set_preference(db, OWNER, hour=18)
    assert (await evening.preference(db, OWNER)) == {"enabled": True, "hour": 18}
    assert (await evening.fire_due(db))["queued"] == 1

    from memos import one_shot
    from opportunities.models import Opportunity
    await one_shot.fire_due(db)
    opp = await db.opportunities.find_one({})
    o = Opportunity(**{k: v for k, v in opp.items() if k != "_id"})
    assert o.for_home()["reminder"] == {"kind": "evening_brief"}
    assert one_shot.push_decision(o)["copy"]["title"] == "Domani"


@pytest.mark.asyncio
async def test_what_ora_did_on_its_own():
    db = AsyncMongoMockClient().done_alone_v1
    now = datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc)
    for _ in range(3):  # the same repair seen by three passes counts once
        await db.ops_self_checks.insert_one({"owner_id": OWNER, "at": (now - timedelta(hours=2)).isoformat(),
                                             "findings": [{"code": "situation_auto_closed", "ref": "sit:1", "repaired": True},
                                                          {"code": "leave_planned", "ref": "e1", "repaired": True},
                                                          {"code": "leave_planned", "ref": "e2", "repaired": True},
                                                          {"code": "no_device_for_notifications", "repaired": False}]})
    await db.reminders.insert_many([
        {"user_id": OWNER, "origin": "situation_stated_time", "notified_state": "raised",
         "notified_at": (now - timedelta(hours=5)).isoformat()},
        {"user_id": OWNER, "origin": "situation_stated_time", "notified_state": "raised",
         "notified_at": (now - timedelta(hours=30)).isoformat()},
    ])
    done = await morning._done_alone(db, OWNER, now)
    assert "Ho chiuso 1 cosa già finita" in done
    assert "Ho calcolato quando partire per 2 appuntamenti" in done
    assert "Ti ho mandato 1 avviso su una cosa che seguivo" in done


@pytest.mark.asyncio
async def test_canary_runs_once_a_day_cleans_up_and_alerts(monkeypatch):
    db = AsyncMongoMockClient().canary_v1
    calls = []

    async def good(db_, now):
        calls.append("good")
        await db_.reminders.insert_one({"user_id": canary.OWNER, "id": "x"})
        return "ok"

    async def bad(db_, now):
        raise AssertionError("durata None")

    async def setup(db_, now):
        return None

    monkeypatch.setattr(canary, "_setup_world", setup)
    monkeypatch.setattr(canary, "CHECKS", [("reminder_lane", good), ("routing", bad)])
    monkeypatch.setenv("CANARY_ALERT_EMAILS", "owner@example.com")
    await db.users.insert_one({"user_id": "usr_owner", "email": "owner@example.com"})
    now = datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc)  # 02:00 Rome, never ran: runs at once
    report = await canary.run_due(db, now=now)
    assert report and not report["ok"] and report["alerted"] == 1
    assert await canary.run_due(db, now=now + timedelta(hours=1)) is None  # once a day
    assert await db.reminders.count_documents({"user_id": canary.OWNER}) == 0  # synthetic rows removed
    alert = await db.reminders.find_one({"user_id": "usr_owner"})
    assert alert["origin"] == "canary" and "percorso" in alert["title"]
    # Next day, before 06:00 Rome: waits.
    assert await canary.run_due(db, now=datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)) is None
    assert (await canary.run_due(db, now=datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)))["checks"][0]["ok"]


@pytest.mark.asyncio
async def test_canary_stuck_reminders_check():
    db = AsyncMongoMockClient().canary_stuck_v1
    now = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
    assert await canary._stuck(db, now) == "nessuno bloccato"
    await db.reminders.insert_one({"id": "r1", "user_id": "u", "status": "open",
                                   "due_at": (now - timedelta(minutes=40)).isoformat()})
    with pytest.raises(AssertionError):
        await canary._stuck(db, now)


def test_canary_appointment_net_check():
    import asyncio
    assert asyncio.run(canary._net(None, datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc))) == "Parrucchiere"


@pytest.mark.asyncio
async def test_bills_read_from_mail_are_deadlines():
    from opportunities.deadlines import upcoming
    db = AsyncMongoMockClient().bills_v1
    now = datetime(2026, 11, 1, 9, 0, tzinfo=ROME)
    base = {"owner_id": OWNER, "status": "known", "kind": "commitment", "direction": "outgoing"}
    await db.financial_facts.insert_many([
        {**base, "id": "f1", "what": "Bolletta della luce", "due_at": "2026-11-03", "money": {"amount": 84.5, "currency": "EUR"}},
        {**base, "id": "f2", "what": "Bolletta della luce", "due_at": "2026-11-03", "money": {"amount": 84.5, "currency": "EUR"}},
        {**base, "id": "f3", "what": "Affitto", "due_at": "2026-12-20"},                       # too far
        {**base, "id": "f4", "what": "Stipendio", "due_at": "2026-11-02", "direction": "incoming"},
        {**base, "id": "f5", "what": "Vecchia", "due_at": "2026-11-02", "status": "superseded"},
    ])
    rows = await upcoming(db, OWNER, now)
    assert [(r["title"], r["kind"]) for r in rows] == [("Bolletta della luce (€84,50)", "bill")]
