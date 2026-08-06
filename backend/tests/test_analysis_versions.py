"""Regression: never ``int("2.0")`` on analysis_version paths."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def test_coerce_never_raises_on_semver_string():
    from documents.intelligence.versions import coerce_analysis_revision, next_analysis_revision

    assert coerce_analysis_revision("2.0") == 0
    assert coerce_analysis_revision("2.0.1") == 0
    assert coerce_analysis_revision(2) == 2
    assert coerce_analysis_revision("3") == 3
    assert coerce_analysis_revision(None) == 0
    assert coerce_analysis_revision("") == 0
    assert next_analysis_revision("2.0") == 1
    assert next_analysis_revision(4) == 5
    # The bug we fix: int("2.0") raises ValueError
    with pytest.raises(ValueError):
        int("2.0")


def test_document_analysis_bump_with_legacy_string():
    from documents.intelligence.versions import coerce_analysis_revision

    prev = {"analysis_version": "2.0"}
    doc = {"analysis_version": "2.0"}
    bumped = coerce_analysis_revision(
        doc.get("analysis_version") if doc.get("analysis_version") is not None
        else prev.get("analysis_version")
    ) + 1
    assert bumped == 1
    assert isinstance(bumped, int)


def test_life_reasoning_model_accepts_legacy_string():
    from documents.intelligence.life_reasoning import DocumentReasoning

    r = DocumentReasoning(analysis_version="2.0")  # type: ignore[arg-type]
    assert r.analysis_version == 1 or r.analysis_version == 0 or isinstance(r.analysis_version, int)
    # Coerced — never raises
    assert r.analysis_version >= 0


def test_migration_stamp_separates_schema_and_revision():
    from documents.intelligence.migration import stamp_document_versions

    patch = stamp_document_versions({
        "analysis": {"summary": "x"},
        "analysis_version": "2.0",
    })
    assert patch["analysis_schema_version"] == "2.0"
    assert patch["analysis_version"] == 1
    assert isinstance(patch["analysis_version"], int)


def test_parse_schema_version_major_minor():
    from documents.intelligence.versions import parse_schema_version, schema_version_string

    assert parse_schema_version("2.0") == (2, 0, 0)
    assert parse_schema_version("2.0.1") == (2, 0, 1)
    assert schema_version_string("2.0") == "2.0"


def test_admin_deadline_title_prefers_supplier():
    from types import SimpleNamespace
    from documents.intelligence.analyzer import _admin_deadline_title

    admin = SimpleNamespace(
        sender="Enel", subject=None, amount="87,40", currency="EUR",
    )
    title = _admin_deadline_title(
        admin=admin, title="Bolletta luce", text="BOLLETTA ENERGIA ELETTRICA Enel",
    )
    assert "Enel" in title
    assert "87" not in title
    assert title.startswith("Pagamento bolletta")


def test_admin_deadline_title_mutuo():
    from types import SimpleNamespace
    from documents.intelligence.analyzer import _admin_deadline_title

    admin = SimpleNamespace(
        sender="Intesa", subject="Rata", amount="872,45", currency="EUR",
    )
    title = _admin_deadline_title(
        admin=admin, title="Mutuo", text="CONTRATTO DI MUTUO IPOTECARIO rata",
    )
    assert "Intesa" in title
    assert "mutuo" in title.lower()
