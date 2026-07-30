"""Deterministic shadow rules (iter17).

Each rule is a pure function of (decision, profile, now_local) → ShadowRuleResult.
NO ML/LLM/embeddings. Confidence gating is applied by the scoring layer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .types import ShadowRuleResult, CRITICAL_CATEGORIES

# ---- helpers ----------------------------------------------------------------

def _confidence_of(profile: Dict[str, Any]) -> str:
    return (profile or {}).get("confidence", "low")


def _is_urgent(decision: Dict[str, Any]) -> bool:
    prio = str(decision.get("priority") or "").lower()
    if prio in ("urgent", "critical", "high"):
        return True
    ttl = decision.get("deadline")
    if ttl:
        try:
            dl = datetime.fromisoformat(str(ttl).replace("Z", "+00:00"))
            hrs = (dl - datetime.now(timezone.utc)).total_seconds() / 3600
            if hrs <= 24:
                return True
        except Exception:
            pass
    return False


def _is_critical(decision: Dict[str, Any]) -> bool:
    cat = str(decision.get("category") or "").lower()
    return any(c in cat for c in CRITICAL_CATEGORIES)


def _hour_in(hour: int, hours: List[int]) -> bool:
    return bool(hours) and hour in hours


def _rate_from(buckets: List[Dict[str, Any]], hour: int) -> float:
    total = sum(b.get("count", 0) for b in buckets) or 0
    if not total:
        return 0.0
    hit = next((b for b in buckets if b.get("hour") == hour), None)
    return (hit.get("count", 0) / total) if hit else 0.0


# ---- rules ------------------------------------------------------------------

def rule_preferred_time_alignment(dec, prof, now_hour: int, metrics) -> ShadowRuleResult:
    r = ShadowRuleResult(rule_id="preferred_time_alignment", confidence=_confidence_of(prof))
    prefs = (prof or {}).get("preferred_work_hours") or []
    if _hour_in(now_hour, prefs):
        r.applied = True
        r.delta = 2.0
        r.reason = "current hour matches preferred work hours"
        r.evidence = {"current_hour": now_hour, "preferred": prefs[:5]}
    else:
        r.reason = "hour not in preferred set"
    return r


def rule_historical_postponement_risk(dec, prof, now_hour: int, metrics) -> ShadowRuleResult:
    r = ShadowRuleResult(rule_id="historical_postponement_risk", confidence=_confidence_of(prof))
    postponed_by_hour = (metrics or {}).get("postponed_by_hour") or []
    rate = _rate_from(postponed_by_hour, now_hour)
    if rate >= 0.35 and (metrics or {}).get("decisions_postponed", 0) >= 5:
        r.applied = True
        r.delta = 2.0
        r.reason = "high postpone frequency in this hour → anticipate visibility"
        r.evidence = {"observed_rate": round(rate, 3), "current_hour": now_hour}
    return r


def rule_completion_affinity(dec, prof, now_hour: int, metrics) -> ShadowRuleResult:
    r = ShadowRuleResult(rule_id="completion_affinity", confidence=_confidence_of(prof))
    completed_by_hour = (metrics or {}).get("completed_by_hour") or []
    rate = _rate_from(completed_by_hour, now_hour)
    if rate >= 0.25:
        r.applied = True
        r.delta = 1.0
        r.reason = "user completes similar decisions in this hour"
        r.evidence = {"observed_rate": round(rate, 3), "current_hour": now_hour}
    return r


def rule_low_success_window(dec, prof, now_hour: int, metrics) -> ShadowRuleResult:
    r = ShadowRuleResult(rule_id="low_success_window", confidence=_confidence_of(prof))
    postponed_by_hour = (metrics or {}).get("postponed_by_hour") or []
    completed_by_hour = (metrics or {}).get("completed_by_hour") or []
    p_rate = _rate_from(postponed_by_hour, now_hour)
    c_rate = _rate_from(completed_by_hour, now_hour)
    if p_rate >= 0.4 and c_rate <= 0.1:
        r.applied = True
        r.delta = 1.0
        r.reason = "low-success window → anticipate before likely postpone"
        r.evidence = {"postpone_rate": round(p_rate, 3), "completion_rate": round(c_rate, 3)}
    return r


def rule_quick_win_affinity(dec, prof, now_hour: int, metrics) -> ShadowRuleResult:
    r = ShadowRuleResult(rule_id="quick_win_affinity", confidence=_confidence_of(prof))
    tr = dec.get("time_required_min") or dec.get("estimated_minutes") or 999
    completion_style = (prof or {}).get("completion_style")
    if isinstance(tr, (int, float)) and tr <= 15 and completion_style == "quick":
        r.applied = True
        r.delta = 1.0
        r.reason = "quick-win aligned with fast-completion profile"
        r.evidence = {"time_required_min": tr, "completion_style": "quick"}
    return r


def rule_category_procrastination(dec, prof, now_hour: int, metrics) -> ShadowRuleResult:
    r = ShadowRuleResult(rule_id="category_procrastination", confidence=_confidence_of(prof))
    proc = (prof or {}).get("procrastination_index")
    sample = (prof or {}).get("sample_size") or 0
    if proc and proc >= 0.4 and sample >= 5:
        r.applied = True
        r.delta = 2.5
        r.reason = "elevated procrastination index → anticipate"
        r.evidence = {"procrastination_index": proc, "sample_size": sample}
    return r


def rule_overload_protection(dec, prof, now_hour: int, metrics) -> ShadowRuleResult:
    """The ONLY rule allowed to produce a negative delta.

    Guarded by deadline_guardrail at aggregate time: even if this rule fires,
    a critical/urgent decision has any negative delta clipped to 0.
    """
    r = ShadowRuleResult(rule_id="overload_protection", confidence=_confidence_of(prof))
    load = (prof or {}).get("average_daily_load") or 0
    if load >= 8 and not _is_urgent(dec):
        r.applied = True
        r.delta = -1.0  # small
        r.reason = "day overloaded, decision not urgent → shadow deprioritize"
        r.evidence = {"average_daily_load": load}
    return r


def rule_deadline_guardrail(dec, prof, now_hour: int, metrics) -> ShadowRuleResult:
    """Marker rule — enforces non-negative delta for critical/urgent decisions.
    Applied at aggregate time (scoring.py). Reports its own status.
    """
    r = ShadowRuleResult(rule_id="deadline_guardrail")
    if _is_urgent(dec) or _is_critical(dec):
        r.applied = True
        r.reason = "critical/urgent decision → negative deltas clipped to 0"
        r.evidence = {"urgent": _is_urgent(dec), "critical": _is_critical(dec)}
    return r


ALL_RULES = [
    rule_preferred_time_alignment,
    rule_historical_postponement_risk,
    rule_completion_affinity,
    rule_low_success_window,
    rule_quick_win_affinity,
    rule_category_procrastination,
    rule_overload_protection,
    rule_deadline_guardrail,
]
