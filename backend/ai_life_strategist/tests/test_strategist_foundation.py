"""AI Life Strategist + Life Setup foundation tests."""
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
os.environ.setdefault("JWT_SECRET", "test-secret-life-setup")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ora_life_setup_test")
os.environ.setdefault("GOAL_ENGINE_ENABLED", "1")

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

MONGO = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
DBNAME = os.environ.get("DB_NAME", "ora_life_setup_test")


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


def uid(prefix: str = "case") -> str:
    return f"ls_test_{prefix}_{uuid.uuid4().hex[:8]}"


def _svc(db):
    from life_setup.service import LifeSetupService
    from ai_life_strategist import cache as c

    c.clear()
    import life_setup.service as ls

    ls._SERVICE = LifeSetupService(db)
    return ls._SERVICE


# ---------------------------------------------------------------------------
# Unit: planner / gaps / benefits / privacy
# ---------------------------------------------------------------------------

def test_domains_complete():
    from ai_life_strategist.models import DOMAINS

    assert len(DOMAINS) == 14
    assert "casa" in DOMAINS and "assicurazioni" in DOMAINS


def test_casa_purchase_prefers_rogito():
    """Domain document preference remains available via legacy helper; MLC gates wrap."""
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_domain_gap_legacy, plan_next
    from ai_life_strategist.knowledge_gap import infer_known_from_text

    facts = infer_known_from_text("Ho comprato casa.")
    assert facts.get("casa.purchased") is True
    ctx = ReasoningContext(
        user_id="u1",
        known_facts=facts,
        last_user_text="Ho comprato casa.",
        session_phase="active",
        domains_touched=["casa"],
    )
    # First-launch planner targets MLC gaps (not a document wizard)
    mlc_plan = plan_next(ctx, focus_domain="casa")
    assert (mlc_plan.meta or {}).get("phase") != "wrap"
    assert str((mlc_plan.meta or {}).get("gap_key") or "").startswith("mlc.")
    # Progressive domain preference still available
    plan = plan_domain_gap_legacy(ctx, focus_domain="casa")
    assert plan is not None
    assert plan.domain == "casa"
    assert plan.prefer_document is True
    assert plan.recommended_document is not None
    assert plan.recommended_document.doc_type == "rogito"
    assert plan.expected_benefit
    assert plan.question_reason


def test_no_duplicate_question():
    from ai_life_strategist.models import StrategistPlan
    from ai_life_strategist.question_planner import avoid_duplicate

    plan = StrategistPlan(
        next_best_question="Domanda X?",
        question_reason="r",
        expected_benefit="b",
        domain="casa",
        alternative_question="Domanda Y?",
    )
    out = avoid_duplicate(plan, ["Domanda X?"])
    assert out.next_best_question == "Domanda Y?"


def test_benefit_explainable():
    from ai_life_strategist.benefit_engine import explain_benefit, pick_best_benefit_for_gap

    b = pick_best_benefit_for_gap("casa.mutuo", "casa")
    assert "mutuo" in b.user_benefit.lower() or "rata" in b.user_benefit.lower()
    assert explain_benefit(b.code)


def test_privacy_refusal_in_plan():
    from ai_life_strategist.policy import filter_unsafe_plan_fields, detect_privacy_sensitive_request

    assert detect_privacy_sensitive_request("Qual è la password del home banking?")
    q, r, b, refused = filter_unsafe_plan_fields(
        "Dammi il PIN della carta",
        "serve",
        "beneficio",
    )
    assert refused is True
    assert "pin" not in q.lower() or "non" in r.lower()


def test_gemini_absent_fallback():
    from ai_life_strategist.service import AILifeStrategistService

    svc = AILifeStrategistService()

    async def _go():
        plan = await svc.next_question(
            "u_fb",
            last_user_text="Ho un'auto e serve la revisione",
            session_phase="active",
            force_fallback=True,
            use_cache=False,
        )
        assert plan.source in ("deterministic_fallback", "cache")
        assert plan.next_best_question
        assert plan.expected_benefit
        return plan

    plan = _run(_go())
    assert plan.domain in ("auto", "casa", "servizi", "assicurazioni")


def test_strategist_structured_fields():
    from ai_life_strategist.service import AILifeStrategistService

    svc = AILifeStrategistService()

    async def _go():
        plan = await svc.next_question(
            "u_struct",
            last_user_text="Devo pagare le bollette della casa",
            force_fallback=True,
            use_cache=False,
        )
        d = plan.public()
        for k in (
            "next_best_question",
            "question_reason",
            "expected_benefit",
            "information_gain",
            "recommended_document",
            "alternative_question",
            "confidence",
            "domain",
            "priority",
        ):
            assert k in d

    _run(_go())


def test_stubs_not_operational():
    from life_setup.adapters_stubs import STUBS

    async def _go():
        for name, stub in STUBS.items():
            r = await stub.fetch()
            assert r.get("stub") is True
            assert r.get("ok") is False

    _run(_go())


# ---------------------------------------------------------------------------
# Scenarios via LifeSetupService
# ---------------------------------------------------------------------------

