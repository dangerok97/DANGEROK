"""Deterministic rule detectors.

Each rule inspects the decision + optional context/daily summary and
returns either None (rule does not fire) or an `AppliedRule` with
human-readable evidence. NO LLM, NO randomness, NO template strings
containing internal identifiers or Python class names.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .types import AppliedRule


# ---------------- helpers ----------------
def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hours_from_now(dt: Optional[datetime]) -> Optional[float]:
    if dt is None:
        return None
    delta = dt - _now()
    return delta.total_seconds() / 3600.0


# ---------------- rule implementations ----------------
def _fmt_hours(h: float) -> str:
    if h < 1:
        return f"{int(max(1, round(h * 60)))} minuti"
    if h < 24:
        return f"{h:.1f} ore".replace(".0", "")
    d = h / 24
    return f"{d:.1f} giorni".replace(".0", "")


def rule_imminent_event(decision: Dict[str, Any]) -> Optional[AppliedRule]:
    """The decision has a `starts_at` within the next 24h and in the future."""
    starts_at = _parse_iso(decision.get("starts_at"))
    if not starts_at:
        return None
    h = _hours_from_now(starts_at)
    if h is None or h <= 0 or h > 24:
        return None
    return AppliedRule(
        id="imminent_event",
        label="Evento imminente",
        evidence=[f"Inizia tra circa {_fmt_hours(h)}."],
        weight="high",
    )


def rule_deadline_soon(decision: Dict[str, Any]) -> Optional[AppliedRule]:
    dl = _parse_iso(decision.get("deadline"))
    if not dl:
        return None
    h = _hours_from_now(dl)
    if h is None or h > 72:
        return None
    if h <= 0:
        return AppliedRule(
            id="deadline_overdue",
            label="Scadenza superata",
            evidence=["La scadenza è già passata."],
            weight="high",
        )
    return AppliedRule(
        id="deadline_soon",
        label="Scadenza vicina",
        evidence=[f"Scade tra {_fmt_hours(h)}."],
        weight="high",
    )


def rule_high_urgency(decision: Dict[str, Any]) -> Optional[AppliedRule]:
    u = decision.get("urgency") or 0
    if u < 8:
        return None
    return AppliedRule(
        id="high_urgency",
        label="Urgenza elevata",
        evidence=[f"Urgenza {u}/10."],
        weight="high",
    )


def rule_high_importance(decision: Dict[str, Any]) -> Optional[AppliedRule]:
    i = decision.get("importance") or 0
    if i < 8:
        return None
    return AppliedRule(
        id="high_importance",
        label="Importanza elevata",
        evidence=[f"Importanza {i}/10."],
        weight="high",
    )


def rule_quick_win(decision: Dict[str, Any]) -> Optional[AppliedRule]:
    d = decision.get("time_required_min") or 0
    if d <= 0 or d > 15:
        return None
    return AppliedRule(
        id="quick_win",
        label="Attività breve",
        evidence=[f"Richiede circa {int(d)} minuti."],
        weight="medium",
    )


def rule_travel_dependency(decision: Dict[str, Any], linked_nodes: List[Dict[str, Any]]) -> Optional[AppliedRule]:
    cat = (decision.get("category") or "").lower()
    if cat == "travel":
        return AppliedRule(
            id="travel_dependency",
            label="Dipendenza da un viaggio",
            evidence=["Categoria dell'attività: viaggio."],
            weight="high",
        )
    for n in linked_nodes or []:
        n_type = (n.get("type") or "").lower()
        label = (n.get("label") or "").lower()
        if n_type in ("trip", "travel") or any(k in label for k in ("volo", "treno", "viaggio")):
            return AppliedRule(
                id="travel_dependency",
                label="Dipendenza da un viaggio",
                evidence=[f"Collegata a: {n.get('label') or 'evento di viaggio'}."],
                weight="high",
            )
    return None


def rule_available_time_slot(daily: Optional[Dict[str, Any]], decision: Dict[str, Any]) -> Optional[AppliedRule]:
    if not daily:
        return None
    free_min = int(daily.get("free_minutes") or 0)
    required = int(decision.get("time_required_min") or 15)
    if free_min < required:
        return None
    return AppliedRule(
        id="available_time_slot",
        label="Finestra libera disponibile",
        evidence=[f"Oggi hai {free_min // 60}h {free_min % 60}min di tempo libero."],
        weight="medium",
    )


def rule_busy_day(daily: Optional[Dict[str, Any]]) -> Optional[AppliedRule]:
    if not daily:
        return None
    signals = daily.get("signals") or []
    warnings = daily.get("warnings") or []
    if "very_busy_day" in warnings:
        return AppliedRule(
            id="busy_day",
            label="Giornata molto piena",
            evidence=["Molte attività già in programma oggi."],
            weight="medium",
        )
    if "busy_day" in signals or "stressful_day" in signals:
        return AppliedRule(
            id="busy_day",
            label="Giornata impegnativa",
            evidence=["La giornata è già ricca di eventi."],
            weight="low",
        )
    return None


def rule_weekend(daily: Optional[Dict[str, Any]]) -> Optional[AppliedRule]:
    if not daily:
        return None
    if daily.get("is_weekend"):
        return AppliedRule(
            id="weekend",
            label="Weekend",
            evidence=["È un fine settimana."],
            weight="low",
        )
    return None


def rule_back_to_back(daily: Optional[Dict[str, Any]]) -> Optional[AppliedRule]:
    if not daily:
        return None
    if "back_to_back_marathon" in (daily.get("warnings") or []):
        return AppliedRule(
            id="back_to_back",
            label="Impegni consecutivi",
            evidence=[f"Consecutivi: {daily.get('consecutive_events')}."],
            weight="medium",
        )
    return None


def rule_postpone_risk_high(decision: Dict[str, Any]) -> Optional[AppliedRule]:
    """Meta-rule: high risk if urgency >= 7 AND (imminent_event OR deadline_soon)."""
    urgency = decision.get("urgency") or 0
    starts_at = _parse_iso(decision.get("starts_at"))
    deadline = _parse_iso(decision.get("deadline"))
    starts_h = _hours_from_now(starts_at) if starts_at else None
    dl_h = _hours_from_now(deadline) if deadline else None
    if urgency >= 7 and ((starts_h is not None and 0 < starts_h <= 24) or (dl_h is not None and dl_h <= 72)):
        return AppliedRule(
            id="postpone_risk_high",
            label="Rimandare oggi comporta un rischio",
            evidence=["Urgenza alta abbinata a un impegno vicino."],
            weight="high",
        )
    return None


# ---------------- master evaluator ----------------
def evaluate_rules(
    *,
    decision: Dict[str, Any],
    linked_nodes: Optional[List[Dict[str, Any]]] = None,
    daily: Optional[Dict[str, Any]] = None,
) -> List[AppliedRule]:
    """Runs every rule in a stable order and returns those that fire."""
    linked_nodes = linked_nodes or []
    candidates = [
        rule_imminent_event(decision),
        rule_deadline_soon(decision),
        rule_high_urgency(decision),
        rule_high_importance(decision),
        rule_quick_win(decision),
        rule_travel_dependency(decision, linked_nodes),
        rule_available_time_slot(daily, decision),
        rule_busy_day(daily),
        rule_back_to_back(daily),
        rule_weekend(daily),
        rule_postpone_risk_high(decision),
    ]
    return [r for r in candidates if r is not None]
