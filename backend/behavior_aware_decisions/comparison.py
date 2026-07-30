"""Comparison engine: real ranking vs shadow ranking (iter17).

Analytical ONLY. Never modifies the real order.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple


def _kendall_tau(a: List[str], b: List[str]) -> float:
    """Simple Kendall tau-b on two rankings (same items, possibly reordered)."""
    common = [x for x in a if x in b]
    idx_b = {x: i for i, x in enumerate(b)}
    n = len(common)
    if n < 2:
        return 1.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            ai, aj = i, j
            bi, bj = idx_b[common[i]], idx_b[common[j]]
            if (ai - aj) * (bi - bj) > 0:
                concordant += 1
            elif (ai - aj) * (bi - bj) < 0:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else 1.0


def compare_rankings(real: List[Dict[str, Any]], shadow_evals: Dict[str, float]) -> Dict[str, Any]:
    """Compare real ranking (list ordered by score desc) with shadow deltas.

    `real` items must have keys: id, score.
    `shadow_evals` is {decision_id -> shadow_priority_delta}.
    """
    n = len(real)
    if n == 0:
        return {"evaluated": 0, "positive": 0, "negative": 0, "unchanged": 0,
                "avg_delta": 0, "max_delta": 0, "min_delta": 0,
                "position_changes": 0, "unchanged_ratio": 1.0,
                "kendall_tau": 1.0, "top_absolute_delta": []}

    shadow_list = []
    for r in real:
        did = r["id"]
        delta = shadow_evals.get(did, 0.0)
        shadow_list.append({"id": did, "shadow_score": (r.get("score") or 0) + delta, "delta": delta})

    shadow_sorted = sorted(shadow_list, key=lambda x: -x["shadow_score"])
    real_order = [r["id"] for r in real]
    shadow_order = [r["id"] for r in shadow_sorted]
    real_pos = {x: i for i, x in enumerate(real_order)}
    shadow_pos = {x: i for i, x in enumerate(shadow_order)}

    position_changes = sum(1 for x in real_order if real_pos.get(x) != shadow_pos.get(x))
    unchanged = position_changes == 0
    deltas = [x["delta"] for x in shadow_list]
    positive = sum(1 for d in deltas if d > 0)
    negative = sum(1 for d in deltas if d < 0)
    zero = sum(1 for d in deltas if d == 0)

    top_abs = sorted(shadow_list, key=lambda x: -abs(x["delta"]))[:10]

    return {
        "evaluated": n,
        "positive": positive,
        "negative": negative,
        "unchanged": zero,
        "avg_delta": round(sum(deltas) / n, 3) if deltas else 0.0,
        "max_delta": round(max(deltas), 3) if deltas else 0.0,
        "min_delta": round(min(deltas), 3) if deltas else 0.0,
        "position_changes": position_changes,
        "unchanged_ratio": round(1.0 - (position_changes / n), 3),
        "kendall_tau": round(_kendall_tau(real_order, shadow_order), 4),
        "top_absolute_delta": [{"id": x["id"], "delta": x["delta"]} for x in top_abs],
    }
