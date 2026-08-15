"""Prompt 5.3 — semantic identity / entity resolution tests."""
from __future__ import annotations

from life_map.assemble import assemble_life_map
from life_map.governance import merge_presentation, stable_inferred_situation_id
from life_map.identity import (
    ResolutionEdge,
    SituationCandidate,
    apply_gemini_same_edges,
    canonical_to_presentation,
    entity_keys_for,
    prefer_presentation_title,
    resolve_candidates_deterministic,
    stable_canonical_id,
)
from life_map.models import (
    EvidenceRef,
    GeminiLifeMapPayload,
    LifeMapInterpretation,
    LifeSituationInterpretation,
)
from life_map.validate import validate_gemini_payload


def _study(
    pid: str,
    *,
    exam_name: str,
    subject: str | None = None,
    exam_date: str,
    updated_at: str = "2026-08-06T12:00:00+00:00",
    source_priority_id: str | None = None,
) -> dict:
    return {
        "id": pid,
        "status": "active",
        "exam_name": exam_name,
        "subject": subject or exam_name,
        "exam_date": exam_date,
        "updated_at": updated_at,
        "source_priority_id": source_priority_id,
    }


def test_case_a_same_study_plan_id_one_canonical():
    """CASE A — same study_plan_id from multiple evidence paths → ONE."""
    c1 = SituationCandidate(
        candidate_id="study:spl_1",
        kind="study",
        title="Psicologia",
        source_type="study_plan",
        source_id="spl_1",
        entity_raw="Psicologia",
        temporal_anchor="2026-08-12",
        evidence_refs=["study:spl_1"],
        href="/study-plan/spl_1",
        temporal="Esame tra 2 giorni",
        updated_at="2026-08-06T10:00:00+00:00",
    )
    c2 = SituationCandidate(
        candidate_id="study:spl_1_dup",
        kind="study",
        title="Psicologia",
        source_type="study_plan",
        source_id="spl_1",  # same authoritative id
        entity_raw="Psicologia",
        temporal_anchor="2026-08-12",
        evidence_refs=["study:spl_1"],
        href="/study-plan/spl_1",
        temporal="Esame tra 2 giorni",
        updated_at="2026-08-06T11:00:00+00:00",
    )
    cans, edges = resolve_candidates_deterministic([c1, c2])
    assert len(cans) == 1
    assert any(e.relation == "same" and e.source == "structured" for e in edges)


def test_case_b_same_entity_same_exam_date():
    """CASE B — Psicologia + Studio: Psicologia same day → ONE."""
    plans = [
        _study("spl_a", exam_name="Psicologia", exam_date="2026-08-12T07:00:00+00:00"),
        _study(
            "spl_b",
            exam_name="Studio: Psicologia",
            subject="Studio: Psicologia",
            exam_date="2026-08-12T07:00:00+00:00",
            updated_at="2026-08-06T18:53:34+00:00",
        ),
    ]
    _, _, _, _, cands = assemble_life_map(
        profile=None, study_plans=plans, travel_projects=[], today=__import__("datetime").date(2026, 8, 10)
    )
    cans, edges = resolve_candidates_deterministic(cands)
    assert len(cans) == 1
    assert cans[0].title == "Psicologia"
    assert any(e.source == "correlation" for e in edges)


def test_case_c_same_subject_different_dates_not_merged_by_correlation():
    """CASE C — same subject, different exam dates → NOT correlation-merged."""
    plans = [
        _study("spl_a", exam_name="Psicologia", exam_date="2026-08-12T07:00:00+00:00"),
        _study("spl_b", exam_name="Psicologia", exam_date="2026-08-13T07:00:00+00:00"),
    ]
    _, _, _, _, cands = assemble_life_map(
        profile=None, study_plans=plans, travel_projects=[], today=__import__("datetime").date(2026, 8, 10)
    )
    cans, edges = resolve_candidates_deterministic(cands)
    assert len(cans) == 2
    assert any(e.relation == "related" for e in edges)


