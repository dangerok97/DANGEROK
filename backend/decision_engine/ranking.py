"""
DecisionRanking — orchestrates evaluator + reasoner and produces the final
ordered list of decisions with attached `score`, `reason`, and `tags`.

Kept intentionally thin: it's the composition point, not a place for logic.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .context import DecisionContext
from .evaluator import DecisionEvaluator
from .reasoner import DecisionReasoner


class DecisionRanking:
    def __init__(self, evaluator: DecisionEvaluator, reasoner: DecisionReasoner):
        self.evaluator = evaluator
        self.reasoner = reasoner

    def rank(self, ctx: DecisionContext) -> List[Dict[str, Any]]:
        open_decisions = [d for d in ctx.decisions if d.get("status", "open") == "open"]
        enriched: List[Dict[str, Any]] = []
        for d in open_decisions:
            base = self.evaluator.base_score(d)
            delta, reason, tags = self.reasoner.evaluate(d, ctx)
            copy = dict(d)
            copy["base_score"] = base
            copy["score"] = round(base + delta, 2)
            copy["reason"] = reason
            copy["reason_tags"] = tags
            enriched.append(copy)

        enriched.sort(key=lambda x: x["score"], reverse=True)
        return enriched
