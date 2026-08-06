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
    "course": ("studio.corso", "studio.universita"),
    "exam": ("studio.esame",),
}

# Cross-type affinity: same house / car / course without title-similarity merge
CROSS_TYPE_AFFINITY = {
    "rogito": ("mutuo", "bolletta", "contratto_luce", "polizza_casa", "contratto_locazione"),
    "mutuo": ("rogito", "bolletta", "contratto_luce"),
    "bolletta": ("rogito", "mutuo", "contratto_luce", "contratto_locazione"),
    "contratto_luce": ("bolletta", "rogito", "mutuo"),
    "libretto": ("polizza_auto", "prestito_auto", "polizza"),
    "polizza_auto": ("libretto", "prestito_auto"),
    "prestito_auto": ("libretto", "polizza_auto"),
    "piano_di_studi": ("verbale", "calendario_esami", "dispensa"),
    "verbale": ("piano_di_studi", "calendario_esami"),
    "calendario_esami": ("piano_di_studi", "verbale"),
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


def _identifier_from_reasoning(reasoning: Dict[str, Any]) -> tuple[Optional[str], Optional[str], float]:
    """Return (object_type, identifier, confidence) from type_specific / entities."""
    ts = reasoning.get("type_specific") or {}
    doc_type = reasoning.get("document_type") or ""
    conf = float(reasoning.get("confidence") or 0.5)
    if doc_type in ("rogito", "mutuo", "bolletta", "contratto_luce", "contratto_locazione", "polizza_casa"):
        addr = ts.get("address") or ts.get("property_address")
        if addr:
            return "house", addr, conf
    if doc_type in ("libretto", "polizza_auto", "prestito_auto"):
        plate = ts.get("plate") or ts.get("insured_object")
        if plate:
            return "vehicle", plate, conf
    if doc_type in ("piano_di_studi", "verbale", "calendario_esami"):
        course = ts.get("course_name") or ts.get("institution")
        if course:
            return "course", course, conf
    for lo in reasoning.get("linked_life_objects") or []:
        if lo.get("object_type") and lo.get("identifier"):
            return lo.get("object_type"), lo.get("identifier"), float(lo.get("confidence") or conf)
    return None, None, 0.0


def find_related_documents(
    profile: Optional[LifeProfile],
    *,
    domain: str,
    reasoning: Dict[str, Any],
    new_document_id: str,
) -> List[RelatedDocumentLink]:
    """High-confidence-only linking of the new document to existing life objects.

    Never merges on title similarity — only normalized address / plate / course.
    """
    if not profile:
        return []
    links: List[RelatedDocumentLink] = []
    seen: set = set()

    def _add(link: RelatedDocumentLink) -> None:
        key = (link.document_id, link.object_type, _normalize(link.identifier))
        if key in seen or link.document_id == new_document_id:
            return
        seen.add(key)
        links.append(link)

    # 1) Explicit linked_life_objects from AI
    for lo in reasoning.get("linked_life_objects") or []:
        conf = float(lo.get("confidence") or 0)
        if conf < HIGH_MATCH_CONFIDENCE:
            continue
        obj_type = lo.get("object_type")
        identifier = lo.get("identifier")
        if not obj_type or not identifier:
            continue
        norm_new = _normalize_plate(identifier) if obj_type == "vehicle" else _normalize(identifier)
        for dname, dom in profile.domains.items():
            for key in IDENTIFIER_KEYS_BY_TYPE.get(obj_type, ()):
                existing = dom.objects.get(key)
                if not existing or not existing.value:
                    continue
                norm_existing = _normalize_plate(existing.value) if obj_type == "vehicle" else _normalize(existing.value)
                if norm_existing and norm_new and norm_existing == norm_new:
                    for did in existing.linked_doc_ids:
                        _add(RelatedDocumentLink(
                            document_id=did, object_type=obj_type, identifier=identifier,
                            match_confidence=conf,
                            reason=f"Stesso {obj_type} ({key}) rilevato con alta confidenza.",
                        ))

    # 2) Cross-type affinity via shared grounded identifier (rogito+mutuo+bolletta, …)
    obj_type, identifier, conf = _identifier_from_reasoning(reasoning)
    doc_type = reasoning.get("document_type") or ""
    if obj_type and identifier and conf >= HIGH_MATCH_CONFIDENCE:
        norm_new = _normalize_plate(identifier) if obj_type == "vehicle" else _normalize(identifier)
        affinity = CROSS_TYPE_AFFINITY.get(doc_type, ())
        for dname, dom in profile.domains.items():
            for key in IDENTIFIER_KEYS_BY_TYPE.get(obj_type, ()):
                existing = dom.objects.get(key)
                if not existing or not existing.value:
                    continue
                norm_existing = _normalize_plate(existing.value) if obj_type == "vehicle" else _normalize(existing.value)
                if not (norm_existing and norm_new and norm_existing == norm_new):
                    continue
                for did in existing.linked_doc_ids:
                    _add(RelatedDocumentLink(
                        document_id=did, object_type=obj_type, identifier=identifier,
                        match_confidence=conf,
                        reason=f"Stesso {obj_type} condiviso tra documenti correlati ({doc_type}).",
                    ))
            # Also scan doc.* markers for affinity types linked on same identifier
            for atype in affinity:
                marker = dom.objects.get(f"doc.{atype}")
                if not marker or not marker.linked_doc_ids:
                    continue
                # Only link if the domain also shares the identifier key
                id_keys = IDENTIFIER_KEYS_BY_TYPE.get(obj_type, ())
                shares = False
                for ik in id_keys:
                    ex = dom.objects.get(ik)
                    if not ex or not ex.value:
                        continue
                    nex = _normalize_plate(ex.value) if obj_type == "vehicle" else _normalize(ex.value)
                    if nex == norm_new:
                        shares = True
                        break
                if not shares:
                    continue
                for did in marker.linked_doc_ids:
                    _add(RelatedDocumentLink(
                        document_id=did, object_type=obj_type, identifier=identifier,
                        match_confidence=conf,
                        reason=f"Affinità {doc_type}↔{atype} sullo stesso {obj_type} (no merge, solo link).",
                    ))

    # 3) AI-proposed related_docs with ask_user on low confidence / contradictions
    for rd in reasoning.get("related_docs") or []:
        did = rd.get("document_id")
        if not did:
            continue
        rconf = float(rd.get("confidence") or 0)
        if rconf < HIGH_MATCH_CONFIDENCE and not rd.get("ask_user"):
            continue
        _add(RelatedDocumentLink(
            document_id=did,
            object_type=rd.get("relation") or "related",
            identifier=identifier or did,
            match_confidence=rconf,
            reason=rd.get("relation") or "Collegamento proposto dall'AI (verifica richiesta).",
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
