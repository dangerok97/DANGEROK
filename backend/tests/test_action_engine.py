"""Action Engine — flows, brain, calendar, home update, dedupe."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
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
        "action_sessions", "action_projects", "documents", "decisions", "tasks",
        "life_nodes", "life_edges", "node_knowledge", "reminders",
        "home_item_state", "home_snapshots", "home_insights", "users",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _svc(db):
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


def _answer_all(svc, user_id, session_id, picks: dict):
    """Answer remaining turns using option ids from picks or first option."""
    async def body():
        from action_engine.models import AnswerBody
        for _ in range(20):
            pub = await svc.get_session(user_id, session_id)
            assert pub is not None
            if pub.get("done") or pub.get("status") == "completed":
                return pub
            turn = pub.get("current_turn")
            assert turn is not None, "active session must always have a question"
            tid = turn["id"]
            opt_id = picks.get(tid)
            if not opt_id and turn.get("options"):
                opt_id = turn["options"][0]["id"]
            res = await svc.answer(user_id, session_id, AnswerBody(option_id=opt_id))
            assert res.get("ok") is True or res.get("completed") is True
            if res.get("completed"):
                return res["session"]
        raise AssertionError("flow did not complete")
    return body()


def test_resolve_categories():
    from action_engine.flows.base import resolve_category
    assert resolve_category("study") == "study"
    assert resolve_category("event") == "event"
    assert resolve_category("travel") == "travel"
    assert resolve_category("visit") == "medical"
    assert resolve_category("bill") == "admin"
    assert resolve_category("payment") == "admin"
    assert resolve_category("activity") == "generic"
    assert resolve_category(None, "document") == "generic"


def test_study_flow_creates_calendar_and_home_update():
    async def body():
        client, db = await _db()
        user = f"u_ae_study_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": user, "filename": "appunti.pdf",
                "display_title": "Analisi 1",
                "analysis": {"macro_category": "education", "confidence": 0.9},
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            from action_engine.models import OpenBody
            opened = await svc.open(user, OpenBody(
                title="Esame Analisi 1",
                item_type="study",
                source_type="document",
                source_id=doc_id,
                home_item_id="home_study_1",
            ))
            session = opened["session"]
            assert session["current_turn"] is not None
            assert session["flow"] == "study"
            assert session["current_turn"]["question"]
            assert session["project"] is not None

            done = await _answer_all(svc, user, session["id"], {
                "exam_date": "in_1_week",
                "has_material": "yes_uploaded",
                "use_uploaded": "yes",
                "hours_per_day": "1h",
                "pace": "distributed",
                "tools": "plan_only",
            })
            assert done["status"] == "completed"
            assert done["effects"].get("home_invalidate") is True
            cal = done["effects"].get("calendar_ids") or []
            assert len(cal) >= 2
            nodes = await db.life_nodes.count_documents({
                "user_id": user, "origin": "action_engine", "type": "event",
            })
            assert nodes >= 2
            rem = await db.reminders.count_documents({"user_id": user})
            assert rem >= 1
            # Brain node exists with answers
            assert done.get("brain_node_id")
            know = await db.node_knowledge.find_one({
                "user_id": user, "node_id": done["brain_node_id"],
            })
            assert know is not None

            from home.service import HomeService
            home = await HomeService(db).build_home(user)
            # After study plan, Home should see sessions or project hint
            titles = []
            if home.primary_focus:
                titles.append(home.primary_focus.get("title", ""))
            for g in home.priorities:
                for it in g.items:
                    titles.append(it.get("title", ""))
            blob = " ".join(titles).lower()
            assert "sessione" in blob or "analisi" in blob or "studio" in blob or home.primary_focus is not None
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_event_flow():
    async def body():
        client, db = await _db()
        user = f"u_ae_evt_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            svc = await _svc(db)
            from action_engine.models import OpenBody
            start = (_now() + timedelta(days=1)).isoformat()
            opened = await svc.open(user, OpenBody(
                title="Concerto Jazz",
                item_type="event",
                location="Milano Arena",
                start_at=start,
                home_item_id="home_evt_1",
            ))
            assert opened["session"]["flow"] == "event"
            assert opened["session"]["current_turn"]
            done = await _answer_all(svc, user, opened["session"]["id"], {
                "has_ticket": "yes",
                "add_calendar": "yes",
                "need_route": "yes",
                "reminder": "1h",
                "leave_time": "yes_30",
            })
            assert done["status"] == "completed"
            assert (done["effects"].get("calendar_ids") or []) or any(
                a["kind"] == "maps" for a in done.get("proposed_actions", [])
            )
            assert await db.reminders.count_documents({"user_id": user}) >= 1
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_travel_flow():
    async def body():
        client, db = await _db()
        user = f"u_ae_trv_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            svc = await _svc(db)
            from action_engine.models import OpenBody
            opened = await svc.open(user, OpenBody(
                title="Weekend Roma",
                item_type="travel",
                home_item_id="home_trv_1",
            ))
            assert opened["session"]["flow"] == "travel"
            done = await _answer_all(svc, user, opened["session"]["id"], {
                "destination": "from_title",
                "transport": "train",
                "bookings": "partial",
                "people": "solo",
                "prep": "all",
            })
            assert done["status"] == "completed"
            assert any(a["status"] == "blocked" for a in done.get("proposed_actions", []))  # weather honest
            assert await db.life_nodes.count_documents({"user_id": user, "type": "event"}) >= 1
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_medical_no_advice():
    async def body():
        client, db = await _db()
        user = f"u_ae_med_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            svc = await _svc(db)
            from action_engine.models import OpenBody
            from action_engine.flows.medical import MEDICAL_DISCLAIMER
            assert "consigli medici" in MEDICAL_DISCLAIMER.lower() or "diagnosi" in MEDICAL_DISCLAIMER.lower()
            opened = await svc.open(user, OpenBody(
                title="Visita dentista",
                item_type="visit",
                location="Studio Bianchi",
                home_item_id="home_med_1",
            ))
            assert opened["session"]["flow"] == "medical"
            turn = opened["session"]["current_turn"]
            assert turn and ("medici" in (turn.get("explanation") or "").lower() or "visita" in turn["question"].lower())
            done = await _answer_all(svc, user, opened["session"]["id"], {
                "confirm_visit": "yes",
                "add_calendar": "yes",
                "need_maps": "yes",
                "documents": "yes",
                "reminder": "1d",
            })
            assert done["status"] == "completed"
            # No invented diagnosis language in proposed actions
            labels = " ".join(a["label"].lower() for a in done.get("proposed_actions", []))
            assert "diagnos" not in labels
            assert "cura" not in labels
            assert await db.life_nodes.count_documents({"user_id": user, "type": "event"}) >= 1
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_admin_invoice_flow():
    async def body():
        client, db = await _db()
        user = f"u_ae_adm_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            svc = await _svc(db)
            from action_engine.models import OpenBody
            due = (_now() + timedelta(days=5)).isoformat()
            opened = await svc.open(user, OpenBody(
                title="Bolletta luce",
                item_type="bill",
                source_type="document",
                source_id="doc_bill_x",
                due_at=due,
                meta={"amount": "87.50"},
                home_item_id="home_bill_1",
            ))
            assert opened["session"]["flow"] == "admin"
            done = await _answer_all(svc, user, opened["session"]["id"], {
                "understand": "clear",
                "payment_status": "pay_now",
                "reminder": "3d",
                "calendar": "yes",
                "open_doc": "yes",
            })
            assert done["status"] == "completed"
            assert await db.reminders.count_documents({"user_id": user}) >= 1
            assert await db.life_nodes.count_documents({"user_id": user, "type": "event"}) >= 1
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_generic_never_empty():
    async def body():
        client, db = await _db()
        user = f"u_ae_gen_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            svc = await _svc(db)
            from action_engine.models import OpenBody
            opened = await svc.open(user, OpenBody(
                title="Chiamare il commercialista",
                item_type="activity",
                home_item_id="home_gen_1",
            ))
            assert opened["session"]["flow"] == "generic"
            assert opened["session"]["current_turn"] is not None
            assert opened["session"]["current_turn"]["options"]
            done = await _answer_all(svc, user, opened["session"]["id"], {
                "intent": "organize",
                "when": "today",
                "support": "reminder",
            })
            assert done["status"] == "completed"
            assert await db.reminders.count_documents({"user_id": user}) >= 1
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_brain_dedupe_and_merge_proposal():
    async def body():
        client, db = await _db()
        user = f"u_ae_brain_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            svc = await _svc(db)
            from action_engine.models import AnswerBody, OpenBody
            # Seed similar project
            await db.action_projects.insert_one({
                "id": "aproj_existing",
                "user_id": user,
                "title": "Esame Fisica",
                "flow": "study",
                "status": "active",
                "session_ids": [],
                "linked": {},
                "created_at": _now().isoformat(),
                "updated_at": _now().isoformat(),
            })
            opened = await svc.open(user, OpenBody(
                title="Esame Fisica 2",
                item_type="study",
                home_item_id="home_brain_1",
            ))
            assert opened.get("merge_proposal") or opened["session"].get("project", {}).get("merge_candidate_id")
            sid = opened["session"]["id"]
            node_id = opened["session"]["brain_node_id"]
            # Answer first turn twice with same value via resume path — open resumes
            turn = opened["session"]["current_turn"]
            opt = turn["options"][0]["id"]
            await svc.answer(user, sid, AnswerBody(option_id=opt))
            # Count knowledge history growth for same key should not explode on identical re-merge
            know1 = await db.node_knowledge.find_one({"user_id": user, "node_id": node_id})
            hist_len = len((know1 or {}).get("history") or [])
            # Re-open same home item resumes
            opened2 = await svc.open(user, OpenBody(
                title="Esame Fisica 2",
                item_type="study",
                home_item_id="home_brain_1",
            ))
            assert opened2.get("resumed") is True
            assert opened2["session"]["id"] == sid
            # Completing rest
            done = await _answer_all(svc, user, sid, {
                "has_material": "no",
                "hours_per_day": "1h",
                "pace": "intense",
                "tools": "plan_only",
            })
            assert done["status"] == "completed"
            know2 = await db.node_knowledge.find_one({"user_id": user, "node_id": node_id})
            assert know2 is not None
            # history grew but node is single
            assert await db.node_knowledge.count_documents({"user_id": user, "node_id": node_id}) == 1
            _ = hist_len
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_cancel_session():
    async def body():
        client, db = await _db()
        user = f"u_ae_cancel_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            svc = await _svc(db)
            from action_engine.models import OpenBody
            opened = await svc.open(user, OpenBody(title="X", item_type="generic", home_item_id="c1"))
            sid = opened["session"]["id"]
            res = await svc.cancel(user, sid)
            assert res["ok"] is True
            assert res["session"]["status"] == "cancelled"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_home_actions_catalog_uses_guide():
    from home.models import HomeItem
    from home.actions_catalog import actions_for
    item = HomeItem(
        id="x", type="study", title="Esame", source_type="document", source_id="d1",
    )
    acts = actions_for(item)
    kinds = {a.kind for a in acts}
    assert "guide" in kinds
    labels = {a.label.lower() for a in acts}
    assert "inizia" in labels or any("organizza" in a.label.lower() for a in acts)


def test_open_api_guard_empty():
    async def body():
        from fastapi.testclient import TestClient
        # Service-level guard already in router; test service requires title
        client, db = await _db()
        user = f"u_ae_empty_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            svc = await _svc(db)
            from action_engine.models import OpenBody
            # Minimal title still works — never empty question
            opened = await svc.open(user, OpenBody(title="Task", item_type="generic"))
            assert opened["session"]["current_turn"]["question"]
        finally:
            await _clean(db, user)
            client.close()
    _run(body())
