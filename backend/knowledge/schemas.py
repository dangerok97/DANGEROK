"""
Extensible schema catalog for the Knowledge Layer.

Design notes
------------
- Schemas are DATA, not Pydantic classes. Adding a new field means editing
  a dict; no code changes, no migrations, no restarts of the frontend.
- The schemas describe the shape the KnowledgeService *knows about*. Unknown
  keys are TOLERATED (stored under `extra`) so integrations can push new
  fields without waiting for a schema update.
- `type` values are lightweight hints: "string", "string_list", "number",
  "boolean", "date", "iso_datetime", "object". They inform validation and
  future UI. Nothing is enforced strictly — soft-coerce, never reject.
- Each property has: key, label (Italian), type, optional `options`
  (allowed values for enum-like fields), optional `example`.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _prop(key: str, label: str, type: str = "string", **rest: Any) -> Dict[str, Any]:
    p = {"key": key, "label": label, "type": type}
    p.update(rest)
    return p


# ------------------------------------------------------------------
# Per-node-type schemas. Order in the list is display order.
# ------------------------------------------------------------------
SCHEMAS: Dict[str, List[Dict[str, Any]]] = {
    "home": [
        _prop("home_type", "Tipo casa", "string", options=["casa_principale", "seconda_casa", "affitto", "in_costruzione"]),
        _prop("address", "Indirizzo"),
        _prop("owner", "Proprietario"),
        _prop("residents", "Residenti", "string_list"),
        _prop("utilities", "Forniture", "string_list", example=["luce", "gas", "acqua", "internet"]),
        _prop("contracts", "Contratti", "string_list"),
        _prop("mortgage", "Mutuo", "object"),
        _prop("notary", "Notaio", "object"),
        _prop("insurances", "Assicurazioni", "string_list"),
        _prop("documents", "Documenti", "string_list"),
        _prop("recurring_expenses", "Spese ricorrenti", "object_list"),
        _prop("purchase_date", "Data acquisto", "date"),
    ],
    "car": [
        _prop("brand", "Marca"),
        _prop("model", "Modello"),
        _prop("plate", "Targa"),
        _prop("insurance", "Assicurazione", "object"),
        _prop("road_tax", "Bollo", "object"),
        _prop("mot", "Revisione", "object"),
        _prop("services", "Tagliandi", "object_list"),
        _prop("tires", "Gomme", "object"),
        _prop("warranty", "Garanzia", "object"),
        _prop("owner", "Proprietario"),
        _prop("purchase_date", "Data acquisto", "date"),
        _prop("mileage_km", "Chilometri", "number"),
    ],
    "person": [
        _prop("name", "Nome"),
        _prop("relation", "Relazione", "string", options=["partner", "familiare", "amico", "collega", "professionista", "altro"]),
        _prop("contacts", "Contatti", "object", example={"phone": "", "email": ""}),
        _prop("birthday", "Compleanno", "date"),
        _prop("shared_documents", "Documenti condivisi", "string_list"),
        _prop("shared_events", "Eventi condivisi", "string_list"),
        _prop("notes", "Note", "string"),
    ],
    "document": [
        _prop("doc_type", "Tipo", "string", options=["identita", "sanitario", "fiscale", "contratto", "fattura", "scontrino", "certificato", "altro"]),
        _prop("category", "Categoria"),
        _prop("issued_at", "Data emissione", "date"),
        _prop("expires_at", "Scadenza", "date"),
        _prop("links", "Collegamenti", "string_list"),
        _prop("state", "Stato", "string", options=["valido", "in_scadenza", "scaduto", "archiviato"]),
        _prop("issuer", "Emesso da"),
        _prop("storage", "Dove è archiviato"),
    ],
    "subscription": [
        _prop("provider", "Fornitore"),
        _prop("plan", "Piano"),
        _prop("amount", "Importo", "number"),
        _prop("currency", "Valuta", "string", options=["EUR", "USD", "GBP", "CHF"]),
        _prop("frequency", "Frequenza", "string", options=["mensile", "bimestrale", "trimestrale", "annuale"]),
        _prop("next_payment", "Prossimo pagamento", "date"),
        _prop("payment_method", "Metodo di pagamento"),
        _prop("auto_renew", "Rinnovo automatico", "boolean"),
        _prop("start_date", "Data inizio", "date"),
        _prop("end_date", "Data fine", "date"),
    ],
    "contract": [
        _prop("contract_type", "Tipo contratto"),
        _prop("counterparty", "Controparte"),
        _prop("signed_at", "Data firma", "date"),
        _prop("start_date", "Inizio", "date"),
        _prop("end_date", "Fine", "date"),
        _prop("notice_period_days", "Preavviso disdetta (giorni)", "number"),
        _prop("attachments", "Allegati", "string_list"),
        _prop("value", "Valore economico", "number"),
        _prop("status", "Stato", "string", options=["attivo", "in_scadenza", "cessato"]),
    ],
    "health": [
        _prop("focus", "Ambito", "string", options=["generale", "cardio", "dentistico", "oculistico", "mentale", "altro"]),
        _prop("doctor", "Medico di riferimento"),
        _prop("last_visit", "Ultima visita", "date"),
        _prop("next_checkup", "Prossimo controllo", "date"),
        _prop("medications", "Farmaci", "string_list"),
        _prop("allergies", "Allergie", "string_list"),
        _prop("blood_type", "Gruppo sanguigno"),
        _prop("emergency_contact", "Contatto di emergenza", "object"),
    ],
    "university": [
        _prop("institution", "Ateneo"),
        _prop("program", "Corso di laurea"),
        _prop("year", "Anno di corso", "number"),
        _prop("gpa", "Media", "number"),
        _prop("credits_earned", "CFU acquisiti", "number"),
        _prop("credits_total", "CFU totali", "number"),
        _prop("advisor", "Relatore/Tutor"),
        _prop("graduation_target", "Data laurea prevista", "date"),
    ],
    "job": [
        _prop("company", "Azienda"),
        _prop("role", "Ruolo"),
        _prop("started_at", "Data inizio", "date"),
        _prop("employment_type", "Tipo contratto", "string", options=["indeterminato", "determinato", "partita_iva", "stage", "collaborazione"]),
        _prop("salary_gross_year", "Retribuzione annua lorda", "number"),
        _prop("manager", "Responsabile"),
        _prop("office_address", "Sede"),
        _prop("remote_days_per_week", "Giorni di smart working", "number"),
    ],
    "trip": [
        _prop("destination", "Destinazione"),
        _prop("start_date", "Partenza", "date"),
        _prop("end_date", "Ritorno", "date"),
        _prop("transport", "Trasporto", "string_list", example=["volo", "treno", "auto"]),
        _prop("accommodation", "Alloggio", "object"),
        _prop("companions", "Compagni di viaggio", "string_list"),
        _prop("budget", "Budget", "number"),
        _prop("bookings", "Prenotazioni", "string_list"),
    ],
    "purchase": [
        _prop("item", "Oggetto"),
        _prop("vendor", "Venditore"),
        _prop("amount", "Importo", "number"),
        _prop("currency", "Valuta"),
        _prop("purchased_at", "Data acquisto", "date"),
        _prop("warranty_until", "Fine garanzia", "date"),
        _prop("payment_method", "Metodo di pagamento"),
        _prop("receipt", "Ricevuta / scontrino"),
    ],
    "pet": [
        _prop("name", "Nome"),
        _prop("species", "Specie", "string", options=["cane", "gatto", "uccello", "roditore", "altro"]),
        _prop("breed", "Razza"),
        _prop("birthday", "Compleanno", "date"),
        _prop("vet", "Veterinario"),
        _prop("microchip", "Microchip"),
        _prop("vaccinations", "Vaccinazioni", "object_list"),
        _prop("food_brand", "Cibo abituale"),
    ],
    "goal": [
        _prop("category", "Categoria", "string", options=["finanza", "salute", "lavoro", "studio", "personale", "relazioni"]),
        _prop("target", "Obiettivo misurabile"),
        _prop("target_date", "Data obiettivo", "date"),
        _prop("progress_pct", "Progresso (%)", "number"),
        _prop("motivation", "Motivazione"),
        _prop("milestones", "Milestone", "object_list"),
    ],
    "event": [
        _prop("event_type", "Tipo evento"),
        _prop("location", "Luogo"),
        _prop("starts_at", "Inizio", "iso_datetime"),
        _prop("ends_at", "Fine", "iso_datetime"),
        _prop("participants", "Partecipanti", "string_list"),
        _prop("dress_code", "Dress code"),
        _prop("notes", "Note"),
    ],
    "finance": [
        _prop("account_type", "Tipo conto", "string", options=["corrente", "risparmio", "investimento", "carta_credito", "carta_debito", "wallet"]),
        _prop("bank", "Banca / Istituto"),
        _prop("iban_masked", "IBAN (mascherato)"),
        _prop("balance", "Saldo", "number"),
        _prop("currency", "Valuta"),
        _prop("linked_cards", "Carte collegate", "string_list"),
    ],
    "generic": [
        _prop("summary", "Descrizione sintetica"),
        _prop("tags", "Tag", "string_list"),
        _prop("notes", "Note"),
    ],
}


SUPPORTED_TYPES = frozenset(SCHEMAS.keys())


def schema_for(node_type: str) -> List[Dict[str, Any]]:
    """Return the schema definition for a node type. Falls back to `generic`."""
    return SCHEMAS.get(node_type) or SCHEMAS["generic"]


# ------------------------------------------------------------------
# Soft validation & coercion
# ------------------------------------------------------------------
def _to_number(v: Any) -> Any:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


_TYPE_COERCERS = {
    "string": lambda v: None if v is None else str(v),
    "number": _to_number,
    "boolean": lambda v: bool(v) if v is not None else None,
    "date": lambda v: None if v is None else str(v),
    "iso_datetime": lambda v: None if v is None else str(v),
    "object": lambda v: v if v is None or isinstance(v, dict) else {"value": v},
    "string_list": lambda v: [] if v is None else [str(x) for x in (v if isinstance(v, list) else [v])],
    "object_list": lambda v: [] if v is None else [x if isinstance(x, dict) else {"value": x} for x in (v if isinstance(v, list) else [v])],
}


def coerce_properties(node_type: str, incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Soft-coerce input against the schema for `node_type`.

    Behavior:
      - Known keys: coerced to the declared type.
      - Unknown keys: kept as-is under `_extra`. Never rejected.
      - `None` values erase the field on merge (see service.merge).
    """
    if not isinstance(incoming, dict):
        return {}
    schema = {p["key"]: p for p in schema_for(node_type)}
    out: Dict[str, Any] = {}
    extra: Dict[str, Any] = {}
    for k, v in incoming.items():
        if k == "_extra" and isinstance(v, dict):
            extra.update(v)
            continue
        if k in schema:
            coercer = _TYPE_COERCERS.get(schema[k]["type"])
            out[k] = coercer(v) if coercer else v
        else:
            extra[k] = v
    if extra:
        out["_extra"] = extra
    return out
