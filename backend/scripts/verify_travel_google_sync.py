"""Real Travel Project ↔ Google Calendar sync verification.

Confirm path with calendar_sync=True → create vacation/outbound/return →
verify google_event_ids → cleanup with delete_project(cleanup_google=True).
Never prints tokens/secrets.
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

EVIDENCE = (
    ROOT.parent / "frontend" / "e2e-evidence" / "travel-action-flow" / "google-verify-report.json"
)


async def pick_user(db):
    from connectors.google_calendar.scopes import CONNECTOR_ID

    candidates = await db.connector_instances.find(
        {"connector_id": CONNECTOR_ID, "status": {"$in": ["connected", "active", "authorized"]}},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(40)

    preferred = None
    for c in candidates:
        scopes = c.get("authorized_scopes") or []
        if "calendar.events" not in " ".join(scopes):
            continue
        meta = c.get("metadata") or {}
        label = f"{c.get('display_label') or ''} {meta.get('account_email') or ''}".lower()
        if "francesconicolocefala" in label:
            preferred = c
            break
        if preferred is None and "@gmail.com" in label:
            # skip synthetic test labels
            if any(label.startswith(p) for p in ("d", "a", "multi_", "user_")) and "_178" in label:
                continue
            preferred = c
    if not preferred:
        for c in candidates:
            if "calendar.events" in " ".join(c.get("authorized_scopes") or []):
                preferred = c
                break
    if not preferred:
        return None, None, None, []

    uid = preferred["user_id"]
    user = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1})
    email = (
        (user or {}).get("email")
        or (preferred.get("metadata") or {}).get("account_email")
        or preferred.get("display_label")
    )
    return uid, email, preferred, preferred.get("authorized_scopes") or []


async def fetch_google_event(db, user_id: str, *, calendar_id: str, event_id: str):
    from action_engine.study.google_sync import fetch_google_event as _fetch

    return await _fetch(db, user_id, calendar_id=calendar_id, event_id=event_id)


async def main() -> int:
    from motor.motor_asyncio import AsyncIOMotorClient
    from action_engine.models import AnswerBody, OpenBody
    from action_engine.service import ActionEngineService
    from action_engine.travel.google_sync import is_google_connected
    from connectors.google_calendar.scopes import CONNECTOR_ID
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService
    from decision_engine import DecisionService

    mongo = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    dbname = os.environ.get("DB_NAME", "ora")
    client = AsyncIOMotorClient(mongo)
    db = client[dbname]

    report: dict = {"ok": False, "steps": [], "db": dbname, "connector_id": CONNECTOR_ID}
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)

    def step(name, **kw):
        report["steps"].append({"step": name, **kw})
        safe = {k: v for k, v in kw.items() if "token" not in k.lower() and "secret" not in k.lower()}
        print(f"STEP {name}: {json.dumps(safe, default=str)}")

    uid, email, inst, scopes = await pick_user(db)
    if not uid:
        report["error"] = "no_connected_calendar_google"
        report["google_available"] = False
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("GOOGLE_UNAVAILABLE: no connected calendar_google with calendar.events")
        client.close()
        return 2

    report["account_email"] = email
    report["user_id"] = uid
    report["instance_id"] = inst.get("id")
    report["google_available"] = True

    connected = await is_google_connected(db, uid)
    vault_ok = bool(inst.get("secret_reference"))
    has_events = "calendar.events" in " ".join(scopes)
    step(
        "connector",
        connected=connected,
        vault_secret_ref=vault_ok,
        has_calendar_events=has_events,
        email=email,
    )
    if not connected or not vault_ok or not has_events:
        report["error"] = "connector_incomplete"
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        client.close()
        return 2

    svc = ActionEngineService(
        db,
        life_graph=LifeGraphService(db),
        knowledge=KnowledgeService(db),
        decisions=DecisionService(db),
    )
    await svc.ensure_indexes()

    tag = uuid.uuid4().hex[:8]
    title = f"Andrò in vacanza dal 20 al 27 settembre 2026 a Vibo Marina (ORA_VERIFY_{tag})"
    opened = await svc.open(
        uid,
        OpenBody(
            title=title,
            force_new=True,
            intent={
                "intent": "travel",
                "subtype": "vacation",
                "confidence": 0.99,
                "reason": "verify_script",
                "needs_clarify": False,
                "entities": {
                    "travel": "Vibo Marina",
                    "place": "Vibo Marina",
                    "start_date": "2026-09-20",
                    "end_date": "2026-09-27",
                    "period": "20–27/9/2026",
                },
            },
            meta={"skip_maps_network": True},
        ),
    )
    sess = opened["session"]
    sid = sess["id"]
    report["action_session_id"] = sid
    step("open", flow=sess.get("flow"), session_id=sid)
    # If clarify slipped through, pick travel chip
    if sess.get("flow") == "clarify":
        await svc.answer(
            uid, sid,
            AnswerBody(option_id="travel", value={"intent": "travel", "subtype": "vacation"}),
        )
        sess = (await svc.get_session(uid, sid)) or {}
        sid = sess["id"]
        step("clarify_to_travel", flow=sess.get("flow"))
    if sess.get("flow") != "travel":
        report["error"] = f"expected travel flow, got {sess.get('flow')}"
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        client.close()
        return 1

    # Drive answers — calendar_sync YES
    for _ in range(40):
        pub = await svc.get_session(uid, sid)
        if pub.get("status") == "completed":
            break
        turn = pub.get("current_turn")
        if not turn:
            break
        tid = turn["id"]
        if tid == "period":
            res = await svc.answer(uid, sid, AnswerBody(text="2026-09-20 - 2026-09-27"))
        elif tid == "destination":
            res = await svc.answer(uid, sid, AnswerBody(text="Vibo Marina"))
        elif tid == "departure_place":
            res = await svc.answer(uid, sid, AnswerBody(option_id="tarquinia", value="Tarquinia"))
        elif tid == "transport":
            res = await svc.answer(uid, sid, AnswerBody(option_id="car", value="car"))
        elif tid == "bookings":
            res = await svc.answer(uid, sid, AnswerBody(option_id="partial", value="partial"))
        elif tid == "companions":
            res = await svc.answer(uid, sid, AnswerBody(option_id="solo", value=1))
        elif tid == "calendar_sync":
            res = await svc.answer(uid, sid, AnswerBody(option_id="yes", value=True))
        elif tid == "prep":
            res = await svc.answer(uid, sid, AnswerBody(skip=True))
        elif tid == "preview":
            res = await svc.answer(uid, sid, AnswerBody(option_id="accept", value="accept"))
        elif tid == "confirm":
            res = await svc.answer(uid, sid, AnswerBody(option_id="confirm", value="confirm"))
        else:
            o = (turn.get("options") or [{"id": "x"}])[0]
            res = await svc.answer(uid, sid, AnswerBody(option_id=o["id"], value=o.get("value")))
        if res.get("ok") is False and res.get("error"):
            report["error"] = res.get("error")
            report["message"] = res.get("message")
            EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
            client.close()
            return 1
        if res.get("completed"):
            pub = res.get("session") or pub
            break

    plan_id = (pub.get("meta") or {}).get("travel_project_id")
    report["travel_project_id"] = plan_id
    step("confirm_done", status=pub.get("status"), travel_project_id=plan_id)
    if not plan_id or pub.get("status") != "completed":
        report["error"] = "confirm_failed"
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        client.close()
        return 1

    # Raw doc for diagnosis (public() strips less of google_sync detail)
    raw = await db.travel_projects.find_one({"id": plan_id, "user_id": uid}, {"_id": 0})
    plan = await svc.travel_projects.get_project(uid, plan_id)
    events = (raw or plan or {}).get("calendar_events") or []
    gsync = (raw or plan or {}).get("google_sync") or {}
    event_ids = [
        {
            "kind": e.get("kind"),
            "google_event_id": e.get("google_event_id"),
            "status": e.get("google_sync_status"),
            "calendar_id": e.get("google_calendar_id"),
        }
        for e in events
    ]
    report["calendar_sync_flag"] = (raw or {}).get("calendar_sync")
    report["answers_calendar_sync"] = ((raw or {}).get("answers") or {}).get("calendar_sync")
    report["calendar_events"] = event_ids
    report["google_sync"] = {
        "connected": gsync.get("connected"),
        "synced": gsync.get("synced"),
        "failed": gsync.get("failed"),
        "skipped": gsync.get("skipped"),
        "banner": gsync.get("banner"),
        "calendar_id": gsync.get("calendar_id"),
    }
    synced = [e for e in events if e.get("google_event_id")]
    # Also accept ids only present on google_sync.synced
    if not synced:
        for s in gsync.get("synced") or []:
            if s.get("event_id"):
                synced.append({
                    "kind": s.get("kind"),
                    "google_event_id": s.get("event_id"),
                    "google_calendar_id": s.get("calendar_id") or gsync.get("calendar_id"),
                    "google_sync_status": "synced",
                })
    step(
        "google_create",
        calendar_sync=(raw or {}).get("calendar_sync"),
        synced_count=len(synced),
        kinds=[e.get("kind") for e in synced],
        event_ids=[e.get("google_event_id") for e in synced],
        skipped=gsync.get("skipped"),
        failed=gsync.get("failed"),
        banner=(gsync.get("banner") or {}).get("message") if isinstance(gsync.get("banner"), dict) else gsync.get("banner"),
    )

    # If confirm skipped sync, force one retry with calendar_sync True (still user-confirmed path)
    if len(synced) < 1 and (raw or {}).get("calendar_sync"):
        from action_engine.travel.google_sync import sync_travel_events, retry_sync
        retry = await retry_sync(db, uid, plan_id)
        report["retry_sync"] = {
            "ok": retry.get("ok"),
            "synced": (retry.get("google_sync") or {}).get("synced"),
            "failed": (retry.get("google_sync") or {}).get("failed"),
            "skipped": (retry.get("google_sync") or {}).get("skipped"),
        }
        step("retry_sync", **{k: v for k, v in report["retry_sync"].items()})
        raw = await db.travel_projects.find_one({"id": plan_id, "user_id": uid}, {"_id": 0})
        events = (raw or {}).get("calendar_events") or []
        synced = [e for e in events if e.get("google_event_id")]

    if len(synced) < 1:
        report["error"] = "no_google_event_ids"
        EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        # Soft-cancel local project; no Google cleanup needed
        await svc.travel_projects.delete_project(uid, plan_id, soft=True, cleanup_google=False)
        client.close()
        return 1

    # Verify each event readable; check no duplicate summaries in window
    from action_engine.travel.google_sync import _gcal_service, _instance_for_user

    gcal = _gcal_service(db)
    inst2 = await _instance_for_user(db, uid)
    access = await gcal._get_access_token(user_id=uid, instance=inst2)
    cal_id = synced[0].get("google_calendar_id") or (plan.get("google_sync") or {}).get("calendar_id") or "primary"
    report["calendar_id"] = cal_id

    verified = []
    for e in synced:
        ev = await fetch_google_event(
            db, uid, calendar_id=e.get("google_calendar_id") or cal_id, event_id=e["google_event_id"],
        )
        verified.append({
            "kind": e.get("kind"),
            "event_id": e.get("google_event_id"),
            "summary": (ev or {}).get("summary"),
            "status": (ev or {}).get("status"),
            "readable": bool(ev),
        })
    report["verified_events"] = verified
    step("google_get", readable=sum(1 for v in verified if v["readable"]), total=len(verified))

    # Duplicate check by unique tag in title
    page = await gcal.provider.list_events(
        access_token=access,
        calendar_id=cal_id,
        time_min=(datetime(2026, 9, 19, tzinfo=timezone.utc)).isoformat(),
        time_max=(datetime(2026, 9, 28, tzinfo=timezone.utc)).isoformat(),
        max_results=50,
    )
    matches = [e for e in (page.events or []) if tag in (e.get("summary") or "") or "ORA_VERIFY_TravelSync" in (e.get("summary") or "")]
    # Our three events share destination titles; count by google ids uniqueness
    ids = [e.get("google_event_id") for e in synced]
    report["duplicate_check"] = {
        "unique_ids": len(set(ids)) == len(ids),
        "listed_verify_tagged": len(matches),
    }
    step("no_duplicate_ids", unique=len(set(ids)) == len(ids), listed=len(matches))

    # Cleanup via API-equivalent service
    cleanup = await svc.travel_projects.delete_project(
        uid, plan_id, soft=True, cleanup_google=True,
    )
    report["cleanup"] = {
        "ok": cleanup.get("ok"),
        "deleted": (cleanup.get("google_cleanup") or {}).get("deleted"),
        "failed": (cleanup.get("google_cleanup") or {}).get("failed"),
    }
    step(
        "cleanup_google",
        deleted_count=len((cleanup.get("google_cleanup") or {}).get("deleted") or []),
        failed=(cleanup.get("google_cleanup") or {}).get("failed"),
    )

    # Verify cancelled/removed
    post = []
    for e in synced:
        ev = await fetch_google_event(
            db, uid, calendar_id=e.get("google_calendar_id") or cal_id, event_id=e["google_event_id"],
        )
        st = (ev or {}).get("status") if ev else "gone"
        post.append({"event_id": e["google_event_id"], "status": st, "kind": e.get("kind")})
    report["post_cleanup"] = post
    cleaned_ok = all(p["status"] in ("cancelled", "gone", None) or p["status"] == "cancelled" for p in post)
    # If get returns 404/None treat as gone
    cleaned_ok = all((p["status"] in ("cancelled", "gone")) for p in post)
    step("post_cleanup_status", ok=cleaned_ok, events=post)

    report["ok"] = bool(synced) and cleaned_ok and len(set(ids)) == len(ids)
    EVIDENCE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("RESULT", "PASS" if report["ok"] else "FAIL")
    print("EVIDENCE", str(EVIDENCE))
    client.close()
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
