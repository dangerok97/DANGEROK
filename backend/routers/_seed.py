"""Common seed / migration side-effects executed after auth."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from decision_engine.service import build_seed_decisions
from deps import DEMO_EMAILS, db, decisions

logger = logging.getLogger("ora.seed")


async def _refresh_time_anchors(user_id: str):
    """Idempotent: re-anchor `starts_at`/`deadline` on any decision whose
    metadata carries `eta_min` or `due_days`. Reserved for demo users only.
    """
    now = datetime.now(timezone.utc)
    cursor = db.decisions.find(
        {
            "user_id": user_id,
            "status": "open",
            "$or": [
                {"metadata.eta_min": {"$type": "number"}},
                {"metadata.due_days": {"$type": "number"}},
            ],
        },
        {"_id": 0, "id": 1, "metadata": 1, "starts_at": 1, "deadline": 1},
    )
    async for d in cursor:
        md = d.get("metadata") or {}
        updates: Dict[str, Any] = {}
        if isinstance(md.get("eta_min"), (int, float)):
            updates["starts_at"] = (now + timedelta(minutes=float(md["eta_min"]))).isoformat()
        if isinstance(md.get("due_days"), (int, float)):
            updates["deadline"] = (now + timedelta(days=float(md["due_days"]))).isoformat()
        if updates:
            await db.decisions.update_one({"id": d["id"], "user_id": user_id}, {"$set": updates})


async def _ensure_live_imminent(user_id: str):
    """Ensure the user always has at least one OPEN imminent-event decision.
    Reserved for demo users only."""
    total = await db.decisions.count_documents({"user_id": user_id})
    if total == 0:
        return
    open_imminent = await db.decisions.count_documents({
        "user_id": user_id,
        "status": "open",
        "metadata.eta_min": {"$type": "number"},
    })
    if open_imminent > 0:
        return
    now = datetime.now(timezone.utc)
    doc = {
        "id": f"dec_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "title": "Esci tra 25 minuti.",
        "description": "Il traffico sta aumentando sul tuo tragitto.",
        "origin": "seed:refresh",
        "category": "travel",
        "urgency": 9, "importance": 8, "risk": 6, "time_required_min": 2,
        "energy": 1, "economic_impact": 2, "personal_impact": 7,
        "place": "Ufficio", "people": [],
        "starts_at": (now + timedelta(minutes=25)).isoformat(),
        "deadline": None,
        "status": "open",
        "linked_to": [],
        "metadata": {"eta_min": 25, "destination": "Ufficio"},
        "history": [{"at": now.isoformat(), "event": "auto_seeded_imminent", "data": {}}],
        "created_at": now.isoformat(),
    }
    await db.decisions.insert_one(doc)


async def prepare_user_decisions(user_id: str, *, is_demo: bool = False):
    """Called after any successful auth. Real users' Decision documents are
    NEVER touched by login (idempotent seed on empty accounts only)."""
    try:
        await decisions.migrate_user_tasks(user_id)
    except Exception:
        logger.exception("Legacy task migration failed for %s", user_id)

    count = await db.decisions.count_documents({"user_id": user_id})
    if count == 0:
        seeds = build_seed_decisions(user_id)
        if seeds:
            await db.decisions.insert_many(seeds)

    if is_demo:
        try:
            await _refresh_time_anchors(user_id)
            await _ensure_live_imminent(user_id)
        except Exception:
            logger.exception("Demo refresh failed for %s", user_id)


def is_demo_email(email: str) -> bool:
    return email in DEMO_EMAILS
