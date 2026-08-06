"""Canonical property registry — aliases → canonical fields.

All gap questions and assimilation use ONLY canonical concepts.
AI may propose alias names; backend maps before persist.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# Canonical field → aliases (lowercase). First match wins when mapping inbound.
CANONICAL_FIELDS: Dict[str, Tuple[str, ...]] = {
    # HOME identity
    "address": (
        "address", "indirizzo", "property_address", "indirizzo_immobile",
        "via", "street_address", "indirizzo_completo",
    ),
    "cadastral_data": (
        "cadastral_data", "dati_catastali", "catastale", "catasto",
        "foglio_particella", "foglio", "riferimento_catastale", "cadastral",
    ),
    "pod": ("pod", "codice_pod", "punto_di_prelievo"),
    "pdr": ("pdr", "codice_pdr", "punto_di_riconsegna"),
    "coords": ("coords", "coordinates", "lat_lng", "geolocation"),
    # HOME / mortgage state
    "lender": ("lender", "banca", "banca_mutuo", "creditore", "bank", "istituto_credito"),
    "monthly_installment": (
        "monthly_installment", "rata", "rata_mensile", "installment",
        "importo_rata", "mortgage_installment",
    ),
    "loan_number": (
        "loan_number", "numero_mutuo", "numero_pratica", "mortgage_number",
        "pratica_mutuo", "contract_loan_number",
    ),
    "interest_rate": ("interest_rate", "tasso", "tasso_interesse", "rate"),
    "mortgage_years_left": (
        "mortgage_years_left", "years_remaining", "anni_residui", "anni_restanti",
    ),
    # Utilities
    "utility_supplier": (
        "utility_supplier", "supplier", "provider", "fornitore",
        "gestore", "operatore", "gestore_energia",
    ),
    "utility_amount": (
        "utility_amount", "amount_total", "amount", "importo", "importo_bolletta",
        "totale",
    ),
    "utility_due_date": (
        "utility_due_date", "due_date", "scadenza", "data_scadenza", "payment_due",
    ),
    "utility_type": ("utility_type", "tipo_utenza", "commodity", "servizio"),
    "consumption": ("consumption", "consumo", "kwh", "smc"),
    "contract_code": ("contract_code", "codice_contratto", "numero_contratto"),
    # Insurance
    "insurance_company": (
        "insurance_company", "company", "compagnia", "assicurazione",
        "compagnia_assicurativa", "insurer",
    ),
    "policy_number": ("policy_number", "numero_polizza", "polizza"),
    "coverage": ("coverage", "copertura", "garanzie"),
    "expiry": ("expiry", "scadenza_polizza", "policy_expiry"),
    "insured_object": ("insured_object", "oggetto_assicurato"),
    # Vehicle identity
    "plate": ("plate", "targa", "license_plate", "numero_targa"),
    "vin": ("vin", "telaio", "numero_telaio", "chassis"),
    "brand": ("brand", "marca", "make"),
    "model": ("model", "modello"),
    # Job / university / travel
    "employer": ("employer", "datore", "datore_di_lavoro", "azienda", "company_name"),
    "profession": ("profession", "mansione", "ruolo", "job_title", "qualifica"),
    "institution": ("institution", "university", "universita", "ateneo", "uni"),
    "course_name": ("course_name", "corso", "corso_di_laurea", "subject", "materia"),
    "destination": ("destination", "destinazione", "luogo"),
    "start_date": ("start_date", "data_inizio", "departure_date", "partenza"),
    "end_date": ("end_date", "data_fine", "return_date", "rientro"),
    # Misc state
    "price": ("price", "prezzo", "prezzo_acquisto", "importo_compravendita"),
    "document_type": ("document_type", "tipo_documento"),
    "domain": ("domain", "dominio"),
    "status_detail": ("status_detail", "stato_dettaglio"),
}

# Concept groups for Knowledge Gap Engine (any alias present → concept satisfied).
CONCEPTS: Dict[str, Tuple[str, ...]] = {
    "home_address": ("address",),
    "cadastral": ("cadastral_data",),
    "pod": ("pod",),
    "pdr": ("pdr",),
    "mortgage": ("lender", "monthly_installment", "loan_number"),
    "utility_supplier": ("utility_supplier",),
    "utility_amount": ("utility_amount",),
    "vehicle_plate": ("plate",),
    "vehicle_vin": ("vin",),
    "insurance": ("insurance_company", "policy_number"),
    "employer": ("employer",),
    "institution": ("institution",),
    "course": ("course_name",),
    "travel_destination": ("destination",),
}

# Which plane a canonical field belongs to.
IDENTITY_CANONICAL: Set[str] = {
    "address", "cadastral_data", "pod", "pdr", "coords",
    "plate", "vin", "brand", "model",
    "employer", "institution", "insured_object",
}
STATE_CANONICAL: Set[str] = {
    "lender", "monthly_installment", "loan_number", "interest_rate", "mortgage_years_left",
    "utility_supplier", "utility_amount", "utility_due_date", "utility_type",
    "consumption", "contract_code",
    "insurance_company", "policy_number", "coverage", "expiry",
    "profession", "course_name", "destination", "start_date", "end_date",
    "price", "document_type", "domain", "status_detail",
}

# Build reverse alias → canonical map
_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for _canon, _aliases in CANONICAL_FIELDS.items():
    for _a in _aliases:
        _ALIAS_TO_CANONICAL.setdefault(_a.lower(), _canon)


def canonical_name(key: str) -> str:
    """Map any alias to its canonical field name (or return normalized key)."""
    k = str(key or "").strip()
    if not k:
        return ""
    return _ALIAS_TO_CANONICAL.get(k.lower(), k)


def plane_for(canonical: str) -> str:
    if canonical in IDENTITY_CANONICAL:
        return "identity"
    if canonical in STATE_CANONICAL:
        return "state"
    # Heuristic
    lower = canonical.lower()
    if any(x in lower for x in ("address", "plate", "vin", "pod", "pdr", "cadastral", "institution", "employer", "brand", "model")):
        return "identity"
    return "state"


def map_properties(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map inbound property bag through registry. Prefer first non-empty value per canonical."""
    out: Dict[str, Any] = {}
    for k, v in (raw or {}).items():
        if v in (None, "", [], {}):
            continue
        canon = canonical_name(k)
        if not canon:
            continue
        # Keep first value; later aliases do not overwrite non-empty
        if canon not in out or out[canon] in (None, "", [], {}):
            out[canon] = v
        # Also preserve original key for backward compat if different
        if k != canon and k not in out:
            # Do not duplicate if already represented
            pass
    return out


