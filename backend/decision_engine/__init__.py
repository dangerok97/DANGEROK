"""
Decision Engine — the reasoning core of ORA.

Public entry points:
    from decision_engine import DecisionService, DecisionContext

Everything else is internal; each component is replaceable via constructor
injection on DecisionService (evaluator/reasoner/ranking).
"""
from .context import DecisionContext
from .evaluator import DecisionEvaluator
from .reasoner import DecisionReasoner
from .ranking import DecisionRanking
from .service import DecisionService

__all__ = [
    "DecisionContext",
    "DecisionEvaluator",
    "DecisionReasoner",
    "DecisionRanking",
    "DecisionService",
]
