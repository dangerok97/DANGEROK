"""Identity vs State split — non-destructive migration from `properties`.

Identity = what defines the object (address, plate, POD…).
State = what changes over time (rates, suppliers, consumption, status…).
`properties` is kept as a union bag for backward compatibility.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from life_objects.models import IDENTITY_PROPERTY_KEYS, STATE_PROPERTY_KEYS, LifeObject


def classify_property_key(key: str) -> str:
    k = str(key or "").strip()
    if k in IDENTITY_PROPERTY_KEYS:
        return "identity"
    if k in STATE_PROPERTY_KEYS:
        return "state"
    # Heuristic for unknown keys
    lower = k.lower()
    if any(x in lower for x in ("address", "plate", "vin", "pod", "pdr", "cadastral", "institution", "employer")):
        return "identity"
    return "state"


def split_properties(properties: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    identity: Dict[str, Any] = {}
    state: Dict[str, Any] = {}
    for k, v in (properties or {}).items():
        if v in (None, "", [], {}):
            continue
        bucket = identity if classify_property_key(k) == "identity" else state
        bucket[k] = v
    return identity, state


def merge_identity_state(
    *,
    identity: Dict[str, Any],
    state: Dict[str, Any],
    properties: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Union properties into identity/state; keep properties as full bag."""
    id_out = dict(identity or {})
    st_out = dict(state or {})
    props_out = dict(properties or {})
    # From properties bag
    id_from_props, st_from_props = split_properties(props_out)
    for k, v in id_from_props.items():
        if k not in id_out or id_out.get(k) in (None, "", [], {}):
            id_out[k] = v
    for k, v in st_from_props.items():
        if v not in (None, "", [], {}):
            st_out[k] = v
    # Explicit identity/state win and also mirror into properties
    for k, v in id_out.items():
        if v not in (None, "", [], {}):
            props_out[k] = v
    for k, v in st_out.items():
        if v not in (None, "", [], {}):
            props_out[k] = v
    return id_out, st_out, props_out


def apply_identity_state_migration(obj: LifeObject) -> LifeObject:
    """Non-destructive: fill identity/state from properties + identity_keys."""
    identity, state, properties = merge_identity_state(
        identity=dict(obj.identity or {}),
        state=dict(obj.state or {}),
        properties=dict(obj.properties or {}),
    )
    # Mirror strong identity_keys into identity display fields when missing
    ik = obj.identity_keys or {}
    if ik.get("address_norm") and "address" not in identity:
        identity["address"] = ik["address_norm"]
    if ik.get("plate") and "plate" not in identity:
        identity["plate"] = ik["plate"]
    if ik.get("vin") and "vin" not in identity:
        identity["vin"] = ik["vin"]
    if ik.get("cadastral") and "cadastral_data" not in identity:
        identity["cadastral_data"] = ik["cadastral"]
    if ik.get("pod") and "pod" not in identity:
        identity["pod"] = ik["pod"]
    if ik.get("pdr") and "pdr" not in identity:
        identity["pdr"] = ik["pdr"]
    if ik.get("institution") and "institution" not in identity:
        identity["institution"] = ik["institution"]
    if ik.get("employer") and "employer" not in identity:
        identity["employer"] = ik["employer"]
    for k, v in identity.items():
        if v not in (None, "", [], {}):
            properties[k] = v
    for k, v in state.items():
        if v not in (None, "", [], {}):
            properties[k] = v
    obj.identity = identity
    obj.state = state
    obj.properties = properties
    return obj


def apply_properties_delta(obj: LifeObject, delta: Dict[str, Any]) -> None:
    """Merge a properties delta into identity/state/properties (non-destructive).

    Routes aliases through property_registry canonical names when available.
    """
    try:
        from life_objects.property_registry import merge_mapped_into

        id_out, st_out, props_out = merge_mapped_into(
            identity=dict(obj.identity or {}),
            state=dict(obj.state or {}),
            properties=dict(obj.properties or {}),
            delta=delta or {},
        )
        obj.identity = id_out
        obj.state = st_out
        obj.properties = props_out
    except Exception:
        props = dict(obj.properties or {})
        identity = dict(obj.identity or {})
        state = dict(obj.state or {})
        for k, v in (delta or {}).items():
            if v in (None, "", [], {}):
                continue
            props[k] = v
            if classify_property_key(k) == "identity":
                identity[k] = v
            else:
                state[k] = v
        obj.properties = props
        obj.identity = identity
        obj.state = state
    apply_identity_state_migration(obj)
