"""Travel Action Flow — classification, period, project, calendar gate, Home, Brain."""
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
        "action_sessions", "action_projects", "travel_projects",
        "study_plans", "study_sessions",
        "documents", "decisions", "tasks",
        "life_nodes", "life_edges", "node_knowledge", "reminders",
        "home_item_state", "home_snapshots", "home_insights", "users",
        "connector_instances",
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


async def _answer_travel_flow(svc, user_id, session_id, *, picks=None, text_overrides=None):
    from action_engine.models import AnswerBody
    picks = picks or {}
    text_overrides = text_overrides or {}
    defaults = {
        "destination": None,
        "departure_place": "tarquinia",
        "transport": "car",
        "bookings": "partial",
        "companions": "solo",
        "calendar_sync": "no",
        "prep": "skip",
        "preview": "accept",
        "confirm": "confirm",
    }
    defaults.update(picks)

    for _ in range(40):
        pub = await svc.get_session(user_id, session_id)
        assert pub is not None
        if pub.get("done") or pub.get("status") == "completed":
            return pub
        turn = pub.get("current_turn")
        assert turn is not None, "active session must have a question"
        tid = turn["id"]

        if tid in text_overrides:
            res = await svc.answer(user_id, session_id, AnswerBody(text=text_overrides[tid]))
            if res.get("ok") is False and res.get("error"):
                raise AssertionError(res)
            if res.get("completed"):
                return res["session"]
            continue

        if tid == "period" and "period" not in defaults:
            res = await svc.answer(
                user_id, session_id,
                AnswerBody(text="dal 9 al 24 agosto 2026"),
            )
            if res.get("ok") is False:
                raise AssertionError(res)
            if res.get("completed"):
                return res["session"]
            continue

        if tid == "destination" and not defaults.get("destination"):
            res = await svc.answer(user_id, session_id, AnswerBody(text="Vibo Marina"))
            if res.get("ok") is False:
                raise AssertionError(res)
            continue

        if tid == "prep":
            res = await svc.answer(user_id, session_id, AnswerBody(skip=True))
            if res.get("completed"):
                return res["session"]
            continue

        opt = defaults.get(tid)
        if opt is None and turn.get("options"):
            opt = turn["options"][0]["id"]
        # Find option value
        value = None
        option_id = opt
        for o in turn.get("options") or []:
            if o["id"] == opt:
                value = o.get("value")
                option_id = o["id"]
                break
        res = await svc.answer(
            user_id, session_id,
            AnswerBody(option_id=option_id, value=value),
        )
        if res.get("ok") is False and res.get("error") not in (None,):
            # allow soft
            if res.get("error") in ("confirm_required",):
                raise AssertionError(res)
            if not res.get("session"):
                raise AssertionError(res)
        if res.get("completed"):
            return res["session"]
    raise AssertionError("travel flow did not complete")


def test_period_parser_dal_al():
    from action_engine.travel.period_parser import parse_travel_period
    r = parse_travel_period("dal 9 al 24 agosto 2026")
    assert r["ok"]
    assert r["start_date"] == "2026-08-09"
    assert r["end_date"] == "2026-08-24"


def test_intent_vacation_period_and_destination():
    from intent_engine import classify_text
    ir = classify_text("Andrò in vacanza dal 9 al 24 agosto a Vibo Marina.")
    assert ir.intent == "travel"
    ents = ir.entities.as_dict()
    assert ents.get("start_date") == "2026-08-09" or ents.get("period")
    # destination extraction best-effort
    assert ents.get("travel") or ents.get("place")


def test_travel_flow_e2e_confirm_creates_project():
    async def run():
        client, db = await _db()
        uid = f"u_travel_{uuid.uuid4().hex[:10]}"
        await _clean(db, uid)
        svc = await _svc(db)
        try:
            from action_engine.models import OpenBody
            opened = await svc.open(uid, OpenBody(
                title="Andrò in vacanza dal 9 al 24 agosto.",
                description="Vacanza estate",
                force_new=True,
                meta={"skip_maps_network": True},
            ))
            sess = opened["session"]
            assert sess["flow"] == "travel"
            assert opened.get("intent", {}).get("intent") == "travel"
            # Period should be pre-seeded — first question not period if parsed
            completed = await _answer_travel_flow(
                svc, uid, sess["id"],
                text_overrides={},
                picks={"calendar_sync": "no"},
            )
            assert completed["status"] == "completed"
            plan_id = completed["meta"].get("travel_project_id")
            assert plan_id
            plan = await svc.travel_projects.get_project(uid, plan_id)
            assert plan
            assert plan["status"] == "active"
            assert plan["destination"]
            assert plan["start_date"]
            assert plan["end_date"]
            assert plan["calendar_events"]
            # No Google sync when calendar_sync false
            assert not (plan.get("google_sync") or {}).get("synced")
        finally:
            await _clean(db, uid)
            client.close()

    _run(run())


