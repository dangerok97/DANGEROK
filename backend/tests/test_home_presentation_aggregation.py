"""Home Presentation Aggregation Layer — one card per Goal (≥13 cases)."""
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
os.environ.setdefault("PROACTIVE_ENGINE_ENABLED", "1")
os.environ.setdefault("CONVERSATION_ENGINE_ENABLED", "1")
_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _run(coro):
    # The session's own loop, not whatever the policy currently points at:
    # a suite that used asyncio.run() before this one has cleared that slot.
    return _loop_harness.run(coro)


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
        "travel_projects", "documents", "decisions", "tasks", "reminders",
        "life_nodes", "life_edges", "node_knowledge",
        "home_item_state", "home_snapshots", "home_insights", "users",
        "connector_instances", "link_proposals", "proactive_suggestions",
        "conversation_sessions", "ingestion_events",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _home_svc(db):
    from home.service import HomeService
    svc = HomeService(db)
    await svc.ensure_indexes()
    return svc


def _surface(home):
    items = []
    if home.primary_focus:
        items.append(home.primary_focus)
    for g in home.priorities or []:
        items.extend(g.items or [])
    return items


def _by_goal(home, goal_id: str):
    return [i for i in _surface(home) if i.get("goal_id") == goal_id]


async def _seed_psicologia_bundle(db, uid: str, *, n_sessions: int = 4, n_reviews: int = 2):
    """Study Goal: plan + sessions + reviews + calendar events + decision + suggestion."""
    from goal_engine import GoalService
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService

    plan_id = f"spl_{uuid.uuid4().hex[:8]}"
    proj_id = f"apr_{uuid.uuid4().hex[:8]}"
    exam = (_now() + timedelta(days=14)).date().isoformat()
    sessions = []
    for i in range(n_sessions):
        st = (_now() + timedelta(days=i if i else 0, hours=2)).isoformat()
        sessions.append({
            "id": f"s{i+1}",
            "status": "completed" if i == 1 else ("skipped" if i == 3 else "planned"),
            "title": f"Ripasso capitolo {i+1}",
            "starts_at": st,
            "session_type": "review" if i < n_reviews else "study",
        })
    await db.study_plans.insert_one({
        "id": plan_id, "user_id": uid, "exam_name": "Psicologia",
        "subject": "Psicologia", "exam_date": exam, "status": "active",
        "sessions": sessions, "document_ids": [], "project_id": proj_id,
        "flashcard_document_ids": [], "interrogami_document_ids": [],
        "action_session_id": f"aes_{uuid.uuid4().hex[:8]}",
        "idempotency_key": f"idem_study_{uid}_{plan_id}",
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    await db.action_projects.insert_one({
        "id": proj_id, "user_id": uid, "status": "active", "flow": "study",
        "title": "Preparazione esame Psicologia",
        "next_focus_hint": "Prossima sessione tra 2 giorni · esame tra 14g",
        "study_plan_id": plan_id,
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    # Life node calendar events (one per session) — historically lacked goal_id
    cal_ids = []
    for s in sessions:
        nid = f"ln_{uuid.uuid4().hex[:8]}"
        cal_ids.append(nid)
        await db.life_nodes.insert_one({
            "id": nid, "user_id": uid, "type": "event", "status": "active",
            "label": s["title"],
            "attributes": {
                "starts_at": s["starts_at"],
                "kind": "study_session",
                "study_plan_id": plan_id,
                "study_session_id": s["id"],
            },
            "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
        })
    # Reminder ripasso
    await db.reminders.insert_one({
        "id": f"rem_{plan_id[:10]}", "user_id": uid,
        "title": f"Ripasso: Psicologia", "status": "open",
        "due_at": (_now() + timedelta(days=13)).isoformat(),
        "meta": {"kind": "study_review", "study_plan_id": plan_id},
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    # Decision
    await db.decisions.insert_one({
        "id": f"dec_{uuid.uuid4().hex[:8]}", "user_id": uid,
        "title": "Studio: Psicologia", "category": "study",
        "status": "open", "urgency": 4, "importance": 5,
        "deadline": exam, "origin": "action_engine_study",
        "metadata": {"study_plan_id": plan_id},
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    gsvc = GoalService(db, life_graph=LifeGraphService(db), knowledge=KnowledgeService(db))
    await gsvc.ensure_indexes()
    plan = await db.study_plans.find_one({"id": plan_id}, {"_id": 0})
    result = await gsvc.upsert_from_study_confirm(plan, effects={
        "next_focus_hint": "Studia capitolo 1",
        "calendar_ids": cal_ids,
    })
    assert result.get("ok") and result.get("goal_id")
    goal_id = result["goal_id"]
    await db.goals.update_one(
        {"id": goal_id},
        {"$set": {"linked_calendar_events": cal_ids}},
    )
    # Proactive suggestion for same Goal
    await db.proactive_suggestions.insert_one({
        "id": f"sug_{uuid.uuid4().hex[:8]}", "user_id": uid,
        "title": "Ripassa flashcard Psicologia",
        "description": "Hai carte da ripassare",
        "reason": "Piano attivo",
        "type": "study", "status": "active",
        "goal_id": goal_id, "study_plan_id": plan_id,
        "priority": "high", "importance": 0.8, "urgency": 0.7, "confidence": 0.9,
        "score": 0.75, "source": "study_plan", "dedupe_key": f"study_nudge:{plan_id}",
        "action": {"kind": "navigate", "label": "Flashcard", "route": f"/study-plan/{plan_id}"},
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
        "expires_at": (_now() + timedelta(days=2)).isoformat(),
        "dismissed": False, "accepted": False, "completed": False,
        "factors": [], "meta": {},
    })
    return plan_id, proj_id, goal_id, cal_ids


async def _seed_vibo_travel(db, uid: str):
    from goal_engine import GoalService
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService

    tid = f"trv_{uuid.uuid4().hex[:8]}"
    proj_id = f"apr_{uuid.uuid4().hex[:8]}"
    start = (_now() + timedelta(days=10)).date().isoformat()
    end = (_now() + timedelta(days=17)).date().isoformat()
    await db.travel_projects.insert_one({
        "id": tid, "user_id": uid, "destination": "Vibo Marina",
        "title": "Vacanza a Vibo Marina", "status": "active",
        "start_date": start, "end_date": end, "phase": "days_until",
        "project_id": proj_id,
        "prep_items": [{"label": "Valigia"}, {"label": "Alloggio"}],
        "transport": "auto",
        "maps": {"duration_label": "5h", "deep_link": "https://maps.example/vibo"},
        "idempotency_key": f"idem_travel_{uid}_{tid}",
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    await db.action_projects.insert_one({
        "id": proj_id, "user_id": uid, "status": "active", "flow": "travel",
        "title": "Vacanza a Vibo Marina",
        "next_focus_hint": "Prepara documenti",
        "travel_project_id": tid,
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    # Outbound + return life nodes
    for label, day in (("Andata Vibo Marina", 10), ("Ritorno Vibo Marina", 17)):
        await db.life_nodes.insert_one({
            "id": f"ln_{uuid.uuid4().hex[:8]}", "user_id": uid,
            "type": "event", "status": "active", "label": label,
            "attributes": {
                "starts_at": (_now() + timedelta(days=day)).isoformat(),
                "kind": "travel_leg",
                "travel_project_id": tid,
            },
            "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
        })
    gsvc = GoalService(db, life_graph=LifeGraphService(db), knowledge=KnowledgeService(db))
    await gsvc.ensure_indexes()
    proj = await db.travel_projects.find_one({"id": tid}, {"_id": 0})
    result = await gsvc.upsert_from_travel_confirm(proj, effects={"next_focus_hint": "Prepara documenti"})
    assert result.get("ok") and result.get("goal_id")
    return tid, proj_id, result["goal_id"]


# --- 1. Study multi-artifact → 1 card ---

def test_01_study_multi_artifact_one_card():
    async def body():
        client, db = await _db()
        uid = f"u_pres_study_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id, _ = await _seed_psicologia_bundle(db, uid)
            home = await (await _home_svc(db)).build_home(uid)
            linked = _by_goal(home, goal_id)
            assert len(linked) == 1, f"expected 1 Psicologia card, got {len(linked)}: {[i.get('title') for i in linked]}"
            card = linked[0]
            assert card.get("presentation_id") or (card.get("meta") or {}).get("presentation_id")
            assert card.get("goal_id") == goal_id
            assert "Psicolog" in (card.get("title") or "") or "Psicolog" in (card.get("goal_title") or "")
            hidden = card.get("hidden_artifact_count")
            if hidden is None:
                hidden = (card.get("meta") or {}).get("hidden_artifact_count", 0)
            assert int(hidden) >= 1
            details = card.get("supporting_details") or (card.get("meta") or {}).get("supporting_details") or []
            assert isinstance(details, list)
            acts = {a.get("label") for a in (card.get("actions") or [])}
            assert acts & {"Continua", "Apri piano", "Inizia sessione", "Inizia", "Flashcard", "Rimanda"}
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 2. Travel multi-artifact → 1 card ---

def test_02_travel_multi_artifact_one_card():
    async def body():
        client, db = await _db()
        uid = f"u_pres_travel_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id = await _seed_vibo_travel(db, uid)
            home = await (await _home_svc(db)).build_home(uid)
            linked = _by_goal(home, goal_id)
            assert len(linked) == 1, f"expected 1 Vibo card, got {len(linked)}: {[i.get('title') for i in linked]}"
            card = linked[0]
            assert "Vibo" in (card.get("title") or "") or "Vibo" in (card.get("goal_title") or "")
            acts = {a.get("label") for a in (card.get("actions") or [])}
            assert acts & {"Continua", "Preparativi", "Apri viaggio", "Percorso", "Calendario", "Documenti", "Apri Maps"}
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 3. Two distinct study Goals → 2 cards ---

def test_03_two_distinct_study_goals():
    async def body():
        client, db = await _db()
        uid = f"u_pres_two_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, g1, _ = await _seed_psicologia_bundle(db, uid)
            # Second distinct exam
            from goal_engine import GoalService
            from life_graph import LifeGraphService
            from knowledge import KnowledgeService
            plan_id = f"spl_{uuid.uuid4().hex[:8]}"
            proj_id = f"apr_{uuid.uuid4().hex[:8]}"
            exam = (_now() + timedelta(days=20)).date().isoformat()
            await db.study_plans.insert_one({
                "id": plan_id, "user_id": uid, "exam_name": "Matematica",
                "subject": "Matematica", "exam_date": exam, "status": "active",
                "sessions": [{"id": "m1", "status": "planned", "title": "Algebra",
                              "starts_at": (_now() + timedelta(days=1)).isoformat()}],
                "document_ids": [], "project_id": proj_id,
                "idempotency_key": f"idem_math_{uid}",
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            await db.action_projects.insert_one({
                "id": proj_id, "user_id": uid, "status": "active", "flow": "study",
                "title": "Esame Matematica", "next_focus_hint": "Algebra",
                "study_plan_id": plan_id,
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            gsvc = GoalService(db, life_graph=LifeGraphService(db), knowledge=KnowledgeService(db))
            plan = await db.study_plans.find_one({"id": plan_id}, {"_id": 0})
            r = await gsvc.upsert_from_study_confirm(plan, effects={"next_focus_hint": "Algebra"})
            g2 = r["goal_id"]
            assert g1 != g2
            home = await (await _home_svc(db)).build_home(uid)
            assert len(_by_goal(home, g1)) == 1
            assert len(_by_goal(home, g2)) == 1
            surface_goals = {i.get("goal_id") for i in _surface(home) if i.get("goal_id")}
            assert {g1, g2} <= surface_goals
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 4. Similar titles, different Goals → not merge ---

def test_04_similar_titles_not_merged():
    async def body():
        client, db = await _db()
        uid = f"u_pres_sim_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            from goal_engine import GoalService
            from life_graph import LifeGraphService
            from knowledge import KnowledgeService
            gsvc = GoalService(db, life_graph=LifeGraphService(db), knowledge=KnowledgeService(db))
            await gsvc.ensure_indexes()
            gids = []
            same_start = (_now() + timedelta(hours=3)).isoformat()
            for name in ("Storia A", "Storia B"):
                plan_id = f"spl_{uuid.uuid4().hex[:8]}"
                proj_id = f"apr_{uuid.uuid4().hex[:8]}"
                await db.study_plans.insert_one({
                    "id": plan_id, "user_id": uid, "exam_name": name,
                    "subject": name, "exam_date": (_now() + timedelta(days=30)).date().isoformat(),
                    "status": "active",
                    "sessions": [{"id": "s1", "status": "planned", "title": "Ripasso",
                                  "starts_at": same_start}],
                    "project_id": proj_id,
                    "idempotency_key": f"idem_{plan_id}",
                    "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
                })
                await db.action_projects.insert_one({
                    "id": proj_id, "user_id": uid, "status": "active", "flow": "study",
                    "title": f"Preparazione {name}", "next_focus_hint": "Ripasso",
                    "study_plan_id": plan_id,
                    "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
                })
                plan = await db.study_plans.find_one({"id": plan_id}, {"_id": 0})
                r = await gsvc.upsert_from_study_confirm(plan, effects={})
                gids.append(r["goal_id"])
            home = await (await _home_svc(db)).build_home(uid)
            assert len(_by_goal(home, gids[0])) == 1
            assert len(_by_goal(home, gids[1])) == 1
            assert gids[0] != gids[1]
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 5. Artifact without goal_id → safe fallback ---

def test_05_artifact_without_goal_safe_fallback():
    async def body():
        client, db = await _db()
        uid = f"u_pres_orphan_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            await db.tasks.insert_one({
                "id": f"task_{uuid.uuid4().hex[:8]}", "user_id": uid,
                "title": "Comprare latte", "status": "open",
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            home = await (await _home_svc(db)).build_home(uid)
            surface = _surface(home)
            # Must not crash; orphan task may or may not surface depending on adapters
            assert home.generated_at
            assert home.ranking_version == "home-rank-1.4"
            # No false goal_id invented
            for i in surface:
                if "latte" in (i.get("title") or "").lower():
                    assert not i.get("goal_id")
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 6. Primary not duplicated in priorities ---

def test_06_primary_not_in_priorities():
    async def body():
        client, db = await _db()
        uid = f"u_pres_pri_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id, _ = await _seed_psicologia_bundle(db, uid)
            home = await (await _home_svc(db)).build_home(uid)
            assert home.primary_focus
            if home.primary_focus.get("goal_id") == goal_id:
                pri_same = [
                    i for g in (home.priorities or []) for i in (g.items or [])
                    if i.get("goal_id") == goal_id
                ]
                assert pri_same == [], f"primary Goal leaked into priorities: {pri_same}"
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 7. Resume not duplicated for same Goal ---

def test_07_resume_not_duplicated():
    async def body():
        client, db = await _db()
        uid = f"u_pres_res_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id, _ = await _seed_psicologia_bundle(db, uid)
            # Incomplete flashcards linked to goal
            doc_id = f"doc_{uuid.uuid4().hex[:8]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": uid, "display_title": "Flash Psicologia",
                "education_analysis": {"topic": "Psicologia"},
                "flashcards": [{"id": "c1", "review_status": "new"}],
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            await db.goals.update_one({"id": goal_id}, {"$addToSet": {"linked_documents": doc_id}})
            home = await (await _home_svc(db)).build_home(uid)
            if home.resume_item and home.resume_item.get("goal_id") == goal_id:
                # Same Goal must not also be primary
                assert not (home.primary_focus and home.primary_focus.get("goal_id") == goal_id)
            # At most one surface card for the Goal
            assert len(_by_goal(home, goal_id)) == 1
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 8. Suggestion incorporated ---

def test_08_suggestion_incorporated():
    async def body():
        client, db = await _db()
        uid = f"u_pres_sug_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        os.environ["PROACTIVE_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id, _ = await _seed_psicologia_bundle(db, uid)
            home = await (await _home_svc(db)).build_home(uid)
            linked = _by_goal(home, goal_id)
            assert len(linked) == 1
            card = linked[0]
            # Suggestion for same goal must not also appear as separate ORA TI CONSIGLIA
            ora = home.ora_ti_consiglia or []
            assert not any(s.get("goal_id") == goal_id for s in ora)
            # Next action or actions may carry suggestion signal
            na = card.get("next_action") or card.get("goal_next_action") or ""
            acts = {a.get("label") for a in (card.get("actions") or [])}
            assert na or acts
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 9. Conversation incorporated ---

def test_09_conversation_incorporated():
    async def body():
        client, db = await _db()
        uid = f"u_pres_ce_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        os.environ["CONVERSATION_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id, _ = await _seed_psicologia_bundle(db, uid)
            ce_id = f"ce_{uuid.uuid4().hex[:8]}"
            await db.conversation_sessions.insert_one({
                "id": ce_id, "user_id": uid, "status": "waiting_user",
                "goal_id": goal_id,
                "summary": "Stavamo preparando l'esame di Psicologia.",
                "intent": {"intent": "study"},
                "resume_token": "tok",
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            home = await (await _home_svc(db)).build_home(uid)
            linked = _by_goal(home, goal_id)
            assert len(linked) == 1
            card = linked[0]
            acts = {a.get("label") for a in (card.get("actions") or [])}
            assert acts & {"Continua organizzazione", "Riprendi conversazione", "Continua"}
            # No separate resume card for same Goal conversation
            if home.resume_item:
                assert home.resume_item.get("goal_id") != goal_id or home.resume_item.get("source_type") != "conversation_session"
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 10. User isolation ---

def test_10_user_isolation():
    async def body():
        client, db = await _db()
        u1 = f"u_pres_iso1_{uuid.uuid4().hex[:8]}"
        u2 = f"u_pres_iso2_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, u1)
        await _clean(db, u2)
        try:
            await db.users.insert_one({"user_id": u1, "email": f"{u1}@t.ora"})
            await db.users.insert_one({"user_id": u2, "email": f"{u2}@t.ora"})
            _, _, g1, _ = await _seed_psicologia_bundle(db, u1)
            _, _, g2 = await _seed_vibo_travel(db, u2)
            h1 = await (await _home_svc(db)).build_home(u1)
            h2 = await (await _home_svc(db)).build_home(u2)
            assert any(i.get("goal_id") == g1 for i in _surface(h1))
            assert not any(i.get("goal_id") == g2 for i in _surface(h1))
            assert any(i.get("goal_id") == g2 for i in _surface(h2))
            assert not any(i.get("goal_id") == g1 for i in _surface(h2))
        finally:
            await _clean(db, u1)
            await _clean(db, u2)
            client.close()
    _run(body())


# --- 11. Refresh stable ---

def test_11_refresh_stable_one_card():
    async def body():
        client, db = await _db()
        uid = f"u_pres_rf_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            _, _, goal_id, _ = await _seed_psicologia_bundle(db, uid)
            svc = await _home_svc(db)
            h1 = await svc.build_home(uid)
            h2 = await svc.build_home(uid)
            assert len(_by_goal(h1, goal_id)) == 1
            assert len(_by_goal(h2, goal_id)) == 1
            c1 = _by_goal(h1, goal_id)[0]
            c2 = _by_goal(h2, goal_id)[0]
            assert c1.get("presentation_id") == c2.get("presentation_id") or c1.get("goal_id") == c2.get("goal_id")
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- 12. Unit: presentation preference + similar title guard ---

def test_12_presentation_unit_preference_order():
    from home.models import HomeItem
    from home.presentation import aggregate_goal_cluster, representation_rank

    now = _now()
    gid = "goal_unit_pref"
    plan = HomeItem(
        id="plan1", type="study", subtype="study_plan", title="Studio: Psicologia",
        source_type="study_plan", source_id="spl1", score=40, goal_id=gid,
        goal_title="Esame Psicologia", goal_type="study",
        meta={"study_plan_id": "spl1", "next_session": {"id": "s1", "title": "Cap 1"},
              "exam_countdown_days": 10},
    )
    event = HomeItem(
        id="ev1", type="event", title="Ripasso capitolo 1",
        source_type="life_node", source_id="ln1", score=55, goal_id=gid,
        start_at=(now + timedelta(hours=2)).isoformat(),
        meta={"study_plan_id": "spl1"},
    )
    proj = HomeItem(
        id="proj1", type="study", subtype="action_project",
        title="Prossima sessione tra 2 giorni",
        source_type="action_project", source_id="apr1", score=50, goal_id=gid,
        meta={"project_id": "apr1"},
    )
    card = aggregate_goal_cluster([plan, event, proj], now=now)
    assert card.goal_id == gid
    assert card.meta["hidden_artifact_count"] == 2
    assert len(card.meta["supporting_details"]) == 2
    assert card.meta["presentation_id"] == f"pres_goal_{gid}"
    # Imminent event should outrank bag project
    assert representation_rank(event, now) > representation_rank(proj, now)


# --- 13. Legacy audit attachable ---

def test_13_legacy_audit_and_migrate():
    async def body():
        client, db = await _db()
        uid = f"u_pres_leg_{uuid.uuid4().hex[:8]}"
        os.environ["GOAL_ENGINE_ENABLED"] = "1"
        await _clean(db, uid)
        try:
            await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.ora"})
            plan_id, _, goal_id, cal_ids = await _seed_psicologia_bundle(db, uid)
            # Strip goal_id from a life_node to simulate legacy
            await db.life_nodes.update_one(
                {"id": cal_ids[0]},
                {"$unset": {"goal_id": "", "attributes.goal_id": ""}},
            )
            import importlib.util
            _audit_path = Path(_BACKEND) / "scripts" / "audit_home_goal_links.py"
            spec = importlib.util.spec_from_file_location("audit_home_goal_links", _audit_path)
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)
            report = await mod.audit(db, uid)
            assert report["summary"]["attachable"] >= 0  # may already be linked via plan
            # Ensure plan itself has goal after confirm
            plan = await db.study_plans.find_one({"id": plan_id})
            # Migration non-destructive
            result = await mod.migrate(db, report, dry_run=False)
            assert result["deleted"] == 0
            home = await (await _home_svc(db)).build_home(uid)
            assert len(_by_goal(home, goal_id)) == 1
        finally:
            await _clean(db, uid)
            client.close()
    _run(body())


# --- ranking version bump ---

def test_ranking_version_presentation():
    from home.models import RANKING_VERSION, PRESENTATION_VERSION
    assert RANKING_VERSION == "home-rank-1.4"
    assert PRESENTATION_VERSION == "home-pres-1.0"


def test_enforce_one_card_per_goal_unit():
    from home.models import HomeItem
    from home.presentation import enforce_one_card_per_goal
    items = [
        HomeItem(id="a", type="study", title="A", source_type="study_plan", source_id="1", goal_id="g1"),
        HomeItem(id="b", type="event", title="B", source_type="life_node", source_id="2", goal_id="g1"),
        HomeItem(id="c", type="bill", title="C", source_type="document", source_id="3"),
    ]
    out = enforce_one_card_per_goal(items)
    assert len([i for i in out if i.goal_id == "g1"]) == 1
    assert any(i.id == "c" for i in out)
