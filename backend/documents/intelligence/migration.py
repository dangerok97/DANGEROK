"""Non-destructive Documents V2 field stamping."""
from __future__ import annotations

from typing import Any

DOCUMENT_SCHEMA_VERSION = "2.0"
ANALYSIS_VERSION = "2.0"
PROCESSING_VERSION = "intel-docs-2.0"


def stamp_document_versions(doc: dict[str, Any]) -> dict[str, Any]:
    """Return $set patch for missing V2 version fields. Never clears data."""
    patch: dict[str, Any] = {}
    if not doc.get("document_schema_version"):
        patch["document_schema_version"] = DOCUMENT_SCHEMA_VERSION
        patch["legacy_data_preserved"] = True
    if doc.get("analysis") and not doc.get("analysis_version"):
        patch["analysis_version"] = ANALYSIS_VERSION
    if not doc.get("processing_version"):
        # Prefer existing pipeline_version if present
        patch["processing_version"] = doc.get("pipeline_version") or PROCESSING_VERSION
    return patch


def with_versions(doc: dict[str, Any]) -> dict[str, Any]:
    """In-memory view with versions filled (does not persist)."""
    out = dict(doc)
    if not out.get("document_schema_version"):
        out["document_schema_version"] = DOCUMENT_SCHEMA_VERSION
        out["legacy_data_preserved"] = out.get("legacy_data_preserved", True)
    if out.get("analysis") and not out.get("analysis_version"):
        out["analysis_version"] = ANALYSIS_VERSION
    if not out.get("processing_version"):
        out["processing_version"] = out.get("pipeline_version") or PROCESSING_VERSION
    return out
