"""Shadow orchestration service (iter17)."""
from __future__ import annotations
import os, time, uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .rules import ALL_RULES, _is_urgent, _is_critical
from .scoring import apply_confidence, clip_per_rule, aggregate
from .storage import ShadowStorage, make_idempotency_key, emit
from .types import ShadowEvaluation, ShadowRuleResult, RULE_SET_VERSION


def _flags_on() -> bool:
    prof = os.environ.get("BEHAVIOR_PROFILE_ENABLED", "false").strip().lower() in ("1","true","yes","on")
    shad = os.environ.get("BEHAVIOR_SHADOW_MODE", "false").strip().lower() in ("1","true","yes","on")
    return prof and shad


class BehaviorShadowService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.storage = ShadowStorage(db)

    async def ensure_ready(self):
        await self.storage.ensure_indexes()

    def _zero_eval(self, user_id: str, decision: Dict[str, Any], *, reason: str) -> ShadowEvaluation:
        return ShadowEvaluation(
            evaluation_id=f"sh_zero_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            decision_id=decision.get("id", ""),
            effective_score=float(decision.get("score") or 0),
            shadow_priority_delta=0.0,
            shadow_score=float(decision.get("score") or 0),
            confidence="low",
            rules_applied=[],
            rules_evaluated=[],
            ranking_applied=False,
            created_at=datetime.now(timezone.utc),
            duration_ms=0.0,
        )

    async def evaluate(self, user_id: str, decision: Dict[str, Any],
                       *, context_hash: Optional[str] = None) -> ShadowEvaluation:
        t0 = time.perf_counter()
        emit("shadow_evaluation_started", user_id=user_id, decision_id=decision.get("id"))
        if not _flags_on():
            emit("shadow_evaluation_skipped", reason="flags_off")
            return self._zero_eval(user_id, decision, reason="flags_off")

        try:
            # Lazy import to keep decoupled when flags are off
            from behavioral_intelligence import BehavioralIntelligenceService
            bi = BehavioralIntelligenceService(self.db)
            profile = (await bi.get_profile(user_id, persist=False)).model_dump()
            metrics = (await bi.get_metrics(user_id, persist=False)).model_dump()
        except Exception as e:
            emit("shadow_evaluation_failed", stage="profile_fetch", err=type(e).__name__)
            return self._zero_eval(user_id, decision, reason="profile_error")

        # Idempotency key — stable across recomputes with same underlying data.
        # We derive profile "version" from sample_size + confidence bucket (both
        # monotone snapshots of the underlying behavior), NOT from computed_at
        # which changes on every call.
        profile_version = f"n={profile.get('sample_size', 0)}|c={profile.get('confidence', 'low')}"
        idem = make_idempotency_key(
            user_id, decision.get("id", ""), decision.get("updated_at"),
            profile_version,
            context_hash,
            RULE_SET_VERSION,
        )
        existing = await self.storage.find_by_idem(idem)
        if existing:
            emit("shadow_evaluation_skipped", reason="idempotent", evaluation_id=existing.get("evaluation_id"))
            existing.pop("_id", None)
            existing.pop("idempotency_key", None)
            return ShadowEvaluation(**existing)

        # Run all rules
        now_hour = datetime.now(timezone.utc).hour
        raw: List[ShadowRuleResult] = [fn(decision, profile, now_hour, metrics) for fn in ALL_RULES]
        confidence_scaled = apply_confidence(raw)
        capped = clip_per_rule(confidence_scaled)
        total, cap_hit, applied = aggregate(capped, decision)
        effective = float(decision.get("score") or 0)
        eval_conf = profile.get("confidence", "low")

        ev = ShadowEvaluation(
            evaluation_id=f"sh_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            decision_id=decision.get("id", ""),
            effective_score=effective,
            shadow_priority_delta=total,
            shadow_score=round(effective + total, 3),
            confidence=eval_conf,
            rules_applied=applied,
            rules_evaluated=capped,
            ranking_applied=False,  # HARD invariant
            behavior_profile_version=profile.get("confidence", "v1.0"),
            decision_version=str(decision.get("updated_at") or ""),
            rule_set_version=RULE_SET_VERSION,
            context_hash=context_hash,
            created_at=datetime.now(timezone.utc),
            duration_ms=(time.perf_counter() - t0) * 1000,
            cap_hit=cap_hit,
        )
        # Persist append-only
        doc = ev.model_dump()
        doc["idempotency_key"] = idem
        try:
            await self.storage.insert(doc)
        except Exception as e:
            emit("shadow_evaluation_failed", stage="insert", err=type(e).__name__)
            # still return the computed evaluation
        emit("shadow_evaluation_completed", evaluation_id=ev.evaluation_id,
             delta_bucket=("neg" if total < 0 else "pos" if total > 0 else "zero"),
             rule_applied_count=len(applied), duration_ms=round(ev.duration_ms, 2))
        return ev

    async def evaluate_batch(self, user_id: str, decisions: List[Dict[str, Any]]) -> List[ShadowEvaluation]:
        out = []
        for d in decisions:
            try:
                out.append(await self.evaluate(user_id, d))
            except Exception as e:
                emit("shadow_evaluation_failed", stage="batch", err=type(e).__name__)
                out.append(self._zero_eval(user_id, d, reason="exception"))
        return out
