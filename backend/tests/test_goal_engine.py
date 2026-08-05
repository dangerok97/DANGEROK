"""Goal Engine Foundation — shadow upsert, dedupe, merge, study/travel, flag."""
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
        "connector_instances",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _goal_svc(db):
    from goal_engine import GoalService
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService
    svc = GoalService(
        db,
        life_graph=LifeGraphService(db),
        knowledge=KnowledgeService(db),
    )
    await svc.ensure_indexes()
    return svc


async def _ae_svc(db):
    from action_engine.service import ActionEngineService
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService
    from decision_engine import DecisionService
    svc = ActionEngineService(
        db,
        life_graph=LifeGraphService(db),
        knowledge=KnowledgeService(db),
        decisions=DecisionService(db),
    )
    await svc.ensure_indexes()
    return svc


def test_shadow_create_and_update_study():
    async def body():
        client, db = await _db()
        uid = f"u_ge_study_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        svc = await _goal_svc(db)
        plan = {
            "id": f"spl_{uuid.uuid4().hex[:8]}",
            "user_id": uid,
            "exam_name": "Psicologia",
            "subject": "Psicologia",
            "exam_date": (_now() + timedelta(days=21)).isoformat(),
            "status": "active",
            "sessions": [
                {"id": "s1", "status": "planned", "starts_at": _now().isoformat()},
                {"id": "s2", "status": "completed", "starts_at": _now().isoformat()},
            ],
            "document_ids": [],
            "project_id": f"apr_{uuid.uuid4().hex[:8]}",
            "brain_node_id": None,
            "action_session_id": f"aes_{uuid.uuid4().hex[:8]}",
            "idempotency_key": f"idem_study_{uid}",
            "source_priority_id": "dec_x",
        }
        await db.action_projects.insert_one({
            "id": plan["project_id"], "user_id": uid, "title": "Studio", "status": "active",
        })
        r1 = await svc.upsert_from_study_confirm(plan, effects={"next_focus_hint": "Studia oggi"})
        assert r1.get("ok") and r1.get("created") is True
        gid = r1["goal_id"]
        g = await db.goals.find_one({"id": gid}, {"_id": 0})
        assert g["goal_type"] == "study"
        assert "Psicologia" in g["title"]
        assert g["study_plan_id"] == plan["id"]
        assert g["project_id"] == plan["project_id"]
        assert g["status"] == "active"
        assert g["completion_percentage"] == 50.0  # 1/2 sessions
        assert g["brain_node_id"]
        # Project bag linked
        proj = await db.action_projects.find_one({"id": plan["project_id"]}, {"_id": 0})
        assert proj.get("goal_id") == gid
        # Update same idempotency → not create
        plan["sessions"][0]["status"] = "completed"
        r2 = await svc.upsert_from_study_confirm(plan, effects={})
        assert r2.get("created") is False
        assert r2["goal_id"] == gid
        count = await db.goals.count_documents({"user_id": uid, "status": {"$ne": "cancelled"}})
        assert count == 1
        g2 = await db.goals.find_one({"id": gid}, {"_id": 0})
        assert g2["completion_percentage"] == 100.0
        # Event trail
        evs = await db.goal_events.find({"goal_id": gid}, {"_id": 0}).to_list(20)
        types = {e["type"] for e in evs}
        assert "GoalCreated" in types
        assert "GoalUpdated" in types
        await _clean(db, uid)
        client.close()

    _run(body())


def test_shadow_travel_and_dedupe():
    async def body():
        client, db = await _db()
        uid = f"u_ge_tr_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        svc = await _goal_svc(db)
        proj = {
            "id": f"trp_{uuid.uuid4().hex[:8]}",
            "user_id": uid,
            "destination": "Calabria",
            "title": "Vacanza Calabria",
            "start_date": (_now() + timedelta(days=10)).date().isoformat(),
            "end_date": (_now() + timedelta(days=20)).date().isoformat(),
            "status": "active",
            "phase": "days_until",
            "prep_items": [{"id": "p1", "label": "Valigia", "category": "luggage"}],
            "calendar_events": [],
            "document_ids": [],
            "companion_names": [],
            "project_id": f"apr_{uuid.uuid4().hex[:8]}",
            "brain_node_id": None,
            "action_session_id": f"aes_{uuid.uuid4().hex[:8]}",
            "idempotency_key": f"idem_travel_{uid}",
        }
        await db.action_projects.insert_one({
            "id": proj["project_id"], "user_id": uid, "title": "Travel", "status": "active",
        })
        r1 = await svc.upsert_from_travel_confirm(proj, effects={"calendar_ids": []})
        assert r1.get("ok") and r1.get("created")
        g = r1["goal"]
        assert g["goal_type"] == "travel"
        assert "Calabria" in g["title"]
        assert g["travel_project_id"] == proj["id"]
        # Title-equivalent second insert without new key → update
        proj2 = {**proj, "id": f"trp_{uuid.uuid4().hex[:8]}", "idempotency_key": f"idem_travel_{uid}_b"}
        # Same destination title should match via title dedupe if type matches —
        # but different idempotency: title match on active travel goals
        r2 = await svc.upsert_from_travel_confirm(proj2, effects={})
        assert r2.get("created") is False
        assert r2["goal_id"] == r1["goal_id"]
        await _clean(db, uid)
        client.close()

    _run(body())


