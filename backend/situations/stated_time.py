"""
When the person says how long it takes, the reminder does not depend on a model.

"Ho messo la lavatrice, dura due ore", "il pane è pronto alle 11", "tra 40
minuti tolgo l'arrosto": the moment is already known. Until now the watch
still asked a model to pick its checkpoint, and with the model out of quota
the person heard nothing. A stated moment is a fact the person gave: it gets
a one-time reminder (memos.one_shot), sent at that moment by code, exactly
like "ricordamelo alle 15".

Only for a Situation the conversation already decided to keep an eye on, and
only from the person's own words in that turn. Questions, negations and the
past ("due ore fa") arm nothing. The Situation's own watch keeps reasoning as
before; if it already announced the result, or the Situation is closed, the
reminder steps aside instead of saying it twice.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

ORIGIN = "situation_stated_time"
MIN_MINUTES = 1
MAX_HOURS = 24

_WORDS = {
    "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6,
    "sette": 7, "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "quindici": 15,
    "venti": 20, "venticinque": 25, "trenta": 30, "trentacinque": 35, "quaranta": 40,
    "quarantacinque": 45, "cinquanta": 50, "cinquantacinque": 55, "sessanta": 60, "novanta": 90,
}
_NUM = r"\d+(?:[.,]\d+)?|" + "|".join(sorted(_WORDS, key=len, reverse=True))
_AMOUNT = (
    rf"(?P<n>{_NUM})\s*(?P<u>minuti|minuto|min|m|ore|ora|h)\b"
    r"(?:\s*e\s*(?P<extra>mezza|mezzo|un quarto|\d+\s*(?:minuti|min|m)?))?"
    r"|(?P<half>mezz'ora|mezzora|mezza ora)|(?P<quarter>un quarto d'ora)"
)
# "from now": tra/fra/mancano. "from the start": dura, ci vogliono, cuoce per...
_FROM_NOW = r"tra|fra|mancano|manca|ancora|entro|nel giro di"
_FROM_START = (r"dura|durano|durerà|ci vogliono|ci vuole|ci mette|ci metterà|ci mettono|"
               r"(?:cuoce|cuociono|cuocere|lievita|lievitare|riposa|riposare|asciuga|asciugare|"
               r"carica|caricare|bolle|bollire|scongela|scongelare|marina|marinare)"
               r"(?:\s+per)?|programma da|ciclo da|timer di|timer da")
_DURATION = re.compile(
    rf"(?P<neg>\bnon\s+)?\b(?P<lead>{_FROM_NOW}|{_FROM_START})\s+(?:circa\s+|più o meno\s+|almeno\s+)?(?:{_AMOUNT})"
    r"(?P<ago>\s+fa\b)?"
)
_CLOCK = re.compile(
    r"(?P<neg>\bnon\s+)?\b(?:finisce|finirà|finiscono|termina|terminerà|è pronto|è pronta|sarà pronto|sarà pronta|"
    r"pronto|pronta|pronti|pronte|scade|suona|fine|finito|finita|arriva|arriverà|passa|passano|"
    r"ritiro|ritirare|ritirarl[oiae]|tolgo|togliere|toglierl[oiae]|spengo|spegnere|spegnerl[oiae]|"
    r"tirarl[oiae] fuori|sfornare|sfornarl[oiae])\b[^.?!\n]{0,30}?\b(?:alle|verso le|per le|intorno alle)\s+"
    r"(?P<h>\d{1,2})(?:[:.](?P<mm>\d{2}))?\b"
)


def _number(token: str) -> Optional[float]:
    token = token.strip()
    if token in _WORDS:
        return float(_WORDS[token])
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


def _minutes(match: re.Match) -> Optional[float]:
    if match.group("half"):
        return 30.0
    if match.group("quarter"):
        return 15.0
    n = _number(match.group("n") or "")
    if n is None:
        return None
    unit = match.group("u") or ""
    minutes = n * 60 if unit in ("ore", "ora", "h") else n
    extra = (match.group("extra") or "").strip()
    if extra in ("mezza", "mezzo"):
        minutes += 30 if unit in ("ore", "ora", "h") else 0
    elif extra == "un quarto":
        minutes += 15 if unit in ("ore", "ora", "h") else 0
    elif extra:
        more = _number(re.sub(r"\D", "", extra))
        minutes += more or 0
    return minutes


def _normalize(text: str) -> str:
    text = (text or "").casefold().replace("’", "'").replace("`", "'")
    text = re.sub(r"\bun'ora\b", "un ora", text)
    text = re.sub(r"\bun'oretta\b", "un ora", text)
    return " ".join(text.split())


def stated_moment(text: str, *, now: datetime, started_at: Optional[datetime] = None
                  ) -> Optional[Tuple[datetime, str]]:
    """The moment the person's words name, as an aware instant, and the words."""
    clean = _normalize(text)
    if not clean or "?" in clean:
        return None
    best: Optional[Tuple[datetime, str]] = None
    for m in _DURATION.finditer(clean):
        if m.group("neg") or m.group("ago"):
            continue
        minutes = _minutes(m)
        if minutes is None or not MIN_MINUTES <= minutes <= MAX_HOURS * 60:
            continue
        lead = m.group("lead")
        from_now = re.fullmatch(_FROM_NOW, lead) is not None
        base = now
        if not from_now and started_at and now - timedelta(hours=12) <= started_at <= now:
            base = started_at
        moment = base + timedelta(minutes=minutes)
        if moment > now and (best is None or moment < best[0]):
            best = (moment, m.group(0).strip())
    for m in _CLOCK.finditer(clean):
        if m.group("neg"):
            continue
        hour, minute = int(m.group("h")), int(m.group("mm") or 0)
        if hour > 23 or minute > 59:
            continue
        moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if moment <= now and hour < 12:
            moment = moment.replace(hour=hour + 12)  # «alle 3» in the morning means 15:00
        if moment <= now or moment - now > timedelta(hours=MAX_HOURS):
            continue
        if best is None or moment < best[0]:
            best = (moment, m.group(0).strip())
    return best


