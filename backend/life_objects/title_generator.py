"""Deterministic canonical title generator — NEVER AI text as final title.

HOME: address → via+city → Casa → Casa #N
VEHICLE: brand → brand+model → plate → Auto
JOB: company → profession → Lavoro
UNIVERSITY: university → course → Università
TRAVEL: destination → Viaggio
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _safe(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _pretty_address(addr: str) -> str:
    """Light title-case for address fragments; keep numbers."""
    s = re.sub(r"\s+", " ", addr.strip())
    if not s:
        return ""
    parts = []
    for w in s.split():
        if w.isdigit() or re.match(r"^\d+[A-Za-z]?$", w):
            parts.append(w.upper() if w.isalpha() else w)
        elif len(w) <= 2 and w.lower() in ("di", "da", "de", "del", "della", "via", "v.", "piazza", "corso"):
            parts.append(w.capitalize() if w.lower() in ("via", "v.", "piazza", "corso") else w.lower())
        else:
            parts.append(w.capitalize())
    return " ".join(parts)


def _extract_via_city(address: str) -> str:
    """Prefer 'Via X, City' style short label."""
    s = re.sub(r"\s+", " ", address.strip())
    if not s:
        return ""
    # Drop CAP / province codes lightly
    s = re.sub(r"\b\d{5}\b", "", s)
    s = re.sub(r"\([A-Za-z]{2}\)", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    # Take up to street + city (2 comma segments)
    bits = [b.strip() for b in s.split(",") if b.strip()]
    if len(bits) >= 2:
        return f"{_pretty_address(bits[0])}, {_pretty_address(bits[1])}"
    return _pretty_address(bits[0] if bits else s)


def generate_canonical_title(
    object_type: str,
    *,
    identity: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    properties: Optional[Dict[str, Any]] = None,
    identity_keys: Optional[Dict[str, str]] = None,
    existing_titles: Optional[List[str]] = None,
    fallback_index: int = 1,
) -> str:
    """Backend-authoritative title. Never returns AI free text as-is for typed objects."""
    t = str(object_type or "CUSTOM").strip().upper()
    identity = identity or {}
    state = state or {}
    properties = properties or {}
    ik = identity_keys or {}

    if t == "HOME":
        addr = (
            _safe(identity.get("address"))
            or _safe(properties.get("address"))
            or _safe(properties.get("property_address"))
            or _safe(ik.get("address_norm"))
        )
        if addr:
            label = _extract_via_city(addr)
            if label:
                # Prefer "Casa di Via Roma" / "Casa - Milano" patterns
                if re.search(r"\bvia\b|\bcorso\b|\bpiazza\b|\bviale\b", label, re.I):
                    return f"Casa di {label}"
                return f"Casa - {label}"
        # Sequential Casa #N when no address
        n = max(1, int(fallback_index or 1))
        titles = {x.strip().lower() for x in (existing_titles or [])}
        while f"casa #{n}" in titles:
            n += 1
        return f"Casa #{n}" if n > 1 else "Casa"

    if t == "VEHICLE":
        brand = _safe(identity.get("brand") or properties.get("brand"))
        model = _safe(identity.get("model") or properties.get("model"))
        plate = _safe(identity.get("plate") or properties.get("plate") or ik.get("plate"))
        if brand and model:
            base = f"{brand} {model}".strip()
            return f"{base} ({plate})" if plate else base
        if brand:
            return f"{brand} ({plate})" if plate else brand
        if plate:
            return f"Auto {plate}"
        return "Auto"

    if t == "JOB":
        company = _safe(
            identity.get("employer")
            or properties.get("employer")
            or state.get("employer")
            or ik.get("employer")
        )
        profession = _safe(state.get("profession") or properties.get("profession") or identity.get("profession"))
        if company:
            return f"Lavoro — {_pretty_address(company)}"
        if profession:
            return f"Lavoro — {_pretty_address(profession)}"
        return "Lavoro"

    if t in ("UNIVERSITY", "COURSE"):
        uni = _safe(
            identity.get("institution")
            or identity.get("university")
            or properties.get("institution")
            or ik.get("institution")
        )
        course = _safe(
            state.get("course_name")
            or properties.get("course_name")
            or identity.get("course_name")
        )
        if t == "COURSE" and course:
            return f"Corso — {_pretty_address(course)}"
        if uni and course:
            return f"Università — {_pretty_address(uni)} ({_pretty_address(course)})"
        if uni:
            return f"Università — {_pretty_address(uni)}"
        if course:
            return f"Università — {_pretty_address(course)}"
        return "Università"

    if t == "TRAVEL":
        dest = _safe(state.get("destination") or identity.get("destination") or properties.get("destination"))
        if dest:
            return f"Viaggio — {_pretty_address(dest)}"
        return "Viaggio"

    if t == "FAMILY_MEMBER":
        return "Familiare"

    # CUSTOM / others: keep a safe short label, never job-ish for homes (handled above)
    return t.replace("_", " ").title() if t else "Oggetto"


def is_incoherent_title(object_type: str, title: str) -> bool:
    """Detect type/title incoherence (e.g. HOME + 'Lavoro')."""
    t = str(object_type or "").upper()
    title_l = (title or "").strip().lower()
    if not title_l:
        return True
    if t == "HOME":
        bad = ("lavoro", "job", "busta paga", "impiego", "datore", "università", "universita", "viaggio", "auto ")
        if title_l in ("lavoro", "job", "work"):
            return True
        if title_l.startswith("lavoro") and "casa" not in title_l:
            return True
        for b in bad:
            if title_l == b or title_l.startswith(b + " ") or title_l.startswith(b + "—") or title_l.startswith(b + "-"):
                return True
        return False
    if t == "JOB":
        if title_l in ("casa", "home") or title_l.startswith("casa "):
            return True
    if t == "VEHICLE":
        if title_l in ("casa", "lavoro", "università", "universita"):
            return True
    return False
