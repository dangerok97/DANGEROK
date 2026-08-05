"""Deterministic intent classifier — rules first, no LLM required."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from intent_engine.entities import extract_entities
from intent_engine.knowledge import (
    CLARIFY_LABELS,
    INTENT_PATTERNS,
    ITEM_TYPE_HINTS,
    NEGATIVE_OVERRIDES,
    SOURCE_HINTS,
    SUBTYPE_RULES,
)
from intent_engine.models import (
    CLASSIFIER_VERSION,
    CONFIDENCE_ACCEPT,
    CONFIDENCE_MARGIN,
    ClarifyOption,
    IntentResult,
)


def normalize(text: str) -> str:
    t = (text or "").lower().strip()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("'", "'").replace("'", "'")
    t = re.sub(r"\s+", " ", t)
    return t


def _pattern_hits(norm: str, patterns: List[Tuple[str, float]]) -> Tuple[float, List[str]]:
    score = 0.0
    hits: List[str] = []
    for pat, w in patterns:
        p = normalize(pat)
        if not p:
            continue
        # Phrase / token boundary-ish match
        if " " in p:
            if p in norm:
                score += w
                hits.append(pat)
        else:
            if re.search(rf"(?<!\w){re.escape(p)}(?!\w)", norm):
                score += w
                hits.append(pat)
    return score, hits


def _apply_hints(
    scores: Dict[str, float],
    *,
    source_type: Optional[str],
    item_type: Optional[str],
) -> List[str]:
    used: List[str] = []
    st = (source_type or "").lower().strip()
    it = (item_type or "").lower().strip()
    if st in SOURCE_HINTS:
        intent, boost = SOURCE_HINTS[st]
        scores[intent] = scores.get(intent, 0.0) + boost
        used.append(f"source:{st}->{intent}+{boost}")
    if it in ITEM_TYPE_HINTS:
        intent, boost = ITEM_TYPE_HINTS[it]
        # Weak item_type hints — never dominate strong text
        scores[intent] = scores.get(intent, 0.0) + boost
        used.append(f"item_type:{it}->{intent}+{boost}")
    return used


def _apply_negatives(scores: Dict[str, float], norm: str) -> None:
    for blocked, if_present, unless in NEGATIVE_OVERRIDES:
        if any(normalize(p) in norm for p in if_present):
            if not any(normalize(u) in norm for u in unless):
                if blocked in scores:
                    scores[blocked] *= 0.15


def _pick_subtype(intent: str, norm: str) -> Optional[str]:
    rules = SUBTYPE_RULES.get(intent) or []
    best_sub: Optional[str] = None
    best_score = 0.0
    for subtype, patterns in rules:
        sc, _ = _pattern_hits(norm, patterns)
        if sc > best_score:
            best_score = sc
            best_sub = subtype
    return best_sub if best_score >= 1.0 else None


def _confidence_from_scores(sorted_scores: List[Tuple[str, float]]) -> float:
    if not sorted_scores:
        return 0.0
    top_n, top_s = sorted_scores[0]
    if top_s <= 0:
        return 0.0
    second = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
    # Normalize: high absolute + clear margin
    base = min(0.95, 0.35 + top_s / 12.0)
    margin = top_s - second
    if margin < 1.0:
        base *= 0.55
    elif margin < 2.0:
        base *= 0.75
    elif margin >= 3.5:
        base = min(0.99, base + 0.12)
    if top_n == "generic" and top_s < 2.0:
        base = min(base, 0.4)
    return round(max(0.0, min(0.99, base)), 4)


def _clarify_options(top: List[Tuple[str, float]], n: int = 2) -> List[ClarifyOption]:
    opts: List[ClarifyOption] = []
    for intent, _sc in top[:n]:
        opts.append(ClarifyOption(
            id=f"clarify_{intent}",
            label=CLARIFY_LABELS.get(intent, intent),
            intent=intent,
            subtype=_pick_subtype(intent, "") if intent == "study" else None,
        ))
    # Always offer a clear study vs event pair when those compete
    intents = {o.intent for o in opts}
    if "study" in intents and "event" in intents:
        for o in opts:
            if o.intent == "study":
                o.label = "Preparare un esame"
                o.subtype = o.subtype or "exam_preparation"
            if o.intent == "event":
                o.label = "Creare un evento"
    return opts


def classify_deterministic(
    text: str,
    *,
    description: Optional[str] = None,
    source_type: Optional[str] = None,
    item_type: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> IntentResult:
    """Score intents from knowledge base + soft source hints. Pure / sync."""
    blob = " ".join(x for x in [text or "", description or ""] if x).strip()
    norm = normalize(blob)
    scores: Dict[str, float] = {k: 0.0 for k in INTENT_PATTERNS}
    hit_log: Dict[str, List[str]] = {}

    for intent, patterns in INTENT_PATTERNS.items():
        sc, hits = _pattern_hits(norm, patterns)
        scores[intent] = sc
        if hits:
            hit_log[intent] = hits

    hints_used = _apply_hints(scores, source_type=source_type, item_type=item_type)
    _apply_negatives(scores, norm)

    # Event keywords dominate weak travel "weekend" co-hit
    if scores.get("event", 0) >= 2.5 and scores.get("travel", 0) > 0:
        if "weekend" in norm and not any(
            x in norm for x in ("vacanza", "viaggio", "volare", "hotel", "ferie", "volo")
        ):
            scores["travel"] *= 0.35
    # "festa di laurea" is social event, not study
    if "festa" in norm and "laurea" in norm:
        scores["event"] = max(scores.get("event", 0), 4.5)
        scores["study"] *= 0.25
    # fattura/bolletta dominate adjacent financial noise
    if any(x in norm for x in ("fattura", "bolletta", "pagare", "bonifico")):
        if scores.get("payment", 0) >= 3.0:
            scores["financial"] *= 0.4
    # richiedere comunicazione: dampen weak task "chiamare" when richiamare/email/whatsapp
    if any(x in norm for x in ("richiamare", "email", "whatsapp", "messaggio")):
        scores["task"] *= 0.3
    # progetto + thesis language: if "progetto" present keep project ahead of study tesi
    if "progetto" in norm and scores.get("project", 0) >= 2.5:
        scores["study"] *= 0.45
        scores["generic"] *= 0.5

    # Precomputed intent on meta wins only as boost confirmation, not override
    meta = meta or {}
    if meta.get("forced_intent") in scores:
        scores[str(meta["forced_intent"])] += 8.0
        hints_used.append("forced_intent")

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_intent, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = _confidence_from_scores(ranked)

    # Empty / nonsense text
    if not norm or (top_score <= 0 and not hints_used):
        return IntentResult(
            intent="generic",
            subtype=None,
            confidence=0.2,
            reason="no_signals",
            needs_clarify=True,
            clarify_options=_clarify_options(
                [("study", 0), ("event", 0), ("task", 0)], n=3,
            ),
            scores=dict(ranked),
            source_hints_used=hints_used,
        )

    subtype = _pick_subtype(top_intent, norm)
    # Psychology / exam special: ensure exam_preparation
    if top_intent == "study" and re.search(r"esame|esami|prepar", norm):
        subtype = subtype or "exam_preparation"

    entities = extract_entities(blob, intent=top_intent)

    needs_clarify = False
    clarify: Optional[List[ClarifyOption]] = None
    margin = top_score - second_score

    # Unambiguous weak signal (only one intent scored) → accept without LLM
    if top_score >= 1.2 and second_score < 0.5 and top_intent != "generic":
        confidence = max(confidence, 0.68)
        needs_clarify = False

    # Soft item_type alone must not accept without text support
    text_supported = bool(hit_log.get(top_intent))
    if confidence < CONFIDENCE_ACCEPT or (margin < 1.5 and confidence < CONFIDENCE_ACCEPT + CONFIDENCE_MARGIN):
        needs_clarify = True
    if not text_supported and top_score < 2.5:
        needs_clarify = True
        confidence = min(confidence, 0.45)
    # Re-apply unambiguous / strong accept after soft checks
    if top_score >= 1.2 and second_score < 0.5 and top_intent != "generic" and text_supported:
        needs_clarify = False
        confidence = max(confidence, 0.68)
        clarify = None
    if top_score >= 3.0 and margin >= 1.0 and top_intent != "generic" and text_supported:
        needs_clarify = False
        confidence = max(confidence, 0.72)
        clarify = None
    if top_score >= 4.0 and margin >= 0.8 and text_supported:
        needs_clarify = False
        confidence = max(confidence, 0.78)
        clarify = None

    if needs_clarify:
        clarify = _clarify_options(ranked, n=2)
        # Human-readable Italian default pair when study/event compete
        if ranked[0][0] in ("study", "event") and ranked[1][0] in ("study", "event"):
            clarify = [
                ClarifyOption(
                    id="clarify_study",
                    label="Preparare un esame",
                    intent="study",
                    subtype="exam_preparation",
                ),
                ClarifyOption(
                    id="clarify_event",
                    label="Creare un evento",
                    intent="event",
                ),
            ]

    hits = hit_log.get(top_intent) or []
    reason_parts = []
    if hits:
        reason_parts.append("keywords:" + ",".join(hits[:5]))
    reason_parts.append("deterministic_rules")
    if hints_used:
        reason_parts.append("hints:" + ";".join(hints_used[:3]))

    # Final: high-confidence study for classic exam phrases
    if top_intent == "study" and subtype == "exam_preparation" and top_score >= 5.0:
        needs_clarify = False
        clarify = None
        confidence = max(confidence, 0.92)

    return IntentResult(
        intent=top_intent,  # type: ignore[arg-type]
        subtype=subtype,
        confidence=confidence,
        reason=" + ".join(reason_parts),
        entities=entities,
        clarify_options=clarify,
        needs_clarify=needs_clarify,
        classifier_version=CLASSIFIER_VERSION,
        scores={k: round(v, 3) for k, v in ranked if v > 0},
        source_hints_used=hints_used,
    )
