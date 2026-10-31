"""
The morning brief: the day in one notification, written by code.

ORA knew today's appointments, the deadlines, the reminders and the weather
of the person's home, and said none of it together. At the person's chosen
hour (08:00 unless changed) one notification sums the day up:

    Sereno, 11–20 °C, niente pioggia. Oggi: 10:30 Dentista. Scadenze: F24:
    scade domani. Bucato: se stendi alle 9, è asciutto verso le 14.

Opening it shows the whole day (brief/router GET /brief/morning/today, built
live): the weather today and tomorrow, the agenda with the leave times, the
reminders, the week's deadlines, what ORA is following, tomorrow.

Built only from stored facts and the hourly forecast, no model: it arrives
even when the model is out of quota. Nothing to say means no notification.
It travels through the one-time reminder lane, once a day at most, and can be
switched off in Settings.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.brief")

DEFAULT_HOUR = 8
# A brief later than this after its hour is no longer a morning brief.
LATE_HOURS = 3
MAX_CHARS = 280
ORIGIN = "morning_brief"


async def preference(db, owner: str) -> Dict[str, Any]:
    row = await db.users.find_one({"user_id": owner}, {"_id": 0, "preferences.morning_brief": 1})
    pref = ((row or {}).get("preferences") or {}).get("morning_brief") or {}
    hour = pref.get("hour", DEFAULT_HOUR)
    try:
        hour = max(5, min(11, int(hour)))
    except (TypeError, ValueError):
        hour = DEFAULT_HOUR
    return {"enabled": pref.get("enabled", True) is not False, "hour": hour}


async def set_preference(db, owner: str, *, enabled: Optional[bool] = None, hour: Optional[int] = None) -> Dict[str, Any]:
    current = await preference(db, owner)
    if enabled is not None:
        current["enabled"] = bool(enabled)
    if hour is not None:
        current["hour"] = max(5, min(11, int(hour)))
    await db.users.update_one({"user_id": owner}, {"$set": {"preferences.morning_brief": current}})
    return current


def _hhmm(value: Any, tz) -> str:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (moment if moment.tzinfo else moment.replace(tzinfo=tz)).astimezone(tz).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


_GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
_MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
         "settembre", "ottobre", "novembre", "dicembre")


def day_label(d) -> str:
    """«Sabato 31 ottobre»."""
    return f"{_GIORNI[d.weekday()].capitalize()} {d.day} {_MESI[d.month - 1]}"


def clock(moment: datetime) -> str:
    """«le 14», «le 14:30»: a person says the hour, not 14:01."""
    q = round((moment.hour * 60 + moment.minute) / 15) * 15
    h, m = divmod(q % (24 * 60), 60)
    return f"{h}" if m == 0 else f"{h}:{m:02d}"


def _when_days(days: int) -> str:
    return "oggi" if days == 0 else "domani" if days == 1 else f"tra {days} giorni"


async def _agenda(db, owner: str, local_now: datetime) -> Dict[str, List[str]]:
    """Today's and tomorrow's appointments, with the leave time where ORA computed one."""
    from opportunities.snapshot import _calendar

    leaves: Dict[str, str] = {}
    try:
        rows = await db.reminders.find(
            {"user_id": owner, "origin": "leave_notice", "status": "open"}, {"_id": 0, "due_at": 1, "meta": 1}
        ).to_list(20)
        for r in rows:
            ref = (r.get("meta") or {}).get("event_ref")
            if ref:
                leaves[str(ref)] = _hhmm(r.get("due_at"), local_now.tzinfo)
    except Exception:
        pass
    out: Dict[str, List[str]] = {"today": [], "tomorrow": []}
    for e in await _calendar(db, owner, local_now):
        day = {0: "today", 1: "tomorrow"}.get(e.get("in_days"))
        if day is None:
            continue
        title = " ".join(str(e.get("title") or "Appuntamento").split())[:60]
        at = "" if e.get("all_day") else _hhmm(e.get("starts_at"), local_now.tzinfo)
        line = f"{at} · {title}" if at else f"Tutto il giorno · {title}"
        place = " ".join(str(e.get("location") or "").split())[:50]
        if place:
            line += f" ({place})"
        if day == "today" and leaves.get(str(e.get("ref"))):
            line += f" — parti alle {leaves[str(e.get('ref'))]}"
        out[day].append(line)
    return {k: v[:5] for k, v in out.items()}


async def _appointments(db, owner: str, local_now: datetime) -> List[str]:
    return (await _agenda(db, owner, local_now))["today"]


async def _deadlines(db, owner: str, local_now: datetime) -> List[str]:
    """Open deadlines of the coming week, said as people say them."""
    from opportunities.deadlines import as_facts, upcoming

    facts = as_facts(await upcoming(db, owner, local_now, days=7), local_now)
    out = []
    for f in sorted(facts, key=lambda f: (not f.get("overdue"), f.get("days_left", 99))):
        title = " ".join(str(f.get("title") or "").split())[:60]
        out.append(f"{title}: scaduta" if f.get("overdue") else f"{title}: scade {_when_days(int(f.get('days_left') or 0))}")
    return out[:4]


async def _watching(db, owner: str) -> List[str]:
    """What ORA is following right now, in the person's words."""
    try:
        rows = await db.situations.find(
            {"user_id": owner, "status": {"$in": ["active", "changed"]}},
            {"_id": 0, "summary": 1, "tracking_summary": 1, "next_check_summary": 1},
        ).sort("updated_at", -1).to_list(3)
    except Exception:
        return []
    out = []
    for r in rows:
        text = " ".join(str(r.get("tracking_summary") or r.get("summary") or "").split())[:90]
        if text:
            nxt = " ".join(str(r.get("next_check_summary") or "").split())[:60]
            out.append(f"{text} — {nxt}" if nxt else text)
    return out


