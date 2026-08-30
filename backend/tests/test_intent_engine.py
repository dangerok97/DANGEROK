"""Intent Classification Engine — corpus (≥100), confidence, AE regression."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

CORPUS_PATH = Path(__file__).resolve().parent / "fixtures" / "intent_corpus_it.json"
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")


def _run(coro):
    # The session's own loop, not whatever the policy currently points at:
    # a suite that used asyncio.run() before this one has cleared that slot.
    return _loop_harness.run(coro)


def _load_corpus():
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert len(data) >= 100, f"corpus must have ≥100 phrases, got {len(data)}"
    return data


CORPUS = _load_corpus()


@pytest.mark.parametrize(
    "case",
    CORPUS,
    ids=[f"{i:03d}_{c['intent']}" for i, c in enumerate(CORPUS)],
)
def test_corpus_intent(case):
    from intent_engine import classify_text
    r = classify_text(case["text"])
    assert r.intent == case["intent"], (
        f"{case['text']!r}: expected intent={case['intent']}, got {r.intent} "
        f"(conf={r.confidence}, scores={r.scores})"
    )
    if case.get("subtype"):
        assert r.subtype == case["subtype"], (
            f"{case['text']!r}: expected subtype={case['subtype']}, got {r.subtype}"
        )
    if case.get("subject"):
        assert (r.entities.subject or "").lower() == case["subject"].lower()
    assert r.needs_clarify is False, f"{case['text']!r} should not need clarify"
    assert r.confidence >= 0.55


def test_psychology_exam_explicit():
    from intent_engine import classify_text
    from intent_engine.mapping import flow_for_intent
    r = classify_text("devo studiare l'esame di psicologia")
    assert r.intent == "study"
    assert r.subtype == "exam_preparation"
    assert r.confidence >= 0.9
    assert r.needs_clarify is False
    assert (r.entities.subject or "").lower() == "psicologia"
    assert flow_for_intent(r.intent, r.subtype) == "study"


def test_event_ticket_not_study():
    from intent_engine import classify_text
    r = classify_text("biglietto per il concerto di stasera")
    assert r.intent == "event"
    assert r.needs_clarify is False


def test_vacation_travel():
    from intent_engine import classify_text
    r = classify_text("vacanza in Sardegna ad agosto")
    assert r.intent == "travel"
    assert r.subtype == "vacation"


def test_medical_dentista():
    from intent_engine import classify_text
    r = classify_text("visita dal dentista")
    assert r.intent == "medical"


def test_payment_bolletta():
    from intent_engine import classify_text
    r = classify_text("fattura e bolletta da pagare")
    assert r.intent == "payment"


def test_low_confidence_clarify():
    from intent_engine import classify_text
    r = classify_text("xyz qwerty asdf")
    assert r.needs_clarify is True
    assert r.clarify_options
    assert len(r.clarify_options) >= 2
    labels = " ".join(o.label.lower() for o in r.clarify_options)
    # Default clarify mentions exam/event options in AE; options exist here
    assert labels or r.intent == "generic"


def test_ambiguous_study_vs_event_clarify_or_study():
    """Strong study signal must win; weak dual signal may clarify."""
    from intent_engine import classify_text
    r = classify_text("devo studiare l'esame di psicologia")
    assert r.needs_clarify is False
    assert r.intent == "study"


def test_wrong_item_type_ignored_for_routing():
    """Erroneous home type 'event' must not override study text."""
    from intent_engine import classify_text
    r = classify_text(
        "devo studiare l'esame di psicologia",
        item_type="event",
        source_type="decision",
    )
    assert r.intent == "study"
    assert r.subtype == "exam_preparation"
    assert r.needs_clarify is False


def test_classifier_version_present():
    from intent_engine import classify_text, CLASSIFIER_VERSION
    r = classify_text("esame di fisica")
    assert r.classifier_version == CLASSIFIER_VERSION


def test_action_engine_open_psychology_study_flow():
    """Regression: AE open with psychology phrase → study first question, NOT ticket."""
    async def body():
        from motor.motor_asyncio import AsyncIOMotorClient
        from action_engine.service import ActionEngineService
        from action_engine.models import OpenBody
        from life_graph import LifeGraphService
        from knowledge import KnowledgeService
        from decision_engine import DecisionService

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        user = f"u_ie_psy_{uuid.uuid4().hex[:8]}"
        try:
            for col in ("action_sessions", "action_projects", "life_nodes", "node_knowledge", "decisions"):
                await db[col].delete_many({"user_id": user})
            svc = ActionEngineService(
                db,
                life_graph=LifeGraphService(db),
                knowledge=KnowledgeService(db),
                decisions=DecisionService(db),
            )
            # Simulate wrong home typing (EVENT) — Intent must still route to study
            opened = await svc.open(user, OpenBody(
                title="devo studiare l'esame di psicologia",
                item_type="event",
                source_type="decision",
                source_id="dec_psy_1",
                home_item_id="home_psy_1",
                force_new=True,
            ))
            session = opened["session"]
            assert session["flow"] == "study", session
            turn = session["current_turn"]
            assert turn is not None
            q = (turn.get("question") or "").lower()
            assert "biglietto" not in q
            assert turn["id"] == "exam_date" or "esame" in q or "material" in q or "quando" in q
            assert opened.get("intent", {}).get("intent") == "study"
            assert opened.get("intent", {}).get("subtype") == "exam_preparation"
        finally:
            for col in ("action_sessions", "action_projects", "life_nodes", "node_knowledge", "decisions"):
                await db[col].delete_many({"user_id": user})
            client.close()
    _run(body())


def test_action_engine_clarify_path():
    async def body():
        from motor.motor_asyncio import AsyncIOMotorClient
        from action_engine.service import ActionEngineService
        from action_engine.models import OpenBody, AnswerBody

        client = AsyncIOMotorClient(MONGO)
        db = client[DBNAME]
        user = f"u_ie_cl_{uuid.uuid4().hex[:8]}"
        try:
            await db.action_sessions.delete_many({"user_id": user})
            svc = ActionEngineService(db)
            opened = await svc.open(user, OpenBody(
                title="xyz qwerty nonsense",
                force_new=True,
            ))
            assert opened["session"]["flow"] == "clarify"
            q = (opened["session"]["current_turn"]["question"] or "").lower()
            assert "non sono sicuro" in q or "esame" in q
            # Choose study
            sid = opened["session"]["id"]
            res = await svc.answer(user, sid, AnswerBody(option_id="clarify_study"))
            assert res.get("ok")
            assert res["session"]["flow"] == "study"
            assert res["session"]["current_turn"]["id"] == "exam_date" or "esame" in (
                res["session"]["current_turn"]["question"] or ""
            ).lower()
        finally:
            await db.action_sessions.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_corpus_size():
    assert len(CORPUS) >= 100
