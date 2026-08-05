"""Optional LLM enricher — never required; deterministic result always wins as baseline."""
from __future__ import annotations

import logging
import os
from typing import Optional

from intent_engine.models import IntentResult

logger = logging.getLogger("ora.intent_engine.enricher")

VALID_INTENTS = frozenset({
    "study", "travel", "event", "medical", "payment", "financial",
    "administrative", "document_review", "task", "communication",
    "shopping", "project", "generic",
})


def llm_enrichment_enabled() -> bool:
    return os.environ.get("INTENT_LLM_ENRICH", "0").lower() in ("1", "true", "yes", "on")


async def maybe_enrich(
    text: str,
    baseline: IntentResult,
    *,
    force: bool = False,
) -> IntentResult:
    """Optionally ask LLM when confidence is middling. Failures → baseline unchanged."""
    if not force and not llm_enrichment_enabled():
        return baseline
    # Only enrich ambiguous band; never override high-confidence deterministic
    if baseline.confidence >= 0.85 and not baseline.needs_clarify and not force:
        return baseline
    if baseline.confidence < 0.35 and not force:
        # Too empty — clarify UI already handles it
        return baseline

    try:
        from llm import chat_json, LLMNotConfigured
    except Exception:
        return baseline

    prompt = (
        "Classifica l'intento dell'utente. Rispondi SOLO JSON con chiavi: "
        "intent, subtype, confidence (0-1), reason, entities (oggetto con subject/place/amount). "
        f"Intenti validi: {sorted(VALID_INTENTS)}. "
        "Se è studio/esame usa intent=study subtype=exam_preparation. "
        f"Testo: {text[:500]}"
    )
    try:
        data = await chat_json(
            [
                {"role": "system", "content": "Sei un classificatore di intenti. Nessuna chiacchiera."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
    except LLMNotConfigured:
        return baseline
    except Exception as e:
        logger.info("intent LLM enrich skipped: %s", type(e).__name__)
        return baseline

    if not isinstance(data, dict):
        return baseline
    intent = str(data.get("intent") or "").lower().strip()
    if intent not in VALID_INTENTS:
        return baseline

    # Merge carefully: LLM can raise confidence only if agrees with baseline top-2
    llm_conf = float(data.get("confidence") or 0.5)
    if intent == baseline.intent:
        baseline.confidence = max(baseline.confidence, min(0.97, (baseline.confidence + llm_conf) / 2 + 0.05))
        baseline.reason = (baseline.reason or "") + " + llm_confirm"
        if data.get("subtype") and not baseline.subtype:
            baseline.subtype = str(data.get("subtype"))
        baseline.needs_clarify = baseline.confidence < 0.62
        if not baseline.needs_clarify:
            baseline.clarify_options = None
        return baseline

    # Disagreement → keep clarify, maybe adjust options
    baseline.needs_clarify = True
    baseline.reason = (baseline.reason or "") + f" + llm_disagree:{intent}"
    baseline.confidence = min(baseline.confidence, 0.5)
    return baseline
