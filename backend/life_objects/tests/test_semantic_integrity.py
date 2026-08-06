"""Unit tests — Semantic Validator, titles, registry, link states, Health 2.0."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ["LIFE_OBJECT_ENGINE_ENABLED"] = "1"
os.environ["LIFE_OBJECT_HOME_UI_ENABLED"] = "0"
os.environ["LIFE_OBJECT_GEMINI"] = "0"
os.environ.setdefault("JWT_SECRET", "test-secret-life-objects")

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def test_property_registry_aliases_to_canonical():
    from life_objects.property_registry import canonical_name, concept_present, map_properties

    assert canonical_name("dati_catastali") == "cadastral_data"
    assert canonical_name("catasto") == "cadastral_data"
    assert canonical_name("foglio_particella") == "cadastral_data"
    assert canonical_name("rata") == "monthly_installment"
    assert canonical_name("provider") == "utility_supplier"
    assert canonical_name("fornitore") == "utility_supplier"
    assert canonical_name("compagnia") == "insurance_company"

    mapped = map_properties({
        "dati_catastali": "Foglio 1",
        "rata": "800",
        "provider": "Enel",
        "pod": "IT001E123",
    })
    assert mapped["cadastral_data"] == "Foglio 1"
    assert mapped["monthly_installment"] == "800"
    assert mapped["utility_supplier"] == "Enel"
    assert mapped["pod"] == "IT001E123"

    assert concept_present(
        "cadastral",
        identity={"cadastral_data": "Foglio 1"},
        state={},
        properties={},
        identity_keys={},
    )
    assert concept_present(
        "cadastral",
        identity={},
        state={},
        properties={"catasto": "x"},
        identity_keys={},
    )
    assert concept_present(
        "cadastral",
        identity={},
        state={},
        properties={},
        identity_keys={"cadastral": "foglio1"},
    )


def test_title_generator_home_never_lavoro():
    from life_objects.title_generator import generate_canonical_title, is_incoherent_title

    assert is_incoherent_title("HOME", "Lavoro") is True
    assert is_incoherent_title("HOME", "Lavoro — ACME") is True
    title = generate_canonical_title(
        "HOME",
        identity={"address": "Via Roma 10, Milano"},
        identity_keys={"address_norm": "via roma 10 milano"},
    )
    assert "lavoro" not in title.lower()
    assert "casa" in title.lower()
    assert "roma" in title.lower() or "milano" in title.lower()

    bare = generate_canonical_title("HOME", identity={}, identity_keys={})
    assert bare.startswith("Casa")

    assert generate_canonical_title(
        "VEHICLE",
        identity={"brand": "Fiat", "model": "Panda", "plate": "AB123CD"},
    ).startswith("Fiat")
    assert generate_canonical_title("JOB", identity={"employer": "ACME"}) .startswith("Lavoro")
    assert "Università" in generate_canonical_title(
        "UNIVERSITY", identity={"institution": "Politecnico"},
    )
    assert generate_canonical_title(
        "TRAVEL", state={"destination": "Lisbona"},
    ).startswith("Viaggio")


def test_semantic_validator_blocks_home_lavoro():
    from life_objects.models import LifeObject, ObjectReasoningDecision
    from life_objects.semantic_validator import validate_before_persist, validate_decision_consultant

    obj = LifeObject(
        user_id="u1",
        type="HOME",
        title="Lavoro",
        identity={"address": "Via Roma 10, Milano"},
        identity_keys={"address_norm": "via roma 10 milano"},
        properties={"address": "Via Roma 10, Milano", "cadastral_data": "Foglio 12"},
    )
    decision = ObjectReasoningDecision(
        action="create",
        object_type="JOB",  # AI wrong
        title="Lavoro",
        properties_delta={"document_type": "rogito", "domain": "casa", "address": "Via Roma 10"},
        invented_facts=False,
    )
    decision = validate_decision_consultant(decision, document_type="rogito", domain="casa")
    assert decision.object_type == "HOME"
    assert (decision.title or "").lower() != "lavoro" or decision.title == ""

    vr = validate_before_persist(
        obj,
        decision=decision,
        document_type="rogito",
        domain="casa",
        properties_delta=decision.properties_delta,
        incoming_identity_keys={"address_norm": "via roma 10 milano", "cadastral": "foglio12"},
        ai_suggested_title="Lavoro",
        ai_suggested_type="JOB",
    )
    assert vr.object_type == "HOME"
    assert vr.title.lower() != "lavoro"
    assert "casa" in vr.title.lower()
    assert vr.allow_persist is True


def test_link_states_four_and_quiet_probable():
    from life_objects.link_states import (
        classify_link_state,
        is_quiet,
        is_user_facing,
        should_assimilate,
        should_propose_merge,
    )

    confirmed = classify_link_state(
        object_type="HOME",
        existing_keys={"address_norm": "via roma 10 milano", "cadastral": "f1"},
        incoming_keys={"address_norm": "via roma 10 milano"},
    )
    assert confirmed == "LINK_CONFIRMED"
    assert should_assimilate(confirmed) and is_quiet(confirmed)

    probable = classify_link_state(
        object_type="HOME",
        existing_keys={"address_norm": "via roma 10 milano"},
        incoming_keys={"address_norm": "via roma 10"},
    )
    # Soft address overlap is quiet (CONFIRMED or PROBABLE) — never user-facing
    assert probable in ("LINK_PROBABLE", "LINK_CONFIRMED")
    assert is_quiet(probable) and not is_user_facing(probable)
    assert should_assimilate(probable)

    conflict = classify_link_state(
        object_type="HOME",
        existing_keys={"cadastral": "aaa", "pod": "IT1"},
        incoming_keys={"cadastral": "bbb", "pod": "IT2"},
    )
    assert conflict == "REAL_CONFLICT"
    assert is_user_facing(conflict) and should_propose_merge(conflict)

    uncertain = classify_link_state(
        object_type="HOME",
        existing_keys={"address_norm": "via verdi"},
        incoming_keys={"pod": "IT999"},
    )
    assert uncertain in ("LINK_UNCERTAIN", "LINK_PROBABLE", "LINK_CONFIRMED")


def test_health_2_dimensions_never_perfect_with_open_conflict():
    from life_objects.enrichment import deterministic_health
    from life_objects.models import LifeObject

    obj = LifeObject(
        user_id="u1",
        type="HOME",
        title="Casa di Via Roma",
        identity={"address": "Via Roma 10", "cadastral_data": "Foglio 1"},
        identity_keys={"address_norm": "via roma 10", "cadastral": "foglio1"},
        state={"lender": "Banca", "monthly_installment": "800", "mortgage_assimilated": True,
               "utility_supplier": "Enel", "utility_assimilated": True},
        documents=["doc_rogito", "doc_mutuo", "doc_bolletta"],
        merge_proposals=[{
            "link_state": "REAL_CONFLICT",
            "conflict": True,
            "reason": "cadastral mismatch",
        }],
        ai_confidence=0.9,
    )
    h = deterministic_health(obj)
    assert h.identity_completeness is not None
    assert h.state_completeness is not None
    assert h.source_consistency is not None
    assert h.temporal_confidence is not None
    assert h.pending_conflicts is not None
    assert (h.overall_score or 0) < 1.0
    assert (h.pending_conflicts or 0) > 0


def test_knowledge_gaps_no_cadastral_or_mutuo_when_present():
    from life_objects.knowledge_gaps import build_gap_questions
    from life_objects.models import LifeObject

    obj = LifeObject(
        user_id="u1",
        type="HOME",
        title="Casa di Via Roma",
        identity={"address": "Via Roma 10", "cadastral_data": "Foglio 12 Particella 3"},
        identity_keys={"address_norm": "via roma 10", "cadastral": "foglio12"},
        state={
            "lender": "Banca X",
            "monthly_installment": "872",
            "mortgage_assimilated": True,
            "utility_supplier": "Enel",
        },
        documents=["doc_rogito", "doc_mutuo", "doc_bolletta"],
    )
    qs = build_gap_questions(obj)
    texts = " ".join(q.question.lower() for q in qs)
    assert "catastale" not in texts
    assert "hai un mutuo" not in texts
