"""
ORA checks its own work, and repairs what it safely can.

24/10/2026, one afternoon, one load of laundry: a watch paused with no next
check, a readiness refused for a reading one minute old, notifications that
expired "while ORA was stopped". Every one was found by a person reading logs.
A system that promises to keep an eye on things has to keep an eye on itself.

Every pass (a few times an hour, in the maintenance lane):

* a Situation watch that is open but has no live alarm is re-armed — at the
  time it had already chosen, or in a few minutes when it never chose one.
  It never invents a judgement: the re-armed check runs the ordinary reasoning;
* a watch whose alarm is long overdue is reported (the runtime is stuck);
* a notification still pending well past its moment is reported, and so is
  one that expired unsent today;
* somebody with things ORA would notify but no device that can receive them
  is reported;
* an appointment in the next hours that nothing is looking at (no review, no
  departure alarm) gets one review arranged an hour before it. The review
  decides whether there is anything to say: the self-check never does.

What it found is written down per person (ops_self_checks), bounded, with no
personal content — codes and references only — so ORA, the app and the person
can see that the watch is being watched.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_OWNERS_PER_PASS = 50
REARM_AFTER_MINUTES = 5
OVERDUE_MINUTES = 20
DELIVERY_LATE_MINUTES = 30
KEEP_REPORTS = 48
# A result told days ago is history; a question unanswered for two weeks is
# no longer something ORA should keep putting in front of the person.
RESULT_STALE_HOURS = 48
QUESTION_STALE_DAYS = 14
RESULT_KINDS = {"useful_result", "important_outcome"}
QUESTION_KINDS = {"needs_information", "needs_authority"}
# An appointment closer than this is looked at before it starts.
EVENT_LOOKAHEAD_HOURS = 3
EVENT_REVIEW_BEFORE_MINUTES = 60
EVENT_TOO_CLOSE_MINUTES = 15
EVENT_WAKE_PREFIX = "calendar_event_due:"


def _moment(value) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _rearm(db, owner: str, goal: dict, now: datetime) -> Optional[str]:
    from agent.repository import AgentRepository
    from ambient.service import AmbientService

    planned = _moment(goal.get("next_run_at"))
    when = planned if planned and planned > now else now + timedelta(minutes=REARM_AFTER_MINUTES)
    alarm = await AmbientService(db).schedule(
        owner, reason="opportunity_revisit", when=when,
        source_ref=f"goal:{goal['id']}", provenance="code_schedule",
    )
    if alarm is None:
        return None
    repo = AgentRepository(db)
    latest = await repo.get_goal(owner, goal["id"])
    if latest is None or not latest.is_open:
        return None
    latest.next_run_at = alarm.scheduled_for
    # Production 25/10 16:30-17:10: the watch had used its three background
    # runs, so every re-armed alarm was refused on arrival ("background
    # budget") and the clothes were never announced. A re-arm by the self-check
    # is at most one every quarter of an hour: it restores the budget and the
    # waiting state the worker expects, otherwise the repair is only cosmetic.
    latest.background_runs = 0
    if latest.status == "active":
        latest.status = "waiting"
    await repo.save_goal(latest)
    await repo.journal(owner, goal["id"], kind="situation_checkpoint_repaired",
                       note="Controllo automatico di ORA: sorveglianza riattivata.",
                       detail={"by": "self_check", "at": alarm.scheduled_for})
    return alarm.scheduled_for


async def check_owner(db, owner: str, *, now: Optional[datetime] = None) -> dict[str, Any]:
    from situations.followup import INITIAL_KIND, KIND, OPEN, read_followup
    from situations.repository import SituationRepository

    now = now or datetime.now(timezone.utc)
    findings: list[dict] = []
    goals = await db.agent_goals.find(
        {"owner_id": owner, "source_kind": {"$in": [KIND, INITIAL_KIND]}, "status": {"$in": list(OPEN)},
         "requires_user_input": {"$ne": True}, "requires_user_authority": {"$ne": True}},
        {"_id": 0, "id": 1, "next_run_at": 1, "source_refs": 1},
    ).to_list(20)
    for goal in goals:
        refs = [str(r).split(":", 1)[1] for r in goal.get("source_refs") or [] if str(r).startswith("situation:")]
        if len(refs) != 1:
            continue
        situation = await SituationRepository(db).get(owner, refs[0])
        if not situation or situation.status not in ("active", "changed"):
            continue
        state = await read_followup(db, owner, refs[0])
        status = state.get("status")
        if status in ("not_scheduled", "recovery_pending"):
            at = await _rearm(db, owner, goal, now)
            findings.append({"code": "watch_without_alarm", "ref": f"goal:{goal['id']}",
                             "repaired": bool(at), "next_check_at": at})
            continue
        due = _moment(goal.get("next_run_at"))
        if status == "due" and due and now - due > timedelta(minutes=OVERDUE_MINUTES):
            findings.append({"code": "watch_overdue", "ref": f"goal:{goal['id']}", "repaired": False,
                             "late_minutes": int((now - due).total_seconds() // 60)})

    findings.extend(await _retire_stale_needs(db, owner, now))
    try:
        findings.extend(await _attend_upcoming_events(db, owner, now))
    except Exception as exc:
        logger.info("self_check events deferred: %s", type(exc).__name__)
    try:
        from situations.closing import close_finished
        findings.extend(await close_finished(db, owner, now=now))
        from situations.outdoor_drying import plan_missing, replan_due
        findings.extend(await plan_missing(db, owner, now=now))
        findings.extend(await replan_due(db, owner, now=now))
    except Exception as exc:
        logger.info("self_check drying deferred: %s", type(exc).__name__)
    try:
        findings.extend(await _review_near_deadlines(db, owner, now))
    except Exception as exc:
        logger.info("self_check deadlines deferred: %s", type(exc).__name__)

    plans = await db.delivery_plans.find(
        {"owner_id": owner, "created_at": {"$gte": (now - timedelta(hours=24)).isoformat()}},
        {"_id": 0, "id": 1, "status": 1, "not_before": 1, "rationale": 1, "mode": 1},
    ).to_list(50)
    for plan in plans:
        moment = _moment(plan.get("not_before"))
        if plan.get("status") == "pending" and moment and now - moment > timedelta(minutes=DELIVERY_LATE_MINUTES):
            findings.append({"code": "delivery_late", "ref": f"delivery:{plan['id']}", "repaired": False})
        elif plan.get("status") == "expired" and "ferma" in str(plan.get("rationale") or ""):
            findings.append({"code": "delivery_missed_while_stopped", "ref": f"delivery:{plan['id']}",
                             "repaired": False})

    wants_push = any(p.get("mode") == "push" for p in plans) or bool(goals)
    if wants_push:
        reachable = await db.push_endpoints.count_documents(
            {"$or": [{"owner_id": owner}, {"user_id": owner}], "status": "active"})
        if not reachable:
            findings.append({"code": "no_device_for_notifications", "ref": f"owner:{owner}", "repaired": False})

    report = {
        "owner_id": owner, "at": now.isoformat(),
        "watches": len(goals), "findings": findings,
        "repaired": sum(1 for f in findings if f.get("repaired")),
        "healthy": not any(not f.get("repaired") for f in findings),
    }
    await db.ops_self_checks.insert_one(dict(report))
    old = await db.ops_self_checks.find({"owner_id": owner}, {"_id": 1}).sort("at", -1).skip(KEEP_REPORTS).to_list(200)
    if old:
        await db.ops_self_checks.delete_many({"_id": {"$in": [d["_id"] for d in old]}})
    if findings:
        logger.info("self_check owner=%s findings=%s", owner[:8],
                    ",".join(f"{f['code']}:{'fixed' if f.get('repaired') else 'open'}" for f in findings))
    return report


async def _attend_upcoming_events(db, owner: str, now: datetime) -> list[dict]:
    """
    An appointment in a few hours must be looked at by somebody.

    Audit 26/10: only appointments with a place got an alarm (the departure
    estimate). "Chiamata con il commercialista alle 15" had none: unless
    something else happened that day, no review ran before it and ORA said
    nothing. One review, an hour before; whether it becomes a notification is
    the ordinary judgement's to decide.
    """
    from ambient.service import AmbientService
    from opportunities.snapshot import _calendar

    out: list[dict] = []
    for event in await _calendar(db, owner, now):
        if event.get("all_day"):
            continue
        start = _moment(event.get("starts_at"))
        ref = str(event.get("ref") or "")
        if not ref or start is None:
            continue
        ahead = start - now
        if ahead <= timedelta(minutes=EVENT_TOO_CLOSE_MINUTES) or ahead > timedelta(hours=EVENT_LOOKAHEAD_HOURS):
            continue
        wake_ref = f"{EVENT_WAKE_PREFIX}{ref}"[:120]
        watched = await db.ambient_wakes.count_documents(
            {"owner_id": owner, "status": {"$ne": "cancelled"},
             "source_ref": {"$in": [wake_ref, f"calendar_departure_due:{ref}"[:120]]}}, limit=1)
        if watched:
            continue
        when = max(now + timedelta(minutes=2), start - timedelta(minutes=EVENT_REVIEW_BEFORE_MINUTES))
        wake = await AmbientService(db).schedule(
            owner, reason="ambient_review", when=when,
            source_ref=wake_ref, provenance="code_schedule",
        )
        out.append({"code": "event_unattended", "ref": f"event:{ref[:80]}",
                    "repaired": wake is not None,
                    "next_check_at": getattr(wake, "scheduled_for", None)})
    return out


def deadline_moments(due: datetime, date_only: bool, local_now: datetime) -> list[tuple[str, datetime]]:
    """When a deadline deserves a look: the evening before and the morning of
    (a bare date), or the evening before and two hours before (a time)."""
    tz = local_now.tzinfo
    day = due.astimezone(tz).date()
    eve = datetime.combine(day - timedelta(days=1), datetime.min.time(), tzinfo=tz).replace(hour=18)
    if date_only:
        morning = datetime.combine(day, datetime.min.time(), tzinfo=tz).replace(hour=9)
        return [("eve", eve), ("morning", morning)]
    return [("eve", eve), ("before", due - timedelta(hours=2))]


async def _review_near_deadlines(db, owner: str, now: datetime) -> list[dict]:
    """
    A deadline the person set gets looked at before it passes.

    Audit 26/10: plan steps and decisions with a date were only titles in
    Home; no review ever saw the date. Now the review sees it (snapshot
    `deadlines`) and this makes sure one actually runs at the useful moments.
    Whether to say anything is, as always, the review's call.
    """
    from ambient.service import AmbientService
    from opportunities.deadlines import upcoming
    from timezone_service import user_clock_context

    clock = await user_clock_context(db, owner, now=now)
    local_now = datetime.fromisoformat(clock["local_datetime"])
    out: list[dict] = []
    for row in await upcoming(db, owner, local_now, days=2):
        for label, moment in deadline_moments(row["due"], row["date_only"], local_now):
            if not (now < moment <= now + timedelta(hours=EVENT_LOOKAHEAD_HOURS)):
                continue
            wake_ref = f"deadline_due:{row['ref']}:{label}:{moment.date().isoformat()}"[:120]
            if await db.ambient_wakes.count_documents(
                    {"owner_id": owner, "source_ref": wake_ref, "status": {"$ne": "cancelled"}}, limit=1):
                continue
            wake = await AmbientService(db).schedule(
                owner, reason="ambient_review", when=moment.astimezone(timezone.utc),
                source_ref=wake_ref, provenance="code_schedule",
            )
            out.append({"code": "deadline_unattended", "ref": row["ref"][:100],
                        "repaired": wake is not None,
                        "next_check_at": getattr(wake, "scheduled_for", None)})
    return out


async def _retire_stale_needs(db, owner: str, now: datetime) -> list[dict]:
    """
    What Home asks the person must still be true.

    Production 25/10: "Serve te" still showed a trip of 20/09, a medical visit
    of 12/10 "oggi alle 13:30", the address for laundry from a closed
    situation and a parking that expired the night before. A need is retired
    when its work ended, when the situation it was about is over, when it
    reported a result more than two days ago, or when a question went two
    weeks without an answer. Retired, not deleted: it stays in the history.
    """
    from agent.needs import NeedService
    from situations.repository import SituationRepository

    service = NeedService(db)
    rows = await db.agent_needs.find({"owner_id": owner, "status": "open"},
                                     {"_id": 0, "id": 1, "goal_id": 1, "kind": 1, "created_at": 1}).to_list(50)
    out: list[dict] = []
    goals: dict[str, Optional[dict]] = {}
    for need in rows:
        gid = need.get("goal_id") or ""
        if gid not in goals:
            goals[gid] = await db.agent_goals.find_one(
                {"owner_id": owner, "id": gid}, {"_id": 0, "status": 1, "source_refs": 1}) if gid else None
        goal = goals[gid]
        why = None
        if goal is None or goal.get("status") in ("completed", "cancelled", "failed", "abandoned"):
            why = "il lavoro a cui si riferiva è finito"
        else:
            refs = [str(r).split(":", 1)[1] for r in goal.get("source_refs") or [] if str(r).startswith("situation:")]
            if refs:
                situation = await SituationRepository(db).get(owner, refs[0])
                if situation is None or situation.status not in ("active", "changed"):
                    why = "la situazione a cui si riferiva è conclusa"
        created = _moment(need.get("created_at"))
        if why is None and created:
            age = now - created
            if need.get("kind") in RESULT_KINDS and age > timedelta(hours=RESULT_STALE_HOURS):
                why = "risultato già comunicato da più di due giorni"
            elif need.get("kind") in QUESTION_KINDS and age > timedelta(days=QUESTION_STALE_DAYS):
                why = "domanda rimasta senza risposta per due settimane"
        if why is None:
            continue
        await service.cancel(owner, need["id"], how=why, by="code")
        out.append({"code": "need_retired", "ref": f"need:{need['id']}", "repaired": True})
    return out


async def run(db, *, now: Optional[datetime] = None) -> dict[str, Any]:
    from situations.followup import INITIAL_KIND, KIND, OPEN

    now = now or datetime.now(timezone.utc)
    owners = await db.agent_goals.distinct(
        "owner_id", {"source_kind": {"$in": [KIND, INITIAL_KIND]}, "status": {"$in": list(OPEN)}})
    recent = await db.delivery_plans.distinct(
        "owner_id", {"created_at": {"$gte": (now - timedelta(hours=24)).isoformat()}})
    # People ORA can reach: their appointments are worth a look even when no
    # watch or notification is open.
    reachable: list = []
    for field in ("owner_id", "user_id"):
        try:
            reachable += await db.push_endpoints.distinct(field, {"status": "active"})
        except Exception:
            pass
    summary = {"owners": 0, "findings": 0, "repaired": 0}
    for owner in list(dict.fromkeys([*owners, *recent, *[r for r in reachable if r]]))[:MAX_OWNERS_PER_PASS]:
        try:
            report = await check_owner(db, owner, now=now)
        except Exception as exc:
            logger.info("self_check deferred owner=%s kind=%s", str(owner)[:8], type(exc).__name__)
            continue
        summary["owners"] += 1
        summary["findings"] += len(report["findings"])
        summary["repaired"] += report["repaired"]
    logger.info("self_check pass %s", summary)
    return summary


async def latest(db, owner: str) -> Optional[dict]:
    doc = await db.ops_self_checks.find_one({"owner_id": owner}, {"_id": 0, "owner_id": 0}, sort=[("at", -1)])
    return doc
