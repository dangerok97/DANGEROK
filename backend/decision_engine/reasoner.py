"""
DecisionReasoner — turns raw decisions + context into (adjusted_score, reason).

This is the extensible part of the engine. Each rule:
  1. Reads decision + context.
  2. Optionally returns a score delta (positive = boost, negative = dampen).
  3. Optionally returns a human-readable Italian fragment (for the "why").

Rules are pure functions and independent. Add a new rule → nothing else changes.

The final "reason" the user sees is composed from fragments, in the order
rules fired. If nothing fires, the reasoner falls back to a summary of the
decision's own attributes (deadline / urgency / effort).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .context import DecisionContext, hours_until


# ---- rule return type -------------------------------------------------
@dataclass
class RuleOutcome:
    delta: float = 0.0
    fragment: Optional[str] = None
    tag: Optional[str] = None  # short machine tag, e.g. "deadline_soon"


Rule = Callable[[Dict[str, Any], DecisionContext], Optional[RuleOutcome]]


# ---- individual rules -------------------------------------------------
def rule_imminent_event(d: Dict[str, Any], ctx: DecisionContext) -> Optional[RuleOutcome]:
    """Anything starting within 1h dominates. Within 3h still boosts."""
    hrs = hours_until(d.get("starts_at"), ctx.now)
    if hrs is None:
        return None
    if 0 <= hrs <= 1:
        return RuleOutcome(delta=+40, fragment=f"Inizia tra {int(hrs*60)} minuti", tag="imminent")
    if 0 <= hrs <= 3:
        return RuleOutcome(delta=+18, fragment=f"Inizia tra {round(hrs,1)} ore", tag="soon")
    return None


def rule_deadline_proximity(d: Dict[str, Any], ctx: DecisionContext) -> Optional[RuleOutcome]:
    hrs = hours_until(d.get("deadline"), ctx.now)
    if hrs is None:
        return None
    days = hrs / 24.0
    if hrs < 0:
        return RuleOutcome(delta=+8, fragment="Deadline superata", tag="overdue")
    if days <= 1:
        return RuleOutcome(delta=+22, fragment="Scade entro 24 ore", tag="deadline_24h")
    if days <= 3:
        return RuleOutcome(delta=+14, fragment=f"Scade tra {int(round(days))} giorni", tag="deadline_soon")
    if days <= 7:
        return RuleOutcome(delta=+5, fragment=f"Scade tra {int(round(days))} giorni", tag="deadline_week")
    return None


def rule_trip_dependency(d: Dict[str, Any], ctx: DecisionContext) -> Optional[RuleOutcome]:
    """If the user has a travel decision within 24h and this decision looks like
    preparation for it (category=preparation OR linked_to travel OR keyword),
    boost significantly."""
    if d.get("category") in ("travel_prep", "preparation"):
        prep_needed = ctx.any_category_within("travel", hours=36, self_id=d.get("id"))
        if prep_needed:
            return RuleOutcome(delta=+16, fragment="Un viaggio parte a breve", tag="trip_prep")

    # Fallback: keyword detection ("valigia", "prepara").
    title = (d.get("title") or "").lower()
    if any(k in title for k in ("valigia", "prepara la partenza", "check-in")):
        if ctx.any_category_within("travel", hours=36, self_id=d.get("id")):
            return RuleOutcome(delta=+14, fragment="Un viaggio parte a breve", tag="trip_prep")

    # Explicit dependency link.
    for link in d.get("linked_to") or []:
        for other in ctx.decisions:
            if other.get("id") != link:
                continue
            if other.get("status", "open") != "open":
                continue
            hrs = hours_until(other.get("starts_at") or other.get("deadline"), ctx.now)
            if hrs is not None and 0 < hrs <= 36:
                return RuleOutcome(delta=+12, fragment="Legata a un evento imminente", tag="linked_soon")
    return None


def rule_high_stakes_dampens_leisure(d: Dict[str, Any], ctx: DecisionContext) -> Optional[RuleOutcome]:
    """Exam / high-stakes deadline within 48h dampens leisure/fitness."""
    if d.get("category") not in ("fitness", "leisure", "hobby"):
        return None
    high_stakes = False
    for other in ctx.decisions:
        if other.get("id") == d.get("id"):
            continue
        if other.get("status", "open") != "open":
            continue
        if other.get("category") in ("exam", "work_deadline", "study"):
            hrs = hours_until(other.get("deadline") or other.get("starts_at"), ctx.now)
            if hrs is not None and 0 <= hrs <= 48:
                high_stakes = True
                break
    if high_stakes:
        return RuleOutcome(delta=-12, fragment="Rimandabile: hai un impegno più critico a breve", tag="dampened_by_stakes")
    return None


def rule_bill_at_risk(d: Dict[str, Any], ctx: DecisionContext) -> Optional[RuleOutcome]:
    """Bills add an economic-consequence flavor to the reason string."""
    if d.get("category") != "bill":
        return None
    hrs = hours_until(d.get("deadline"), ctx.now)
    if hrs is not None and 0 <= hrs <= 24 * 7:
        return RuleOutcome(delta=+4, fragment="Rimandarla ha conseguenze economiche", tag="bill_risk")
    return None


def rule_quick_win(d: Dict[str, Any], ctx: DecisionContext) -> Optional[RuleOutcome]:
    """Small, high-importance items bubble up: 'costa poco farlo ora'."""
    t = d.get("time_required_min") or 15
    imp = d.get("importance") or 5
    if t <= 5 and imp >= 6:
        return RuleOutcome(delta=+6, fragment="Richiede pochi minuti", tag="quick_win")
    return None


def rule_positive_signal(d: Dict[str, Any], ctx: DecisionContext) -> Optional[RuleOutcome]:
    """Positive/informational items (e.g. 'you saved 220€') never take the top.
    They deserve to be visible but must not dominate action items."""
    if d.get("category") in ("insight", "achievement"):
        return RuleOutcome(delta=-8, fragment="Insight positivo · nessuna azione richiesta", tag="insight")
    return None


DEFAULT_RULES: List[Rule] = [
    rule_imminent_event,
    rule_deadline_proximity,
    rule_trip_dependency,
    rule_high_stakes_dampens_leisure,
    rule_bill_at_risk,
    rule_quick_win,
    rule_positive_signal,
]


# ---- reasoner ---------------------------------------------------------
class DecisionReasoner:
    def __init__(self, rules: List[Rule] | None = None):
        self.rules = list(rules) if rules is not None else list(DEFAULT_RULES)

    def add_rule(self, rule: Rule) -> None:
        """Public hook: bolt on a new rule at runtime."""
        self.rules.append(rule)

    def evaluate(self, d: Dict[str, Any], ctx: DecisionContext) -> Tuple[float, str, List[str]]:
        """Return (total_delta, reason_text, tags)."""
        deltas: List[float] = []
        fragments: List[str] = []
        tags: List[str] = []
        for rule in self.rules:
            try:
                out = rule(d, ctx)
            except Exception:
                out = None
            if out is None:
                continue
            deltas.append(out.delta)
            if out.fragment:
                fragments.append(out.fragment)
            if out.tag:
                tags.append(out.tag)

        total = round(sum(deltas), 2)
        reason = _compose_reason(d, fragments)
        return total, reason, tags


def _compose_reason(d: Dict[str, Any], fragments: List[str]) -> str:
    """Compose a compact, calm Italian explanation."""
    if fragments:
        # Deduplicate while preserving order.
        seen = []
        for f in fragments:
            if f not in seen:
                seen.append(f)
        # Cap to 3 fragments for calmness.
        return " · ".join(seen[:3]) + "."

    # Fallback: describe the decision itself.
    urgency = d.get("urgency") or 5
    time_min = d.get("time_required_min") or 15
    if urgency >= 8:
        return f"Alta urgenza · richiede {time_min} minuti."
    if urgency >= 6:
        return f"Urgenza media · richiede {time_min} minuti."
    return f"Da tenere d'occhio · richiede {time_min} minuti."
