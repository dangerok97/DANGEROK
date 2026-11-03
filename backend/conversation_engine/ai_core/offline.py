"""
When no model answers: the few things ORA can still do by code, and says so.

Test 3/11 on the owner's account: Gemini, Gemini 2 and Groq out of quota,
OpenAI unauthorised, Mistral timing out — «Ho avviato la lavatrice» got «non
riesco a usare il mio motore di ragionamento». The reminder lane, the typical
durations and the calendar all work without a model. For the commonest
sentences, code does the job and says plainly that it did it without
reasoning; everything else gets an honest, more useful refusal.

Deliberately narrow: an explicit «ricordami» with an explicit time, or a
household appliance just started. Nothing is guessed beyond that.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("ora.ai_core.offline")

UNAVAILABLE = ("Il modello che uso per ragionare non risponde in questo momento: riprova tra qualche minuto. "
               "Intanto promemoria, avvisi e controlli automatici continuano a funzionare.")

_NUM = {"un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
        "otto": 8, "nove": 9, "dieci": 10, "quindici": 15, "venti": 20, "trenta": 30, "quaranta": 40,
        "quarantacinque": 45, "cinquanta": 50}
_ASK = re.compile(r"\b(?:ricordami|ricordarmi|fammi ricordare|avvisami)\b", re.I)
_IN = re.compile(r"\btra\s+(?:(mezz'?ora)|(un quarto d'?ora)|(\d+|[a-z]+)\s*(minut[oi]|min|or[ae]))\b", re.I)
_AT = re.compile(r"\balle\s+(\d{1,2})(?:[:.](\d{2}))?\b", re.I)
_STARTED = re.compile(r"\b(?:ho\s+(?:messo|avviato|acceso|fatto partire|attaccato|azionato|caricato)|"
                      r"sto\s+(?:facendo|usando)|[èe]\s+partit[ao])\b", re.I)


def _minutes(m: re.Match) -> Optional[int]:
    if m.group(1):
        return 30
    if m.group(2):
        return 15
    raw, unit = m.group(3).casefold(), m.group(4).casefold()
    n = int(raw) if raw.isdigit() else _NUM.get(raw)
    if not n:
        return None
    return n * 60 if unit.startswith("or") else n


def _what(text: str, *cut: re.Match) -> str:
    rest = text
    for m in cut:
        if m:
            rest = rest.replace(m.group(0), " ")
    rest = _ASK.sub(" ", rest)
    rest = re.sub(r"\b(?:domani|dopodomani|oggi|stasera|per favore|per piacere)\b", " ", rest, flags=re.I)
    rest = " ".join(rest.split()).strip(" ,.!?")
    rest = re.sub(r"^(?:di|che|a|ad|per)\s+", "", rest, flags=re.I)
    return rest[:1].upper() + rest[1:] if rest else ""


async def _reminder(db, owner: str, text: str, session_id: str) -> Optional[str]:
    from memos.caps import set_reminder

    if not _ASK.search(text):
        return None
    m_in, m_at = _IN.search(text), _AT.search(text)
    args = {}
    if m_in:
        minutes = _minutes(m_in)
        if not minutes:
            return None
        args["delay_minutes"] = minutes
    elif m_at:
        from timezone_service import user_clock_context
        from conversation_engine.ai_core.appointment_net import stated_day

        clock = await user_clock_context(db, owner)
        now = datetime.fromisoformat(clock["local_datetime"])
        hour, minute = int(m_at.group(1)), int(m_at.group(2) or 0)
        if hour > 23 or minute > 59:
            return None
        day = stated_day(text, now=now) or now.date()
        at = datetime(day.year, day.month, day.day, hour, minute, tzinfo=now.tzinfo)
        if at <= now and day == now.date():
            at = at + timedelta(hours=12) if hour < 12 and at + timedelta(hours=12) > now else at + timedelta(days=1)
        args["at_local"] = at.replace(tzinfo=None).isoformat(timespec="minutes")
    else:
        return None
    what = _what(text, m_in, m_at)
    if not what:
        return None
    obs = await set_reminder({"what": what, **args}, {"db": db, "user_id": owner, "session_id": session_id})
    p = obs.payload or {}
    if not p.get("ok"):
        return None
    return (f"Fatto: ti ricordo «{p.get('what')}» {p.get('at_label', '')}. "
            "(Il modello che uso per ragionare ora non risponde: questo l'ho impostato direttamente.)")


_APPLIANCES = {"washer", "dryer", "dishwasher"}


def _span(m: int) -> str:
    return f"{m} min" if m < 90 else (f"{m / 60:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " ore")


async def _appliance(db, owner: str, text: str, session_id: str) -> Optional[str]:
    from memos.caps import set_reminder
    from situations.typical import match

    if not _STARTED.search(text):
        return None
    t = match(text)
    if t is None or t.key not in _APPLIANCES:
        return None  # pots and moka need a person, not a reminder by code
    obs = await set_reminder({"what": f"Controlla la {t.label}: di solito a quest'ora ha finito",
                              "delay_minutes": t.likely}, {"db": db, "user_id": owner, "session_id": session_id})
    p = obs.payload or {}
    if not p.get("ok"):
        return None
    return (f"Ti avviso {p.get('at_label', '')}: di solito la {t.label} impiega tra {_span(t.low)} "
            f"e {_span(t.high)}. Se mi dici quanto dura il programma, lo correggo. "
            "(Il modello che uso per ragionare ora non risponde: l'avviso l'ho impostato direttamente.)")


async def answer(db, owner: str, text: str, *, session_id: str = "") -> str:
    """What to say when no model answered. Never raises."""
    clean = " ".join(str(text or "").split())
    for handler in (_reminder, _appliance):
        try:
            said = await handler(db, owner, clean, session_id)
            if said:
                return said
        except Exception as exc:
            logger.info("offline %s skipped: %s", handler.__name__, type(exc).__name__)
    return UNAVAILABLE
