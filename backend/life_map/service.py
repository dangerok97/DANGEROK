"""Life Map service — assemble → identity resolve → optional AI → presentation.

life_map_snapshots = DERIVED / REBUILDABLE cache — never source of truth.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from life_map.assemble import assemble_life_map
from life_map.gemini_identity import resolve_identity_with_gemini
from life_map.gemini_interpret import interpret_with_gemini, life_map_gemini_enabled
from life_map.governance import merge_presentation
from life_map.identity import (
    apply_gemini_same_edges,
    canonical_to_presentation,
    resolve_candidates_deterministic,
)
from life_map.models import LifeMapInterpretation, LifeMapResponse, now_iso

logger = logging.getLogger("ora.life_map")

CACHE_COLLECTION = "life_map_snapshots"


def _log_identity_debug(candidates, canonicals, edges) -> None:
    """DEV-only identity trace — no emails/names; source ids + anchors only."""
    try:
        for c in candidates:
            if getattr(c, "kind", None) != "study":
                continue
            logger.info(
                "life_map.debug candidate id=%s source=%s:%s entity=%s anchor=%s "
                "lineage=%s evidence=%s updated=%s",
                c.candidate_id,
                c.source_type,
                c.source_id,
                (c.entity_raw or "")[:80],
                c.temporal_anchor,
                list(c.lineage_refs or [])[:6],
                list(c.evidence_refs or [])[:6],
                c.updated_at,
            )
        for e in edges:
            logger.info(
                "life_map.debug edge rel=%s source=%s reason=%s a=%s b=%s",
                e.relation,
                e.source,
                e.reason,
                e.a,
                e.b,
            )
        for can in canonicals:
            logger.info(
                "life_map.debug canonical id=%s title=%s anchor=%s members=%s refs=%s",
                can.identity.canonical_key,
                (can.title or "")[:80],
                can.identity.temporal_anchor,
                list(can.member_ids),
                list(can.identity.source_refs)[:8],
            )
    except Exception as ex:
        logger.info("life_map.debug soft-fail: %s", type(ex).__name__)


def _cache_ttl_s() -> int:
    try:
        return max(60, int(os.environ.get("LIFE_MAP_CACHE_TTL_SEC") or "900"))
    except Exception:
        return 900


class LifeMapService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db[CACHE_COLLECTION].create_index("user_id", unique=True)
        await self.db[CACHE_COLLECTION].create_index([("user_id", 1), ("fingerprint", 1)])

    async def _load_sources(self, user_id: str) -> Dict[str, Any]:
        from life_setup.profile_service import LifeProfileService

        profile_svc = LifeProfileService(self.db)
        profile = await profile_svc.get_or_create(user_id)
        profile_dict = profile.public() if profile else {}

        study_plans: List[Dict[str, Any]] = []
        travel_projects: List[Dict[str, Any]] = []
        life_os_plans: List[Dict[str, Any]] = []
        try:
            from action_engine.study.plan_service import StudyPlanService

            study_plans = await StudyPlanService(self.db).list_plans(user_id)
        except Exception as e:
            logger.info("life_map study list soft-fail: %s", type(e).__name__)
        try:
            from action_engine.travel.project_service import TravelProjectService

            travel_projects = await TravelProjectService(self.db).list_projects(user_id)
        except Exception as e:
            logger.info("life_map travel list soft-fail: %s", type(e).__name__)
        try:
            cur = (
                self.db.life_os_plans.find(
                    {"user_id": user_id, "status": {"$in": ["active", "paused"]}},
                    {"_id": 0},
                )
                .sort("updated_at", -1)
                .limit(20)
            )
            life_os_plans = await cur.to_list(20)
        except Exception as e:
            logger.info("life_map life_os list soft-fail: %s", type(e).__name__)

        return {
            "profile": profile_dict,
            "study_plans": study_plans,
            "travel_projects": travel_projects,
            "life_os_plans": life_os_plans,
        }

    async def _get_cache(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.db[CACHE_COLLECTION].find_one({"user_id": user_id}, {"_id": 0})

    async def _save_cache(
        self,
        user_id: str,
        *,
        fingerprint: str,
        interpretation: Optional[LifeMapInterpretation],
    ) -> None:
        doc = {
            "user_id": user_id,
            "fingerprint": fingerprint,
            "interpretation": interpretation.model_dump() if interpretation else None,
            "updated_at": now_iso(),
        }
        await self.db[CACHE_COLLECTION].update_one(
            {"user_id": user_id},
            {"$set": doc},
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

    async def get_life_map(
        self,
        user_id: str,
        *,
        force_refresh: bool = False,
        enrich: Optional[bool] = None,
    ) -> LifeMapResponse:
        sources = await self._load_sources(user_id)
        areas, _raw_situations, evidence, fingerprint, candidates = assemble_life_map(
            profile=sources.get("profile"),
            study_plans=sources.get("study_plans"),
            travel_projects=sources.get("travel_projects"),
            life_os_plans=sources.get("life_os_plans"),
        )

        # Identity resolution BEFORE presentation / Gemini enrich
        canonicals, det_edges = resolve_candidates_deterministic(candidates)
        if os.environ.get("LIFE_MAP_DEBUG", "").strip() in ("1", "true", "yes"):
            _log_identity_debug(candidates, canonicals, det_edges)

        want_ai = life_map_gemini_enabled() if enrich is None else bool(enrich)
        gemini_id_edges = []
        if want_ai and candidates:
            try:
                gemini_id_edges = await resolve_identity_with_gemini(
                    candidates, det_edges, max_pairs=8
                )
                if gemini_id_edges:
                    canonicals = apply_gemini_same_edges(
                        candidates, det_edges, gemini_id_edges
                    )
            except Exception as e:
                logger.info("life_map identity gemini soft-fail: %s", type(e).__name__)

        situations = [canonical_to_presentation(c) for c in canonicals]
        situations.sort(key=lambda s: (0 if s.temporal else 1, s.title))

        ai_status: str = "off"
        interpretation: Optional[LifeMapInterpretation] = None

        cached = await self._get_cache(user_id)
        if (
            want_ai
            and not force_refresh
            and cached
            and self._cache_fresh(cached, fingerprint)
            and cached.get("interpretation")
        ):
            try:
                interpretation = LifeMapInterpretation.model_validate(cached["interpretation"])
                ai_status = "cached"
            except Exception:
                interpretation = None

        if want_ai and interpretation is None:
            try:
                interpretation = await interpret_with_gemini(
                    areas=areas,
                    situations=situations,
                    evidence=evidence,
                )
                if interpretation:
                    ai_status = "fresh"
                    await self._save_cache(
                        user_id,
                        fingerprint=fingerprint,
                        interpretation=interpretation,
                    )
                else:
                    ai_status = "failed" if life_map_gemini_enabled() else "skipped"
            except Exception as e:
                logger.info("life_map enrich soft-fail: %s", type(e).__name__)
                ai_status = "failed"

        if not want_ai:
            ai_status = "off"

        evid_ids = {e.id for e in evidence}
        areas, situations = merge_presentation(
            areas=areas,
            situations=situations,
            interpretation=interpretation,
            valid_evidence_ids=evid_ids,
        )

        return LifeMapResponse(
            ok=True,
            areas=areas,
            situations=situations,
            evidence=evidence,
            interpretation=interpretation,
            fingerprint=fingerprint,
            deterministic=True,
            ai_enrichment=ai_status,  # type: ignore[arg-type]
            generated_at=now_iso(),
        )


def get_life_map_service(db=None) -> LifeMapService:
    if db is None:
        from deps import db as _db

        db = _db
    return LifeMapService(db)
