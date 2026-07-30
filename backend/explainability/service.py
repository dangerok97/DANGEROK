"""ExplanationService — composes DecisionExplanation deterministically.

Reads:
  - the Decision doc,
  - the latest ContextSnapshot for the decision (optional),
  - today's DailySummary (optional),
  - Life Graph nodes linked to the decision (optional).

Writes NOTHING.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .rules import evaluate_rules
from .text import (
    classify_confidence,
    classify_impact,
    classify_postpone_risk,
    compose_human_summary,
    compose_reasoning_steps,
)
from .types import DECISION_EXPLANATION_VERSION, DataSource, DecisionExplanation


# Safe display names — the ONLY strings that may appear in `data_sources`.
_SOURCE_NAME_GOOGLE = "Google Calendar"
_SOURCE_NAME_LIFE = "Life Graph"
_SOURCE_NAME_KNOWLEDGE = "Knowledge Layer"
_SOURCE_NAME_DAILY = "Daily Intelligence"
_SOURCE_NAME_MANUAL = "Manual Input"

_SAFE_SOURCES = {
    _SOURCE_NAME_GOOGLE, _SOURCE_NAME_LIFE, _SOURCE_NAME_KNOWLEDGE,
    _SOURCE_NAME_DAILY, _SOURCE_NAME_MANUAL,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExplanationService:
    def __init__(self, db, *, life_graph, context_asm, decisions, daily):
        self.db = db
        self.life_graph = life_graph
        self.context_asm = context_asm
        self.decisions = decisions
        self.daily = daily

    async def _load_context(
        self,
        user_id: str,
        decision: Dict[str, Any],
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        # Latest snapshot (may be absent)
        snapshot = await self.context_asm.latest(user_id, decision["id"])
        # Today's daily summary
        try:
            daily = (await self.daily.today(user_id)).to_dict()
        except Exception:
            daily = None
        # Linked nodes
        node_ids: List[str] = decision.get("node_ids") or []
        linked_nodes: List[Dict[str, Any]] = []
        if node_ids:
            cursor = self.db.life_nodes.find(
                {"user_id": user_id, "id": {"$in": node_ids}, "status": "active"},
                {"_id": 0, "id": 1, "type": 1, "label": 1, "attributes": 1},
            )
            linked_nodes = await cursor.to_list(length=len(node_ids))
        return snapshot, daily, linked_nodes

    def _extract_data_sources(
        self,
        *,
        decision: Dict[str, Any],
        snapshot: Optional[Dict[str, Any]],
        daily: Optional[Dict[str, Any]],
        linked_nodes: List[Dict[str, Any]],
    ) -> List[DataSource]:
        sources: List[DataSource] = []

        origin = (decision.get("origin") or "").lower()
        # 1) Google Calendar
        if origin.startswith("ingestion:calendar") or (decision.get("metadata") or {}).get("origin") == "ingestion:calendar":
            sources.append(DataSource(
                source=_SOURCE_NAME_GOOGLE,
                confidence="high",
                last_updated_at=decision.get("updated_at") or decision.get("created_at"),
                notes="Evento proveniente dal tuo calendario.",
            ))

        # 2) Life Graph
        if linked_nodes:
            latest_upd = max(
                [n.get("attributes", {}).get("updated_at") or "" for n in linked_nodes] or [""]
            ) or None
            sources.append(DataSource(
                source=_SOURCE_NAME_LIFE,
                confidence="high",
                last_updated_at=latest_upd,
                notes=f"Collegata a {len(linked_nodes)} elemento/i del Life Graph.",
            ))

        # 3) Knowledge Layer — inspect snapshot signals if available
        if snapshot:
            signals = snapshot.get("signals") or []
            know = [s for s in signals if s.get("source_module") == "knowledge"]
            if know:
                sources.append(DataSource(
                    source=_SOURCE_NAME_KNOWLEDGE,
                    confidence="high",
                    last_updated_at=snapshot.get("generated_at"),
                    notes=f"{len(know)} fatti strutturati considerati.",
                ))

        # 4) Daily Intelligence
        if daily:
            sources.append(DataSource(
                source=_SOURCE_NAME_DAILY,
                confidence=str(daily.get("confidence", "medium")),
                last_updated_at=daily.get("generated_at"),
                notes=f"Sintesi della giornata (score {daily.get('score')}).",
            ))

        # 5) Manual Input — anything the user typed directly
        if origin.startswith("user") or origin == "":
            sources.append(DataSource(
                source=_SOURCE_NAME_MANUAL,
                confidence="high",
                last_updated_at=decision.get("created_at"),
                notes="Impegno inserito manualmente.",
            ))

        # Safety net: strip any accidental non-safe name
        return [s for s in sources if s.source in _SAFE_SOURCES]

    def _build_context_used(
        self,
        *,
        snapshot: Optional[Dict[str, Any]],
        daily: Optional[Dict[str, Any]],
        linked_nodes: List[Dict[str, Any]],
    ) -> List[str]:
        items: List[str] = []
        if snapshot:
            items.append("Snapshot di contesto per la decisione")
        if daily:
            items.append("Sintesi della giornata")
        if linked_nodes:
            items.append(f"{len(linked_nodes)} nodo/i collegati")
        return items

    async def build(self, user_id: str, decision_id: str) -> Optional[DecisionExplanation]:
        decision = await self.decisions.get(user_id, decision_id)
        if not decision:
            return None

        snapshot, daily, linked_nodes = await self._load_context(user_id, decision)

        rules = evaluate_rules(decision=decision, linked_nodes=linked_nodes, daily=daily)
        applied_ids = {r.id for r in rules}

        summary = compose_human_summary(rules)
        steps = compose_reasoning_steps(rules)
        impact = classify_impact(decision)
        postpone_risk = classify_postpone_risk(decision, applied_ids)
        confidence = classify_confidence(
            has_snapshot=snapshot is not None,
            has_daily=daily is not None,
            rules_count=len(rules),
        )
        data_sources = self._extract_data_sources(
            decision=decision, snapshot=snapshot, daily=daily, linked_nodes=linked_nodes,
        )
        context_used = self._build_context_used(
            snapshot=snapshot, daily=daily, linked_nodes=linked_nodes,
        )

        return DecisionExplanation(
            decision_id=decision["id"],
            priority_score=decision.get("score"),
            confidence=confidence,
            estimated_duration_minutes=int(decision.get("time_required_min") or 15),
            estimated_impact=impact,
            estimated_postpone_risk=postpone_risk,
            generated_at=_now_iso(),
            human_summary=summary,
            reasoning_steps=steps,
            data_sources=[ds.to_dict() for ds in data_sources],
            applied_rules=[r.to_dict() for r in rules],
            context_used=context_used,
            version=DECISION_EXPLANATION_VERSION,
        )
