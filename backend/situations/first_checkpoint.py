"""Recover the FIRST checkpoint of an unattended real-life Situation.

The existing conversation and ambient lanes can create/repair a watch, but a
Situation with an attention purpose and *no first check at all* used to fall
through an opportunity review that could quite legitimately choose silence.
This separate admission to the SAME Situation/Agent/Ambient watch is needed.

No domain-specific timer, weather guess, new scheduler, or provider write:
the model decides whether/when a first evidence check is worth doing. Code
guards owner, source revision, lease, retry budget, timestamp and readback.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from situations.followup import arrange_followup, read_followup
from situations.repository import SituationRepository
from timezone_service import user_clock_context

logger = logging.getLogger("ora.situations.first_checkpoint")
COLLECTION = "situation_first_checkpoint_decisions"
MAX_PER_WAKE = 2
MAX_ATTEMPTS = 3
MODEL_TIMEOUT = 35
LEASE_SECONDS = 90

_SYSTEM = """You are ORA deciding whether an ALREADY PERSISTED, owner-verified
temporary Situation with a user-relevant attention purpose needs its FIRST
automatic follow-up. This is not a request to create another Situation or
claim that a physical outcome happened.

Decide from the supplied situation facts and the exact current clock.
No laundry-specific or domain-specific schedules. Do not infer location,
consent, weather, elapsed drying, completed delivery, provider availability,
or that a notification will reach a device.

A check_at is a time to re-evaluate evidence, NOT an estimated completion
time. You may schedule a bounded fresh-source check ONLY when it has a
concrete reason to be useful without asking the person an avoidable question.
If missing permissions/source/physical data make all checks useless, select
needs_input and explain exactly which missing fact matters. If no future
attention is justified, select no_benefit. Never schedule after the stated
temporal window has conclusively passed. Never invent a physical result.

Return JSON only:
{"decision":"schedule|needs_input|no_benefit",
 "check_at":"timezone-aware ISO 8601 for next EVIDENCE review, within 72h; only for schedule",
 "purpose":"why ORA will check, 300 chars max",
 "completion_when":"human outcome to evaluate, 400 chars max",
 "notify_when":"specific earlier exception that deserves attention, 400 chars max",
 "reason":"short, honest explanation, 260 chars max"}.
Never use a hardcoded cadence just to appear active. An empty or unusable
response is an unavailable model, NOT a decision to schedule."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(owner: str, sid: str, revision: int) -> str:
    # Canonical IDs are short/validated by the Situation repository; no title.
    return f"{owner}:{sid}:{revision}"


def _iso_at(raw) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return moment.astimezone(timezone.utc) if moment.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


