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
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------
# Regexes (label-aware, priority-ordered to reduce false positives).
#
# Design goal: never let a technical ID (ticket, order, timestamp) slip
# into the "phones" bucket, and never let a raw 11-digit sequence be
# classified as an Italian Codice Fiscale (which is 16 alphanumerics).
# We achieve this via a strict priority pipeline in `extract_entities`
# that reserves character spans as they are claimed.
# ---------------------------------------------------------------------

# --- Self-anchored, high-precision patterns ------------------------
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_URL_RE = re.compile(r"\bhttps?://[^\s<>\"]+", re.IGNORECASE)
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")

_AMOUNT_RE = re.compile(
    r"(?:€|EUR|USD|\$|GBP|£)\s?\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2})?"
    r"|\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2})\s?(?:€|EUR|USD|\$|GBP|£)"
)

_DATE_RES = [
    re.compile(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b"),
    re.compile(r"\b\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}\b"),
    re.compile(
        r"\b\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
        r"agosto|settembre|ottobre|novembre|dicembre|january|february|march|"
        r"april|may|june|july|august|september|october|november|december)"
        r"\s+\d{2,4}\b",
        re.IGNORECASE,
    ),
]
_TIME_RE = re.compile(r"(?<!\d)\d{1,2}[:.]\d{2}(?:[:.]\d{2})?(?!\d)")

# --- Tax IDs (Italy) -----------------------------------------------
# Codice Fiscale (persona fisica): esattamente 16 char, pattern rigido.
_CF_ALPHA_RE = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")
# P.IVA / CF numerico (persona giuridica): esattamente 11 cifre,
# OBBLIGATORIA la label prima ("P.IVA", "Partita IVA", "VAT", "C.F.",
# "Codice Fiscale"). Un numero 11-digit senza label NON è un tax_id.
_PIVA_LABELED_RE = re.compile(
    r"(?i)\b(?:p\.?\s*iva|piva|partita\s+iva|vat(?:\s*(?:number|n[.°]?))?|"
    r"c\.?\s*f\.?|cod(?:ice)?\.?\s*fisc(?:ale)?|codice\s+fiscale)"
    r"[^\d\n]{0,25}(\d{11})(?!\d)"
)

# --- Phones (label-aware or clearly international) -----------------
# Un telefono è ammesso SOLO se:
#   1) preceduto da label esplicita (Tel/Cell/Mob/Phone/Fax/Contatto/WhatsApp)
#   2) oppure porta prefisso internazionale +XX
#   3) oppure rispetta il formato rigido di mobile italiano 3XX + 6-7 cifre
# Inoltre, dopo la normalizzazione, la lunghezza deve essere 7..15 cifre.
_PHONE_LABEL_ALT = (
    r"tel(?:efono)?|cell(?:ulare)?|mob(?:ile)?|phone|fax|contatto|whatsapp"
)
_PHONE_LABELED_RE = re.compile(
    r"(?i)\b(?:" + _PHONE_LABEL_ALT + r")\.?[\s:#\-]{0,10}"
    r"((?:\+?\d{1,3}[\s./\-]?)?(?:\(?\d{2,4}\)?[\s./\-]?)?"
    r"\d{2,4}[\s./\-]?\d{2,4}(?:[\s./\-]?\d{1,4})?)(?!\d)"
)
_PHONE_INTL_RE = re.compile(
    r"(?<![\w+])(\+\d{1,3}[\s./\-]?(?:\(?\d{2,4}\)?[\s./\-]?)?"
    r"\d{2,4}[\s./\-]?\d{2,4}(?:[\s./\-]?\d{1,4})?)(?!\d)"
)
_PHONE_IT_MOBILE_RE = re.compile(
    r"(?<![\w+])(3\d{2}[\s./\-]?\d{6,7})(?!\d)"
)

# --- Order / Ticket / Booking IDs (label-required) ------------------
# Estrae un ID SOLO se preceduto da una label riconoscibile: previene
# la deriva verso categorie "telefono" o "codice fiscale" per token
# tipo `TktID: 128492577` o `Ordine 1750329600`.  Ogni label debole
# ("biglietto", "codice") DEVE portare un qualifier per evitare
# false positive su testo tipo "BIGLIETTO CONCERTO".
_ORDER_LABEL_ALT = (
    r"numero\s+ordine|n[.°]?\s*ordine|ordine|"
    r"order(?:\s*(?:id|number|n[.°]?|no))?|"
    r"prenotazione\s*(?:n[.°]?|id|numero|code|codice)?|"
    r"reservation(?:\s*(?:id|number|n[.°]?|no))?|"
    r"booking(?:\s*(?:id|ref|code|number|n[.°]?))?|"
    r"conferma\s*(?:n[.°]?|id|numero)?|"
    r"riferimento|ref(?:erence)?(?:\s*(?:id|n[.°]?|no|number))?|"
    r"codice\s+(?:ordine|prenotazione|biglietto|conferma|transazione|operazione)|"
    r"tkt(?:\s*id)?|ticket(?:\s*(?:id|number|n[.°]?))?|"
    r"biglietto\s+(?:n[.°]?|id|numero)|"
    r"fattura\s+n[.°]?"
)
_ORDER_LABELED_RE = re.compile(
    r"(?i)\b(?:" + _ORDER_LABEL_ALT + r")[\s:#\-.]{0,10}"
    r"([A-Z0-9][A-Z0-9\-_/]{2,30})\b"
)

# --- Generic long numeric IDs (fallback, non-claimed spans only) ---
_NUMBER_RE = re.compile(r"(?<![\w.,])\d{4,}(?![\w.,])")

_PLACE_KEYWORDS = (
    "via ", "viale ", "corso ", "piazza ", "roma", "milano", "torino",
    "napoli", "firenze", "bologna", "palermo", "genova", "bari", "venezia",
)
_ORG_HINTS = (
    " spa", " srl", " s.p.a", " s.r.l", " inc", " ltd", " gmbh", " sas", " snc",
)


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
def _spans_overlap(span: Tuple[int, int], claimed: List[Tuple[int, int]]) -> bool:
    s, e = span
    for cs, ce in claimed:
        if not (e <= cs or s >= ce):
            return True
    return False


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s or "")


