"""Deterministic, versioned Home ranking — rules only, no LLM required."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .actions_catalog import actions_for
from .dedupe import canonical_title_time_key
from .models import RANKING_VERSION, HomeItem, PriorityBand, ReasonFactor, UrgencyLevel
from .reason_presentation import format_reason_summary
from .temporal import (
    TEMPORAL_EXPIRED_RECOVERABLE,
    TEMPORAL_EXPIRED_STALE,
    TEMPORAL_SUPERSEDED,
    enrich_item_temporal_meta,
    hours_until as _hours_until,
    is_plan_shell,
)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    from .temporal import parse_dt

    return parse_dt(value)


def classify_urgency(item: HomeItem, now: datetime) -> UrgencyLevel:
    meta = item.meta or {}
    state = meta.get("temporal_state")
    # Expired plan shells are stale — not "overdue urgency" for Daily Focus
    if state == TEMPORAL_EXPIRED_STALE:
        return "none"
    if state == TEMPORAL_EXPIRED_RECOVERABLE:
        return "soon"
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
    state = (item.meta or {}).get("temporal_state")
    if state == TEMPORAL_EXPIRED_STALE or state == TEMPORAL_SUPERSEDED:
        return "later"
    urg = item.urgency
    hrs = _hours_until(item.due_at or item.start_at, now)
    if state == TEMPORAL_EXPIRED_RECOVERABLE:
        return "this_week" if score < 60 else "today"
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

    # Enrich temporal / ownership meta before scoring
    item.meta = enrich_item_temporal_meta(item, now)
    state = item.meta.get("temporal_state")

    # Type base weights
    type_weights = {
        "bill": 18, "payment": 18, "visit": 16, "event": 14, "travel": 15,
        "needs_review": 20, "verify": 20, "study": 12, "reply": 14,
        "activity": 10, "resume": 8, "insight": 5, "generic": 8,
    }
    tw = type_weights.get(item.type, 8)
    score += tw
    factors.append(ReasonFactor(code="type", label=f"Tipo {item.type}", weight=tw))

    # Canonical active execution (Life OS or any adapter that opts in) — not source hardcode
    if item.meta.get("canonical_execution") and item.meta.get("actionable_now"):
        score += 26.0
        factors.append(
            ReasonFactor(
                code="canonical_active",
                label="Piano canonico attivo",
                weight=26,
            )
        )
    elif item.meta.get("canonical_execution"):
        score += 12.0
        factors.append(
            ReasonFactor(code="canonical_plan", label="Piano canonico", weight=12)
        )

    # Freshness for canonical plans (recently updated execution state)
    if item.meta.get("canonical_execution"):
        fresh = item.meta.get("freshness") or item.updated_at
        if fresh:
            try:
                from .temporal import parse_dt

                fdt = parse_dt(str(fresh))
                if fdt is not None:
                    age_h = (now - fdt).total_seconds() / 3600.0
                    if age_h <= 24:
                        score += 4.0
                        factors.append(
                            ReasonFactor(
                                code="fresh_canonical",
                                label="Aggiornato di recente",
                                weight=4,
                            )
                        )
                    elif age_h <= 72:
                        score += 2.0
                        factors.append(
                            ReasonFactor(
                                code="fresh_canonical",
                                label="Piano recente",
                                weight=2,
                            )
                        )
            except Exception:
                pass

    hrs_due = _hours_until(item.due_at, now)
    hrs_start = _hours_until(item.start_at, now)
    hrs = hrs_due if hrs_due is not None else hrs_start

    if state == TEMPORAL_SUPERSEDED:
        score -= 40.0
        factors.append(
            ReasonFactor(code="superseded", label="Sostituito da piano più recente", weight=-40)
        )
    elif state == TEMPORAL_EXPIRED_STALE:
        # Past plan deadline without open work must NOT win Daily Focus
        score -= 38.0
        factors.append(
            ReasonFactor(
                code="expired_stale",
                label="Scadenza passata senza azione aperta",
                weight=-38,
                detail=f"{abs(hrs):.1f}h fa" if hrs is not None else None,
            )
        )
    elif state == TEMPORAL_EXPIRED_RECOVERABLE:
        # Mild recovery signal — must stay below an active canonical plan (~46)
        w = 6.0
        score += w
        factors.append(
            ReasonFactor(
                code="expired_recoverable",
                label="Recupero possibile",
                weight=w,
            )
        )
    elif hrs is not None:
        if hrs < 0:
            # True overdue debt (bills, explicit overdue activities) — not plan shells
            if is_plan_shell(item) and not item.meta.get("overdue_activity"):
                score -= 20.0
                factors.append(
                    ReasonFactor(
                        code="expired_plan",
                        label="Orizzonte piano passato",
                        weight=-20,
                    )
                )
            else:
                w = min(40.0, 22.0 + abs(hrs) * 0.5)
                score += w
                factors.append(
                    ReasonFactor(
                        code="overdue",
                        label="Scadenza superata",
                        weight=w,
                        detail=f"{abs(hrs):.1f}h fa",
                    )
                )
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

    # PRESENTATION summary from factor codes + type — never join raw "Tipo …" labels
    reason_summary = format_reason_summary(factors, item_type=item.type)

    return round(score, 2), factors, reason_summary


def rank_items(items: List[HomeItem], *, now: Optional[datetime] = None) -> List[HomeItem]:
    now = now or datetime.now(timezone.utc)
    enriched: List[HomeItem] = []

    # Pre-enrich temporal so bill criticality ignores stale plan shells
    prepped: List[HomeItem] = []
    for raw in items:
        it = raw.model_copy(deep=True)
        it.meta = enrich_item_temporal_meta(it, now)
        prepped.append(it)

    # Mark legacy plan shells superseded when a canonical active plan exists
    # for the same goal_id (generic — not title matching).
    active_canonical_goals = {
        (i.meta or {}).get("goal_id") or i.goal_id
        for i in prepped
        if (i.meta or {}).get("canonical_execution")
        and (i.meta or {}).get("actionable_now")
        and ((i.meta or {}).get("goal_id") or i.goal_id)
    }
    for i in prepped:
        gid = (i.meta or {}).get("goal_id") or i.goal_id
        if (
            gid
            and gid in active_canonical_goals
            and not (i.meta or {}).get("canonical_execution")
            and is_plan_shell(i)
        ):
            i.meta = {**(i.meta or {}), "temporal_state": TEMPORAL_SUPERSEDED, "supersession": "canonical_active"}

    has_critical_bill = any(
        i.type in ("bill", "payment")
        and (i.meta or {}).get("temporal_state") not in (TEMPORAL_EXPIRED_STALE, TEMPORAL_SUPERSEDED)
        and classify_urgency(i, now) in ("overdue", "urgent", "soon")
        for i in prepped
    )

    for item in prepped:
        item.urgency = classify_urgency(item, now)
        score, factors, summary = score_item(item, now)

        # Do not dampen canonical Life OS / active plans as "leisure"
        if (
            has_critical_bill
            and item.type == "activity"
            and item.subtype in ("fitness", "leisure", None)
            and not (item.meta or {}).get("canonical_execution")
        ):
            score -= 12
            factors.append(ReasonFactor(code="dampened", label="Rimandabile rispetto a scadenze", weight=-12))
            summary = format_reason_summary(factors, item_type=item.type)

        item.score = score
        item.reason_factors = factors
        item.reason_summary = summary
        # A band the user corrected by hand survives re-ranking. `_apply_state`
        # writes the override before this runs, and without this guard the
        # classifier overwrote it on the same pass: the correction was stored,
        # the item was flagged as corrected, and the person saw no change.
        # Scoring and ordering stay the system's — only the band the user
        # explicitly set is theirs. A snoozed item is the exception: "waiting"
        # is where it actually is now, and that is more recent than the
        # correction.
        classified = classify_priority(item, now, score)
        corrected = (item.meta or {}).get("priority_corrected") and item.priority
        item.priority = (
            item.priority
            if corrected and classified != "waiting"
            else classified
        )
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
        # Never merge distinct Goals on title alone. Legacy items without a Goal
        # retain the exact normalized title + hour cross-source fallback.
        gid = item.goal_id or (item.meta or {}).get("goal_id") or ""
        title_key = canonical_title_time_key(
            item.title,
            item.start_at or item.due_at,
            goal_id=gid or None,
        )
        alt = item.meta.get("title_dedupe") or title_key
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
