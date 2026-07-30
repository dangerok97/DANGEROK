"""Deterministic Italian text composers for DecisionExplanation.

Strictly template-based. NO LLM. No random selection: given the same
input rules we always emit the exact same string.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .types import AppliedRule


# Ordered by descending priority: the first match wins the top of the
# `human_summary`. This makes the summary deterministic.
_SUMMARY_TEMPLATES: List[tuple] = [
    (("deadline_overdue",),
     "La scadenza è già passata: gestirla ora riduce il rischio."),
    (("postpone_risk_high", "imminent_event"),
     "Questa attività è prioritaria: è imminente e rimandarla oggi comporta un rischio elevato."),
    (("imminent_event", "available_time_slot"),
     "Questa attività è prioritaria perché è imminente e oggi hai una finestra libera sufficiente per completarla."),
    (("imminent_event", "quick_win"),
     "Ha inizio a breve e richiede pochi minuti: chiudila subito."),
    (("deadline_soon", "quick_win"),
     "La scadenza è vicina ma bastano pochi minuti per completarla."),
    (("deadline_soon", "available_time_slot"),
     "La scadenza è vicina e oggi hai una finestra libera adatta."),
    (("travel_dependency", "imminent_event"),
     "È collegata a un viaggio in arrivo: oggi conviene prepararla."),
    (("quick_win", "available_time_slot"),
     "È un impegno breve e oggi hai spazio libero: chiuderlo alleggerisce la giornata."),
    (("imminent_event",),
     "Questa attività è prioritaria perché è imminente."),
    (("deadline_soon",),
     "La scadenza è vicina: meglio agire oggi."),
    (("high_urgency", "high_importance"),
     "Ha urgenza e importanza elevate: è tra le più rilevanti oggi."),
    (("high_urgency",),
     "L'urgenza è elevata."),
    (("high_importance",),
     "L'importanza è elevata."),
    (("quick_win",),
     "È un'attività breve: puoi chiuderla in pochi minuti."),
    (("travel_dependency",),
     "È collegata a un viaggio pianificato."),
    (("busy_day",),
     "La giornata è già impegnativa: valuta se inserirla o rimandarla in modo consapevole."),
    (("weekend",),
     "È un weekend: ricorda di preservare il tempo di recupero."),
]


def _rule_ids(rules: List[AppliedRule]) -> set:
    return {r.id for r in rules}


def compose_human_summary(rules: List[AppliedRule]) -> str:
    ids = _rule_ids(rules)
    for required, template in _SUMMARY_TEMPLATES:
        if all(rid in ids for rid in required):
            return template
    return "Questa attività è consigliata perché rientra tra quelle rilevanti nel tuo contesto attuale."


def compose_reasoning_steps(rules: List[AppliedRule]) -> List[str]:
    """One human step per fired rule, preserving the rule evaluation order."""
    steps: List[str] = []
    for r in rules:
        # Deterministic: label + first evidence when present.
        if r.evidence:
            steps.append(f"{r.label}: {r.evidence[0]}")
        else:
            steps.append(r.label)
    return steps


# ---- Estimation helpers ----------------------------------------------
def classify_impact(decision: Dict) -> str:
    """Deterministic bucket from (importance, personal_impact, economic_impact)."""
    imp = int(decision.get("importance") or 0)
    pi = int(decision.get("personal_impact") or 0)
    ei = int(decision.get("economic_impact") or 0)
    score = imp + pi + ei
    if score >= 22:
        return "high"
    if score >= 12:
        return "medium"
    return "low"


def classify_postpone_risk(decision: Dict, applied_rule_ids: set) -> str:
    if "postpone_risk_high" in applied_rule_ids or "deadline_overdue" in applied_rule_ids:
        return "high"
    if "imminent_event" in applied_rule_ids or "deadline_soon" in applied_rule_ids:
        return "medium"
    if (decision.get("urgency") or 0) >= 7:
        return "medium"
    return "low"


def classify_confidence(*, has_snapshot: bool, has_daily: bool, rules_count: int) -> str:
    """More data → higher confidence."""
    ticks = 0
    if has_snapshot: ticks += 1
    if has_daily: ticks += 1
    if rules_count >= 3: ticks += 1
    if ticks >= 3:
        return "high"
    if ticks >= 1:
        return "medium"
    return "low"