def test_merge_and_timeline():
    async def body():
        client, db = await _db()
        uid = f"u_ge_m_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        svc = await _goal_svc(db)
        from goal_engine.models import Goal, GoalCreateBody
        a = await svc.create(uid, GoalCreateBody(
            title="Preparare esame Storia", goal_type="study",
            desired_outcome="Passare Storia",
            idempotency_key=f"merge_a_{uid}",
        ))
        # Distinct title so dedupe does not collapse before explicit merge
        b = await svc.create(uid, GoalCreateBody(
            title="Ripasso letteratura moderna", goal_type="study",
            linked_documents=["doc1"],
            idempotency_key=f"merge_b_{uid}",
        ))
        assert a.get("created") is True and b.get("created") is True, (a, b)
        mid = await svc.merge(
            uid,
            source_goal_id=b["goal"]["id"],
            target_goal_id=a["goal"]["id"],
        )
        assert mid["ok"]
        assert "doc1" in mid["goal"]["linked_documents"]
        src = await db.goals.find_one({"id": b["goal"]["id"]}, {"_id": 0})
        assert src["status"] == "cancelled"
        assert src["merged_into_id"] == a["goal"]["id"]
        tl = await svc.timeline(uid, a["goal"]["id"])
        assert tl["ok"]
        types = [e["type"] for e in tl["events"]]
        assert "GoalMerged" in types
        await _clean(db, uid)
        client.close()

    _run(body())


def test_flag_off_noop():
    async def body():
        client, db = await _db()
        uid = f"u_ge_off_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        os.environ["GOAL_ENGINE_ENABLED"] = "0"
        svc = await _goal_svc(db)
        r = await svc.upsert_from_study_confirm({
            "id": "spl_x", "user_id": uid, "exam_name": "X",
            "sessions": [], "document_ids": [],
            "idempotency_key": "k_off",
        })
        assert r.get("skipped") is True
        assert await db.goals.count_documents({"user_id": uid}) == 0
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        client.close()

    _run(body())


def test_study_confirm_creates_goal_via_ae():
    """Full Study confirm path → Goal in Mongo; Home UX untouched."""
    async def body():
        client, db = await _db()
        uid = f"u_ge_ae_s_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        # Reset singleton so it picks test db
        import goal_engine.service as ges
        ges._svc = None

        from action_engine.study.models import StudyPlan, StudySessionItem, make_idempotency_key
        from action_engine.study.plan_service import StudyPlanService
        from life_graph import LifeGraphService
        from knowledge import KnowledgeService
        from decision_engine import DecisionService

        exam = "Psicologia"
        exam_date = (_now() + timedelta(days=14)).isoformat()
        plan = StudyPlan(
            user_id=uid,
            exam_name=exam,
            subject=exam,
            exam_date=exam_date,
            status="awaiting_confirmation",
            sessions=[
                StudySessionItem(
                    user_id=uid,
                    title="Studio Psicologia",
                    starts_at=(_now() + timedelta(days=1)).isoformat(),
                    ends_at=(_now() + timedelta(days=1, hours=1)).isoformat(),
                    duration_minutes=60,
                ),
            ],
            preview={"ok": True, "sessions_count": 1},
            idempotency_key=make_idempotency_key(uid, None, exam, exam_date),
            project_id=f"apr_{uuid.uuid4().hex[:8]}",
        )
        await db.action_projects.insert_one({
            "id": plan.project_id, "user_id": uid, "title": "Studio", "status": "active",
        })
        sps = StudyPlanService(
            db,
            life_graph=LifeGraphService(db),
            knowledge=KnowledgeService(db),
            decisions=DecisionService(db),
        )
        await sps.upsert_draft(plan)
        res = await sps.confirm(uid, plan.id, force=True)
        assert res.get("ok"), res
        assert res.get("effects", {}).get("goal", {}).get("goal_id")
        gid = res["effects"]["goal"]["goal_id"]
        g = await db.goals.find_one({"id": gid, "user_id": uid}, {"_id": 0})
        assert g is not None
        assert g["study_plan_id"] == plan.id
        assert g["goal_type"] == "study"
        assert g["brain_node_id"]
        # Timeline
        from goal_engine import GoalService
        tl = await GoalService(db).timeline(uid, gid)
        assert any(e["type"] == "GoalCreated" for e in tl["events"])
        await _clean(db, uid)
        client.close()

    _run(body())


