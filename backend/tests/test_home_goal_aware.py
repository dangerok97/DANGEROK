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


async def _seed_study_goal_bundle(db, uid: str, *, skipped: bool = False, session_today: bool = True):
    """Study plan + action_project + optional session docs sharing one Goal."""
    from goal_engine import GoalService
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService

    plan_id = f"spl_{uuid.uuid4().hex[:8]}"
    proj_id = f"apr_{uuid.uuid4().hex[:8]}"
    exam = (_now() + timedelta(days=12)).date().isoformat()
    today_iso = _now().isoformat()
    sessions = [
        {
            "id": "s1", "status": "planned",
            "title": "Ripasso capitolo 1",
            "starts_at": today_iso if session_today else (_now() + timedelta(hours=6)).isoformat(),
        },
        {"id": "s2", "status": "completed", "title": "Done", "starts_at": (_now() - timedelta(days=1)).isoformat()},
        {"id": "s3", "status": "planned", "title": "Flashcard", "starts_at": (_now() + timedelta(days=2)).isoformat()},
    ]
    if skipped:
        sessions.append({
            "id": "s_skip", "status": "skipped",
            "title": "Saltata", "starts_at": (_now() - timedelta(days=2)).isoformat(),
        })
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


async def _seed_travel_goal_bundle(db, uid: str, *, with_prep: bool = True):
    from goal_engine import GoalService
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService

    tid = f"trv_{uuid.uuid4().hex[:8]}"
    proj_id = f"apr_{uuid.uuid4().hex[:8]}"
    start = (_now() + timedelta(days=10)).date().isoformat()
    end = (_now() + timedelta(days=17)).date().isoformat()
    prep = [{"label": "Valigia"}, {"label": "Alloggio da confermare"}] if with_prep else []
    await db.travel_projects.insert_one({
        "id": tid, "user_id": uid, "destination": "Calabria",
        "title": "Vacanza Calabria", "status": "active",
        "start_date": start, "end_date": end, "phase": "days_until",
        "project_id": proj_id, "prep_items": prep,
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


# --- unit / schema ---

def test_ranking_version_goal_aware():
    from home.models import RANKING_VERSION
    # Bumped by Presentation Aggregation Layer (still Goal-aware)
    assert RANKING_VERSION == "home-rank-1.4"


def test_goal_context_attach_fields_unit():
    from home.goal_context import attach_goal_context
    from home.models import HomeItem
    from goal_engine.models import Goal, GoalProgress

    now = _now()
    goal = Goal(
        id="goal_unit1", user_id="u1", goal_type="study", title="Esame X",
        status="active", next_action="Ripassa cap. 1",
        target_date=(now + timedelta(days=10)).date().isoformat(),
        project_id="apr_1", study_plan_id="spl_1",
        importance=5, urgency=4,
        progress=GoalProgress(ratio=0.4, label="2/5 sessioni", source="study_sessions"),
        completion_percentage=40.0,
    )
    item = HomeItem(
        id="h1", type="study", subtype="study_plan", title="Studio",
        source_type="study_plan", source_id="spl_1",
        meta={"study_plan_id": "spl_1", "skipped_sessions": 1},
    )
    out = attach_goal_context([item], [goal], now=now)
    assert out[0].goal_id == "goal_unit1"
    assert out[0].goal_title == "Esame X"
    assert out[0].goal_type == "study"
    assert out[0].goal_status == "active"
    assert out[0].goal_progress == 40.0
    assert out[0].goal_next_action == "Ripassa cap. 1"
    assert out[0].goal_target_date
    assert out[0].goal_project_id == "apr_1"
    assert out[0].goal_blockers and "saltate" in out[0].goal_blockers[0].lower()


def test_travel_soft_progress_no_precise_pct():
    from home.goal_context import _progress_public
    from goal_engine.models import Goal, GoalProgress

    g = Goal(
        id="g_tr", user_id="u", goal_type="travel", title="Vacanza",
        progress=GoalProgress(ratio=0.15, label="fase: days_until", phase="days_until", source="travel_phase"),
        completion_percentage=15.0,
    )
    pct, label = _progress_public(g)
    assert pct is None
    assert label and "fase" in label


def test_artifact_without_goal_unchanged():
    from home.goal_context import attach_goal_context
    from home.models import HomeItem

    item = HomeItem(
        id="h2", type="bill", title="Bolletta",
        source_type="document", source_id="doc1",
    )
    out = attach_goal_context([item], [], now=_now())
    assert out[0].goal_id is None
    assert out[0].title == "Bolletta"


# --- integration cases (checklist) ---

def test_study_session_today():
    async def body():
        client, db = await _db()
        uid = f"u_gah_today_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id = await _seed_study_goal_bundle(db, uid, session_today=True)
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            linked = [i for i in surface if i.get("goal_id") == goal_id]
            assert linked
            meta = linked[0].get("meta") or {}
            assert meta.get("session_today") or meta.get("next_session")
            codes = {f.code for f in (home.explanation.factors if home.explanation else [])}
            if home.primary_focus and home.primary_focus.get("goal_id") == goal_id:
                assert codes & {"session_today", "goal_next_action", "goal_context", "goal_urgency", "goal_importance"}
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_skipped_session_boosts_and_blockers():
    async def body():
        client, db = await _db()
        uid = f"u_gah_skip_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id = await _seed_study_goal_bundle(db, uid, skipped=True)
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            linked = next(i for i in surface if i.get("goal_id") == goal_id)
            assert (linked.get("meta") or {}).get("skipped_sessions", 0) >= 1
            blockers = linked.get("goal_blockers") or []
            assert any("saltate" in b.lower() for b in blockers)
            if home.primary_focus and home.primary_focus.get("goal_id") == goal_id:
                codes = {f.code for f in home.explanation.factors}
                assert "goal_skipped_sessions" in codes or "skipped_sessions" in codes
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_travel_missing_prep():
    async def body():
        client, db = await _db()
        uid = f"u_gah_prep_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id = await _seed_travel_goal_bundle(db, uid, with_prep=True)
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            linked = next(i for i in surface if i.get("goal_id") == goal_id)
            meta = linked.get("meta") or {}
            assert meta.get("missing_prep")
            blockers = linked.get("goal_blockers") or []
            assert blockers or "Manca" in (linked.get("description") or "")
            # Soft progress — no unreliable precise % required
            assert linked.get("goal_progress") is None or linked.get("goal_progress_label")
            assert linked.get("goal_type") == "travel"
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_blocked_goal_surfaces_block():
    async def body():
        client, db = await _db()
        uid = f"u_gah_block_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id = await _seed_travel_goal_bundle(db, uid)
            await db.goals.update_one(
                {"id": goal_id, "user_id": uid},
                {"$set": {
                    "status": "blocked",
                    "current_state": "Alloggio non confermato",
                    "updated_at": _now().isoformat(),
                }},
            )
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            linked = next(i for i in surface if i.get("goal_id") == goal_id)
            assert linked.get("goal_status") == "blocked"
            assert linked.get("goal_blockers")
            assert any("alloggio" in b.lower() for b in linked["goal_blockers"])
            blob = f"{linked.get('description') or ''} {home.primary_focus and home.primary_focus.get('description') or ''}"
            assert "Blocco" in blob or "alloggio" in blob.lower()
            if home.primary_focus and home.primary_focus.get("goal_id") == goal_id:
                codes = {f.code for f in home.explanation.factors}
                assert "goal_blocked" in codes
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_completed_goal_not_on_active_home():
    async def body():
        client, db = await _db()
        uid = f"u_gah_done_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            plan_id, _, goal_id = await _seed_study_goal_bundle(db, uid)
            await db.goals.update_one(
                {"id": goal_id},
                {"$set": {"status": "completed", "completed_at": _now().isoformat()}},
            )
            await db.study_plans.update_one({"id": plan_id}, {"$set": {"status": "completed"}})
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            assert not any(i.get("goal_id") == goal_id for i in surface)
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_multi_artifact_same_goal_and_dedupe():
    async def body():
        client, db = await _db()
        uid = f"u_gah_dedupe_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            plan_id, proj_id, goal_id = await _seed_study_goal_bundle(db, uid)
            # Extra document linked to same goal
            doc_id = f"doc_{uuid.uuid4().hex[:8]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": uid, "display_title": "Appunti Psicologia",
                "education_analysis": {"topic": "Psicologia", "summary_short": "Note"},
                "flashcards": [{"id": "c1", "review_status": "new"}],
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            await db.goals.update_one(
                {"id": goal_id},
                {"$addToSet": {"linked_documents": doc_id}},
            )
            svc = await _home_svc(db)
            home = await svc.build_home(uid)
            surface = _focus_and_priority_items(home)
            linked = [i for i in surface if i.get("goal_id") == goal_id]
            assert len(linked) == 1, f"expected 1 focus/priority for goal, got {len(linked)}: {linked}"
            rep = linked[0]
            assert rep.get("goal_title")
            assert "Psicolog" in (rep.get("goal_title") or "")
            assert rep.get("goal_type") == "study"
            assert rep.get("goal_project_id") == proj_id or rep.get("goal_project_id")
            assert rep.get("source_type") in ("study_plan", "study")
            assert rep.get("subtype") != "action_project"
            ae = [i for i in surface if i.get("source_type") == "action_project" and i.get("goal_id") == goal_id]
            assert ae == []
            assert home.ranking_version == "home-rank-1.4"
            # Actions: Apri piano / Inizia where applicable
            acts = {a.get("label") for a in (rep.get("actions") or [])}
            assert acts & {"Apri piano", "Inizia sessione", "Inizia", "Flashcard", "Interrogami"}
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
                assert "Obiettivo:" in (primary.get("description") or "") or primary.get("goal_title")
                assert primary.get("goal_target_date")
            expl = home.explanation
            assert expl is not None
            codes = {f.code for f in expl.factors}
            if primary.get("goal_id"):
                assert codes & {
                    "goal_importance", "goal_urgency", "goal_context",
                    "goal_next_action", "goal_progress", "goal_deadline_pressure",
                    "goal_deadline_near", "goal_stale", "goal_skipped_sessions",
                    "session_today",
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
            assert linked[0].get("goal_type") == "travel"
        finally:
            await _clean(db, uid)
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
            await db.study_plans.update_one(
                {"id": plan_id}, {"$set": {"status": "draft"}},
            )
            home = await (await _home_svc(db)).build_home(uid)
            # Draft-only: resume is promoted into Adesso (not empty); Continua may be empty
            assert home.primary_focus is not None or home.resume_item is not None
            surface_item = home.resume_item or home.primary_focus
            blob = f"{surface_item.get('title','')} {surface_item.get('description','')}"
            assert surface_item.get("goal_id") or "Psicolog" in blob or "Obiettivo" in blob
            # Resume ≠ duplicate of primary when both present for same goal
            if home.primary_focus and home.resume_item and home.resume_item.get("goal_id"):
                if home.primary_focus.get("goal_id") == home.resume_item.get("goal_id"):
                    assert home.primary_focus.get("id") != home.resume_item.get("id")
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
            assert len(home.insights) <= 2
            if any(i.source == "goal_engine" for i in home.insights):
                assert any("Psicolog" in t or "%" in t or "esame" in t for t in texts)
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


def test_no_goals_legacy_home():
    async def body():
        client, db = await _db()
        uid = f"u_gah_nogoals_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            await db.documents.insert_one({
                "id": f"doc_{uuid.uuid4().hex[:8]}", "user_id": uid,
                "display_title": "Fattura gas",
                "admin_analysis": {"amount": "50€", "due_date": (_now() + timedelta(days=2)).isoformat()},
                "analysis": {"macro_category": "admin"},
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            for i in surface:
                assert not i.get("goal_id")
            assert home.ranking_version == "home-rank-1.4"
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
            await _seed_study_goal_bundle(db, uid)
            os.environ["GOAL_ENGINE_ENABLED"] = "0"
            home = await (await _home_svc(db)).build_home(uid)
            surface = _focus_and_priority_items(home)
            for i in surface:
                assert i.get("goal_id") is None
            assert any(
                i.get("source_type") == "study_plan" or i.get("subtype") == "study_plan"
                for i in surface
            )
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


def test_idle_goal_proposal_when_no_artifact():
    async def body():
        client, db = await _db()
        uid = f"u_gah_idle_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            from goal_engine.models import Goal
            from goal_engine.repository import GoalRepository
            g = Goal(
                user_id=uid, goal_type="study", title="Esame Storia",
                status="active", next_action="Apri i materiali",
                study_plan_id=f"spl_missing_{uuid.uuid4().hex[:6]}",
                importance=6, urgency=5,
                target_date=(_now() + timedelta(days=8)).date().isoformat(),
            )
            await GoalRepository(db).upsert(g)
            home = await (await _home_svc(db)).build_home(uid)
            assert home.primary_focus is not None
            assert home.primary_focus.get("goal_id") == g.id
            assert "Obiettivo:" in (home.primary_focus.get("description") or "")
            # Opens plan/route — not a Goal page
            acts = home.primary_focus.get("actions") or []
            routes = [a.get("route") or "" for a in acts]
            assert not any("/goals" in r or "/goal/" in r for r in routes)
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())
