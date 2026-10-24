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
  is reported.

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


async def run(db, *, now: Optional[datetime] = None) -> dict[str, Any]:
    from situations.followup import INITIAL_KIND, KIND, OPEN

    now = now or datetime.now(timezone.utc)
    owners = await db.agent_goals.distinct(
        "owner_id", {"source_kind": {"$in": [KIND, INITIAL_KIND]}, "status": {"$in": list(OPEN)}})
    recent = await db.delivery_plans.distinct(
        "owner_id", {"created_at": {"$gte": (now - timedelta(hours=24)).isoformat()}})
    summary = {"owners": 0, "findings": 0, "repaired": 0}
    for owner in list(dict.fromkeys([*owners, *recent]))[:MAX_OWNERS_PER_PASS]:
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