def test_case_lineage_merges_despite_date_drift():
    """Same Home source_priority_id → structured SAME (freshest date wins)."""
    plans = [
        _study(
            "spl_old",
            exam_name="Psicologia",
            exam_date="2026-08-12T07:00:00+00:00",
            updated_at="2026-08-05T18:52:57+00:00",
            source_priority_id="hi_shared",
        ),
        _study(
            "spl_new",
            exam_name="Psicologia",
            exam_date="2026-08-13T07:00:00+00:00",
            updated_at="2026-08-06T12:47:25+00:00",
            source_priority_id="hi_shared",
        ),
    ]
    _, _, _, _, cands = assemble_life_map(
        profile=None, study_plans=plans, travel_projects=[], today=__import__("datetime").date(2026, 8, 10)
    )
    cans, edges = resolve_candidates_deterministic(cands)
    assert len(cans) == 1
    assert any(e.reason.startswith("shared_lineage") for e in edges)
    # Freshest wins temporal presentation
    assert "3 giorni" in (cans[0].temporal or "") or cans[0].identity.temporal_anchor == "2026-08-13"


def test_case_d_same_travel_project():
    projects = [
        {
            "id": "trp_1",
            "status": "active",
            "title": "Vacanza: Vibo Marina",
            "destination": "Vibo Marina",
            "start_date": "2026-08-09",
            "end_date": "2026-08-24",
            "phase": "during",
            "updated_at": "2026-08-06T10:00:00+00:00",
        }
    ]
    # two candidates same source_id
    _, _, _, _, cands = assemble_life_map(
        profile=None, study_plans=[], travel_projects=projects
    )
    assert len(cands) == 1
    dup = SituationCandidate(**{**cands[0].__dict__})
    dup.candidate_id = "travel:trp_1_alias"
    cans, _ = resolve_candidates_deterministic([cands[0], dup])
    assert len(cans) == 1


def test_case_e_similar_labels_unrelated_not_merged():
    plans = [
        _study("spl_a", exam_name="Psicologia", exam_date="2026-08-12T07:00:00+00:00"),
        _study("spl_b", exam_name="Psicologia sociale", exam_date="2026-08-20T07:00:00+00:00"),
    ]
    _, _, _, _, cands = assemble_life_map(
        profile=None, study_plans=plans, travel_projects=[], today=__import__("datetime").date(2026, 8, 10)
    )
    cans, edges = resolve_candidates_deterministic(cands)
    assert len(cans) == 2
    assert not any(e.relation == "same" for e in edges)


def test_case_f_gemini_same_allowed():
    a = SituationCandidate(
        candidate_id="study:a",
        kind="study",
        title="Psicologia",
        source_type="study_plan",
        source_id="a",
        entity_raw="Psicologia",
        temporal_anchor="2026-08-12",
        evidence_refs=["study:a"],
        updated_at="2026-08-06T10:00:00+00:00",
        href="/study-plan/a",
    )
    b = SituationCandidate(
        candidate_id="study:b",
        kind="study",
        title="Preparare Psicologia",
        source_type="study_plan",
        source_id="b",
        entity_raw="Preparare Psicologia",
        temporal_anchor="2026-08-12",
        evidence_refs=["study:b"],
        updated_at="2026-08-06T11:00:00+00:00",
        href="/study-plan/b",
    )
    # No deterministic same (entity keys don't intersect: preparare psicologia vs psicologia
    # — actually "preparare psicologia" doesn't share key with "psicologia" unless we add token overlap.
    # For CASE F use overlapping entity via presentation form)
    b.entity_raw = "Studio: Psicologia"
    det_cans, det_edges = resolve_candidates_deterministic([a, b])
    assert len(det_cans) == 1  # correlation already merges — use different anchor for gemini-only
    # Reset: different anchors so only gemini can merge — but structured blocks different temporal
    b.entity_raw = "Psicologia"
    b.temporal_anchor = "2026-08-12"
    a.temporal_anchor = "2026-08-12"
    # Force no correlation by changing b entity to non-intersecting then gemini says same with shared evidence
    b.entity_raw = "Esame di Psicologia"
    # entity_keys: "esame di psicologia" vs "psicologia" — no intersection; gemini can merge
    det_cans, det_edges = resolve_candidates_deterministic([a, b])
    assert len(det_cans) == 2
    gemini_edges = [
        ResolutionEdge(
            a="study:a",
            b="study:b",
            relation="same",
            source="gemini",
            evidence_refs=["study:a", "study:b"],
            reason="same exam",
        )
    ]
    cans = apply_gemini_same_edges([a, b], det_edges, gemini_edges)
    assert len(cans) == 1


