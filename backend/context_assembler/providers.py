"""Six context providers. Each returns a ProviderResult. Failures are captured."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .freshness import evaluate_freshness
from .redaction import is_highly_sensitive_key
from .types import ProviderResult, Signal


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==================================================================
# 1. Decision provider — data straight from the decision itself.
# ==================================================================
async def decision_provider(repo, user_id: str, decision: Dict[str, Any]) -> ProviderResult:
    t0 = time.perf_counter()
    signals: List[Signal] = []
    now = datetime.now(timezone.utc)

    def add(key: str, value: Any, value_type: str, unit: Optional[str] = None, verified: bool = True, reliability: str = "user_verified"):
        if value is None:
            return
        signals.append(Signal(
            key=key, value=value, value_type=value_type, unit=unit,
            source_module="decision", source_id=decision.get("id"),
            confidence=1.0, verified=verified, sensitivity="personal",
            observed_at=_now(), reliability_tier=reliability,
        ))

    add("decision_category", decision.get("category") or "generic", "string")
    add("urgency", decision.get("urgency"), "number")
    add("importance", decision.get("importance"), "number")
    add("risk", decision.get("risk"), "number")
    add("time_required_min", decision.get("time_required_min"), "number", unit="min")
    add("energy_required", decision.get("energy"), "number")
    add("place", decision.get("place"), "string")
    people = decision.get("people") or []
    if people:
        signals.append(Signal(
            key="people_involved", value=list(people), value_type="string_list",
            source_module="decision", source_id=decision.get("id"),
            confidence=1.0, verified=True, sensitivity="personal",
            observed_at=_now(), reliability_tier="user_verified",
        ))

    # Time signals + hours_until derived
    deadline = decision.get("deadline")
    starts_at = decision.get("starts_at")
    if deadline:
        add("deadline_iso", deadline, "iso_datetime")
        hrs = _hours_until(deadline, now)
        if hrs is not None:
            signals.append(Signal(
                key="deadline_hours", value=round(hrs, 2), value_type="number", unit="hours",
                source_module="decision", source_id=decision.get("id"),
                confidence=1.0, verified=True, sensitivity="personal",
                observed_at=_now(), reliability_tier="user_verified",
                freshness=evaluate_freshness("decision_deadline", _now(), now=now),
            ))
    if starts_at:
        add("starts_at_iso", starts_at, "iso_datetime")
        hrs = _hours_until(starts_at, now)
        if hrs is not None:
            add("starts_in_hours", round(hrs, 2), "number", unit="hours")

    return ProviderResult(name="decision", signals=signals, duration_ms=(time.perf_counter() - t0) * 1000)


def _hours_until(iso_str: str, now: datetime) -> Optional[float]:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - now).total_seconds() / 3600.0


# ==================================================================
# 2. Linked nodes provider
# ==================================================================
async def linked_nodes_provider(repo, user_id: str, decision: Dict[str, Any], allowed_types: set) -> ProviderResult:
    t0 = time.perf_counter()
    signals: List[Signal] = []
    node_ids = list(dict.fromkeys(decision.get("node_ids") or []))  # de-dup keep order
    if not node_ids:
        return ProviderResult(name="linked_nodes", duration_ms=(time.perf_counter() - t0) * 1000)

    nodes = await repo.list_nodes(user_id, node_ids)
    kept: List[str] = []
    for n in nodes:
        if n["type"] not in allowed_types:
            continue
        kept.append(n["id"])
        signals.append(Signal(
            key="linked_node", value={"id": n["id"], "type": n["type"], "label": n.get("label")}, value_type="object",
            source_module="linked_nodes", source_id=n["id"],
            confidence=1.0, verified=True, sensitivity="personal",
            observed_at=_now(), reliability_tier="user_verified",
        ))
    return ProviderResult(name="linked_nodes", signals=signals, linked_node_ids=kept, duration_ms=(time.perf_counter() - t0) * 1000)


# ==================================================================
# 3. Knowledge provider — only for the KEPT linked nodes.
# ==================================================================
_TYPE_TO_PROPS: Dict[str, List[str]] = {
    "home":         ["home_type", "address", "residents", "utilities", "purchase_date"],
    "car":          ["brand", "model", "plate", "insurance", "road_tax", "mot", "mileage_km"],
    "person":       ["name", "relation", "birthday"],
    "document":     ["doc_type", "issued_at", "expires_at", "state"],
    "subscription": ["provider", "plan", "amount", "currency", "frequency", "next_payment", "auto_renew"],
    "contract":     ["contract_type", "counterparty", "start_date", "end_date", "status", "value"],
    "health":       ["focus", "doctor", "next_checkup", "emergency_contact"],
    "university":   ["institution", "program", "year", "gpa", "graduation_target"],
    "job":          ["company", "role", "started_at", "employment_type"],
    "trip":         ["destination", "start_date", "end_date"],
    "purchase":     ["item", "vendor", "amount", "purchased_at", "warranty_until"],
    "pet":          ["name", "species", "vet"],
    "goal":         ["category", "target", "target_date", "progress_pct"],
    "event":        ["event_type", "location", "starts_at", "ends_at"],
    "finance":      ["account_type", "bank", "balance", "currency"],
    "generic":      ["summary", "tags"],
}


async def knowledge_provider(repo, user_id: str, node_ids: List[str], allow_highly_sensitive: bool = False) -> ProviderResult:
    t0 = time.perf_counter()
    signals: List[Signal] = []
    kversions: Dict[str, int] = {}
    if not node_ids:
        return ProviderResult(name="knowledge", duration_ms=(time.perf_counter() - t0) * 1000)

    nodes_by_id = {n["id"]: n for n in await repo.list_nodes(user_id, node_ids)}
    kmap = await repo.get_knowledge_bulk(user_id, node_ids)

    for nid in node_ids:
        node = nodes_by_id.get(nid)
        if not node:
            continue
        kdoc = kmap.get(nid) or {}
        kversions[nid] = int(kdoc.get("version") or 0)
        props = (kdoc.get("properties") or {})
        wanted = _TYPE_TO_PROPS.get(node["type"], []) or list(props.keys())
        for k in wanted:
            env = props.get(k)
            if env is None:
                continue
            if not isinstance(env, dict) or "value" not in env or "value_type" not in env:
                continue
            sensitivity = env.get("sensitivity") or "personal"
            if sensitivity == "highly_sensitive" and not allow_highly_sensitive:
                continue
            if is_highly_sensitive_key(k) and not allow_highly_sensitive:
                continue
            provenance = env.get("provenance") or {}
            verified = bool(provenance.get("verified_by_user"))
            confidence = float(provenance.get("confidence") or 1.0)
            reliability = "user_verified" if verified else _rel_from_source(provenance.get("source_type"))
            observed = provenance.get("last_confirmed_at") or provenance.get("extracted_at") or _now()
            signals.append(Signal(
                key=f"{node['type']}.{k}",
                value=env.get("value"),
                value_type=env.get("value_type") or "string",
                unit=env.get("unit"),
                source_module="knowledge",
                source_id=nid,
                confidence=confidence,
                verified=verified,
                sensitivity=sensitivity,
                observed_at=observed,
                reliability_tier=reliability,
                freshness=evaluate_freshness(_freshness_key_for(node["type"], k), observed),
            ))

    return ProviderResult(name="knowledge", signals=signals, knowledge_versions=kversions, duration_ms=(time.perf_counter() - t0) * 1000)


def _rel_from_source(source_type: Optional[str]) -> str:
    mapping = {
        "user_input": "user_verified",
        "document":   "document",
        "banking":    "official",
        "calendar":   "official",
        "email":      "document",
        "ai_extraction": "system_derived",
        "system":     "system_derived",
        "migration":  "system_derived",
    }
    return mapping.get(source_type or "", "system_derived")


def _freshness_key_for(node_type: str, prop_key: str) -> str:
    if prop_key in ("address",):
        return "home_address"
    if prop_key == "plate":
        return "car_plate"
    if prop_key in ("expires_at", "next_payment", "next_checkup", "warranty_until", "end_date"):
        return "document_expiry"
    if prop_key in ("name",):
        return "person_name"
    if prop_key in ("provider",):
        return "provider_name"
    return "user_preference"


# ==================================================================
# 4. Graph provider
# ==================================================================
async def graph_provider(repo, user_id: str, root_ids: List[str], depth: int = 1, allowed_types: Optional[set] = None) -> ProviderResult:
    t0 = time.perf_counter()
    signals: List[Signal] = []
    if not root_ids:
        return ProviderResult(name="graph", duration_ms=(time.perf_counter() - t0) * 1000)

    res = await repo.graph_neighbors(user_id, root_ids, depth=depth)
    distances = res.get("distances") or {}
    edges = res.get("edges") or []

    # Fetch nodes that are within reach and pass the allowed_types filter.
    all_ids = list(distances.keys())
    nodes = await repo.list_nodes(user_id, all_ids)
    by_id = {n["id"]: n for n in nodes}

    for nid, dist in distances.items():
        if dist == 0:
            continue
        n = by_id.get(nid)
        if not n:
            continue
        if allowed_types and n["type"] not in allowed_types:
            continue
        signals.append(Signal(
            key="graph_neighbor",
            value={"id": nid, "type": n["type"], "label": n.get("label"), "distance": dist},
            value_type="object",
            source_module="graph",
            source_id=nid,
            confidence=0.9, verified=True, sensitivity="personal",
            observed_at=_now(), reliability_tier="user_verified",
        ))

    for e in edges[:50]:
        signals.append(Signal(
            key="graph_edge",
            value={"from": e["from_node"], "to": e["to_node"], "type": e.get("type")},
            value_type="object",
            source_module="graph",
            source_id=e.get("id"),
            confidence=1.0, verified=True, sensitivity="personal",
            observed_at=_now(), reliability_tier="user_verified",
        ))

    return ProviderResult(name="graph", signals=signals, duration_ms=(time.perf_counter() - t0) * 1000)


# ==================================================================
# 5. Auto-Link provider
# ==================================================================
async def auto_link_provider(repo, user_id: str, decision_id: str) -> ProviderResult:
    t0 = time.perf_counter()
    signals: List[Signal] = []
    proposals = await repo.accepted_proposals(user_id, decision_id)
    for p in proposals:
        signals.append(Signal(
            key="accepted_link",
            value={
                "proposal_id": p.get("id"),
                "node_id": p.get("node_id"),
                "confidence": p.get("confidence"),
                "matcher_version": p.get("matcher_version"),
                "signals": [s.get("tag") for s in (p.get("matching_signals") or [])],
            },
            value_type="object",
            source_module="auto_link",
            source_id=p.get("id"),
            confidence=float(p.get("confidence") or 1.0),
            verified=True, sensitivity="personal",
            observed_at=p.get("accepted_at") or _now(),
            reliability_tier="verifiable_id",
        ))
    return ProviderResult(name="auto_link", signals=signals, duration_ms=(time.perf_counter() - t0) * 1000)


# ==================================================================
# 6. System provider
# ==================================================================
async def system_provider(repo, user_id: str) -> ProviderResult:
    t0 = time.perf_counter()
    now = datetime.now(timezone.utc)
    signals = [
        Signal(key="now_iso", value=now.isoformat(), value_type="iso_datetime",
               source_module="system", confidence=1.0, verified=True, sensitivity="public",
               observed_at=now.isoformat(), reliability_tier="official"),
        Signal(key="weekday", value=now.strftime("%A").lower(), value_type="string",
               source_module="system", confidence=1.0, verified=True, sensitivity="public",
               observed_at=now.isoformat(), reliability_tier="official"),
        Signal(key="hour_of_day", value=now.hour, value_type="number", unit="hour",
               source_module="system", confidence=1.0, verified=True, sensitivity="public",
               observed_at=now.isoformat(), reliability_tier="official"),
    ]
    return ProviderResult(name="system", signals=signals, duration_ms=(time.perf_counter() - t0) * 1000)
