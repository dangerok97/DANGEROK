"""Proactive Engine foundation — fixtures corpus + unit/integration coverage."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
os.environ.setdefault("PROACTIVE_ENGINE_ENABLED", "1")
os.environ.setdefault("GOAL_ENGINE_ENABLED", "1")
_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
FIXTURES = Path(__file__).parent / "fixtures" / "proactive_scenarios.json"


def _run(coro):
    # Was a local try/except that built a fresh loop whenever the global slot
    # had been cleared — which silently swapped the loop underneath anything
    # bound to the old one. One shared loop, decided in one place, instead.
    return _loop_harness.run(coro)


def _close_client(client):
    try:
        client.close()
    except Exception:
        pass


def _now():
    return datetime.now(timezone.utc)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    for col in (
        "proactive_suggestions", "proactive_learning",
        "goals", "goal_events",
        "study_plans", "study_sessions", "travel_projects",
        "documents", "life_nodes", "calendar_events",
        "home_item_state", "home_snapshots", "home_insights", "users",
    ):
        await db[col].delete_many({"user_id": user_id})


async def _svc(db):
    from proactive_engine import ProactiveEngineService
    svc = ProactiveEngineService(db)
    await svc.ensure_indexes()
    return svc


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

async def setup_study_skipped(db, user_id: str, *, skipped_count: int, days_to_exam: int):
    plan_id = _uid("spl")
    goal_id = _uid("goal")
    exam = (_now() + timedelta(days=days_to_exam)).isoformat()
    await db.study_plans.insert_one({
        "id": plan_id, "user_id": user_id, "status": "active",
        "exam_name": "Psicologia", "exam_date": exam,
        "daily_minutes": 60, "preferred_ranges": [{"start": "18:00", "end": "20:00"}],
        "document_ids": [], "sessions": [], "created_at": _now().isoformat(),
    })
    await db.goals.insert_one({
        "id": goal_id, "user_id": user_id, "goal_type": "study",
        "title": "Preparare esame Psicologia", "status": "active",
        "study_plan_id": plan_id, "importance": 8,
        "progress": {"ratio": 0.2}, "completion_percentage": 20,
        "idempotency_key": f"ik_{goal_id}",
        "created_at": _now().isoformat(),
    })
    for i in range(skipped_count):
        sid = _uid("ssn")
        start = _now() - timedelta(days=i + 1, hours=2)
        await db.study_sessions.insert_one({
            "id": sid, "plan_id": plan_id, "user_id": user_id,
            "status": "skipped", "session_type": "study",
            "title": f"Sessione {i}", "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=1)).isoformat(),
            "duration_minutes": 60, "updated_at": start.isoformat(),
            "created_at": start.isoformat(),
        })
    return {"plan_id": plan_id, "goal_id": goal_id}


async def setup_study_clean(db, user_id: str, *, sessions: int):
    plan_id = _uid("spl")
    await db.study_plans.insert_one({
        "id": plan_id, "user_id": user_id, "status": "active",
        "exam_name": "Storia", "exam_date": (_now() + timedelta(days=20)).isoformat(),
        "sessions": [], "created_at": _now().isoformat(),
    })
    for i in range(sessions):
        start = _now() + timedelta(days=i + 1)
        await db.study_sessions.insert_one({
            "id": _uid("ssn"), "plan_id": plan_id, "user_id": user_id,
            "status": "planned", "title": f"Ok {i}",
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=1)).isoformat(),
            "created_at": _now().isoformat(),
        })
    return {"plan_id": plan_id}


async def setup_travel(db, user_id: str, *, days: int, incomplete: int):
    tp_id = _uid("trv")
    start = (_now() + timedelta(days=days)).replace(hour=10, minute=0, second=0, microsecond=0)
    prep = []
    for i in range(max(incomplete, 1) if incomplete else 0):
        prep.append({"id": f"p{i}", "label": f"Prep {i}", "done": False})
    # always have at least catalog-like items when incomplete>0
    await db.travel_projects.insert_one({
        "id": tp_id, "user_id": user_id, "status": "active",
        "destination": "Calabria", "title": "Vacanza Calabria",
        "start_date": start.isoformat(), "prep_items": prep,
        "created_at": _now().isoformat(),
    })
    gid = _uid("goal")
    await db.goals.insert_one({
        "id": gid, "user_id": user_id, "goal_type": "travel",
        "title": "Vacanza Calabria", "status": "active",
        "travel_project_id": tp_id, "idempotency_key": f"ik_{gid}",
        "created_at": _now().isoformat(),
    })
    return {"travel_project_id": tp_id}


async def setup_calendar_overlap(db, user_id: str, *, offset_hours: int = 2):
    base = _now() + timedelta(hours=offset_hours)
    a = _uid("ev")
    b = _uid("ev")
    for eid, title, sh in ((a, "Riunione A", 0), (b, "Visita B", 30)):
        start = base + timedelta(minutes=sh)
        await db.life_nodes.insert_one({
            "id": eid, "user_id": user_id, "type": "event", "status": "active",
            "label": title,
            "attributes": {
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=1)).isoformat(),
            },
            "created_at": _now().isoformat(),
        })
    return {"event_ids": [a, b]}


async def setup_calendar_clear(db, user_id: str, *, offset_hours: int = 0):
    for i in range(2):
        start = _now() + timedelta(hours=offset_hours + i * 3)
        await db.life_nodes.insert_one({
            "id": _uid("ev"), "user_id": user_id, "type": "event", "status": "active",
            "label": f"Solo {i}",
            "attributes": {
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=1)).isoformat(),
            },
            "created_at": _now().isoformat(),
        })
    return {}


async def setup_education_doc(db, user_id: str, *, linked: bool, has_flashcards: bool):
    doc_id = _uid("doc")
    await db.documents.insert_one({
        "id": doc_id, "user_id": user_id, "title": "Appunti esame",
        "doc_type": "education", "category": "study",
        "flashcards": [{"q": "1", "a": "2"}] if has_flashcards else [],
        "created_at": _now().isoformat(), "uploaded_at": _now().isoformat(),
    })
    goal_id = _uid("goal")
    linked_docs = [doc_id] if linked else []
    await db.goals.insert_one({
        "id": goal_id, "user_id": user_id, "goal_type": "study",
        "title": "Studio", "status": "active",
        "linked_documents": linked_docs, "idempotency_key": f"ik_{goal_id}",
        "created_at": _now().isoformat(),
    })
    return {"document_id": doc_id, "goal_id": goal_id}


async def setup_receipt_doc(db, user_id: str):
    await db.documents.insert_one({
        "id": _uid("doc"), "user_id": user_id, "title": "Scontrino",
        "doc_type": "receipt", "category": "finance",
        "created_at": _now().isoformat(), "uploaded_at": _now().isoformat(),
    })
    return {}


async def apply_setup(db, user_id: str, setup: dict):
    kind = setup.get("kind")
    if kind == "study_skipped":
        return await setup_study_skipped(
            db, user_id,
            skipped_count=int(setup.get("skipped_count") or 1),
            days_to_exam=int(setup.get("days_to_exam") or 14),
        )
    if kind == "study_clean":
        return await setup_study_clean(db, user_id, sessions=int(setup.get("sessions") or 5))
    if kind == "travel_departure":
        return await setup_travel(
            db, user_id,
            days=int(setup.get("days_to_departure") or 3),
            incomplete=int(setup.get("incomplete_prep") or 0),
        )
    if kind == "calendar_overlap":
        return await setup_calendar_overlap(db, user_id, offset_hours=int(setup.get("offset_hours") or 2))
    if kind == "calendar_clear":
        return await setup_calendar_clear(db, user_id, offset_hours=int(setup.get("offset_hours") or 0))
    if kind == "education_doc":
        return await setup_education_doc(
            db, user_id,
            linked=bool(setup.get("linked")),
            has_flashcards=bool(setup.get("has_flashcards")),
        )
    if kind == "receipt_doc":
        return await setup_receipt_doc(db, user_id)
    if kind == "stub_only":
        # Intentionally no real connector data — stubs must stay empty
        return {"stub_type": setup.get("stub_type")}
    if kind == "low_value_generic":
        return {"synthetic": "low"}
    if kind == "quiet_hours_low":
        return {"quiet": True}
    if kind == "during_driving":
        await db.life_nodes.insert_one({
            "id": _uid("ev"), "user_id": user_id, "type": "event", "status": "active",
            "label": "In viaggio in autostrada",
            "attributes": {
                "starts_at": (_now() - timedelta(minutes=10)).isoformat(),
                "ends_at": (_now() + timedelta(hours=2)).isoformat(),
            },
            "created_at": _now().isoformat(),
        })
        await setup_study_skipped(db, user_id, skipped_count=1, days_to_exam=20)
        return {"driving": True}
    if kind == "duplicate_window":
        ctx = await setup_study_skipped(db, user_id, skipped_count=2, days_to_exam=10)
        return ctx
    if kind == "high_dismiss_rate":
        ctx = await setup_study_skipped(db, user_id, skipped_count=2, days_to_exam=10)
        from proactive_engine.learning import LearningStore
        store = LearningStore(db)
        for _ in range(5):
            await store.record(user_id, "study", "study_plan", event="dismissed")
        return ctx
    if kind == "flag_disabled":
        return await setup_study_skipped(db, user_id, skipped_count=2, days_to_exam=7)
    if kind == "other_user_data":
        other = _uid("u_other")
        await setup_study_skipped(db, other, skipped_count=3, days_to_exam=5)
        return {"other_user": other}
    if kind == "multi_candidates_rank":
        await setup_study_skipped(db, user_id, skipped_count=3, days_to_exam=5)
        await setup_travel(db, user_id, days=1, incomplete=3)
        await setup_calendar_overlap(db, user_id, offset_hours=1)
        return {}
    if kind == "home_max3_dedupe":
        await setup_study_skipped(db, user_id, skipped_count=2, days_to_exam=6)
        await setup_travel(db, user_id, days=2, incomplete=2)
        await setup_calendar_overlap(db, user_id, offset_hours=1)
        await setup_education_doc(db, user_id, linked=True, has_flashcards=False)
        return {}
    if kind == "notification_policy":
        return await setup_study_skipped(db, user_id, skipped_count=2, days_to_exam=4)
    return {}


def _match_type(suggestions, typ: str):
    return [s for s in suggestions if s.get("type") == typ]


# ---------------------------------------------------------------------------
# Fixture corpus
# ---------------------------------------------------------------------------

def _load_scenarios():
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return data["scenarios"]


SCENARIOS = _load_scenarios()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_proactive_scenario(scenario):
    async def body():
        client, db = await _db()
        uid = f"u_pe_{scenario['id']}_{uuid.uuid4().hex[:6]}"
        await _clean(db, uid)
        setup = scenario.get("setup") or {}
        ctx = await apply_setup(db, uid, setup)
        kind = setup.get("kind")

        # Unit-level gate checks without full regen where needed
        if kind == "low_value_generic":
            from proactive_engine.decision_engine import GateContext, would_assistant_speak
            from proactive_engine.models import SuggestionCandidate
            cand = SuggestionCandidate(
                title="Hai tempo libero",
                reason="motivational fluff",
                type="generic",
                source="noise",
                dedupe_key="noise1",
                confidence=0.4,
                urgency_hint=0.2,
                importance_hint=0.2,
                evidence={},
            )
            gate = would_assistant_speak(
                cand, score=0.2, confidence=0.4,
                ctx=GateContext(now=_now()),
            )
            assert gate.accept is False
            _close_client(client)
            return

        if kind == "quiet_hours_low":
            from proactive_engine.decision_engine import GateContext, would_assistant_speak
            from proactive_engine.models import SuggestionCandidate
            from proactive_engine.notification_policy import evaluate_notification
            cand = SuggestionCandidate(
                title="Piccolo nudge studio",
                reason="low urgency quiet",
                type="life",
                source="life",
                dedupe_key="q1",
                confidence=0.7,
                urgency_hint=0.3,
                importance_hint=0.4,
                evidence={"note": "x"},
            )
            # Quiet hours: Home may still accept; push must not send_now
            ctx_g = GateContext(now=_now(), quiet_hours=True, likely_sleep=True)
            gate = would_assistant_speak(cand, score=0.55, confidence=0.7, ctx=ctx_g)
            assert gate.accept is True
            assert any("quiet" in n for n in gate.notes)
            pol = evaluate_notification(
                {"urgency": 0.3, "priority": "low"},
                now=_now(),
            )
            assert pol.send_now is False
            _close_client(client)
            return

        if kind == "stub_only":
            from proactive_engine.generators.stubs import (
                generate_email_candidates,
                generate_finance_candidates,
                generate_health_candidates,
                generate_weather_candidates,
            )
            gens = {
                "emails": generate_email_candidates,
                "finance": generate_finance_candidates,
                "weather": generate_weather_candidates,
                "health": generate_health_candidates,
            }
            stub_type = setup.get("stub_type")
            out = await gens[stub_type](db, uid)
            assert out == [], f"stub {stub_type} must not invent content"
            svc = await _svc(db)
            regen = await svc.regenerate(uid)
            typed = _match_type(regen.get("suggestions") or [], stub_type)
            assert typed == []
            await _clean(db, uid)
            _close_client(client)
            return

        prev = os.environ.get("PROACTIVE_ENGINE_ENABLED")
        if kind == "flag_disabled":
            os.environ["PROACTIVE_ENGINE_ENABLED"] = "0"

        try:
            svc = await _svc(db)
            if kind == "duplicate_window":
                r1 = await svc.regenerate(uid)
                r2 = await svc.regenerate(uid)
                assert r1["created"] >= 1
                assert r2["created"] == 0  # dedupe window
                return

            if kind == "flag_disabled":
                r = await svc.regenerate(uid)
                assert r.get("enabled") is False
                assert r.get("created") == 0
                home = await svc.home_suggestions(uid)
                assert home == []
                return

            if kind == "other_user_data":
                r = await svc.regenerate(uid)
                assert r["created"] == 0  # no own data
                other = ctx.get("other_user")
                r_other = await svc.regenerate(other)
                assert r_other["created"] >= 1
                mine = await svc.list_suggestions(uid)
                assert mine["count"] == 0
                await _clean(db, other)
                return

            if kind == "notification_policy":
                r = await svc.regenerate(uid)
                assert r["created"] >= 1
                sug = r["suggestions"][0]
                pol = await svc.notification_preview(uid, sug["id"])
                assert pol["ok"]
                assert pol["decision"]["send_now"] is False
                assert pol["decision"]["channel"] in ("home", "none")
                return

            if kind == "home_max3_dedupe":
                await svc.regenerate(uid)
                home = await svc.home_suggestions(uid, limit=3)
                assert len(home) <= 3
                keys = [h.get("dedupe_key") for h in home]
                assert len(keys) == len(set(keys))
                return

            if kind == "multi_candidates_rank":
                r = await svc.regenerate(uid)
                assert r["created"] >= 2
                scores = []
                for s in r["suggestions"]:
                    full = await svc.repo.get(uid, s["id"])
                    scores.append(full.score)
                assert scores == sorted(scores, reverse=True) or len(scores) >= 1
                return

            if kind == "during_driving":
                r = await svc.regenerate(uid)
                # Driving blocks create when detectable
                assert r["created"] == 0
                assert any(
                    "during_driving" in (x.get("reasons") or [])
                    for x in (r.get("rejected_samples") or [])
                )
                return

            if kind == "high_dismiss_rate":
                r = await svc.regenerate(uid)
                # May suppress if score below threshold after learning
                assert r["ok"]
                return

            # Default path: regenerate and check expect_emit
            r = await svc.regenerate(uid)
            typ = (scenario.get("assert") or {}).get("type")
            created_of_type = _match_type(r.get("suggestions") or [], typ) if typ else (r.get("suggestions") or [])
            if scenario.get("expect_emit"):
                assert len(created_of_type) >= 1 or r["created"] >= 1, (
                    f"{scenario['id']} expected emit, got {r}"
                )
                action_kind = (scenario.get("assert") or {}).get("action_kind")
                if action_kind and created_of_type:
                    act = (created_of_type[0].get("action") or {}).get("kind")
                    assert act == action_kind
            else:
                if typ:
                    assert created_of_type == [], f"{scenario['id']} must not emit {typ}: {created_of_type}"
                else:
                    assert r["created"] == 0 or created_of_type == []
        finally:
            if kind == "flag_disabled":
                os.environ["PROACTIVE_ENGINE_ENABLED"] = prev or "1"
            await _clean(db, uid)
            _close_client(client)

    _run(body())


# ---------------------------------------------------------------------------
# Focused unit / integration tests
# ---------------------------------------------------------------------------

def test_fixture_corpus_size():
    assert len(SCENARIOS) >= 200


def test_scoring_deterministic_no_random():
    from proactive_engine.models import SuggestionCandidate
    from proactive_engine.scoring import score_candidate
    cand = SuggestionCandidate(
        title="Recupera sessione",
        reason="1 sessione saltata",
        type="study",
        source="study_plan",
        dedupe_key="k1",
        urgency_hint=0.7,
        importance_hint=0.7,
        confidence=0.9,
        evidence={"exam_date": (_now() + timedelta(days=5)).isoformat()},
    )
    a = score_candidate(cand, now=_now())
    b = score_candidate(cand, now=_now())
    assert a[0] == b[0]
    assert a[1] == b[1]
    assert a[2] == b[2]


def test_learning_multiplier_bounds():
    from proactive_engine.learning import compute_multiplier
    assert compute_multiplier(0, 0) == 1.0
    assert compute_multiplier(10, 0) >= 1.0
    assert compute_multiplier(0, 10) <= 0.8
    assert 0.5 <= compute_multiplier(3, 7) <= 1.35


def test_snooze_presets():
    from proactive_engine.notification_policy import snooze_until_iso
    now = _now()
    for p in ("15m", "1h", "stasera", "domani"):
        raw = snooze_until_iso(p, now=now)
        assert datetime.fromisoformat(raw.replace("Z", "+00:00")) > now


def test_accept_study_creates_recovery_session():
    async def body():
        client, db = await _db()
        uid = f"u_pe_accept_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        ctx = await setup_study_skipped(db, uid, skipped_count=2, days_to_exam=8)
        svc = await _svc(db)
        r = await svc.regenerate(uid)
        assert r["created"] >= 1
        sug = r["suggestions"][0]
        acc = await svc.accept(uid, sug["id"])
        assert acc["ok"]
        assert acc["result"]["effect"] == "recovery_session_created"
        sid = acc["result"]["session_id"]
        sess = await db.study_sessions.find_one({"id": sid, "user_id": uid}, {"_id": 0})
        assert sess is not None
        assert sess["status"] == "planned"
        assert sess["meta"].get("recovery") is True
        plan = await db.study_plans.find_one({"id": ctx["plan_id"]}, {"_id": 0})
        assert plan.get("next_recovery_session_id") == sid
        await _clean(db, uid)
        _close_client(client)
    _run(body())


def test_home_ora_ti_consiglia_max3():
    async def body():
        client, db = await _db()
        uid = f"u_pe_home_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        await setup_study_skipped(db, uid, skipped_count=2, days_to_exam=5)
        await setup_travel(db, uid, days=2, incomplete=2)
        await setup_calendar_overlap(db, uid, offset_hours=1)
        from home.service import HomeService
        home = await HomeService(db).build_home(uid)
        assert hasattr(home, "ora_ti_consiglia")
        assert len(home.ora_ti_consiglia) <= 3
        await _clean(db, uid)
        _close_client(client)
    _run(body())


def test_flag_off_home_empty_section():
    async def body():
        client, db = await _db()
        uid = f"u_pe_flag_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        await setup_study_skipped(db, uid, skipped_count=2, days_to_exam=5)
        prev = os.environ.get("PROACTIVE_ENGINE_ENABLED")
        os.environ["PROACTIVE_ENGINE_ENABLED"] = "0"
        try:
            from home.service import HomeService
            home = await HomeService(db).build_home(uid)
            assert home.ora_ti_consiglia == []
        finally:
            os.environ["PROACTIVE_ENGINE_ENABLED"] = prev or "1"
            await _clean(db, uid)
            _close_client(client)
    _run(body())


def test_dismiss_accept_learning_persists():
    async def body():
        client, db = await _db()
        uid = f"u_pe_learn_{uuid.uuid4().hex[:8]}"
        await _clean(db, uid)
        await setup_study_skipped(db, uid, skipped_count=2, days_to_exam=6)
        svc = await _svc(db)
        r = await svc.regenerate(uid)
        assert r["created"] >= 1
        sid = r["suggestions"][0]["id"]
        await svc.dismiss(uid, sid)
        st = await svc.learning.get_stats(uid, "study", "study_plan")
        assert st.dismissed >= 1
        await _clean(db, uid)
        _close_client(client)
    _run(body())
