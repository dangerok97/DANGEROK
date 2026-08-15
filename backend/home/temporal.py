"""Generic temporal / ownership helpers for Home ranking — domain-neutral."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Presentation / ranking states (not necessarily DB enums)
TEMPORAL_ACTIVE = "ACTIVE"
TEMPORAL_UPCOMING = "UPCOMING"
TEMPORAL_EXPIRED_RECOVERABLE = "EXPIRED_RECOVERABLE"
TEMPORAL_EXPIRED_STALE = "EXPIRED_STALE"
TEMPORAL_COMPLETED = "COMPLETED"
TEMPORAL_SUPERSEDED = "SUPERSEDED"


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            s = f"{s}T12:00:00+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def hours_until(value: Optional[str], now: datetime) -> Optional[float]:
    dt = parse_dt(value)
    if dt is None:
        return None
    return (dt - now).total_seconds() / 3600.0


def is_plan_shell(item: Any) -> bool:
    """True for durable plan-like Home items (not bills/events)."""
    st = getattr(item, "source_type", None) or ""
    subtype = getattr(item, "subtype", None) or ""
    meta = getattr(item, "meta", None) or {}
    if meta.get("plan_shell") is True:
        return True
    if st in ("study_plan", "travel_project", "life_os_plan"):
        return True
    if subtype in ("study_plan", "life_os_plan", "travel_project"):
        return True
    return False


def classify_temporal_state(
    *,
    due_at: Optional[str],
    now: datetime,
    actionable_now: bool = False,
    has_open_work: bool = False,
    recovery_debt: bool = False,
    status: str = "open",
    meta_state: Optional[str] = None,
    past_due_is_stale: bool = False,
) -> str:
    """Classify temporal relevance for ranking/presentation.

    past_due_is_stale: only for plan shells (study/travel/life_os). Bills, events,
    and other concrete debts stay ACTIVE when past due so overdue ranking still works.
    """
    if meta_state in (
        TEMPORAL_ACTIVE,
        TEMPORAL_UPCOMING,
        TEMPORAL_EXPIRED_RECOVERABLE,
        TEMPORAL_EXPIRED_STALE,
        TEMPORAL_COMPLETED,
        TEMPORAL_SUPERSEDED,
    ):
        return meta_state
    if status in ("completed", "done", "archived", "cancelled"):
        return TEMPORAL_COMPLETED

    hrs = hours_until(due_at, now)
    if actionable_now or (has_open_work and (hrs is None or hrs >= 0)):
        if hrs is not None and 0 <= hrs <= 72:
            return TEMPORAL_ACTIVE
        if hrs is None or hrs > 72:
            return TEMPORAL_UPCOMING if not actionable_now else TEMPORAL_ACTIVE
        # past due but still actionable today
        if hrs < 0 and actionable_now:
            return TEMPORAL_ACTIVE

    if hrs is not None and hrs < 0:
        if not past_due_is_stale:
            # Concrete overdue work (bill/event/activity) — not a stale plan horizon
            return TEMPORAL_ACTIVE
        if recovery_debt or has_open_work:
            return TEMPORAL_EXPIRED_RECOVERABLE
        return TEMPORAL_EXPIRED_STALE

    if hrs is not None and hrs >= 0:
        return TEMPORAL_UPCOMING
    return TEMPORAL_ACTIVE if actionable_now else TEMPORAL_UPCOMING


def enrich_item_temporal_meta(item: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Ensure meta.temporal_state / actionable_now / plan_shell are set for ranking."""
    now = now or datetime.now(timezone.utc)
    meta = dict(getattr(item, "meta", None) or {})
    if "plan_shell" not in meta:
        meta["plan_shell"] = is_plan_shell(item)

    actionable = bool(meta.get("actionable_now"))
    has_open = bool(
        meta.get("has_open_near_term")
        or meta.get("session_today")
        or meta.get("next_step")
        or meta.get("next_session")
    )
    recovery = bool(
        meta.get("recovery_debt")
        or int(meta.get("missed_sessions") or 0) > 0
        or int(meta.get("skipped_sessions") or 0) > 0
        or meta.get("overdue_activity")
    )
    # Plan shells with past deadline and no open work → not actionable.
    # Override adapter ACTIVE/UPCOMING when the clock says the horizon is past
    # and there is no session-today / recovery debt (generic ownership).
    hrs = hours_until(getattr(item, "due_at", None) or getattr(item, "start_at", None), now)
    meta_state = meta.get("temporal_state")
    if (
        meta.get("plan_shell")
        and hrs is not None
        and hrs < 0
        and not meta.get("session_today")
        and not meta.get("canonical_execution")
    ):
        if not recovery and not actionable:
            has_open = False
            actionable = False
            meta_state = TEMPORAL_EXPIRED_STALE
        elif recovery and not meta.get("session_today"):
            # Past horizon + skipped/missed work → recoverable, not Daily Focus winner
            meta_state = TEMPORAL_EXPIRED_RECOVERABLE
            actionable = bool(meta.get("next_session") or meta.get("has_open_near_term"))

    state = classify_temporal_state(
        due_at=getattr(item, "due_at", None) or getattr(item, "start_at", None),
        now=now,
        actionable_now=actionable,
        has_open_work=has_open,
        recovery_debt=recovery,
        status=str(getattr(item, "status", None) or "open"),
        meta_state=meta_state,
        past_due_is_stale=bool(meta.get("plan_shell")),
    )
    meta["temporal_state"] = state
    if state in (TEMPORAL_EXPIRED_STALE, TEMPORAL_SUPERSEDED):
        meta["actionable_now"] = False
    elif "actionable_now" not in meta:
        meta["actionable_now"] = actionable or (
            state == TEMPORAL_ACTIVE and bool(meta.get("canonical_execution"))
        )
    return meta


def public_rank_trace_row(item: Any) -> Dict[str, Any]:
    meta = getattr(item, "meta", None) or {}
    return {
        "id": getattr(item, "id", None),
        "source": getattr(item, "source_type", None),
        "canonical_id": meta.get("life_os_plan_id")
        or meta.get("study_plan_id")
        or meta.get("travel_project_id")
        or getattr(item, "source_id", None),
        "type": getattr(item, "type", None),
        "status": getattr(item, "status", None),
        "due_at": getattr(item, "due_at", None),
        "temporal_state": meta.get("temporal_state"),
        "expired": meta.get("temporal_state")
        in (TEMPORAL_EXPIRED_STALE, TEMPORAL_EXPIRED_RECOVERABLE),
        "actionable": bool(meta.get("actionable_now")),
        "canonical_execution": bool(meta.get("canonical_execution")),
        "freshness": meta.get("freshness"),
        "supersession": meta.get("supersession"),
        "score": getattr(item, "score", None),
        "priority": getattr(item, "priority", None),
        "route": meta.get("route"),
        "factors": [
            {"code": f.code, "weight": f.weight}
            for f in (getattr(item, "reason_factors", None) or [])[:10]
        ],
    }
