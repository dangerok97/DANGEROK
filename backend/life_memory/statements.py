"""Human Italian memory statements — never expose schema keys to UI."""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

# Keys that must never become Memory V1 (sensitivity / weak signal / internal).
SENSITIVE_KEY_FRAGMENTS = (
    "iban",
    "vin",
    "pod",
    "pdr",
    "targa",
    "plate",
    "codice_fiscale",
    "fiscal",
    "password",
    "secret",
    "coordinate",
    "lat",
    "lon",
    "lng",
    "ssn",
    "carta_identita",
    "passport",
    "documento_identita",
)

# Transient / operational keys — not durable human memory.
TRANSIENT_KEY_FRAGMENTS = (
    "pending_",
    "hypothesis",
    "bolletta_importo",
    "bolletta_scadenza",
    "mutuo_rata",
    "ownership_hypothesis",
    "pipeline",
    "analysis_version",
)

# Values that are internal enums, not human memory.
ENUM_LIKE_VALUES = {
    "studio",
    "lavoro",
    "casa",
    "auto",
    "travel",
    "viaggi",
    "active",
    "paused",
    "true",
    "false",
}

DOMAIN_GROUP_LABELS_IT = {
    "lavoro": "Lavoro",
    "studio": "Studio",
    "casa": "Casa",
    "auto": "Auto",
    "famiglia": "Famiglia",
    "salute": "Salute",
    "finanze": "Finanze",
    "viaggi": "Viaggi",
    "animali": "Animali",
    "assicurazioni": "Assicurazioni",
    "abbonamenti": "Abbonamenti",
    "internet": "Internet",
    "documenti": "Documenti",
    "servizi": "Servizi",
    "mlc": "Identità",
    "note": "Appunti",
    "identity": "Identità",
}

# Slot families for identity / contradiction (same slot → one memory).
SLOT_ALIASES = {
    "lavoro.ruolo": "lavoro.role",
    "ruolo": "lavoro.role",
    "mlc.current_situation.work": "lavoro.role",
    "mlc.responsibilities": "lavoro.role",
    "responsibilities": "lavoro.role",
    "studio.universita": "studio.university",
    "universita": "studio.university",
    "studio.corso": "studio.course",
    "studio.facolta": "studio.course",
    "corso": "studio.course",
    "casa.citta": "casa.city",
    "citta": "casa.city",
    "mlc.life_places.home": "casa.city",
    "casa.indirizzo": "casa.address",
    "indirizzo": "casa.address",
    "auto.modello": "auto.model",
    "modello": "auto.model",
    "mlc.identity.name": "identity.name",
    "identity.preferred_name": "identity.name",
    "preferred_name": "identity.name",
    "famiglia.nucleo": "famiglia.household",
    "nucleo": "famiglia.household",
}


def is_sensitive_key(key: str) -> bool:
    k = (key or "").lower()
    return any(frag in k for frag in SENSITIVE_KEY_FRAGMENTS)


def is_transient_key(key: str) -> bool:
    k = (key or "").lower()
    if k.endswith(".active") or k.endswith(".current_situation") or k in (
        "active",
        "current_situation",
        "mlc.current_situation",
    ):
        return True
    return any(frag in k for frag in TRANSIENT_KEY_FRAGMENTS if frag not in (".active", "active"))


def normalize_slot(domain: str, key: str) -> str:
    k = (key or "").strip().lower()
    if k in SLOT_ALIASES:
        return SLOT_ALIASES[k]
    # strip domain prefix duplication
    d = (domain or "").strip().lower()
    if d and k.startswith(d + "."):
        return k
    if d and "." not in k:
        return f"{d}.{k}"
    return k or f"{d}.unknown"


def group_label_for_domain(domain: Optional[str]) -> str:
    d = (domain or "").strip().lower()
    if d in DOMAIN_GROUP_LABELS_IT:
        return DOMAIN_GROUP_LABELS_IT[d]
    if not d:
        return "Altro"
    # Open-ended: Title Case of domain key, never invent taxonomy filler
    return d.replace("_", " ").strip().title()


def _clean_str(value: Any) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        s = " ".join(value.split()).strip()
        return s or None
    return None


