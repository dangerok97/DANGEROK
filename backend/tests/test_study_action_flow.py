"""Study Action Flow — comprehensive coverage (intent → confirm → Home)."""
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
        "action_sessions", "action_projects", "study_plans", "study_sessions",
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


async def _answer_study_flow(svc, user_id, session_id, *, picks=None, text_overrides=None):
    """Drive study flow to confirm via UI-equivalent answers (not silent API complete)."""
    from action_engine.models import AnswerBody
    picks = picks or {}
    text_overrides = text_overrides or {}
    exam_iso = (_now() + timedelta(days=21)).date().isoformat()
    defaults = {
        "exam_date": None,  # use text
        "select_materials": "none",
        "daily_time": "1h",
        "available_days": None,  # multi
        "preferred_time_ranges": "evening",
        "intensity": "distributed",
        "tools": None,  # multi
        "calendar_sync": "no",
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
            if res.get("completed"):
                return res["session"]
            continue

        if tid == "exam_date" and not defaults.get("exam_date"):
            res = await svc.answer(user_id, session_id, AnswerBody(text=exam_iso))
            if res.get("ok") is False and res.get("error"):
                raise AssertionError(res)
            if res.get("completed"):
                return res["session"]
            continue

        if tid == "available_days":
            res = await svc.answer(
                user_id, session_id,
                AnswerBody(value=[0, 1, 2, 3, 4]),
            )
            if res.get("completed"):
                return res["session"]
            continue

        if tid == "tools":
            res = await svc.answer(
                user_id, session_id,
                AnswerBody(value=["study", "review", "flashcards"]),
            )
            if res.get("completed"):
                return res["session"]
            continue

        if tid == "select_materials":
            opt_id = defaults.get("select_materials") or "none"
            # prefer first doc chip if present
            doc_opts = [o for o in turn.get("options") or [] if str(o["id"]).startswith("doc_")]
            if opt_id == "use_first_doc" and doc_opts:
                res = await svc.answer(user_id, session_id, AnswerBody(
                    option_id=doc_opts[0]["id"], value=[doc_opts[0]["value"]],
                ))
            else:
                # Fall back to none when search didn't surface docs
                fallback = opt_id if opt_id != "use_first_doc" else "none"
                res = await svc.answer(user_id, session_id, AnswerBody(option_id=fallback, value=[]))
            if res.get("ok") is False and res.get("error") == "answer_required":
                res = await svc.answer(user_id, session_id, AnswerBody(value=[]))
            if res.get("completed"):
                return res["session"]
            continue

        opt_id = defaults.get(tid)
        if not opt_id and turn.get("options"):
            opt_id = turn["options"][0]["id"]
        res = await svc.answer(user_id, session_id, AnswerBody(option_id=opt_id))
        if res.get("ok") is False and res.get("error") in ("impossible_plan",):
            # recover: pick more days already done — fail test
            raise AssertionError(res)
        if res.get("completed"):
            return res.get("session") or (await svc.get_session(user_id, session_id))
    raise AssertionError("study flow did not complete")


def test_date_parser_relative_and_ambiguous():
    from action_engine.study.date_parser import parse_exam_date
    r = parse_exam_date("in_2_weeks")
    assert r["ok"] is True
    r2 = parse_exam_date("15/12/2099")
    assert r2["ok"] is True
    bad = parse_exam_date("not a date")
    assert bad["ok"] is False


def test_intent_received_and_subject_extracted():
    from intent_engine import classify_text
    from action_engine.flows import resolve_flow_from_intent
    ir = classify_text("Preparazione esame di Psicologia")
    assert ir.intent == "study"
    assert ir.subtype == "exam_preparation" or ir.entities.subject
    assert resolve_flow_from_intent(ir.intent, ir.subtype) == "study"
    assert ir.entities.subject and "psicolog" in ir.entities.subject.lower()


def test_study_flow_e2e_confirm_creates_plan():
    async def body():
        client, db = await _db()
        user = f"u_study_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            await db.documents.insert_one({
                "id": doc_id, "user_id": user,
                "filename": "psicologia.pdf",
                "display_title": "Appunti Psicologia",
                "analysis": {"macro_category": "education", "keywords": ["psicologia"]},
                "education_analysis": {"subject": "Psicologia", "topic": "Memoria"},
                "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
            })
            svc = await _svc(db)
            from action_engine.models import OpenBody
            from intent_engine import classify_text
            intent = classify_text("Preparazione esame di Psicologia")
            opened = await svc.open(user, OpenBody(
                title="Preparazione esame di Psicologia",
                home_item_id="home_psy_1",
                intent=intent.public(),
            ))
            session = opened["session"]
            # 1) intent received
            assert session["flow"] == "study"
            assert session["meta"]["intent"] == "study"
            # 2) subject extracted — confirm_subject skipped
            assert session["current_turn"]["id"] == "exam_date"
            assert session["answers"].get("confirm_subject") or session["meta"]["intent_entities"].get("subject")

            done = await _answer_study_flow(svc, user, session["id"], picks={
                "select_materials": "use_first_doc",
                "intensity": "distributed",
                "calendar_sync": "no",
            })
            assert done["status"] == "completed"
            plan_id = done["meta"].get("study_plan_id") or (done.get("effects") or {}).get("study_plan_id")
            assert plan_id
            plan = await db.study_plans.find_one({"id": plan_id, "user_id": user})
            assert plan is not None
            assert plan["status"] == "active"
            assert plan["exam_name"]
            assert len(plan.get("sessions") or []) >= 2
            # sessions persisted
            n = await db.study_sessions.count_documents({"plan_id": plan_id, "user_id": user})
            assert n >= 2
            # Home update — study plan surfaces
            from home.service import HomeService
            home = await HomeService(db).build_home(user)
            home_d = home.model_dump() if hasattr(home, "model_dump") else dict(home)
            titles = [(home_d.get("primary_focus") or {}).get("title", "")]
            titles += [i.get("title", "") for i in (home_d.get("priorities") or [])]
            titles += [i.get("title", "") for i in (home_d.get("items") or [])]
            blob = " ".join(str(t) for t in titles).lower()
            plan_on_home = await db.study_plans.find_one({"id": plan_id, "status": "active"})
            assert plan_on_home is not None
            from home.adapters.study import load_study_state
            items, _ = await load_study_state(db, user)
            assert any(
                (i.meta or {}).get("study_plan_id") == plan_id or i.source_id == plan_id
                for i in items
            ), f"plan not on Home study adapter; titles={blob!r}"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_docs_found_and_none():
    async def body():
        client, db = await _db()
        user = f"u_docs_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            from action_engine.study.documents import search_study_documents
            empty = await search_study_documents(db, user_id=user, subject="Psicologia")
            assert empty["empty"] is True
            await db.documents.insert_one({
                "id": f"doc_{uuid.uuid4().hex[:8]}", "user_id": user,
                "display_title": "Psicologia cognitiva",
                "analysis": {"macro_category": "education"},
                "education_analysis": {"subject": "Psicologia"},
                "deleted": False,
            })
            found = await search_study_documents(db, user_id=user, subject="Psicologia")
            assert found["empty"] is False
            assert found["total"] >= 1
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_intensities_and_impossible_plan():
    from action_engine.study.generator import generate_plan_sessions
    exam = (_now() + timedelta(days=20)).isoformat()
    for intensity in ("light", "distributed", "intensive", "custom"):
        gen = generate_plan_sessions(
            user_id="u", plan_id="p", exam_name="X", subject="X",
            exam_date_iso=exam, daily_minutes=60, available_days=[0, 1, 2, 3, 4],
            intensity=intensity,
        )
        assert gen["ok"] is True, intensity
        assert len(gen["sessions"]) >= 2
    # impossible: no days
    bad = generate_plan_sessions(
        user_id="u", plan_id="p", exam_name="X", subject="X",
        exam_date_iso=exam, daily_minutes=60, available_days=[],
        intensity="distributed",
    )
    assert bad["ok"] is False


