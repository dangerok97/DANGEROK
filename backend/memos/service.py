"""Durable recurring memo scheduling.

A memo is not a Situation: the fact is stable Memory and the recurrence is an
explicit user-facing obligation. The ambient runtime only checks due rows and
raises one ordinary Opportunity; the existing delivery pipeline decides how it
reaches the person.
"""
from __future__ import annotations

import calendar
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

COLLECTION = "recurring_memos"
CLAIM_SECONDS = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(owner_id: str, memory_ref: str, category: str) -> str:
    raw = f"{owner_id}|{memory_ref}|{category}"
    return "rmm_" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Europe/Rome")
    except Exception:
        return ZoneInfo("Europe/Rome")


def _next_annual(*, month: int, day: int, timezone_name: str, hour: int = 9,
                 now: Optional[datetime] = None, after_year: Optional[int] = None) -> datetime:
    tz = _zone(timezone_name)
    moment = (now or _now()).astimezone(tz)
    start_year = max(moment.year, int(after_year or moment.year))
    for year in range(start_year, start_year + 12):
        if day > calendar.monthrange(year, month)[1]:
            continue
        candidate = datetime(year, month, day, hour, 0, tzinfo=tz)
        if candidate > moment:
            return candidate.astimezone(timezone.utc)
    raise ValueError("annual_date_not_resolvable")


def _public(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc.get("id"),
        "memory_ref": doc.get("memory_ref"),
        "category": doc.get("category"),
        "label": doc.get("label"),
        "person": doc.get("person"),
        "month": doc.get("month"),
        "day": doc.get("day"),
        "timezone": doc.get("timezone"),
        "remind_hour_local": doc.get("remind_hour_local"),
        "next_due_at": doc.get("next_due_at"),
        "status": doc.get("status"),
    }


