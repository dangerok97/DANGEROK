"""
What happened last time — the person's own history as evidence.

Every time somebody hung the washing out, ORA started from zero: a generic
article on drying times and the weather. But the best evidence about how long
something takes *at this person's home* is how long it took the last times.

When a Situation is resolved or cancelled, what ORA estimated and when it
actually ended are kept (no free text the person did not give, no coordinates).
When a similar Situation starts — similar description, same place — the last
few are offered to the reasoning as a citable observation and as an empirical
baseline: "il 25/10 stesi alle 09:39, stima 16:00-17:00, ritirati alle 17:40".

This is a record of what the person said and did, not a measurement of the
physical outcome, and it says so.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

COLLECTION = "situation_experiences"
KEEP_PER_OWNER = 200
MAX_RECALLED = 3
_STOP = {"i", "il", "lo", "la", "le", "gli", "un", "una", "di", "a", "ad", "da", "in", "per", "con",
         "su", "e", "ho", "sono", "al", "alla", "del", "della", "the", "and"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ù]{3,}", (text or "").casefold()) if w not in _STOP}


def similar(a: str, b: str) -> bool:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.5


def _local(value: Optional[str], tz: str) -> str:
    if not value:
        return ""
    try:
        from zoneinfo import ZoneInfo
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(ZoneInfo(tz)).strftime("%d/%m %H:%M")
    except Exception:
        return ""


async def record(db, owner: str, situation, *, operation: str) -> None:
    """Keep what was estimated and when it ended. Never raises."""
    try:
        goal = await db.agent_goals.find_one(
            {"owner_id": owner, "source_refs": f"situation:{situation.id}"},
            {"_id": 0, "situation_outcome": 1}, sort=[("updated_at", -1)])
        outcome = (goal or {}).get("situation_outcome") or {}
        latest = situation.history[-1].changes if situation.history else {}
        doc = {
            "owner_id": owner, "situation_id": situation.id,
            "summary": str(situation.summary or "")[:200],
            "location_label": str(situation.location_label or "")[:120],
            "started_at": situation.started_at, "ended_at": situation.resolved_at,
            "operation": operation,
            "estimate": {"headline": str(outcome.get("headline") or "")[:200],
                         "window_start": outcome.get("window_start"),
                         "window_end": outcome.get("window_end")} if outcome else None,
            # Only facts the person (or the conversation) added when closing it.
            "closing_facts": [str(f)[:160] for f in (latest.get("facts") or [])][:3],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        await db[COLLECTION].update_one({"owner_id": owner, "situation_id": situation.id},
                                        {"$set": doc}, upsert=True)
        old = await db[COLLECTION].find({"owner_id": owner}, {"_id": 1}).sort(
            "recorded_at", -1).skip(KEEP_PER_OWNER).to_list(100)
        if old:
            await db[COLLECTION].delete_many({"_id": {"$in": [d["_id"] for d in old]}})
    except Exception as exc:
        logger.info("situation experience not recorded: %s", type(exc).__name__)


async def recall(db, owner: str, situation, *, tz: str = "Europe/Rome") -> Optional[str]:
    """One line about the last similar Situations at the same place, or None."""
    rows = await db[COLLECTION].find(
        {"owner_id": owner, "situation_id": {"$ne": situation.id}},
        {"_id": 0}).sort("recorded_at", -1).to_list(40)
    here = (situation.location_label or "").casefold().strip()
    picked = [r for r in rows if similar(r.get("summary", ""), situation.summary or "")
              and (not here or not r.get("location_label") or r["location_label"].casefold().strip() == here)]
    if not picked:
        return None
    parts = []
    for r in picked[:MAX_RECALLED]:
        est = r.get("estimate") or {}
        window = ""
        if est.get("window_start") and est.get("window_end"):
            window = f", stima {_local(est['window_start'], tz)[-5:]}-{_local(est['window_end'], tz)[-5:]}"
        how = "chiusa" if r.get("operation") == "resolve" else "annullata"
        facts = f" ({'; '.join(r['closing_facts'])})" if r.get("closing_facts") else ""
        parts.append(f"{_local(r.get('started_at'), tz)} inizio{window}, {how} alle "
                     f"{_local(r.get('ended_at'), tz)[-5:]}{facts}")
    text = ("Esperienze precedenti della persona in situazioni simili"
            f"{' a ' + situation.location_label if situation.location_label else ''}: "
            + " | ".join(parts) + ". L'orario di chiusura è quando la persona l'ha segnalata, "
            "non una misura dell'esito.")
    return text[:600]
