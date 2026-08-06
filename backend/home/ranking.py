"""Deterministic, versioned Home ranking — rules only, no LLM required."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .actions_catalog import actions_for
from .models import RANKING_VERSION, HomeItem, PriorityBand, ReasonFactor, UrgencyLevel


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _hours_until(value: Optional[str], now: datetime) -> Optional[float]:
    dt = _parse_dt(value)
    if dt is None:
        return None
    return (dt - now).total_seconds() / 3600.0


def classify_urgency(item: HomeItem, now: datetime) -> UrgencyLevel:
    hrs = _hours_until(item.due_at or item.start_at, now)
    if hrs is None:
        return item.urgency if item.urgency != "none" else "none"
    if hrs < 0:
        return "overdue"
    if hrs <= 3:
        return "urgent"
    if hrs <= 24:
        return "soon"
    if hrs <= 72:
        return "upcoming"
    return "none"


def classify_priority(item: HomeItem, now: datetime, score: float) -> PriorityBand:
    if item.status in ("waiting", "deferred", "in_attesa"):
        return "waiting"
    urg = item.urgency
    hrs = _hours_until(item.due_at or item.start_at, now)
    if urg == "overdue" or score >= 80:
        return "critical"
    if urg == "urgent" or (hrs is not None and 0 <= hrs <= 24) or score >= 60:
        return "today"
    if urg in ("soon", "upcoming") or (hrs is not None and 0 <= hrs <= 168) or score >= 40:
        return "this_week"
    if item.type in ("needs_review", "verify") and score >= 25:
        return "today"
    return "later"


def score_item(item: HomeItem, now: datetime) -> Tuple[float, List[ReasonFactor], str]:
    """Compute score + human factors. Never invents narrative beyond factors."""
    factors: List[ReasonFactor] = []
    score = 10.0  # base presence

    # Type base weights
    type_weights = {
        "bill": 18, "payment": 18, "visit": 16, "event": 14, "travel": 15,
        "needs_review": 20, "verify": 20, "study": 12, "reply": 14,
        "activity": 10, "resume": 8, "insight": 5, "generic": 8,
    }
    tw = type_weights.get(item.type, 8)
    score += tw
    factors.append(ReasonFactor(code="type", label=f"Tipo {item.type}", weight=tw))

    hrs_due = _hours_until(item.due_at, now)
    hrs_start = _hours_until(item.start_at, now)
    hrs = hrs_due if hrs_due is not None else hrs_start

    if hrs is not None:
        if hrs < 0:
            w = min(40.0, 22.0 + abs(hrs) * 0.5)
            score += w
            factors.append(ReasonFactor(code="overdue", label="Scadenza superata", weight=w, detail=f"{abs(hrs):.1f}h fa"))
        elif hrs <= 3:
            w = 35.0
            score += w
            factors.append(ReasonFactor(code="imminent", label="Imminente", weight=w, detail=f"tra {hrs*60:.0f} min"))
        elif hrs <= 24:
            w = 28.0
            score += w
            factors.append(ReasonFactor(code="within_24h", label="Entro 24 ore", weight=w))
        elif hrs <= 72:
            w = 18.0
            score += w
            factors.append(ReasonFactor(code="within_3d", label="Entro 3 giorni", weight=w))
        elif hrs <= 168:
            w = 8.0
            score += w
            factors.append(ReasonFactor(code="within_week", label="Questa settimana", weight=w))

    if item.amount:
        score += 6
        factors.append(ReasonFactor(code="amount", label="Importo rilevato", weight=6, detail=str(item.amount)))

    if item.confidence is not None:
        if item.confidence < 0.55:
            score += 12  # needs attention
            factors.append(ReasonFactor(code="low_confidence", label="Dati da verificare", weight=12))
        elif item.confidence >= 0.85:
            score += 4
            factors.append(ReasonFactor(code="high_confidence", label="Alta confidenza dati", weight=4))

    if item.type in ("needs_review", "verify"):
        score += 10
        factors.append(ReasonFactor(code="needs_review", label="Richiede verifica", weight=10))

    if item.meta.get("overdue_activity"):
        score += 15
        factors.append(ReasonFactor(code="overdue_activity", label="Attività in ritardo", weight=15))

    if item.meta.get("incomplete_study"):
        score += 8
        factors.append(ReasonFactor(code="incomplete_study", label="Studio incompleto", weight=8))

    if item.meta.get("quiz_incomplete") or item.meta.get("flashcard_incomplete"):
        score += 9
        factors.append(ReasonFactor(code="resume_study", label="Sessione studio da riprendere", weight=9))

    # Goal-aware boost (home-rank-1.2) — only when goal_id attached; Brain ≠ score
    if item.goal_id:
        from home.goal_context import goal_score_delta
        g_delta, g_factors = goal_score_delta(item, now)
        score += g_delta
        factors.extend(g_factors)

    # Session-today / skipped from study meta (independent of Goal attach)
    if item.meta.get("session_today"):
        score += 7
        factors.append(ReasonFactor(code="session_today", label="Sessione oggi", weight=7))
    if item.meta.get("skipped_sessions"):
        try:
            n = int(item.meta["skipped_sessions"])
        except (TypeError, ValueError):
            n = 0
        if n > 0 and not item.goal_id:
            w = min(10.0, 4.0 + n)
            score += w
            factors.append(ReasonFactor(
                code="skipped_sessions", label="Sessioni saltate", weight=w, detail=str(n),
            ))
    if item.meta.get("missing_prep") and not item.goal_id:
        score += 8
        factors.append(ReasonFactor(
            code="missing_prep", label="Preparazione mancante", weight=8,
        ))

    # Soft dampen leisure-like activities when critical bills/events exist — applied later in rank_items
    summary_parts = [f.label for f in sorted(factors, key=lambda x: -x.weight)[:3]]
    reason_summary = "; ".join(summary_parts) if summary_parts else "Priorità calcolata da regole ORA"

    return round(score, 2), factors, reason_summary


def rank_items(items: List[HomeItem], *, now: Optional[datetime] = None) -> List[HomeItem]:
    now = now or datetime.now(timezone.utc)
    enriched: List[HomeItem] = []

    has_critical_bill = any(
        i.type in ("bill", "payment") and classify_urgency(i, now) in ("overdue", "urgent", "soon")
        for i in items
    )

    for raw in items:
        item = raw.model_copy(deep=True)
        item.urgency = classify_urgency(item, now)
        score, factors, summary = score_item(item, now)

        if has_critical_bill and item.type == "activity" and item.subtype in ("fitness", "leisure", None):
            score -= 12
            factors.append(ReasonFactor(code="dampened", label="Rimandabile rispetto a scadenze", weight=-12))
            summary = f"{summary}; rimandabile rispetto a scadenze"

        item.score = score
        item.reason_factors = factors
        item.reason_summary = summary
        item.priority = classify_priority(item, now, score)
        item.ranking_version = RANKING_VERSION
        item.actions = actions_for(item)
        item.updated_at = item.updated_at or now.isoformat()
        enriched.append(item)

    enriched.sort(key=lambda x: (-x.score, x.start_at or x.due_at or "", x.id))
    return enriched


def dedupe_items(items: List[HomeItem], *, collapse_goals: bool = False) -> List[HomeItem]:
    """
    Collapse duplicates by source or normalized title+time window.

    Goal collapse is owned by the Presentation Aggregation Layer
    (`home.presentation.aggregate_presentation`) so supporting_details can
    retain sibling artifacts. Pass collapse_goals=True only as a legacy fallback.
    """
    seen: Dict[str, HomeItem] = {}
    order: List[str] = []
    for item in items:
        key = item.meta.get("dedupe_key") or f"{item.source_type}:{item.source_id}:{item.type}"
        # Never merge distinct Goals on title alone — scope title_dedupe by goal_id
        gid = item.goal_id or (item.meta or {}).get("goal_id") or ""
        title_key = (
            f"{gid}|{(item.title or '').strip().lower()}|"
            f"{(item.start_at or item.due_at or '')[:13]}"
        )
        alt = item.meta.get("title_dedupe") or title_key
        if gid and not str(alt).startswith(str(gid)):
            alt = f"{gid}|{alt}"
        existing = seen.get(key) or seen.get(alt)
        if existing is None:
            seen[key] = item
            seen[alt] = item
            order.append(key)
            continue
        # keep higher score / more complete
        if item.score >= existing.score:
            # replace
            for k, v in list(seen.items()):
                if v.id == existing.id:
                    seen[k] = item
            seen[key] = item
            seen[alt] = item
    # unique by id preserving order
    out: List[HomeItem] = []
    used = set()
    for k in order:
        it = seen.get(k)
        if it and it.id not in used:
            used.add(it.id)
            out.append(it)
    if collapse_goals:
        try:
            from home.goal_context import dedupe_by_goal
            out = dedupe_by_goal(out)
        except Exception:
            pass
    return out


def persist_payload(items: List[HomeItem]) -> List[Dict[str, Any]]:
    """Full persistence shape including score (DB only)."""
    rows = []
    for it in items:
        d = it.model_dump()
        d["generated_at"] = datetime.now(timezone.utc).isoformat()
        rows.append(d)
    return rows