def _strip_role_prefix(s: str) -> str:
    return re.sub(r"(?i)^(nella|nel|nello|come|da)\s+", "", s).strip() or s


def statement_for_profile_fact(
    *,
    domain: str,
    key: str,
    value: Any,
) -> Optional[str]:
    """Return a calm Italian statement, or None if not presentable as memory."""
    if is_sensitive_key(key) or is_transient_key(key):
        return None
    # Bare `active` keys are operational flags
    leaf = key.split(".")[-1].lower()
    if leaf in ("active", "current_situation"):
        return None
    slot = normalize_slot(domain, key)
    s = _clean_str(value)

    if isinstance(value, bool):
        if value is False:
            return None
        bool_map = {
            "casa.owned": "Hai una casa di proprietà.",
            "casa.purchased": "Hai acquistato casa.",
            "casa.affitto": "Vivi in affitto.",
            "casa.mutuo": "Hai un mutuo attivo.",
            "casa.utenze": "Hai utenze domestiche collegate.",
            "casa.assicurazione": "Hai un'assicurazione casa.",
            "auto.owned": "Hai un'auto.",
        }
        for frag, text in bool_map.items():
            if frag in key or frag.split(".")[-1] == key.split(".")[-1]:
                if frag.startswith((domain + ".") if domain else "") or frag in key:
                    return text
        return None

    if not s:
        return None
    if s.lower() in ENUM_LIKE_VALUES:
        return None
    # Avoid dumping raw enums / codes
    if re.fullmatch(r"[a-z0-9_\-.]{1,40}", s) and "_" in s:
        return None

    if slot == "lavoro.role":
        role = _strip_role_prefix(s)
        low = role.lower()
        if any(x in low for x in ("guardia", "finanza", "azienda", "comune", "universit")):
            return f"Lavori nella {role}."
        return f"Lavori come {role}."
    if slot == "studio.university":
        return f"Studi a {s}."
    if slot == "studio.course":
        return f"Studi {s}."
    if slot == "casa.city":
        return f"Vivi a {s}."
    if slot == "casa.address":
        return f"Abiti in {s}."
    if slot == "auto.model":
        return f"Usi un {s}." if not s.lower().startswith(("un ", "una ")) else f"Usi {s}."
    if slot == "identity.name":
        return f"Ti chiami {s}."
    if slot == "famiglia.household":
        return f"Il tuo nucleo familiare: {s}."

    # Generic durable string — skip MLC internals without a template
    if key.lower().startswith("mlc."):
        return None
    leaf_label = leaf.replace("_", " ").strip()
    if leaf_label in ("value", "raw", "status"):
        return None
    return f"{leaf_label[:1].upper() + leaf_label[1:]}: {s}."


def statement_for_study_subject(subject: str) -> str:
    s = " ".join((subject or "").split()).strip()
    s = re.sub(r"(?i)^studio:\s*", "", s).strip()
    return f"Studi {s}."


def statement_for_note(content: str) -> Optional[str]:
    s = " ".join((content or "").split()).strip()
    if not s or len(s) < 2:
        return None
    if len(s) > 240:
        s = s[:239].rstrip() + "…"
    return s if s.endswith((".", "!", "?")) else f"{s}."


def provenance_label(source: str, *, has_document: bool = False) -> str:
    if has_document or source == "document_extract":
        return "Da un documento"
    if source in ("user_said", "user_confirmed", "corrected"):
        return "Me lo hai detto"
    if source in ("structured_account", "account", "system_account"):
        return "Dal tuo account"
    if source == "device_signal":
        return "Dalla posizione del dispositivo"
    if source == "semantic_extract":
        return "Dalla conversazione con ORA"
    if source == "inferred":
        return "Da quello che ORA ha capito"
    if source == "user_memory":
        return "Lo hai salvato tu"
    if source == "study_plan":
        return "Dai tuoi studi"
    return "Da Life Setup"


def confidence_to_status(
    *,
    confidence: float,
    field_status: str,
    source: str,
    confirmed: bool = False,
    key: str = "",
) -> str:
    from life_memory.authority import memory_status_from_authority

    return memory_status_from_authority(
        source=source,
        field_status=field_status,
        confidence=confidence,
        confirmed=confirmed,
        key=key,
    )
