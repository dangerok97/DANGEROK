"""Document Insights — pure deterministic extractor.

NO LLM, NO OCR re-run. Reads only fields already persisted on the
`documents` collection by Iteration 20 (extracted_text + metadata) and
returns a structured, ready-to-render insights payload.

Categories extracted (regex-based, tuned for IT + EN docs):
    persons, organizations, places, dates, times, numbers, amounts,
    emails, phones, urls, iban, tax_ids.

Also produces a lightweight "structured summary": type-detection via
keyword bag + candidate field selection from raw text.
"""
from __future__ import annotations

import re
from collections import Counter, OrderedDict
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------
# Regexes (anchored to reduce false positives)
# ---------------------------------------------------------------------
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_URL_RE = re.compile(r"\bhttps?://[^\s<>\"]+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]?)?\d{2,4}[ .-]?\d{2,4}[ .-]?\d{0,4}(?!\d)")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_TAX_RE = re.compile(r"\b(?:[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]|\b\d{11}\b)\b")  # CF or P.IVA IT

_DATE_RES = [
    re.compile(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b"),
    re.compile(r"\b\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}\b"),
    re.compile(r"\b\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{2,4}\b", re.IGNORECASE),
]
_TIME_RE = re.compile(r"(?<!\d)\d{1,2}[:.]\d{2}(?:[:.]\d{2})?\b")
_AMOUNT_RE = re.compile(r"(?:€|EUR|USD|\$|GBP|£)\s?\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2})?|\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2})\s?(?:€|EUR|USD|\$|GBP|£)")
_NUMBER_RE = re.compile(r"(?<![\w.,])\d{4,}(?![\w.,])")  # long numeric ids (>=4 digits)

_PLACE_KEYWORDS = ("via ", "viale ", "corso ", "piazza ", "roma", "milano", "torino", "napoli", "firenze",
                   "bologna", "palermo", "genova", "bari", "venezia")
_ORG_HINTS = (" spa", " srl", " s.p.a", " s.r.l", " inc", " ltd", " gmbh", " sas", " snc")


# ---------------------------------------------------------------------
# Structured summary — keyword-based type detection + heuristic fields
# ---------------------------------------------------------------------
_TYPE_HINTS: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("Biglietto concerto", "ticket", ("biglietto", "concerto", "ingresso", "porte", "gate", "posto", "settore")),
    ("Biglietto evento",   "ticket", ("biglietto", "evento", "manifestazione", "spettacolo")),
    ("Biglietto viaggio",  "ticket", ("volo", "flight", "boarding", "carta d'imbarco", "treno", "italo", "trenitalia")),
    ("Fattura",            "invoice", ("fattura", "invoice", "totale imponibile", "iva", "vat")),
    ("Scontrino",          "receipt", ("scontrino", "ricevuta fiscale", "totale complessivo")),
    ("Contratto",          "contract", ("contratto", "agreement", "sottoscritto", "clausola", "articolo 1")),
    ("Bolletta",           "bill", ("bolletta", "utenza", "consumo", "importo da pagare", "scadenza pagamento")),
    ("Certificato",        "certificate", ("certificato", "attestato", "certifica")),
    ("Referto sanitario",  "medical", ("referto", "analisi", "esami", "diagnosi", "medico")),
    ("Documento identità", "id",       ("carta d'identità", "codice fiscale", "passaporto", "patente")),
]


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _dedup(items: List[str], limit: int = 20) -> List[str]:
    seen = OrderedDict()
    for it in items:
        k = _norm_ws(it).lower()
        if not k or k in seen:
            continue
        seen[k] = _norm_ws(it)
        if len(seen) >= limit:
            break
    return list(seen.values())


