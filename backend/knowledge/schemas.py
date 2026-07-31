"""
Extensible schema catalog for the Knowledge Layer.

Design notes
------------
- Schemas are DATA, not Pydantic classes. Adding a new field means editing
  a dict; no code changes, no migrations, no restarts of the frontend.
- The schemas describe the shape the KnowledgeService *knows about*. Unknown
  keys are TOLERATED (stored under `_extra`) so integrations can push new
  fields without waiting for a schema update.
- Every entry declares: `key, label, type, sensitivity` (+ optional
  `options`, `unit`, `format`, `example`).
- `sensitivity` values: `public | personal | sensitive | highly_sensitive`.
  Nothing in this catalog is `highly_sensitive` by default; that tier is
  reserved for future integrations dealing with credentials, health records,
  full card numbers, etc.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _prop(key: str, label: str, type: str = "string", sensitivity: str = "personal", **rest: Any) -> Dict[str, Any]:
    p = {"key": key, "label": label, "type": type, "sensitivity": sensitivity}
    p.update(rest)
    return p


# ------------------------------------------------------------------
# Per-node-type schemas. Order in the list is display order.
# ------------------------------------------------------------------
SCHEMAS: Dict[str, List[Dict[str, Any]]] = {
    "home": [
        _prop("home_type", "Tipo casa", "string", options=["casa_principale", "seconda_casa", "affitto", "in_costruzione"]),
        _prop("address", "Indirizzo", sensitivity="sensitive"),
        _prop("owner", "Proprietario"),
        _prop("residents", "Residenti", "string_list", sensitivity="sensitive"),
        _prop("utilities", "Forniture", "string_list", example=["luce", "gas", "acqua", "internet"]),
        _prop("contracts", "Contratti", "string_list"),
        _prop("mortgage", "Mutuo", "object", sensitivity="sensitive"),
        _prop("notary", "Notaio", "object"),
        _prop("insurances", "Assicurazioni", "string_list"),
        _prop("documents", "Documenti", "string_list"),
        _prop("recurring_expenses", "Spese ricorrenti", "object_list", unit="EUR"),
        _prop("purchase_date", "Data acquisto", "date"),
    ],
    "car": [
        _prop("brand", "Marca", sensitivity="public"),
        _prop("model", "Modello", sensitivity="public"),
        _prop("plate", "Targa", sensitivity="sensitive"),
        _prop("insurance", "Assicurazione", "object"),
        _prop("road_tax", "Bollo", "object", unit="EUR"),
        _prop("mot", "Revisione", "object"),
        _prop("services", "Tagliandi", "object_list"),
        _prop("tires", "Gomme", "object"),
        _prop("warranty", "Garanzia", "object"),
        _prop("owner", "Proprietario"),
        _prop("purchase_date", "Data acquisto", "date"),
        _prop("mileage_km", "Chilometri", "number", unit="km"),
    ],
    "person": [
        _prop("name", "Nome"),
        _prop("relation", "Relazione", "string", options=["partner", "familiare", "amico", "collega", "professionista", "altro"]),
        _prop("contacts", "Contatti", "object", sensitivity="sensitive", example={"phone": "", "email": ""}),
        _prop("birthday", "Compleanno", "date"),
        _prop("shared_documents", "Documenti condivisi", "string_list"),
        _prop("shared_events", "Eventi condivisi", "string_list"),
        _prop("notes", "Note", "string"),
    ],
    "document": [
        _prop("filename", "Nome file"),
        _prop("mime_type", "Tipo MIME"),
        _prop("doc_type", "Tipo", "string", options=["identita", "sanitario", "fiscale", "contratto", "fattura", "scontrino", "certificato", "altro"]),
        _prop("category", "Categoria"),
        _prop("issued_at", "Data emissione", "date"),
        _prop("expires_at", "Scadenza", "date"),
        _prop("links", "Collegamenti", "string_list"),
        _prop("state", "Stato", "string", options=["valido", "in_scadenza", "scaduto", "archiviato"]),
        _prop("issuer", "Emesso da"),
        _prop("storage", "Dove è archiviato", sensitivity="sensitive"),
        _prop("tags", "Tag", "string_list", sensitivity="public"),
        _prop("notes", "Note"),
    ],
    "subscription": [
        _prop("provider", "Fornitore"),
        _prop("plan", "Piano"),
        _prop("amount", "Importo", "number", unit="EUR"),
        _prop("currency", "Valuta", "string", options=["EUR", "USD", "GBP", "CHF"]),
        _prop("frequency", "Frequenza", "string", options=["mensile", "bimestrale", "trimestrale", "annuale"]),
        _prop("next_payment", "Prossimo pagamento", "date"),
        _prop("payment_method", "Metodo di pagamento", sensitivity="sensitive"),
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
        _prop("notice_period_days", "Preavviso disdetta (giorni)", "number", unit="giorni"),
        _prop("attachments", "Allegati", "string_list"),
        _prop("value", "Valore economico", "number", unit="EUR"),
        _prop("status", "Stato", "string", options=["attivo", "in_scadenza", "cessato"]),
    ],
    "health": [
        _prop("focus", "Ambito", "string", sensitivity="sensitive", options=["generale", "cardio", "dentistico", "oculistico", "mentale", "altro"]),
        _prop("doctor", "Medico di riferimento", sensitivity="sensitive"),
        _prop("last_visit", "Ultima visita", "date", sensitivity="sensitive"),
        _prop("next_checkup", "Prossimo controllo", "date"),
        _prop("medications", "Farmaci", "string_list", sensitivity="highly_sensitive"),
        _prop("allergies", "Allergie", "string_list", sensitivity="highly_sensitive"),
        _prop("blood_type", "Gruppo sanguigno", sensitivity="highly_sensitive"),
        _prop("emergency_contact", "Contatto di emergenza", "object", sensitivity="sensitive"),
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
        _prop("salary_gross_year", "Retribuzione annua lorda", "number", unit="EUR", sensitivity="sensitive"),
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
        _prop("budget", "Budget", "number", unit="EUR"),
        _prop("bookings", "Prenotazioni", "string_list"),
    ],
    "purchase": [
        _prop("item", "Oggetto"),
        _prop("vendor", "Venditore"),
        _prop("amount", "Importo", "number", unit="EUR"),
        _prop("currency", "Valuta"),
        _prop("purchased_at", "Data acquisto", "date"),
        _prop("warranty_until", "Fine garanzia", "date"),
        _prop("payment_method", "Metodo di pagamento", sensitivity="sensitive"),
        _prop("receipt", "Ricevuta / scontrino"),
    ],
    "pet": [
        _prop("name", "Nome"),
        _prop("species", "Specie", "string", options=["cane", "gatto", "uccello", "roditore", "altro"]),
        _prop("breed", "Razza"),
        _prop("birthday", "Compleanno", "date"),
        _prop("vet", "Veterinario"),
        _prop("microchip", "Microchip", sensitivity="sensitive"),
        _prop("vaccinations", "Vaccinazioni", "object_list"),
        _prop("food_brand", "Cibo abituale"),
    ],
    "goal": [
        _prop("category", "Categoria", "string", options=["finanza", "salute", "lavoro", "studio", "personale", "relazioni"]),
        _prop("target", "Obiettivo misurabile"),
        _prop("target_date", "Data obiettivo", "date"),
        _prop("progress_pct", "Progresso (%)", "number", unit="%"),
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
        _prop("iban_masked", "IBAN (mascherato)", sensitivity="sensitive"),
        _prop("balance", "Saldo", "number", unit="EUR", sensitivity="sensitive"),
        _prop("currency", "Valuta"),
        _prop("linked_cards", "Carte collegate", "string_list", sensitivity="sensitive"),
    ],
    "generic": [
        _prop("summary", "Descrizione sintetica"),
        _prop("tags", "Tag", "string_list", sensitivity="public"),
        _prop("notes", "Note"),
    ],
}


SUPPORTED_TYPES = frozenset(SCHEMAS.keys())


def schema_for(node_type: str) -> List[Dict[str, Any]]:
    """Return the schema definition for a node type. Falls back to `generic`."""
    return SCHEMAS.get(node_type) or SCHEMAS["generic"]


def schema_index(node_type: str) -> Dict[str, Dict[str, Any]]:
    """Return schema as {key: entry} for O(1) lookup."""
    return {p["key"]: p for p in schema_for(node_type)}


def sensitive_keys_of(node_type: str) -> List[str]:
    """Keys marked `sensitive` or `highly_sensitive` in the schema."""
    return [p["key"] for p in schema_for(node_type) if p.get("sensitivity") in ("sensitive", "highly_sensitive")]
