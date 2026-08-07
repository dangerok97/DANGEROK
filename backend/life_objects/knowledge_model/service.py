"""KnowledgeModelService — read/write Digital Twin knowledge on a Life Object."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_objects.knowledge_model.decisions import (
    propose_decision,
    serialize_decisions,
    set_decision_outcome,
)
from life_objects.knowledge_model.facts import (
    FactImmutabilityError,
    delete_fact,
    facts_history_for_type,
    serialize_facts,
)
from life_objects.knowledge_model.hypotheses import (
    confirm_hypothesis,
    reject_hypothesis,
    serialize_hypotheses,
)
from life_objects.knowledge_model.integration import (
    apply_never_ask_filters,
    ensure_knowledge_migrated,
    ingest_properties_into_knowledge,
)
from life_objects.knowledge_model.memory_events import serialize_memory
from life_objects.knowledge_model.models import KnowledgeDecision
from life_objects.knowledge_model.timeline import build_timeline, serialize_timeline


class KnowledgeModelService:
    """Operates on LifeObject knowledge sections via LifeObjectRepository."""

    def __init__(self, repo):
        self.repo = repo

    async def _load(self, user_id: str, object_id: str):
        obj = await self.repo.get(user_id, object_id)
        if not obj:
            return None
        ensure_knowledge_migrated(obj)
        return obj

    async def get_facts(self, user_id: str, object_id: str) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        await self.repo.upsert(obj)  # persist migration if any
        return {
            "ok": True,
            "object_id": object_id,
            "facts": serialize_facts(obj.facts),
            "count": len(obj.facts or []),
            "rule": "facts_never_deleted",
        }

    async def get_hypotheses(self, user_id: str, object_id: str) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        await self.repo.upsert(obj)
        return {
            "ok": True,
            "object_id": object_id,
            "hypotheses": serialize_hypotheses(obj.hypotheses),
            "count": len(obj.hypotheses or []),
            "rule": "hypotheses_never_auto_promoted",
        }

    async def get_decisions(self, user_id: str, object_id: str) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        await self.repo.upsert(obj)
        return {
            "ok": True,
            "object_id": object_id,
            "decisions": serialize_decisions(obj.decisions),
            "count": len(obj.decisions or []),
        }

    async def get_memory(self, user_id: str, object_id: str) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        await self.repo.upsert(obj)
        return {
            "ok": True,
            "object_id": object_id,
            "memory": serialize_memory(obj.memory),
            "count": len(obj.memory or []),
        }

    async def get_timeline(self, user_id: str, object_id: str) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        groups = build_timeline(
            memory=list(obj.memory or []),
            facts=list(obj.facts or []),
            history=list(obj.history or []),
        )
        await self.repo.upsert(obj)
        return {
            "ok": True,
            "object_id": object_id,
            "timeline": serialize_timeline(groups),
            "groups_count": len(groups),
            "goals": list(obj.goals or []),
        }

    async def get_knowledge(self, user_id: str, object_id: str) -> Dict[str, Any]:
        """Aggregate read: five sections + timeline."""
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        groups = build_timeline(
            memory=list(obj.memory or []),
            facts=list(obj.facts or []),
            history=list(obj.history or []),
        )
        await self.repo.upsert(obj)
        return {
            "ok": True,
            "object_id": object_id,
            "type": obj.type,
            "title": obj.title,
            "facts": serialize_facts(obj.facts),
            "hypotheses": serialize_hypotheses(obj.hypotheses),
            "decisions": serialize_decisions(obj.decisions),
            "goals": list(obj.goals or []),  # link-only, no Goal Engine duplication
            "memory": serialize_memory(obj.memory),
            "timeline": serialize_timeline(groups),
            "rules": {
                "facts_never_deleted": True,
                "hypotheses_never_auto_promoted": True,
                "gemini_consultant_backend_authority": True,
            },
        }

    async def propose_hypothesis(
        self,
        user_id: str,
        object_id: str,
        *,
        type: str,
        value: Any = None,
        confidence: float = 0.4,
        reason: str = "",
        question_to_confirm: str = "",
        evidence: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        from life_objects.knowledge_model.hypotheses import add_hypothesis
        from life_objects.knowledge_model.models import KnowledgeHypothesis

        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        hyp = KnowledgeHypothesis(
            type=type,
            value=value,
            confidence=confidence,
            reason=reason or "Ipotesi proposta (internal)",
            question_to_confirm=question_to_confirm or f"Confermi {type} = {value}?",
            evidence=list(evidence or []),
            status="active",
            source="api",
            life_object_id=obj.id,
        )
        obj.hypotheses = add_hypothesis(list(obj.hypotheses or []), hyp)
        await self.repo.upsert(obj)
        return {"ok": True, "hypothesis": hyp.model_dump(), "object_id": object_id}

    async def confirm_hypothesis(
        self,
        user_id: str,
        object_id: str,
        *,
        hypothesis_id: str,
        verified_by: str = "user",
    ) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        res = confirm_hypothesis(
            hypotheses=list(obj.hypotheses or []),
            facts=list(obj.facts or []),
            hypothesis_id=hypothesis_id,
            verified_by=verified_by,
            life_object_id=obj.id,
        )
        if not res.get("ok"):
            return res
        obj.hypotheses = res["hypotheses"]
        obj.facts = res["facts"]
        await self.repo.upsert(obj)
        return {
            "ok": True,
            "fact": res.get("fact").model_dump() if res.get("fact") else None,
            "hypothesis": res.get("hypothesis").model_dump() if res.get("hypothesis") else None,
            "object_id": object_id,
        }

    async def reject_hypothesis(
        self,
        user_id: str,
        object_id: str,
        *,
        hypothesis_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        res = reject_hypothesis(
            list(obj.hypotheses or []), hypothesis_id, reason=reason,
        )
        if not res.get("ok"):
            return res
        obj.hypotheses = res["hypotheses"]
        await self.repo.upsert(obj)
        return {
            "ok": True,
            "hypothesis": res["hypothesis"].model_dump(),
            "object_id": object_id,
        }

    async def set_decision_outcome(
        self,
        user_id: str,
        object_id: str,
        *,
        decision_id: str,
        outcome: str,
        user_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        res = set_decision_outcome(
            list(obj.decisions or []),
            decision_id,
            outcome=outcome,
            user_choice=user_choice,
        )
        if not res.get("ok"):
            return res
        obj.decisions = res["decisions"]
        if outcome == "never_ask_again":
            apply_never_ask_filters(obj)
        await self.repo.upsert(obj)
        return {
            "ok": True,
            "decision": res["decision"].model_dump(),
            "object_id": object_id,
        }

    async def propose_decision(
        self,
        user_id: str,
        object_id: str,
        *,
        title: str,
        reason: str = "",
        benefit: str = "",
        risk: str = "",
        alternatives: Optional[List[str]] = None,
        ai_reasoning: str = "",
        kind: str = "suggestion",
    ) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        res = propose_decision(
            list(obj.decisions or []),
            KnowledgeDecision(
                life_object_id=obj.id,
                title=title,
                reason=reason or title,
                benefit=benefit,
                risk=risk,
                alternatives=list(alternatives or []),
                ai_reasoning=ai_reasoning,
                kind=kind,
                outcome="pending",
            ),
        )
        obj.decisions = res["decisions"]
        await self.repo.upsert(obj)
        return {
            "ok": True,
            "suppressed": bool(res.get("suppressed")),
            "created": bool(res.get("created")),
            "decision": res["decision"].model_dump() if res.get("decision") else None,
            "object_id": object_id,
        }

    async def fact_history(
        self, user_id: str, object_id: str, fact_type: str,
    ) -> Dict[str, Any]:
        obj = await self._load(user_id, object_id)
        if not obj:
            return {"ok": False, "error": "not_found"}
        hist = facts_history_for_type(list(obj.facts or []), fact_type)
        return {
            "ok": True,
            "object_id": object_id,
            "type": fact_type,
            "history": serialize_facts(hist),
            "count": len(hist),
        }

    def refuse_delete_fact(self, facts, fact_id: str) -> None:
        """Guard — always raises FactImmutabilityError."""
        delete_fact(facts, fact_id)


def get_knowledge_service(repo) -> KnowledgeModelService:
    return KnowledgeModelService(repo)


# Re-export for integration callers
__all__ = [
    "KnowledgeModelService",
    "get_knowledge_service",
    "ingest_properties_into_knowledge",
    "ensure_knowledge_migrated",
    "apply_never_ask_filters",
    "FactImmutabilityError",
]
