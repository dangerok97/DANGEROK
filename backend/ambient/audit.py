"""Read-only, content-free counts for the autonomous work pipeline."""
from __future__ import annotations

import asyncio


async def pipeline_counts(db, *, owner_id=None) -> dict:
    """Return only aggregate states; no source text, names, IDs or tokens."""
    scope = {"owner_id": owner_id} if owner_id is not None else {}
    queries = {
        "opportunities.active": ("opportunities", {"status": "active"}),
        "opportunities.delivery_pending": ("opportunities", {"status": "active", "delivery_review_state": "pending"}),
        "opportunities.delivery_settled": ("opportunities", {"status": "active", "delivery_review_state": "settled"}),
        "opportunities.delivery_paused": ("opportunities", {"status": "active", "delivery_review_state": "paused"}),
        "opportunities.delivery_legacy_untracked": ("opportunities", {"status": "active", "delivery_review_state": {"$exists": False}}),
        "opportunities.agent_pending": ("opportunities", {"status": "active", "agent_review_state": "pending"}),
        "opportunities.agent_settled": ("opportunities", {"status": "active", "agent_review_state": "settled"}),
        "opportunities.agent_paused": ("opportunities", {"status": "active", "agent_review_state": "paused"}),
        "goals.active": ("agent_goals", {"status": "active"}),
        "goals.waiting": ("agent_goals", {"status": "waiting"}),
        "goals.completed": ("agent_goals", {"status": "completed"}),
        "wakes.pending": ("ambient_wakes", {"status": "pending"}),
        "wakes.claimed": ("ambient_wakes", {"status": "claimed"}),
        "wakes.failed": ("ambient_wakes", {"status": "failed"}),
    }

    async def count(collection, condition):
        return await db[collection].count_documents({**scope, **condition})

    values = await asyncio.gather(*(count(collection, condition)
                                    for collection, condition in queries.values()))
    return dict(zip(queries, values))
