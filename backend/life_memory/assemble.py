"""Assemble Memory candidates from durable sources — no Gemini, no Contesti temporals."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from life_memory.models import EvidenceRef
from life_memory.authority import (
    authority_band,
    is_current_location_key,
    is_residence_key,
    names_match,
)
from life_memory.statements import (
    confidence_to_status,
    group_label_for_domain,
    is_sensitive_key,
    is_transient_key,
    normalize_slot,
    provenance_label,
    statement_for_note,
    statement_for_profile_fact,
    statement_for_study_subject,
)

HIDDEN_DOMAINS = {"doc"}


@dataclass
class MemoryCandidate:
    candidate_id: str
    kind: str
    statement: str
    domain: Optional[str]
    group_label: str
    slot: str
    entity_keys: List[str] = field(default_factory=list)
    status: str = "known"
    authority: str = "suggested"
    evidence_refs: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    provenance_label: Optional[str] = None
    learned_at: Optional[str] = None
    updated_at: Optional[str] = None
    value_norm: str = ""
    source_priority: int = 50  # lower = more authoritative
    sensitivity: str = "normal"
    editable: bool = False


def _entity_keys(text: str) -> List[str]:
    raw = re.sub(r"(?i)^studio:\s*", "", text or "")
    tokens = re.findall(r"[a-zA-ZàèéìòùÀÈÉÌÒÙ]{3,}", raw.lower())
    return sorted(set(tokens))


def _norm_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return " ".join(str(value).lower().split())


def _role_norm(value: Any) -> str:
    s = _norm_value(value)
    return re.sub(r"^(nella|nel|nello|come|da)\s+", "", s).strip()


_SOURCE_PRIORITY = {
    "user_confirmed": 10,
    "corrected": 10,
    "user_said": 20,
    "document_extract": 30,
    "semantic_extract": 40,
    "inferred": 70,
    "system": 80,
    "user_memory": 25,
    "study_plan": 35,
}


def _parse_ts(raw: Optional[str]) -> float:
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def assemble_life_memory(
    *,
    profile: Optional[Dict[str, Any]],
    study_plans: Optional[Sequence[Dict[str, Any]]] = None,
    user_notes: Optional[Sequence[Dict[str, Any]]] = None,
    auth_user: Optional[Dict[str, Any]] = None,
) -> Tuple[List[MemoryCandidate], List[EvidenceRef], str]:
    candidates: List[MemoryCandidate] = []
    evidence: List[EvidenceRef] = []

    domains = (profile or {}).get("domains") or {}
    for domain_key, dom in domains.items():
        domain = str(domain_key or "").lower().strip()
        if not domain or domain in HIDDEN_DOMAINS:
            continue
        # MLC maps into Identità group presentation
        objects = (dom or {}).get("objects") or {}
        if not isinstance(objects, dict):
            continue
        for key, obj in objects.items():
            if not isinstance(obj, dict):
                continue
            k = str(key or "")
            if is_sensitive_key(k) or is_transient_key(k):
                continue
            # Current device location ≠ residence memory
            if is_current_location_key(k):
                continue
            status_field = str(obj.get("status") or "extracted")
            if status_field == "rejected":
                continue
            value = obj.get("value")
            source = str(obj.get("source") or "user_said")
            # Device signal must never become "Vivi a…" known residence
            if source == "device_signal" and is_residence_key(k):
                continue
            statement = statement_for_profile_fact(domain=domain, key=k, value=value)
            if not statement:
                continue
            conf = float(obj.get("confidence") or 0.5)
            confirmed = bool(obj.get("confirmed")) or status_field in (
                "confirmed",
                "corrected",
            )
            # Account name corroboration → structured authority
            account_name = (auth_user or {}).get("name") if auth_user else None
            if (
                account_name
                and normalize_slot(domain, k) == "identity.name"
                and names_match(value, account_name)
            ):
                source = "structured_account"
                confirmed = True
                status_field = "confirmed"
                conf = max(conf, 0.95)
            mem_status = confidence_to_status(
                confidence=conf,
                field_status=status_field,
                source=source,
                confirmed=confirmed,
                key=k,
            )
            if mem_status == "superseded":
                continue
            # Weak AI inference without confirmation — drop very low signal
            band = authority_band(
                source=source, field_status=status_field, confirmed=confirmed
            )
            if band == "ai_inferred" and conf < 0.55:
                continue

            eid = f"life_profile:{domain}:{k}"
            evidence.append(
                EvidenceRef(
                    id=eid,
                    kind="life_profile_fact",
                    label=k.split(".")[-1][:40],
                    summary=statement[:120],
                )
            )
            has_doc = bool(obj.get("source_document_id") or obj.get("linked_doc_ids"))
            slot = normalize_slot(domain, k)
            # Prefer presentation domain of the slot family (responsibilities → Lavoro)
            present_domain = (
                slot.split(".")[0]
                if "." in slot
                else ("identity" if domain == "mlc" else domain)
            )
            if present_domain == "mlc":
                present_domain = "identity"
            vnorm = _role_norm(value) if slot == "lavoro.role" else _norm_value(value)
            auth = authority_band(
                source=source, field_status=status_field, confirmed=confirmed
            )
            pri = _SOURCE_PRIORITY.get(source, 50)
            if auth in ("user_confirmed", "user_stated", "structured_account"):
                pri = min(pri, 10)
            candidates.append(
                MemoryCandidate(
                    candidate_id=f"cand:{eid}",
                    kind="fact",
                    statement=statement,
                    domain=present_domain,
                    group_label=group_label_for_domain(present_domain),
                    slot=slot,
                    entity_keys=_entity_keys(statement),
                    status=mem_status,
                    authority=auth,
                    evidence_refs=[eid],
                    source_refs=[eid],
                    provenance_label=provenance_label(source, has_document=has_doc),
                    learned_at=obj.get("confirmed_at") or obj.get("updated_at"),
                    updated_at=obj.get("updated_at"),
                    value_norm=vnorm,
                    source_priority=pri,
                    sensitivity=(
                        "sensitive" if domain in ("salute", "finanze") else "normal"
                    ),
                    editable=False,
                )
            )

    # Account identity — authoritative name when profile lacks a stronger name fact
    account_name = ((auth_user or {}).get("name") or "").strip()
    if account_name:
        has_name = any(c.slot == "identity.name" for c in candidates)
        if not has_name:
            statement = statement_for_profile_fact(
                domain="identity", key="identity.preferred_name", value=account_name
            )
            if statement:
                eid = "account:name"
                evidence.append(
                    EvidenceRef(
                        id=eid,
                        kind="account_identity",
                        label="name",
                        summary=statement[:120],
                    )
                )
                candidates.append(
                    MemoryCandidate(
                        candidate_id=f"cand:{eid}",
                        kind="fact",
                        statement=statement,
                        domain="identity",
                        group_label=group_label_for_domain("identity"),
                        slot="identity.name",
                        entity_keys=_entity_keys(statement),
                        status="known",
                        authority="structured_account",
                        evidence_refs=[eid],
                        source_refs=[eid],
                        provenance_label="Dal tuo account",
                        value_norm=_norm_value(account_name),
                        source_priority=5,
                    )
                )

    # Durable study subject (not exam countdown — that belongs to Contesti)
    seen_subjects: set = set()
    for plan in study_plans or []:
        if str(plan.get("status") or "") not in ("active", "paused"):
            continue
        subject = (plan.get("subject") or plan.get("exam_name") or "").strip()
        if not subject:
            continue
        subject_clean = re.sub(r"(?i)^studio:\s*", "", subject).strip()
        ek = tuple(_entity_keys(subject_clean))
        if not ek or ek in seen_subjects:
            continue
        seen_subjects.add(ek)
        pid = str(plan.get("id") or "")
        eid = f"study_plan:{pid}"
        statement = statement_for_study_subject(subject_clean)
        evidence.append(
            EvidenceRef(
                id=eid,
                kind="study_plan",
                label="studio",
                summary=statement[:120],
            )
        )
        candidates.append(
            MemoryCandidate(
                candidate_id=f"cand:{eid}",
                kind="study_subject",
                statement=statement,
                domain="studio",
                group_label=group_label_for_domain("studio"),
                slot=f"studio.subject:{'|'.join(ek)}",
                entity_keys=list(ek),
                status="known",
                authority="structured_system",
                evidence_refs=[eid],
                source_refs=[eid],
                provenance_label=provenance_label("study_plan"),
                learned_at=plan.get("created_at"),
                updated_at=plan.get("updated_at"),
                value_norm=_norm_value(subject_clean),
                source_priority=_SOURCE_PRIORITY["study_plan"],
            )
        )

    for note in user_notes or []:
        durable_status = str(note.get("status") or "active")
        if durable_status in ("superseded", "forgotten", "rejected", "expired"):
            continue
        content = note.get("statement") or note.get("content") or ""
        statement = statement_for_note(str(content))
        if not statement:
            continue
        mid = str(note.get("id") or note.get("memory_id") or "")
        if not mid:
            continue
        eid = f"user_memory:{mid}"
        evidence.append(
            EvidenceRef(
                id=eid,
                kind="user_memory",
                label="appunto",
                summary=statement[:120],
            )
        )
        candidates.append(
            MemoryCandidate(
                candidate_id=f"cand:{eid}",
                kind=str(note.get("kind") or "note")[:80],
                statement=statement,
                domain="note",
                group_label=group_label_for_domain("note"),
                slot=f"note:{mid}",
                entity_keys=_entity_keys(statement),
                status="known" if durable_status == "active" else durable_status,
                authority=str(note.get("authority") or "user_stated"),
                evidence_refs=list(note.get("evidence_refs") or [eid])[:8],
                source_refs=list(
                    dict.fromkeys([eid] + list(note.get("provenance") or []))
                )[:8],
                provenance_label=provenance_label(
                    str(note.get("authority") or "user_memory")
                ),
                learned_at=note.get("created_at"),
                updated_at=note.get("updated_at") or note.get("created_at"),
                value_norm=_norm_value(statement),
                source_priority=_SOURCE_PRIORITY["user_memory"],
                editable=False,
            )
        )

    fp_payload = {
        "cands": [
            {
                "id": c.candidate_id,
                "slot": c.slot,
                "value": c.value_norm,
                "status": c.status,
                "updated": c.updated_at,
            }
            for c in candidates
        ]
    }
    fingerprint = hashlib.sha256(
        json.dumps(fp_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:24]

    return candidates, evidence, fingerprint
