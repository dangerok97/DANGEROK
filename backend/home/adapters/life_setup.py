"""Home adapter — benefit cards after Life Experience; soft resume if interrupted.

After first setup: NEVER show a Life Setup section.
Home shows only Italian benefit signals («Adesso posso seguire il tuo mutuo.»).
"""
from __future__ import annotations

from typing import List, Set, Tuple

from home.models import ConnectionWarning, HomeAction, HomeItem, ReasonFactor


async def _known_keys_for_user(db, user_id: str) -> Set[str]:
    keys: Set[str] = set()
    try:
        from life_setup.profile_service import LifeProfileService

        prof = await LifeProfileService(db).get(user_id)
        if prof:
            keys |= set(LifeProfileService(db).flat_known(prof).keys())
    except Exception:
        pass
    try:
        sess = await db.life_setup_sessions.find_one(
            {"user_id": user_id, "status": "completed"},
            {"_id": 0, "known_facts": 1, "benefits_active": 1},
            sort=[("updated_at", -1)],
        )
        if sess:
            for k, v in (sess.get("known_facts") or {}).items():
                if v not in (None, False, "", []):
                    keys.add(k)
    except Exception:
        pass
    return keys


async def load_life_setup_items(db, user_id: str) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    """Benefit insights after conversation — never a permanent Life Setup module."""
    items: List[HomeItem] = []

    # 1) Activated benefits after completed / active profile knowledge
    try:
        from ai_life_strategist.benefit_engine import home_benefit_cards

        known = await _known_keys_for_user(db, user_id)
        if known:
            for b in home_benefit_cards(known, limit=5):
                if not b.home_signal:
                    continue
                items.append(
                    HomeItem(
                        id=f"life_benefit:{b.code}:{user_id}",
                        type="insight",
                        subtype="life_benefit",
                        title=b.home_signal,
                        description=b.user_benefit,
                        source_type="life_experience",
                        source_id=b.code,
                        priority="today",
                        urgency="none",
                        confidence=0.85,
                        actions=[
                            HomeAction(
                                id="open_ora",
                                label="Continua con ORA",
                                kind="navigate",
                                route="/life-setup?resume=1",
                                primary=True,
                            )
                        ],
                        reason_factors=[
                            ReasonFactor(
                                code=b.code,
                                label=b.title,
                                weight=0.8,
                                detail=b.user_benefit,
                            )
                        ],
                        reason_summary=b.user_benefit,
                        meta={
                            "wizard": False,
                            "life_setup_section": False,
                            "benefit_code": b.code,
                            "domain": b.domain,
                            "chain": b.chain,
                            "forbidden_copy_codes": ["completa_il_profilo", "life_setup"],
                        },
                    )
                )
    except Exception:
        pass

    # 2) Soft resume only if interrupted/skipped and no completed session after
    try:
        done = await db.life_setup_sessions.find_one(
            {"user_id": user_id, "status": "completed"},
            {"_id": 0, "id": 1},
        )
        if done:
            return items, []

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
            return items, []

        # Avoid duplicating if we already have benefit cards
        if items:
            return items, []

        items.append(
            HomeItem(
                id=f"life_experience_resume:{sess['id']}",
                type="insight",
                subtype="life_experience_resume",
                title="ORA può aiutarti ancora di più",
                description=(
                    "Quando vuoi, raccontami un pezzo della tua vita "
                    "o carica un documento utile."
                ),
                source_type="life_experience",
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
                        code="life_experience_soft_resume",
                        label="Ripresa gentile",
                        weight=0.5,
                        detail="Nessun wizard; nessun «completa il profilo».",
                    )
                ],
                reason_summary="Suggerimento unico dopo un'interruzione — non una sezione da completare.",
                meta={
                    "wizard": False,
                    "life_setup_section": False,
                    "forbidden_copy_codes": ["completa_il_profilo", "life_setup"],
                },
            )
        )
    except Exception:
        return items, []
    return items, []
