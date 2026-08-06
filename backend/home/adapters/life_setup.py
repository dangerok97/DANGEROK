"""Home adapter — optional ONE soft Life Setup resume card (never a Life Setup section)."""
from __future__ import annotations

from typing import List, Tuple

from home.models import ConnectionWarning, HomeAction, HomeItem, ReasonFactor


async def load_life_setup_items(db, user_id: str) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    """At most one insight/resume card. No permanent Life Setup module on Home."""
    items: List[HomeItem] = []
    try:
        sess = await db.life_setup_sessions.find_one(
            {
                "user_id": user_id,
                "status": {"$in": ["interrupted", "skipped"]},
                "resume_suggestion_emitted": True,
            },
            {"_id": 0},
            sort=[("updated_at", -1)],
        )
        if not sess:
            return [], []
        # Suppress if user already has active life_setup again or completed later
        later = await db.life_setup_sessions.find_one(
            {"user_id": user_id, "status": {"$in": ["completed", "active"]}},
            {"_id": 0, "id": 1},
            sort=[("updated_at", -1)],
        )
        if later and later.get("id") != sess.get("id"):
            # If completed after interrupt, hide
            if later:
                done = await db.life_setup_sessions.find_one(
                    {"user_id": user_id, "status": "completed"},
                    {"_id": 0, "id": 1},
                )
                if done:
                    return [], []

        items.append(
            HomeItem(
                id=f"life_setup_resume:{sess['id']}",
                type="insight",
                subtype="life_setup_resume",
                title="ORA può aiutarti ancora di più",
                description=(
                    "Quando vuoi, raccontami un pezzo della tua vita "
                    "o carica un documento utile."
                ),
                source_type="life_setup",
                source_id=sess["id"],
                priority="later",
                urgency="none",
                confidence=0.75,
                actions=[
                    HomeAction(
                        id="continue_ora",
                        label="Continua con ORA",
                        kind="navigate",
                        route="/life-setup?resume=1",
                        primary=True,
                    )
                ],
                reason_factors=[
                    ReasonFactor(
                        code="life_setup_soft_resume",
                        label="Ripresa gentile",
                        weight=0.5,
                        detail="Nessun wizard; nessun «completa il profilo».",
                    )
                ],
                reason_summary="Suggerimento unico dopo un'interruzione — non una sezione Life Setup.",
                meta={
                    "wizard": False,
                    "life_setup_section": False,
                    "forbidden_copy": ["completa il profilo", "life setup"],
                },
            )
        )
    except Exception:
        return [], []
    return items, []
