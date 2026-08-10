"""Epistemic authority → Memory status → clarification eligibility.

USER_CONFIRMED / USER_STATED > DOCUMENT > STRUCTURED_ACCOUNT > AI_INFERRED / SUGGESTED / DEVICE_SIGNAL

Gemini must not be asked to reconfirm strong-authority facts.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

# Keys that Life Setup NLP extracts from first-person user utterances
# (never written by GPS reverse-geocode — that uses confirm_location → user_confirmed).
UTTERANCE_DURABLE_KEYS = frozenset(
    {
        "mlc.identity.name",
        "identity.preferred_name",
        "mlc.life_places.home",
        "casa.citta",
        "lavoro.ruolo",
        "mlc.responsibilities",
    }
)

RESIDENCE_KEYS = frozenset(
    {
        "mlc.life_places.home",
        "casa.citta",
        "casa.indirizzo",
    }
)

CURRENT_LOCATION_KEYS = frozenset(
    {
        "device.current_city",
        "mlc.current_location",
        "location.current_city",
    }
)


def authority_band(
    *,
    source: str,
    field_status: str,
    confirmed: bool = False,
) -> str:
    """Coarse authority band — not a giant ontology."""
    src = (source or "").lower()
    st = (field_status or "").lower()
    if st == "rejected":
        return "rejected"
    if src == "device_signal" or st == "device_signal":
        return "device_signal"
    if confirmed or st in ("confirmed", "corrected") or src in (
        "user_confirmed",
        "corrected",
    ):
        return "user_confirmed"
    if src == "user_said":
        return "user_stated"
    if src == "document_extract":
        return "authoritative_document"
    if src in ("account", "system_account", "structured_account"):
        return "structured_account"
    if src == "semantic_extract":
        return "suggested"
    if src == "inferred" or st == "suggested":
        return "ai_inferred"
    if src == "study_plan":
        return "structured_system"
    return "suggested"


def memory_status_from_authority(
    *,
    source: str,
    field_status: str,
    confidence: float,
    confirmed: bool = False,
    key: str = "",
) -> str:
    """Map provenance → known | likely | ambiguous | superseded."""
    band = authority_band(
        source=source, field_status=field_status, confirmed=confirmed
    )
    if band == "rejected" or field_status == "rejected":
        return "superseded"
    # GPS / device must never become durable residence "known"
    if band == "device_signal":
        if key in RESIDENCE_KEYS:
            return "ambiguous"  # do not assert "Vivi a…" as known
        return "likely"
    if band in ("user_confirmed", "user_stated", "structured_account"):
        return "known"
    if band == "authoritative_document":
        return "known" if confidence >= 0.55 else "likely"
    if band == "structured_system":
        return "known"
    if band == "ai_inferred":
        if confidence >= 0.75:
            return "likely"
        return "ambiguous"
    # suggested / semantic
    if confidence >= 0.75:
        return "likely"
    return "ambiguous"


def needs_clarification(
    *,
    status: str,
    authority: str,
    has_profile_targets: bool,
    sensitivity: str = "normal",
) -> bool:
    """Clarifiable only when ORA lacks sufficient epistemic authority."""
    if not has_profile_targets:
        return False
    if status in ("known", "superseded"):
        return False
    if authority in (
        "user_confirmed",
        "user_stated",
        "structured_account",
        "authoritative_document",
        "structured_system",
    ):
        return False
    if status in ("ambiguous", "likely"):
        return True
    return False


def names_match(a: Any, b: Any) -> bool:
    sa = " ".join(str(a or "").lower().split())
    sb = " ".join(str(b or "").lower().split())
    if not sa or not sb:
        return False
    return sa == sb or sa in sb or sb in sa


def is_residence_key(key: str) -> bool:
    return (key or "") in RESIDENCE_KEYS or (key or "").endswith(".citta")


def is_current_location_key(key: str) -> bool:
    return (key or "") in CURRENT_LOCATION_KEYS


def question_switches_to_ora_perspective(question: str) -> bool:
    """Detect bad persona: ORA asking as if the memory is about itself."""
    q = " ".join((question or "").lower().split())
    bad = (
        "mi chiamo ",
        "io mi chiamo",
        "sono io ",
        "il mio nome è",
        "il mio nome e",
        "vivo io ",
        "io vivo ",
        "lavoro io ",
        "ti riferivi a me",
        "riferivi a me",
    )
    return any(b in q for b in bad)