async def _reminders(db, owner: str, local_now: datetime) -> List[str]:
    end = datetime.combine(local_now.date() + timedelta(days=1), time(0), tzinfo=local_now.tzinfo)
    rows = await db.reminders.find(
        {"user_id": owner, "status": {"$in": ["open", "active", "pending"]},
         "notified_state": {"$exists": False}, "origin": {"$nin": [ORIGIN, "phone_call_result", "evening_brief", "canary", "leave_notice"]},
         "due_at": {"$gte": local_now.astimezone(timezone.utc).isoformat(),
                    "$lt": end.astimezone(timezone.utc).isoformat()}},
        {"_id": 0, "title": 1, "due_at": 1}).sort("due_at", 1).to_list(5)
    return [f"{' '.join(str(r.get('title') or '').split())[:35]} alle {_hhmm(r.get('due_at'), local_now.tzinfo)}"
            for r in rows][:3]


async def _weather(db, owner: str, local_now: datetime) -> Optional[Dict[str, Any]]:
    """Today and tomorrow at home, and whether a load hung out this morning dries today."""
    try:
        point = await _where(db, owner)
        if point is None:
            return None
        lat, lon, label = point
        import weather as weather_service
        data = await weather_service.forecast_at(lat=lat, lon=lon, place=label)
        if not data.get("available"):
            return None
        days = data.get("days") or [{}]
        today, tomorrow = days[0], (days[1] if len(days) > 1 else {})
        out: Dict[str, Any] = {"place": (label or "")[:40], "today": today, "tomorrow": tomorrow,
                               "sunset": data.get("sunset") or "", "drying": None}
        from situations import outdoor_drying as od
        from situations.calibration import factor
        hang = local_now.replace(hour=9, minute=0, second=0, microsecond=0)
        if local_now > hang:
            q = (local_now.minute // 15 + 1) * 15
            hang = local_now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=q)
        hours = await od._fetch_hours(lat, lon, hang)
        if hours:
            units = od.LOAD_UNITS * await factor(db, owner, "drying")
            r = od.compute(hours, start=hang.astimezone(timezone.utc), now=hang.astimezone(timezone.utc), units=units)
            dry, dusk, rain = r.get("dry_at"), r.get("dusk_at"), r.get("rain_at")
            tz = local_now.tzinfo
            if rain is not None:
                out["drying"] = {"good": False, "text": f"Bucato: meglio non stendere fuori, pioggia verso le {clock(rain.astimezone(tz))}."}
            elif dry and (dusk is None or dry <= dusk + timedelta(minutes=30)):
                out["drying"] = {"good": True, "text": (f"Buona giornata per il bucato: se stendi alle {clock(hang)}, "
                                                        f"è asciutto verso le {clock(dry.astimezone(tz))}.")}
            else:
                out["drying"] = {"good": False, "text": "Bucato: oggi fuori non si asciuga prima di sera."}
        return out
    except Exception as exc:
        logger.info("brief weather skipped: %s", type(exc).__name__)
        return None


