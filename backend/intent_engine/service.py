"""Intent Engine service — classify text → IntentResult."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from intent_engine.classifier import classify_deterministic
from intent_engine.enricher import maybe_enrich
from intent_engine.models import ClassifyBody, IntentResult

logger = logging.getLogger("ora.intent_engine")

_engine: Optional["IntentEngine"] = None


class IntentEngine:
    """Reusable single intent brain for Home, Parla, Documents, AE, etc."""

    def classify_sync(
        self,
        text: str,
        *,
        description: Optional[str] = None,
        source_type: Optional[str] = None,
        item_type: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> IntentResult:
        return classify_deterministic(
            text,
            description=description,
            source_type=source_type,
            item_type=item_type,
            meta=meta,
        )

    async def classify(
        self,
        text: str,
        *,
        description: Optional[str] = None,
        source_type: Optional[str] = None,
        item_type: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        use_llm: bool = False,
        precomputed: Optional[IntentResult] = None,
    ) -> IntentResult:
        if precomputed is not None:
            return precomputed
        result = self.classify_sync(
            text,
            description=description,
            source_type=source_type,
            item_type=item_type,
            meta=meta,
        )
        if use_llm:
            blob = " ".join(x for x in [text or "", description or ""] if x)
            result = await maybe_enrich(blob, result, force=True)
        return result

    async def classify_body(self, body: ClassifyBody) -> IntentResult:
        if body.intent is not None:
            return body.intent
        return await self.classify(
            body.text,
            description=body.description,
            source_type=body.source_type,
            item_type=body.item_type,
            meta=body.meta,
            use_llm=body.use_llm,
        )


def get_intent_engine() -> IntentEngine:
    global _engine
    if _engine is None:
        _engine = IntentEngine()
    return _engine


def classify_text(
    text: str,
    *,
    description: Optional[str] = None,
    source_type: Optional[str] = None,
    item_type: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> IntentResult:
    """Sync helper for adapters / decision create (no LLM)."""
    return get_intent_engine().classify_sync(
        text,
        description=description,
        source_type=source_type,
        item_type=item_type,
        meta=meta,
    )