async def _claim(db, owner: str, sid: str, revision: int, now: datetime) -> bool:
    """One worker per owner+Situation+revision; expiring claims retry at most 3x."""
    key = _key(owner, sid, revision)
    await db[COLLECTION].create_index([("owner_id", 1), ("status", 1), ("retry_after", 1)])
    try:
        await db[COLLECTION].insert_one({
            "_id": key, "owner_id": owner, "situation_id": sid,
            "revision": revision, "status": "processing",
            "attempts": 1,
            "retry_after": now + timedelta(seconds=LEASE_SECONDS),
            "created_at": now, "updated_at": now,
        })
        return True
    except DuplicateKeyError:
        pass
    resumed = await db[COLLECTION].find_one_and_update(
        {
            "_id": key, "owner_id": owner,
            "status": {"$in": ["processing", "retry"]},
            "retry_after": {"$lte": now},
            "attempts": {"$lt": MAX_ATTEMPTS},
        },
        {"$inc": {"attempts": 1},
         "$set": {"status": "processing",
                  "retry_after": now + timedelta(seconds=LEASE_SECONDS),
                  "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    return resumed is not None


async def _finish(db, owner: str, sid: str, revision: int, *, status: str,
                  reason: str = "", retry_after: datetime | None = None) -> None:
    if status == "retry":
        row = await db[COLLECTION].find_one(
            {"_id": _key(owner, sid, revision)}, {"_id": 0, "attempts": 1},
        )
        if int((row or {}).get("attempts") or 0) >= MAX_ATTEMPTS:
            status, retry_after = "paused", None
    await db[COLLECTION].update_one(
        {"_id": _key(owner, sid, revision),
         "owner_id": owner, "status": "processing"},
        {"$set": {
            "status": status,
            "reason": " ".join(str(reason).split())[:260],
            "retry_after": retry_after,
            "updated_at": _now(),
        }},
    )


async def decision_for(db, owner: str, sid: str, revision: int) -> dict | None:
    """Read only this person's current-revision admission; never expose a model dump."""
    if db is None or not owner or not sid:
        return None
    row = await db[COLLECTION].find_one({
        "_id": _key(owner, sid, revision), "owner_id": owner,
    }, {"_id": 0, "status": 1, "reason": 1, "retry_after": 1, "updated_at": 1})
    if not row:
        return None
    for name in ("retry_after", "updated_at"):
        if isinstance(row.get(name), datetime):
            row[name] = row[name].isoformat()
    return row


async def review_unattended(db, owner: str, *, limit: int = MAX_PER_WAKE) -> dict:
    """One bounded pass on an ambient wake; only user-owned active Situations."""
    stats = {"eligible": 0, "scheduled": 0, "needs_input": 0,
             "no_benefit": 0, "retry": 0, "skipped": 0}
    if db is None or not owner:
        return stats

    situations = await db.situations.find(
        {
            "user_id": owner, "status": {"$in": ["active", "changed"]},
            "$or": [{"attention_intent": {"$type": "string", "$gt": ""}},
                    {"next_check_summary": {"$type": "string", "$gt": ""}}],
        },
        {"_id": 0, "id": 1, "revision": 1},
    ).sort("updated_at", -1).limit(8).to_list(8)

    for ref in situations:
        if stats["eligible"] >= max(1, min(limit, MAX_PER_WAKE)):
            break
        sid = str(ref.get("id") or "")
        situation = await SituationRepository(db).get(owner, sid)
        if not situation or situation.status not in ("active", "changed"):
            continue
        if not (situation.attention_intent or situation.next_check_summary):
            continue
        state = await read_followup(db, owner, sid)
        if state["status"] != "not_scheduled":
            stats["skipped"] += 1
            continue
        if not await _claim(db, owner, sid, situation.revision, _now()):
            stats["skipped"] += 1
            continue
        stats["eligible"] += 1
        try:
            clock = await user_clock_context(db, owner)
            safe_context = {
                "now": clock.get("local_datetime"),
                "timezone": clock.get("timezone"),
                "situation": {
                    "ref": f"situation:{sid}", "revision": situation.revision,
                    "summary": situation.summary[:250],
                    "temporal_scope": situation.temporal_scope,
                    "attention_intent": situation.attention_intent,
                    "next_check_summary": situation.next_check_summary,
                    "current_state": situation.current_state_summary,
                    "expected_outcome": situation.expected_outcome_summary,
                    "place_label": situation.location_label,
                    "facts": situation.facts[:5],
                    "assumptions": situation.assumptions[:4],
                    "constraints": situation.constraints[:5],
                    "source_refs": situation.source_refs[:6],
                    "confirmed_places": situation.linked_object_refs[:5],
                    "created_at": situation.created_at,
                },
                "available_observations": (
                    "The Situation and current clock are verified. Live weather, "
                    "provider health, physical outcome and push reachability "
                    "have NOT been read during this admission."
                ),
            }
            from research.reasoning import _ask_model
            answer = await asyncio.wait_for(
                _ask_model(_SYSTEM, json.dumps(safe_context, ensure_ascii=False, default=str)),
                timeout=MODEL_TIMEOUT,
            )
            if not isinstance(answer, dict):
                await _finish(db, owner, sid, situation.revision,
                              status="retry", reason="modello non disponibile",
                              retry_after=_now()+timedelta(minutes=5))
                stats["retry"] += 1
                continue
            kind = str(answer.get("decision") or "").strip().lower()
            reason = str(answer.get("reason") or "")[:260]
            if kind in ("needs_input", "no_benefit"):
                await _finish(db, owner, sid, situation.revision,
                              status=kind, reason=reason)
                stats[kind] += 1
                continue
            if kind != "schedule":
                await _finish(db, owner, sid, situation.revision,
                              status="retry", reason="risposta del modello non valida",
                              retry_after=_now()+timedelta(minutes=5))
                stats["retry"] += 1
                continue

            target = _iso_at(answer.get("check_at"))
            actual = _now()
            if (target is None or target < actual + timedelta(seconds=60)
                    or target > actual + timedelta(hours=72)):
                await _finish(db, owner, sid, situation.revision,
                              status="needs_input",
                              reason="nessun orario futuro valido verificato dal modello")
                stats["needs_input"] += 1
                continue
            purpose = str(answer.get("purpose") or "").strip()[:300]
            completion = str(answer.get("completion_when") or "").strip()[:400]
            notify = str(answer.get("notify_when") or "").strip()[:400]
            if not purpose or not completion or not notify:
                await _finish(db, owner, sid, situation.revision,
                              status="needs_input",
                              reason="mancano scopo, condizione di esito o condizione di avviso")
                stats["needs_input"] += 1
                continue

            # Revisions/cancellation can race the model's deliberation.
            fresh = await SituationRepository(db).get(owner, sid)
            if not fresh or fresh.revision != situation.revision or fresh.status not in ("active", "changed"):
                await _finish(db, owner, sid, situation.revision,
                              status="obsolete", reason="la situazione è cambiata")
                stats["skipped"] += 1
                continue
            arranged = await arrange_followup(
                db, owner, situation_id=sid, expected_revision=situation.revision,
                check_at=target.isoformat(), purpose=purpose,
                notify_when=notify, completion_when=completion,
            )
            confirmed = (arranged.get("ok") is True
                         and arranged.get("status") in ("scheduled", "due", "running")
                         and bool(arranged.get("next_check_at")))
            if confirmed:
                await _finish(db, owner, sid, situation.revision,
                              status="scheduled", reason="checkpoint persistito e riletto")
                stats["scheduled"] += 1
            else:
                await _finish(db, owner, sid, situation.revision,
                              status="retry", reason=str(arranged.get("error") or "non verificato"),
                              retry_after=_now()+timedelta(minutes=5))
                stats["retry"] += 1
        except Exception as exc:
            logger.warning("first checkpoint admission soft-fail type=%s", type(exc).__name__)
            await _finish(db, owner, sid, situation.revision,
                          status="retry", reason="errore tecnico durante la programmazione",
                          retry_after=_now()+timedelta(minutes=5))
            stats["retry"] += 1

    return stats
