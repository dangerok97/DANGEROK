"""Proactive generator — soft resume after Life Setup interrupt (one suggestion)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from proactive_engine.models import SuggestionAction, SuggestionCandidate


async def generate_life_setup_candidates(
    db, user_id: str, *, now: Optional[datetime] = None,
) -> List[SuggestionCandidate]:
    now = now or datetime.now(timezone.utc)
    out: List[SuggestionCandidate] = []
    try:
        sess = await db.life_setup_sessions.find_one(
            {
                "user_id": user_id,
                "status": {"$in": ["interrupted", "skipped"]},
            },
            {"_id": 0},
            sort=[("updated_at", -1)],
        )
        if not sess:
            return []
        # Never if completed afterwards
        done = await db.life_setup_sessions.find_one(
            {"user_id": user_id, "status": "completed"},
            {"_id": 0, "id": 1},
        )
        if done:
            return []
        out.append(
            SuggestionCandidate(
                title="ORA può aiutarti ancora di più",
                description=(
                    "Quando vuoi, raccontami un pezzo della tua vita "
                    "o carica un documento utile."
                ),
                reason="Hai interrotto la prima conversazione — un solo suggerimento gentile.",
                type="life",
                source="life_setup_interrupt",
                action=SuggestionAction(
                    kind="resume_life_conversation",
                    label="Continua con ORA",
                    route="/life-setup?resume=1",
                    params={"life_setup_session_id": sess.get("id")},
                ),
                dedupe_key=f"life_setup_resume:{user_id}",
                evidence={"life_setup_session_id": sess.get("id")},
                meta={"wizard": False, "forbidden": ["Completa il profilo", "Life Setup"]},
                importance_hint=0.55,
                urgency_hint=0.3,
                confidence=0.8,
            )
        )
    except Exception:
        return []
    return out