# ---------------------------------------------------------------------
# Entity extraction (regex over raw text)
# ---------------------------------------------------------------------
def extract_entities(text: str) -> Dict[str, List[str]]:
    if not text:
        return {}
    T = text
    out: Dict[str, List[str]] = {
        "emails": _dedup(_EMAIL_RE.findall(T), 20),
        "urls":   _dedup(_URL_RE.findall(T), 20),
        "phones": _dedup([m.group(0) for m in _PHONE_RE.finditer(T) if len(re.sub(r"\D", "", m.group(0))) >= 8], 20),
        "iban":   _dedup(_IBAN_RE.findall(T), 5),
        "tax_ids": _dedup(_TAX_RE.findall(T), 10),
        "amounts": _dedup(_AMOUNT_RE.findall(T), 15),
        "times":  _dedup(_TIME_RE.findall(T), 20),
        "numbers": _dedup(_NUMBER_RE.findall(T), 25),
    }
    dates: List[str] = []
    for r in _DATE_RES:
        dates.extend(r.findall(T))
    out["dates"] = _dedup(dates, 20)
    # Places: heuristic — lines containing an italian address keyword.
    lower = T.lower()
    places = [ln.strip() for ln in T.splitlines()
              if any(k in ln.lower() for k in _PLACE_KEYWORDS)]
    out["places"] = _dedup(places, 10)
    # Organizations: lines with company suffix
    orgs = [ln.strip() for ln in T.splitlines() if any(h in ln.lower() for h in _ORG_HINTS)]
    out["organizations"] = _dedup(orgs, 10)
    # Persons — extremely conservative: uppercase bigrams at start of lines
    person_re = re.compile(r"^([A-ZÀÈÉÌÒÙ][a-zà-ù]+(?:\s+[A-ZÀÈÉÌÒÙ][a-zà-ù]+){1,2})$", re.MULTILINE)
    persons = person_re.findall(T)
    out["persons"] = _dedup(persons, 15)

    # Drop empty categories to keep the payload lean.
    return {k: v for k, v in out.items() if v}


# ---------------------------------------------------------------------
# Type detection + structured summary
# ---------------------------------------------------------------------
def detect_type(text: str, filename: str, mime_type: str) -> Tuple[str, str]:
    """Returns (label, key). Falls back to a mime-based generic label."""
    if not text:
        return _fallback_type(filename, mime_type)
    lower = (text + " " + (filename or "")).lower()
    best: Optional[Tuple[str, str, int]] = None
    for label, key, hints in _TYPE_HINTS:
        score = sum(1 for h in hints if h in lower)
        if score > 0 and (best is None or score > best[2]):
            best = (label, key, score)
    if best:
        return best[0], best[1]
    return _fallback_type(filename, mime_type)


def _fallback_type(filename: str, mime_type: str) -> Tuple[str, str]:
    mt = (mime_type or "").lower()
    if mt == "application/pdf":
        return "Documento PDF", "pdf"
    if mt.startswith("image/"):
        return "Immagine / scansione", "image"
    if mt.startswith("text/"):
        return "Documento di testo", "text"
    return "Documento", "generic"


def _first_matching_line(text: str, keywords: Tuple[str, ...]) -> Optional[str]:
    if not text:
        return None
    for ln in text.splitlines():
        low = ln.lower()
        if any(k in low for k in keywords):
            s = _norm_ws(ln)
            if 3 <= len(s) <= 200:
                return s
    return None


