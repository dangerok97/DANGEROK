"""Human presentation for Home ranking reasons.

INTERNAL ranking keeps ReasonFactor codes/weights/labels for scoring & debug.
PRESENTATION maps structured factor codes (+ item type) → short Italian summary.
Never invents facts (no "valigia"/"domani") beyond what factors encode.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Set

from home.models import ReasonFactor

# Presentation-only domain nouns (never raw engine type strings).
_DOMAIN_IT = {
    "travel": "viaggio",
    "study": "studio",
    "bill": "pagamento",
    "payment": "pagamento",
    "event": "evento",
    "visit": "visita",
    "needs_review": "voce da verificare",
    "verify": "voce da verificare",
    "reply": "risposta",
    "activity": "attività",
    "resume": "attività in corso",
    "insight": "priorità",
    "generic": "priorità",
}

_TIME_CODES = frozenset({
    "overdue", "imminent", "within_24h", "within_3d", "within_week",
})
_DATA_CODES = frozenset({"low_confidence", "needs_review"})


def _codes(factors: Iterable[ReasonFactor]) -> Set[str]:
    return {f.code for f in factors if f and f.code}


def _infer_type(factors: Iterable[ReasonFactor], item_type: Optional[str]) -> Optional[str]:
    if item_type:
        return item_type
    for f in factors:
        if f.code != "type":
            continue
        lab = (f.label or "").strip()
        if lab.lower().startswith("tipo "):
            return lab[5:].strip() or None
        if f.detail:
            return str(f.detail).strip() or None
    return None


def format_reason_summary(
    factors: List[ReasonFactor],
    *,
    item_type: Optional[str] = None,
) -> str:
    """Build a short human Italian summary from structured factors.

    Prefer factor codes over labels. Must never emit "Tipo travel" / raw types.
    """
    if not factors:
        return "Priorità calcolata da regole ORA"

    codes = _codes(factors)
    itype = _infer_type(factors, item_type)
    domain = _DOMAIN_IT.get(itype or "", "priorità")

    # Insufficient / weak data — short prudent copy
    if codes & _DATA_CODES and not (codes & _TIME_CODES):
        if "needs_review" in codes or itype in ("needs_review", "verify"):
            return "Serve una verifica: i dati non bastano ancora."
        return "I dati sono incompleti: meglio verificare prima di decidere."

    missing_prep = "missing_prep" in codes
    dampened = "dampened" in codes

    # Domain + urgency compositions (no invented calendar words)
    if itype == "travel":
        summary = _travel_summary(codes, missing_prep=missing_prep)
    elif itype == "study":
        summary = _study_summary(codes)
    elif itype in ("bill", "payment"):
        summary = _deadline_summary(codes, noun="pagamento")
    elif itype in ("event", "visit"):
        summary = _deadline_summary(codes, noun=domain)
    else:
        summary = _generic_summary(codes, domain=domain, missing_prep=missing_prep)

    if dampened and "rimandabile" not in summary.lower():
        summary = f"{summary} Rimandabile rispetto a scadenze più urgenti."

    # Hard guard: never leak engine type joins
    if "tipo " in summary.lower():
        summary = summary.replace("Tipo ", "").replace("tipo ", "")
    return summary.strip() or "Priorità calcolata da regole ORA"


def _travel_summary(codes: Set[str], *, missing_prep: bool) -> str:
    if "overdue" in codes:
        if missing_prep:
            return "C’è una scadenza del viaggio già superata e manca ancora qualcosa da preparare."
        return "C’è una scadenza del viaggio già superata."
    if "imminent" in codes or "within_24h" in codes:
        if missing_prep:
            return "Il viaggio è imminente e manca ancora qualcosa da preparare."
        return "Il viaggio è imminente."
    if "within_3d" in codes:
        if missing_prep:
            return "Il viaggio è vicino e manca ancora qualcosa da preparare."
        return "Il viaggio è vicino."
    if "within_week" in codes:
        if missing_prep:
            return "Il viaggio è in settimana e manca ancora qualcosa da preparare."
        return "Il viaggio è in programma questa settimana."
    if missing_prep:
        return "Manca ancora qualcosa da preparare per il viaggio."
    return "Il viaggio richiede attenzione ora."


def _study_summary(codes: Set[str]) -> str:
    if "overdue" in codes:
        return "La scadenza dello studio è già passata."
    if "imminent" in codes or "within_24h" in codes:
        return "La scadenza dello studio è molto vicina."
    if "within_3d" in codes:
        return "La scadenza dello studio è vicina."
    if "within_week" in codes:
        return "La scadenza dello studio è in settimana."
    if "resume_study" in codes or "session_today" in codes:
        return "C’è una sessione di studio da riprendere."
    if "incomplete_study" in codes or "skipped_sessions" in codes:
        return "Il piano di studio ha ancora passi aperti."
    return "Lo studio richiede attenzione ora."


def _deadline_summary(codes: Set[str], *, noun: str) -> str:
    if "overdue" in codes:
        return f"La scadenza del {noun} è già passata."
    if "imminent" in codes or "within_24h" in codes:
        return f"La scadenza del {noun} è molto vicina."
    if "within_3d" in codes:
        return f"La scadenza del {noun} è vicina."
    if "within_week" in codes:
        return f"La scadenza del {noun} è in settimana."
    if "amount" in codes:
        return f"C’è un importo da gestire per il {noun}."
    return f"Il {noun} richiede attenzione ora."


def _generic_summary(codes: Set[str], *, domain: str, missing_prep: bool) -> str:
    if "overdue" in codes:
        return "C’è una scadenza già superata."
    if "imminent" in codes or "within_24h" in codes:
        return "C’è qualcosa di imminente da affrontare."
    if "within_3d" in codes or "within_week" in codes:
        return "C’è una scadenza vicina da tenere d’occhio."
    if missing_prep:
        return "Manca ancora qualcosa da preparare."
    if "overdue_activity" in codes:
        return "C’è un’attività in ritardo."
    # Prefer non-type top signal wording without leaking labels
    if domain and domain != "priorità":
        return f"Questa priorità ({domain}) richiede attenzione ora."
    return "Priorità calcolata da regole ORA"