def test_idempotency_and_duplicate_plan():
    async def body():
        client, db = await _db()
        user = f"u_idem_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            svc = await _svc(db)
            from action_engine.models import OpenBody, AnswerBody
            from intent_engine import classify_text
            intent = classify_text("Esame di Psicologia")
            o1 = await svc.open(user, OpenBody(
                title="Esame di Psicologia", home_item_id="h1", intent=intent.public(),
            ))
            done1 = await _answer_study_flow(svc, user, o1["session"]["id"])
            plan_id = done1["meta"]["study_plan_id"]
            # Re-confirm idempotent
            plan = await svc.study_plans.get_plan(user, plan_id)
            assert plan["status"] == "active"
            again = await svc.study_plans.confirm(user, plan_id)
            assert again.get("already_confirmed") or again.get("ok")

            # Second flow same priority → duplicate handling
            o2 = await svc.open(user, OpenBody(
                title="Esame di Psicologia", home_item_id="h2", intent=intent.public(), force_new=True,
            ))
            # drive until duplicate or confirm
            sid = o2["session"]["id"]
            for _ in range(40):
                pub = await svc.get_session(user, sid)
                if pub.get("done"):
                    break
                turn = pub["current_turn"]
                tid = turn["id"]
                if tid == "duplicate_resolution":
                    res = await svc.answer(user, sid, AnswerBody(option_id="open", value="open"))
                    assert res.get("opened_plan_id") or res.get("completed")
                    break
                if tid == "exam_date":
                    await svc.answer(user, sid, AnswerBody(text=(_now() + timedelta(days=21)).date().isoformat()))
                elif tid == "available_days":
                    await svc.answer(user, sid, AnswerBody(value=[0, 1, 2, 3, 4]))
                elif tid == "tools":
                    await svc.answer(user, sid, AnswerBody(value=["study", "review"]))
                elif tid == "confirm":
                    res = await svc.answer(user, sid, AnswerBody(option_id="confirm", value="confirm"))
                    # may surface duplicate
                    if res.get("error") == "duplicate" or pub.get("current_turn", {}).get("id") == "duplicate_resolution":
                        continue
                    break
                else:
                    opt = (turn.get("options") or [{"id": "x"}])[0]["id"]
                    await svc.answer(user, sid, AnswerBody(option_id=opt))
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_resume_draft_and_logout_persistence():
    async def body():
        client, db = await _db()
        user = f"u_resume_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            svc = await _svc(db)
            from action_engine.models import OpenBody, AnswerBody
            from intent_engine import classify_text
            intent = classify_text("Esame Matematica")
            opened = await svc.open(user, OpenBody(
                title="Esame Matematica", home_item_id="home_math", intent=intent.public(),
            ))
            sid = opened["session"]["id"]
            await svc.answer(user, sid, AnswerBody(
                text=(_now() + timedelta(days=14)).date().isoformat(),
            ))
            draft = await svc.save_draft(user, sid)
            assert draft.get("draft") is True
            plan_id = draft.get("plan_id")
            assert plan_id
            # Simulate logout/login: resume by home_item_id
            resumed = await svc.open(user, OpenBody(
                title="Esame Matematica", home_item_id="home_math", intent=intent.public(),
            ))
            assert resumed.get("resumed") is True
            assert resumed["session"]["id"] == sid
            assert resumed["session"]["answers"].get("exam_date")
            # Cancel keeps draft plan
            await svc.cancel(user, sid)
            plan = await db.study_plans.find_one({"id": plan_id})
            assert plan is not None
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_back_navigation_and_preview_modify():
    async def body():
        client, db = await _db()
        user = f"u_back_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            svc = await _svc(db)
            from action_engine.models import OpenBody, AnswerBody
            from intent_engine import classify_text
            from action_engine.study.models import PlanModifyBody
            intent = classify_text("Esame Storia")
            opened = await svc.open(user, OpenBody(
                title="Esame Storia", home_item_id="hs", intent=intent.public(),
            ))
            sid = opened["session"]["id"]
            await svc.answer(user, sid, AnswerBody(text=(_now() + timedelta(days=30)).date().isoformat()))
            cur = (await svc.get_session(user, sid))["current_turn"]["id"]
            assert cur == "select_materials"
            back = await svc.back(user, sid)
            assert back["session"]["current_turn"]["id"] == "exam_date"
            # Re-answer and jump to preview via full flow partial
            await svc.answer(user, sid, AnswerBody(text=(_now() + timedelta(days=30)).date().isoformat()))
            # finish to preview quickly
            for _ in range(20):
                pub = await svc.get_session(user, sid)
                if pub["current_turn"]["id"] == "preview":
                    break
                tid = pub["current_turn"]["id"]
                if tid == "available_days":
                    await svc.answer(user, sid, AnswerBody(value=[0, 2, 4]))
                elif tid == "tools":
                    await svc.answer(user, sid, AnswerBody(value=["study"]))
                else:
                    opt = pub["current_turn"]["options"][0]["id"]
                    await svc.answer(user, sid, AnswerBody(option_id=opt))
            mod = await svc.modify_preview(user, sid, PlanModifyBody(intensity="intensive", daily_minutes=90))
            assert mod.get("ok") is True
            assert mod["preview"]["intensity"] == "intensive"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_google_absent_and_delete_isolation():
    async def body():
        client, db = await _db()
        u1 = f"u_g1_{uuid.uuid4().hex[:6]}"
        u2 = f"u_g2_{uuid.uuid4().hex[:6]}"
        try:
            await _clean(db, u1)
            await _clean(db, u2)
            await db.users.insert_one({"user_id": u1, "email": f"{u1}@t.ora"})
            await db.users.insert_one({"user_id": u2, "email": f"{u2}@t.ora"})
            svc = await _svc(db)
            from action_engine.models import OpenBody
            from intent_engine import classify_text
            intent = classify_text("Esame Biologia")
            o = await svc.open(u1, OpenBody(title="Esame Biologia", home_item_id="hb", intent=intent.public()))
            assert o["session"]["meta"].get("google_connected") is False
            done = await _answer_study_flow(svc, u1, o["session"]["id"])
            plan_id = done["meta"]["study_plan_id"]
            # Gemini absent — plan still created (deterministic)
            plan = await svc.study_plans.get_plan(u1, plan_id)
            assert plan["status"] == "active"
            # Isolation: u2 cannot read
            other = await svc.study_plans.get_plan(u2, plan_id)
            assert other is None
            # Delete
            await svc.study_plans.delete_plan(u1, plan_id)
            deleted = await svc.study_plans.get_plan(u1, plan_id)
            assert deleted["status"] == "cancelled"
        finally:
            await _clean(db, u1)
            await _clean(db, u2)
            client.close()
    _run(body())