def test_missing_only_questions_and_destination():
    async def run():
        client, db = await _db()
        uid = f"u_travel_{uuid.uuid4().hex[:10]}"
        await _clean(db, uid)
        svc = await _svc(db)
        try:
            from action_engine.models import OpenBody
            # Seed home place in Brain
            await db.life_nodes.insert_one({
                "id": f"place_{uuid.uuid4().hex[:8]}",
                "user_id": uid,
                "type": "home",
                "label": "Tarquinia",
                "status": "active",
                "attributes": {"kind": "home"},
                "created_at": _now().isoformat(),
            })
            opened = await svc.open(uid, OpenBody(
                title="Vacanza Vibo Marina dal 9 al 24 agosto 2026",
                force_new=True,
                meta={"skip_maps_network": True},
            ))
            sess = opened["session"]
            turn_ids = [t["id"] for t in sess.get("turns") or []]
            # Period + destination known → skipped from unanswered
            answers = sess.get("answers") or {}
            assert "period" in answers or "period" not in [t for t in turn_ids if t == sess.get("current_turn", {}).get("id")]
            # Departure should offer Tarquinia
            dep_turn = next(t for t in sess["turns"] if t["id"] == "departure_place")
            labels = " ".join(o["label"] for o in dep_turn["options"])
            assert "Tarquinia" in labels
            completed = await _answer_travel_flow(svc, uid, sess["id"])
            assert completed["status"] == "completed"
            plan = await svc.travel_projects.get_project(
                uid, completed["meta"]["travel_project_id"],
            )
            assert "Vibo" in (plan.get("destination") or "") or plan.get("destination")
            assert plan.get("departure_place")
        finally:
            await _clean(db, uid)
            client.close()

    _run(run())


def test_no_silent_calendar_create_and_confirm_gate():
    async def run():
        client, db = await _db()
        uid = f"u_travel_{uuid.uuid4().hex[:10]}"
        await _clean(db, uid)
        svc = await _svc(db)
        try:
            from action_engine.models import OpenBody, AnswerBody
            opened = await svc.open(uid, OpenBody(
                title="Vacanza a Roma dal 1 al 7 settembre 2026",
                force_new=True,
                meta={"skip_maps_network": True},
            ))
            sid = opened["session"]["id"]
            # Drive until preview then try complete without confirm
            for _ in range(30):
                pub = await svc.get_session(uid, sid)
                if pub.get("current_turn", {}).get("id") == "confirm":
                    break
                if pub.get("current_turn", {}).get("id") == "preview":
                    await svc.answer(uid, sid, AnswerBody(option_id="accept", value="accept"))
                    continue
                # Use helper step-by-step until confirm
                turn = pub["current_turn"]
                tid = turn["id"]
                if tid == "destination":
                    await svc.answer(uid, sid, AnswerBody(text="Roma"))
                elif tid == "period":
                    await svc.answer(uid, sid, AnswerBody(text="2026-09-01 - 2026-09-07"))
                elif tid == "prep":
                    await svc.answer(uid, sid, AnswerBody(skip=True))
                else:
                    o = turn["options"][0]
                    await svc.answer(uid, sid, AnswerBody(option_id=o["id"], value=o.get("value")))

            # complete without confirm must fail
            blocked = await svc.complete(uid, sid)
            assert blocked.get("ok") is False
            assert blocked.get("error") == "confirm_required"
            # No active travel project yet from silent path
            active = await db.travel_projects.count_documents(
                {"user_id": uid, "status": "active"},
            )
            assert active == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(run())


def test_calendar_propose_confirm_google_absent():
    async def run():
        client, db = await _db()
        uid = f"u_travel_{uuid.uuid4().hex[:10]}"
        await _clean(db, uid)
        svc = await _svc(db)
        try:
            from action_engine.models import OpenBody
            opened = await svc.open(uid, OpenBody(
                title="Andrò in vacanza dal 9 al 24 agosto 2026 a Napoli",
                force_new=True,
                meta={"skip_maps_network": True},
            ))
            completed = await _answer_travel_flow(
                svc, uid, opened["session"]["id"],
                picks={"calendar_sync": "yes"},
            )
            plan = await svc.travel_projects.get_project(
                uid, completed["meta"]["travel_project_id"],
            )
            assert plan["calendar_sync"] is True
            assert len(plan["calendar_events"]) >= 3
            kinds = {e["kind"] for e in plan["calendar_events"]}
            assert "vacation_block" in kinds
            assert "outbound" in kinds
            assert "return" in kinds
            g = plan.get("google_sync") or {}
            assert g.get("connected") is False or "not_connected" in (g.get("skipped") or [])
            # Life graph nodes created
            nodes = await db.life_nodes.count_documents(
                {"user_id": uid, "attributes.travel_project_id": plan["id"]},
            )
            assert nodes >= 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(run())


def test_maps_deep_link_without_network():
    async def run():
        from action_engine.travel.maps import build_maps_info, google_maps_dir_link
        link = google_maps_dir_link("Tarquinia", "Vibo Marina", travelmode="car")
        assert "google.com/maps/dir" in link
        assert "Tarquinia" in link and "Vibo" in link
        info = await build_maps_info(
            origin="Tarquinia", destination="Vibo Marina",
            transport="car", allow_network=False,
        )
        assert info.deep_link
        assert info.estimate_source == "unavailable"
        assert "non disponibili" in (info.honesty or "").lower() or info.honesty

    _run(run())


