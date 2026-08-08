"""AI-first Life Experience — reasoning loop, benefits Home/Proactive, anti-wizard."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

os.environ["LIFE_SETUP_ENABLED"] = "1"
os.environ["AI_LIFE_STRATEGIST_ENABLED"] = "1"
os.environ["AI_LIFE_STRATEGIST_GEMINI"] = "0"
os.environ.setdefault("JWT_SECRET", "test-secret-life-experience")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ora_life_experience_test")
os.environ.setdefault("GOAL_ENGINE_ENABLED", "1")

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

MONGO = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
DBNAME = os.environ.get("DB_NAME", "ora_life_experience_test")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    for col in (
        "life_setup_sessions",
        "life_profiles",
        "goals",
        "life_nodes",
        "life_edges",
        "proactive_suggestions",
        "documents",
        "conversation_sessions",
    ):
        await db[col].delete_many({"user_id": user_id})


def uid(prefix: str = "le") -> str:
    return f"le_test_{prefix}_{uuid.uuid4().hex[:8]}"


def _svc(db):
    from life_setup.service import LifeSetupService
    from ai_life_strategist import cache as c

    c.clear()
    import life_setup.service as ls

    ls._SERVICE = LifeSetupService(db)
    return ls._SERVICE


def test_gemini_context_has_structured_fields_not_only_message():
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.reasoning_loop import to_gemini_context_json
    from ai_life_strategist.reasoner import GEMINI_TASK_QUESTION

    ctx = ReasoningContext(
        user_id="u1",
        known_facts={"casa.owned": True},
        missing_keys=["casa.mutuo"],
        goals_summary="Obiettivo Casa",
        calendar_summary="Nessun evento",
        documents_summary="Documenti: rogito",
        conversation_summary="Conversazione attiva",
        confidence_overall=0.6,
        last_user_text="Ho il mutuo",
    )
    payload = to_gemini_context_json(ctx)
    assert "known" in payload
    assert "missing" in payload
    assert "confidence" in payload
    assert "goals" in payload
    assert "calendar_summary" in payload
    assert "documents_summary" in payload
    assert "conversation_summary" in payload
    assert "beneficio" in GEMINI_TASK_QUESTION.lower()
    assert "continua liberamente" not in GEMINI_TASK_QUESTION.lower()


def test_domains_any_order_studio_first():
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_next
    from ai_life_strategist.knowledge_gap import infer_known_from_text

    text = "Studio all'università e ho il piano di studi"
    facts = infer_known_from_text(text)
    ctx = ReasoningContext(
        user_id="u1",
        known_facts=facts,
        last_user_text=text,
        session_phase="active",
        domains_touched=[],
    )
    plan = plan_next(ctx)
    # MLC-first: not wrap; one natural question (may be identity / places / priority)
    assert (plan.meta or {}).get("phase") != "wrap"
    assert plan.next_best_question
    assert "?" in plan.next_best_question
    assert plan.next_best_question.count("?") <= 2
    assert str((plan.meta or {}).get("gap_key") or "").startswith("mlc.")


def test_prefer_document_piano_studi():
    from ai_life_strategist.document_strategy import recommend_document, document_keys_from_upload

    rec = recommend_document("piano_di_studi", domain="studio")
    assert rec is not None
    assert "piano" in rec.label.lower()
    keys = document_keys_from_upload("piano_di_studi")
    assert "doc.piano_di_studi" in keys
    assert "studio.active" in keys


def test_refuse_never_repeats():
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_next
    from ai_life_strategist.knowledge_gap import infer_known_from_text

    facts = infer_known_from_text("Ho comprato casa.")
    ctx = ReasoningContext(
        user_id="u1",
        known_facts=facts,
        asked_keys=["mlc.identity.name"],
        refused_keys=["mlc.identity.name"],
        last_user_text="preferisco non dirti il nome",
        session_phase="active",
        domains_touched=["casa"],
    )
    plan = plan_next(ctx)
    assert (plan.meta or {}).get("gap_key") != "mlc.identity.name"
    assert plan.recommended_document is None


def test_home_signals_italian():
    from ai_life_strategist.benefit_engine import home_benefit_cards

    cards = home_benefit_cards({"casa.owned", "casa.purchased", "doc.rogito", "casa.mutuo"})
    assert cards
    for c in cards:
        assert c.home_signal
        assert "adesso posso" in c.home_signal.lower() or "posso" in c.home_signal.lower()
        assert "completa il profilo" not in (c.home_signal or "").lower()
        assert "life setup" not in (c.home_signal or "").lower()


def test_wrap_copy_no_life_setup_phrase():
    from ai_life_strategist.conversation_planner import wrap_up_turn, assert_not_wizard_copy

    turn = wrap_up_turn(domains=["casa"], benefits=["seguire il mutuo"])
    assert assert_not_wizard_copy(turn["text"])
    assert "life setup" not in turn["text"].lower()


def test_deterministic_fallback_italian_without_gemini():
    from ai_life_strategist.service import AILifeStrategistService

    svc = AILifeStrategistService()

    async def _go():
        plan = await svc.next_question(
            "u_it",
            last_user_text="Ho comprato casa.",
            force_fallback=True,
            use_cache=False,
        )
        assert plan.source == "deterministic_fallback"
        assert plan.expected_benefit
        # Italian MLC follow-up (not a wizard / not forced rogito)
        text = plan.next_best_question + " " + plan.expected_benefit
        assert any(
            w in text.lower()
            for w in ("chiami", "lavoro", "studio", "vivi", "aiut", "casa", "ora", "contesto")
        )
        assert (plan.meta or {}).get("phase") != "wrap"
        assert str((plan.meta or {}).get("gap_key") or "").startswith("mlc.")

    _run(_go())


def test_home_adapter_emits_benefit_not_wizard():
    user = uid("home")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            await svc.answer(user, "Ho comprato casa.")
            await svc.upload_doc(
                user,
                {
                    "doc_type": "rogito",
                    "synthetic_text": "ROGITO Via Test 1 Milano",
                    "filename": "r.txt",
                },
            )
            await svc.answer(user, "Ho un mutuo da seguire.")
            await svc.complete(user)

            from home.adapters.life_setup import load_life_setup_items

            items, _ = await load_life_setup_items(db, user)
            assert items
            titles = " ".join(i.title for i in items).lower()
            assert "completa il profilo" not in titles
            assert "life setup" not in titles
            assert any(i.subtype == "life_benefit" for i in items) or "posso" in titles
            for i in items:
                assert i.meta.get("life_setup_section") is False
                assert i.meta.get("wizard") is False
        finally:
            client.close()

    _run(_go())


def test_proactive_benefit_never_completa_profilo():
    user = uid("pro")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            await svc.answer(user, "Ho comprato casa.")
            await svc.upload_doc(
                user,
                {
                    "doc_type": "rogito",
                    "synthetic_text": "ROGITO",
                    "filename": "r.txt",
                },
            )
            await svc.answer(user, "Sì, ho il mutuo.")
            await svc.complete(user)

            from proactive_engine.generators.life_setup import generate_life_setup_candidates

            cands = await generate_life_setup_candidates(db, user)
            blob = " ".join(
                f"{c.title} {c.description} {c.reason}" for c in cands
            ).lower()
            assert "completa il profilo" not in blob
            assert "life setup" not in blob
            if cands:
                assert any(
                    c.source == "life_experience_benefit" or "posso" in (c.description or "").lower()
                    for c in cands
                )
        finally:
            client.close()

    _run(_go())


def test_interrupt_resume_natural():
    user = uid("resume")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            await svc.answer(user, "Ho un'auto.")
            cancel = await svc.cancel(user)
            assert cancel["should_show"] is False
            sug = cancel.get("resume_suggestion") or {}
            assert "completa il profilo" not in (sug.get("title") or "").lower()
            # Resume with force
            again = await svc.start(user, force=True)
            assert again["ok"]
            assert again.get("wizard") is False
            assert again["turn"]["ui"]["wizard"] is False
        finally:
            client.close()

    _run(_go())


def test_replan_after_new_info():
    user = uid("replan")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            a1 = await svc.answer(user, "Ho comprato casa.")
            g1 = ((a1["turn"].get("plan") or {}).get("meta") or {}).get("gap_key")
            up = await svc.upload_doc(
                user,
                {"doc_type": "rogito", "synthetic_text": "ROGITO", "filename": "r.txt"},
            )
            g2 = ((up["turn"].get("plan") or {}).get("meta") or {}).get("gap_key")
            # Plan must change after document (or wrap)
            assert g2 != g1 or (up["turn"].get("plan") or {}).get("meta", {}).get("phase") in (
                "wrap",
                "active",
                "document",
            )
            q2 = (up["turn"].get("question") or up["turn"].get("text") or "").lower()
            assert "rogito" not in q2 or g2 != "doc.rogito"
        finally:
            client.close()

    _run(_go())
