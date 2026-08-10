"""Prompt 5.2 — grounded Gemini Life Map vertical slice (mocked Gemini)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from life_map.assemble import assemble_life_map
from life_map.gemini_interpret import interpret_with_gemini, life_map_gemini_enabled
from life_map.governance import (
    is_presentable_life_map_item,
    merge_presentation,
    stable_inferred_situation_id,
)
from life_map.models import (
    EvidenceRef,
    GeminiLifeMapPayload,
    LifeMapInterpretation,
    LifeSituationInterpretation,
    PresentationSituation,
)
from life_map.validate import validate_gemini_payload


PALESTRA_EVIDENCE = EvidenceRef(
    id="profile:salute:salute.attivita",
    kind="life_profile_fact",
    label="Salute",
    summary="Da settembre inizio palestra con Marco.",
)


def test_novel_grounded_situation_open_semantics_presentable():
    """§28 — palestra-like novel situation without gym taxonomy."""
    evidence = [PALESTRA_EVIDENCE]
    payload = GeminiLifeMapPayload(
        novel_situations=[
            {
                "id": "gemini-arbitrary-id",
                "label": "Palestra con Marco",
                "temporal_state": "Da settembre",
                "evidence_refs": ["profile:salute:salute.attivita"],
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
    sit = interp.situations[0]
    expected_id = stable_inferred_situation_id(["profile:salute:salute.attivita"])
    assert sit.id == expected_id
    assert sit.id != "gemini-arbitrary-id"
    assert sit.kind == "inferred"
    assert sit.href is None

    areas, situations = merge_presentation(
        areas=[],
        situations=[],
        interpretation=interp,
        valid_evidence_ids={e.id for e in evidence},
    )
    assert len(situations) == 1
    assert situations[0].title == "Palestra con Marco"
    assert situations[0].kind == "inferred"
    assert situations[0].href == ""
    assert situations[0].id == expected_id
    # No gym enum
    assert "gym" not in situations[0].kind


def test_stable_identity_survives_label_paraphrase():
    refs = ["profile:salute:salute.attivita"]
    a = stable_inferred_situation_id(refs)
    b = stable_inferred_situation_id(list(reversed(refs)))
    assert a == b
    payload1 = GeminiLifeMapPayload(
        novel_situations=[
            {
                "label": "Palestra con Marco",
                "evidence_refs": refs,
                "confidence": "likely",
            }
        ]
    )
    payload2 = GeminiLifeMapPayload(
        novel_situations=[
            {
                "label": "Allenamenti con Marco",
                "evidence_refs": refs,
                "confidence": "likely",
            }
        ]
    )
    i1 = validate_gemini_payload(
        payload1, evidence=[PALESTRA_EVIDENCE], known_area_ids=set(), known_situation_ids=set()
    )
    i2 = validate_gemini_payload(
        payload2, evidence=[PALESTRA_EVIDENCE], known_area_ids=set(), known_situation_ids=set()
    )
    assert i1.situations[0].id == i2.situations[0].id == a


def test_hallucinated_paris_dropped():
    """§29 — travel invention with fake evidence ref."""
    payload = GeminiLifeMapPayload(
        novel_situations=[
            {
                "label": "Viaggio a Parigi",
                "evidence_refs": ["travel:fake_paris"],
                "confidence": "known",
            }
        ]
    )
    interp = validate_gemini_payload(
        payload,
        evidence=[PALESTRA_EVIDENCE],
        known_area_ids=set(),
        known_situation_ids=set(),
    )
    assert interp.situations == []
    areas, situations = merge_presentation(
        areas=[],
        situations=[],
        interpretation=interp,
        valid_evidence_ids={PALESTRA_EVIDENCE.id},
    )
    assert situations == []


def test_ambiguous_relationship_not_promoted():
    """§30 — Marco relationship ambiguous → ambiguity, not confirmed relation."""
    payload = GeminiLifeMapPayload(
        novel_situations=[
            {
                "label": "Palestra con Marco",
                "evidence_refs": [PALESTRA_EVIDENCE.id],
                "confidence": "likely",
            }
        ],
        relationships=[
            {
                "source_id": "inferred:x",
                "target_id": "area:salute",
                "relation": "involves_person",
                "evidence_refs": [PALESTRA_EVIDENCE.id],
                "confidence": "ambiguous",
                "ambiguity_question": "Marco è un amico o un trainer?",
            }
        ],
    )
    # First validate novel sit to get stable id, then relationships need that id —
    # ambiguous rel uses source inferred:x which won't match; test ambiguity channel:
    payload2 = GeminiLifeMapPayload(
        ambiguities=[
            {
                "question": "Marco è un amico o un trainer?",
                "about_ids": ["area:salute"],
                "evidence_refs": [PALESTRA_EVIDENCE.id],
            }
        ],
        relationships=[
            {
                "source_id": "area:salute",
                "target_id": "area:famiglia",
                "relation": "involves_person",
                "evidence_refs": [PALESTRA_EVIDENCE.id],
                "confidence": "ambiguous",
                "ambiguity_question": "Marco è un amico o un trainer?",
            }
        ],
    )
    interp = validate_gemini_payload(
        payload2,
        evidence=[PALESTRA_EVIDENCE],
        known_area_ids={"area:salute", "area:famiglia"},
        known_situation_ids=set(),
    )
    assert interp.relationships == []
    assert any("Marco" in a.question for a in interp.ambiguities)


def test_deterministic_exam_date_wins_over_ai():
    """§31 — structured exam temporal not mutated by AI."""
    det = PresentationSituation(
        id="study:sp1",
        kind="study",
        title="Psicologia",
        temporal="Esame il 20 settembre",
        href="/study-plan/sp1",
    )
    evid = EvidenceRef(
        id="study:sp1",
        kind="study_plan",
        label="Psicologia",
        summary="Esame il 20 settembre",
    )
    interp = LifeMapInterpretation(
        ai_used=True,
        situations=[
            LifeSituationInterpretation(
                id=stable_inferred_situation_id(["study:sp1"]),
                label="Preparazione Psicologia",
                temporal_state="Esame il 18 settembre",
                evidence_refs=["study:sp1"],
                confidence="likely",
                source="inferred",
            )
        ],
    )
    _, situations = merge_presentation(
        areas=[],
        situations=[det],
        interpretation=interp,
        valid_evidence_ids={evid.id},
    )
    # Dedup drops AI; structured temporal untouched
    assert len(situations) == 1
    assert situations[0].id == "study:sp1"
    assert situations[0].temporal == "Esame il 20 settembre"


def test_dedup_ai_paraphrase_of_study():
    """§32 — one situation when AI rephrases same study evidence."""
    det = PresentationSituation(
        id="study:sp1",
        kind="study",
        title="Esame di Psicologia",
        temporal="Esame tra 5 giorni",
        href="/study-plan/sp1",
    )
    interp = LifeMapInterpretation(
        ai_used=True,
        situations=[
            LifeSituationInterpretation(
                id="inferred:dup",
                label="Preparazione Psicologia",
                evidence_refs=["study:sp1"],
                confidence="likely",
                source="inferred",
            )
        ],
    )
    _, situations = merge_presentation(
        areas=[],
        situations=[det],
        interpretation=interp,
        valid_evidence_ids={"study:sp1"},
    )
    assert len(situations) == 1
    assert situations[0].title == "Esame di Psicologia"


@pytest.mark.asyncio
async def test_gemini_down_keeps_deterministic(monkeypatch):
    """§33 — Gemini error → still return structured map."""
    monkeypatch.setenv("LIFE_MAP_GEMINI", "1")
    areas, situations, evidence, _, _cands = assemble_life_map(
        profile={
            "domains": {
                "lavoro": {
                    "objects": {"lavoro.ruolo": {"value": "Analista"}},
                }
            }
        },
        study_plans=[],
        travel_projects=[],
    )
    with patch(
        "llm.structured.chat_json",
        new=AsyncMock(side_effect=TimeoutError("timeout")),
    ):
        interp = await interpret_with_gemini(
            areas=areas, situations=situations, evidence=evidence
        )
    assert interp is None
    merged_a, merged_s = merge_presentation(
        areas=areas,
        situations=situations,
        interpretation=None,
        valid_evidence_ids={e.id for e in evidence},
    )
    assert any(a.domain == "lavoro" for a in merged_a)
    assert merged_s == situations


def test_feature_off_no_gemini(monkeypatch):
    """§34 — LIFE_MAP_GEMINI=0 → no AI."""
    monkeypatch.setenv("LIFE_MAP_GEMINI", "0")
    assert life_map_gemini_enabled() is False


@pytest.mark.asyncio
async def test_feature_off_interpret_skips_chat(monkeypatch):
    monkeypatch.setenv("LIFE_MAP_GEMINI", "0")
    with patch("llm.structured.chat_json", new=AsyncMock()) as chat:
        out = await interpret_with_gemini(areas=[], situations=[], evidence=[PALESTRA_EVIDENCE])
        assert out is None
        chat.assert_not_called()


def test_presentable_policy():
    assert is_presentable_life_map_item(
        confidence="likely",
        evidence_refs=[PALESTRA_EVIDENCE.id],
        valid_evidence_ids={PALESTRA_EVIDENCE.id},
    )
    assert not is_presentable_life_map_item(
        confidence="ambiguous",
        evidence_refs=[PALESTRA_EVIDENCE.id],
        valid_evidence_ids={PALESTRA_EVIDENCE.id},
    )
    assert not is_presentable_life_map_item(
        confidence="likely",
        evidence_refs=["missing"],
        valid_evidence_ids={PALESTRA_EVIDENCE.id},
    )


def test_assemble_still_includes_profile_evidence_for_novel():
    """Evidence source for vertical slice: Life Profile free-text fact."""
    profile = {
        "domains": {
            "salute": {
                "objects": {
                    "salute.attivita": {
                        "value": "Da settembre inizio palestra con Marco.",
                    }
                }
            }
        }
    }
    areas, sits, evid, _, _cands = assemble_life_map(
        profile=profile, study_plans=[], travel_projects=[]
    )
    assert any(a.domain == "salute" for a in areas)
    assert sits == []
    assert any("palestra" in (e.summary or "").lower() for e in evid)
