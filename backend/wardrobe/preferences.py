"""Opt-in durable wardrobe taste feedback, isolated per ORA owner.

A feedback mark belongs to an exact outfit and occasion; no other account
can read or influence it. Preference weights are applied to existing outfit
candidates, never used to make up new garments or claim real stylist training.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .recommend import OCCASIONS
from .service import WardrobeError

MAX_FEEDBACK = 250


class OutfitFeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    occasion: Literal["running", "casual_evening", "chic_evening", "club", "wedding"]
    item_ids: list[str] = Field(min_length=2, max_length=3)
    reaction: Literal["like", "dislike"]

    @model_validator(mode="after")
    def check_ids(self):
        if len(self.item_ids) != len(set(self.item_ids)):
            raise ValueError("Duplicate item")
        if any(not re.fullmatch(r"[0-9a-f]{32}", key) for key in self.item_ids):
            raise ValueError("Invalid wardrobe item")
        return self


def combo_key(occasion: str, item_ids: list[str]) -> str:
    content = f"{occasion}:{'|'.join(sorted(item_ids))}"
    return hashlib.sha256(content.encode()).hexdigest()


def complete_owned_outfit(items: list[dict], occasion: str, ids: list[str]) -> bool:
    known = {i["id"]: i for i in items}
    if len(set(ids)) != len(ids) or any(i not in known for i in ids):
        return False
    members = [known[i] for i in ids]
    if any(i.get("status") != "available" or
           i.get("formality") not in OCCASIONS[occasion] for i in members):
        return False
    cats = sorted(i["category"] for i in members)
    return cats in (["bottom", "shoes", "top"], ["one_piece", "shoes"])


async def record_feedback(db, owner: str, items: list[dict], body: OutfitFeedbackInput) -> dict:
    if not complete_owned_outfit(items, body.occasion, body.item_ids):
        raise WardrobeError(
            "Il look non è completo o contiene capi non disponibili. Aggiorna il guardaroba.", 409)
    token = combo_key(body.occasion, body.item_ids)
    key = f"{owner}:{token}"
    col = db.wardrobe_outfit_feedback
    now = datetime.now(timezone.utc).isoformat()
    existing = await col.find_one({"_id": key, "user_id": owner})
    if not existing and await col.count_documents({"user_id": owner}) >= MAX_FEEDBACK:
        raise WardrobeError("Limite delle preferenze raggiunto in questa versione.", 409)
    if existing:
        result = await col.update_one(
            {"_id": key, "user_id": owner},
            {"$set": {"reaction": body.reaction, "updated_at": now}},
        )
        if not result.matched_count:
            raise WardrobeError("Preferenza cambiata durante il salvataggio.", 409)
    else:
        record = {
            "_id": key, "user_id": owner,
            "occasion": body.occasion, "item_ids": sorted(body.item_ids),
            "reaction": body.reaction, "created_at": now, "updated_at": now,
        }
        try:
            await col.insert_one(record)
        except Exception as exc:
            if getattr(exc, "code", None) == 11000:
                # Concurrent request: do not bypass a preference updated by another tab.
                raise WardrobeError("Preferenza già registrata. Aggiorna i consigli.", 409) from None
            raise
    return {"stored": True, "reaction": body.reaction, "occasion": body.occasion,
            "item_ids": list(body.item_ids)}


async def load_feedback(db, owner: str) -> list[dict]:
    docs = await db.wardrobe_outfit_feedback.find({"user_id": owner}).to_list(
        length=MAX_FEEDBACK + 1)
    return docs[:MAX_FEEDBACK]


def prioritize_outfits(outfits: list[dict], feedback: list[dict], occasion: str,
                       limit: int = 12) -> tuple[list[dict], bool]:
    """Learn a bounded affinity for real saved items, prefer liked, avoid disliked.

    Returns (candidates, all_disliked). Explicit dislikes are never offered
    as a positive recommendation, even when that is the sole available look.
    """
    by_combo = {
        combo_key(row["occasion"], row["item_ids"]): row["reaction"]
        for row in feedback
        if row.get("occasion") == occasion and
        row.get("reaction") in ("like", "dislike")
    }
    item_score: dict[str, float] = {}
    for row in feedback:
        weight = 1.0 if row.get("reaction") == "like" else -1.2
        if row.get("reaction") not in ("like", "dislike"):
            continue
        for item_id in row.get("item_ids", []):
            item_score[item_id] = item_score.get(item_id, 0) + weight

    candidates = []
    for rank, look in enumerate(outfits):
        exact = by_combo.get(combo_key(occasion, look["item_ids"]))
        if exact == "dislike":
            continue
        boost = 100 if exact == "like" else 0
        boost += sum(max(-4, min(4, item_score.get(i, 0))) for i in look["item_ids"])
        candidates.append((float(boost), rank, {**look, "feedback": exact}))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return [look for _, _, look in candidates[:limit]], bool(outfits and not candidates)


async def delete_item_feedback(db, owner: str, item_id: str) -> None:
    # No image, no preference survives an explicit item deletion. Owner guarded.
    await db.wardrobe_outfit_feedback.delete_many(
        {"user_id": owner, "item_ids": item_id})
