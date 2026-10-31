"""
The daily canary: ORA tests its own autonomy in production, every morning.

Until now a broken reminder lane, a weather provider that changed its answer
or a routing key that expired was found by the owner, with a screenshot.
Once a day (first maintenance pass after 06:00 Rome, or right after the first
deploy) a synthetic account that no person owns walks the paths autonomy rests
on, with the real providers and the real lanes:

* reminder lane: a reminder due a minute ago becomes a pushable Opportunity;
* stuck reminders: nobody's reminder is overdue without having been raised;
* weather + drying: the hourly forecast arrives and the drying model answers;
* routing: a real drive time between two fixed points;
* leave notice: an appointment with a place gets its leave reminder;
* morning brief: the day page has the weather and the agenda;
* appointment net: a stated appointment is still understood.

Every synthetic row is removed at the end. The result is kept in
`canary_runs`; when something fails, the people listed in CANARY_ALERT_EMAILS
get one notification saying what, through the one-time reminder lane.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("ora.canary")

OWNER = "ora_canary"
ROME = ZoneInfo("Europe/Rome")
RUN_FROM_HOUR = 6
# Fixed points: Tarquinia (home) and Viterbo (appointment).
HOME = (42.2489, 11.7558)
AWAY = (42.4207, 12.1077)
STUCK_AFTER_MINUTES = 15
KEEP_RUNS = 30

WORDS = {
    "reminder_lane": "i promemoria non diventano notifiche",
    "stuck_reminders": "ci sono promemoria scaduti mai partiti",
    "weather": "il meteo orario non risponde",
    "routing": "il calcolo del percorso non risponde",
    "leave_notice": "l'avviso di partenza non si prepara",
    "morning_brief": "il punto del mattino è incompleto",
    "appointment_net": "gli appuntamenti scritti in chat non vengono capiti",
}


async def _clean(db) -> None:
    for name in ("reminders", "opportunities", "delivery_plans", "calendar_events", "life_places",
                 "situations", "users", "brief_runs", "ambient_wakes", "agent_goals"):
        for field in ("user_id", "owner_id"):
            try:
                await db[name].delete_many({field: OWNER})
            except Exception:
                pass


async def _reminder_lane(db, now: datetime) -> str:
    from memos import one_shot
    from opportunities.models import Opportunity

    rid = f"rem_canary_{int(now.timestamp())}"
    await db.reminders.insert_one({
        "id": rid, "user_id": OWNER, "title": "Controllo automatico", "status": "open",
        "due_at": (now - timedelta(minutes=1)).isoformat(), "origin": "chat_reminder",
        "created_at": now.isoformat(), "updated_at": now.isoformat(), "meta": {}})
    await one_shot.fire_due(db, now=now)
    row = await db.opportunities.find_one({"owner_id": OWNER, "source_context": one_shot.SOURCE_CONTEXT}, {"_id": 0})
    if not row:
        raise AssertionError("nessuna opportunità dal promemoria")
    decision = one_shot.push_decision(Opportunity(**row))
    if decision.get("mode") != "push":
        raise AssertionError(f"modo {decision.get('mode')}")
    return "promemoria → notifica push"


async def _stuck(db, now: datetime) -> str:
    rows = await db.reminders.find(
        {"user_id": {"$ne": OWNER}, "status": {"$in": ["open", "active", "pending"]},
         "notified_state": {"$exists": False},
         "due_at": {"$gte": (now - timedelta(days=2)).isoformat(),
                    "$lt": (now - timedelta(minutes=STUCK_AFTER_MINUTES)).isoformat()}},
        {"_id": 0, "id": 1, "due_at": 1}).to_list(20)
    stuck = []
    for r in rows:
        try:
            due = datetime.fromisoformat(str(r["due_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if due.tzinfo and now - due > timedelta(minutes=STUCK_AFTER_MINUTES):
            stuck.append(r["id"])
    if stuck:
        raise AssertionError(f"{len(stuck)} bloccati")
    return "nessuno bloccato"


async def _weather(db, now: datetime) -> str:
    from situations import outdoor_drying as od

    hours = await od._fetch_hours(HOME[0], HOME[1], now)
    if not hours:
        raise AssertionError("nessuna ora di previsione")
    r = od.compute(hours, start=now, now=now)
    if not isinstance(r, dict) or "dry_at" not in r:
        raise AssertionError("modello asciugatura senza risposta")
    return f"{len(hours)} ore"


async def _routing(db, now: datetime) -> str:
    from places import routing

    if not routing.capabilities().get("available"):
        raise AssertionError("routing non configurato")
    r = await routing.get_route(origin={"latitude": HOME[0], "longitude": HOME[1]},
                                destination={"latitude": AWAY[0], "longitude": AWAY[1]}, travel_mode="drive")
    d = r.get("duration_seconds") if isinstance(r, dict) else None
    if not r.get("available") or not isinstance(d, (int, float)) or not 600 < d < 7200:
        raise AssertionError(f"durata {d}")
    return f"{round(d / 60)} min"


async def _setup_world(db, now: datetime) -> None:
    from places.models import Coordinates, LifePlace
    from places.repository import PlacesRepository

    await db.users.update_one({"user_id": OWNER}, {"$set": {"user_id": OWNER, "name": "Controllo",
                                                            "timezone": "Europe/Rome"}}, upsert=True)
    await PlacesRepository(db).save_place(LifePlace(
        user_id=OWNER, label="Casa", role="home", role_confirmed_by_user=True, source="user_stated",
        coordinates=Coordinates(latitude=HOME[0], longitude=HOME[1], precision="exact"),
        locality="Tarquinia", location_source="map_selection"))
    start = now + timedelta(hours=3)
    await db.calendar_events.insert_one({
        "id": "evt_canary", "user_id": OWNER, "title": "Controllo", "status": "confirmed",
        "start_at": start.isoformat(), "end_at": (start + timedelta(hours=1)).isoformat(),
        "all_day": False, "location": "Viterbo"})


async def _leave(db, now: datetime) -> str:
    from places.leave_notice import plan_owner

    rows = await plan_owner(db, OWNER, now=now)
    row = next((r for r in rows if r.get("event") == "Controllo"), None)
    if not row or row.get("status") != "planned":
        raise AssertionError(f"stato {row.get('status') if row else 'nessun evento'}")
    return f"parti {row['minutes']} min prima + margine"


async def _brief(db, now: datetime) -> str:
    from brief.morning import full

    out = await full(db, OWNER, now.astimezone(ROME))
    keys = [s["key"] for s in out["sections"]]
    if "weather" not in keys or "today" not in keys:
        raise AssertionError(f"sezioni {keys}")
    if not out["headline"]:
        raise AssertionError("notifica vuota")
    return ", ".join(keys)


async def _net(db, now: datetime) -> str:
    from conversation_engine.ai_core.appointment_net import parse

    local = now.astimezone(ROME).replace(hour=8, minute=0)
    found = parse("Domani alle 15 ho l'appuntamento dal parrucchiere a Montalto di Castro", now=local)
    if not found or found["start"].hour != 15 or "Montalto" not in found["location"]:
        raise AssertionError(str(found))
    return found["title"]


CHECKS: List[tuple[str, Callable[[Any, datetime], Awaitable[str]]]] = [
    ("reminder_lane", _reminder_lane), ("stuck_reminders", _stuck), ("weather", _weather),
    ("routing", _routing), ("leave_notice", _leave), ("morning_brief", _brief), ("appointment_net", _net),
]


async def run_once(db, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    results = []
    await _clean(db)
    try:
        await _setup_world(db, now)
    except Exception as exc:
        results.append({"name": "setup", "ok": False, "detail": type(exc).__name__})
    for name, fn in CHECKS:
        t0 = time.monotonic()
        try:
            detail = await fn(db, now)
            ok = True
        except Exception as exc:
            detail, ok = f"{type(exc).__name__}: {str(exc)[:160]}", False
        results.append({"name": name, "ok": ok, "detail": str(detail)[:200],
                        "ms": round((time.monotonic() - t0) * 1000)})
    await _clean(db)
    return {"at": now.isoformat(), "ok": all(r["ok"] for r in results), "checks": results}


async def _alert(db, report: Dict[str, Any], now: datetime) -> int:
    emails = [e.strip().lower() for e in os.environ.get("CANARY_ALERT_EMAILS", "").split(",") if e.strip()]
    if not emails:
        return 0
    failed = [WORDS.get(c["name"], c["name"]) for c in report["checks"] if not c["ok"]]
    text = ("Controllo automatico di ORA: " + "; ".join(failed) + ". Il resto funziona.")[:280]
    sent = 0
    async for u in db.users.find({"email": {"$in": emails}}, {"_id": 0, "user_id": 1}):
        rid = f"rem_canary_alert_{u['user_id']}_{now.astimezone(ROME).date().isoformat()}"[:90]
        await db.reminders.update_one({"id": rid}, {"$setOnInsert": {
            "id": rid, "user_id": u["user_id"], "title": text, "status": "open", "due_at": now.isoformat(),
            "origin": "canary", "created_at": now.isoformat(), "updated_at": now.isoformat(),
            "meta": {"kind": "canary"}}}, upsert=True)
        sent += 1
    return sent


async def run_due(db, *, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Once a day, after 06:00 Rome — or at once if it has never run."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ROME)
    ever = await db.canary_runs.find_one({}, {"_id": 1})
    if ever and local.hour < RUN_FROM_HOUR:
        return None
    key = local.date().isoformat()
    claimed = await db.canary_runs.update_one({"_id": key}, {"$setOnInsert": {"started_at": now.isoformat()}},
                                              upsert=True)
    if not claimed.upserted_id:
        return None
    report = await run_once(db, now=now)
    report["alerted"] = 0 if report["ok"] else await _alert(db, report, now)
    await db.canary_runs.update_one({"_id": key}, {"$set": report})
    old = await db.canary_runs.find({}, {"_id": 1}).sort("_id", -1).skip(KEEP_RUNS).to_list(100)
    if old:
        await db.canary_runs.delete_many({"_id": {"$in": [d["_id"] for d in old]}})
    (logger.info if report["ok"] else logger.warning)(
        "canary %s %s", "ok" if report["ok"] else "FAILED",
        {c["name"]: (c["ok"], c["detail"][:60]) for c in report["checks"]})
    return report


async def latest(db, limit: int = 7) -> List[Dict[str, Any]]:
    return await db.canary_runs.find({}, {"started_at": 0}).sort("_id", -1).to_list(limit)
