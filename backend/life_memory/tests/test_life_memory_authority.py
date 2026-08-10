"""Prompt 6.1.1 — epistemic authority + clarification eligibility."""
from __future__ import annotations

from life_memory.assemble import assemble_life_memory
from life_memory.authority import (
    authority_band,
    memory_status_from_authority,
    needs_clarification,
    question_switches_to_ora_perspective,
)
from life_memory.gemini_clarify import deterministic_clarify_question
from life_memory.identity import resolve_memory_candidates
from life_memory.models import ClarificationSession, ProfileWriteTarget


def _obj(value, *, source="inferred", status="suggested", confidence=0.55, confirmed=False):
    return {
        "value": value,
        "source": source,
        "status": status,
        "confidence": confidence,
        "confirmed": confirmed,
        "updated_at": "2026-08-08T12:00:00+00:00",
    }


def _profile(domains: dict):
    return {
        "user_id": "u1",
        "domains": {
            d: {"domain": d, "objects": objs} for d, objs in domains.items()
        },
    }


def test_a_life_setup_confirmed_occupation_known_no_clarify():
    profile = _profile(
        {
            "lavoro": {
                "lavoro.ruolo": _obj(
                    "Guardia di Finanza",
                    source="user_said",
                    status="confirmed",
                    confidence=0.95,
                    confirmed=True,
                )
            }
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    work = [m for m in mems if m.slot == "lavoro.role"]
    assert len(work) == 1
    assert work[0].status == "known"
    assert work[0].clarifiable is False
    assert "Da chiarire" not in work[0].statement


def test_b_life_setup_confirmed_name_known():
    profile = _profile(
        {
            "mlc": {
                "mlc.identity.name": _obj(
                    "Francesco",
                    source="user_said",
                    status="confirmed",
                    confirmed=True,
                    confidence=0.95,
                )
            }
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    name = [m for m in mems if m.slot == "identity.name"]
    assert name and name[0].status == "known" and not name[0].clarifiable


def test_c_gps_alone_not_known_residence():
    """Device signal / current location must not create known 'Vivi a…'."""
    profile = _profile(
        {
            "casa": {
                "casa.citta": _obj(
                    "Tarquinia",
                    source="device_signal",
                    status="suggested",
                    confidence=0.9,
                )
            }
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    # device residence dropped entirely
    assert not any(c.slot == "casa.city" for c in cands)

    profile2 = _profile(
        {
            "mlc": {
                "mlc.current_location": _obj(
                    "Tarquinia", source="device_signal", status="suggested"
                )
            }
        }
    )
    cands2, _, _ = assemble_life_memory(profile=profile2)
    assert not any("Vivi" in (c.statement or "") for c in cands2)


def test_d_gps_plus_explicit_residence_confirmation_known():
    profile = _profile(
        {
            "casa": {
                "casa.citta": _obj(
                    "Tarquinia",
                    source="user_confirmed",
                    status="confirmed",
                    confirmed=True,
                    confidence=0.95,
                )
            }
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    city = [m for m in mems if m.slot == "casa.city"]
    assert city and city[0].status == "known" and not city[0].clarifiable


def test_e_ai_inferred_city_clarification_eligible():
    profile = _profile(
        {
            "casa": {
                "casa.citta": _obj(
                    "Viterbo",
                    source="inferred",
                    status="suggested",
                    confidence=0.55,
                )
            }
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    city = [m for m in mems if m.slot == "casa.city"]
    assert city
    assert city[0].status == "ambiguous"
    assert city[0].clarifiable is True


def test_f_explicit_correction_supersedes_stale():
    profile = _profile(
        {
            "casa": {
                "casa.citta": _obj(
                    "Roma",
                    source="inferred",
                    status="suggested",
                    confidence=0.6,
                )
            },
            "mlc": {
                "mlc.life_places.home": _obj(
                    "Tarquinia",
                    source="user_said",
                    status="confirmed",
                    confirmed=True,
                    confidence=0.95,
                )
            },
        }
    )
    cands, _, _ = assemble_life_memory(profile=profile)
    mems, _, _ = resolve_memory_candidates(cands)
    city = [m for m in mems if m.slot == "casa.city"]
    assert len(city) == 1
    assert "Tarquinia" in (city[0].belief_statement or city[0].statement)
    assert "Roma" not in (city[0].belief_statement or "")
    assert city[0].status == "known"


def test_g_name_clarify_question_never_ora_perspective():
    q_bad = "Scusa, ma mi chiamo Francesco o ti riferivi a me?"
    assert question_switches_to_ora_perspective(q_bad) is True
    q_good = "Mi risulta che ti chiami Francesco. È corretto?"
    assert question_switches_to_ora_perspective(q_good) is False
    sess = ClarificationSession(
        id="lmc_x",
        user_id="u1",
        memory_id="memory:x",
        belief_statement="Ti chiami Francesco.",
        profile_targets=[ProfileWriteTarget(domain="mlc", key="mlc.identity.name")],
    )
    det = deterministic_clarify_question(sess)
    assert "mi chiamo" not in det.lower()
    assert "ti chiami" in det.lower() or "francesco" in det.lower()
    assert not question_switches_to_ora_perspective(det)


def test_h_deterministic_question_addresses_user():
    sess = ClarificationSession(
        id="lmc_x",
        user_id="u1",
        memory_id="memory:x",
        belief_statement="Lavori nella Guardia di Finanza.",
    )
    q = deterministic_clarify_question(sess)
    assert "lavori" in q.lower() or "guardia" in q.lower()
    assert "mi chiamo" not in q.lower()


def test_i_known_item_not_clarifiable():
    assert (
        needs_clarification(
            status="known",
            authority="user_stated",
            has_profile_targets=True,
        )
        is False
    )


def test_j_ambiguous_item_clarifiable():
    assert (
        needs_clarification(
            status="ambiguous",
            authority="ai_inferred",
            has_profile_targets=True,
        )
        is True
    )


def test_account_name_boosts_known():
    profile = _profile(
        {
            "mlc": {
                "mlc.identity.name": _obj(
                    "Francesco", source="inferred", status="suggested", confidence=0.55
                )
            }
        }
    )
    cands, _, _ = assemble_life_memory(
        profile=profile, auth_user={"name": "francesco"}
    )
    mems, _, _ = resolve_memory_candidates(cands)
    name = [m for m in mems if m.slot == "identity.name"]
    assert name and name[0].status == "known" and not name[0].clarifiable


def test_authority_bands():
    assert authority_band(source="user_confirmed", field_status="confirmed", confirmed=True) == "user_confirmed"
    assert authority_band(source="inferred", field_status="suggested") == "ai_inferred"
    assert memory_status_from_authority(
        source="user_said", field_status="confirmed", confidence=0.9, confirmed=True
    ) == "known"
