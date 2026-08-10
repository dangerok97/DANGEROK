"""Prompt 6 — Life Memory V1 regression tests (A–N)."""
from __future__ import annotations

from life_memory.assemble import assemble_life_memory
from life_memory.gemini_present import life_memory_gemini_enabled
from life_memory.identity import (
    apply_gemini_wordings,
    resolve_memory_candidates,
    stable_memory_id,
)
from life_memory.models import MemoryItem
from life_memory.statements import (
    is_sensitive_key,
    statement_for_profile_fact,
)


def _profile_fact(key: str, value, **extra):
    base = {
        "key": key,
        "value": value,
        "confidence": 0.9,
        "source": "user_said",
        "status": "confirmed",
        "updated_at": "2026-08-01T10:00:00+00:00",
    }
    base.update(extra)
    return base


def _profile(domains: dict):
    return {
        "user_id": "u1",
        "domains": {
            d: {"domain": d, "objects": objs} for d, objs in domains.items()
        },
    }


def test_a_life_profile_known_fact_canonical_memory():
    profile = _profile(
        {
            "lavoro": {
                "lavoro.ruolo": _profile_fact("lavoro.ruolo", "Guardia di Finanza"),
            }
        }
    )
    cands, evid, fp = assemble_life_memory(profile=profile)
    assert fp
    assert evid
    mems, groups, _ = resolve_memory_candidates(cands)
    assert len(mems) == 1
    assert "Guardia di Finanza" in mems[0].statement
    assert mems[0].status == "known"
    assert groups and groups[0].label == "Lavoro"


