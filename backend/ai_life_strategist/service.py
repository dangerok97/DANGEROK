"""AI Life Strategist service facade."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Set

from ai_life_strategist import cache as strategist_cache
from ai_life_strategist.benefit_engine import active_benefits, available_benefits
from ai_life_strategist.conversation_planner import (
    build_active_turn,
    build_greeting_turn,
    build_resume_suggestion,
    wrap_up_turn,
)
from ai_life_strategist.knowledge_gap import compute_gaps, infer_domain_from_text, infer_known_from_text
from ai_life_strategist.models import DOMAINS, ReasoningContext, StrategistPlan
from ai_life_strategist.policy import sanitize_known_facts, user_text_is_credential_dump
from ai_life_strategist.reasoner import reason

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
    def enabled(self) -> bool:
        return ai_life_strategist_enabled()

    def domains(self) -> List[Dict[str, str]]:
        from ai_life_strategist.models import DOMAIN_ICONS, DOMAIN_LABELS_IT

        return [
            {"id": d, "label": DOMAIN_LABELS_IT[d], "icon": DOMAIN_ICONS.get(d, "grid")}
            for d in DOMAINS
        ]

    def build_context(
        self,
        user_id: str,
        *,
        known_facts: Optional[Dict[str, Any]] = None,
        asked_questions: Optional[List[str]] = None,
        asked_keys: Optional[List[str]] = None,
        linked_doc_types: Optional[List[str]] = None,
        last_user_text: Optional[str] = None,
        session_phase: str = "active",
        domains_touched: Optional[List[str]] = None,
    ) -> ReasoningContext:
        facts = sanitize_known_facts(dict(known_facts or {}))
        if last_user_text and not user_text_is_credential_dump(last_user_text):
            facts.update(infer_known_from_text(last_user_text))
        known_keys: Set[str] = {k for k, v in facts.items() if v not in (None, False, "", [])}
        gaps = compute_gaps(known_keys, asked_keys=set(asked_keys or []))
        avail = available_benefits(known_keys)
        active = active_benefits(known_keys)
        touched = list(domains_touched or [])
        inferred = infer_domain_from_text(last_user_text or "")
        if inferred and inferred not in touched:
            touched.append(inferred)
        return ReasoningContext(
            user_id=user_id,
            domains_touched=touched,
            known_facts=facts,
            missing_keys=[g.key for g in gaps],
            asked_questions=list(asked_questions or []),
            linked_doc_types=list(linked_doc_types or []),
            last_user_text=last_user_text,
            session_phase=session_phase,
            benefits_available=[b.code for b in avail],
            benefits_active=[b.code for b in active],
        )

    async def next_question(
        self,
        user_id: str,
        *,
        known_facts: Optional[Dict[str, Any]] = None,
        asked_questions: Optional[List[str]] = None,
        asked_keys: Optional[List[str]] = None,
        linked_doc_types: Optional[List[str]] = None,
        last_user_text: Optional[str] = None,
        session_phase: str = "active",
        domains_touched: Optional[List[str]] = None,
        force_fallback: bool = False,
        use_cache: bool = True,
    ) -> StrategistPlan:
        if not self.enabled():
            # Still return deterministic plan so Life Setup can run offline of flag misuse
            force_fallback = True

        ctx = self.build_context(
            user_id,
            known_facts=known_facts,
            asked_questions=asked_questions,
            asked_keys=asked_keys,
            linked_doc_types=linked_doc_types,
            last_user_text=last_user_text,
            session_phase=session_phase,
            domains_touched=domains_touched,
        )

        cache_payload = {
            "known_keys": sorted(ctx.known_facts.keys()),
            "missing_keys": ctx.missing_keys[:20],
            "asked_questions": ctx.asked_questions[-10:],
            "linked_doc_types": ctx.linked_doc_types,
            "session_phase": ctx.session_phase,
            "focus_domain": (ctx.domains_touched[-1] if ctx.domains_touched else None),
            "last_user_text_hash": strategist_cache.text_hash(last_user_text),
            "benefits_available": ctx.benefits_available,
            "benefits_active": ctx.benefits_active,
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
        plan = await self.next_question(user_id, **kwargs)
        if phase == "greeting" and not kwargs.get("last_user_text"):
            return build_greeting_turn(plan)
        if plan.meta.get("phase") == "wrap":
            return wrap_up_turn(
                domains=kwargs.get("domains_touched") or [plan.domain],
                benefits=[plan.expected_benefit],
            )
        return build_active_turn(plan, ack=ack)

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