class RecurringMemoService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db[COLLECTION].create_index("id", unique=True)
        await self.db[COLLECTION].create_index(
            [("owner_id", 1), ("memory_ref", 1), ("category", 1)], unique=True
        )
        await self.db[COLLECTION].create_index([("status", 1), ("next_due_at", 1)])

    async def save_annual(
        self, owner_id: str, *, memory_ref: str, category: str, label: str,
        person: str, month: int, day: int, timezone_name: str = "Europe/Rome",
        remind_hour_local: int = 9,
    ) -> Dict[str, Any]:
        memory = await self.db.memories.find_one(
            {"user_id": owner_id, "id": memory_ref, "status": "active"}, {"_id": 0}
        )
        if not memory:
            return {"ok": False, "error": "durable_memory_required"}
        month, day = int(month), int(day)
        hour = max(0, min(23, int(remind_hour_local)))
        if month < 1 or month > 12 or day < 1 or day > 31:
            return {"ok": False, "error": "invalid_annual_date"}
        try:
            next_due = _next_annual(
                month=month, day=day, timezone_name=timezone_name, hour=hour
            )
        except Exception:
            return {"ok": False, "error": "invalid_annual_date"}

        value = memory.get("value") if isinstance(memory.get("value"), dict) else {}
        remembered_month = value.get("month")
        remembered_day = value.get("day")
        if remembered_month is not None and int(remembered_month) != month:
            return {"ok": False, "error": "memory_date_mismatch"}
        if remembered_day is not None and int(remembered_day) != day:
            return {"ok": False, "error": "memory_date_mismatch"}

        now = _now().isoformat()
        memo_id = _stable_id(owner_id, memory_ref, category)
        doc = {
            "id": memo_id,
            "owner_id": owner_id,
            "memory_ref": memory_ref,
            "category": str(category or "annual_memo")[:60],
            "label": str(label or memory.get("statement") or "Promemoria annuale")[:220],
            "person": str(person or value.get("person") or "")[:120],
            "recurrence": "annual",
            "month": month,
            "day": day,
            "timezone": timezone_name or "Europe/Rome",
            "remind_hour_local": hour,
            "next_due_at": next_due.isoformat(),
            "status": "active",
            "last_fired_at": None,
            "last_fired_year": None,
            "claim_until": "",
            "created_at": now,
            "updated_at": now,
        }
        await self.db[COLLECTION].update_one(
            {"owner_id": owner_id, "memory_ref": memory_ref, "category": doc["category"]},
            {"$set": doc},
            upsert=True,
        )
        saved = await self.db[COLLECTION].find_one({"id": memo_id}, {"_id": 0})
        return {"ok": True, "memo": _public(saved or doc)}

    async def reconcile_governed_memory(
        self, owner_id: str, *, old_ref: str, new_ref: Optional[str] = None,
    ) -> Dict[str, int]:
        """Preserve an already-authorized annual reminder across Memory corrections.

        This NEVER creates a reminder when no active reminder existed for the
        old owned memory. On forgetting, or a replacement of a different kind,
        disable the old schedule rather than notifying about a stale fact.
        New reminders inherit the original hour/timezone without overwriting
        a newer reminder the person already set for the replacement memory.
        """
        outcome = {"transferred": 0, "disabled": 0}
        if not owner_id or not old_ref or old_ref == new_ref:
            return outcome
        old_rows = await self.db[COLLECTION].find(
            {"owner_id": owner_id, "memory_ref": old_ref, "status": "active"},
            {"_id": 0},
        ).to_list(24)
        if not old_rows:
            return outcome

        old_memory = await self.db.memories.find_one(
            {"user_id": owner_id, "id": old_ref}, {"_id": 0, "kind": 1}
        )
        replacement = (
            await self.db.memories.find_one(
                {"user_id": owner_id, "id": new_ref, "status": "active"},
                {"_id": 0},
            )
            if new_ref else None
        )
        # If the target Memory was not committed yet (or was itself replaced),
        # never disable an authorized reminder as a fallback. Retry once the
        # authoritative replacement becomes available.
        if new_ref is not None and replacement is None:
            raise RuntimeError("MEMORY_REPLACEMENT_NOT_READY")
        kind = str((replacement or {}).get("kind") or "")
        value = (replacement or {}).get("value")
        if not isinstance(value, dict):
            value = {}
        allowed = bool(
            replacement and old_memory and kind == old_memory.get("kind")
            and kind in ("birthday", "anniversary", "annual_date")
        )
        try:
            month = int(value.get("month")) if allowed else 0
            day = int(value.get("day")) if allowed else 0
        except (TypeError, ValueError):
            month = day = 0
            allowed = False

        stamp = _now().isoformat()
        for memo in old_rows:
            category = str(memo.get("category") or "")
            target_doc = None
            if allowed and category in ("birthday", "anniversary", "annual_memo"):
                try:
                    hour = int(
                        memo["remind_hour_local"]
                        if memo.get("remind_hour_local") is not None else 9
                    )
                    timezone_name = str(memo.get("timezone") or "Europe/Rome")
                    due = _next_annual(
                        month=month, day=day, hour=hour,
                        timezone_name=timezone_name,
                    )
                    new_id = _stable_id(owner_id, str(new_ref), category)
                    target_doc = {
                        **{key: item for key, item in memo.items() if key != "_id"},
                        "id": new_id,
                        "memory_ref": str(new_ref),
                        "month": month, "day": day,
                        "person": str(value.get("person") or memo.get("person") or "")[:120],
                        "next_due_at": due.isoformat(),
                        "claim_until": "", "status": "active",
                        "last_fired_at": None, "last_fired_year": None,
                        "created_at": stamp, "updated_at": stamp,
                        "superseded_from": memo.get("id"),
                    }
                except (TypeError, ValueError):
                    target_doc = None
            if target_doc:
                lookup = {
                    "owner_id": owner_id, "memory_ref": str(new_ref),
                    "category": category,
                }
                # Idempotent insert; a later explicit user setting wins.
                await self.db[COLLECTION].update_one(
                    lookup, {"$setOnInsert": target_doc}, upsert=True
                )
                target = await self.db[COLLECTION].find_one(lookup, {"_id": 0, "id": 1})
                if not target:
                    # Do not disable the source if the replacement was not saved.
                    continue
                await self.db[COLLECTION].update_one(
                    {"id": memo.get("id"), "owner_id": owner_id,
                     "memory_ref": old_ref, "status": "active"},
                    {"$set": {
                        "status": "superseded", "claim_until": "",
                        "superseded_by": target["id"], "updated_at": stamp,
                    }},
                )
                outcome["transferred"] += 1
            else:
                await self.db[COLLECTION].update_one(
                    {"id": memo.get("id"), "owner_id": owner_id,
                     "memory_ref": old_ref, "status": "active"},
                    {"$set": {
                        "status": "disabled", "claim_until": "",
                        "disabled_reason": "source_memory_replaced_or_forgotten",
                        "updated_at": stamp,
                    }},
                )
                outcome["disabled"] += 1
        return outcome

    async def _claim_due(self, *, now: datetime) -> Optional[Dict[str, Any]]:
        stamp = now.isoformat()
        claim_until = (now + timedelta(seconds=CLAIM_SECONDS)).isoformat()
        return await self.db[COLLECTION].find_one_and_update(
            {
                "status": "active",
                "next_due_at": {"$lte": stamp},
                "$or": [
                    {"claim_until": {"$exists": False}},
                    {"claim_until": {"$lt": stamp}},
                ],
            },
            {"$set": {"claim_until": claim_until, "updated_at": stamp}},
            sort=[("next_due_at", 1)],
            return_document=True,
        )

    async def fire_due(self, *, now: Optional[datetime] = None, limit: int = 5) -> Dict[str, int]:
        from opportunities.models import EvidenceRef, Opportunity
        from opportunities.repository import OpportunityRepository

        moment = now or _now()
        out = {"due": 0, "raised": 0, "disabled": 0}
        repo = OpportunityRepository(self.db)
        for _ in range(max(1, min(int(limit or 1), 10))):
            memo = await self._claim_due(now=moment)
            if not memo:
                break
            out["due"] += 1
            memory = await self.db.memories.find_one(
                {"user_id": memo["owner_id"], "id": memo["memory_ref"], "status": "active"},
                {"_id": 0},
            )
            if not memory:
                previous = await self.db.memories.find_one(
                    {"user_id": memo["owner_id"], "id": memo["memory_ref"]},
                    {"_id": 0, "id": 1, "status": 1, "superseded_by": 1},
                )
                if previous and previous.get("status") == "superseded":
                    # An older Memory was replaced between claiming this due
                    # memo and reading it. Recover or defer, but NEVER send a
                    # false notification or discard its original authorization.
                    from memos.recovery import resolve_replacement

                    action, replacement_id = await resolve_replacement(
                        self.db, str(memo["owner_id"]), previous
                    )
                    if action != "defer":
                        await self.reconcile_governed_memory(
                            str(memo["owner_id"]), old_ref=str(memo["memory_ref"]),
                            new_ref=replacement_id if action == "transfer" else None,
                        )
                    continue
                await self.db[COLLECTION].update_one(
                    {"id": memo["id"]},
                    {"$set": {"status": "disabled", "claim_until": None,
                              "updated_at": moment.isoformat()}},
                )
                out["disabled"] += 1
                continue

            timezone_name = str(memo.get("timezone") or "Europe/Rome")
            reminder_hour = int(
                memo["remind_hour_local"] if memo.get("remind_hour_local") is not None else 9
            )
            # A corrected durable date is authoritative. A claimed old
            # occurrence must never announce the old birthday as "today".
            # Re-arm the same user-authorized reminder for the corrected date;
            # do not create a second memo or a second notification.
            remembered = memory.get("value") if isinstance(memory.get("value"), dict) else {}
            if remembered.get("month") is not None and remembered.get("day") is not None:
                try:
                    corrected_month = int(remembered["month"])
                    corrected_day = int(remembered["day"])
                    corrected_due = _next_annual(
                        month=corrected_month, day=corrected_day,
                        timezone_name=timezone_name, hour=reminder_hour, now=moment,
                    )
                except (TypeError, ValueError):
                    await self.db[COLLECTION].update_one(
                        {"id": memo["id"], "owner_id": memo["owner_id"],
                         "claim_until": memo.get("claim_until")},
                        {"$set": {"status": "disabled", "claim_until": "",
                                  "updated_at": moment.isoformat(),
                                  "disabled_reason": "invalid_memory_date"}},
                    )
                    out["disabled"] += 1
                    continue
                if (corrected_month, corrected_day) != (int(memo["month"]), int(memo["day"])):
                    await self.db[COLLECTION].update_one(
                        {"id": memo["id"], "owner_id": memo["owner_id"],
                         "claim_until": memo.get("claim_until")},
                        {"$set": {
                            "month": corrected_month, "day": corrected_day,
                            "person": str(remembered.get("person") or memo.get("person") or "")[:120],
                            "next_due_at": corrected_due.isoformat(),
                            "claim_until": "", "updated_at": moment.isoformat(),
                        }},
                    )
                    continue
            local = moment.astimezone(_zone(timezone_name))
            year = local.year
            # A missed run must not announce yesterday's (or last year's)
            # birthday as happening "today". Re-arm the next valid occurrence.
            if ((local.month, local.day) != (int(memo["month"]), int(memo["day"]))
                    or local.hour < reminder_hour):
                next_due = _next_annual(
                    month=int(memo["month"]), day=int(memo["day"]),
                    timezone_name=timezone_name, hour=reminder_hour, now=moment,
                )
                await self.db[COLLECTION].update_one(
                    {"id": memo["id"]},
                    {"$set": {
                        "next_due_at": next_due.isoformat(),
                        "claim_until": "",
                        "updated_at": moment.isoformat(),
                    }},
                )
                continue
            person = str(remembered.get("person") or memo.get("person") or "").strip()
            label = str(memo.get("label") or memory.get("statement") or "Promemoria").strip()
            if memo.get("category") == "birthday":
                title = f"Compleanno di {person}" if person else "Compleanno da ricordare"
                why = (
                    f"Oggi è il compleanno di {person}." if person
                    else "Oggi ricorre un compleanno che mi hai chiesto di ricordare."
                )
            else:
                title = label[:280]
                why = f"Oggi ricorre: {label}"[:400]

            opportunity = Opportunity(
                owner_id=memo["owner_id"],
                identity_key=f"recurring_memo:{memo['id']}:{year}",
                status="active",
                semantic_summary=title[:280],
                why_it_matters="Mi hai chiesto di ricordartelo ogni anno.",
                why_now=why[:400],
                relevance="high",
                urgency="urgent",
                time_sensitivity="perishable",
                confidence="strong",
                initiative="inform",
                what_ora_can_do="Ricordartelo oggi.",
                evidence=[
                    EvidenceRef(
                        kind="memory",
                        ref=str(memo["memory_ref"]),
                        summary=str(memory.get("statement") or label)[:240],
                    )
                ],
                source_context="recurring_memo",
                decision_provenance="user",
                valid_until=(local.replace(hour=23, minute=59, second=59, microsecond=0)).isoformat(),
                surface_state="surfaced",
                surface_rationale="Promemoria ricorrente richiesto dall'utente.",
            )
            await repo.save(opportunity)
            next_due = _next_annual(
                month=int(memo["month"]), day=int(memo["day"]),
                timezone_name=timezone_name,
                hour=reminder_hour,
                now=moment,
                after_year=year + 1,
            )
            await self.db[COLLECTION].update_one(
                {"id": memo["id"]},
                {"$set": {
                    "last_fired_at": moment.isoformat(),
                    "last_fired_year": year,
                    "next_due_at": next_due.isoformat(),
                    "claim_until": "",
                    "updated_at": moment.isoformat(),
                }},
            )
            out["raised"] += 1
        return out
