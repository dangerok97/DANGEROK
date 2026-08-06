#!/usr/bin/env python3
"""
Audit + non-destructive migration for Home Goal presentation links.

- Scans study_plans, travel_projects, action_projects, life_nodes, reminders,
  decisions, conversation_sessions, google ingestion for missing goal_id.
- Attaches goal_id where a persistent ref reconstructs the link uniquely.
- NEVER deletes plans/sessions/events/suggestions.
- Optional --archive-fixtures moves local e2e fixture markers (not user data).

Usage:
  python scripts/audit_home_goal_links.py --report
  python scripts/audit_home_goal_links.py --migrate
  python scripts/audit_home_goal_links.py --migrate --user-id USER
  python scripts/audit_home_goal_links.py --archive-fixtures  # local fixtures only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    name = os.environ.get("DB_NAME", "ora_dev")
    client = AsyncIOMotorClient(url)
    return client, client[name]


async def _load_goals(db, user_id: Optional[str] = None) -> List[dict]:
    q: Dict[str, Any] = {"status": {"$nin": ["completed", "cancelled", "archived"]}}
    if user_id:
        q["user_id"] = user_id
    return await db.goals.find(q, {"_id": 0}).to_list(2000)


def _index_goals(goals: List[dict]):
    by_id = {g["id"]: g for g in goals if g.get("id")}
    by_plan = {g["study_plan_id"]: g for g in goals if g.get("study_plan_id")}
    by_travel = {g["travel_project_id"]: g for g in goals if g.get("travel_project_id")}
    by_project = {g["project_id"]: g for g in goals if g.get("project_id")}
    by_session = {
        g["source_action_session_id"]: g
        for g in goals if g.get("source_action_session_id")
    }
    by_cal = {}
    for g in goals:
        for cid in g.get("linked_calendar_events") or []:
            if cid and cid not in by_cal:
                by_cal[cid] = g
    return by_id, by_plan, by_travel, by_project, by_session, by_cal


async def audit(db, user_id: Optional[str] = None) -> Dict[str, Any]:
    goals = await _load_goals(db, user_id)
    by_id, by_plan, by_travel, by_project, by_session, by_cal = _index_goals(goals)

    report: Dict[str, Any] = {
        "generated_at": _now(),
        "goals": len(goals),
        "collections": {},
        "attachable": [],
        "ambiguous": [],
        "orphan_artifacts": [],
    }

    async def scan(col_name: str, query: dict, extract_refs):
        if user_id:
            query = {**query, "user_id": user_id}
        docs = await db[col_name].find(query, {"_id": 0}).to_list(5000)
        missing = 0
        attachable = 0
        for d in docs:
            if d.get("goal_id") and d["goal_id"] in by_id:
                continue
            # nested meta
            meta = d.get("meta") or d.get("metadata") or d.get("attributes") or {}
            if meta.get("goal_id") and meta["goal_id"] in by_id:
                continue
            missing += 1
            refs = extract_refs(d, meta)
            matches = []
            for kind, key in refs:
                g = None
                if kind == "plan":
                    g = by_plan.get(key)
                elif kind == "travel":
                    g = by_travel.get(key)
                elif kind == "project":
                    g = by_project.get(key)
                elif kind == "session":
                    g = by_session.get(key)
                elif kind == "cal":
                    g = by_cal.get(key)
                elif kind == "goal":
                    g = by_id.get(key)
                if g:
                    matches.append(g["id"])
            uniq = list(dict.fromkeys(matches))
            entry = {
                "collection": col_name,
                "id": d.get("id"),
                "user_id": d.get("user_id"),
                "title": d.get("title") or d.get("label") or d.get("exam_name"),
                "refs": refs,
                "candidate_goal_ids": uniq,
            }
            if len(uniq) == 1:
                attachable += 1
                report["attachable"].append(entry)
            elif len(uniq) > 1:
                report["ambiguous"].append(entry)
            else:
                report["orphan_artifacts"].append(entry)
        report["collections"][col_name] = {
            "scanned": len(docs),
            "missing_goal_id": missing,
            "attachable": attachable,
        }

    await scan(
        "study_plans",
        {"status": {"$in": ["active", "paused", "draft", "awaiting_confirmation"]}},
        lambda d, m: [("plan", d.get("id"))] if d.get("id") else [],
    )
    await scan(
        "travel_projects",
        {"status": {"$in": ["active", "paused", "draft", "awaiting_confirmation"]}},
        lambda d, m: [("travel", d.get("id"))] if d.get("id") else [],
    )
    await scan(
        "action_projects",
        {"status": "active"},
        lambda d, m: (
            ([("project", d["id"])] if d.get("id") else [])
            + ([("plan", d["study_plan_id"])] if d.get("study_plan_id") else [])
            + ([("travel", d["travel_project_id"])] if d.get("travel_project_id") else [])
        ),
    )
    await scan(
        "life_nodes",
        {"type": "event", "status": "active"},
        lambda d, m: (
            ([("plan", m["study_plan_id"])] if m.get("study_plan_id") else [])
            + ([("travel", m["travel_project_id"])] if m.get("travel_project_id") else [])
            + ([("session", m["action_session_id"])] if m.get("action_session_id") else [])
            + ([("cal", d["id"])] if d.get("id") else [])
            + ([("goal", m["goal_id"])] if m.get("goal_id") else [])
        ),
    )
    await scan(
        "reminders",
        {"status": {"$in": ["open", "active", "pending"]}},
        lambda d, m: (
            ([("plan", m.get("study_plan_id") or d.get("study_plan_id"))]
             if (m.get("study_plan_id") or d.get("study_plan_id")) else [])
            + ([("goal", m.get("goal_id") or d.get("goal_id"))]
               if (m.get("goal_id") or d.get("goal_id")) else [])
        ),
    )
    await scan(
        "decisions",
        {"status": {"$in": ["open", "in_progress", "partially_completed", "postponed"]}},
        lambda d, m: (
            ([("plan", m.get("study_plan_id"))] if m.get("study_plan_id") else [])
            + ([("travel", m.get("travel_project_id"))] if m.get("travel_project_id") else [])
            + ([("session", m.get("action_session_id"))] if m.get("action_session_id") else [])
            + ([("goal", m.get("goal_id") or d.get("goal_id"))]
               if (m.get("goal_id") or d.get("goal_id")) else [])
        ),
    )
    await scan(
        "conversation_sessions",
        {"status": {"$in": ["active", "waiting_user", "running_action", "paused"]}},
        lambda d, m: (
            ([("goal", d["goal_id"])] if d.get("goal_id") else [])
            + ([("session", d["action_session_id"])] if d.get("action_session_id") else [])
            + ([("plan", d.get("study_plan_id") or m.get("study_plan_id"))]
               if (d.get("study_plan_id") or m.get("study_plan_id")) else [])
            + ([("travel", d.get("travel_project_id") or m.get("travel_project_id"))]
               if (d.get("travel_project_id") or m.get("travel_project_id")) else [])
        ),
    )

    report["summary"] = {
        "attachable": len(report["attachable"]),
        "ambiguous": len(report["ambiguous"]),
        "orphan_artifacts": len(report["orphan_artifacts"]),
    }
    return report


async def migrate(db, report: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
    """Non-destructive: set goal_id only when uniquely reconstructible."""
    updated = 0
    skipped = 0
    for entry in report.get("attachable") or []:
        col = entry["collection"]
        doc_id = entry["id"]
        gid = entry["candidate_goal_ids"][0]
        uid = entry["user_id"]
        if not doc_id or not gid:
            skipped += 1
            continue
        if dry_run:
            updated += 1
            continue
        # Prefer top-level goal_id; also stamp attributes/meta when relevant
        patch: Dict[str, Any] = {"goal_id": gid, "goal_id_migrated_at": _now()}
        if col == "life_nodes":
            await db[col].update_one(
                {"id": doc_id, "user_id": uid},
                {"$set": {"attributes.goal_id": gid, **{k: v for k, v in patch.items() if k != "goal_id"}},
                 "$setOnInsert": {}},
            )
            # Also set top-level for adapters that read it
            await db[col].update_one(
                {"id": doc_id, "user_id": uid},
                {"$set": {"goal_id": gid}},
            )
        elif col == "decisions":
            await db[col].update_one(
                {"id": doc_id, "user_id": uid},
                {"$set": {"goal_id": gid, "metadata.goal_id": gid, "goal_id_migrated_at": _now()}},
            )
        elif col == "reminders":
            await db[col].update_one(
                {"id": doc_id, "user_id": uid},
                {"$set": {"goal_id": gid, "meta.goal_id": gid, "goal_id_migrated_at": _now()}},
            )
        else:
            await db[col].update_one(
                {"id": doc_id, "user_id": uid},
                {"$set": patch},
            )
        updated += 1
    return {"updated": updated, "skipped": skipped, "dry_run": dry_run, "deleted": 0}


async def archive_fixtures(db) -> Dict[str, Any]:
    """Mark local e2e fixture users — does NOT delete artifacts."""
    cur = db.users.find(
        {"email": {"$regex": r"^e2e_.*(home|goal|pres|ce)_"}},
        {"_id": 0, "user_id": 1, "email": 1},
    )
    users = await cur.to_list(500)
    n = 0
    for u in users:
        await db.users.update_one(
            {"user_id": u["user_id"]},
            {"$set": {"fixture_archived_at": _now(), "fixture_archive": True}},
        )
        n += 1
    return {"fixture_users_marked": n, "deleted": 0}


async def main():
    ap = argparse.ArgumentParser(description="Audit/migrate Home Goal presentation links")
    ap.add_argument("--report", action="store_true", help="Write JSON report")
    ap.add_argument("--migrate", action="store_true", help="Attach goal_id where unique")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--user-id", default=None)
    ap.add_argument("--archive-fixtures", action="store_true")
    ap.add_argument(
        "--out",
        default=str(Path(_BACKEND).parent / "docs" / "home_goal_link_audit.json"),
    )
    args = ap.parse_args()

    client, db = await _db()
    try:
        report = await audit(db, args.user_id)
        result: Dict[str, Any] = {"audit": report}
        if args.migrate:
            result["migrate"] = await migrate(db, report, dry_run=args.dry_run)
        if args.archive_fixtures:
            result["archive_fixtures"] = await archive_fixtures(db)
        if args.report or args.migrate or args.archive_fixtures:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote {args.out}")
        print(json.dumps(report.get("summary") or report, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
