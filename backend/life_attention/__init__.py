"""Attention & Intervention Intelligence (V2.9.3) — the "SHOULD I SPEAK?" layer.

`ImpactAssessment → AttentionDecision → (only if permitted) the existing
Proactive Engine → Suggestion`.

V2.9.3 decides whether reasoning is worth the user's attention. Silence is a
first-class outcome and the most common correct one. The model proposes; a
deterministic system gate can only ever make the result quieter, never louder.
No push is ever dispatched.
"""

from life_attention.models import AttentionDecision
from life_attention.service import AttentionService

__all__ = ["AttentionDecision", "AttentionService"]
