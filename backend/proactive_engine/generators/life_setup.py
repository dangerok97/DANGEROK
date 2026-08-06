"""Proactive generator — benefit-driven Life Experience suggestions (Italian).

Never «Completa il profilo». Always explain the concrete benefit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Set

from proactive_engine.models import SuggestionAction, SuggestionCandidate


async def _known_keys(db, user_id: str) -> Set[str]:
    keys: Set[str] = set()
    try:
        from life_setup.profile_service import LifeProfileService

        prof = await LifeProfileService(db).get(user_id)
        if prof:
            for k, v in LifeProfileService(db).flat_known(prof).items():
                if v not in (None, False, "", []):
                    keys.add(k)
    except Exception:
        pass
    try:
        sess = await db.life_setup_sessions.find_one(
            {"user_id": user_id},
            {"_id": 0, "known_facts": 1, "status": 1},
            sort=[("updated_at", -1)],
        )
        if sess:
            for k, v in (sess.get("known_facts") or {}).items():
                if v not in (None, False, "", []):
                    keys.add(k)
    except Exception:
        pass
    return keys


async def generate_life_setup_candidates(
    db, user_id: str, *, now: Optional[datetime] = None,
) -> List[SuggestionCandidate]:
    now = now or datetime.now(timezone.utc)
    out: List[SuggestionCandidate] = []

    # Benefit-driven proactive (after knowledge exists)
    try:
        from ai_life_strategist.benefit_engine import proactive_benefit_suggestions

        known = await _known_keys(db, user_id)
        for b in proactive_benefit_suggestions(known, limit=3):
            if not b.proactive_signal:
                continue
            out.append(
                SuggestionCandidate(
                    title=b.title,
                    description=b.proactive_signal,
                    reason=b.user_benefit,
                    type="life",
                    source="life_experience_benefit",
                    action=SuggestionAction(
                        kind="life_benefit",
                        label="Vedi su Home",
                        route="/(tabs)",
                        params={"benefit_code": b.code, "domain": b.domain},
                    ),
                    dedupe_key=f"life_benefit:{b.code}:{user_id}",
                    evidence={"benefit_code": b.code, "domain": b.domain, "chain": b.chain},
                    meta={
                        "wizard": False,
                        "forbidden": ["Completa il profilo", "Life Setup"],
                        "benefit_code": b.code,
                    },
                    importance_hint=0.7,
                    urgency_hint=0.45,
                    confidence=0.82,
                )
            )
    except Exception:
        pass

    # Soft resume if interrupted and never completed
    try:
        done = await db.life_setup_sessions.find_one(
            {"user_id": user_id, "status": "completed"},
            {"_id": 0, "id": 1},
        )
        if done:
            return out

        sess = await db.life_setup_sessions.find_one(
            {
                "user_id": user_id,
                "status": {"$in": ["interrupted", "skipped"]},
            },
            {"_id": 0},
            sort=[("updated_at", -1)],
        )
        if not sess:
            return out

        # Prefer benefit cards over resume if we already have them
        if out:
            return out

        out.append(
            SuggestionCandidate(
                title="ORA può aiutarti ancora di più",
                description=(
                    "Quando vuoi, raccontami un pezzo della tua vita "
                    "o carica un documento utile."
                ),
                reason="Hai interrotto la prima conversazione — un solo suggerimento gentile.",
                type="life",
                source="life_experience_interrupt",
                action=SuggestionAction(
                    kind="resume_life_conversation",
                    label="Continua con ORA",
                    route="/life-setup?resume=1",
                    params={"life_setup_session_id": sess.get("id")},
                ),
                dedupe_key=f"life_experience_resume:{user_id}",
                evidence={"life_setup_session_id": sess.get("id")},
                meta={"wizard": False, "forbidden": ["Completa il profilo", "Life Setup"]},
                importance_hint=0.55,
                urgency_hint=0.3,
                confidence=0.8,
            )
        )
    except Exception:
        return out
    return out