def test_b_same_fact_multiple_sources_one_memory():
    profile = _profile(
        {
            "lavoro": {
                "lavoro.ruolo": _profile_fact(
                    "lavoro.ruolo",
                    "Guardia di Finanza",
                    source="user_said",
                    status="confirmed",
                ),
            },
            "mlc": {
                "mlc.responsibilities": _profile_fact(
                    "mlc.responsibilities",
                    "nella Guardia di Finanza",
                    source="semantic_extract",
                    status="extracted",
                    confidence=0.8,
                    updated_at="2026-08-02T10:00:00+00:00",
                ),
            },
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, notes = resolve_memory_candidates(cands)
    # same slot family lavoro.role → one
    assert len([m for m in mems if "Finanza" in m.statement]) == 1
    assert any(n.relation == "same" for n in notes)


def test_c_similar_but_distinct_remain_distinct():
    profile = _profile(
        {
            "casa": {
                "casa.citta": _profile_fact("casa.citta", "Tarquinia"),
                "casa.indirizzo": _profile_fact(
                    "casa.indirizzo", "Via Roma 1", status="confirmed"
                ),
            }
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    assert len(mems) == 2
    texts = " ".join(m.statement for m in mems)
    assert "Tarquinia" in texts and "Via Roma" in texts


def test_d_explicit_correction_supersedes_stale():
    profile = _profile(
        {
            "casa": {
                "casa.citta": _profile_fact(
                    "casa.citta",
                    "Roma",
                    source="document_extract",
                    status="extracted",
                    confidence=0.7,
                    updated_at="2026-01-01T10:00:00+00:00",
                ),
            },
            "mlc": {
                "mlc.life_places.home": _profile_fact(
                    "mlc.life_places.home",
                    "Tarquinia",
                    source="user_said",
                    status="corrected",
                    confidence=1.0,
                    updated_at="2026-08-01T10:00:00+00:00",
                ),
            },
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    city = [m for m in mems if "Vivi" in m.statement]
    assert len(city) == 1
    assert "Tarquinia" in city[0].statement
    assert "Roma" not in city[0].statement
    assert city[0].status == "known"


def test_e_unresolved_contradiction_ambiguous():
    profile = _profile(
        {
            "casa": {
                "casa.citta": _profile_fact(
                    "casa.citta",
                    "Roma",
                    source="inferred",
                    status="suggested",
                    confidence=0.6,
                    updated_at="2026-08-01T10:00:00+00:00",
                ),
            },
            "mlc": {
                "mlc.life_places.home": _profile_fact(
                    "mlc.life_places.home",
                    "Tarquinia",
                    source="inferred",
                    status="suggested",
                    confidence=0.6,
                    updated_at="2026-08-02T10:00:00+00:00",
                ),
            },
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    assert len([c for c in cands if c.slot == "casa.city"]) >= 2
    mems, _, _ = resolve_memory_candidates(cands)
    city = [
        m
        for m in mems
        if "vivi" in (m.statement or "").lower()
        or "vivi" in (m.belief_statement or "").lower()
    ]
    assert len(city) == 1
    assert city[0].status == "ambiguous"


def test_f_gemini_flag_off_deterministic():
    assert life_memory_gemini_enabled() is False
    profile = _profile(
        {"studio": {"studio.corso": _profile_fact("studio.corso", "Psicologia")}}
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    assert mems and "Psicologia" in mems[0].statement


def test_g_gemini_hallucinated_memory_id_rejected():
    mem = MemoryItem(
        id="memory:abc",
        statement="Vivi a Tarquinia.",
        domain="casa",
        status="known",
    )
    out = apply_gemini_wordings([mem], [("memory:forged", "Inventato."), ("memory:abc", "Vivi a Tarquinia.")])
    assert len(out) == 1
    assert "Inventato" not in out[0].statement


def test_h_feature_flag_off_works(monkeypatch):
    monkeypatch.setenv("MEMORY_GEMINI", "0")
    assert life_memory_gemini_enabled() is False


def test_i_temporary_study_not_exam_countdown():
    plans = [
        {
            "id": "spl_1",
            "status": "active",
            "exam_name": "Psicologia",
            "subject": "Psicologia",
            "exam_date": "2026-08-13T07:00:00+00:00",
        },
        {
            "id": "spl_2",
            "status": "active",
            "exam_name": "Studio: Psicologia",
            "subject": "Studio: Psicologia",
            "exam_date": "2026-08-12T07:00:00+00:00",
        },
    ]
    cands, _, _ = assemble_life_memory(profile=None, study_plans=plans)
    mems, _, _ = resolve_memory_candidates(cands)
    assert len(mems) == 1
    assert mems[0].statement == "Studi Psicologia."
    assert "giorni" not in mems[0].statement.lower()


def test_j_sensitive_weak_inference_not_surfaced():
    assert is_sensitive_key("auto.vin")
    assert is_sensitive_key("finanze.iban")
    profile = _profile(
        {
            "auto": {
                "auto.vin": _profile_fact("auto.vin", "WVWZZZ1JZXW000001", confidence=0.9),
                "auto.modello": _profile_fact("auto.modello", "Golf"),
            },
            "salute": {
                "salute.diagnosi": _profile_fact(
                    "salute.diagnosi",
                    "something",
                    source="inferred",
                    status="suggested",
                    confidence=0.4,
                ),
            },
        }
    )
    # force a weak inferred non-sensitive that should skip
    profile["domains"]["salute"]["objects"]["salute.nota"] = _profile_fact(
        "salute.nota",
        "dolore",
        source="inferred",
        status="suggested",
        confidence=0.4,
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    texts = " ".join(m.statement for m in mems)
    assert "WVWZZZ" not in texts
    assert "Golf" in texts
    assert "dolore" not in texts


def test_k_stable_memory_id_across_source_ordering():
    a = stable_memory_id(["life_profile:casa:casa.citta", "life_profile:mlc:home"], "casa.city")
    b = stable_memory_id(["life_profile:mlc:home", "life_profile:casa:casa.citta"], "casa.city")
    assert a == b


def test_l_human_presentation_no_enum_leakage():
    s = statement_for_profile_fact(
        domain="lavoro", key="lavoro.ruolo", value="Guardia di Finanza"
    )
    assert s
    assert "lavoro.ruolo" not in s
    assert "confidence" not in s.lower()
    assert "Guardia di Finanza" in s


def test_m_partial_sources_still_useful():
    # study alone when profile empty — still memory
    cands, _, _ = assemble_life_memory(
        profile=None,
        study_plans=[
            {
                "id": "spl_x",
                "status": "active",
                "subject": "Matematica",
            }
        ],
    )
    mems, _, _ = resolve_memory_candidates(cands)
    assert mems and "Matematica" in mems[0].statement


def test_n_empty_user():
    cands, evid, fp = assemble_life_memory(profile=None, study_plans=[], user_notes=[])
    mems, groups, _ = resolve_memory_candidates(cands)
    assert cands == []
    assert mems == []
    assert groups == []
    assert evid == []
    assert fp  # fingerprint still defined


def test_notes_included_as_memory():
    cands, _, _ = assemble_life_memory(
        profile=None,
        user_notes=[{"id": "mem_1", "content": "Parcheggio al piano -2", "created_at": "2026-08-01T10:00:00+00:00"}],
    )
    mems, groups, _ = resolve_memory_candidates(cands)
    assert len(mems) == 1
    assert "Parcheggio" in mems[0].statement
    assert any(g.domain == "note" for g in groups)


def test_rejected_profile_fact_excluded():
    profile = _profile(
        {
            "casa": {
                "casa.citta": _profile_fact(
                    "casa.citta", "Roma", status="rejected", source="document_extract"
                )
            }
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    assert cands == []
