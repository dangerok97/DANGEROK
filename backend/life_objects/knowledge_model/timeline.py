"""Life Timeline — semantic grouping of related events (not document sort order)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_objects.knowledge_model.models import KnowledgeFact, MemoryEvent, TimelineGroup


_GROUP_TITLES = {
    "purchase_path": "Percorso acquisto",
    "mortgage_path": "Percorso mutuo",
    "utility_path": "Percorso utenze",
    "insurance_path": "Percorso assicurazioni",
    "solar_path": "Percorso fotovoltaico",
    "vehicle_path": "Percorso veicolo",
    "general": "Altri eventi",
}

# Preferred order of event kinds within mortgage path
_MORTGAGE_ORDER = (
    "purchase",
    "mortgage",
    "mortgage_surrogacy",
    "rate_change",
    "mortgage_extinction",
)

_UTILITY_ORDER = (
    "utility_contract",
    "utility_bill",
    "supplier_change",
)


def build_timeline(
    *,
    memory: List[MemoryEvent],
    facts: Optional[List[KnowledgeFact]] = None,
    history: Optional[List[Any]] = None,
) -> List[TimelineGroup]:
    """Group memory (+ optional fact/history hints) into semantic paths."""
    buckets: Dict[str, List[Dict[str, Any]]] = {}

    for m in memory or []:
        key = m.timeline_group or _infer_group(m.kind)
        buckets.setdefault(key, []).append({
            "id": m.id,
            "kind": m.kind,
            "title": m.title,
            "narrative": m.narrative,
            "at": m.at,
            "source": m.source,
            "source_id": m.source_id,
            "related_fact_ids": list(m.related_fact_ids or []),
            "origin": "memory",
        })

    # Enrich utility_path from superseded supplier facts (historical)
    for f in facts or []:
        if f.type in ("utility_supplier", "supplier") and f.status in ("superseded", "current", "archived"):
            buckets.setdefault("utility_path", []).append({
                "id": f.id,
                "kind": "supplier_fact",
                "title": f"Fornitore: {f.value}",
                "narrative": (
                    f"Fornitore {f.value} "
                    f"({'attuale' if f.status == 'current' else f.status})"
                ),
                "at": f.created_at,
                "source": f.source,
                "source_id": f.source_id,
                "related_fact_ids": [f.id],
                "origin": "fact",
                "fact_status": f.status,
                "active": f.active,
            })

    # Soft history hints (technical) only if no memory yet for that stamp
    for h in history or []:
        if hasattr(h, "model_dump"):
            hd = h.model_dump()
        elif isinstance(h, dict):
            hd = h
        else:
            continue
        event = str(hd.get("event") or "")
        if event not in ("updated", "created", "assimilated"):
            continue
        # Skip if we already have richer memory around same source_id
        sid = hd.get("source_id")
        already = False
        if sid:
            for evs in buckets.values():
                if any(e.get("source_id") == sid for e in evs):
                    already = True
                    break
        if already:
            continue
        delta = hd.get("delta") or {}
        kind_hint = "life_event"
        group = "general"
        if (delta.get("assimilation") or {}).get("kind") == "mortgage":
            kind_hint, group = "mortgage", "mortgage_path"
        elif (delta.get("assimilation") or {}).get("kind") == "utility":
            kind_hint, group = "utility_bill", "utility_path"
        buckets.setdefault(group, []).append({
            "id": f"hist_{sid or hd.get('at')}",
            "kind": kind_hint,
            "title": (hd.get("summary") or event)[:120],
            "narrative": hd.get("summary") or "",
            "at": hd.get("at"),
            "source": hd.get("source"),
            "source_id": sid,
            "related_fact_ids": [],
            "origin": "history",
        })

    groups: List[TimelineGroup] = []
    for key, events in buckets.items():
        events = _sort_group_events(key, events)
        started = events[0].get("at") if events else None
        ended = events[-1].get("at") if events else None
        status = "active"
        if key == "mortgage_path" and any(e.get("kind") == "mortgage_extinction" for e in events):
            status = "completed"
        groups.append(TimelineGroup(
            id=f"tg_{key}",
            group_key=key,
            title=_GROUP_TITLES.get(key, key),
            summary=_summarize(key, events),
            events=events,
            started_at=started,
            ended_at=ended,
            status=status,
        ))

    # Stable order: purchase → mortgage → utility → insurance → solar → vehicle → general
    order = [
        "purchase_path", "mortgage_path", "utility_path",
        "insurance_path", "solar_path", "vehicle_path", "general",
    ]
    rank = {k: i for i, k in enumerate(order)}
    groups.sort(key=lambda g: (rank.get(g.group_key, 50), g.started_at or ""))
    return groups


def _infer_group(kind: str) -> str:
    k = str(kind or "")
    if k in ("purchase", "lease"):
        return "purchase_path"
    if "mortgage" in k or k == "rate_change":
        return "mortgage_path"
    if k in ("utility_bill", "utility_contract", "supplier_change", "supplier_fact"):
        return "utility_path"
    if "insurance" in k:
        return "insurance_path"
    if k == "solar":
        return "solar_path"
    if "vehicle" in k:
        return "vehicle_path"
    return "general"


def _sort_group_events(group_key: str, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    order_map: Dict[str, int] = {}
    if group_key == "mortgage_path":
        order_map = {k: i for i, k in enumerate(_MORTGAGE_ORDER)}
    elif group_key == "utility_path":
        order_map = {k: i for i, k in enumerate(_UTILITY_ORDER)}

    def key_fn(e: Dict[str, Any]):
        return (order_map.get(str(e.get("kind")), 50), e.get("at") or "")

    return sorted(events, key=key_fn)


def _summarize(group_key: str, events: List[Dict[str, Any]]) -> str:
    if not events:
        return ""
    if group_key == "mortgage_path":
        kinds = {e.get("kind") for e in events}
        parts = []
        if "mortgage" in kinds:
            parts.append("mutuo")
        if "mortgage_surrogacy" in kinds:
            parts.append("surroga")
        if "mortgage_extinction" in kinds:
            parts.append("estinzione")
        return " → ".join(parts) if parts else f"{len(events)} eventi mutuo"
    if group_key == "utility_path":
        suppliers = [
            e.get("title") for e in events
            if e.get("kind") in ("supplier_fact", "supplier_change")
        ]
        if suppliers:
            return f"Fornitori tracciati: {len(suppliers)}"
        return f"{len(events)} eventi utenze"
    return f"{len(events)} eventi"


def serialize_timeline(groups: List[TimelineGroup]) -> List[Dict[str, Any]]:
    return [g.model_dump() for g in groups]
