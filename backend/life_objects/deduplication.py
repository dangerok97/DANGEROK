"""Life Object deduplication — NEVER match on title alone.

Strong keys: address, cadastral, POD/PDR, plate, VIN, lender+property, coords.
On conflict with incompatible keys → propose merge (never silent Casa 2).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from life_objects.models import LifeObject


# Keys that uniquely identify an object when present (ordered by strength).
STRONG_KEYS_BY_TYPE: Dict[str, Tuple[str, ...]] = {
    "HOME": ("cadastral", "pod", "pdr", "address_norm", "coords", "lender_property"),
    "VEHICLE": ("plate", "vin"),
    "MORTGAGE": ("lender_property", "address_norm", "cadastral"),
    "UTILITY": ("pod", "pdr", "contract_code", "address_norm"),
    "INSURANCE": ("policy_number", "plate", "address_norm"),
    "UNIVERSITY": ("institution",),
    "COURSE": ("course_key", "institution"),
    "JOB": ("employer",),
    "TRAVEL": ("travel_dest_period",),
    "FAMILY_MEMBER": ("person_key",),
    "PERSON": ("person_key",),
    "BANK_ACCOUNT": ("iban_last4",),
    "COMPANY": ("company_vat", "company_name_norm"),
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_plate(value: Any) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    return s


def normalize_pod_pdr(value: Any) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    return s


def normalize_cadastral(value: Any) -> str:
    """Collapse foglio/particella/sub into a compact key."""
    s = normalize_text(value)
    s = re.sub(r"\s+", "", s)
    return s


def extract_identity_keys_from_reasoning(
    *,
    object_type: str,
    reasoning: Dict[str, Any],
    type_specific: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Build identity_keys from DocumentReasoning / type_specific — no invented facts."""
    ts = type_specific if isinstance(type_specific, dict) else {}
    if not ts:
        ts = reasoning.get("type_specific") if isinstance(reasoning.get("type_specific"), dict) else {}
    keys: Dict[str, str] = {}

    address = (
        ts.get("address")
        or ts.get("property_address")
        or _entity_value(reasoning, "address")
        or _entity_value(reasoning, "indirizzo")
    )
    if address:
        keys["address_norm"] = normalize_text(address)

    cadastral = ts.get("cadastral_data") or _entity_value(reasoning, "cadastral")
    if cadastral:
        keys["cadastral"] = normalize_cadastral(cadastral)

    pod = ts.get("pod") or _entity_value(reasoning, "pod") or _find_in_text(reasoning, r"\bIT\d{3}E\d+\b")
    if pod:
        keys["pod"] = normalize_pod_pdr(pod)

    pdr = ts.get("pdr") or _entity_value(reasoning, "pdr")
    if pdr:
        keys["pdr"] = normalize_pod_pdr(pdr)

    plate = ts.get("plate") or _entity_value(reasoning, "plate") or _entity_value(reasoning, "targa")
    if not plate and object_type == "VEHICLE":
        insured = ts.get("insured_object")
        if insured and normalize_plate(insured) and 5 <= len(normalize_plate(insured)) <= 10:
            plate = insured
    if plate and object_type in ("VEHICLE", "INSURANCE"):
        p = normalize_plate(plate)
        if 5 <= len(p) <= 10:
            keys["plate"] = p

    vin = ts.get("vin") or _entity_value(reasoning, "vin")
    if vin:
        keys["vin"] = normalize_plate(vin)

    lender = ts.get("lender")
    prop = ts.get("property_address") or address
    if lender and prop:
        keys["lender_property"] = f"{normalize_text(lender)}|{normalize_text(prop)}"

    coords = ts.get("coords") or ts.get("coordinates")
    if coords:
        keys["coords"] = normalize_text(coords)

    contract = ts.get("contract_code")
    if contract:
        keys["contract_code"] = normalize_text(contract)

    institution = ts.get("institution") or _entity_value(reasoning, "university")
    if institution:
        keys["institution"] = normalize_text(institution)

    course = ts.get("course_name")
    if course and institution:
        keys["course_key"] = f"{normalize_text(institution)}|{normalize_text(course)}"
    elif course:
        keys["course_key"] = normalize_text(course)

    employer = ts.get("employer") or ts.get("company") or _entity_value(reasoning, "employer")
    if employer and object_type == "JOB":
        keys["employer"] = normalize_text(employer)

    policy = ts.get("policy_number")
    if policy:
        keys["policy_number"] = normalize_text(policy)

    # Drop empties
    return {k: v for k, v in keys.items() if v}


def extract_identity_keys_from_travel(project: Dict[str, Any]) -> Dict[str, str]:
    dest = normalize_text(project.get("destination") or project.get("title") or "")
    start = str(project.get("start_date") or project.get("departure_date") or "")[:10]
    end = str(project.get("end_date") or project.get("return_date") or "")[:10]
    if not dest:
        return {}
    return {"travel_dest_period": f"{dest}|{start}|{end}"}


def extract_identity_keys_from_study(plan: Dict[str, Any]) -> Dict[str, str]:
    keys: Dict[str, str] = {}
    inst = plan.get("institution") or plan.get("university") or ""
    course = plan.get("course_name") or plan.get("subject") or plan.get("title") or ""
    if inst:
        keys["institution"] = normalize_text(inst)
    if course and inst:
        keys["course_key"] = f"{normalize_text(inst)}|{normalize_text(course)}"
    elif course:
        keys["course_key"] = normalize_text(course)
    return keys


def _entity_value(reasoning: Dict[str, Any], etype: str) -> Optional[str]:
    etype_l = etype.lower()
    for e in reasoning.get("entities") or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("type") or "").lower() == etype_l:
            v = e.get("value")
            if v:
                return str(v)
    return None