def weather_line(w: Optional[Dict[str, Any]], key: str = "today") -> str:
    """«Sereno, 11–20 °C, niente pioggia»."""
    if not w:
        return ""
    d = w.get(key) or {}
    bits = []
    if d.get("condition_label"):
        bits.append(str(d["condition_label"]))
    if d.get("min_c") is not None and d.get("max_c") is not None:
        bits.append(f"{d['min_c']}–{d['max_c']} °C")
    rain = d.get("rain_chance_pct")
    if rain is not None:
        bits.append("niente pioggia" if rain < 15 else f"pioggia {rain}%")
    return ", ".join(bits)


async def _home_weather(db, owner: str, local_now: datetime) -> str:
    w = await _weather(db, owner, local_now)
    line = weather_line(w)
    return (f"{w['place']}: {line}" if w and w.get("place") else line) if line else ""


async def _where(db, owner: str):
    """
    Where the day's weather is read: the confirmed home; else the place where
    things were last hung out to dry (30/10: no home saved, so the first brief
    had nothing to say); else where the person is now, if location is on.
    """
    from places.service import PlacesService

    places = PlacesService(db)
    for p in await places.list_places(owner):
        if p.role == "home" and p.coordinates is not None and p.state == "confirmed":
            return p.coordinates.latitude, p.coordinates.longitude, p.locality or p.label
    last = await db.reminders.find_one(
        {"user_id": owner, "meta.kind": "drying_end"}, {"_id": 0, "meta": 1}, sort=[("updated_at", -1)])
    meta = (last or {}).get("meta") or {}
    if meta.get("place_ref"):
        p = await places.get_place(owner, str(meta["place_ref"]).split(":", 1)[-1])
        if p and p.coordinates is not None:
            return p.coordinates.latitude, p.coordinates.longitude, p.locality or p.label
    if meta.get("point"):
        sit = await db.situations.find_one({"user_id": owner, "id": meta.get("situation_id")},
                                           {"_id": 0, "location_label": 1})
        return float(meta["point"][0]), float(meta["point"][1]), (sit or {}).get("location_label") or ""
    try:
        from home.service import HomeService
        here = await HomeService(db)._where_they_are(owner)
        if here:
            return here
    except Exception:
        pass
    return None


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


_DONE = {
    "leave_planned": lambda n: f"Ho calcolato quando partire per {_n(n, 'appuntamento', 'appuntamenti')}",
    "drying_planned": lambda n: "Ho fatto il calcolo dal meteo per il bucato steso",
    "drying_replanned": lambda n: "Ho ricalcolato col meteo aggiornato quando si asciuga il bucato",
    "situation_auto_closed": lambda n: f"Ho chiuso {_n(n, 'cosa già finita', 'cose già finite')}",
    "watch_without_alarm": lambda n: f"Ho rimesso in moto {_n(n, 'controllo fermo', 'controlli fermi')}",
    "watch_overdue": lambda n: f"Ho recuperato {_n(n, 'controllo in ritardo', 'controlli in ritardo')}",
    "event_unattended": lambda n: f"Ho messo sotto controllo {_n(n, 'appuntamento', 'appuntamenti')} vicino",
    "deadline_unattended": lambda n: f"Ho programmato il controllo di {_n(n, 'scadenza', 'scadenze')}",
    "need_retired": lambda n: f"Ho tolto da Home {_n(n, 'richiesta non più attuale', 'richieste non più attuali')}",
    "habit_proposed": lambda n: "Ho notato un promemoria che chiedi spesso",
}
_SAID = {
    "situation_stated_time": ("avviso su una cosa che seguivo", "avvisi su cose che seguivo"),
    "leave_notice": ("avviso di partenza", "avvisi di partenza"),
    "chat_reminder": ("promemoria che mi avevi chiesto", "promemoria che mi avevi chiesto"),
}