def test_case_g_gemini_same_blocked_by_structured_temporal_conflict():
    a = SituationCandidate(
        candidate_id="study:a",
        kind="study",
        title="Psicologia",
        source_type="study_plan",
        source_id="a",
        entity_raw="Psicologia",
        temporal_anchor="2026-09-01",
        evidence_refs=["study:a"],
        updated_at="2026-08-01T00:00:00+00:00",
    )
    b = SituationCandidate(
        candidate_id="study:b",
        kind="study",
        title="Psicologia",
        source_type="study_plan",
        source_id="b",
        entity_raw="Psicologia",
        temporal_anchor="2026-11-01",
        evidence_refs=["study:b"],
        updated_at="2026-08-02T00:00:00+00:00",
    )
    _, det_edges = resolve_candidates_deterministic([a, b])
    assert any(e.relation == "related" for e in det_edges)
    gemini_edges = [
        ResolutionEdge(
            a="study:a",
            b="study:b",
            relation="same",
            source="gemini",
            evidence_refs=["study:a", "study:b"],
            reason="labels match",
        )
    ]
    cans = apply_gemini_same_edges([a, b], det_edges, gemini_edges)
    assert len(cans) == 2


def test_case_h_i_assemble_without_gemini():
    plans = [_study("spl_a", exam_name="Psicologia", exam_date="2026-08-12T07:00:00+00:00")]
    areas, sits, evid, fp, cands = assemble_life_map(
        profile=None,
        study_plans=plans,
        travel_projects=[],
        today=__import__("datetime").date(2026, 8, 10),
    )
    cans, _ = resolve_candidates_deterministic(cands)
    assert len(cans) == 1
    assert fp


def test_case_j_freshest_temporal_wins():
    plans = [
        _study(
            "spl_old",
            exam_name="Psicologia",
            exam_date="2026-08-12T07:00:00+00:00",
            updated_at="2026-08-05T10:00:00+00:00",
            source_priority_id="hi_x",
        ),
        _study(
            "spl_new",
            exam_name="Psicologia",
            exam_date="2026-08-13T07:00:00+00:00",
            updated_at="2026-08-06T12:00:00+00:00",
            source_priority_id="hi_x",
        ),
    ]
    _, _, _, _, cands = assemble_life_map(
        profile=None, study_plans=plans, travel_projects=[], today=__import__("datetime").date(2026, 8, 10)
    )
    cans, _ = resolve_candidates_deterministic(cands)
    assert len(cans) == 1
    assert cans[0].identity.temporal_anchor == "2026-08-13"


def test_case_k_related_not_same():
    plans = [
        _study("spl_a", exam_name="Psicologia", exam_date="2026-09-01T07:00:00+00:00"),
        _study("spl_b", exam_name="Psicologia", exam_date="2026-11-01T07:00:00+00:00"),
    ]
    _, _, _, _, cands = assemble_life_map(
        profile=None, study_plans=plans, travel_projects=[]
    )
    cans, edges = resolve_candidates_deterministic(cands)
    assert len(cans) == 2
    assert any(e.relation == "related" for e in edges)


def test_case_l_stable_id_order_invariant():
    refs = ["study_plan:b", "study_plan:a", "home_item:hi"]
    assert stable_canonical_id(refs, []) == stable_canonical_id(list(reversed(refs)), [])


def test_case_m_hallucinated_evidence_still_rejected():
    payload = GeminiLifeMapPayload(
        novel_situations=[
            {
                "label": "Viaggio a Parigi",
                "evidence_refs": ["travel:fake"],
                "confidence": "known",
            }
        ]
    )
    interp = validate_gemini_payload(
        payload,
        evidence=[EvidenceRef(id="study:1", kind="study_plan", label="x", summary="x")],
        known_area_ids=set(),
        known_situation_ids=set(),
    )
    assert interp.situations == []


