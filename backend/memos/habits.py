"""
Noticing a habit and offering to take it over.

«Ricordami alle 20 la pastiglia» on Monday, Tuesday and Thursday: the person
is doing by hand what a repeating reminder does by itself. When the same
one-time reminder was asked on at least three different days in the last
three weeks, at about the same time of day, ORA offers — once, in the app —
to make it repeat: every day, or every week on that weekday.

Only the person's own requests are evidence. A proposal declined is never
made again for the same thing. Accepting creates an ordinary repeating
reminder (memos.caps / memos.one_shot), so everything else — snooze, «Fatto»,
cancelling the series — works as for one set by hand.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("ora.habits")

COLLECTION = "habit_proposals"
SOURCE_CONTEXT = "habit_proposal"
WINDOW_DAYS = 21
MIN_DAYS = 3
TIME_SPREAD_MINUTES = 60
ORIGINS = ("chat_reminder",)


def _key(title: str) -> str:
    words = re.findall(r"[a-zà-ù0-9]+", (title or "").casefold())
    stop = {"di", "a", "la", "il", "le", "lo", "i", "gli", "un", "una", "da", "ricordami", "ricordarmi"}
    return " ".join(w for w in words if w not in stop)[:80]


def find(rows: List[Dict[str, Any]], tz) -> List[Dict[str, Any]]:
    """Patterns in one person's one-time reminders. Pure: rows in, proposals out."""
    groups: Dict[str, List[datetime]] = defaultdict(list)
    titles: Dict[str, str] = {}
    for r in rows:
        if (r.get("meta") or {}).get("repeat"):
            continue
        try:
            due = datetime.fromisoformat(str(r.get("due_at")).replace("Z", "+00:00")).astimezone(tz)
        except (TypeError, ValueError):
            continue
        k = _key(r.get("title") or "")
        if not k:
            continue
        groups[k].append(due)
        titles.setdefault(k, " ".join(str(r.get("title") or "").split())[:120])
    out = []
    for k, dues in groups.items():
        days = {d.date() for d in dues}
        if len(days) < MIN_DAYS:
            continue
        minutes = sorted(d.hour * 60 + d.minute for d in dues)
        mid = minutes[len(minutes) // 2]
        if max(abs(m - mid) for m in minutes) > TIME_SPREAD_MINUTES:
            continue
        weekdays = {d.weekday() for d in dues}
        repeat = "weekly" if len(weekdays) == 1 else "daily"
        out.append({"key": k, "title": titles[k], "repeat": repeat, "hour": mid // 60, "minute": mid % 60,
                    "weekday": next(iter(weekdays)) if repeat == "weekly" else None, "days": len(days)})
    return out


_DAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")


def wording(p: Dict[str, Any]) -> str:
    when = f"ogni {_DAYS[p['weekday']]}" if p["repeat"] == "weekly" else "ogni giorno"
    return f"Me l'hai chiesto {p['days']} volte: vuoi che ti ricordi «{p['title']}» {when} alle {p['hour']:02d}:{p['minute']:02d}?"


async def propose(db, owner: str, *, now: Optional[datetime] = None, tz_name: str = "Europe/Rome") -> List[dict]:
    """Self-check: raise at most one new proposal per pass. Never raises."""
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    now = now or datetime.now(timezone.utc)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Rome")
    try:
        rows = await db.reminders.find(
            {"user_id": owner, "origin": {"$in": list(ORIGINS)},
             "due_at": {"$gte": (now - timedelta(days=WINDOW_DAYS)).isoformat()}},
            {"_id": 0, "title": 1, "due_at": 1, "meta": 1}).to_list(300)
        for p in find(rows, tz):
            if await db[COLLECTION].find_one({"owner_id": owner, "key": p["key"]}, {"_id": 1}):
                continue
            # Already repeating by hand-made series? Then there is nothing to offer.
            if await db.reminders.find_one({"user_id": owner, "meta.repeat": {"$exists": True},
                                            "status": "open", "title": p["title"]}, {"_id": 1}):
                continue
            import hashlib
            pid = "hab_" + hashlib.sha256(f"{owner}|{p['key']}".encode()).hexdigest()[:16]
            await db[COLLECTION].insert_one({"id": pid, "owner_id": owner, "key": p["key"], "status": "proposed",
                                             "proposal": {**p, "tz": tz.key}, "created_at": now.isoformat()})
            await OpportunityRepository(db).save(Opportunity(
                owner_id=owner, identity_key=f"{SOURCE_CONTEXT}:{pid}", status="active",
                semantic_summary=wording(p)[:280],
                why_it_matters="Lo stai già facendo a mano: un promemoria ricorrente lo fa da solo.",
                why_now="Ho notato che chiedi spesso lo stesso promemoria alla stessa ora.",
                relevance="medium", urgency="none", time_sensitivity="stable", confidence="strong",
                initiative="recommend", what_ora_can_do="Renderlo ricorrente.",
                evidence=[EvidenceRef(kind="habit", ref=pid, summary=p["title"][:240])],
                source_context=SOURCE_CONTEXT, decision_provenance="user",
                valid_until=(now + timedelta(days=7)).isoformat(),
                surface_state="surfaced", surface_rationale="Abitudine osservata nei promemoria della persona.",
            ))
            return [{"code": "habit_proposed", "ref": f"habit:{pid}", "repaired": True}]
    except Exception as exc:
        logger.info("habit proposal deferred: %s", type(exc).__name__)
    return []


async def answer(db, owner: str, opportunity_id: str, accept: bool) -> Dict[str, Any]:
    import uuid
    from opportunities.service import OpportunityService

    opp = await db.opportunities.find_one({"owner_id": owner, "id": opportunity_id}, {"_id": 0})
    if not opp or opp.get("source_context") != SOURCE_CONTEXT:
        return {"ok": False, "reason": "not_a_proposal"}
    pid = str(opp.get("identity_key") or "").split(":", 1)[-1]
    row = await db[COLLECTION].find_one({"owner_id": owner, "id": pid}, {"_id": 0})
    if not row or row.get("status") != "proposed":
        await OpportunityService(db).resolve(owner, opportunity_id)
        return {"ok": False, "reason": "already_answered"}
    out: Dict[str, Any] = {"ok": True, "accepted": accept}
    if accept:
        from memos.one_shot import next_occurrence
        p = row["proposal"]
        tz = ZoneInfo(p.get("tz") or "Europe/Rome")
        now = datetime.now(timezone.utc)
        local = now.astimezone(tz)
        first = local.replace(hour=p["hour"], minute=p["minute"], second=0, microsecond=0)
        if p["repeat"] == "weekly":
            first += timedelta(days=(p["weekday"] - first.weekday()) % 7)
        if first <= local:
            nxt = next_occurrence(first.astimezone(timezone.utc), p["repeat"], tz.key, after=now)
            first = nxt.astimezone(tz) if nxt else first + timedelta(days=1)
        rid = f"rem_{uuid.uuid4().hex[:16]}"
        stamp = now.isoformat()
        await db.reminders.insert_one({
            "id": rid, "user_id": owner, "title": p["title"], "status": "open",
            "due_at": first.astimezone(timezone.utc).isoformat(), "origin": "chat_reminder",
            "created_at": stamp, "updated_at": stamp,
            "meta": {"repeat": p["repeat"], "tz": tz.key, "series": rid, "from_habit": pid},
        })
        out["first_at"] = first.isoformat()
    await db[COLLECTION].update_one({"owner_id": owner, "id": pid},
                                    {"$set": {"status": "accepted" if accept else "declined",
                                              "answered_at": datetime.now(timezone.utc).isoformat()}})
    await OpportunityService(db).resolve(owner, opportunity_id)
    return out
