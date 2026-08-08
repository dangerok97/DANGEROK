"""Minimum Life Context V1 — semantic coverage (not a 5-question wizard)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["LIFE_SETUP_ENABLED"] = "1"
os.environ["AI_LIFE_STRATEGIST_ENABLED"] = "1"
os.environ["AI_LIFE_STRATEGIST_GEMINI"] = "0"
os.environ.setdefault("JWT_SECRET", "test-secret-mlc")

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def test_scenario_a_multi_nucleus_no_reask():
    from ai_life_strategist.knowledge_gap import infer_known_from_text
    from ai_life_strategist.minimum_life_context import evaluate_mlc_coverage
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_next

    text = "Mi chiamo Luca, vivo a Milano e lavoro come architetto."
    facts = infer_known_from_text(text)
    assert facts.get("mlc.identity.name", "").lower() == "luca"
    assert "milano" in str(facts.get("mlc.life_places.home", "")).lower()
    assert facts.get("mlc.current_situation") == "lavoro"
    assert facts.get("lavoro.ruolo")

    from ai_life_strategist.minimum_life_context import is_mlc_sufficient

    cov = evaluate_mlc_coverage(facts)
    assert cov.public()["nuclei"]["identity"]["status"] == "covered"
    assert cov.public()["nuclei"]["life_places"]["status"] == "covered"
    assert cov.public()["nuclei"]["current_situation"]["status"] == "covered"
    assert cov.public()["nuclei"]["responsibilities"]["status"] == "covered"
    # mlc-v1: rich core → priority implicit (addressed), not missing
    assert cov.public()["nuclei"]["immediate_priority"]["status"] == "implicit"
    assert cov.public()["nuclei"]["immediate_priority"]["addressed"] is True
    assert is_mlc_sufficient(facts)

    plan = plan_next(
        ReasoningContext(
            user_id="u_a",
            known_facts=facts,
            last_user_text=text,
            session_phase="active",
        )
    )
    q = (plan.next_best_question or "").lower()
    assert "luca" not in q
    assert "milano" not in q
    assert "come ti chiami" not in q
    assert "dove vivi" not in q
    # Still prefer one priority ask before wrap
    assert (plan.meta or {}).get("phase") != "wrap"
    assert (plan.meta or {}).get("gap_key") == "mlc.immediate_priority"
    # asked alone does not address — after ask, wrap without perfect priority phrasing
    plan2 = plan_next(
        ReasoningContext(
            user_id="u_a",
            known_facts=facts,
            asked_keys=["mlc.immediate_priority"],
            session_phase="active",
        )
    )
    assert (plan2.meta or {}).get("phase") == "wrap"


def test_scenario_b_studio_followup():
    from ai_life_strategist.knowledge_gap import infer_known_from_text
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_next

    facts = infer_known_from_text("Studio.")
    assert facts.get("studio.active") is True
    plan = plan_next(
        ReasoningContext(
            user_id="u_b",
            known_facts=facts,
            last_user_text="Studio.",
            session_phase="active",
        )
    )
    q = plan.next_best_question or ""
    assert "?" in q
    assert (plan.meta or {}).get("phase") != "wrap"
    # Natural deepen or other MLC gap — not a checklist UI
    assert "1/5" not in q and "step" not in q.lower()


def test_scenario_c_multi_cover():
    from ai_life_strategist.knowledge_gap import infer_known_from_text
    from ai_life_strategist.minimum_life_context import evaluate_mlc_coverage

    text = (
        "Lavoro e studio e in questo periodo la cosa più importante per me "
        "è preparare gli esami."
    )
    facts = infer_known_from_text(text)
    assert facts.get("mlc.current_situation") == "lavoro_studio"
    assert "esame" in str(facts.get("mlc.immediate_priority", "")).lower() or facts.get(
        "studio.esame"
    )
    cov = evaluate_mlc_coverage(facts)
    assert cov.public()["nuclei"]["current_situation"]["status"] == "covered"
    assert cov.public()["nuclei"]["immediate_priority"]["status"] == "covered"
    assert cov.public()["nuclei"]["responsibilities"]["status"] == "covered"


def test_scenario_d_skip_does_not_block():
    from ai_life_strategist.minimum_life_context import evaluate_mlc_coverage, is_mlc_sufficient
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_next

    facts = {
        "mlc.identity.name": "Luca",
        "mlc.current_situation": "lavoro",
        "mlc.life_places.home": "Milano",
        "mlc.responsibilities": "architetto",
        "lavoro.ruolo": "architetto",
    }
    # Rich core → sufficient via implicit priority (mlc-v1 heuristic)
    assert is_mlc_sufficient(facts)
    assert is_mlc_sufficient(facts, refused_keys={"mlc.immediate_priority"})
    facts2 = {**facts, "mlc.immediate_priority": "scadenze lavoro"}
    assert is_mlc_sufficient(facts2)
    # asked_keys alone do NOT address a nucleus / do not change sufficiency semantics
    cov_asked = evaluate_mlc_coverage(facts)
    assert cov_asked.public()["nuclei"]["immediate_priority"]["status"] != "covered"

    # Skip one optional-ish nucleus: refuse places but places already covered — use skip on
    # a missing nucleus while others solid
    facts3 = {
        "mlc.identity.name": "Ada",
        "mlc.current_situation": "studio",
        "mlc.responsibilities": "ingegneria",
        "mlc.immediate_priority": "esami",
        "studio.active": True,
    }
    # places missing → not ready
    assert not is_mlc_sufficient(facts3)
    # skip places → still need covered_count>=3 and priority covered → ready
    assert is_mlc_sufficient(facts3, refused_keys={"mlc.life_places.home"})

    plan = plan_next(
        ReasoningContext(
            user_id="u_d",
            known_facts=facts3,
            refused_keys=["mlc.life_places.home"],
            session_phase="active",
        )
    )
    assert (plan.meta or {}).get("phase") == "wrap"


def test_scenario_e_persistence_resume_from_facts():
    """Coverage is derived from known_facts (backend), not React state."""
    from ai_life_strategist.minimum_life_context import evaluate_mlc_coverage
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_next

    persisted = {
        "mlc.identity.name": "Luca",
        "mlc.life_places.home": "Milano",
        "mlc.current_situation": "lavoro",
        "lavoro.ruolo": "architetto",
        "mlc.responsibilities": "architetto",
    }
    cov = evaluate_mlc_coverage(persisted)
    assert cov.public()["nuclei"]["immediate_priority"]["status"] == "implicit"
    plan = plan_next(
        ReasoningContext(user_id="u_e", known_facts=persisted, session_phase="active")
    )
    assert (plan.meta or {}).get("gap_key") == "mlc.immediate_priority"
    assert "luca" not in (plan.next_best_question or "").lower()


def test_asked_keys_do_not_address_nucleus():
    from ai_life_strategist.minimum_life_context import compute_mlc_gaps, evaluate_mlc_coverage

    facts = {"studio.active": True, "mlc.current_situation": "studio"}
    cov = evaluate_mlc_coverage(facts)
    assert cov.public()["nuclei"]["identity"]["status"] == "missing"
    assert cov.public()["nuclei"]["identity"]["addressed"] is False
    # Even if identity was asked, it stays missing/unaddressed
    gaps = compute_mlc_gaps(facts, asked_keys={"mlc.identity.name"})
    assert any(g.key == "mlc.identity.name" for g in gaps)


def test_scenario_f_mlc_done():
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_next
    from ai_life_strategist.conversation_planner import wrap_up_turn
    from ai_life_strategist.service import AILifeStrategistService
    import asyncio

    facts = {
        "mlc.identity.name": "Luca",
        "mlc.current_situation": "lavoro",
        "mlc.life_places.home": "Milano",
        "mlc.responsibilities": "architetto",
        "mlc.immediate_priority": "organizzare scadenze",
        "lavoro.ruolo": "architetto",
    }
    plan = plan_next(
        ReasoningContext(user_id="u_f", known_facts=facts, session_phase="active")
    )
    assert (plan.meta or {}).get("phase") == "wrap"
    assert (plan.meta or {}).get("completion_reason") == "minimum_life_context"

    async def _turn():
        svc = AILifeStrategistService()
        return await svc.plan_turn(
            "u_f",
            known_facts=facts,
            session_phase="active",
            force_fallback=True,
            use_cache=False,
        )

    turn = asyncio.get_event_loop().run_until_complete(_turn())
    assert turn.get("ui", {}).get("done") is True
    assert "abbastanza" in (turn.get("text") or "").lower() or "iniziare" in (
        turn.get("text") or ""
    ).lower()


def test_not_wrap_on_empty_domain_gaps_alone():
    """Old behavior wrapped when DOMAIN_GAPS empty via skips — MLC must still gate."""
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_next

    # Almost no facts — must NOT wrap even if we pretend domains skipped
    plan = plan_next(
        ReasoningContext(
            user_id="u_empty",
            known_facts={},
            postponed_keys=[
                "casa.owned",
                "auto.owned",
                "studio.active",
                "lavoro.ruolo",
                "salute.visita",
            ],
            session_phase="active",
        )
    )
    assert (plan.meta or {}).get("phase") != "wrap"


def test_legacy_domain_gap_helper_still_finds_rogito():
    from ai_life_strategist.knowledge_gap import infer_known_from_text
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist.question_planner import plan_domain_gap_legacy

    facts = infer_known_from_text("Ho comprato casa.")
    plan = plan_domain_gap_legacy(
        ReasoningContext(
            user_id="u1",
            known_facts=facts,
            last_user_text="Ho comprato casa.",
            session_phase="active",
            domains_touched=["casa"],
        ),
        focus_domain="casa",
    )
    assert plan is not None
    assert plan.prefer_document is True
    assert plan.recommended_document is not None
    assert plan.recommended_document.doc_type == "rogito"
