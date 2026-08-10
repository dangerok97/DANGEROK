"""Prompt 6.1 — Memory clarification loop tests (A–O)."""
from __future__ import annotations

from life_memory.assemble import assemble_life_memory
from life_memory.gemini_clarify import (
    deterministic_clarify_question,
    heuristic_resolve,
    validate_resolution,
)
from life_memory.identity import resolve_memory_candidates
from life_memory.models import (
    ClarificationSession,
    GeminiClarifyResolution,
    ProfileWriteTarget,
    ProposedFact,
)
from life_memory.present import assertive_core, present_statement


def _profile(domains: dict):
    return {
        "user_id": "u1",
        "domains": {
            d: {"domain": d, "objects": objs} for d, objs in domains.items()
        },
    }


def _fact(key, value, **extra):
    base = {
        "key": key,
        "value": value,
        "confidence": 0.55,
        "source": "inferred",
        "status": "suggested",
        "updated_at": "2026-08-01T10:00:00+00:00",
    }
    base.update(extra)
    return base


def _ambiguous_city_memory():
    profile = _profile(
        {
            "casa": {"casa.citta": _fact("casa.citta", "Tarquinia")},
            "mlc": {"mlc.life_places.home": _fact("mlc.life_places.home", "Tarquinia")},
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    city = [m for m in mems if m.slot == "casa.city"][0]
    return city


def test_l_ambiguous_language_non_assertive():
    presented, core = present_statement("Vivi a Tarquinia.", "ambiguous")
    assert "Mi risulta" in presented
    assert "sicura" in presented
    assert core.startswith("Vivi a Tarquinia")


def test_m_known_language_assertive():
    presented, core = present_statement("Vivi a Tarquinia.", "known")
    assert presented == core
    assert presented.startswith("Vivi a")
    assert "risulta" not in presented.lower()


def test_n_no_confidence_leakage():
    m = _ambiguous_city_memory()
    assert "0." not in m.statement
    assert "confidence" not in m.statement.lower()
    assert "AMBIGUOUS" not in m.statement


def test_clarifiable_contract_fields():
    m = _ambiguous_city_memory()
    assert m.clarifiable is True
    assert m.profile_targets
    assert m.clarification_goal
    assert m.candidate_values


def test_a_confirm_proposed_fact_shape():
    m = _ambiguous_city_memory()
    sess = ClarificationSession(
        id="lmc_1",
        user_id="u1",
        memory_id=m.id,
        belief_statement=m.belief_statement or m.statement,
        candidate_values=m.candidate_values,
        profile_targets=m.profile_targets,
        evidence_refs=m.evidence_refs,
    )
    raw = GeminiClarifyResolution(
        resolution="confirmed",
        target_memory_id=m.id,
        proposed_facts=[
            ProposedFact(
                domain=m.profile_targets[0].domain,
                key=m.profile_targets[0].key,
                value="tarquinia",
                action="confirm",
            )
        ],
    )
    v = validate_resolution(sess, raw)
    assert v.resolution == "confirmed"
    assert v.proposed_facts


def test_b_corrected_requires_value():
    m = _ambiguous_city_memory()
    sess = ClarificationSession(
        id="lmc_1",
        user_id="u1",
        memory_id=m.id,
        belief_statement="Vivi a Tarquinia.",
        profile_targets=m.profile_targets,
        candidate_values=["tarquinia"],
    )
    raw = GeminiClarifyResolution(
        resolution="corrected",
        target_memory_id=m.id,
        proposed_facts=[
            ProposedFact(
                domain=m.profile_targets[0].domain,
                key=m.profile_targets[0].key,
                value="Roma",
                action="correct",
            )
        ],
    )
    v = validate_resolution(sess, raw)
    assert v.resolution == "corrected"
    assert v.proposed_facts[0].value == "Roma"


def test_c_still_ambiguous():
    m = _ambiguous_city_memory()
    sess = ClarificationSession(
        id="lmc_1",
        user_id="u1",
        memory_id=m.id,
        belief_statement="Vivi a Tarquinia.",
        profile_targets=m.profile_targets,
    )
    raw = GeminiClarifyResolution(
        resolution="still_ambiguous",
        target_memory_id=m.id,
        needs_followup=True,
        followup_question="Mi dici dove vivi adesso?",
    )
    v = validate_resolution(sess, raw)
    assert v.resolution == "still_ambiguous"


def test_d_heuristic_yes_confirm():
    m = _ambiguous_city_memory()
    sess = ClarificationSession(
        id="lmc_1",
        user_id="u1",
        memory_id=m.id,
        belief_statement="Vivi a Tarquinia.",
        profile_targets=m.profile_targets,
        candidate_values=["tarquinia"],
    )
    r = heuristic_resolve(sess, user_text="Sì.")
    assert r.resolution == "confirmed"


def test_e_multi_fact_additional_suggest_only():
    m = _ambiguous_city_memory()
    sess = ClarificationSession(
        id="lmc_1",
        user_id="u1",
        memory_id=m.id,
        belief_statement="Vivi a Tarquinia.",
        profile_targets=m.profile_targets,
        candidate_values=["tarquinia"],
    )
    raw = GeminiClarifyResolution(
        resolution="confirmed",
        target_memory_id=m.id,
        proposed_facts=[
            ProposedFact(
                domain=m.profile_targets[0].domain,
                key=m.profile_targets[0].key,
                value="Tarquinia",
                action="confirm",
            )
        ],
        additional_facts=[
            ProposedFact(
                domain="lavoro",
                key="lavoro.citta",
                value="Civitavecchia",
                action="correct",
            )
        ],
    )
    v = validate_resolution(sess, raw)
    assert v.additional_facts
    assert all(f.action == "suggest" for f in v.additional_facts)


def test_f_hallucinated_memory_id_rejected():
    m = _ambiguous_city_memory()
    sess = ClarificationSession(
        id="lmc_1",
        user_id="u1",
        memory_id=m.id,
        belief_statement="Vivi a Tarquinia.",
        profile_targets=m.profile_targets,
    )
    raw = GeminiClarifyResolution(
        resolution="corrected",
        target_memory_id="memory:forged",
        proposed_facts=[
            ProposedFact(domain="casa", key="casa.citta", value="Roma", action="correct")
        ],
    )
    v = validate_resolution(sess, raw)
    assert v.target_memory_id == m.id
    # forged id forces still_ambiguous and clears proposed
    assert v.resolution == "still_ambiguous"
    assert v.proposed_facts == []


def test_g_unrelated_mutation_dropped():
    m = _ambiguous_city_memory()
    sess = ClarificationSession(
        id="lmc_1",
        user_id="u1",
        memory_id=m.id,
        belief_statement="Vivi a Tarquinia.",
        profile_targets=[ProfileWriteTarget(domain="casa", key="casa.citta")],
    )
    raw = GeminiClarifyResolution(
        resolution="corrected",
        target_memory_id=m.id,
        proposed_facts=[
            ProposedFact(domain="finanze", key="finanze.iban", value="IT00", action="correct"),
            ProposedFact(domain="casa", key="casa.citta", value="Roma", action="correct"),
        ],
    )
    v = validate_resolution(sess, raw)
    assert len(v.proposed_facts) == 1
    assert v.proposed_facts[0].key == "casa.citta"


def test_h_gemini_unavailable_free_text_no_mutate():
    m = _ambiguous_city_memory()
    sess = ClarificationSession(
        id="lmc_1",
        user_id="u1",
        memory_id=m.id,
        belief_statement="Vivi a Tarquinia.",
        profile_targets=m.profile_targets,
        candidate_values=["tarquinia"],
    )
    r = heuristic_resolve(sess, user_text="Ora vivo a Viterbo da due mesi")
    assert r.resolution == "still_ambiguous"
    assert r.evidence_interpretation == "gemini_unavailable_free_text"


def test_o_no_domain_specific_frontend_branching_in_goal():
    m = _ambiguous_city_memory()
    assert "city" not in (m.clarification_goal or "").lower() or "durable" in (
        m.clarification_goal or ""
    ).lower()
    # Goal is generic
    assert "Determine whether this belief" in (m.clarification_goal or "")


def test_deterministic_question_exists():
    sess = ClarificationSession(
        id="lmc_1",
        user_id="u1",
        memory_id="memory:x",
        belief_statement="Vivi a Tarquinia.",
    )
    q = deterministic_clarify_question(sess)
    assert "Tarquinia" in q or "tarquinia" in q.lower()
    assert "?" in q


def test_assertive_core_strips_soft_wrapper():
    soft = "Mi risulta che vivi a Tarquinia, ma non ne sono ancora sicura."
    assert assertive_core(soft).startswith("Vivi a Tarquinia")


def test_j_superseded_not_current_after_strong_correct():
    profile = _profile(
        {
            "casa": {
                "casa.citta": _fact(
                    "casa.citta",
                    "Roma",
                    source="inferred",
                    status="suggested",
                    confidence=0.6,
                    updated_at="2026-01-01T10:00:00+00:00",
                )
            },
            "mlc": {
                "mlc.life_places.home": _fact(
                    "mlc.life_places.home",
                    "Tarquinia",
                    source="user_said",
                    status="corrected",
                    confidence=1.0,
                    updated_at="2026-08-01T10:00:00+00:00",
                )
            },
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    city = [m for m in mems if "Vivi" in (m.belief_statement or m.statement)]
    assert len(city) == 1
    assert "Tarquinia" in (city[0].belief_statement or "")
    assert "Roma" not in (city[0].belief_statement or "")
    assert city[0].status == "known"
