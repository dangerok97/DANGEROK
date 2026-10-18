"""Transparent, deterministic outfit pilot; never pretend this is an AI stylist.

Based on role coverage, weather bands and formality filtering concepts in
Wardrowbe (Copyright 2026 Anish S., MIT). Adapted for ORA's smaller taxonomy;
see docs/wardrobe-v1.md and backend/wardrobe/THIRD_PARTY_LICENSE.txt.
"""
from __future__ import annotations

from itertools import product
from typing import Any

OCCASIONS = {
    "running": ("sport",),
    "casual_evening": ("casual", "smart"),
    "chic_evening": ("smart", "formal"),
    "club": ("smart", "casual"),
    "wedding": ("formal", "smart"),
}
REQUIRED = ("top", "bottom", "shoes")
NEUTRAL = {"nero", "bianco", "grigio", "beige", "blu", "marrone"}
COLOR_ALIASES = {
    "black": "nero", "white": "bianco", "grey": "grigio", "gray": "grigio",
    "navy": "blu", "blue": "blu", "brown": "marrone", "cream": "beige",
    "green": "verde", "red": "rosso", "pink": "rosa", "yellow": "giallo",
}


def _color(item: dict) -> str:
    value = str(item.get("color") or "").strip().casefold()
    return COLOR_ALIASES.get(value, value)


def _season_score(item: dict, temperature_c: float | None) -> float:
    """Small, explainable adaptation of Wardrowbe's temperature-bucket approach."""
    if temperature_c is None:
        return 0.0
    seasons = item.get("seasons") or []
    if temperature_c <= 10:
        if "winter" in seasons:
            return 1.5
        if seasons and seasons == ["summer"]:
            return -3.0
    if temperature_c >= 27:
        if "summer" in seasons:
            return 1.5
        if seasons and seasons == ["winter"]:
            return -3.0
    return 0.0


def _palette_score(combo: tuple[dict, ...]) -> float:
    colors = [_color(item) for item in combo]
    distinct = set(colors)
    vivid = [c for c in distinct if c not in NEUTRAL]
    if len(vivid) > 1:
        return -2.0
    if len(distinct) == 1:
        return 1.5
    if len(distinct) <= 3 and any(c in NEUTRAL for c in distinct):
        return 2.0
    return 0.0


def recommend(items: list[dict], occasion: str, temperature_c: float | None = None) -> dict[str, Any]:
    """Return only owned, available garments; missing slots stay explicitly missing.

    No hallucinated shoes, inferred dress codes, outfit renderings or AI claims.
    This rules-based pilot is NOT a professional fashion-quality guarantee.
    """
    if occasion not in OCCASIONS:
        raise ValueError("Occasione non supportata")
    allowed = OCCASIONS[occasion]
    available = [item for item in items if item.get("status") == "available" and item.get("formality") in allowed]
    by_role: dict[str, list[dict]] = {
        role: sorted((i for i in available if i.get("category") == role),
                     key=lambda i: (i.get("name", "").casefold(), i.get("id", "")))[:20]
        for role in REQUIRED
    }
    missing = [role for role in REQUIRED if not by_role[role]]
    if missing:
        return {"engine": "rules-v1", "occasion": occasion, "outfits": [],
                "missing": missing, "message": "Non ho abbastanza capi adatti e disponibili per un look completo."}

    results: list[tuple[float, tuple[str, ...], tuple[dict, ...]]] = []
    for combo in product(*(by_role[r] for r in REQUIRED)):
        # All pieces are from different body slots and can each be worn once.
        score = _palette_score(combo) + sum(_season_score(i, temperature_c) for i in combo)
        score += sum(0.8 if i["formality"] == allowed[0] else 0.0 for i in combo)
        results.append((score, tuple(str(i["id"]) for i in combo), combo))
    results.sort(key=lambda x: (-x[0], x[1]))
    chosen: list[dict] = []
    for score, ids, combo in results:
        if any(set(ids) == set(existing["item_ids"]) for existing in chosen):
            continue
        # An alternative should be visually distinct, not simply swap identical shoes.
        if chosen and len(set(ids) & set(chosen[0]["item_ids"])) > 1:
            continue
        chosen.append({
            "item_ids": list(ids),
            "title": "Look sportivo" if occasion == "running" else "Abbinamento dal tuo guardaroba",
            "why": "Capi disponibili, coerenti per formalità e combinazione cromatica indicativa.",
            "score": round(score, 1),
        })
        if len(chosen) == 2:
            break
    return {"engine": "rules-v1", "occasion": occasion, "outfits": chosen,
            "missing": [], "message": "Consigli preliminari: controlla vestibilità e dress code."}