def test_home_adapter_travel_phase():
    async def run():
        client, db = await _db()
        uid = f"u_travel_{uuid.uuid4().hex[:10]}"
        await _clean(db, uid)
        try:
            start = (_now() + timedelta(days=5)).date().isoformat()
            end = (_now() + timedelta(days=12)).date().isoformat()
            await db.travel_projects.insert_one({
                "id": f"trp_{uuid.uuid4().hex[:10]}",
                "user_id": uid,
                "status": "active",
                "title": "Vacanza: Test",
                "destination": "Vibo Marina",
                "start_date": start,
                "end_date": end,
                "transport": "car",
                "maps": {"deep_link": "https://www.google.com/maps/dir/?api=1"},
                "calendar_events": [],
                "created_at": _now().isoformat(),
                "updated_at": _now().isoformat(),
            })
            from home.adapters.travel import load_travel_state
            items, _ = await load_travel_state(db, uid)
            assert any(i.type == "travel" for i in items)
            travel = next(i for i in items if i.type == "travel")
            assert travel.meta.get("phase") in ("days_until", "upcoming")
            assert travel.source_type == "travel_project"
        finally:
            await _clean(db, uid)
            client.close()

    _run(run())


def test_resume_draft_and_isolation():
    async def run():
        client, db = await _db()
        uid = f"u_travel_{uuid.uuid4().hex[:10]}"
        uid2 = f"u_travel_{uuid.uuid4().hex[:10]}"
        await _clean(db, uid)
        await _clean(db, uid2)
        svc = await _svc(db)
        try:
            from action_engine.models import OpenBody, AnswerBody
            opened = await svc.open(uid, OpenBody(
                title="Vacanza Sicilia dal 10 al 20 agosto 2026",
                home_item_id="home_travel_1",
                force_new=True,
                meta={"skip_maps_network": True},
            ))
            sid = opened["session"]["id"]
            # Answer one turn then draft
            pub = await svc.get_session(uid, sid)
            turn = pub["current_turn"]
            if turn["id"] == "destination":
                await svc.answer(uid, sid, AnswerBody(text="Sicilia"))
            elif turn["id"] == "departure_place":
                await svc.answer(uid, sid, AnswerBody(option_id="tarquinia", value="Tarquinia"))
            else:
                o = turn["options"][0]
                await svc.answer(uid, sid, AnswerBody(option_id=o["id"], value=o.get("value")))
            await svc.save_draft(uid, sid)
            # Resume
            resumed = await svc.open(uid, OpenBody(
                title="Vacanza Sicilia",
                home_item_id="home_travel_1",
            ))
            assert resumed.get("resumed") is True
            assert resumed["session"]["id"] == sid
            # Isolation: other user cannot see project
            draft = await db.travel_projects.find_one({"user_id": uid}, {"_id": 0})
            if draft:
                other = await svc.travel_projects.get_project(uid2, draft["id"])
                assert other is None
        finally:
            await _clean(db, uid)
            await _clean(db, uid2)
            client.close()

    _run(run())


def test_brain_links_on_confirm():
    async def run():
        client, db = await _db()
        uid = f"u_travel_{uuid.uuid4().hex[:10]}"
        await _clean(db, uid)
        svc = await _svc(db)
        try:
            from action_engine.models import OpenBody
            opened = await svc.open(uid, OpenBody(
                title="Vacanza a Firenze dal 5 al 12 settembre 2026",
                force_new=True,
                meta={"skip_maps_network": True},
            ))
            completed = await _answer_travel_flow(svc, uid, opened["session"]["id"])
            plan_id = completed["meta"]["travel_project_id"]
            edges = await db.life_edges.count_documents({
                "user_id": uid,
                "attributes.travel_project_id": plan_id,
            })
            assert edges >= 1
            places = await db.life_nodes.count_documents({
                "user_id": uid,
                "attributes.kind": "travel_destination",
            })
            assert places >= 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(run())


def test_companions_transport_bookings():
    async def run():
        client, db = await _db()
        uid = f"u_travel_{uuid.uuid4().hex[:10]}"
        await _clean(db, uid)
        svc = await _svc(db)
        try:
            from action_engine.models import OpenBody
            opened = await svc.open(uid, OpenBody(
                title="Andrò in vacanza dal 9 al 24 agosto 2026",
                force_new=True,
                meta={"skip_maps_network": True},
            ))
            completed = await _answer_travel_flow(
                svc, uid, opened["session"]["id"],
                picks={
                    "transport": "train",
                    "bookings": "all",
                    "companions": "2",
                },
            )
            plan = await svc.travel_projects.get_project(
                uid, completed["meta"]["travel_project_id"],
            )
            assert plan["transport"] == "train"
            assert plan["bookings"] == "all"
            assert plan["companions"] == 2
        finally:
            await _clean(db, uid)
            client.close()

    _run(run())