async def _done_alone(db, owner: str, now_utc: datetime) -> List[str]:
    """What ORA did on its own in the last 24 hours, without being asked at that moment."""
    since = (now_utc - timedelta(hours=24)).isoformat()
    out: List[str] = []
    try:
        seen: Dict[str, set] = {}
        async for r in db.ops_self_checks.find({"owner_id": owner, "at": {"$gte": since}}, {"_id": 0, "findings": 1}):
            for f in r.get("findings") or []:
                if f.get("repaired") and f.get("code") in _DONE:
                    seen.setdefault(f["code"], set()).add(str(f.get("ref") or len(seen.get(f["code"], ()))))
        out += [_DONE[code](len(refs)) for code, refs in seen.items()]
    except Exception as exc:
        logger.info("brief done-alone checks skipped: %s", type(exc).__name__)
    try:
        counts: Dict[str, int] = {}
        async for r in db.reminders.find({"user_id": owner, "notified_state": "raised",
                                          "notified_at": {"$gte": since}, "origin": {"$in": list(_SAID)}},
                                         {"_id": 0, "origin": 1}):
            counts[r["origin"]] = counts.get(r["origin"], 0) + 1
        for origin, n in counts.items():
            one, many = _SAID[origin]
            out.append(f"Ti ho mandato {_n(n, one, many)}")
    except Exception as exc:
        logger.info("brief done-alone reminders skipped: %s", type(exc).__name__)
    return out[:6]


def compose(appointments: List[str], deadlines: List[str], reminders: List[str], weather: str,
            drying: str = "") -> str:
    """The notification body: the day in two or three short sentences."""
    parts = []
    if weather:
        parts.append(weather[0].upper() + weather[1:] + ".")
    parts.append(("Oggi: " + "; ".join(appointments) + ".") if appointments else "Niente in agenda oggi.")
    if deadlines:
        parts.append("Scadenze: " + "; ".join(deadlines) + ".")
    if reminders:
        parts.append("Promemoria: " + "; ".join(reminders) + ".")
    if drying:
        parts.append(drying)
    if not (weather or appointments or deadlines or reminders or drying):
        return ""
    text = " ".join(parts)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS - 1].rstrip() + "…"


