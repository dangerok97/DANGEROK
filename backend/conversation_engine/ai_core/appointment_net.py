"""
An appointment said in chat lands in the calendar even when the model forgets.

«Alle 15 ho l'appuntamento dal parrucchiere a Montalto di Castro»: the leave
notice needs a calendar event with a place. The model is asked to create one;
the light model does not always do it. After the turn, if the person's own
words carry an appointment cue, a clock time and a place, and no event exists
at that time, ORA writes it in its own calendar (reversible, never Google),
computes the leave time, and says both in the same answer, so nothing is
claimed that did not happen and nothing is done silently.

Deliberately narrow: questions, negations, the past and anything without an
explicit time and an explicit place are left to the conversation.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.appointment_net")

_CUE = re.compile(r"\b(?:appuntamento|visita|prenotazione|prenotat[oa]|ho (?:il|la|lo|l'|un|una|i|le)\b|"
                  r"devo (?:andare|essere)|mi aspetta|incontro|riunione|colloquio|controllo)", re.I)
_TIME = re.compile(r"\b(?:alle|per le|verso le|alle ore|ore)\s+(\d{1,2})(?:[:.](\d{2}))?\b", re.I)
_PAST = re.compile(r"\b(?:ho avuto|era|ero|sono stat[oa]|c'era|avevo)\b", re.I)
_NEG = re.compile(r"\bnon\b", re.I)
_DAYS = {"lunedì": 0, "lunedi": 0, "martedì": 1, "martedi": 1, "mercoledì": 2, "mercoledi": 2,
         "giovedì": 3, "giovedi": 3, "venerdì": 4, "venerdi": 4, "sabato": 5, "domenica": 6}
_PLACE_NAME = r"[A-ZÀ-Ý][\wÀ-ÿ'’]+(?:\s+(?:di|del|della|dei|delle|d'|sul|sulla|al|alla|in)?\s*[A-ZÀ-Ý][\wÀ-ÿ'’]+)*"
_PLACE = re.compile(rf"\b(?:a|ad|in|presso)\s+({_PLACE_NAME})")
_ADDRESS = re.compile(r"\b((?:via|viale|piazza|piazzale|corso|largo|vicolo)\s+[^,.;?!]{2,60})", re.I)
_WHO = re.compile(r"\b(?:dal|dalla|dallo|dai|dagli|dalle|da)\s+([a-zà-ù]+(?:\s+[a-zà-ù]+)?)", re.I)
_WHAT = re.compile(r"\b(appuntamento|visita|colloquio|riunione|incontro|controllo|prenotazione)"
                   r"(?:\s+(?:dal|dalla|dallo|di|del|della|dal)\s+([a-zà-ù]+))?", re.I)
_STOP_WHO = {"casa", "me", "te", "lui", "lei", "noi", "voi", "loro", "solo", "sola"}


def parse(text: str, *, now: datetime) -> Optional[Dict[str, Any]]:
    """{'start', 'title', 'location'} from the person's words, or None."""
    raw = " ".join(str(text or "").split())
    if not raw or "?" in raw or not _CUE.search(raw) or _PAST.search(raw) or _NEG.search(raw):
        return None
    tm = _TIME.search(raw)
    if not tm:
        return None
    hour, minute = int(tm.group(1)), int(tm.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    low = raw.casefold()
    day = now.date()
    if "dopodomani" in low:
        day = day + timedelta(days=2)
    elif "domani" in low:
        day = day + timedelta(days=1)
    else:
        for name, wd in _DAYS.items():
            if re.search(rf"\b{name}\b", low):
                ahead = (wd - now.weekday()) % 7 or 7
                day = day + timedelta(days=ahead)
                break
    start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=now.tzinfo)
    if start <= now and hour < 12 and day == now.date():
        start = start.replace(hour=hour + 12)
    if start <= now:
        return None
    address = _ADDRESS.search(raw)
    place = _PLACE.search(raw)
    location = (address.group(1) if address else "") or (place.group(1) if place else "")
    if address and place and place.group(1) not in address.group(1):
        location = f"{address.group(1).strip()}, {place.group(1)}"
    location = location.strip()
    if not location:
        return None
    title = ""
    who = _WHO.search(raw)
    if who and who.group(1).split()[0].casefold() not in _STOP_WHO and (not place or who.group(1) not in place.group(1)):
        words = [w for w in who.group(1).split() if w.casefold() not in
                 {"a", "ad", "in", "presso", "alle", "per", "verso", "oggi", "domani", "dopodomani"}]
        title = (words[0] if words else "").strip()
    if not title:
        what = _WHAT.search(raw)
        title = " ".join(x for x in (what.group(1), what.group(2)) if x) if what else "Appuntamento"
    title = title[:1].upper() + title[1:]
    return {"start": start, "title": title[:60], "location": location[:160]}


async def ensure_after_turn(db, owner: str, user_message: str, *, session_id: str = "") -> Optional[str]:
    """Write the appointment if missing; return the sentence to add to the answer."""
    try:
        from timezone_service import user_clock_context
        from opportunities.snapshot import _calendar

        clock = await user_clock_context(db, owner)
        now = datetime.fromisoformat(clock["local_datetime"])
        found = parse(user_message, now=now)
        if not found:
            return None
        for e in await _calendar(db, owner, now):
            try:
                at = datetime.fromisoformat(str(e.get("starts_at")).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if at.tzinfo and abs((at - found["start"]).total_seconds()) <= 600:
                return None  # already there (the model, or the person, wrote it)
        from home.manual_event import create_manual_event
        start = found["start"]
        key = hashlib.sha256(f"{owner}|{session_id}|{user_message}".encode()).hexdigest()[:20]
        await create_manual_event(
            db, owner, title=found["title"], start=start.isoformat(),
            end=(start + timedelta(minutes=60)).isoformat(), tz_name=str(clock.get("timezone") or "Europe/Rome"),
            request_id=f"net:{key}", location=found["location"], end_time_known=False,
            description="Segnato da ORA dalla tua frase in chat.")
        when = start.strftime("%H:%M")
        day = "oggi" if start.date() == now.date() else "domani" if start.date() == now.date() + timedelta(days=1) \
            else start.strftime("%d/%m")
        sentence = f"Ho segnato nel calendario di ORA «{found['title']}» {day} alle {when} a {found['location']}."
        from places.leave_notice import plan_owner
        rows = await plan_owner(db, owner)
        row = next((r for r in rows if r.get("event") == found["title"]), None)
        if row and row.get("status") == "planned":
            sentence += (f" Ti avviso alle {row['leave_at_local']} quando è ora di partire "
                         f"(circa {row['minutes']} min {row['mode']}), con il percorso pronto.")
        elif row and row.get("status") == "needs_location":
            sentence += " Per dirti quando partire mi serve la posizione o la tua casa in Vita → Luoghi."
        elif row and row.get("status") == "destination_unresolved":
            sentence += " Non ho trovato il luogo sulla mappa: se mi dai l'indirizzo calcolo quando partire."
        return sentence
    except Exception as exc:
        logger.info("appointment net skipped: %s", type(exc).__name__)
        return None
