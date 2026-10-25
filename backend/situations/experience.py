"""
What happened last time — the person's own history as evidence.

Every time somebody hung the washing out, ORA started from zero: a generic
article on drying times and the weather. But the best evidence about how long
something takes *at this person's home* is how long it took the last times.

When a Situation is resolved or cancelled, ORA keeps its own record: what the
weather readings actually measured while it watched, its first and its final
hypothesis, and when the Situation ended. Nothing is asked of the person; a
fact they added when closing it is kept too, but never required.
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
            {"_id": 0, "id": 1, "situation_outcome": 1}, sort=[("updated_at", -1)])
        outcome = (goal or {}).get("situation_outcome") or {}
        conditions = await _observed_conditions(db, owner, (goal or {}).get("id"))
        first = await db.agent_journal.find_one(
            {"owner_id": owner, "goal_id": (goal or {}).get("id"), "kind": "situation_outcome_assessed"},
            {"_id": 0, "note": 1}, sort=[("at", 1)]) if goal else None
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
            # ORA's own data: what the weather actually did while it watched,
            # its first and its final hypothesis. Nothing asked of the person.
            "conditions": conditions,
            "first_hypothesis": str((first or {}).get("note") or "")[:200],
            "final_hypothesis": {"headline": str(outcome.get("headline") or "")[:200],
                                 "ready": outcome.get("action_reason") == "outcome_ready"} if outcome else None,
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


async def _observed_conditions(db, owner: str, goal_id: Optional[str]) -> Optional[dict]:
    """Ranges of what the weather readings measured during the watch."""
    if not goal_id:
        return None
    rows = await db.agent_evidence.find(
        {"owner_id": owner, "goal_id": goal_id, "provenance.capability": "weather.read",
         "measures": {"$exists": True}}, {"_id": 0, "measures": 1}).to_list(60)
    ranges: dict[str, list[float]] = {}
    for row in rows:
        for key in ("temperature_c", "humidity_pct", "wind_kmh"):
            value = (row.get("measures") or {}).get(key)
            if isinstance(value, (int, float)):
                ranges.setdefault(key, []).append(float(value))
    if not ranges:
        return None
    return {key: [min(v), max(v)] for key, v in ranges.items()} | {"readings": len(rows)}


def _conditions_text(c: Optional[dict]) -> str:
    if not c:
        return ""
    bits = []
    for key, unit in (("temperature_c", "°C"), ("humidity_pct", "% umidità"), ("wind_kmh", " km/h vento")):
        if key in c:
            lo, hi = c[key]
            bits.append(f"{round(lo)}{unit}" if round(lo) == round(hi) else f"{round(lo)}–{round(hi)}{unit}")
    return (" con " + ", ".join(bits)) if bits else ""


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
        final = r.get("final_hypothesis") or {}
        said = "; ORA aveva concluso che fosse pronto" if final.get("ready") else ""
        parts.append(f"{_local(r.get('started_at'), tz)} inizio{_conditions_text(r.get('conditions'))}"
                     f"{window}{said}, {how} alle {_local(r.get('ended_at'), tz)[-5:]}{facts}")
    text = ("Esperienze precedenti della persona in situazioni simili"
            f"{' a ' + situation.location_label if situation.location_label else ''}: "
            + " | ".join(parts) + ". L'orario di chiusura è quando la persona l'ha segnalata, "
            "non una misura dell'esito.")
    return text[:600]