def test_session_actions_and_complete_blocked_without_confirm():
    async def body():
        client, db = await _db()
        user = f"u_act_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            svc = await _svc(db)
            from action_engine.models import OpenBody
            from intent_engine import classify_text
            intent = classify_text("Esame Chimica")
            o = await svc.open(user, OpenBody(title="Esame Chimica", home_item_id="hc", intent=intent.public()))
            # API complete without confirm must fail
            blocked = await svc.complete(user, o["session"]["id"])
            assert blocked.get("error") == "confirm_required"
            done = await _answer_study_flow(svc, user, o["session"]["id"])
            plan_id = done["meta"]["study_plan_id"]
            plan = await svc.study_plans.get_plan(user, plan_id)
            sid = plan["sessions"][0]["id"]
            started = await svc.study_plans.session_action(user, sid, "start")
            assert started["session"]["status"] == "in_progress"
            done_s = await svc.study_plans.session_action(user, sid, "complete")
            assert done_s["session"]["status"] == "completed"
            # snooze another
            if len(plan["sessions"]) > 1:
                s2 = plan["sessions"][1]["id"]
                sn = await svc.study_plans.session_action(user, s2, "snooze", snooze_minutes=120)
                assert sn["session"]["status"] == "snoozed"
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_upload_mid_flow_keeps_answers():
    async def body():
        client, db = await _db()
        user = f"u_up_{uuid.uuid4().hex[:8]}"
        try:
            await _clean(db, user)
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})
            svc = await _svc(db)
            from action_engine.models import OpenBody, AnswerBody
            from intent_engine import classify_text
            intent = classify_text("Esame Fisica")
            o = await svc.open(user, OpenBody(title="Esame Fisica", home_item_id="hf", intent=intent.public()))
            sid = o["session"]["id"]
            await svc.answer(user, sid, AnswerBody(text=(_now() + timedelta(days=18)).date().isoformat()))
            res = await svc.answer(user, sid, AnswerBody(option_id="upload", value="__upload__"))
            assert res.get("upload_required") is True
            assert res["session"]["answers"].get("exam_date")
            # Resume search docs
            await db.documents.insert_one({
                "id": f"doc_{uuid.uuid4().hex[:8]}", "user_id": user,
                "display_title": "Fisica 1", "analysis": {"macro_category": "education"},
                "education_analysis": {"subject": "Fisica"}, "deleted": False,
            })
            searched = await svc.search_docs(user, sid)
            assert searched["ok"] is True
            assert searched["session"]["answers"].get("exam_date")
        finally:
            await _clean(db, user)
            client.close()
    _run(body())


