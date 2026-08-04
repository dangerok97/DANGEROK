"""Extensible document taxonomy (macro + subcategories)."""
from __future__ import annotations

from typing import Any, Optional

# Map legacy deterministic type_key → (macro, sub)
LEGACY_TYPE_MAP: dict[str, tuple[str, str]] = {
    "ticket": ("event", "concert_ticket"),
    "invoice": ("financial", "invoice"),
    "receipt": ("receipt", "purchase_receipt"),
    "contract": ("contract", "employment_contract"),
    "bill": ("financial", "invoice"),
    "medical": ("medical", "medical_appointment"),
    "certificate": ("certificate", "certificate"),
    "id_card": ("identity", "identity"),
    "passport": ("identity", "identity"),
    "cv": ("work", "generic"),
    "bank_statement": ("financial", "tax_document"),
    "tax_doc": ("financial", "tax_document"),
    "generic": ("generic", "generic"),
}

MACRO_CATEGORIES = frozenset({
    "event", "education", "work", "administrative", "financial", "medical",
    "travel", "legal", "receipt", "contract", "certificate", "identity",
    "personal", "generic", "unknown",
})

# Keyword hints for education / travel / events beyond legacy classifier
_EDU_KW = (
    "dispensa", "appunti", "slide", "lezione", "esame", "universit", "capitolo",
    "riassunto", "definizione", "bibliografia", "corso", "facoltà", "cfu",
)
_TRAVEL_KW = ("volo", "boarding", "check-in", "treno", "biglietto ferroviario", "hotel", "prenotazione")
_EVENT_KW = (
    "concerto", "cinema", "spettacolo", "mostra", "biglietto", "ingresso", "gate",
    "appuntamento", "visita", "convocazione", "ingresso", "ore ", "h.",
)
_MED_APPT_KW = ("visita", "ambulatorio", "ospedale", "prenotazione sanitaria", "referto", "prescrizione", "visita specialistica")
_ADMIN_KW = (
    "comunicazione", "scadenza", "protocollo", "ufficio", "amministrazione",
    "richiesta di", "azione richiesta", "oggetto:", "mittente", "comune di",
)


def map_legacy(type_key: str) -> tuple[str, str]:
    return LEGACY_TYPE_MAP.get(type_key or "generic", ("generic", "generic"))


def refine_taxonomy(
    *,
    type_key: str,
    text: str,
    filename: str = "",
) -> dict[str, Any]:
    """Produce macro/sub + short reasoning from legacy type + text heuristics."""
    text_l = (text or "").lower()
    name_l = (filename or "").lower()
    blob = f"{text_l}\n{name_l}"
    macro, sub = map_legacy(type_key)
    reasons: list[str] = [f"Classificatore base: {type_key}"]

    edu_hits = sum(1 for k in _EDU_KW if k in blob)
    if edu_hits >= 2 or type_key in ("cv",):
        if edu_hits >= 2:
            macro, sub = "education", "university_notes"
            if "esame" in blob:
                sub = "university_exam"
            elif "slide" in blob:
                sub = "lecture_slides"
            elif "appunti" in blob or "dispensa" in blob:
                sub = "school_notes" if "scuola" in blob else "university_notes"
            reasons.append(f"Segnali studio ({edu_hits})")

    if any(k in blob for k in _TRAVEL_KW):
        if "volo" in blob or "boarding" in blob:
            macro, sub = "travel", "flight_booking"
        elif "treno" in blob or "ferrovi" in blob:
            macro, sub = "travel", "train_ticket"
        elif "hotel" in blob:
            macro, sub = "travel", "hotel_booking"
        else:
            macro, sub = "travel", "generic"
        reasons.append("Segnali viaggio/prenotazione")

    if type_key == "ticket" or (any(k in blob for k in _EVENT_KW) and macro not in ("travel",)):
        macro = "event"
        if "cinema" in blob:
            sub = "cinema_ticket"
        elif "concerto" in blob:
            sub = "concert_ticket"
        elif "mostra" in blob or "museum" in blob:
            sub = "exhibition_ticket"
        elif any(k in blob for k in _MED_APPT_KW):
            macro, sub = "medical", "medical_appointment"
        elif sub == "concert_ticket" or type_key == "ticket":
            sub = sub if sub != "generic" else "concert_ticket"
        reasons.append("Segnali evento/appuntamento")

    if type_key == "medical" or (any(k in blob for k in _MED_APPT_KW) and "concerto" not in blob):
        if any(k in blob for k in ("prescrizione", "farmaco", "ricetta")):
            sub = "prescription"
        elif any(k in blob for k in ("referto", "esame emato", "diagnosi")):
            sub = "medical_report"
        else:
            sub = "medical_appointment"
        macro = "medical"
        reasons.append("Segnali sanitari")

    admin_hits = sum(1 for k in _ADMIN_KW if k in blob)
    if admin_hits >= 2 and macro in ("generic", "unknown", "event"):
        # Prefer admin over weak event signals when no concert/ticket markers
        if not any(k in blob for k in ("concerto", "biglietto", "stadio", "treno", "visita specialistica")):
            macro, sub = "administrative", "official_communication"
            reasons.append(f"Segnali amministrativi ({admin_hits})")

    if macro not in MACRO_CATEGORIES:
        macro = "unknown"

    return {
        "macro_category": macro,
        "subcategory": sub,
        "reasoning_summary": "; ".join(reasons)[:400],
    }


def candidate_actions(macro: str, sub: str) -> list[str]:
    actions = ["open_document", "reanalyze"]
    if macro in ("event", "travel", "medical") or sub.endswith("_ticket") or "appointment" in sub:
        actions.extend(["confirm_event", "add_to_calendar", "open_maps", "remind_later"])
    if macro == "education":
        actions.extend(["save_to_brain", "ask_brain", "review_concepts"])
    if macro in ("financial", "receipt", "administrative"):
        actions.extend(["create_reminder", "save_to_brain"])
    if macro in ("contract", "legal", "certificate"):
        actions.extend(["create_reminder", "needs_review"])
    return list(dict.fromkeys(actions))