def _aware(value: Any) -> Optional[datetime]:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else None


async def arm(db, owner: str, situation, user_message: str) -> Optional[dict]:
    """Create or move the reminder for this Situation's stated moment. Never raises."""
    try:
        if not (situation.attention_intent or situation.next_check_summary):
            return None
        if situation.status not in ("active", "changed"):
            return None
        from timezone_service import user_clock_context

        clock = await user_clock_context(db, owner)
        now = datetime.fromisoformat(clock["local_datetime"])
        started = _aware(situation.started_at)
        found = stated_moment(user_message, now=now, started_at=started)
        rid = f"rem_sit_{situation.id}"[:80]
        existing = await db.reminders.find_one({"id": rid, "user_id": owner}, {"_id": 0, "due_at": 1})
        summary = " ".join(str(situation.summary or "").split())[:110]
        typical = None
        if not found:
            from situations import outdoor_drying
            if outdoor_drying.applies(situation.summary or "", user_message, " ".join(getattr(situation, "facts", None) or [])):
                # Drying outdoors: computed from the hourly weather, not a
                # usual duration and not a guess (24-26/10).
                planned = await outdoor_drying.plan(db, owner, situation, tz=now.tzinfo)
                return {**planned, "drying": True} if planned else None
            # Nothing stated. A usual duration gives a fallback the first
            # time only: a later turn must not keep pushing it forward, and
            # it never replaces a moment the person stated.
            from situations.typical import match
            typical = match(situation.summary or "", user_message)
            if typical is None or existing:
                return None
            base = started if started and now - timedelta(hours=12) <= started <= now else now
            from situations.calibration import factor
            moment = base + timedelta(minutes=typical.likely * await factor(db, owner, f"typical:{typical.key}"))
            if moment <= now + timedelta(minutes=1):
                return None
            words = f"tempo tipico: {typical.label}"
        else:
            moment, words = found
        due = moment.astimezone(timezone.utc).isoformat()
        local = moment.strftime("%H:%M")
        title = (f"Di solito a quest'ora ha finito: {summary}" if typical
                 else f"Sono le {local}, l'ora che avevi detto: {summary}")
        doc = {
            "id": rid, "user_id": owner, "status": "open", "due_at": due,
            "title": title[:160],
            "origin": ORIGIN, "updated_at": datetime.now(timezone.utc).isoformat(),
            "meta": {"situation_id": situation.id, "kind": "typical_end" if typical else "stated_end",
                     "typical_key": typical.key if typical else None,
                     "start": (started if started and typical and base == started else now).isoformat(),
                     "words": words[:80]},
        }
        if existing and existing.get("due_at") == due:
            return {"at_local": local, "unchanged": True}
        await db.reminders.update_one(
            {"id": rid, "user_id": owner},
            {"$set": doc, "$unset": {"notified_state": "", "notified_at": ""},
             "$setOnInsert": {"created_at": doc["updated_at"]}},
            upsert=True,
        )
        out = {"at_local": local, "words": words[:80]}
        if typical:
            out.update({"typical": True, "typical_range_minutes": [typical.low, typical.high]})
        return out
    except Exception as exc:
        logger.info("stated time not armed: %s", type(exc).__name__)
        return None


async def disarm(db, owner: str, situation_id: str) -> None:
    try:
        await db.reminders.update_many(
            {"user_id": owner, "origin": ORIGIN, "meta.situation_id": situation_id,
             "status": {"$in": ["open", "active", "pending"]}},
            {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    except Exception as exc:
        logger.info("stated time not disarmed: %s", type(exc).__name__)


async def already_said(db, owner: str, row: dict) -> bool:
    """The Situation is over, or its watch already announced the result."""
    sid = str((row.get("meta") or {}).get("situation_id") or "")
    if row.get("origin") != ORIGIN or not sid:
        return False
    situation = await db.situations.find_one({"user_id": owner, "id": sid}, {"_id": 0, "status": 1})
    if not situation or situation.get("status") not in ("active", "changed"):
        return True
    goal = await db.agent_goals.find_one(
        {"owner_id": owner, "source_refs": f"situation:{sid}"},
        {"_id": 0, "situation_outcome": 1}, sort=[("updated_at", -1)])
    if (row.get("meta") or {}).get("kind") == "rain_risk":
        # Rain is an exception to warn about, whatever the watch concluded.
        return False
    outcome = (goal or {}).get("situation_outcome") or {}
    if outcome.get("action_reason") == "outcome_ready":
        return True
    # A usual duration is only a fallback: once the watch has its own
    # estimate for this situation, that estimate is what the person hears.
    return ((row.get("meta") or {}).get("kind") == "typical_end"
            and bool(outcome.get("window_start") or outcome.get("window_end")))
