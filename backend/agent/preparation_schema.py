"""Output types for the two existing source-grounded preparation calls.

These are native provider schemas, not truth or authority checks. They use
the shared JSON Schema subset; the preparation boundary still owns the
4000-character limit, citation count, source freshness and negative verdict.
Each call receives only the evidence IDs actually retained in its payload.
"""
from typing import Any, Iterable


def _refs(evidence_ids: list[str]) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string", "enum": list(evidence_ids)}}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def draft_schema(evidence_ids: Iterable[str]) -> dict[str, Any]:
    ids = list(evidence_ids)
    if not ids:
        raise ValueError("A preparation schema requires supplied evidence IDs")
    return _object({
        "content": {"type": "string", "description":
                    "The concise complete useful draft in Italian, at most 4000 characters; state each finding "
                    "once, with supported calculations and limits. Empty when unsupported."},
        "evidence_ids": _refs(ids),
    })


def audit_schema(evidence_ids: Iterable[str]) -> dict[str, Any]:
    ids = list(evidence_ids)
    if not ids:
        raise ValueError("A preparation schema requires supplied evidence IDs")
    return _object({
        "claim_review": {"type": "array", "description":
                         "1–12 brief checks covering material clauses, calculations, and every material change or deletion.",
                         "items": _object({
                             "claim": {"type": "string"},
                             "evidence_ids": _refs(ids),
                             "source_quotes": {"type": "array", "description":
                                 "At most 3 verbatim input premises; stated or derived checks require at least one. "
                                 "For a calculation quote its operands and conditions; its result need not be in the source.",
                                 "items": _object({
                                     "evidence_id": {"type": "string", "enum": list(ids)},
                                     "quote": {"type": "string", "description":
                                         "1–280 characters copied exactly from this evidence row's claim, not its metadata."},
                                 })},
                             "premises": {"type": "string", "description":
                                 "Short supporting premises and missing assumptions; for a calculation state its operation and result."},
                             "support": {"type": "string", "enum": ["stated", "derived", "conditional", "unsupported"]},
                             "correction": {"type": "string"},
                         })},
        "verified": {"type": "boolean"},
        "content": {"type": "string", "description":
                    "The concise corrected complete draft in Italian, at most 4000 characters. Retain supported "
                    "calculations, comparisons and limits; empty for a negative verdict."},
        "evidence_ids": _refs(ids),
        "reason": {"type": "string", "description": "A short reason for the positive or negative verdict."},
    })