def test_travel_confirm_creates_goal_via_ae():
    async def body():
        client, db = await _db()
        uid = f"u_ge_ae_t_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        import goal_engine.service as ges
        ges._svc = None

        from action_engine.travel.models import TravelProject, make_idempotency_key
        from action_engine.travel.project_service import TravelProjectService
        from life_graph import LifeGraphService
        from knowledge import KnowledgeService
        from decision_engine import DecisionService

        start = (_now() + timedelta(days=30)).date().isoformat()
        end = (_now() + timedelta(days=40)).date().isoformat()
        proj = TravelProject(
            user_id=uid,
            destination="Calabria",
            title="Vacanza Calabria",
            start_date=start,
            end_date=end,
            status="awaiting_confirmation",
            transport="car",
            bookings="none",
            companions=1,
            calendar_sync=False,
            idempotency_key=make_idempotency_key(uid, None, "Calabria", start, end),
            project_id=f"apr_{uuid.uuid4().hex[:8]}",
            answers={"calendar_sync": False},
        )
        await db.action_projects.insert_one({
            "id": proj.project_id, "user_id": uid, "title": "Travel", "status": "active",
        })
        tps = TravelProjectService(
            db,
            life_graph=LifeGraphService(db),
            knowledge=KnowledgeService(db),
            decisions=DecisionService(db),
        )
        await tps.upsert_draft(proj)
        res = await tps.confirm(uid, proj.id, force=True)
        assert res.get("ok"), res
        gid = res.get("effects", {}).get("goal", {}).get("goal_id")
        assert gid
        g = await db.goals.find_one({"id": gid}, {"_id": 0})
        assert g["goal_type"] == "travel"
        assert g["travel_project_id"] == proj.id
        assert "Calabria" in g["title"]
        # Brain trip/goal node linked
        assert g["brain_node_id"]
        node = await db.life_nodes.find_one({"id": g["brain_node_id"]}, {"_id": 0})
        assert node is not None
        await _clean(db, uid)
        client.close()

    _run(body())


def test_progress_never_fake_without_sessions():
    from goal_engine.progress import progress_from_study_plan, progress_from_travel_project
    p = progress_from_study_plan({"sessions": [], "status": "active"})
    assert p.ratio == 0.0
    assert p.source == "study_sessions"
    t = progress_from_travel_project({"phase": "upcoming", "prep_items": [], "status": "active"})
    assert t.ratio == 0.0


def test_api_crud_search_archive(monkeypatch):
    """HTTP surface smoke via service layer (auth-tested elsewhere)."""
    async def body():
        client, db = await _db()
        uid = f"u_ge_api_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        svc = await _goal_svc(db)
        from goal_engine.models import GoalCreateBody, GoalPatchBody
        created = await svc.create(uid, GoalCreateBody(title="Goal API", goal_type="generic"))
        gid = created["goal"]["id"]
        got = await svc.get(uid, gid)
        assert got["title"] == "Goal API"
        patched = await svc.patch(uid, gid, GoalPatchBody(description="desc", status="planning"))
        assert patched["goal"]["status"] == "planning"
        found = await svc.search(uid, q="API")
        assert any(g["id"] == gid for g in found)
        arch = await svc.archive(uid, gid)
        assert arch["goal"]["status"] == "archived"
        await _clean(db, uid)
        client.close()

    _run(body())


def test_project_is_not_goal():
    """action_projects remain bags; Goal is separate collection."""
    async def body():
        client, db = await _db()
        uid = f"u_ge_bag_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        svc = await _goal_svc(db)
        pid = f"apr_{uuid.uuid4().hex[:8]}"
        await db.action_projects.insert_one({
            "id": pid, "user_id": uid, "title": "Bag", "status": "active", "flow": "study",
        })
        from goal_engine.models import Goal
        g = Goal(user_id=uid, title="Preparare esame X", goal_type="study", project_id=pid, status="active")
        r = await svc.upsert(g)
        assert r["goal"]["id"] != pid
        assert r["goal"]["project_id"] == pid
        assert await db.goals.count_documents({"user_id": uid}) == 1
        assert await db.action_projects.count_documents({"user_id": uid}) == 1
        await _clean(db, uid)
        client.close()

    _run(body())