def test_study_exam_identity_a_known_subject_psicologia():
    """A — known subject → exam question contains Psicologia (schema convention)."""
    from action_engine.study.flow import build_turns

    turns = build_turns({
        "intent_entities": {"subject": "Psicologia"},
        "title": "Preparazione esame di Psicologia",
        "display_title": "Psicologia",
    })
    date_q = next(t for t in turns if t.id == "exam_date")
    assert "Psicologia" in date_q.question
    assert date_q.question == "Quando è l'esame di Psicologia?"
    assert not any(t.id == "confirm_subject" for t in turns)


def test_study_exam_identity_b_insight_title_not_exam_name():
    """B — unknown exam + insight/home title must NOT appear in questions."""
    from action_engine.study.flow import build_turns, _subject_from_ctx

    insight = "Adesso posso seguire il ritmo dello studio senza perdere pezzi"
    ctx = {
        "intent_entities": {},
        "title": insight,
        "display_title": insight,
    }
    assert _subject_from_ctx(ctx) is None
    turns = build_turns(ctx)
    parts: list[str] = []
    for t in turns:
        parts.append(t.question or "")
        for o in (t.options or []):
            parts.append(o.label or "")
            parts.append(str(o.value))
    blob = " ".join(parts)
    assert insight not in blob
    assert "Adesso posso seguire" not in blob
    date_q = next(t for t in turns if t.id == "exam_date")
    assert date_q.question == "Quando è l'esame?"


