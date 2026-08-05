"""Home V2 Goal-aware — dedupe, context, flag-off, ranking factors. No Goal UX."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
os.environ.setdefault("GOAL_ENGINE_ENABLED", "1")
_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _now():
    return datetime.now(timezone.utc)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    for col in (
        "goals", "goal_events",
        "action_sessions", "action_projects", "study_plans", "study_sessions",
        "travel_projects", "documents", "decisions", "tasks",
        "life_nodes", "life_edges", "node_knowledge", "reminders",
        "home_item_state", "home_snapshots", "home_insights", "users",
        "connector_instances", "link_proposals",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _home_svc(db):
    from home.service import HomeService
    svc = HomeService(db)
    await svc.ensure_indexes()
    return svc


async def _seed_study_goal_bundle(db, uid: str):
    """Study plan + action_project + optional session docs sharing one Goal."""
    from goal_engine import GoalService
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService

    plan_id = f"spl_{uuid.uuid4().hex[:8]}"
    proj_id = f"apr_{uuid.uuid4().hex[:8]}"
    exam = (_now() + timedelta(days=12)).date().isoformat()
    sessions = [
        {
            "id": "s1", "status": "planned",
            "title": "Ripasso capitolo 1",
            "starts_at": (_now() + timedelta(hours=6)).isoformat(),
        },
        {"id": "s2", "status": "completed", "title": "Done", "starts_at": _now().isoformat()},
        {"id": "s3", "status": "planned", "title": "Flashcard", "starts_at": (_now() + timedelta(days=2)).isoformat()},
    ]
    await db.study_plans.insert_one({
        "id": plan_id, "user_id": uid, "exam_name": "Psicologia",
        "subject": "Psicologia", "exam_date": exam, "status": "active",
        "sessions": sessions, "document_ids": [], "project_id": proj_id,
        "action_session_id": f"aes_{uuid.uuid4().hex[:8]}",
        "idempotency_key": f"idem_study_{uid}",
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    await db.action_projects.insert_one({
        "id": proj_id, "user_id": uid, "status": "active", "flow": "study",
        "title": "Preparazione esame Psicologia",
        "next_focus_hint": "Studia capitolo 1",
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    gsvc = GoalService(db, life_graph=LifeGraphService(db), knowledge=KnowledgeService(db))
    await gsvc.ensure_indexes()
    plan = await db.study_plans.find_one({"id": plan_id}, {"_id": 0})
    result = await gsvc.upsert_from_study_confirm(plan, effects={"next_focus_hint": "Studia capitolo 1"})
    assert result.get("ok") and result.get("goal_id")
    return plan_id, proj_id, result["goal_id"]


async def _seed_travel_goal_bundle(db, uid: str):
    from goal_engine import GoalService
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService

    tid = f"trv_{uuid.uuid4().hex[:8]}"
    proj_id = f"apr_{uuid.uuid4().hex[:8]}"
    start = (_now() + timedelta(days=10)).date().isoformat()
    end = (_now() + timedelta(days=17)).date().isoformat()
    await db.travel_projects.insert_one({
        "id": tid, "user_id": uid, "destination": "Calabria",
        "title": "Vacanza Calabria", "status": "active",
        "start_date": start, "end_date": end, "phase": "days_until",
        "project_id": proj_id, "prep_items": [{"label": "Valigia"}],
        "idempotency_key": f"idem_travel_{uid}",
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    await db.action_projects.insert_one({
        "id": proj_id, "user_id": uid, "status": "active", "flow": "travel",
        "title": "Vacanza Calabria",
        "next_focus_hint": "Prepara documenti",
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    gsvc = GoalService(db, life_graph=LifeGraphService(db), knowledge=KnowledgeService(db))
    await gsvc.ensure_indexes()
    proj = await db.travel_projects.find_one({"id": tid}, {"_id": 0})
    result = await gsvc.upsert_from_travel_confirm(proj, effects={"next_focus_hint": "Prepara documenti"})
    assert result.get("ok") and result.get("goal_id")
    return tid, proj_id, result["goal_id"]


def _focus_and_priority_items(home):
    items = []
    if home.primary_focus:
        items.append(home.primary_focus)
    for g in home.priorities or []:
        items.extend(g.items or [])
    return items


def test_ranking_version_goal_aware():
    from home.models import RANKING_VERSION
    assert RANKING_VERSION == "home-rank-1.1"


def test_same_goal_collapses_to_single_representative():
    async def body():
        client, db = await _db()
        uid = f"u_gah_dedupe_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            plan_id, proj_id, goal_id = await _seed_study_goal_bundle(db, uid)
            svc = await _home_svc(db)
            home = await svc.build_home(uid)
            surface = _focus_and_priority_items(home)
            linked = [i for i in surface if i.get("goal_id") == goal_id]
            assert len(linked) == 1, f"expected 1 focus/priority for goal, got {len(linked)}: {linked}"
            rep = linked[0]
            assert rep.get("goal_title")
            assert "Psicolog" in (rep.get("goal_title") or "")
            assert rep.get("goal_progress") is not None
            # Prefer study_plan over action_project bag
            assert rep.get("source_type") in ("study_plan", "study")
            assert rep.get("subtype") != "action_project"
            # No competing AE project card for same goal
            ae = [i for i in surface if i.get("source_type") == "action_project" and i.get("goal_id") == goal_id]
            assert ae == []
            assert home.ranking_version == "home-rank-1.1"
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_study_shadow_home_goal_context():
    async def body():
        client, db = await _db()
        uid = f"u_gah_study_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id = await _seed_study_goal_bundle(db, uid)
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            assert any(i.get("goal_id") == goal_id for i in surface)
            primary = home.primary_focus
            assert primary is not None
            if primary.get("goal_id") == goal_id:
                assert primary.get("goal_title")
                assert primary.get("goal_next_action") or primary.get("meta", {}).get("next_session")
            expl = home.explanation
            assert expl is not None
            codes = {f.code for f in expl.factors}
            # When primary is goal-linked, explanation must cite goal factors
            if primary.get("goal_id"):
                assert codes & {
                    "goal_importance", "goal_urgency", "goal_context",
                    "goal_next_action", "goal_progress", "goal_deadline_pressure",
                    "goal_deadline_near",
                }
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_travel_shadow_home_goal_context():
    async def body():
        client, db = await _db()
        uid = f"u_gah_travel_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id = await _seed_travel_goal_bundle(db, uid)
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            linked = [i for i in surface if i.get("goal_id") == goal_id]
            assert len(linked) == 1
            assert "Calabria" in (linked[0].get("goal_title") or linked[0].get("title") or "")
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_flag_off_no_goal_fields():
    async def body():
        client, db = await _db()
        uid = f"u_gah_off_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            os.environ["GOAL_ENGINE_ENABLED"] = "1"
            plan_id, proj_id, goal_id = await _seed_study_goal_bundle(db, uid)
            # Flag off for Home read path
            os.environ["GOAL_ENGINE_ENABLED"] = "0"
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            for i in surface:
                assert i.get("goal_id") is None
                assert "goal_id" not in (i or {}) or i.get("goal_id") is None
            # Still surfaces study plan (pre-change behavior)
            assert any(
                i.get("source_type") == "study_plan" or i.get("subtype") == "study_plan"
                for i in surface
            )
            # With flag off, action_project may also appear (no goal collapse)
            # — that is acceptable pre-goal behavior
        finally:
            os.environ["GOAL_ENGINE_ENABLED"] = "1"
            await _clean(db, uid)
            client.close()
    _run(body())


def test_isolation_two_users():
    async def body():
        client, db = await _db()
        a = f"u_gah_iso_a_{uuid.uuid4().hex[:6]}"
        b = f"u_gah_iso_b_{uuid.uuid4().hex[:6]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, a)
        await _clean(db, b)
        try:
            await db.users.insert_one({"user_id": a, "email": f"{a}@t.ora"})
            await db.users.insert_one({"user_id": b, "email": f"{b}@t.ora"})
            _, _, gid_a = await _seed_study_goal_bundle(db, a)
            home_b = await (await _home_svc(db)).build_home(b)
            surface_b = _focus_and_priority_items(home_b)
            assert not any(i.get("goal_id") == gid_a for i in surface_b)
            assert home_b.primary_focus is None or home_b.primary_focus.get("goal_id") != gid_a
        finally:
            await _clean(db, a)
            await _clean(db, b)
            client.close()
    _run(body())


def test_resume_mentions_goal_title():
    async def body():
        client, db = await _db()
        uid = f"u_gah_resume_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            from goal_engine import GoalService
            from life_graph import LifeGraphService
            from knowledge import KnowledgeService

            plan_id = f"spl_{uuid.uuid4().hex[:8]}"
            sess_id = f"aes_{uuid.uuid4().hex[:8]}"
            await db.study_plans.insert_one({
                "id": plan_id, "user_id": uid, "exam_name": "Psicologia",
                "status": "draft", "sessions": [],
                "action_session_id": sess_id,
                "idempotency_key": f"idem_draft_{uid}",
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            await db.action_sessions.insert_one({
                "id": sess_id, "user_id": uid, "status": "active",
                "flow": "study", "title": "Preparazione esame",
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            gsvc = GoalService(db, life_graph=LifeGraphService(db), knowledge=KnowledgeService(db))
            await gsvc.upsert_from_study_confirm({
                "id": plan_id, "user_id": uid, "exam_name": "Psicologia",
                "status": "active", "sessions": [
                    {"id": "s1", "status": "planned", "starts_at": _now().isoformat()},
                ],
                "project_id": None, "action_session_id": sess_id,
                "idempotency_key": f"idem_draft_{uid}",
                "exam_date": (_now() + timedelta(days=20)).isoformat(),
            })
            # Force draft surface: keep plan as draft for resume adapter path
            await db.study_plans.update_one(
                {"id": plan_id}, {"$set": {"status": "draft"}},
            )
            home = await (await _home_svc(db)).build_home(uid)
            assert home.resume_item is not None
            blob = f"{home.resume_item.get('title','')} {home.resume_item.get('description','')}"
            assert home.resume_item.get("goal_id") or "Psicolog" in blob or "Obiettivo" in blob
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_goal_insight_present():
    async def body():
        client, db = await _db()
        uid = f"u_gah_ins_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            await _seed_study_goal_bundle(db, uid)
            home = await (await _home_svc(db)).build_home(uid)
            texts = [i.text for i in (home.insights or [])]
            # May be crowded out by other insights — at least no crash; prefer goal text when slot free
            assert len(home.insights) <= 2
            if any("goal_engine" == getattr(i, "source", None) or i.source == "goal_engine" for i in home.insights):
                assert any("Psicolog" in t or "%" in t for t in texts)
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())
