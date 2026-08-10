"""Life Map foundation — no live Gemini calls."""
from __future__ import annotations

from datetime import date

from life_map.assemble import assemble_life_map
from life_map.gemini_interpret import life_map_gemini_enabled
from life_map.models import EvidenceRef, GeminiLifeMapPayload
from life_map.governance import merge_presentation
from life_map.validate import validate_gemini_payload


def test_assemble_persistent_area_from_facts():
    profile = {
        "domains": {
            "lavoro": {
                "domain": "lavoro",
                "objects": {
                    "lavoro.ruolo": {"key": "lavoro.ruolo", "value": "Guardia di Finanza"},
                },
            },
            "mlc": {
                "domain": "mlc",
                "objects": {"mlc.identity.name": {"value": "Test"}},
            },
        }
    }
    areas, sits, evid, fp, _cands = assemble_life_map(
        profile=profile, study_plans=[], travel_projects=[]
    )
    assert len(areas) == 1
    assert areas[0].domain == "lavoro"
    assert areas[0].title == "Lavoro"
    assert areas[0].identity == "Guardia di Finanza"
    assert sits == []
    assert any(e.id.startswith("profile:lavoro:") for e in evid)
    assert fp


def test_assemble_active_study_situation():
    today = date(2026, 8, 9)
    plans = [
        {
            "id": "sp1",
            "status": "active",
            "exam_name": "Psicologia",
            "subject": "Psicologia",
            "exam_date": "2026-08-14",
        },
        {"id": "sp2", "status": "draft", "exam_name": "Draft", "exam_date": "2026-09-01"},
        {
            "id": "sp3",
            "status": "active",
            "exam_name": "Past",
            "exam_date": "2026-08-01",
        },
    ]
    areas, sits, evid, _, _cands = assemble_life_map(
        profile=None, study_plans=plans, travel_projects=[], today=today
    )
    assert areas == []
    assert len(sits) == 1
    assert sits[0].kind == "study"
    assert sits[0].title == "Psicologia"
    assert sits[0].href == "/study-plan/sp1"
    assert "Esame" in (sits[0].temporal or "")
    assert any(e.id == "study:sp1" for e in evid)


def test_assemble_active_travel_situation():
    projects = [
        {
            "id": "tp1",
            "status": "active",
            "title": "Vacanza a Vibo Marina",
            "destination": "Vibo Marina",
            "start_date": "2026-08-09",
            "end_date": "2026-08-24",
            "phase": "during",
        }
    ]
    _, sits, evid, _, _cands = assemble_life_map(
        profile=None, study_plans=[], travel_projects=projects
    )
    assert len(sits) == 1
    assert sits[0].kind == "travel"
    assert "Vibo" in sits[0].title
    assert sits[0].href == "/travel-project/tp1"
    assert any(e.id == "travel:tp1" for e in evid)


def test_novel_situation_accepted_with_evidence():
    evidence = [
        EvidenceRef(
            id="profile:salute:salute.attivita",
            kind="life_profile_fact",
            label="Salute",
            summary="palestra con Marco da settembre",
        )
    ]
    payload = GeminiLifeMapPayload(
        novel_situations=[
            {
                "id": "inferred:palestra",
                "label": "Palestra con Marco",
                "temporal_state": "Da settembre",
                "evidence_refs": ["profile:salute:salute.attivita"],
                "related_area_ids": ["area:salute"],
                "confidence": "likely",
            }
        ]
    )
    interp = validate_gemini_payload(
        payload,
        evidence=evidence,
        known_area_ids={"area:salute"},
        known_situation_ids=set(),
    )
    assert len(interp.situations) == 1
    assert interp.situations[0].label == "Palestra con Marco"
    assert interp.situations[0].source == "inferred"
    from life_map.governance import stable_inferred_situation_id
    assert interp.situations[0].id == stable_inferred_situation_id(
        ["profile:salute:salute.attivita"]
    )


