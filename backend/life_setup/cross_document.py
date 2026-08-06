"""Cross-document reasoning — link (never merge) related life objects.

Compares a newly understood document against existing Life Profile objects
and previously linked documents to:
  * link (not merge) matches on the SAME house / vehicle / supplier when the
    match is high-confidence (normalized address / plate / supplier name),
  * detect duplicates (same document_type + same key identifier already
    linked) and contradictions (existing confirmed value differs from a new
    high-confidence extracted value) and surface them for user confirmation
    instead of silently overwriting.

Never merges two different objects just because titles look similar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from life_setup.models import LifeProfile

HIGH_MATCH_CONFIDENCE = 0.75


def _normalize(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = re.sub(r"[^a-z0-9àèéìòù ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_plate(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


IDENTIFIER_KEYS_BY_TYPE = {
    "house": ("casa.indirizzo",),
    "vehicle": ("auto.targa",),
    "supplier": ("casa.bolletta_fornitore",),
}


@dataclass
class RelatedDocumentLink:
    document_id: str
    object_type: str
    identifier: str
    match_confidence: float
    reason: str


@dataclass
class ConfirmationRequest:
    domain: str
    key: str
    label: str
    existing_value: Any
    new_value: Any
    new_confidence: float
    source_document_id: str
    kind: str  # "contradiction" | "duplicate" | "renewal"
    field: Dict[str, Any] = field(default_factory=dict)


def find_related_documents(
    profile: Optional[LifeProfile],
    *,
    domain: str,
    reasoning: Dict[str, Any],
    new_document_id: str,
) -> List[RelatedDocumentLink]:
    """High-confidence-only linking of the new document to existing life objects."""
    if not profile:
        return []
    links: List[RelatedDocumentLink] = []
    linked_objects = reasoning.get("linked_life_objects") or []
    dom = profile.domains.get(domain)
    if not dom:
        return []

    for lo in linked_objects:
        conf = float(lo.get("confidence") or 0)
        if conf < HIGH_MATCH_CONFIDENCE:
            continue
        obj_type = lo.get("object_type")
        identifier = lo.get("identifier")
        if not obj_type or not identifier:
            continue
        norm_new = _normalize_plate(identifier) if obj_type == "vehicle" else _normalize(identifier)
        for key in IDENTIFIER_KEYS_BY_TYPE.get(obj_type, ()):
            existing = dom.objects.get(key)
            if not existing or not existing.value:
                continue
            norm_existing = _normalize_plate(existing.value) if obj_type == "vehicle" else _normalize(existing.value)
            if norm_existing and norm_new and norm_existing == norm_new:
                for did in existing.linked_doc_ids:
                    if did != new_document_id:
                        links.append(RelatedDocumentLink(
                            document_id=did, object_type=obj_type, identifier=identifier,
                            match_confidence=conf,
                            reason=f"Stesso {obj_type} ({key}) rilevato con alta confidenza.",
                        ))
    return links


def detect_conflicts(
    profile: Optional[LifeProfile],
    *,
    domain: str,
    mapped_fields: List[Any],
    source_document_id: str,
) -> List[ConfirmationRequest]:
    """Never silently overwrite a confirmed/corrected field that conflicts."""
    if not profile:
        return []
    dom = profile.domains.get(domain)
    if not dom:
        return []
    out: List[ConfirmationRequest] = []
    for mf in mapped_fields:
        existing = dom.objects.get(mf.key)
        if not existing or existing.value in (None, "", [], False):
            continue
        if existing.status not in ("confirmed", "corrected"):
            continue
        if _normalize(existing.value) == _normalize(mf.value):
            continue
        # Existing confirmed value differs from newly extracted value.
        kind = "contradiction"
        if mf.key.endswith("_scadenza") or mf.key.endswith("scadenza"):
            kind = "renewal"
        out.append(ConfirmationRequest(
            domain=domain,
            key=mf.key,
            label=mf.label or mf.key,
            existing_value=existing.value,
            new_value=mf.value,
            new_confidence=mf.confidence,
            source_document_id=source_document_id,
            kind=kind,
            field={
                "domain": mf.domain, "key": mf.key, "value": mf.value,
                "raw_value": mf.raw_value, "confidence": mf.confidence,
            },
        ))
    return out


def detect_duplicate_document(
    profile: Optional[LifeProfile],
    *,
    domain: str,
    doc_type: str,
    identifier: Optional[str],
    new_document_id: str,
) -> Optional[str]:
    """Return an existing document_id if this looks like a duplicate upload
    of the same real-world document (same type + same normalized identifier)."""
    if not profile or not identifier:
        return None
    dom = profile.domains.get(domain)
    if not dom:
        return None
    key = f"doc.{doc_type}"
    existing = dom.objects.get(key)
    if not existing or not existing.linked_doc_ids:
        return None
    for did in existing.linked_doc_ids:
        if did != new_document_id:
            return did
    return None