def build_structured_summary(
    text: str, entities: Dict[str, List[str]], type_key: str, doc: Dict[str, Any],
) -> Dict[str, Optional[str]]:
    """Emit an ordered dict of human-readable {label: value} pairs. Any
    value that would be empty is omitted from the result."""
    fields: List[Tuple[str, Optional[str]]] = []

    fields.append(("Tipo", None))  # filled by caller (label from detect_type)

    # Common candidates
    if entities.get("dates"):
        fields.append(("Data", entities["dates"][0]))
    if entities.get("times"):
        # If we have >= 2 times, first is often "porta/apertura" and last is "inizio"
        times = entities["times"]
        fields.append(("Ora", times[-1]))
        if len(times) >= 2:
            fields.append(("Apertura porte", times[0]))
    if entities.get("places"):
        fields.append(("Luogo", entities["places"][0]))
    if entities.get("organizations"):
        fields.append(("Azienda / Ente", entities["organizations"][0]))

    if type_key == "ticket":
        # Try to find the "event name": a capitalized short line near the top
        event = _first_matching_line(text, ("evento", "concerto", "tour", "artist"))
        if not event and text:
            for ln in text.splitlines()[:10]:
                s = _norm_ws(ln)
                if s.isupper() and 3 <= len(s) <= 60:
                    event = s
                    break
        if event:
            fields.append(("Evento", event))
        order = _first_matching_line(text, ("ordine", "order", "prenotazione", "reservation", "biglietto"))
        if order and entities.get("numbers"):
            fields.append(("Numero ordine", entities["numbers"][0]))
        elif entities.get("numbers"):
            fields.append(("Numero ordine", entities["numbers"][0]))

    if type_key == "invoice":
        if entities.get("amounts"):
            fields.append(("Totale", entities["amounts"][-1]))
        if entities.get("numbers"):
            fields.append(("Numero fattura", entities["numbers"][0]))
        if entities.get("tax_ids"):
            fields.append(("P.IVA/CF", entities["tax_ids"][0]))
        if entities.get("iban"):
            fields.append(("IBAN", entities["iban"][0]))

    if type_key == "bill":
        if entities.get("amounts"):
            fields.append(("Importo", entities["amounts"][-1]))
        if entities.get("dates"):
            fields.append(("Scadenza", entities["dates"][-1]))

    if type_key == "receipt":
        if entities.get("amounts"):
            fields.append(("Totale", entities["amounts"][-1]))

    if type_key == "contract":
        if entities.get("persons"):
            fields.append(("Sottoscrittore", entities["persons"][0]))
        if entities.get("dates"):
            fields.append(("Data firma", entities["dates"][0]))

    if type_key == "medical":
        if entities.get("dates"):
            fields.append(("Data referto", entities["dates"][0]))
        if entities.get("persons"):
            fields.append(("Paziente", entities["persons"][0]))

    if doc.get("created_at"):
        fields.append(("Documento caricato", str(doc["created_at"])[:10]))

    # Drop dupes / empty
    seen_keys = set()
    result: List[Tuple[str, str]] = []
    for k, v in fields:
        if k in seen_keys:
            continue
        if v is None:
            continue
        seen_keys.add(k)
        result.append((k, v))
    return {"fields": [{"label": k, "value": v} for k, v in result]}


# ---------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------
def compute_insights(doc: Dict[str, Any]) -> Dict[str, Any]:
    text = doc.get("extracted_text") or ""
    filename = doc.get("filename") or ""
    mime = doc.get("mime_type") or ""
    entities = extract_entities(text)
    type_label, type_key = detect_type(text, filename, mime)

    summary = build_structured_summary(text, entities, type_key, doc)
    # Inject the detected type as the first field of the summary
    summary_fields = [{"label": "Tipo", "value": type_label}] + summary["fields"]

    return {
        "id": doc.get("id"),
        "filename": filename,
        "type_key": type_key,
        "type_label": type_label,
        "summary": {"fields": summary_fields},
        "entities": entities,
        "extraction": {
            "engine": doc.get("extraction_engine"),
            "method": ("OCR" if doc.get("ocr_used") else "PDF" if (mime == "application/pdf") else "TEXT"),
            "text_extracted": bool(doc.get("text_extracted")),
            "ocr_used": bool(doc.get("ocr_used")),
            "pages": doc.get("pages"),
            "language": doc.get("detected_language"),
            "confidence": doc.get("confidence"),
            "duration_ms": doc.get("extraction_duration_ms"),
            "extracted_at": doc.get("extracted_at"),
            "error_code": doc.get("extraction_error_code"),
        },
        "technical_metadata": {
            "hash": doc.get("hash"),
            "size": doc.get("size"),
            "mime_type": mime,
            "storage_provider": doc.get("storage_provider"),
            "original_filename": doc.get("original_filename"),
        },
        "history": {
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "archived": bool(doc.get("archived")),
            "deleted": bool(doc.get("deleted")),
            "version": doc.get("version") or 1,
            "upload_source": doc.get("upload_source"),
        },
        "content": {
            "text": text,
            "length": len(text),
        },
    }