def test_case_n_psicologia_screenshot_regression():
    """Real shape for user_0ea622447cfc Contesti screenshot.

    Semantic truth (runtime-verified Prompt 5.3.1):
    - spl_e725 + spl_65b56 share home_item lineage → SAME (stale Aug-12 vs freshest Aug-13)
    - spl_da0809 is title-polluted Studio: Psicologia same day as spl_65b56 → SAME
    - Pair e725×da0809 alone is RELATED (different dates) but transitive SAME via 65b56
    Expected Contesti: 1 Psicologia + 1 Vibo — not 3 study rows.
    """
    plans = [
        _study(
            "spl_65b56e1d26b546",
            exam_name="Psicologia",
            exam_date="2026-08-12T07:00:00+00:00",
            updated_at="2026-08-05T18:52:57+00:00",
            source_priority_id="hi_e56b48d7ae1a7ec2",
        ),
        _study(
            "spl_da0809cf760b49",
            exam_name="Studio: Psicologia",
            subject="Studio: Psicologia",
            exam_date="2026-08-12T07:00:00+00:00",
            updated_at="2026-08-05T18:53:34+00:00",
            source_priority_id="hi_75215ece18c1e39c",
        ),
        _study(
            "spl_e7253f82a9b14d",
            exam_name="Psicologia",
            exam_date="2026-08-13T07:00:00+00:00",
            updated_at="2026-08-06T12:47:25+00:00",
            source_priority_id="hi_e56b48d7ae1a7ec2",
        ),
    ]
    _, raw, _, _, cands = assemble_life_map(
        profile=None,
        study_plans=plans,
        travel_projects=[
            {
                "id": "trp_f4ffeebae74c44",
                "status": "active",
                "title": "Vacanza: Vibo Marina",
                "destination": "Vibo Marina",
                "start_date": "2026-08-09",
                "end_date": "2026-08-24",
                "phase": "during",
            }
        ],
        today=__import__("datetime").date(2026, 8, 10),
    )
    assert len(raw) == 4  # pre-identity
    cans, edges = resolve_candidates_deterministic(cands)
    study = [c for c in cans if c.kind == "study"]
    travel = [c for c in cans if c.kind == "travel"]
    assert len(study) == 1
    assert len(travel) == 1
    assert study[0].title == "Psicologia"
    assert "Studio:" not in study[0].title
    assert study[0].identity.temporal_anchor == "2026-08-13"
    member_set = set(study[0].member_ids)
    assert member_set == {
        "study:spl_65b56e1d26b546",
        "study:spl_da0809cf760b49",
        "study:spl_e7253f82a9b14d",
    }
    assert any(
        e.relation == "same"
        and "shared_lineage" in (e.reason or "")
        and {e.a, e.b}
        == {"study:spl_e7253f82a9b14d", "study:spl_65b56e1d26b546"}
        for e in edges
    )
    assert any(
        e.relation == "same"
        and e.reason == "entity_and_temporal_anchor"
        and {e.a, e.b}
        == {"study:spl_da0809cf760b49", "study:spl_65b56e1d26b546"}
        for e in edges
    )
    assert any(
        e.relation == "related"
        and e.reason == "same_entity_different_temporal"
        and {e.a, e.b}
        == {"study:spl_e7253f82a9b14d", "study:spl_da0809cf760b49"}
        for e in edges
    )
    rows = [canonical_to_presentation(c) for c in cans]
    assert len(rows) == 2


def test_runtime_stale_lineage_same_not_two_exams():
    """Prompt 5.3.1 — divergent exam_date + shared authoritative lineage → SAME.

    Without lineage, different dates would be RELATED only. Shared home_item
    proves stale version of the same exam object.
    """
    plans = [
        _study(
            "spl_old",
            exam_name="Psicologia",
            exam_date="2026-08-12T07:00:00+00:00",
            updated_at="2026-08-05T10:00:00+00:00",
            source_priority_id="hi_shared_exam",
        ),
        _study(
            "spl_new",
            exam_name="Psicologia",
            exam_date="2026-08-13T07:00:00+00:00",
            updated_at="2026-08-06T12:00:00+00:00",
            source_priority_id="hi_shared_exam",
        ),
    ]
    _, _, _, _, cands = assemble_life_map(
        profile=None, study_plans=plans, travel_projects=[], today=__import__("datetime").date(2026, 8, 10)
    )
    cans, edges = resolve_candidates_deterministic(cands)
    assert len(cans) == 1
    assert cans[0].identity.temporal_anchor == "2026-08-13"
    assert any(e.relation == "same" and "shared_lineage" in (e.reason or "") for e in edges)


def test_entity_keys_open_semantic():
    assert "psicologia" in entity_keys_for("Studio: Psicologia")
    assert "psicologia" in entity_keys_for("Psicologia")
    assert entity_keys_for("Studio: Psicologia") & entity_keys_for("Psicologia")


def test_prefer_clean_title():
    members = [
        SituationCandidate(
            candidate_id="a",
            kind="study",
            title="Studio: Psicologia",
            entity_raw="Studio: Psicologia",
            source_type="study_plan",
            source_id="a",
        ),
        SituationCandidate(
            candidate_id="b",
            kind="study",
            title="Psicologia",
            entity_raw="Psicologia",
            source_type="study_plan",
            source_id="b",
        ),
    ]
    assert prefer_presentation_title(members) == "Psicologia"