def test_study_exam_identity_c_unknown_neutral_question():
    """C — unknown → neutral exam date question."""
    from action_engine.study.flow import build_turns

    turns = build_turns({
        "intent_entities": {},
        "title": "Priorità generica",
        "display_title": "Priorità generica",
    })
    confirm = next(t for t in turns if t.id == "confirm_subject")
    assert "Quale esame" in confirm.question
    assert "Priorità generica" not in confirm.question
    date_q = next(t for t in turns if t.id == "exam_date")
    assert date_q.question == "Quando è l'esame?"


def test_study_exam_identity_d_plan_service_ignores_session_title():
    """D — plan_service must not use session.title as exam identity; e2e still ok."""
    from action_engine.study.plan_service import StudyPlanService

    svc = StudyPlanService(db=None)  # type: ignore[arg-type]
    insight = "Adesso posso seguire..."
    plan = svc.build_draft_from_answers(
        user_id="u_id",
        answers={
            "exam_date": (_now() + timedelta(days=14)).date().isoformat(),
            "daily_time": 60,
            "available_days": [0, 1, 2],
            "preferred_time_ranges": [{"start": "18:00", "end": "20:00"}],
            "intensity": "distributed",
            "tools": ["study"],
            "calendar_sync": False,
        },
        session={"title": insight, "home_item_id": "h1", "meta": {"intent_entities": {}}},
        meta={"timezone": "Europe/Rome"},
    )
    assert insight not in (plan.exam_name or "")
    assert plan.exam_name == "Esame"
    assert plan.subject is None
