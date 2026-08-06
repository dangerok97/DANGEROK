"""Explainability payload — reason + structured factors, no chain-of-thought."""
from __future__ import annotations

from typing import List, Optional

from proactive_engine.models import ScoreFactor, SuggestionExplain


def build_explain(
    *,
    reason: str,
    factors: List[ScoreFactor],
    gate_notes: Optional[List[str]] = None,
    would_speak: bool = True,
) -> SuggestionExplain:
    # Cap factors for UI — keep top by |weight*value|
    ranked = sorted(
        factors,
        key=lambda f: abs(float(f.weight) * float(f.value)),
        reverse=True,
    )[:8]
    summary = (reason or "").strip()
    if not summary and ranked:
        summary = ranked[0].label
    return SuggestionExplain(
        summary=summary or "Intervento valutato da ORA",
        factors=ranked,
        would_assistant_speak=would_speak,
        gate_notes=list(gate_notes or []),
    )