def test_ungrounded_novel_situation_rejected():
    payload = GeminiLifeMapPayload(
        novel_situations=[
            {
                "id": "inferred:auto",
                "label": "Possiedi un'auto",
                "evidence_refs": ["profile:auto:fake"],
                "confidence": "known",
            }
        ]
    )
    interp = validate_gemini_payload(
        payload,
        evidence=[],
        known_area_ids=set(),
        known_situation_ids=set(),
    )
    assert interp.situations == []


def test_ambiguous_relation_becomes_ambiguity_not_fact():
    evidence = [
        EvidenceRef(
            id="profile:salute:x",
            kind="life_profile_fact",
            label="Salute",
            summary="palestra con Marco",
        )
    ]
    payload = GeminiLifeMapPayload(
        novel_situations=[
            {
                "id": "inferred:marco",
                "label": "Palestra con Marco",
                "evidence_refs": ["profile:salute:x"],
                "confidence": "ambiguous",
                "ambiguity_question": "Marco è un amico o un trainer?",
            }
        ]
    )
    interp = validate_gemini_payload(
        payload,
        evidence=evidence,
        known_area_ids={"area:salute"},
        known_situation_ids=set(),
    )
    assert interp.situations == []
    assert len(interp.ambiguities) == 1
    assert "Marco" in interp.ambiguities[0].question


def test_judgy_label_rejected():
    evidence = [
        EvidenceRef(id="study:1", kind="study_plan", label="Esame", summary="x")
    ]
    payload = GeminiLifeMapPayload(
        novel_situations=[
            {
                "id": "inferred:x",
                "label": "La tua sfida universitaria",
                "evidence_refs": ["study:1"],
                "confidence": "likely",
            }
        ]
    )
    interp = validate_gemini_payload(
        payload,
        evidence=evidence,
        known_area_ids=set(),
        known_situation_ids=set(),
    )
    assert interp.situations == []


def test_merge_injects_grounded_novel_not_ungrounded():
    from life_map.models import (
        LifeMapInterpretation,
        LifeSituationInterpretation,
        PresentationArea,
        PresentationSituation,
    )

    areas = [PresentationArea(id="area:studio", domain="studio", title="Studio")]
    sits = [
        PresentationSituation(
            id="study:1",
            kind="study",
            title="Psicologia",
            href="/study-plan/1",
        )
    ]
    grounded = LifeMapInterpretation(
        ai_used=True,
        situations=[
            LifeSituationInterpretation(
                id="inferred:palestra",
                label="Palestra",
                evidence_refs=["profile:salute:x"],
                confidence="likely",
                source="inferred",
            )
        ],
    )
    _, out_s = merge_presentation(
        areas=areas,
        situations=sits,
        interpretation=grounded,
        valid_evidence_ids={"profile:salute:x", "study:1"},
    )
    assert len(out_s) == 2
    assert out_s[0].id == "study:1"
    assert out_s[1].title == "Palestra"
    assert out_s[1].href == ""

    bad = LifeMapInterpretation(
        ai_used=True,
        situations=[
            LifeSituationInterpretation(
                id="inferred:paris",
                label="Parigi",
                evidence_refs=["travel:fake"],
                confidence="likely",
                source="inferred",
            )
        ],
    )
    _, out_bad = merge_presentation(
        areas=areas,
        situations=sits,
        interpretation=bad,
        valid_evidence_ids={"study:1"},
    )
    assert len(out_bad) == 1


def test_gemini_flag_default_off(monkeypatch):
    monkeypatch.delenv("LIFE_MAP_GEMINI", raising=False)
    assert life_map_gemini_enabled() is False
    monkeypatch.setenv("LIFE_MAP_GEMINI", "1")
    assert life_map_gemini_enabled() is True


def test_empty_sources():
    areas, sits, evid, fp, _cands = assemble_life_map(
        profile={"domains": {}}, study_plans=[], travel_projects=[]
    )
    assert areas == []
    assert sits == []
    assert evid == []
    assert fp
