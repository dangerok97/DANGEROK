"""Impact Reasoning (V2.9.2) — the "SO WHAT?" layer.

`LifeChangeSignal → bounded context → one reasoning call → ImpactAssessment`.

V2.9.2 works out what a change might MEAN. It does not decide whether ORA
should say anything about it — that is V2.9.3. It creates no suggestion, no
notification and no message, and executes no tool.
"""

from life_reasoning.models import Impact, ImpactAssessment
from life_reasoning.service import ImpactReasoningService

__all__ = ["Impact", "ImpactAssessment", "ImpactReasoningService"]
