"""Real study-plan ↔ Google Calendar sync verification.

Uses the same service paths as the UI (confirm sync, snooze, delete plan).
Never prints tokens/secrets. Cleans up synthetic Google events.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

EVIDENCE = ROOT.parent / "frontend" / "test-results" / "study-google-sync" / "verify-report.json"


def _mint_token(user_id: str) -> str:
    import jwt as pyjwt
    from deps import JWT_SECRET, JWT_ALGO, JWT_EXPIRY_DAYS

    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def pick_user(db):
    from connectors.google_calendar.scopes import CONNECTOR_ID

    # Prefer real Gmail accounts with calendar.events (manual connect).
    candidates = await db.connector_instances.find(
        {"connector_id": CONNECTOR_ID, "status": "connected"},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(30)
    inst = None
    for c in candidates:
        scopes = c.get("authorized_scopes") or []
        label = (c.get("display_label") or "") + " " + str((c.get("metadata") or {}).get("account_email") or "")
        if "calendar.events" not in " ".join(scopes):
            continue
        if "francesconicolocefala" in label.lower() or "@gmail.com" in label.lower():
            # Prefer non-test synthetic labels
            if label.startswith("d") and "_178" in label:
                continue
            if label.startswith("a") and "_178" in label:
                continue
            if label.startswith("multi_"):
                continue
            if label.startswith("user_"):
                continue
            inst = c
            break
    if not inst:
        for c in candidates:
            if "calendar.events" in " ".join(c.get("authorized_scopes") or []):
                inst = c
                break
    if not inst:
        raise RuntimeError("No connected calendar_google instance with calendar.events")
    uid = inst["user_id"]
    user = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1})
    email = (user or {}).get("email") or (inst.get("metadata") or {}).get("account_email") or inst.get("display_label")
    scopes = inst.get("authorized_scopes") or []
    return uid, email, inst, scopes


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    from action_engine.study.google_sync import (
        delete_plan_google_events,
        fetch_google_event,
        is_google_connected,
        sync_plan_sessions,
        update_session_google_event,
    )
    from action_engine.study.models import StudyPlan, StudySessionItem
    from action_engine.study.plan_service import StudyPlanService
    from connectors.google_calendar.scopes import CONNECTOR_ID
    from deps import db, get_google_calendar_service, life_graph, knowledge

    report: dict = {"ok": False, "steps": []}

    def step(name, **kw):
        report["steps"].append({"step": name, **kw})
        print(f"STEP {name}: {json.dumps({k: v for k, v in kw.items() if k != 'detail'}, default=str)}")

    uid, email, inst, scopes = await pick_user(db)
    report["account_email"] = email
    report["user_id"] = uid
    report["instance_id"] = inst.get("id")
    report["connector_id"] = inst.get("connector_id")

    connected = await is_google_connected(db, uid)
    step("is_google_connected", ok=connected, connector_id=CONNECTOR_ID)
    if not connected:
        report["error"] = "is_google_connected false — wrong connector_id lookup?"
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    has_events = any("calendar.events" in s for s in scopes)
    has_list = any("calendarlist.readonly" in s for s in scopes)
    vault_ok = bool(inst.get("secret_reference"))
    step(
        "scopes_and_vault",
        has_calendar_events=has_events,
        has_calendarlist_readonly=has_list,
        vault_secret_ref=vault_ok,
        scopes_count=len(scopes),
    )
    if not has_events or not vault_ok:
        report["error"] = "missing calendar.events scope or vault"
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    gcal = get_google_calendar_service()
    access = await gcal._get_access_token(user_id=uid, instance=inst)
    cals = await gcal.provider.list_calendars(access_token=access)
    primary = next((c for c in cals if c.primary), cals[0] if cals else None)
    if not primary:
        report["error"] = "no calendars accessible"
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1
    cal_id = primary.id
    report["calendar_id"] = cal_id
    report["calendar_summary"] = primary.summary
    step("default_calendar", calendar_id=cal_id, summary=primary.summary, calendars=len(cals))

    # Synthetic plan: one session tomorrow afternoon (Europe/Rome intent, UTC store)
    now = datetime.now(timezone.utc)
    start = (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=60)
    tag = uuid.uuid4().hex[:8]
    exam = f"ORA_VERIFY_StudySync_{tag}"
    plan = StudyPlan(
        user_id=uid,
        status="active",
        exam_name=exam,
        subject="Verifica sync",
        exam_date=(now + timedelta(days=14)).isoformat(),
        timezone="Europe/Rome",
        calendar_sync=True,
        intensity="distributed",
        daily_minutes=60,
    )
    session = StudySessionItem(
        plan_id=plan.id,
        user_id=uid,
        title=f"Studio: {exam}",
        topic="Sessione sintetica verifica Google",
        starts_at=start.isoformat(),
        ends_at=end.isoformat(),
        duration_minutes=60,
        status="planned",
        session_type="study",
    )
    plan.sessions = [session]
    await db.study_plans.insert_one(plan.model_dump())
    await db.study_sessions.insert_one(session.model_dump())
    report["plan_id"] = plan.id
    report["session_id"] = session.id
    step("plan_seeded", plan_id=plan.id, session_id=session.id, starts_at=session.starts_at)

    sync = await sync_plan_sessions(
        db=db,
        user_id=uid,
        plan=plan.model_dump(),
        sessions=[session.model_dump()],
    )
    await db.study_plans.update_one(
        {"id": plan.id},
        {"$set": {"google_sync": sync, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    step(
        "sync_create",
        connected=sync.get("connected"),
        synced=len(sync.get("synced") or []),
        failed=sync.get("failed"),
        calendar_id=sync.get("calendar_id"),
    )

    sess = await db.study_sessions.find_one({"id": session.id}, {"_id": 0})
    eid = (sess or {}).get("google_event_id")
    gcal_id = (sess or {}).get("google_calendar_id")
    status = (sess or {}).get("google_sync_status")
    report["google_event_id"] = eid
    report["google_calendar_id"] = gcal_id
    report["sync_status"] = status
    if not eid or status != "synced":
        report["error"] = "create sync failed"
        # cleanup plan rows
        await db.study_plans.delete_one({"id": plan.id})
        await db.study_sessions.delete_one({"id": session.id})
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    ev = await fetch_google_event(db, uid, calendar_id=gcal_id, event_id=eid)
    if not ev:
        report["error"] = "event not readable from Google API"
        await delete_plan_google_events(db, uid, plan.id)
        await db.study_plans.delete_one({"id": plan.id})
        await db.study_sessions.delete_one({"id": session.id})
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    ev_start = (ev.get("start") or {}).get("dateTime")
    ev_end = (ev.get("end") or {}).get("dateTime")
    ev_tz = (ev.get("start") or {}).get("timeZone")
    report["google_event"] = {
        "summary": ev.get("summary"),
        "start": ev_start,
        "end": ev_end,
        "timeZone": ev_tz,
        "status": ev.get("status"),
    }
    title_ok = exam in (ev.get("summary") or "")
    # Allow timezone offset differences — compare instant
    start_ok = False
    try:
        gs = datetime.fromisoformat(ev_start.replace("Z", "+00:00"))
        start_ok = abs((gs - start).total_seconds()) < 120
    except Exception:
        start_ok = False
    step(
        "google_get_after_create",
        title_ok=title_ok,
        start_ok=start_ok,
        summary=ev.get("summary"),
        start=ev_start,
        timeZone=ev_tz,
        sync_status=status,
    )

    # Duplicate check: list events in window, count matching summary
    page = await gcal.provider.list_events(
        access_token=access,
        calendar_id=gcal_id,
        time_min=(start - timedelta(hours=1)).isoformat(),
        time_max=(end + timedelta(hours=1)).isoformat(),
        max_results=50,
    )
    matches = [e for e in (page.events or []) if exam in (e.get("summary") or "")]
    report["duplicate_count"] = len(matches)
    step("no_duplicates", count=len(matches), ok=len(matches) == 1)

    # Update via plan_service snooze (same path as UI session action)
    svc = StudyPlanService(db, life_graph=life_graph, knowledge=knowledge)
    snooze = await svc.session_action(uid, session.id, "snooze", snooze_minutes=90)
    report["update_api"] = {
        "ok": snooze.get("ok"),
        "google_sync": snooze.get("google_sync"),
        "new_starts_at": (snooze.get("session") or {}).get("starts_at"),
    }
    step(
        "snooze_update",
        ok=bool((snooze.get("google_sync") or {}).get("ok")),
        google=snooze.get("google_sync"),
    )

    sess2 = await db.study_sessions.find_one({"id": session.id}, {"_id": 0})
    ev2 = await fetch_google_event(db, uid, calendar_id=gcal_id, event_id=eid)
    new_start = datetime.fromisoformat(sess2["starts_at"].replace("Z", "+00:00"))
    ev2_start = ((ev2 or {}).get("start") or {}).get("dateTime")
    update_ok = False
    if ev2_start:
        gs2 = datetime.fromisoformat(ev2_start.replace("Z", "+00:00"))
        update_ok = abs((gs2 - new_start).total_seconds()) < 120
    report["update_result"] = {
        "ok": update_ok,
        "session_starts_at": sess2.get("starts_at"),
        "google_start": ev2_start,
        "google_sync_status": sess2.get("google_sync_status"),
    }
    step("google_get_after_update", ok=update_ok, google_start=ev2_start)

    # Delete via plan_service.delete_plan (same as UI plan-delete)
    deleted = await svc.delete_plan(uid, plan.id, soft=True)
    report["delete_api"] = deleted
    await asyncio.sleep(1.0)
    ev3 = await fetch_google_event(db, uid, calendar_id=gcal_id, event_id=eid)
    gone = ev3 is None or (ev3 or {}).get("status") == "cancelled"
    report["delete_result"] = {"ok": gone, "google_status": (ev3 or {}).get("status") if ev3 else "not_found"}
    step("google_after_delete", gone=gone, status=(ev3 or {}).get("status") if ev3 else "not_found")

    # Hard cleanup residual rows
    await db.study_plans.delete_one({"id": plan.id})
    await db.study_sessions.delete_one({"id": session.id})

    report["ok"] = bool(
        connected and has_events and vault_ok and eid and status == "synced"
        and title_ok and start_ok and len(matches) == 1 and update_ok and gone
    )
    EVIDENCE.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("RESULT", "PASS" if report["ok"] else "FAIL")
    print(f"evidence={EVIDENCE}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
