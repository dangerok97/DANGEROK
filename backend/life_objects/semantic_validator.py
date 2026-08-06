"""Semantic Validator — ALWAYS runs before Life Object persist.

Gemini is consultant; backend is final authority on type, title, merge, fields.
Fixes incoherence (e.g. HOME + title «Lavoro» → Casa / Casa di Via Roma).
Never invents facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from life_objects.assimilation import (
    assimilate_document_into_object,
    document_assimilates_into_home,
)
from life_objects.identity_state import apply_identity_state_migration
from life_objects.link_states import (
    LinkState,
    classify_link_state,
    should_assimilate,
    should_propose_merge,
)
from life_objects.models import LifeObject, ObjectReasoningDecision
from life_objects.property_registry import map_properties, merge_mapped_into
from life_objects.provenance import ensure_provenance_fields
from life_objects.title_generator import generate_canonical_title, is_incoherent_title
from life_objects.types import DOC_TYPE_TO_OBJECT, DOMAIN_TO_OBJECT, LIFE_OBJECT_TYPES


@dataclass
class ValidationResult:
    """Outcome of semantic validation before persist."""

    obj: LifeObject
    object_type: str
    title: str
    link_state: LinkState = "LINK_CONFIRMED"
    assimilation: Dict[str, Any] = field(default_factory=dict)
    corrections: List[str] = field(default_factory=list)
    rejected_inventions: List[str] = field(default_factory=list)
    allow_persist: bool = True
    user_facing_conflict: bool = False


def _coerce_type(raw: Any, *, document_type: str = "", domain: str = "") -> str:
    s = str(raw or "").strip().upper()
    if s in LIFE_OBJECT_TYPES and s != "CUSTOM":
        return s
    hinted = DOC_TYPE_TO_OBJECT.get(str(document_type or "").lower()) or DOMAIN_TO_OBJECT.get(
        str(domain or "").lower()
    )
    if hinted:
        return hinted
    if s in LIFE_OBJECT_TYPES:
        return s
    return "CUSTOM"


def _reject_invented(decision: Optional[ObjectReasoningDecision]) -> List[str]:
    rejected: List[str] = []
    if decision is None:
        return rejected
    if getattr(decision, "invented_facts", False):
        rejected.append("decision.invented_facts=true")
    # Empty title from AI is fine — generator fills it
    return rejected


def validate_before_persist(
    obj: LifeObject,
    *,
    decision: Optional[ObjectReasoningDecision] = None,
    document_type: str = "",
    domain: str = "",
    document_id: Optional[str] = None,
    existing_match: Optional[LifeObject] = None,
    incoming_identity_keys: Optional[Dict[str, str]] = None,
    properties_delta: Optional[Dict[str, Any]] = None,
    existing_titles: Optional[List[str]] = None,
    ai_suggested_title: Optional[str] = None,
    ai_suggested_type: Optional[str] = None,
) -> ValidationResult:
    """Authoritative validation. Mutates a copy-like path on `obj` in place.

    Pipeline position: Document → OCR → Document AI → Life Object AI → **here** → Canonical Object.
    """
    corrections: List[str] = []
    rejected = _reject_invented(decision)

    # --- Type authority ---
    doc_type = document_type or (
        (properties_delta or {}).get("document_type")
        or (obj.properties or {}).get("document_type")
        or ""
    )
    doc_type = str(doc_type or "").lower()
    dom = domain or str((properties_delta or {}).get("domain") or (obj.properties or {}).get("domain") or "")

    backend_type = _coerce_type(
        ai_suggested_type or (decision.object_type if decision else None) or obj.type,
        document_type=doc_type,
        domain=dom,
    )
    # Document type mapping wins over AI for known home docs
    mapped_type = DOC_TYPE_TO_OBJECT.get(doc_type)
    if mapped_type:
        if backend_type != mapped_type:
            corrections.append(f"type:{backend_type}->{mapped_type} (doc={doc_type})")
        backend_type = mapped_type

    # Never persist HOME labeled as job from AI type confusion when doc is home-domain
    if backend_type == "JOB" and (
        doc_type in ("rogito", "mutuo", "bolletta", "polizza_casa", "contratto_locazione")
        or str(dom).lower() == "casa"
    ):
        corrections.append("type:JOB->HOME (home document)")
        backend_type = "HOME"

    obj.type = backend_type  # type: ignore[assignment]

    # --- Map properties through registry ---
    delta = dict(properties_delta or {})
    if decision and decision.properties_delta:
        for k, v in decision.properties_delta.items():
            if k not in delta and v not in (None, "", [], {}):
                delta[k] = v
    mapped = map_properties(delta)
    id_out, st_out, props_out = merge_mapped_into(
        identity=dict(obj.identity or {}),
        state=dict(obj.state or {}),
        properties=dict(obj.properties or {}),
        delta=mapped,
    )
    obj.identity = id_out
    obj.state = st_out
    obj.properties = props_out
    apply_identity_state_migration(obj)

    # --- Identity keys (backend merges, no AI inventions) ---
    ik = dict(obj.identity_keys or {})
    for k, v in (incoming_identity_keys or {}).items():
        if v and (k not in ik or not ik.get(k)):
            ik[k] = v
        elif v:
            ik[k] = ik.get(k) or v
    if decision and decision.identity_keys:
        for k, v in decision.identity_keys.items():
            if v and not ik.get(k):
                ik[k] = v
    obj.identity_keys = ik

    # --- Link state vs existing match ---
    link_state: LinkState = "LINK_CONFIRMED"
    if existing_match is not None:
        link_state = classify_link_state(
            object_type=backend_type,
            existing_keys=dict(existing_match.identity_keys or {}),
            incoming_keys=dict(ik),
        )
    elif not ik and backend_type in ("HOME", "VEHICLE"):
        link_state = "LINK_UNCERTAIN"

    # --- Assimilation for clear same-object updates ---
    assimilation: Dict[str, Any] = {}
    if (
        existing_match is not None
        and should_assimilate(link_state)
        and (document_assimilates_into_home(doc_type) or backend_type == existing_match.type)
    ):
        assimilation = assimilate_document_into_object(
            obj,
            document_type=doc_type,
            properties_delta=mapped,
            document_id=document_id,
            link_state=link_state,
        )
        if assimilation.get("assimilated"):
            corrections.append(f"assimilated:{assimilation.get('kind')}")

    # --- Canonical title (NEVER AI text as final) ---
    ai_title = (ai_suggested_title or (decision.title if decision else "") or obj.title or "").strip()
    if is_incoherent_title(backend_type, ai_title):
        corrections.append(f"title_incoherent:{ai_title!r}")
        ai_title = ""  # discard

    # HOME must never persist as Lavoro
    if backend_type == "HOME" and ai_title.strip().lower() in ("lavoro", "job", "work"):
        corrections.append("blocked:HOME+Lavoro")
        ai_title = ""

    title = generate_canonical_title(
        backend_type,
        identity=obj.identity,
        state=obj.state,
        properties=obj.properties,
        identity_keys=obj.identity_keys,
        existing_titles=existing_titles,
    )
    # If generator produced generic and previous coherent title was better for JOB/etc. — keep generator
    if title:
        if obj.title != title:
            corrections.append(f"title:{obj.title!r}->{title!r}")
        obj.title = title

    # Hard invariant
    if obj.type == "HOME" and (obj.title or "").strip().lower() in ("lavoro", "job", "work"):
        obj.title = generate_canonical_title(
            "HOME",
            identity=obj.identity,
            state=obj.state,
            properties=obj.properties,
            identity_keys=obj.identity_keys,
        )
        corrections.append("forced_home_title")

    if obj.type == "HOME" and is_incoherent_title("HOME", obj.title):
        obj.title = generate_canonical_title(
            "HOME",
            identity=obj.identity,
            state=obj.state,
            properties=obj.properties,
            identity_keys=obj.identity_keys,
        )
        corrections.append("repaired_home_title")

    # --- Conflict handling ---
    user_facing = False
    allow = True
    if should_propose_merge(link_state):
        user_facing = True
        # Persist is still allowed on the primary object with conflict recorded
        allow = True
        corrections.append("REAL_CONFLICT")

    # Reject invented facts from decision — strip suspicious empty confidence boosts
    if rejected and decision is not None:
        decision.invented_facts = False  # force flag down; we already rejected content
        corrections.append("stripped_invented_facts_flag")

    ensure_provenance_fields(obj)
    apply_identity_state_migration(obj)
    obj.touch()

    return ValidationResult(
        obj=obj,
        object_type=backend_type,
        title=obj.title,
        link_state=link_state,
        assimilation=assimilation,
        corrections=corrections,
        rejected_inventions=rejected,
        allow_persist=allow,
        user_facing_conflict=user_facing,
    )


def validate_decision_consultant(
    decision: ObjectReasoningDecision,
    *,
    document_type: str = "",
    domain: str = "",
) -> ObjectReasoningDecision:
    """Downgrade AI decision to consultant suggestions; backend overrides type/title."""
    doc_type = str(document_type or (decision.properties_delta or {}).get("document_type") or "").lower()
    dom = str(domain or (decision.properties_delta or {}).get("domain") or "")
    final_type = _coerce_type(decision.object_type, document_type=doc_type, domain=dom)
    mapped = DOC_TYPE_TO_OBJECT.get(doc_type)
    if mapped:
        final_type = mapped
    decision.object_type = final_type  # type: ignore[assignment]

    # Map properties
    decision.properties_delta = map_properties(decision.properties_delta or {})

    # Title becomes suggestion only — clear if incoherent; generator applied at persist
    if is_incoherent_title(final_type, decision.title or ""):
        decision.title = ""
    if final_type == "HOME" and (decision.title or "").strip().lower() in ("lavoro", "job", "work"):
        decision.title = ""

    if decision.invented_facts:
        decision.invented_facts = False
        decision.confidence = min(float(decision.confidence or 0.4), 0.3)

    # AI may propose merge; backend classifies link state later
    return decision