def merge_mapped_into(
    *,
    identity: Dict[str, Any],
    state: Dict[str, Any],
    properties: Dict[str, Any],
    delta: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Apply mapped delta into identity/state/properties (non-destructive)."""
    mapped = map_properties(delta)
    id_out = dict(identity or {})
    st_out = dict(state or {})
    props_out = dict(properties or {})
    for canon, v in mapped.items():
        if v in (None, "", [], {}):
            continue
        props_out[canon] = v
        if plane_for(canon) == "identity":
            if canon not in id_out or id_out.get(canon) in (None, "", [], {}):
                id_out[canon] = v
            else:
                # Identity already set — keep existing unless empty
                id_out[canon] = id_out.get(canon) or v
        else:
            st_out[canon] = v
        # Compatibility mirrors for legacy consumers (overwrite state mirrors)
        if canon == "utility_supplier":
            props_out["supplier"] = v
            st_out["supplier"] = v
        if canon == "utility_amount":
            props_out["amount_total"] = v
            st_out["amount_total"] = v
        if canon == "insurance_company":
            props_out["company"] = v
            st_out["company"] = v
        if canon == "cadastral_data":
            props_out["cadastral"] = v
            if "cadastral" not in id_out or id_out.get("cadastral") in (None, "", [], {}):
                id_out["cadastral"] = v
    # Also keep unmapped original keys that were not aliases
    for k, v in (delta or {}).items():
        if v in (None, "", [], {}):
            continue
        if canonical_name(k) == k and k not in mapped:
            props_out[k] = v
            if plane_for(k) == "identity":
                id_out.setdefault(k, v)
            else:
                st_out[k] = v
    return id_out, st_out, props_out


def concept_present(
    concept: str,
    *,
    identity: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    properties: Optional[Dict[str, Any]] = None,
    identity_keys: Optional[Dict[str, str]] = None,
) -> bool:
    """True if the semantic concept is satisfied under any alias/canonical key."""
    fields = CONCEPTS.get(concept)
    if not fields:
        return False
    bags: List[Dict[str, Any]] = [
        dict(identity or {}),
        dict(state or {}),
        dict(properties or {}),
    ]
    ik = dict(identity_keys or {})
    # identity_keys use slightly different names
    ik_aliases = {
        "address": ("address_norm", "address"),
        "cadastral_data": ("cadastral", "cadastral_data"),
        "pod": ("pod",),
        "pdr": ("pdr",),
        "plate": ("plate",),
        "vin": ("vin",),
        "employer": ("employer",),
        "institution": ("institution",),
    }
    for field in fields:
        for bag in bags:
            if _has_value(bag, field):
                return True
            # Check aliases in bag
            for alias in CANONICAL_FIELDS.get(field, ()):
                if _has_value(bag, alias):
                    return True
        for ak in ik_aliases.get(field, (field,)):
            if ik.get(ak):
                return True
    # Special: mortgage concept also via history-assimilated flag checked by caller
    return False


def _has_value(bag: Dict[str, Any], key: str) -> bool:
    v = bag.get(key)
    return v not in (None, "", [], {})


def known_canonical_keys() -> Iterable[str]:
    return CANONICAL_FIELDS.keys()


def all_aliases_for(canonical: str) -> List[str]:
    return list(CANONICAL_FIELDS.get(canonical, ()))
