"""Evidence calibration + public source presentation — generic, not course-specific."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from life_os.models import EvidenceRef, EvidenceStatus

_INTERNAL_ID_RE = re.compile(
    r"^(lcf_|doc_|lop_|lgo_|lpi_|ces_|loa_)[A-Za-z0-9_-]+$",
    re.I,
)


def classify_evidence_refs(refs: Sequence[Any]) -> Dict[str, Any]:
    """Summarize whether target-specific evidence exists."""
    kinds: List[str] = []
    for r in refs or []:
        if isinstance(r, EvidenceRef):
            kinds.append(r.kind)
        elif isinstance(r, dict):
            kinds.append(str(r.get("kind") or "GENERAL_EXTERNAL_EVIDENCE"))
        elif isinstance(r, str):
            kinds.append("GENERAL_EXTERNAL_EVIDENCE")
    target = any(k == "TARGET_SPECIFIC_EVIDENCE" for k in kinds)
    user = any(k == "USER_PROVIDED_CONTENT" for k in kinds)
    general = any(k == "GENERAL_EXTERNAL_EVIDENCE" for k in kinds)
    return {
        "has_target_specific": target or user,
        "has_general_external": general,
        "kinds": kinds[:20],
        "calibration": (
            "target_specific"
            if (target or user)
            else ("general_only" if general else "none")
        ),
    }


def calibration_note_for_ai(quality: Dict[str, Any]) -> str:
    cal = quality.get("calibration") or "none"
    if cal == "target_specific":
        return (
            "Target-specific or user-provided evidence is available. "
            "You may speak about the user's concrete programme/materials when citing it."
        )
    if cal == "general_only":
        return (
            "Only GENERAL external evidence is available. "
            "Do NOT claim it is the user's official syllabus/programme/policy. "
            "Calibrate: useful common topics while noting official materials are not yet identified."
        )
    return (
        "No solid external evidence. Prefer asking for materials or searching; "
        "do not invent official requirements."
    )


def _looks_internal_id(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return True
    if _INTERNAL_ID_RE.match(t):
        return True
    if t.startswith("http://") or t.startswith("https://"):
        return False
    if re.fullmatch(r"[a-f0-9]{16,}", t, re.I):
        return True
    return False


def human_display_name(raw: Any) -> str:
    """Pick a human-readable source label; never prefer internal ids."""
    if isinstance(raw, EvidenceRef):
        for cand in (raw.display_name, raw.label, raw.ref):
            s = str(cand or "").strip()
            if s and not _looks_internal_id(s):
                return s[:160]
        if raw.source_type == "user_file":
            return "File fornito da te"
        return "Fonte"
    if isinstance(raw, dict):
        for key in ("display_name", "label", "name", "original_name", "filename"):
            s = str(raw.get(key) or "").strip()
            if s and not _looks_internal_id(s):
                return s[:160]
        for key in ("ref", "source_id", "id", "document_id", "file_id"):
            s = str(raw.get(key) or "").strip()
            if s and not _looks_internal_id(s):
                return s[:160]
        if str(raw.get("source_type") or "") == "user_file":
            return "File fornito da te"
        return "Fonte"
    if isinstance(raw, str):
        s = raw.strip()
        if s and not _looks_internal_id(s):
            return s[:160]
        return "Fonte"
    return "Fonte"


def canonical_evidence_key(raw: Any) -> str:
    """Stable identity for dedupe (document/file preferred over label)."""
    if isinstance(raw, EvidenceRef):
        for cand in (raw.source_id, raw.ref):
            s = str(cand or "").strip()
            if s:
                return s.lower()
        return (raw.display_name or raw.label or "").strip().lower()[:120]
    if isinstance(raw, dict):
        for key in ("source_id", "document_id", "file_id", "ref", "id"):
            s = str(raw.get(key) or "").strip()
            if s:
                return s.lower()
        return human_display_name(raw).lower()
    if isinstance(raw, str):
        return raw.strip().lower()[:120]
    return ""


def normalize_evidence_list(raw: Any) -> List[EvidenceRef]:
    out: List[EvidenceRef] = []
    for r in raw or []:
        try:
            if isinstance(r, EvidenceRef):
                out.append(r)
            elif isinstance(r, dict):
                kind = str(r.get("kind") or "GENERAL_EXTERNAL_EVIDENCE")
                if kind not in (
                    "USER_PROVIDED_CONTENT",
                    "PERSONAL_CONTEXT",
                    "TARGET_SPECIFIC_EVIDENCE",
                    "GENERAL_EXTERNAL_EVIDENCE",
                    "MODEL_KNOWLEDGE",
                    "INFERENCE",
                ):
                    kind = "GENERAL_EXTERNAL_EVIDENCE"
                status = str(r.get("status") or "active")
                if status not in ("active", "superseded", "historical"):
                    status = "active"
                label = str(r.get("label") or "")[:120]
                display = str(r.get("display_name") or "")[:160]
                if not display or _looks_internal_id(display):
                    display = human_display_name(r)
                out.append(
                    EvidenceRef(
                        ref=str(r.get("ref") or r.get("url") or r.get("id") or "ev")[:120],
                        kind=kind,  # type: ignore[arg-type]
                        label=label if not _looks_internal_id(label) else "",
                        url=(str(r["url"])[:300] if r.get("url") else None),
                        display_name=display[:160],
                        status=status,  # type: ignore[arg-type]
                        source_type=str(r.get("source_type") or "")[:40],
                        source_id=str(r.get("source_id") or r.get("document_id") or "")[:80],
                    )
                )
            elif isinstance(r, str) and r.strip():
                s = r.strip()
                out.append(
                    EvidenceRef(
                        ref=s[:120],
                        kind="GENERAL_EXTERNAL_EVIDENCE",
                        display_name=human_display_name(s),
                        label="" if _looks_internal_id(s) else s[:120],
                    )
                )
        except Exception:
            continue
    return out[:24]


def merge_evidence_refs(
    prior: Sequence[Any],
    incoming: Sequence[Any],
    *,
    supersede_prior_user_files: bool = False,
) -> List[EvidenceRef]:
    """Merge evidence; optionally mark older user_file refs superseded by newer files.

    Conversational facts (source_type=user_conversation) must NOT supersede
    user_file evidence merely because a rebuild/replace mutation occurred.
    """
    prior_n = normalize_evidence_list(list(prior or []))
    new_n = normalize_evidence_list(list(incoming or []))
    if supersede_prior_user_files and new_n:
        incoming_file_keys = {
            canonical_evidence_key(e)
            for e in new_n
            if e.source_type == "user_file"
            or (
                e.kind == "USER_PROVIDED_CONTENT"
                and e.source_type not in ("user_conversation",)
                and (e.ref or "").startswith("doc_")
            )
        }
        if incoming_file_keys:
            for e in prior_n:
                is_file = e.source_type == "user_file" or (
                    e.kind == "USER_PROVIDED_CONTENT"
                    and e.source_type != "user_conversation"
                    and (e.ref or "").startswith("doc_")
                )
                if is_file and canonical_evidence_key(e) not in incoming_file_keys:
                    e.status = "superseded"
    by_key: Dict[str, EvidenceRef] = {}
    for e in prior_n + new_n:
        k = canonical_evidence_key(e) or e.ref
        prev = by_key.get(k)
        if prev is None:
            by_key[k] = e
            continue
        if e.status == "active" and prev.status != "active":
            by_key[k] = e
        elif not prev.display_name and e.display_name:
            by_key[k] = e
        elif e.status == "active":
            by_key[k] = e
    return list(by_key.values())[:24]


def conversational_evidence_ref(
    *,
    summary: str,
    session_id: str = "",
    turn_or_epoch: str = "",
) -> Dict[str, Any]:
    """User-turn fact as USER_PROVIDED_CONTENT (not Life Memory dump)."""
    label = (summary or "").strip()[:120] or "Fatto indicato in conversazione"
    ref = f"conv:{(session_id or 'sess')[:40]}:{(turn_or_epoch or 'turn')[:40]}"
    return {
        "ref": ref[:120],
        "kind": "USER_PROVIDED_CONTENT",
        "label": label,
        "display_name": label,
        "source_type": "user_conversation",
        "source_id": ref[:80],
        "status": "active",
    }


def public_evidence_sources(
    refs: Sequence[Any],
    *,
    include_historical: bool = False,
) -> List[Dict[str, Any]]:
    """Workspace-safe source list: human labels, deduped, no internal ids as display."""
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for r in normalize_evidence_list(list(refs or [])):
        st: EvidenceStatus = r.status or "active"
        if not include_historical and st in ("superseded", "historical"):
            continue
        key = canonical_evidence_key(r) or r.ref
        if key in seen:
            continue
        seen.add(key)
        name = human_display_name(r)
        if _looks_internal_id(name) or name in ("Fonte", "Fonte fornita"):
            # No human-readable label available — omit from normal UI
            continue
        out.append(
            {
                "display_name": name,
                "source_kind": r.kind,
                "source_type": r.source_type or "",
                "uploaded_by_user": r.kind == "USER_PROVIDED_CONTENT"
                or r.source_type in ("user_file", "user_conversation"),
                "authority_label": "Fornito da te"
                if (
                    r.kind == "USER_PROVIDED_CONTENT"
                    or r.source_type in ("user_file", "user_conversation")
                )
                else "",
                "status": st,
            }
        )
    return out[:12]