def test_scenario_casa_mutuo_bollette():
    user = uid("casa")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            st = await svc.start(user)
            assert st["ok"] and st.get("wizard") is False
            assert st["turn"]["ui"]["wizard"] is False

            ans = await svc.answer(user, "Ho comprato casa.")
            assert ans["ok"]
            turn = ans["turn"]
            plan = turn.get("plan") or {}
            text = (turn.get("text") or turn.get("question") or "").lower()
            # MLC-first: after house purchase, ask next nucleus — documents optional
            assert str((plan.get("meta") or {}).get("gap_key") or "").startswith("mlc.")
            assert plan.get("prefer_document") is not True
            assert any(
                w in text
                for w in ("chiami", "lavoro", "studio", "vivi", "aiut", "impegni", "prior")
            )

            # Optional document still works (not required for MLC)
            up = await svc.upload_doc(
                user,
                {
                    "doc_type": "rogito",
                    "synthetic_text": "ROGITO Via Milano 1 compravendita 2026",
                    "filename": "rogito.txt",
                },
            )
            assert up["ok"]
            profile = up.get("profile") or {}
            assert "casa" in (profile.get("domains") or {})

            # Reach MLC via conversation, then complete through Sprint 2B API
            for msg in (
                "Mi chiamo Luca",
                "Vivo a Milano",
                "Lavoro come architetto",
                "La priorità è gestire le scadenze di casa",
            ):
                step = await svc.answer(user, msg)
                assert step["ok"]

            # May already be done mid-way; complete must still succeed
            done = await svc.complete(user)
            assert done.get("ok") is not False
            assert done["should_show"] is False
            assert done["module_visible"] is False
            st2 = await svc.status(user)
            assert st2["should_show"] is False
        finally:
            client.close()

    _run(_go())


def test_scenario_auto():
    user = uid("auto")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            ans = await svc.answer(user, "Ho una macchina nuova.")
            assert "auto" in ans["session"]["domains_touched"] or (ans["turn"].get("plan") or {}).get("domain") == "auto"
            assert (ans["turn"] or {}).get("expected_benefit")
        finally:
            client.close()

    _run(_go())


def test_scenario_studio_universita():
    user = uid("studio")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            ans = await svc.answer(user, "Studio all'università e ho un esame.")
            assert "studio" in ans["session"]["domains_touched"]
            assert ans["turn"]["expected_benefit"]
        finally:
            client.close()

    _run(_go())


def test_scenario_salute_assicurazioni_famiglia():
    user = uid("saf")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            for text, dom in [
                ("Ho una visita medica la prossima settimana.", "salute"),
                ("Devo rinnovare l'assicurazione.", "assicurazioni"),
                ("Vivo con la mia famiglia.", "famiglia"),
            ]:
                ans = await svc.answer(user, text)
                assert ans["ok"]
                assert ans.get("wizard") is False
                assert dom in ans["session"]["domains_touched"] or (ans["turn"].get("plan") or {}).get("domain")
        finally:
            client.close()

    _run(_go())


def test_interrupt_hides_wizard():
    user = uid("interrupt")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            cancel = await svc.cancel(user)
            assert cancel["should_show"] is False
            assert cancel["module_visible"] is False
            assert cancel["wizard"] is False
            sug = cancel.get("resume_suggestion") or {}
            title = (sug.get("title") or "").lower()
            assert "completa il profilo" not in title
            assert "life setup" not in title
            assert "aiutarti ancora" in title or "ora" in title
            st = await svc.status(user)
            assert st["should_show"] is False
        finally:
            client.close()

    _run(_go())


def test_skip_postpone():
    user = uid("skip")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            sk = await svc.skip(user, postpone_all=True)
            assert sk["should_show"] is False
            assert sk["module_visible"] is False
        finally:
            client.close()

    _run(_go())


def test_explain_benefit_endpoint_shape():
    user = uid("explain")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            await svc.answer(user, "Ho comprato casa.")
            ex = await svc.explain(user)
            assert ex["ok"]
            assert ex["explain"]["expected_benefit"]
            assert ex["explain"]["user_explanation"]
        finally:
            client.close()

    _run(_go())


def test_privacy_credential_not_stored():
    user = uid("priv")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            ans = await svc.answer(user, "password: SuperSecret123 PIN=9999")
            assert ans.get("privacy_refusal") is True
            sess = ans["session"]
            assert "SuperSecret123" not in str(sess.get("known_facts"))
        finally:
            client.close()

    _run(_go())


def test_user_isolation():
    a, b = uid("iso_a"), uid("iso_b")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, a)
            await _clean(db, b)
            svc = _svc(db)
            await svc.start(a)
            await svc.answer(a, "Ho comprato casa.")
            await svc.start(b)
            pa = await svc.profiles.get(a)
            pb = await svc.profiles.get(b)
            assert pa and "casa" in pa.domains
            assert not pb or "casa" not in pb.domains or not pb.domains["casa"].objects.get("casa.purchased")
        finally:
            client.close()

    _run(_go())


def test_profile_user_correct_delete():
    from life_setup.profile_service import LifeProfileService

    user = uid("prof")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            ps = LifeProfileService(db)
            await ps.apply_facts(user, {"casa.owned": True}, domain_hint="casa")
            p = await ps.correct_fact(user, "casa", "casa.owned", False)
            assert p.domains["casa"].objects["casa.owned"].confirmed is True
            p2 = await ps.delete_fact(user, "casa", "casa.owned")
            assert "casa.owned" not in p2.domains["casa"].objects
        finally:
            client.close()

    _run(_go())


def test_confirmed_not_overwritten_by_inferred():
    from life_setup.profile_service import LifeProfileService

    user = uid("conf")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            ps = LifeProfileService(db)
            await ps.upsert_fact(
                user,
                domain="casa",
                key="casa.mutuo",
                value="ok",
                source="user_confirmed",
                confirmed=True,
                confidence=0.95,
            )
            await ps.upsert_fact(
                user,
                domain="casa",
                key="casa.mutuo",
                value="unknown",
                source="inferred",
                confidence=0.4,
            )
            p = await ps.get(user)
            assert p.domains["casa"].objects["casa.mutuo"].value == "ok"
        finally:
            client.close()

    _run(_go())
