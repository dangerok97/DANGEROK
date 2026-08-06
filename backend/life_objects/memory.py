"""History / memory helpers for Life Objects (temporal + trend foundation)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_objects.models import LifeObject, LifeObjectHistoryEntry, now_iso


def append_history(
    obj: LifeObject,
    *,
    event: str,
    source: str,
    source_id: Optional[str] = None,
    summary: str = "",
    delta: Optional[Dict[str, Any]] = None,
    improves: Optional[List[str]] = None,
    worsens: Optional[List[str]] = None,
    max_entries: int = 200,
) -> LifeObject:
    entry = LifeObjectHistoryEntry(
        at=now_iso(),
        event=event,
        source=source,
        source_id=source_id,
        summary=summary[:500],
        delta=delta or {},
        improves=list(improves or []),
        worsens=list(worsens or []),
    )
    hist = list(obj.history or [])
    hist.append(entry)
    obj.history = hist[-max_entries:]
    return obj


def utility_amount_series(obj: LifeObject) -> List[Dict[str, Any]]:
    """Extract bolletta/utility amounts from history for trend helpers."""
    series: List[Dict[str, Any]] = []
    for h in obj.history or []:
        delta = h.delta or {}
        amount = delta.get("amount") or delta.get("amount_total")
        if amount is None:
            props = delta.get("properties") or {}
            if isinstance(props, dict):
                amount = props.get("amount_total") or props.get("amount")
        if amount is None:
            continue
        try:
            # Normalize "123,45" / "EUR 123.45"
            raw = str(amount).replace("EUR", "").replace("€", "").strip().replace(".", "").replace(",", ".")
            # If both . and , were present European style already handled; fallback:
            if raw.count(".") > 1:
                raw = str(amount).replace("EUR", "").replace("€", "").strip().replace(",", "")
            val = float(raw)
        except (TypeError, ValueError):
            continue
        series.append({
            "at": h.at,
            "amount": val,
            "source_id": h.source_id,
            "utility_type": (delta.get("utility_type") or (delta.get("properties") or {}).get("utility_type")),
        })
    return series


def basic_utility_trend(obj: LifeObject, *, utility_type: Optional[str] = None) -> Dict[str, Any]:
    """Basic trend for same utility type (rising / falling / flat / unknown)."""
    series = utility_amount_series(obj)
    if utility_type:
        series = [s for s in series if not s.get("utility_type") or s.get("utility_type") == utility_type]
    if len(series) < 2:
        return {
            "trend": "unknown",
            "points": len(series),
            "delta": None,
            "latest": series[-1]["amount"] if series else None,
        }
    # Compare last two
    a, b = series[-2]["amount"], series[-1]["amount"]
    delta = round(b - a, 2)
    if abs(delta) < 0.01 * max(abs(a), 1.0):
        trend = "flat"
    elif delta > 0:
        trend = "rising"
    else:
        trend = "falling"
    return {
        "trend": trend,
        "points": len(series),
        "delta": delta,
        "latest": b,
        "previous": a,
        "utility_type": utility_type,
    }
