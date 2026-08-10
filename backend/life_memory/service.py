"""Life Memory service — assemble → identity → optional Gemini wording → response.

life_memory_snapshots = DERIVED / REBUILDABLE cache — never source of truth.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from life_memory.assemble import assemble_life_memory
from life_memory.gemini_present import life_memory_gemini_enabled, polish_with_gemini
from life_memory.identity import apply_gemini_wordings, resolve_memory_candidates
from life_memory.models import LifeMemoryResponse, now_iso

logger = logging.getLogger("ora.life_memory")

CACHE_COLLECTION = "life_memory_snapshots"


def _cache_ttl_s() -> int:
    try:
        return max(60, int(os.environ.get("MEMORY_CACHE_TTL_SEC") or "900"))
    except Exception:
        return 900


def _debug_enabled() -> bool:
    return (os.environ.get("MEMORY_DEBUG") or "").strip().lower() in ("1", "true", "yes")


class LifeMemoryService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db[CACHE_COLLECTION].create_index("user_id", unique=True)
        await self.db[CACHE_COLLECTION].create_index([("user_id", 1), ("fingerprint", 1)])

    async def _load_sources(self, user_id: str) -> Dict[str, Any]:
        partial_sources: List[str] = []
        profile_dict: Dict[str, Any] = {}
        study_plans: List[Dict[str, Any]] = []
        user_notes: List[Dict[str, Any]] = []

        auth_user: Dict[str, Any] = {}
        try:
            from life_setup.profile_service import LifeProfileService

            ps = LifeProfileService(self.db)
            # Epistemic repair: Life Setup NLP leftovers (inferred utterance keys)
            try:
                await ps.repair_utterance_inferred_authority(user_id)
            except Exception as e:
                logger.info("life_memory authority repair soft-fail: %s", type(e).__name__)
            profile = await ps.get_or_create(user_id)
            profile_dict = profile.public() if profile else {}
        except Exception as e:
            logger.info("life_memory profile soft-fail: %s", type(e).__name__)
            partial_sources.append("life_profile")

        try:
            u = await self.db.users.find_one(
                {"user_id": user_id}, {"_id": 0, "name": 1, "email": 1}
            )
            auth_user = u or {}
        except Exception as e:
            logger.info("life_memory auth user soft-fail: %s", type(e).__name__)

        try:
            from action_engine.study.plan_service import StudyPlanService

            study_plans = await StudyPlanService(self.db).list_plans(user_id)
        except Exception as e:
            logger.info("life_memory study soft-fail: %s", type(e).__name__)
            partial_sources.append("study_plans")

        try:
            cursor = self.db.memories.find({"user_id": user_id}, {"_id": 0}).sort(
                "created_at", -1
            ).limit(40)
            user_notes = await cursor.to_list(40)
        except Exception as e:
            logger.info("life_memory notes soft-fail: %s", type(e).__name__)
            partial_sources.append("user_notes")

        return {
            "profile": profile_dict,
            "study_plans": study_plans,
            "user_notes": user_notes,
            "auth_user": auth_user,
            "partial_sources": partial_sources,
        }

    async def invalidate_cache(self, user_id: str) -> None:
        await self.db[CACHE_COLLECTION].delete_one({"user_id": user_id})

    async def _get_cache(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.db[CACHE_COLLECTION].find_one({"user_id": user_id}, {"_id": 0})

    async def _save_cache(
        self, user_id: str, *, fingerprint: str, wordings: List[Dict[str, str]]
    ) -> None:
        await self.db[CACHE_COLLECTION].update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "fingerprint": fingerprint,
                    "wordings": wordings,
                    "updated_at": now_iso(),
                }
            },
            upsert=True,
        )

    def _cache_fresh(self, cached: Dict[str, Any], fingerprint: str) -> bool:
        if not cached or cached.get("fingerprint") != fingerprint:
            return False
        raw = cached.get("updated_at") or ""
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
            return age <= _cache_ttl_s()
        except Exception:
            return False

    async def get_life_memory(
        self,
        user_id: str,
        *,
        force_refresh: bool = False,
        enrich: Optional[bool] = None,
    ) -> LifeMemoryResponse:
        sources = await self._load_sources(user_id)
        candidates, evidence, fingerprint = assemble_life_memory(
            profile=sources.get("profile"),
            study_plans=sources.get("study_plans"),
            user_notes=sources.get("user_notes"),
            auth_user=sources.get("auth_user"),
        )
        memories, groups, _notes = resolve_memory_candidates(candidates)

        want_ai = life_memory_gemini_enabled() if enrich is None else bool(enrich)
        ai_status: str = "off"
        wordings_pairs = None

        cached = await self._get_cache(user_id)
        if (
            want_ai
            and not force_refresh
            and cached
            and self._cache_fresh(cached, fingerprint)
            and cached.get("wordings")
        ):
            try:
                wordings_pairs = [
                    (str(w.get("memory_id")), str(w.get("statement")))
                    for w in (cached.get("wordings") or [])
                    if w.get("memory_id") and w.get("statement")
                ]
                ai_status = "cached"
            except Exception:
                wordings_pairs = None

        if want_ai and wordings_pairs is None:
            try:
                wordings_pairs = await polish_with_gemini(
                    memories=memories, evidence=evidence
                )
                if wordings_pairs:
                    ai_status = "fresh"
                    await self._save_cache(
                        user_id,
                        fingerprint=fingerprint,
                        wordings=[
                            {"memory_id": a, "statement": b} for a, b in wordings_pairs
                        ],
                    )
                else:
                    ai_status = "failed" if life_memory_gemini_enabled() else "skipped"
            except Exception as e:
                logger.info("life_memory enrich soft-fail: %s", type(e).__name__)
                ai_status = "failed"

        if wordings_pairs:
            memories = apply_gemini_wordings(memories, wordings_pairs)

        if not want_ai:
            ai_status = "off"

        if not _debug_enabled():
            for m in memories:
                m.resolution_source = None
                m.member_ids = []

        return LifeMemoryResponse(
            ok=True,
            memories=memories,
            groups=groups,
            evidence=evidence if _debug_enabled() else [],
            fingerprint=fingerprint,
            deterministic=True,
            ai_enrichment=ai_status,  # type: ignore[arg-type]
            partial=bool(sources.get("partial_sources")),
            partial_sources=list(sources.get("partial_sources") or []),
            generated_at=now_iso(),
        )


def get_life_memory_service(db=None) -> LifeMemoryService:
    if db is None:
        from deps import db as _db

        db = _db
    return LifeMemoryService(db)
