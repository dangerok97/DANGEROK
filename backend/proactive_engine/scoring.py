"""Deterministic suggestion scoring — never random."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from proactive_engine.models import ScoreFactor, SuggestionCandidate


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def score_candidate(
    cand: SuggestionCandidate,
    *,
    now: Optional[datetime] = None,
    goal: Optional[Dict[str, Any]] = None,
    brain_ctx: Optional[Dict[str, Any]] = None,
    calendar_busy: bool = False,
    learning_multiplier: float = 1.0,
) -> Tuple[float, float, float, List[ScoreFactor]]:
    """Return (score, importance, urgency, factors).

    Weights are fixed and explainable. Learning multiplier is bounded.

    `cand.quality_hint`, when supplied, contributes one additional bounded and
    explainable factor. It exists because importance/urgency/confidence alone
    top out around 0.54 for a candidate carrying neither a deadline nor a goal
    link — below the 0.55 "assistant test" floor a generic candidate must
    clear. Every legacy generator happens to carry one or the other, so the
    ceiling was invisible until a source emitted neither. Leaving it None
    reproduces the previous behaviour exactly.
    """
    now = now or datetime.now(timezone.utc)
    factors: List[ScoreFactor] = []

    urgency = _clamp(cand.urgency_hint)
    importance = _clamp(cand.importance_hint)
    confidence = _clamp(cand.confidence)

    # Deadlines / time-to-event from evidence
    deadline = _parse_dt(
        (cand.evidence or {}).get("deadline")
        or (cand.evidence or {}).get("exam_date")
        or (cand.evidence or {}).get("departure_at")
        or cand.expires_at
    )
    if deadline:
        hours = (deadline - now).total_seconds() / 3600.0
        if hours < 0:
            time_u = 0.95
            factors.append(ScoreFactor(
                code="deadline_passed", label="Scadenza passata", weight=0.22, value=time_u,
            ))
        elif hours <= 24:
            time_u = 0.9
            factors.append(ScoreFactor(
                code="deadline_24h", label="Entro 24 ore", weight=0.2, value=time_u,
            ))
        elif hours <= 72:
            time_u = 0.75
            factors.append(ScoreFactor(
                code="deadline_72h", label="Entro 3 giorni", weight=0.16, value=time_u,
            ))
        elif hours <= 168:
            time_u = 0.55
            factors.append(ScoreFactor(
                code="deadline_week", label="Entro una settimana", weight=0.12, value=time_u,
            ))
        else:
            time_u = 0.35
            factors.append(ScoreFactor(
                code="deadline_later", label="Scadenza lontana", weight=0.06, value=time_u,
            ))
        urgency = _clamp(0.55 * urgency + 0.45 * time_u)

    # Goal linkage
    if goal:
        g_imp = goal.get("importance")
        if g_imp is not None:
            try:
                gi = _clamp(float(g_imp) / 10.0 if float(g_imp) > 1 else float(g_imp))
                importance = _clamp(0.6 * importance + 0.4 * gi)
                factors.append(ScoreFactor(
                    code="goal_importance", label="Importanza obiettivo", weight=0.14, value=gi,
                ))
            except Exception:
                pass
        prog = (goal.get("progress") or {}) if isinstance(goal.get("progress"), dict) else {}
        ratio = float(prog.get("ratio") or goal.get("completion_percentage") or 0) / (
            100.0 if float(prog.get("ratio") or 0) > 1 or float(goal.get("completion_percentage") or 0) > 1 else 1.0
        )
        if float(goal.get("completion_percentage") or 0) > 1:
            ratio = float(goal.get("completion_percentage") or 0) / 100.0
        elif prog.get("ratio") is not None:
            ratio = float(prog.get("ratio") or 0)
        if ratio < 0.35 and cand.type in ("study", "travel", "projects"):
            boost = 0.12
            importance = _clamp(importance + boost)
            factors.append(ScoreFactor(
                code="low_progress", label="Progresso basso", weight=0.1, value=boost,
                detail=f"ratio≈{ratio:.2f}",
            ))
        factors.append(ScoreFactor(
            code="goal_linked", label="Collegato a obiettivo", weight=0.08, value=0.08,
        ))

    # Brain soft context (presence only — never invent facts)
    if brain_ctx and brain_ctx.get("node_id"):
        factors.append(ScoreFactor(
            code="brain_context", label="Contesto Brain", weight=0.05, value=0.05,
        ))
        confidence = _clamp(confidence + 0.03)

    # Calendar pressure
    if calendar_busy:
        factors.append(ScoreFactor(
            code="calendar_busy", label="Calendario pieno", weight=0.06, value=0.06,
            detail="Preferisci interventi ad alto valore",
        ))
        # Slightly raise bar: lower score unless urgency high
        if urgency < 0.7:
            urgency = _clamp(urgency * 0.92)

    # Type base
    type_w = {
        "study": 0.08, "travel": 0.07, "calendar": 0.09, "documents": 0.06,
        "projects": 0.05, "life": 0.04, "generic": 0.03,
        "finance": 0.0, "emails": 0.0, "weather": 0.0, "health": 0.0,
    }.get(cand.type, 0.03)
    factors.append(ScoreFactor(
        code="type_base", label=f"Tipo {cand.type}", weight=type_w, value=type_w,
    ))

    # Candidate-supplied quality (general-purpose: actionability/novelty as
    # judged by whichever layer produced this candidate). Never domain-derived.
    quality: Optional[float] = None
    if getattr(cand, "quality_hint", None) is not None:
        quality = _clamp(cand.quality_hint)
        factors.append(ScoreFactor(
            code="candidate_quality", label="Qualità del candidato",
            weight=0.12, value=quality,
        ))

    factors.append(ScoreFactor(
        code="confidence", label="Confidenza evidenza", weight=0.1, value=confidence,
    ))
    factors.append(ScoreFactor(
        code="urgency", label="Urgenza", weight=0.22, value=urgency,
    ))
    factors.append(ScoreFactor(
        code="importance", label="Importanza", weight=0.2, value=importance,
    ))

    base = (
        0.22 * urgency
        + 0.20 * importance
        + 0.12 * confidence
        + 0.08 * type_w / 0.09
        + sum(f.weight * f.value for f in factors if f.code.startswith("deadline")) * 0.15
        + (0.08 if goal else 0.0)
        + (0.05 if brain_ctx and brain_ctx.get("node_id") else 0.0)
        + (0.12 * quality if quality is not None else 0.0)
    )
    # Normalize roughly into 0–1
    score = _clamp(base)

    # Learning — bounded
    mult = _clamp(learning_multiplier, 0.5, 1.35)
    if abs(mult - 1.0) > 0.01:
        factors.append(ScoreFactor(
            code="learning", label="Apprendimento preferenze", weight=0.08, value=mult - 1.0,
            detail=f"×{mult:.2f}",
        ))
    score = _clamp(score * mult)

    return score, importance, urgency, factors


def priority_from_score(score: float, urgency: float) -> str:
    if score >= 0.78 or urgency >= 0.9:
        return "critical"
    if score >= 0.62 or urgency >= 0.7:
        return "high"
    if score >= 0.42:
        return "medium"
    return "low"
