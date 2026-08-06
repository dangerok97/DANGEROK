"""Non-destructive Documents V2 field stamping."""
from __future__ import annotations

from typing import Any

from documents.intelligence.versions import (
    ANALYSIS_SCHEMA_VERSION,
    DOCUMENT_SCHEMA_VERSION,
    PROCESSING_VERSION,
    coerce_analysis_revision,
    is_semantic_version_string,
)

# Back-compat aliases (schema shape — semantic strings, never int()-parsed)
ANALYSIS_VERSION = ANALYSIS_SCHEMA_VERSION


def stamp_document_versions(doc: dict[str, Any]) -> dict[str, Any]:
    """Return $set patch for missing V2 version fields. Never clears data.

    Separates:
    * ``document_schema_version`` / ``analysis_schema_version`` — semantic strings
    * ``analysis_version`` — integer revision counter (legacy ``"2.0"`` coerced)
    """
    patch: dict[str, Any] = {}
    if not doc.get("document_schema_version"):
        patch["document_schema_version"] = DOCUMENT_SCHEMA_VERSION
        patch["legacy_data_preserved"] = True
    if not doc.get("analysis_schema_version"):
        # Migrate legacy analysis_version="2.0" → schema field + int revision
        legacy = doc.get("analysis_version")
        if is_semantic_version_string(legacy):
            patch["analysis_schema_version"] = str(legacy).strip()
            patch["analysis_version"] = 1
        elif doc.get("analysis"):
            patch["analysis_schema_version"] = ANALYSIS_SCHEMA_VERSION
            if doc.get("analysis_version") is None:
                patch["analysis_version"] = 1
    elif doc.get("analysis") and doc.get("analysis_version") is None:
        patch["analysis_version"] = 1
    # Heal in-place if someone still has a dotted string in analysis_version
    elif is_semantic_version_string(doc.get("analysis_version")):
        patch["analysis_schema_version"] = str(doc["analysis_version"]).strip()
        patch["analysis_version"] = 1
    if not doc.get("processing_version"):
        patch["processing_version"] = doc.get("pipeline_version") or PROCESSING_VERSION
    return patch


def with_versions(doc: dict[str, Any]) -> dict[str, Any]:
    """In-memory view with versions filled (does not persist)."""
    out = dict(doc)
    patch = stamp_document_versions(out)
    out.update(patch)
    # Ensure analysis_version is always a safe int in the view
    if out.get("analysis") is not None:
        out["analysis_version"] = coerce_analysis_revision(out.get("analysis_version")) or 1
        out.setdefault("analysis_schema_version", ANALYSIS_SCHEMA_VERSION)
    return out
