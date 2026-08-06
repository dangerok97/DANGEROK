"""Life Object reasoner — Gemini via Provider Manager + deterministic fallback.

Never invents facts. Output always validated ObjectReasoningDecision (Pydantic).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from life_objects.deduplication import (
    extract_identity_keys_from_reasoning,
    normalize_text,
)
from life_objects.models import ObjectReasoningDecision
from life_objects.types import DOC_TYPE_TO_OBJECT, DOMAIN_TO_OBJECT

logger = logging.getLogger("ora.life_objects.reasoner")

REASONING_VERSION = "life-object-reasoner-1.0"


def life_object_gemini_enabled() -> bool:
    raw = (os.environ.get("LIFE_OBJECT_GEMINI") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _default_title(object_type: str, keys: Dict[str, str], reasoning: Dict[str, Any]) -> str:
    """Suggestion only — Semantic Validator regenerates canonical title before persist."""
    from life_objects.property_registry import map_properties
    from life_objects.title_generator import generate_canonical_title

    ts = reasoning.get("type_specific") if isinstance(reasoning.get("type_specific"), dict) else {}
    mapped = map_properties(ts)
    return generate_canonical_title(
        object_type,
        identity=mapped,
        state=mapped,
        properties=mapped,
        identity_keys=keys,
    )


def deterministic_reason_from_document(
    *,
    reasoning: Dict[str, Any],
    existing_candidates: Optional[List[Dict[str, Any]]] = None,
) -> ObjectReasoningDecision:
    """Rule-based decision — used when Gemini absent or invalid."""
    doc_type = str(reasoning.get("document_type") or "altro")
    domain = str(reasoning.get("domain") or "generico")
    object_type = DOC_TYPE_TO_OBJECT.get(doc_type) or DOMAIN_TO_OBJECT.get(domain) or "CUSTOM"

    # Bolletta may also create/link UTILITY but primary link is HOME when address present
    keys = extract_identity_keys_from_reasoning(object_type=object_type, reasoning=reasoning)

    # If HOME without any strong key → uncertain (do not invent Casa 2)
    strong_present = bool(keys)
    candidates = existing_candidates or []

    matched_id = None
    action = "create"
    merge_with = None

    if candidates:
        # Prefer candidate sharing any identity key
        for c in candidates:
            cik = c.get("identity_keys") or {}
            if any(cik.get(k) == v for k, v in keys.items() if v):
                matched_id = c.get("id")
                action = "update"
                break
        if not matched_id and strong_present and len(candidates) == 1:
            # Single HOME/VEHICLE of that type with overlapping soft key?
            only = candidates[0]
            if only.get("type") == object_type and keys.get("address_norm"):
                old_addr = (only.get("identity_keys") or {}).get("address_norm") or ""
                if old_addr and (
                    old_addr in keys["address_norm"] or keys["address_norm"] in old_addr
                ):
                    matched_id = only.get("id")
                    action = "update"
        if not matched_id and len(candidates) > 1 and strong_present:
            action = "propose_merge"
            merge_with = candidates[0].get("id")
            matched_id = candidates[0].get("id")

    if not strong_present and object_type in ("HOME", "VEHICLE"):
        # Without identity — do not create a second silent object if one already exists
        same_type = [c for c in candidates if c.get("type") == object_type]
        if same_type:
            action = "propose_merge"
            matched_id = same_type[0].get("id")
            merge_with = matched_id
        else:
            action = "uncertain"

    title = _default_title(object_type, keys, reasoning)
    summary = str(reasoning.get("summary") or reasoning.get("context") or "")[:500]

    improves: List[str] = []
    worsens: List[str] = []
    if doc_type in ("rogito", "libretto", "piano_di_studi"):
        improves.append("identity_strengthened")
    if doc_type == "bolletta":
        improves.append("utility_visibility")
        if reasoning.get("criticality") in ("high", "critical"):
            worsens.append("payment_pressure")
    if doc_type == "mutuo":
        improves.append("mortgage_linked")

    next_q = None
    next_why = ""
    if object_type == "HOME" and not keys.get("address_norm"):
        next_q = "Qual è l'indirizzo completo di questa casa?"
        next_why = "Serve un indirizzo stabile per non creare una seconda Casa."
    elif object_type == "VEHICLE" and not keys.get("plate"):
        next_q = "Qual è la targa del veicolo?"
        next_why = "La targa è la chiave primaria per unificare libretto e polizza."
    elif action == "propose_merge":
        next_q = "Queste informazioni appartengono allo stesso oggetto di vita?"
        next_why = "Ho trovato indizi contrastanti: meglio confermare prima di unire."

    props: Dict[str, Any] = {}
    ts = reasoning.get("type_specific") if isinstance(reasoning.get("type_specific"), dict) else {}
    for k, v in ts.items():
        if v not in (None, "", [], {}):
            props[k] = v
    props["document_type"] = doc_type
    props["domain"] = domain

    conf = float(reasoning.get("confidence") or 0.4)
    if action == "uncertain":
        conf = min(conf, 0.35)

    suggested = []
    for a in (reasoning.get("recommended_actions") or [])[:5]:
        if isinstance(a, dict) and a.get("title"):
            suggested.append(str(a["title"]))
        elif isinstance(a, str):
            suggested.append(a)

    from life_objects.semantic_validator import validate_decision_consultant

    decision = ObjectReasoningDecision(
        action=action,  # type: ignore[arg-type]
        object_type=object_type,  # type: ignore[arg-type]
        object_id=matched_id,
        merge_with_id=merge_with,
        title=title,
        summary=summary,
        identity_keys=keys,
        properties_delta=props,
        improves=improves,
        worsens=worsens,
        next_question=next_q,
        next_question_why=next_why,
        suggested_actions=suggested,
        confidence=conf,
        reason_summary=str(reasoning.get("reason_summary") or "Deterministic life-object mapping")[:300],
        invented_facts=False,
        ai_used=False,
        provider="local-deterministic",
        model="local-deterministic",
    )
    return validate_decision_consultant(decision, document_type=doc_type, domain=domain)


async def reason_from_document(
    *,
    reasoning: Dict[str, Any],
    existing_candidates: Optional[List[Dict[str, Any]]] = None,
    user_preference: Optional[str] = None,
) -> ObjectReasoningDecision:
    """Prefer Gemini structured JSON; fall back deterministically."""
    fallback = deterministic_reason_from_document(
        reasoning=reasoning, existing_candidates=existing_candidates,
    )
    if not life_object_gemini_enabled():
        return fallback

    try:
        from llm.structured import chat_json
        from llm import llm_status
    except Exception as e:
        logger.info("life_object reasoner import soft-fail: %s", e)
        return fallback

    status = llm_status()
    if not status.get("configured"):
        return fallback

    candidates = existing_candidates or []
    payload = {
        "task": (
            "Decide which Life Object this document updates. "
            "Never invent facts not present in the document. "
            "Never match on title alone — use address/cadastral/POD/PDR/plate/VIN/lender+property/coords. "
            "If conflict between two homes/vehicles, use action=propose_merge. "
            "If identity is too weak, use action=uncertain (do not create Casa 2)."
        ),
        "document_reasoning": {
            "document_type": reasoning.get("document_type"),
            "domain": reasoning.get("domain"),
            "title": reasoning.get("title"),
            "summary": reasoning.get("summary"),
            "entities": (reasoning.get("entities") or [])[:20],
            "type_specific": reasoning.get("type_specific") or {},
            "linked_life_objects": reasoning.get("linked_life_objects") or [],
            "confidence": reasoning.get("confidence"),
        },
        "existing_candidates": [
            {
                "id": c.get("id"),
                "type": c.get("type"),
                "title": c.get("title"),
                "identity_keys": c.get("identity_keys") or {},
            }
            for c in candidates[:10]
        ],
        "allowed_types": list(DOC_TYPE_TO_OBJECT.values())
        + ["TRAVEL", "FAMILY_MEMBER", "CUSTOM", "UTILITY", "MORTGAGE", "INSURANCE", "JOB", "COURSE"],
        "allowed_actions": ["create", "update", "propose_merge", "skip", "uncertain"],
    }

    system = (
        "Sei il Life Object Engine di ORA. Rispondi SOLO con JSON valido "
        "conforme allo schema ObjectReasoningDecision. Non inventare fatti. "
        "invented_facts deve essere sempre false. "
        "Se non sei sicuro dell'identità, action=uncertain o propose_merge."
    )
    import json

    try:
        parsed, meta = await chat_json(
            system=system,
            user=json.dumps(payload, ensure_ascii=False)[:12000],
            model_cls=ObjectReasoningDecision,
            session_id=f"ora-life-object-{reasoning.get('document_id') or 'doc'}",
            user_preference=user_preference,
        )
        from life_objects.semantic_validator import validate_decision_consultant

        if parsed.invented_facts:
            logger.info("rejecting AI decision: invented_facts=true")
            return fallback
        # Merge AI decision with deterministic identity keys (never drop strong keys)
        det_keys = fallback.identity_keys or {}
        ai_keys = dict(parsed.identity_keys or {})
        for k, v in det_keys.items():
            if v and not ai_keys.get(k):
                ai_keys[k] = v
        parsed.identity_keys = ai_keys
        if not parsed.title:
            parsed.title = fallback.title
        if not parsed.object_type or parsed.object_type == "CUSTOM":
            parsed.object_type = fallback.object_type
        # Prefer deterministic match id when AI omitted it but keys match
        if not parsed.object_id and fallback.object_id and parsed.action in ("update", "propose_merge"):
            parsed.object_id = fallback.object_id
        parsed.ai_used = True
        parsed.provider = str(meta.get("provider") or "gemini")
        parsed.model = str(meta.get("model") or "")
        # Fill properties from deterministic if empty
        if not parsed.properties_delta:
            parsed.properties_delta = fallback.properties_delta
        # Gemini = consultant; backend coerces type/title/properties
        return validate_decision_consultant(
            parsed,
            document_type=str(reasoning.get("document_type") or ""),
            domain=str(reasoning.get("domain") or ""),
        )
    except Exception as e:
        logger.info("life_object Gemini soft-fail → deterministic: %s", type(e).__name__)
        return fallback


def reason_from_travel(project: Dict[str, Any]) -> ObjectReasoningDecision:
    from life_objects.deduplication import extract_identity_keys_from_travel

    keys = extract_identity_keys_from_travel(project)
    dest = project.get("destination") or project.get("title") or "Viaggio"
    return ObjectReasoningDecision(
        action="create",
        object_type="TRAVEL",
        title=f"Viaggio — {dest}",
        summary=str(project.get("summary") or project.get("notes") or "")[:400],
        identity_keys=keys,
        properties_delta={
            "destination": project.get("destination"),
            "start_date": project.get("start_date") or project.get("departure_date"),
            "end_date": project.get("end_date") or project.get("return_date"),
            "travel_project_id": project.get("id"),
        },
        improves=["travel_project_linked"],
        confidence=0.75,
        reason_summary="Shadow TRAVEL object from Travel Project confirm",
        ai_used=False,
    )


def reason_from_study(plan: Dict[str, Any]) -> ObjectReasoningDecision:
    from life_objects.deduplication import extract_identity_keys_from_study

    keys = extract_identity_keys_from_study(plan)
    object_type = "UNIVERSITY" if keys.get("institution") else "COURSE"
    if plan.get("course_name") or plan.get("subject"):
        # Prefer COURSE when specific course is known; still keep institution key
        if keys.get("course_key"):
            object_type = "COURSE"
    title = plan.get("course_name") or plan.get("title") or plan.get("institution") or "Studio"
    return ObjectReasoningDecision(
        action="create",
        object_type=object_type,  # type: ignore[arg-type]
        title=str(title)[:120],
        summary=str(plan.get("summary") or "")[:400],
        identity_keys=keys,
        properties_delta={
            "institution": plan.get("institution") or plan.get("university"),
            "course_name": plan.get("course_name") or plan.get("subject"),
            "study_plan_id": plan.get("id"),
        },
        improves=["study_plan_linked"],
        confidence=0.7,
        reason_summary="Shadow UNIVERSITY/COURSE from Study Plan confirm",
        ai_used=False,
    )


def infer_object_type_for_goal(goal: Dict[str, Any]) -> Optional[str]:
    gt = str(goal.get("goal_type") or "").lower()
    title = normalize_text(goal.get("title") or "")
    if gt in ("travel", "vacation") or "viaggio" in title or "vacanza" in title:
        return "TRAVEL"
    if gt in ("study", "exam") or "esame" in title or "studio" in title or "universit" in title:
        return "UNIVERSITY"
    if "casa" in title or "mutuo" in title:
        return "HOME"
    if "auto" in title or "targa" in title:
        return "VEHICLE"
    if "lavoro" in title or "job" in title:
        return "JOB"
    return None
