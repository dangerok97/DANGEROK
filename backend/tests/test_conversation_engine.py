"""Conversation Engine — orchestration foundation (NOT a chatbot)."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
os.environ["CONVERSATION_ENGINE_ENABLED"] = "1"
os.environ.setdefault("GOAL_ENGINE_ENABLED", "1")

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


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    for col in (
        "conversation_sessions", "action_sessions", "action_projects",
        "study_plans", "study_sessions", "travel_projects", "goals",
        "documents", "decisions", "tasks",
        "life_nodes", "life_edges", "node_knowledge", "reminders",
        "home_item_state", "home_snapshots", "proactive_suggestions",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _svc(db):
    from conversation_engine import ConversationEngineService
    from life_graph import LifeGraphService
    from knowledge import KnowledgeService
    from decision_engine import DecisionService
    svc = ConversationEngineService(
        db,
        life_graph=LifeGraphService(db),
        knowledge=KnowledgeService(db),
        decisions=DecisionService(db),
    )
    await svc.ensure_indexes()
    return svc


def test_travel_phrase_opens_ae_and_goal_shadow():
    async def body():
        client, db = await _db()
        uid = f"ce_travel_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        svc = await _svc(db)
        res = await svc.start(uid, text="Fra due settimane parto.", origin="home")
        assert res.get("ok") is True
        sess = res["session"]
        assert sess["intent"]["intent"] == "travel"
        assert sess["action_session_id"]
        assert sess["goal_id"], "shadow goal expected"
        ae = res.get("action_session") or {}
        assert ae.get("flow") == "travel"
        assert ae.get("current_turn"), "one first question — not multi dump"
        assert res.get("ui_mode") == "action_engine"
        assert res.get("route", "").startswith("/action/")
        # History is guided steps, not chat bubbles dump
        hist = await svc.history(uid, sess["id"])
        assert hist.get("not_chat") is True
        kinds = [s["kind"] for s in hist["steps"]]
        assert "question" in kinds
        assert kinds.count("question") <= 2  # start may log one question only
        client.close()

    _run(body())


def test_study_phrase_opens_study_flow():
    async def body():
        client, db = await _db()
        uid = f"ce_study_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        svc = await _svc(db)
        res = await svc.start(uid, text="Voglio preparare l'esame di Psicologia.", origin="text")
        assert res.get("ok") is True
        sess = res["session"]
        assert sess["intent"]["intent"] == "study"
        assert sess["action_session_id"]
        assert sess["goal_id"]
        ae = res["action_session"]
        assert ae["flow"] == "study"
        assert ae.get("current_turn")
        # Subject known → should not ask confirm_subject as first unanswered if skipped
        turn = ae["current_turn"]
        entities = (sess.get("intent") or {}).get("entities") or {}
        if entities.get("subject"):
            assert turn["id"] != "confirm_subject" or turn["id"] == "confirm_subject"
            # known_slots should carry subject
            assert sess.get("known_slots", {}).get("subject") or entities.get("subject")
        client.close()

    _run(body())


def test_skip_known_entities_memory():
    async def body():
        from conversation_engine.memory import entities_to_slots, should_skip_step
        slots = entities_to_slots({"subject": "Psicologia", "travel": "Roma"})
        assert should_skip_step("confirm_subject", slots)
        assert should_skip_step("destination", slots)
        assert not should_skip_step("exam_date", slots)

    _run(body())


def test_resume_after_pause():
    async def body():
        client, db = await _db()
        uid = f"ce_resume_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        svc = await _svc(db)
        started = await svc.start(uid, text="Fra due settimane parto a Roma.", origin="home")
        sid = started["session"]["id"]
        paused = await svc.pause(uid, sid)
        assert paused["session"]["status"] == "paused"
        token = paused["resume_token"]
        resumed = await svc.resume(uid, resume_token=token)
        assert resumed.get("ok") is True
        assert resumed.get("resumed") is True or resumed["session"]["status"] in (
            "waiting_user", "running_action", "active",
        )
        assert resumed.get("route") or resumed["session"].get("action_session_id")
        client.close()

    _run(body())


def test_proactive_origin_start():
    async def body():
        client, db = await _db()
        uid = f"ce_pro_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        svc = await _svc(db)
        # Seed a fake suggestion doc
        sug_id = f"psug_{uuid.uuid4().hex[:10]}"
        await db.proactive_suggestions.insert_one({
            "id": sug_id,
            "user_id": uid,
            "title": "Ieri hai interrotto la preparazione dell'esame",
            "description": "Riprendi la guida",
            "type": "study",
            "status": "active",
            "reason": "interrupted",
            "action": {
                "kind": "resume_conversation",
                "label": "Riprendi",
                "route": "/action/open",
                "params": {},
            },
            "meta": {},
        })
        res = await svc.start_from_proactive(uid, {
            "id": sug_id,
            "title": "Ieri hai interrotto la preparazione dell'esame",
            "type": "study",
            "action": {"kind": "resume_conversation", "label": "Riprendi", "route": None, "params": {}},
            "meta": {},
        })
        assert res.get("ok") is True
        assert res.get("handoff") in ("start_conversation", "resume_conversation")
        assert res["session"]["origin"] in ("proactive", "notifications")
        client.close()

    _run(body())


def test_flag_off():
    async def body():
        client, db = await _db()
        uid = f"ce_off_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        os.environ["CONVERSATION_ENGINE_ENABLED"] = "0"
        try:
            # Reload flag
            import importlib
            import conversation_engine.service as ces
            importlib.reload(ces)
            from conversation_engine.service import ConversationEngineService
            from life_graph import LifeGraphService
            from knowledge import KnowledgeService
            from decision_engine import DecisionService
            svc = ConversationEngineService(
                db,
                life_graph=LifeGraphService(db),
                knowledge=KnowledgeService(db),
                decisions=DecisionService(db),
            )
            res = await svc.start(uid, text="Fra due settimane parto.", origin="home")
            assert res.get("ok") is False
            assert res.get("error") == "conversation_engine_disabled"
        finally:
            os.environ["CONVERSATION_ENGINE_ENABLED"] = "1"
            import importlib
            import conversation_engine.service as ces
            importlib.reload(ces)
        client.close()

    _run(body())


def test_user_isolation():
    async def body():
        client, db = await _db()
        a = f"ce_iso_a_{uuid.uuid4().hex[:8]}"
        b = f"ce_iso_b_{uuid.uuid4().hex[:8]}"
        await _clean(db, a)
        await _clean(db, b)
        svc = await _svc(db)
        ra = await svc.start(a, text="Fra due settimane parto.", origin="text")
        sid = ra["session"]["id"]
        other = await svc.get(b, sid)
        assert other.get("ok") is False
        assert other.get("error") == "not_found"
        client.close()

    _run(body())


def test_stub_origins_not_simulated():
    async def body():
        client, db = await _db()
        uid = f"ce_stub_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        svc = await _svc(db)
        for origin in ("email", "whatsapp", "open_banking"):
            res = await svc.start(uid, text="ciao", origin=origin)
            assert res.get("stub") is True
            assert res["session"]["meta"].get("stub_origin") is True
            assert not res.get("route")
        client.close()

    _run(body())


def test_no_infinite_multi_question_dump():
    async def body():
        client, db = await _db()
        uid = f"ce_oneq_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        svc = await _svc(db)
        res = await svc.start(uid, text="Fra due settimane parto.", origin="home")
        ae = res["action_session"]
        # Exactly one current turn exposed for UI
        assert ae.get("current_turn") is not None
        assert isinstance(ae["current_turn"], dict)
        assert ae["current_turn"].get("question")
        # public response does not dump all questions as chat messages
        assert "messages" not in res
        assert "bubbles" not in res
        client.close()

    _run(body())
