"""AI Life Strategist service facade — Life Experience reasoning loop."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from ai_life_strategist import cache as strategist_cache
from ai_life_strategist.conversation_planner import (
    build_active_turn,
    build_greeting_turn,
    build_resume_suggestion,
    wrap_up_turn,
)
from ai_life_strategist.models import DOMAINS, ReasoningContext, StrategistPlan
from ai_life_strategist.reasoner import reason
from ai_life_strategist.reasoning_loop import assemble_reasoning_context

logger = logging.getLogger("ora.ai_life_strategist")

_SERVICE: Optional["AILifeStrategistService"] = None


def ai_life_strategist_enabled() -> bool:
    raw = (os.environ.get("AI_LIFE_STRATEGIST_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_strategist_service() -> "AILifeStrategistService":
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AILifeStrategistService()
    return _SERVICE


class AILifeStrategistService:
    def __init__(self, db=None):
        self.db = db

    def enabled(self) -> bool:
        return ai_life_strategist_enabled()

    def domains(self) -> List[Dict[str, str]]:
        from ai_life_strategist.models import DOMAIN_ICONS, DOMAIN_LABELS_IT

        return [
            {"id": d, "label": DOMAIN_LABELS_IT[d], "icon": DOMAIN_ICONS.get(d, "grid")}
            for d in DOMAINS
        ]

    async def build_context(
        self,
        user_id: str,
        *,
        known_facts: Optional[Dict[str, Any]] = None,
        asked_questions: Optional[List[str]] = None,
        asked_keys: Optional[List[str]] = None,
        refused_keys: Optional[List[str]] = None,
        postponed_keys: Optional[List[str]] = None,
        linked_doc_types: Optional[List[str]] = None,
        last_user_text: Optional[str] = None,
        session_phase: str = "active",
        domains_touched: Optional[List[str]] = None,
        db=None,
    ) -> ReasoningContext:
        """Steps 1–7 of the AI Reasoning Loop."""
        return await assemble_reasoning_context(
            user_id,
            db=db if db is not None else self.db,
            known_facts=known_facts,
            asked_questions=asked_questions,
            asked_keys=asked_keys,
            refused_keys=refused_keys,
            postponed_keys=postponed_keys,
            linked_doc_types=linked_doc_types,
            last_user_text=last_user_text,
            session_phase=session_phase,
            domains_touched=domains_touched,
        )

    async def next_question(
        self,
        user_id: str,
        *,
        known_facts: Optional[Dict[str, Any]] = None,
        asked_questions: Optional[List[str]] = None,
        asked_keys: Optional[List[str]] = None,
        refused_keys: Optional[List[str]] = None,
        postponed_keys: Optional[List[str]] = None,
        linked_doc_types: Optional[List[str]] = None,
        last_user_text: Optional[str] = None,
        session_phase: str = "active",
        domains_touched: Optional[List[str]] = None,
        force_fallback: bool = False,
        use_cache: bool = True,
        db=None,
    ) -> StrategistPlan:
        if not self.enabled():
            force_fallback = True

        ctx = await self.build_context(
            user_id,
            known_facts=known_facts,
            asked_questions=asked_questions,
            asked_keys=asked_keys,
            refused_keys=refused_keys,
            postponed_keys=postponed_keys,
            linked_doc_types=linked_doc_types,
            last_user_text=last_user_text,
            session_phase=session_phase,
            domains_touched=domains_touched,
            db=db,
        )

        cache_payload = {
            "known_keys": sorted(ctx.known_facts.keys()),
            "missing_keys": ctx.missing_keys[:20],
            "asked_questions": ctx.asked_questions[-10:],
            "asked_keys": ctx.asked_keys[-20:],
            "refused_keys": ctx.refused_keys[-10:],
            "postponed_keys": ctx.postponed_keys[-10:],
            "linked_doc_types": ctx.linked_doc_types,
            "session_phase": ctx.session_phase,
            "focus_domain": (ctx.domains_touched[-1] if ctx.domains_touched else None),
            "last_user_text_hash": strategist_cache.text_hash(last_user_text),
            "benefits_available": ctx.benefits_available,
            "benefits_active": ctx.benefits_active,
            "highest_benefit": ctx.highest_benefit_code,
        }
        key = strategist_cache.make_key("next_q", user_id, cache_payload)
        if use_cache and not force_fallback:
            hit = strategist_cache.get(key)
            if hit:
                try:
                    plan = StrategistPlan.model_validate(hit)
                    plan.source = "cache"
                    return plan
                except Exception:
                    pass

        # Steps 8–9: build plan with ONE question; step 10 is wait (caller)
        plan = await reason(ctx, force_fallback=force_fallback)
        if use_cache:
            strategist_cache.set(key, plan.model_dump())
        return plan

    async def plan_turn(
        self,
        user_id: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        phase = kwargs.get("session_phase") or "active"
        ack = kwargs.pop("ack", None)
        last_bridge = kwargs.pop("last_bridge", None)
        force_fallback = bool(kwargs.get("force_fallback"))
        plan = await self.next_question(user_id, **kwargs)
        known = kwargs.get("known_facts") or {}
        if phase == "greeting" and not kwargs.get("last_user_text"):
            return build_greeting_turn(plan)
        if plan.meta.get("phase") == "wrap":
            return await wrap_up_turn(
                known_facts=known,
                domains=kwargs.get("domains_touched") or [plan.domain],
                benefits=[plan.expected_benefit],
                force_fallback=force_fallback or not self.enabled(),
            )
        return build_active_turn(
            plan,
            ack=ack,
            last_bridge=last_bridge,
            known_facts=known,
        )

    def resume_suggestion(self) -> Dict[str, Any]:
        return build_resume_suggestion()

    def explain_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        p = StrategistPlan.model_validate(plan) if not isinstance(plan, StrategistPlan) else plan
        return {
            "question": p.next_best_question,
            "reason": p.question_reason,
            "expected_benefit": p.expected_benefit,
            "user_explanation": p.explain_for_user(),
            "domain": p.domain,
            "prefer_document": p.prefer_document,
            "recommended_document": p.recommended_document.model_dump() if p.recommended_document else None,
            "information_gain": p.information_gain,
            "confidence": p.confidence,
        }
