"""Shared ORA AI Core / WhatsApp wardrobe read capability.

The same tool works from ORA conversations and WhatsApp because both channels
use ToolRegistry. Never return photo data or encrypted storage identifiers.
"""
from __future__ import annotations

from typing import Any

from conversation_engine.ai_core.models import Observation
from .service import OutfitInput, WardrobeError, WardrobeService, PhotoCipher

CAPABILITY = "suggest_wardrobe_outfit"


def _observation(status: str, payload: dict) -> Observation:
    return Observation(
        kind="tool", name=CAPABILITY, status=status,
        payload={**payload, "grounding": "PERSONAL_CONTEXT", "memory_eligible": False},
    )


async def suggest_wardrobe_outfit(arguments: dict[str, Any], runtime: dict[str, Any]) -> Observation:
    owner = str(runtime.get("user_id") or "")
    db = runtime.get("db")
    if not owner or db is None:
        return _observation("error", {"status": "NOT_AUTHENTICATED"})
    try:
        body = OutfitInput(
            occasion=arguments.get("occasion"),
            use_ai=True,
            style_note=str(arguments.get("style_note") or "")[:200],
            temperature_c=arguments.get("temperature_c"),
        )
    except (ValueError, TypeError):
        return _observation("partial", {"status": "INVALID_OCCASION",
                   "reason": "Indica corsa, serata casual, serata chic, discoteca o matrimonio."})
    try:
        service = WardrobeService(db, PhotoCipher.configured())
        outcome = await service.outfits(owner, body)
        # Metadata lookup is owner-scoped and never decrypts photos.
        catalog = {item["id"]: item for item in await service.list_metadata(owner)}
    except WardrobeError:
        return _observation("error", {"status": "UNAVAILABLE", "reason": "Guardaroba non disponibile ora."})
    if not outcome["outfits"]:
        return _observation("partial", {
            "status": "NEEDS_WARDROBE_ITEMS",
            "missing_categories": outcome.get("missing", []),
            "reason": "Non ci sono abbastanza capi adatti e disponibili registrati.",
            "ui_actions": [{"kind": "ora_screen", "path": "/guardaroba",
                            "label": "Apri il guardaroba in ORA"}],
        })
    looks = []
    for look in outcome["outfits"][:2]:
        pieces = [{
            "name": catalog[item_id]["name"],
            "category": catalog[item_id]["category"],
            "color": catalog[item_id]["color"],
        } for item_id in look["item_ids"] if item_id in catalog]
        looks.append({
            "pieces": pieces,
            "verdict": look.get("verdict"),
            "why": look.get("why", ""),
            "cautions": list(look.get("cautions") or [])[:3],
            "styling_tip": look.get("styling_tip", ""),
        })
    return _observation("ok", {
        "status": "ok", "occasion": outcome["occasion"], "looks": looks,
        "engine": outcome["engine"], "ai_status": outcome.get("ai_status"),
        "candidate_count": outcome.get("candidate_count"),
        "notice": outcome.get("message"),
        "ui_actions": [{"kind": "ora_screen", "path": "/guardaroba",
                        "label": "Apri il guardaroba in ORA"}],
    })
