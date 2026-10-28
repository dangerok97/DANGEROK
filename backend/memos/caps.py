"""Cognitive capability for explicit recurring personal memos."""
from __future__ import annotations

from typing import Any, Dict

from conversation_engine.ai_core.models import Observation
from memos.service import RecurringMemoService


async def save_recurring_memo(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    db = runtime.get("db")
    owner = str(runtime.get("user_id") or "")
    if db is None or not owner:
        return Observation(
            kind="tool", name="save_recurring_memo", status="error",
            payload={"ok": False, "error": "runtime_unavailable"},
        )
    service = RecurringMemoService(db)
    try:
        result = await service.save_annual(
            owner,
            memory_ref=str(arguments.get("memory_ref") or ""),
            category=str(arguments.get("category") or "annual_memo"),
            label=str(arguments.get("label") or ""),
            person=str(arguments.get("person") or ""),
            month=int(arguments.get("month")),
            day=int(arguments.get("day")),
            timezone_name=str(arguments.get("timezone") or "Europe/Rome"),
            remind_hour_local=int(
                arguments["remind_hour_local"]
                if arguments.get("remind_hour_local") is not None else 9
            ),
        )
    except (TypeError, ValueError):
        result = {"ok": False, "error": "invalid_annual_date"}
    return Observation(
        kind="tool",
        name="save_recurring_memo",
        status="ok" if result.get("ok") else "error",
        payload=result,
        provenance=[str(arguments.get("memory_ref") or "")] if result.get("ok") else [],
    )


# --- one-time reminders from the conversation -------------------------------
#
# "Ricordami domani alle 9 di chiamare il dentista", "tra mezz'ora ricordami il
# forno". Before 26/10 there was no tool for this: the model could only open a
# Situation and hope its own checkpoint fired. These write the same rows the
# one-time reminder lane sends by code (memos.one_shot), so the reminder no
# longer depends on a model being available at that moment.

_OPEN = ("open", "active", "pending")
_DAYS = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
_MONTHS = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")


def _obs(name: str, ok: bool, payload: Dict[str, Any]) -> Observation:
    return Observation(kind="tool", name=name, status="ok" if ok else "error",
                       payload={"ok": ok, **payload})


def _label(moment) -> str:
    return f"{_DAYS[moment.weekday()]} {moment.day} {_MONTHS[moment.month - 1]}, {moment:%H:%M}"


async def _local_now(db, owner):
    from datetime import datetime
    from timezone_service import user_clock_context

    clock = await user_clock_context(db, owner)
    return datetime.fromisoformat(clock["local_datetime"])


_REPEAT_WORDS = {"daily": "ogni giorno", "weekdays": "dal lunedì al venerdì", "weekly": "ogni settimana"}


def _public(row: Dict[str, Any], tz) -> Dict[str, Any]:
    from memos.one_shot import _due

    due = _due(row)
    out = {"reminder_id": row.get("id"), "what": row.get("title"),
           "at_label": _label(due.astimezone(tz)) if due else ""}
    repeat = (row.get("meta") or {}).get("repeat")
    if repeat:
        out["repeats"] = _REPEAT_WORDS.get(repeat, repeat)
    return out


async def set_reminder(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    import uuid
    from datetime import datetime, timedelta, timezone

    name = "set_reminder"
    db, owner = runtime.get("db"), str(runtime.get("user_id") or "")
    if db is None or not owner:
        return _obs(name, False, {"error": "runtime_unavailable"})
    what = " ".join(str(arguments.get("what") or "").split())[:160]
    if not what:
        return _obs(name, False, {"error": "what_missing", "say": "Serve sapere cosa ricordare."})
    now = await _local_now(db, owner)
    moment = None
    if arguments.get("delay_minutes") not in (None, ""):
        try:
            moment = now + timedelta(minutes=float(arguments["delay_minutes"]))
        except (TypeError, ValueError):
            moment = None
    elif arguments.get("at_local"):
        try:
            parsed = datetime.fromisoformat(str(arguments["at_local"]).strip())
            moment = parsed.replace(tzinfo=now.tzinfo) if parsed.tzinfo is None else parsed.astimezone(now.tzinfo)
        except ValueError:
            moment = None
    if moment is None:
        return _obs(name, False, {"error": "when_missing",
                                  "say": "Serve un momento preciso: un orario o fra quanto."})
    if moment <= now + timedelta(seconds=30):
        return _obs(name, False, {"error": "in_the_past", "now_local": now.isoformat(timespec="minutes")})
    if moment - now > timedelta(days=366):
        return _obs(name, False, {"error": "too_far"})
    due = moment.astimezone(timezone.utc)
    window = [(due - timedelta(minutes=1)).isoformat(), (due + timedelta(minutes=1)).isoformat()]
    same = await db.reminders.find_one(
        {"user_id": owner, "title": what, "status": {"$in": list(_OPEN)},
         "due_at": {"$gte": window[0], "$lte": window[1]}}, {"_id": 0})
    if same:
        return _obs(name, True, {"status": "already_set", **_public(same, now.tzinfo)})
    from memos.one_shot import REPEATS
    repeat = str(arguments.get("repeat") or "").strip().lower()
    if repeat in ("", "none", "no"):
        repeat = ""
    elif repeat not in REPEATS:
        return _obs(name, False, {"error": "invalid_repeat", "allowed": list(REPEATS)})
    stamp = datetime.now(timezone.utc).isoformat()
    meta = {"session_id": str(runtime.get("session_id") or "")[:80]}
    if repeat:
        meta.update({"repeat": repeat, "tz": str(getattr(now.tzinfo, "key", "") or "Europe/Rome")})
    row = {"id": f"rem_{uuid.uuid4().hex[:16]}", "user_id": owner, "title": what,
           "body": " ".join(str(arguments.get("note") or "").split())[:300],
           "status": "open", "due_at": due.isoformat(), "origin": "chat_reminder",
           "created_at": stamp, "updated_at": stamp, "meta": meta}
    if repeat:
        row["meta"]["series"] = row["id"]
    await db.reminders.insert_one(dict(row))
    return _obs(name, True, {"status": "set", **_public(row, now.tzinfo),
                             "repeat": _REPEAT_WORDS.get(repeat, "una volta"),
                             "delivery": "notifica sul telefono all'ora indicata, e in Home"})


async def list_reminders(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    from datetime import timezone

    name = "list_reminders"
    db, owner = runtime.get("db"), str(runtime.get("user_id") or "")
    if db is None or not owner:
        return _obs(name, False, {"error": "runtime_unavailable"})
    now = await _local_now(db, owner)
    rows = await db.reminders.find(
        {"user_id": owner, "status": {"$in": list(_OPEN)}, "notified_state": {"$exists": False},
         "due_at": {"$gte": now.astimezone(timezone.utc).isoformat()}}, {"_id": 0},
    ).sort("due_at", 1).limit(20).to_list(20)
    return _obs(name, True, {"count": len(rows), "reminders": [_public(r, now.tzinfo) for r in rows]})


async def cancel_reminder(arguments: Dict[str, Any], runtime: Dict[str, Any]) -> Observation:
    from datetime import datetime, timezone

    name = "cancel_reminder"
    db, owner = runtime.get("db"), str(runtime.get("user_id") or "")
    rid = str(arguments.get("reminder_id") or "").strip()
    if db is None or not owner:
        return _obs(name, False, {"error": "runtime_unavailable"})
    if not rid:
        return _obs(name, False, {"error": "reminder_id_missing", "say": "Usa list_reminders per trovarlo."})
    result = await db.reminders.update_one(
        {"user_id": owner, "id": rid, "status": {"$in": list(_OPEN)}},
        {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}})
    if not result.modified_count:
        return _obs(name, False, {"error": "not_found_or_closed"})
    return _obs(name, True, {"status": "cancelled", "reminder_id": rid})