async def full(db, owner: str, local_now: datetime) -> Dict[str, Any]:
    """The whole brief: what the notification says and what the page shows."""
    row = await db.users.find_one({"user_id": owner}, {"_id": 0, "name": 1}) or {}
    first = str(row.get("name") or "").split(" ")[0][:30]
    hello = "Buongiorno" if local_now.hour < 13 else "Buon pomeriggio" if local_now.hour < 18 else "Buonasera"
    agenda = await _agenda(db, owner, local_now)
    deadlines = await _deadlines(db, owner, local_now)
    reminders = await _reminders(db, owner, local_now)
    w = await _weather(db, owner, local_now)
    watching = await _watching(db, owner)
    sections: List[Dict[str, Any]] = []
    if w:
        lines = [weather_line(w)]
        if w.get("sunset"):
            lines.append(f"Tramonto alle {w['sunset']}")
        if weather_line(w, "tomorrow"):
            lines.append(f"Domani: {weather_line(w, 'tomorrow')}")
        sections.append({"key": "weather", "icon": (w["today"].get("icon") or "partly-sunny-outline"),
                         "title": f"Il tempo{' a ' + w['place'] if w.get('place') else ''}", "lines": lines})
    sections.append({"key": "today", "icon": "calendar-outline", "title": "Oggi",
                     "lines": agenda["today"] or ["Niente in agenda."]})
    done = await _done_alone(db, owner, local_now.astimezone(timezone.utc))
    if done:
        sections.append({"key": "done", "icon": "sparkles-outline", "title": "Nelle ultime 24 ore, da sola",
                         "lines": done})
    if reminders:
        sections.append({"key": "reminders", "icon": "alarm-outline", "title": "Promemoria di oggi", "lines": reminders})
    if deadlines:
        sections.append({"key": "deadlines", "icon": "time-outline", "title": "Scadenze", "lines": deadlines})
    if w and w.get("drying"):
        sections.append({"key": "drying", "icon": "shirt-outline", "title": "Bucato", "lines": [w["drying"]["text"]],
                         "good": w["drying"]["good"]})
    if watching:
        sections.append({"key": "watching", "icon": "eye-outline", "title": "Sto seguendo", "lines": watching})
    if agenda["tomorrow"]:
        sections.append({"key": "tomorrow", "icon": "calendar-clear-outline", "title": "Domani", "lines": agenda["tomorrow"]})
    if not w:
        sections.append({"key": "missing", "icon": "home-outline", "title": "Manca il meteo",
                         "lines": ["Dimmi dov'è casa (Prepara ORA) e ogni mattina ti dico che tempo fa e se è giornata da bucato."]})
    weather_short = weather_line(w)
    drying_short = ""
    if w and w.get("drying") and w["drying"]["good"]:
        drying_short = w["drying"]["text"].replace("Buona giornata per il bucato: ", "Bucato: ")
    headline = compose([a.replace(" · ", " ") for a in agenda["today"][:3]], deadlines[:2], reminders[:2],
                       weather_short, drying_short)
    return {"greeting": f"{hello}{', ' + first if first else ''}", "day": day_label(local_now),
            "headline": headline, "sections": sections, "at": local_now.isoformat(timespec="minutes")}


async def build(db, owner: str, local_now: datetime) -> str:
    return (await full(db, owner, local_now))["headline"]


async def fire_due(db, *, now: Optional[datetime] = None, limit: int = 50) -> Dict[str, int]:
    """Once a day per person, at their hour: queue the brief in the reminder lane."""
    from timezone_service import user_clock_context

    now = now or datetime.now(timezone.utc)
    out = {"checked": 0, "queued": 0, "empty": 0}
    owners: List[str] = []
    for field in ("owner_id", "user_id"):
        try:
            owners += await db.push_endpoints.distinct(field, {"status": "active"})
        except Exception:
            pass
    for owner in list(dict.fromkeys(o for o in owners if o))[:limit]:
        pref = await preference(db, owner)
        if not pref["enabled"]:
            continue
        clock = await user_clock_context(db, owner, now=now)
        local_now = datetime.fromisoformat(clock["local_datetime"])
        due = local_now.replace(hour=pref["hour"], minute=0, second=0, microsecond=0)
        if not (due <= local_now < due + timedelta(hours=LATE_HOURS)):
            continue
        out["checked"] += 1
        rid = f"rem_brief_{owner}_{local_now.date().isoformat()}"[:80]
        claimed = await db.brief_runs.update_one(
            {"_id": rid}, {"$setOnInsert": {"owner_id": owner, "at": now.isoformat()}}, upsert=True)
        if not claimed.upserted_id:
            continue  # already done today (or by another instance)
        text = await build(db, owner, local_now)
        if not text:
            out["empty"] += 1
            continue
        stamp = now.isoformat()
        await db.reminders.insert_one({
            "id": rid, "user_id": owner, "title": text, "status": "open", "due_at": stamp,
            "origin": ORIGIN, "created_at": stamp, "updated_at": stamp,
            "meta": {"kind": ORIGIN},
        })
        out["queued"] += 1
    if out["queued"] or out["empty"]:
        logger.info("morning_brief %s", out)
    return out
