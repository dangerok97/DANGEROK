"""Link / merge semantic states.

Four states:
- LINK_CONFIRMED — identity match confirmed; quiet assimilation allowed
- LINK_PROBABLE — strong soft overlap; quiet (not user-facing)
- LINK_UNCERTAIN — weak signal; backend holds, no silent second object
- REAL_CONFLICT — incompatible strong keys; ONLY this is user-facing / home-disturbing
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

LinkState = Literal[
    "LINK_CONFIRMED",
    "LINK_PROBABLE",
    "LINK_UNCERTAIN",
    "REAL_CONFLICT",
]

LINK_STATES: Tuple[str, ...] = (
    "LINK_CONFIRMED",
    "LINK_PROBABLE",
    "LINK_UNCERTAIN",
    "REAL_CONFLICT",
)

# Strong keys that, when both present and unequal → REAL_CONFLICT
CONFLICT_KEYS_BY_TYPE: Dict[str, Tuple[str, ...]] = {
    "HOME": ("cadastral", "pod", "pdr", "coords"),
    "VEHICLE": ("plate", "vin"),
    "JOB": ("employer",),
    "UNIVERSITY": ("institution",),
    "COURSE": ("course_key",),
    "TRAVEL": ("travel_dest_period",),
}


def classify_link_state(
    *,
    object_type: str,
    existing_keys: Dict[str, str],
    incoming_keys: Dict[str, str],
    address_soft_match: bool = False,
) -> LinkState:
    """Classify relationship between an existing object and an incoming identity."""
    t = str(object_type or "").upper()
    existing = {k: v for k, v in (existing_keys or {}).items() if v}
    incoming = {k: v for k, v in (incoming_keys or {}).items() if v}
    if not incoming and not existing:
        return "LINK_UNCERTAIN"

    conflict_keys = CONFLICT_KEYS_BY_TYPE.get(t, ())
    for k in conflict_keys:
        a, b = existing.get(k), incoming.get(k)
        if a and b and a != b:
            return "REAL_CONFLICT"

    # Exact shared strong key → confirmed
    shared_exact = [k for k, v in incoming.items() if existing.get(k) == v]
    strong_home = ("cadastral", "pod", "pdr", "address_norm", "lender_property", "coords")
    strong_vehicle = ("plate", "vin")
    strong = {
        "HOME": strong_home,
        "VEHICLE": strong_vehicle,
        "MORTGAGE": ("lender_property", "address_norm", "cadastral"),
        "UTILITY": ("pod", "pdr", "contract_code", "address_norm"),
        "JOB": ("employer",),
        "UNIVERSITY": ("institution",),
        "COURSE": ("course_key", "institution"),
        "TRAVEL": ("travel_dest_period",),
    }.get(t, tuple(incoming.keys()))

    if any(k in strong for k in shared_exact):
        return "LINK_CONFIRMED"

    # Soft address for HOME (containment or street+number overlap)
    if t == "HOME":
        a = existing.get("address_norm") or ""
        b = incoming.get("address_norm") or ""
        if a and b:
            from life_objects.deduplication import LifeObjectDeduper
            if LifeObjectDeduper._address_soft_equal(a, b) or address_soft_match:
                return "LINK_CONFIRMED" if a == b or a in b or b in a else "LINK_PROBABLE"
        if shared_exact:
            return "LINK_PROBABLE"

    if shared_exact:
        return "LINK_PROBABLE"

    if incoming and existing and not shared_exact:
        # Both have keys but none shared — uncertain unless conflict already caught
        return "LINK_UNCERTAIN"

    if not incoming:
        return "LINK_UNCERTAIN"

    return "LINK_UNCERTAIN"


def is_user_facing(state: LinkState) -> bool:
    """Only REAL_CONFLICT disturbs the user / Home."""
    return state == "REAL_CONFLICT"


def is_quiet(state: LinkState) -> bool:
    return state in ("LINK_CONFIRMED", "LINK_PROBABLE")


def should_assimilate(state: LinkState) -> bool:
    """Clear same-object updates assimilate without merge_proposal piles."""
    return state in ("LINK_CONFIRMED", "LINK_PROBABLE")


def should_propose_merge(state: LinkState) -> bool:
    return state == "REAL_CONFLICT"


def summarize_pending_links(obj_public: Dict[str, Any]) -> Dict[str, int]:
    """Count pending link/merge entries by state for health scoring."""
    counts = {
        "LINK_CONFIRMED": 0,
        "LINK_PROBABLE": 0,
        "LINK_UNCERTAIN": 0,
        "REAL_CONFLICT": 0,
    }
    for p in obj_public.get("merge_proposals") or []:
        if not isinstance(p, dict):
            continue
        st = str(p.get("link_state") or "LINK_UNCERTAIN")
        if st not in counts:
            st = "REAL_CONFLICT" if p.get("conflict") else "LINK_UNCERTAIN"
        counts[st] = counts.get(st, 0) + 1
    for r in obj_public.get("pending_links") or []:
        if not isinstance(r, dict):
            continue
        st = str(r.get("link_state") or "LINK_UNCERTAIN")
        if st in counts:
            counts[st] += 1
    return counts
