"""Optional Gemini structured extraction via Provider Manager — never decision-maker."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError

from semantic_engine.models import PROMPT_VERSION, EntityValue, DEFAULT_TZ

logger = logging.getLogger("ora.semantic_engine.gemini")

_TIMEOUT_MS = int(os.environ.get("SEMANTIC_GEMINI_TIMEOUT_MS", "8000"))
_MAX_RETRIES = int(os.environ.get("SEMANTIC_GEMINI_RETRIES", "1"))


class GeminiEntity(BaseModel):
    name: str
    raw: Any = None
    normalized: Any = None
    confidence: float = 0.0
    status: str = "known"
    label: Optional[str] = None
    ambiguity: Optional[Dict[str, Any]] = None


class GeminiExtractionPayload(BaseModel):
    entities: list[GeminiEntity] = Field(default_factory=list)
    reason_summary: str = ""
    flow_hint: Optional[str] = None


SYSTEM = (
    "Sei il modulo di estrazione semantica di ORA. "
    "Estrai SOLO entità strutturate in JSON. Non decidere azioni. Non scrivere catene di ragionamento. "
    "Campi: entities[{name,raw,normalized,confidence,status,label,ambiguity}], reason_summary, flow_hint. "
    "Date in ISO YYYY-MM-DD Europe/Rome. Se 'fra due settimane parto' → solo departure_date, NON inventare return_date. "
    "Non richiedere dati sensibili. Rispondi SOLO JSON valido."
)


def _ai_preference_allows(user_preference: Optional[str] = None) -> bool:
    pref = (user_preference or os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if pref in ("off", "none", "disabled"):
        return False
    flag = (os.environ.get("SEMANTIC_GEMINI_ENABLED") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return True


def _minimal_user_prompt(text: str, *, intent: Optional[str], known: Optional[Dict[str, Any]]) -> str:
    # Minimal context — no full docs / health / bank
    safe_known = {}
    if known:
        for k in ("destination", "subject", "departure_date", "return_date", "payee", "amount"):
            if k in known:
                safe_known[k] = known[k]
    return json.dumps(
        {
            "text": (text or "")[:800],
            "intent_hint": intent,
            "already_known": safe_known,
            "prompt_version": PROMPT_VERSION,
        },
        ensure_ascii=False,
    )


async def gemini_extract(
    text: str,
    *,
    intent: Optional[str] = None,
    known: Optional[Dict[str, Any]] = None,
    user_preference: Optional[str] = None,
    timezone: str = DEFAULT_TZ,
) -> tuple[Dict[str, EntityValue], Dict[str, Any]]:
    """Returns (entities, usage_meta). Empty entities on failure — caller falls back."""
    usage: Dict[str, Any] = {
        "provider": None,
        "model": None,
        "latency_ms": None,
        "prompt_version": PROMPT_VERSION,
        "attempted": False,
        "ok": False,
    }
    if not _ai_preference_allows(user_preference):
        usage["skipped"] = "ai_preference_or_disabled"
        return {}, usage

    try:
        from llm.manager import get_manager
        from llm.errors import LLMNotConfigured
    except Exception as e:
        usage["error"] = type(e).__name__
        return {}, usage

    mgr = get_manager()
    usage["attempted"] = True
    last_err = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            # Soft timeout via env; Provider Manager handles failover
            res = await mgr.chat(
                system=SYSTEM,
                user=_minimal_user_prompt(text, intent=intent, known=known),
                json_mode=True,
                user_preference=user_preference or "gemini",
            )
            usage["provider"] = res.provider
            usage["model"] = res.model
            usage["latency_ms"] = (res.usage or {}).get("latency_ms")
            usage["token_usage"] = {
                k: v for k, v in (res.usage or {}).items()
                if k in ("prompt_tokens", "completion_tokens", "total_tokens", "latency_ms")
            }
            payload = _parse_payload(res.text)
            entities: Dict[str, EntityValue] = {}
            for ge in payload.entities:
                entities[ge.name] = EntityValue(
                    raw=ge.raw,
                    normalized=ge.normalized,
                    confidence=float(ge.confidence or 0),
                    status=ge.status if ge.status in (
                        "known", "ambiguous", "inferred", "confirmed", "corrected", "missing", "low_confidence"
                    ) else "known",
                    source="gemini",
                    timezone=timezone,
                    ambiguity=ge.ambiguity,
                    label=ge.label,
                )
            usage["ok"] = True
            usage["reason_summary"] = payload.reason_summary
            usage["flow_hint"] = payload.flow_hint
            return entities, usage
        except LLMNotConfigured:
            usage["error"] = "LLMNotConfigured"
            return {}, usage
        except Exception as e:
            last_err = type(e).__name__
            logger.info("gemini extract attempt %s failed: %s", attempt, last_err)
            continue
    usage["error"] = last_err or "unknown"
    return {}, usage


def _parse_payload(text: str) -> GeminiExtractionPayload:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # try find object
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise
        data = json.loads(m.group(0))
    return GeminiExtractionPayload.model_validate(data)


async def optional_rephrase_question(
    template_question: str,
    *,
    slot: str,
    user_preference: Optional[str] = None,
) -> Optional[str]:
    """Optional Gemini phrasing that MUST keep the same slot meaning. Fail → None."""
    if not _ai_preference_allows(user_preference):
        return None
    if (os.environ.get("SEMANTIC_GEMINI_REPHRASE") or "0").strip().lower() not in ("1", "true", "yes"):
        return None
    try:
        from llm.manager import get_manager
        res = await get_manager().chat(
            system=(
                "Riformula in italiano breve la domanda ORA. "
                f"NON cambiare il significato dello slot '{slot}'. "
                "Una sola frase. Solo testo, no JSON."
            ),
            user=template_question[:300],
            json_mode=False,
            user_preference=user_preference or "gemini",
        )
        q = (res.text or "").strip().split("\n")[0].strip()
        if len(q) < 5 or len(q) > 180:
            return None
        return q
    except Exception:
        return None