def _find_in_text(reasoning: Dict[str, Any], pattern: str) -> Optional[str]:
    blob = " ".join(
        str(x)
        for x in (
            reasoning.get("summary"),
            reasoning.get("context"),
            reasoning.get("title"),
            str(reasoning.get("type_specific") or ""),
        )
        if x
    )
    m = re.search(pattern, blob, re.IGNORECASE)
    return m.group(0) if m else None


class LifeObjectDeduper:
    """Match existing Life Objects by strong identity keys only."""

    def __init__(self, repo):
        self.repo = repo

    async def find_match(
        self,
        user_id: str,
        *,
        object_type: str,
        identity_keys: Dict[str, str],
    ) -> Tuple[Optional[LifeObject], Optional[str], List[LifeObject]]:
        """
        Returns (best_match, match_key, all_candidates).
        If multiple distinct objects share different keys → callers should propose_merge.
        Never matches on title.
        """
        if not identity_keys:
            return None, None, []

        strong = STRONG_KEYS_BY_TYPE.get(object_type, tuple(identity_keys.keys()))
        # Prefer strongest key order
        ordered = [k for k in strong if k in identity_keys] + [
            k for k in identity_keys if k not in strong
        ]

        matched: Optional[LifeObject] = None
        matched_key: Optional[str] = None
        for key in ordered:
            found = await self.repo.find_by_identity_key(
                user_id, object_type=object_type, key=key, value=identity_keys[key],
            )
            if found:
                matched = found
                matched_key = key
                break

        candidates = await self.repo.find_candidates(
            user_id, object_type=object_type, identity_keys=identity_keys,
        )
        # Soft address containment for HOME (rogito vs mutuo/bolletta variants)
        if not matched and object_type == "HOME" and identity_keys.get("address_norm"):
            soft = await self._soft_address_match(user_id, identity_keys["address_norm"])
            if soft:
                matched = soft
                matched_key = "address_norm_soft"
                if soft not in candidates:
                    candidates.append(soft)

        # Deduplicate candidates by id
        seen = set()
        uniq: List[LifeObject] = []
        for c in candidates:
            if c.id not in seen:
                seen.add(c.id)
                uniq.append(c)

        # Conflict: multiple distinct objects hit by different keys
        if len(uniq) > 1:
            return matched or uniq[0], matched_key or "conflict", uniq

        return matched, matched_key, uniq

    async def _soft_address_match(self, user_id: str, address_norm: str) -> Optional[LifeObject]:
        """Match HOME when one address string contains the other (street-level)."""
        if not address_norm or len(address_norm) < 8:
            return None
        homes = await self.repo.list_by_type(user_id, object_type="HOME", limit=40)
        hits: List[LifeObject] = []
        for h in homes:
            old = (h.identity_keys or {}).get("address_norm") or ""
            if not old:
                continue
            if old == address_norm or old in address_norm or address_norm in old:
                hits.append(h)
                continue
            # Token overlap: require shared street token + number
            ot, nt = set(old.split()), set(address_norm.split())
            shared = ot & nt
            has_num = any(t.isdigit() for t in shared)
            if has_num and len(shared) >= 3:
                hits.append(h)
        if len(hits) == 1:
            return hits[0]
        return None

    def merge_fields(self, target: LifeObject, source: LifeObject) -> LifeObject:
        """Merge source into target (non-destructive for confirmed properties)."""
        # Union lists
        for attr in ("documents", "calendar_events", "goals", "projects", "brain_nodes"):
            existing = list(getattr(target, attr) or [])
            for x in getattr(source, attr) or []:
                if x not in existing:
                    existing.append(x)
            setattr(target, attr, existing)

        # Properties: keep target if present, fill gaps from source
        props = dict(target.properties or {})
        for k, v in (source.properties or {}).items():
            if k not in props or props[k] in (None, "", [], {}):
                props[k] = v
        target.properties = props

        # Identity keys: union
        ik = dict(target.identity_keys or {})
        for k, v in (source.identity_keys or {}).items():
            if v and k not in ik:
                ik[k] = v
        target.identity_keys = ik

        # History append
        hist = list(target.history or [])
        hist.extend(source.history or [])
        target.history = hist[-200:]

        target.source_count = max(target.source_count, 0) + max(source.source_count, 0)
        if source.confidence > target.confidence:
            target.confidence = source.confidence
        if not target.summary and source.summary:
            target.summary = source.summary
        if not target.ai_summary and source.ai_summary:
            target.ai_summary = source.ai_summary
        return target

    def has_identity_conflict(
        self,
        existing: LifeObject,
        incoming_keys: Dict[str, str],
    ) -> bool:
        """True when same key name has different non-empty values."""
        for k, v in incoming_keys.items():
            old = (existing.identity_keys or {}).get(k)
            if old and v and old != v:
                # address_norm soft: containment OR street+number token overlap
                if k == "address_norm" and self._address_soft_equal(old, v):
                    continue
                return True
        return False

    @staticmethod
    def _address_soft_equal(a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b or a in b or b in a:
            return True
        ta, tb = set(a.split()), set(b.split())
        shared = ta & tb
        # Drop pure CAP tokens for overlap (5-digit)
        shared_sig = {t for t in shared if not (t.isdigit() and len(t) == 5)}
        has_num = any(t.isdigit() for t in shared_sig)
        streetish = any(t in shared_sig for t in ("via", "viale", "corso", "piazza", "vicolo"))
        return has_num and (streetish or len(shared_sig) >= 3)
