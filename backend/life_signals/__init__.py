"""Life Change Signal (V2.9.1) — event-driven foundation for Continuous Life
Reasoning.

`life mutation → LifeChangeSignal → [V2.9.2] impact reasoning →
[V2.9.3] attention → intervention`.

V2.9.1 stops at the signal: it answers "WHAT CHANGED?" and deliberately not
"SO WHAT?" or "SHOULD I SPEAK?". It creates no proactive suggestion, sends no
notification, calls no LLM, and runs no background worker.
"""

from life_signals.models import LifeChangeSignal
from life_signals.service import LifeSignalService

__all__ = ["LifeChangeSignal", "LifeSignalService"]