# ---------------------------------------------------------------------
# Entity extraction — strict priority pipeline with span reservation.
#
# Priority (high → low):
#   1. emails / urls / iban   (structural, self-anchored)
#   2. amounts                (must carry currency symbol/code)
#   3. dates                  (strict formats)
#   4. times                  (HH:MM[:SS], not adjacent to more digits)
#   5. tax_ids                (CF alfanumerico 16 char OR P.IVA labelled)
#   6. phones                 (label OR intl prefix OR IT mobile format)
#   7. order/ticket IDs       (label required)
#   8. numbers                (fallback; only unclaimed long digit runs)
# Each priority reserves character spans so lower-priority buckets can
# never re-claim the same characters, killing false positives at the
# root.
# ---------------------------------------------------------------------
def extract_entities(text: str) -> Dict[str, List[str]]:
    if not text:
        return {}

    claimed: List[Tuple[int, int]] = []
    entities: Dict[str, List[str]] = {}

    def _consume(pattern: re.Pattern, group: int = 0) -> List[str]:
        vals: List[str] = []
        for m in pattern.finditer(text):
            try:
                gs, ge = m.span(group)
            except IndexError:
                continue
            if gs < 0:
                continue
            ms, me = m.span(0)  # claim the FULL match span (incl. any label)
            if _spans_overlap((ms, me), claimed):
                continue
            val = m.group(group)
            if val is None:
                continue
            vals.append(val)
            claimed.append((ms, me))
        return vals

    # 1. Emails / URLs / IBAN
    entities["emails"] = _dedup(_consume(_EMAIL_RE), 20)
    entities["urls"]   = _dedup(_consume(_URL_RE), 20)
    entities["iban"]   = _dedup(_consume(_IBAN_RE), 5)

    # 2. Amounts (currency-anchored)
    entities["amounts"] = _dedup(_consume(_AMOUNT_RE), 15)

    # 3. Dates
    dates: List[str] = []
    for r in _DATE_RES:
        dates.extend(_consume(r))
    entities["dates"] = _dedup(dates, 20)

    # 4. Times
    entities["times"] = _dedup(_consume(_TIME_RE), 20)

    # 5. Tax IDs — CF alfanumerico + P.IVA con label
    tax_vals: List[str] = []
    tax_vals.extend(_consume(_CF_ALPHA_RE))
    tax_vals.extend(_consume(_PIVA_LABELED_RE, group=1))
    entities["tax_ids"] = _dedup(tax_vals, 10)

    # 6. Phones — label OR intl prefix OR IT mobile format, 7..15 digits
    phone_vals: List[str] = []
    for pat in (_PHONE_LABELED_RE, _PHONE_INTL_RE, _PHONE_IT_MOBILE_RE):
        for m in pat.finditer(text):
            try:
                gs, ge = m.span(1)
            except IndexError:
                continue
            if gs < 0:
                continue
            val = m.group(1) or ""
            digits = _digits_only(val)
            if not (7 <= len(digits) <= 15):
                continue
            ms, me = m.span(0)
            if _spans_overlap((ms, me), claimed):
                continue
            phone_vals.append(_norm_ws(val))
            claimed.append((ms, me))
    entities["phones"] = _dedup(phone_vals, 20)

    # 7. Order / Ticket / Booking IDs — label required
    order_vals: List[str] = []
    for m in _ORDER_LABELED_RE.finditer(text):
        try:
            gs, ge = m.span(1)
        except IndexError:
            continue
        if gs < 0:
            continue
        ms, me = m.span(0)
        if _spans_overlap((ms, me), claimed):
            continue
        val = _norm_ws(m.group(1) or "")
        low = val.lower()
        if not val or low in ("id", "no", "n", "n.", "num", "number"):
            continue
        # Reject anything without at least one digit (technical IDs are
        # numeric or alphanumeric; a pure-letter capture such as
        # "CONCERTO" after a weak label is almost always a false match).
        if not any(ch.isdigit() for ch in val):
            continue
        # Filter out anything that already looks like a date/time token
        if re.fullmatch(r"\d{1,2}[:.]\d{2}(?:[:.]\d{2})?", val):
            continue
        order_vals.append(val)
        claimed.append((ms, me))
    entities["order_ids"] = _dedup(order_vals, 20)

    # 8. Generic long numeric IDs (fallback, unclaimed spans only)
    generic_nums: List[str] = []
    for m in _NUMBER_RE.finditer(text):
        s, e = m.span(0)
        if _spans_overlap((s, e), claimed):
            continue
        generic_nums.append(m.group(0))
        claimed.append((s, e))
    # Backward-compat: `numbers` unifies order_ids + generic ids.
    entities["numbers"] = _dedup(order_vals + generic_nums, 25)

    # Places — line-level heuristic
    places = [ln.strip() for ln in text.splitlines()
              if any(k in ln.lower() for k in _PLACE_KEYWORDS)]
    entities["places"] = _dedup(places, 10)
    # Organizations — line-level heuristic
    orgs = [ln.strip() for ln in text.splitlines()
            if any(h in ln.lower() for h in _ORG_HINTS)]
    entities["organizations"] = _dedup(orgs, 10)
    # Persons — extremely conservative: uppercase bigrams at line start
    person_re = re.compile(
        r"^([A-ZÀÈÉÌÒÙ][a-zà-ù]+(?:\s+[A-ZÀÈÉÌÒÙ][a-zà-ù]+){1,2})$",
        re.MULTILINE,
    )
    entities["persons"] = _dedup(person_re.findall(text), 15)

    # Drop empty categories to keep the payload lean.
    return {k: v for k, v in entities.items() if v}


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
        # Prefer label-anchored order/ticket IDs; fall back to any long number.
        if entities.get("order_ids"):
            fields.append(("Numero ordine", entities["order_ids"][0]))
        elif entities.get("numbers"):
            fields.append(("Numero ordine", entities["numbers"][0]))

    if type_key == "invoice":
        if entities.get("amounts"):
            fields.append(("Totale", entities["amounts"][-1]))
        if entities.get("order_ids"):
            fields.append(("Numero fattura", entities["order_ids"][0]))
        elif entities.get("numbers"):
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
