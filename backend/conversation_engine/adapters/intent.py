"""Intent Engine adapter — classify natural language input."""
from __future__ import annotations

from typing import Any, Dict, Optional

from intent_engine import get_intent_engine
from intent_engine.models import IntentResult


class IntentAdapter:
    def __init__(self, *, use_llm: bool = False):
        self.use_llm = use_llm
        self._engine = get_intent_engine()

    async def classify(
        self,
        text: str,
        *,
        description: Optional[str] = None,
        source_type: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> IntentResult:
        return await self._engine.classify(
            text or "",
            description=description,
            source_type=source_type,
            item_type=None,
            meta=meta,
            use_llm=self.use_llm,
        )

    @staticmethod
    def to_dict(intent: IntentResult) -> Dict[str, Any]:
        return intent.model_dump() if hasattr(intent, "model_dump") else dict(intent)
