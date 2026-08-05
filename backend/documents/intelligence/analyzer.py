"""Local (+ optional LLM) structured document analysis."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from documents.insights import compute_insights
from documents.intelligence.schemas import (
    DocumentAnalysis,
    EducationAnalysis,
    EntityItem,
    EventCandidate,
    GenericAction,
    LLMDocumentEnrichment,
)
from documents.intelligence.taxonomy import candidate_actions, refine_taxonomy
from llm import LLMNotConfigured, llm_status
from llm.errors import LLMQuotaError, LLMRateLimitError, LLMTimeoutError
from llm.structured import chat_json, chunk_text


def _user_llm_pref(user: Optional[dict]) -> Optional[str]:
    if not user:
        return None
    prefs = user.get("preferences") or {}
    val = (prefs.get("llm_provider") or "").strip().lower()
    return val or None

logger = logging.getLogger("ora.documents.intel")

PROMPT_VERSION = "doc-intel-json-2"

_IT_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_event_id() -> str:
    return f"evc_{uuid.uuid4().hex[:12]}"


def _ai_consent_enabled(user: Optional[dict]) -> bool:
    if user is None:
        return True
    prefs = user.get("preferences") or {}
    # Default allow AI analysis unless explicitly false
    return prefs.get("document_ai_analysis", True) is not False


def _env_ai_documents() -> bool:
    return os.environ.get("DOCUMENT_AI_ENABLED", "1").lower() in ("1", "true", "yes")


def maps_query_url(query: str) -> str:
    from urllib.parse import quote_plus
    q = quote_plus(query.strip())
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def maps_directions_url(query: str) -> str:
    from urllib.parse import quote_plus
    q = quote_plus(query.strip())
    return f"https://www.google.com/maps/dir/?api=1&destination={q}"


def _parse_italian_datetime(text: str) -> tuple[Optional[datetime], bool, Optional[str]]:
    """Return (utc_dt, ambiguous, original_snippet)."""
    if not text:
        return None, False, None
    # ISO-ish
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm = int(m.group(4) or 0), int(m.group(5) or 0)
        try:
            local = datetime(y, mo, d, hh, mm, tzinfo=ZoneInfo("Europe/Rome"))
            return local.astimezone(timezone.utc), False, m.group(0)
        except Exception:
            pass

    # d month yyyy
    m = re.search(
        r"(\d{1,2})\s+(" + "|".join(_IT_MONTHS.keys()) + r")\s+(\d{4})(?:\s*(?:ore\s*)?(\d{1,2})[:\.](\d{2}))?",
        text,
        re.I,
    )
    if m:
        d, mon, y = int(m.group(1)), _IT_MONTHS[m.group(2).lower()], int(m.group(3))
        hh, mm = int(m.group(4) or 0), int(m.group(5) or 0)
        try:
            local = datetime(y, mon, d, hh, mm, tzinfo=ZoneInfo("Europe/Rome"))
            return local.astimezone(timezone.utc), False, m.group(0)
        except Exception:
            pass

    # dd/mm/yyyy or ambiguous mm/dd
    m = re.search(r"\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})\b(?:\s*(?:ore\s*)?(\d{1,2})[:\.](\d{2}))?", text)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        hh, mm = int(m.group(4) or 0), int(m.group(5) or 0)
        ambiguous = a <= 12 and b <= 12 and a != b
        # Prefer IT: day/month
        day, month = a, b
        if ambiguous:
            # keep IT preference but flag
            pass
        if month > 12 and a <= 12:
            day, month = b, a
            ambiguous = False
        try:
            local = datetime(y, month, day, hh, mm, tzinfo=ZoneInfo("Europe/Rome"))
            return local.astimezone(timezone.utc), ambiguous, m.group(0)
        except Exception:
            return None, True, m.group(0)

    return None, False, None


def _priority_urgency(macro: str, sub: str, start: Optional[datetime]) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    priority = "medium"
    urgency = "none"
    if macro == "medical" or "exam" in sub or "appointment" in sub:
        priority = "high"
    if "invoice" in sub or "tax" in sub or "official" in sub:
        priority = "high"
    if macro == "event" and "concert" in sub:
        priority = "medium"
    if start is None:
        return priority, urgency
    delta = start - now
    days = delta.total_seconds() / 86400
    if days < 0:
        urgency = "overdue"
        priority = "critical" if priority in ("high", "critical") else "high"
    elif days <= 2:
        urgency = "urgent"
        if priority == "medium":
            priority = "high"
    elif days <= 7:
        urgency = "soon"
    elif days <= 30:
        urgency = "upcoming"
    if "exam" in sub or macro == "medical":
        if days <= 30 and priority != "critical":
            priority = "high"
    return priority, urgency


def _field_map(insights: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in insights.get("resolved_fields") or []:
        k = f.get("field_key") or f.get("label")
        v = f.get("value")
        if k and v:
            out[str(k)] = str(v)
    return out


def _clean_field(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    s = str(v).strip()
    # Drop values that look like labeled leftovers
    if re.match(r"(?i)^(indirizzo|luogo|data|ora|citt[aà]|venue)\s*:", s):
        return None
    return s[:120]


def _suggest_title(macro: str, sub: str, fields: dict, filename: str, text: str) -> str:
    if macro == "medical" or "appointment" in sub:
        struct = _clean_field(
            fields.get("venue")
            or _extract_labeled(text, ("Struttura", "Presso", "Luogo"))
        )
        date = _clean_field(
            fields.get("event_date")
            or fields.get("date")
            or _extract_labeled(text, ("Data", "Data visita"))
        )
        parts = [p for p in ("Visita specialistica", struct, date) if p]
        return " – ".join(parts)[:160]
    if macro == "travel" and "train" in sub:
        origin = _extract_labeled(text, ("Stazione partenza", "Partenza da", "Origine", "Da"))
        dest = _extract_labeled(text, ("Stazione arrivo", "Arrivo a", "Destinazione", "A"))
        if origin or dest:
            return f"Treno {(origin or '?')} -> {(dest or '?')}"[:160]
    if macro == "event" or "ticket" in sub:
        artist = _clean_field(
            fields.get("artist")
            or fields.get("event_name")
            or _extract_labeled(text, ("Artista", "Evento", "Titolo"))
            or fields.get("title")
        )
        venue = _clean_field(
            fields.get("venue")
            or _extract_labeled(text, ("Venue", "Luogo", "Struttura"))
        )
        date = _clean_field(
            fields.get("event_date")
            or fields.get("date")
            or _extract_labeled(text, ("Data", "Data evento"))
        )
        parts = [p for p in (artist, venue, date) if p]
        if parts:
            return " – ".join(parts)[:160]
    if macro == "education":
        subject = fields.get("subject") or _guess_subject(text)
        topic = fields.get("topic") or _extract_labeled(text, ("Argomento", "Topic"))
        if subject and topic:
            return f"{subject} – {topic}"[:160]
        if subject:
            return f"Dispensa / appunti – {subject}"[:160]
    if macro == "administrative":
        obj = _extract_labeled(text, ("Oggetto", "Subject"))
        if obj:
            return f"Comunicazione – {obj}"[:160]
    if macro == "financial" or sub == "invoice":
        supplier = fields.get("supplier") or fields.get("vendor")
        date = fields.get("date") or fields.get("invoice_date")
        if supplier:
            return f"Fattura {supplier}" + (f" – {date}" if date else "")
    if macro == "receipt":
        merchant = fields.get("merchant") or fields.get("vendor")
        if merchant:
            return f"Ricevuta – {merchant}"[:160]
    # clean filename
    base = re.sub(r"[_-]+", " ", os_path_stem(filename)).strip()
    if re.match(r"^(img|scan|documento|doc|ticket|file|caso)\s*", base, re.I):
        return f"Documento {macro}" if macro != "generic" else base[:120] or filename
    return base[:160] or filename


def os_path_stem(name: str) -> str:
    import os
    return os.path.splitext(os.path.basename(name or "documento"))[0]


def _guess_subject(text: str) -> Optional[str]:
    m = re.search(r"(?i)\b(?:materia|corso|insegnamento)\s*[:\-]\s*([^\n]{3,60})", text or "")
    if m:
        return m.group(1).strip()
    for subj in (
        "antropologia", "storia", "matematica", "fisica", "chimica", "diritto",
        "economia", "filosofia", "informatica", "biologia", "letteratura",
    ):
        if subj in (text or "").lower():
            return subj.capitalize()
    return None


def _extract_labeled(text: str, labels: tuple[str, ...]) -> Optional[str]:
    for lab in labels:
        m = re.search(rf"(?im)^\s*{re.escape(lab)}\s*[:\-]\s*(.+)$", text or "")
        if m:
            return m.group(1).strip()[:200]
    return None


def _doors_vs_event_times(text: str) -> tuple[Optional[str], Optional[str]]:
    """Return (doors_open_hhmm, event_start_hhmm) without confusing the two."""
    doors = None
    start = None
    m = re.search(r"(?i)apertura\s+porte\s*[:\-]?\s*(\d{1,2})[:\.](\d{2})", text or "")
    if m:
        doors = f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(
        r"(?i)(?:inizio\s+(?:evento|concerto|spettacolo)|ora\s+inizio|ore)\s*[:\-]?\s*(\d{1,2})[:\.](\d{2})",
        text or "",
    )
    if m:
        start = f"{int(m.group(1)):02d}:{m.group(2)}"
    return doors, start


def _build_events(
    *,
    doc_id: str,
    macro: str,
    sub: str,
    fields: dict,
    text: str,
    entities: dict,
) -> list[EventCandidate]:
    if macro not in ("event", "travel", "medical") and "ticket" not in sub and "appointment" not in sub:
        # still check strong event signals
        if not re.search(r"(?i)\b(concerto|biglietto|appuntamento|visita|spettacolo|cinema)\b", text or ""):
            return []

    dates = list(entities.get("dates") or [])
    times = list(entities.get("times") or [])
    places = list(entities.get("places") or [])

    date_src = (
        fields.get("event_date")
        or fields.get("date")
        or _extract_labeled(text, ("Data", "Data evento", "Data visita", "Giorno"))
        or (dates[0] if dates else "")
    )
    doors_t, event_t = _doors_vs_event_times(text)
    time_src = (
        fields.get("event_time")
        or event_t
        or fields.get("time")
        or _extract_labeled(text, ("Ora", "Orario", "Ora visita", "Partenza"))
        or (times[0] if times else "")
    )
    # Prefer event start over doors-open for the calendar start
    if event_t:
        time_src = event_t
    combined = f"{date_src} {time_src}".strip()
    start, ambiguous, original = _parse_italian_datetime(combined or text[:500])
    if start is None and date_src:
        start, ambiguous, original = _parse_italian_datetime(date_src)

    # For ambiguous numeric dates with insufficient context, do not silently pick
    if ambiguous and not re.search(r"(?i)\b(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\b", text or ""):
        start = None

    origin = _extract_labeled(text, ("Stazione partenza", "Partenza da", "Origine", "Da"))
    dest = _extract_labeled(text, ("Stazione arrivo", "Arrivo a", "Destinazione", "A"))
    if sub == "train_ticket" or (origin and dest):
        venue = f"{origin or '?'} → {dest or '?'}"
        address = None
        city = dest or fields.get("city")
        title = f"Treno {origin or ''} → {dest or ''}".strip()
    else:
        venue = (
            _clean_field(fields.get("venue"))
            or _clean_field(fields.get("location"))
            or _extract_labeled(text, ("Venue", "Struttura", "Luogo", "Presso"))
            or _clean_field(places[0] if places else None)
        )
        address = _clean_field(fields.get("address")) or _extract_labeled(text, ("Indirizzo", "Address"))
        city = _clean_field(fields.get("city")) or _extract_labeled(text, ("Città", "Citta", "City"))
        title = (
            _clean_field(fields.get("event_name"))
            or _clean_field(fields.get("artist"))
            or _extract_labeled(text, ("Artista", "Evento", "Titolo"))
            or _clean_field(fields.get("title"))
            or ("Visita medica" if macro == "medical" else "Appuntamento")
        )

    booking = (
        fields.get("order_id")
        or fields.get("booking_reference")
        or fields.get("pnr")
        or _extract_labeled(text, ("Codice prenotazione", "Codice ordine", "PNR", "Ordine"))
    )
    missing = []
    if not start:
        missing.append("start_datetime")
    if not venue and not address and not (origin or dest):
        missing.append("location")
    if not title or title == "Appuntamento":
        missing.append("title")
    if ambiguous:
        missing.append("date_disambiguation")

    priority, urgency = _priority_urgency(macro, sub, start)
    venue = _clean_field(venue)
    address = _clean_field(address)
    city = _clean_field(city)
    # If field map polluted venue with address label, recover from labels
    if not venue:
        venue = _extract_labeled(text, ("Venue", "Struttura", "Luogo", "Presso"))
    loc_parts = [p for p in (venue, address, city) if p]
    maps_q = ", ".join(loc_parts) if loc_parts else None

    end = None
    arrival = _extract_labeled(text, ("Orario arrivo", "Arrivo", "Ora arrivo"))
    if start and arrival:
        am = re.search(r"(\d{1,2})[:\.](\d{2})", arrival)
        if am:
            try:
                local_end = start.astimezone(ZoneInfo("Europe/Rome")).replace(
                    hour=int(am.group(1)), minute=int(am.group(2)),
                )
                end = local_end.astimezone(timezone.utc).isoformat()
            except Exception:
                end = (start + timedelta(hours=2)).isoformat()
    elif start and time_src and re.search(r"(\d{1,2}[:\.]\d{2})\s*[-–]\s*(\d{1,2}[:\.]\d{2})", time_src):
        m = re.search(r"(\d{1,2})[:\.](\d{2})\s*[-–]\s*(\d{1,2})[:\.](\d{2})", time_src)
        if m and start:
            try:
                local_end = start.astimezone(ZoneInfo("Europe/Rome")).replace(
                    hour=int(m.group(3)), minute=int(m.group(4)),
                )
                end = local_end.astimezone(timezone.utc).isoformat()
            except Exception:
                end = (start + timedelta(hours=2)).isoformat()
    elif start:
        end = (start + timedelta(hours=2)).isoformat()

    conf = 0.75
    if missing:
        conf -= 0.15 * len(missing)
    if ambiguous:
        conf -= 0.25
    conf = max(0.15, min(0.95, conf))

    notes = ["Estrazione locale da testo e campi risolti"]
    if doors_t and event_t and doors_t != event_t:
        notes.append(f"Apertura porte {doors_t}; inizio evento {event_t} (usato inizio evento)")
    if origin and dest:
        notes.append(f"Origine/destinazione distinte: {origin} / {dest}")

    ev = EventCandidate(
        id=_new_event_id(),
        title=str(title)[:160],
        description=(text or "")[:400],
        start_datetime=start.isoformat() if start else None,
        end_datetime=end,
        start_text_original=original,
        venue_name=venue,
        address=address,
        city=city,
        booking_reference=booking,
        source_document_id=doc_id,
        category=sub if sub else macro,
        priority=priority,  # type: ignore
        urgency=urgency,  # type: ignore
        confidence=conf,
        missing_fields=missing,
        extraction_notes="; ".join(notes),
        ambiguous_date=ambiguous,
        maps_query=maps_q,
        status="proposed",
    )
    return [ev]


def _build_education(text: str, fields: dict, keywords: list[str]) -> Optional[EducationAnalysis]:
    subject = fields.get("subject") or _guess_subject(text)
    if not subject and not any(k in (text or "").lower() for k in ("appunti", "dispensa", "lezione", "esame")):
        return None
    # naive concept bullets: lines with ":" or capitalized terms
    concepts = []
    for line in (text or "").splitlines():
        line = line.strip()
        if 10 < len(line) < 120 and (":" in line or line[:1].isupper()):
            concepts.append(line[:120])
        if len(concepts) >= 8:
            break
    defs = [c for c in concepts if ":" in c][:6]
    summary = " ".join((text or "").split())[:400]
    detailed = " ".join((text or "").split())[:1200]
    edu = EducationAnalysis(
        subject=subject,
        topic=fields.get("topic"),
        suggested_title=f"{subject or 'Studio'} – appunti"[:160],
        summary_short=summary[:280],
        summary_detailed=detailed,
        key_concepts=concepts[:8],
        definitions=defs,
        keywords=keywords[:12],
        questions_for_review=[
            f"Quali sono i concetti principali di {subject}?" if subject else "Quali concetti emergono dal testo?",
            "Quali definizioni sono presenti nel documento?",
        ],
        confidence=0.55 if subject else 0.4,
    )
    from documents.intelligence.study_tools import enrich_education
    return EducationAnalysis(**enrich_education(edu.model_dump(), text))


def content_fingerprint(text: str, filename: str = "") -> str:
    h = hashlib.sha256()
    h.update((filename or "").encode("utf-8", errors="replace"))
    h.update(b"\0")
    h.update((text or "").encode("utf-8", errors="replace"))
    return h.hexdigest()[:32]


async def analyze_document(
    doc: dict[str, Any],
    *,
    user: Optional[dict] = None,
    force_local: bool = False,
    force_ai: bool = False,
) -> dict[str, Any]:
    """Return validated analysis payload to persist on the document."""
    insights = compute_insights(doc)
    text = (doc.get("extracted_text") or "")
    filename = doc.get("original_filename") or doc.get("filename") or "documento"
    content_hash = content_fingerprint(text, filename)
    type_key = insights.get("type_key") or insights.get("classification", {}).get("type_key") or "generic"
    tax = refine_taxonomy(type_key=type_key, text=text, filename=filename)
    fields = _field_map(insights)
    entities_raw = insights.get("entities") or {}
    keywords = []
    for k in ("organizations", "places", "persons"):
        for v in entities_raw.get(k) or []:
            if v and v not in keywords:
                keywords.append(v)
    keywords = keywords[:15]

    base_conf = float(insights.get("classification", {}).get("confidence") or 50) / 100.0
    title = _suggest_title(tax["macro_category"], tax["subcategory"], fields, filename, text)
    events = _build_events(
        doc_id=doc["id"],
        macro=tax["macro_category"],
        sub=tax["subcategory"],
        fields=fields,
        text=text,
        entities=entities_raw,
    )
    education = None
    if tax["macro_category"] == "education":
        education = _build_education(text, fields, keywords)

    entity_items = []
    for etype, vals in entities_raw.items():
        if etype == "technical_ids":
            continue
        for v in (vals or [])[:10]:
            entity_items.append(EntityItem(type=etype, value=str(v), confidence=0.6))

    actions = candidate_actions(tax["macro_category"], tax["subcategory"])
    warnings: list[str] = []
    if not text.strip():
        warnings.append("Nessun testo estraibile; analisi limitata ai metadati.")
    if any(e.ambiguous_date for e in events):
        warnings.append("Data ambigua: conferma richiesta prima di creare l'evento.")
    if doc.get("ocr_used"):
        warnings.append("Testo ottenuto via OCR: verifica i campi importanti.")

    requires_review = bool(
        warnings
        or any(e.missing_fields or e.ambiguous_date or e.confidence < 0.55 for e in events)
        or base_conf < 0.5
    )

    ai_used = False
    ai_skipped_dedupe = False
    model_name = "local-deterministic"
    usage_meta: dict[str, Any] = {}
    summary = (text[:280] if text else f"Documento {tax['macro_category']}").strip()
    summary_detailed = (text[:1200] if text else summary).strip()

    prev = doc.get("analysis") or {}
    same_content = (
        prev.get("content_hash") == content_hash
        and prev.get("ai_used")
        and prev.get("prompt_version") == PROMPT_VERSION
    )

    allow_ai = (
        not force_local
        and _env_ai_documents()
        and _ai_consent_enabled(user)
        and llm_status().get("configured")
        and bool(text.strip())
    )
    if allow_ai and same_content and not force_ai:
        # Deduplicate: reuse previous AI enrichment fields, recompute local events
        ai_used = True
        ai_skipped_dedupe = True
        model_name = prev.get("model") or llm_status().get("model") or "llm"
        title = prev.get("suggested_title") or title
        summary = prev.get("summary") or summary
        summary_detailed = prev.get("summary_detailed") or summary_detailed
        if prev.get("keywords"):
            keywords = list(dict.fromkeys(list(prev.get("keywords") or []) + keywords))[:15]
        usage_meta = {"deduplicated": True, "content_hash": content_hash}
        warnings.append("Analisi AI deduplicata: contenuto invariato, nessuna nuova chiamata.")
    elif allow_ai:
        try:
            enriched = await _llm_enrich(
                doc["id"], text, tax, title, user_preference=_user_llm_pref(user),
            )
            if enriched:
                ai_used = True
                model_name = enriched.get("model") or llm_status().get("model") or "llm"
                usage_meta = enriched.get("usage") or {}
                title = enriched.get("suggested_title") or title
                summary = enriched.get("summary") or summary
                summary_detailed = enriched.get("summary_detailed") or summary_detailed
                if enriched.get("keywords"):
                    keywords = list(dict.fromkeys(keywords + enriched["keywords"]))[:15]
                if enriched.get("education") and tax["macro_category"] == "education":
                    try:
                        edu_src = enriched["education"]
                        if hasattr(edu_src, "model_dump"):
                            edu_src = edu_src.model_dump()
                        education = EducationAnalysis(
                            **{**(education.model_dump() if education else {}), **edu_src}
                        )
                    except Exception:
                        pass
        except LLMNotConfigured as e:
            msg = str(e).lower()
            if "disponibile" in msg or "fallback" in msg or "nessun provider" in msg:
                warnings.append(
                    "Nessun provider AI disponibile (quota/errori/failover esaurito): usata analisi locale."
                )
            else:
                warnings.append("Provider AI non configurato: usata solo analisi locale.")
        except LLMRateLimitError:
            warnings.append("Rate limit provider AI: usata analisi locale.")
        except LLMTimeoutError:
            warnings.append("Timeout provider AI: usata analisi locale.")
        except LLMQuotaError:
            warnings.append("Quota provider AI esaurita: usata analisi locale.")
        except Exception:
            logger.warning("LLM enrich failed type=%s", "Exception")
            warnings.append("Arricchimento AI non riuscito: mantenuta analisi locale.")

    analysis = DocumentAnalysis(
        document_id=doc["id"],
        original_filename=filename,
        suggested_title=title,
        short_description=summary[:200],
        macro_category=tax["macro_category"],
        subcategory=tax["subcategory"],
        confidence=max(0.05, min(1.0, base_conf if not ai_used else min(0.95, base_conf + 0.1))),
        language=doc.get("detected_language") or doc.get("language"),
        summary=summary,
        summary_detailed=summary_detailed,
        keywords=keywords,
        entities=entity_items[:40],
        dates=list(entities_raw.get("dates") or [])[:20],
        locations=list(entities_raw.get("places") or [])[:20],
        monetary_values=[
            f"{a.get('amount')} {a.get('currency')}" if isinstance(a, dict) else str(a)
            for a in (entities_raw.get("amounts") or [])[:20]
        ],
        actions=actions,
        warnings=warnings,
        requires_review=requires_review,
        reasoning_summary=tax["reasoning_summary"],
        created_at=_now(),
        model=model_name,
        prompt_version=PROMPT_VERSION if ai_used else "none",
        analysis_version=int(doc.get("analysis_version") or prev.get("analysis_version") or 0) + (0 if ai_skipped_dedupe else 1),
        ai_used=ai_used,
        local_only=not ai_used,
    )
    analysis_dump = analysis.model_dump()
    analysis_dump["content_hash"] = content_hash
    analysis_dump["usage"] = usage_meta

    generic_actions: list[GenericAction] = []
    due = None
    from documents.intelligence.admin_extract import build_admin_analysis
    admin = build_admin_analysis(
        text,
        macro=tax["macro_category"],
        amounts=list(entities_raw.get("amounts") or []),
    )
    if admin:
        due = None
        if admin.due_date:
            due_dt, _, _ = _parse_italian_datetime(admin.due_date)
            due = due_dt.isoformat() if due_dt else None
        if admin.required_actions:
            for ra in admin.required_actions:
                generic_actions.append(
                    GenericAction(
                        action_type="generic_action",
                        title="Azione richiesta",
                        description=ra,
                        due_datetime=due,
                        amount=admin.amount,
                        priority=admin.priority,
                        urgency=admin.urgency,
                        requires_confirmation=True,
                    )
                )
        if admin.due_date or admin.amount:
            generic_actions.append(
                GenericAction(
                    action_type="create_reminder",
                    title="Promemoria scadenza" if admin.due_date else "Promemoria pagamento",
                    description=admin.simple_explanation,
                    due_datetime=due,
                    amount=admin.amount,
                    priority="high",
                    urgency="soon" if due else "upcoming",
                    requires_confirmation=True,
                )
            )
    elif tax["macro_category"] == "administrative":
        due_raw = _extract_labeled(text, ("Scadenza", "Entro il", "Data limite"))
        if due_raw:
            due_dt, _, _ = _parse_italian_datetime(due_raw)
            due = due_dt.isoformat() if due_dt else None
        generic_actions.append(
            GenericAction(
                action_type="generic_action",
                title="Azione richiesta dalla comunicazione",
                description=_extract_labeled(text, ("Azione richiesta", "Richiesta", "Oggetto")) or analysis.short_description,
                due_datetime=due,
                priority="high",
                urgency="soon" if due else "upcoming",
                requires_confirmation=True,
            )
        )
    for a in actions:
        if a in ("create_reminder", "needs_review"):
            generic_actions.append(
                GenericAction(
                    action_type=a,
                    title="Promemoria" if a == "create_reminder" else "Revisione richiesta",
                    description=analysis.short_description,
                    priority="medium",
                    urgency="upcoming" if a == "create_reminder" else "none",
                    requires_confirmation=True,
                )
            )

    edu_dump = education.model_dump() if education else None
    if edu_dump:
        from documents.intelligence.study_tools import enrich_education
        edu_dump = enrich_education(edu_dump, text)

    return {
        "analysis": analysis_dump,
        "event_candidates": [e.model_dump() for e in events],
        "education_analysis": edu_dump,
        "admin_analysis": admin.model_dump() if admin else None,
        "generic_actions": [g.model_dump() for g in generic_actions],
        "insights_snapshot": {
            "type_key": type_key,
            "type_label": insights.get("type_label"),
            "classification": insights.get("classification"),
        },
        "content_hash": content_hash,
        "ai_deduplicated": ai_skipped_dedupe,
    }


async def _llm_enrich(
    doc_id: str,
    text: str,
    tax: dict,
    title: str,
    user_preference: Optional[str] = None,
) -> Optional[dict]:
    """Structured LLM enrichment with chunking + Pydantic validation."""
    chunks = chunk_text(text)
    if not chunks:
        return None
    system = (
        "Sei il modulo Document Intelligence di ORA. Rispondi SOLO con JSON valido "
        "conforme allo schema richiesto. Non inventare fatti assenti dal testo. "
        "Non fornire consigli clinici. Distingui solo contenuto presente nel documento. "
        "Campi JSON: suggested_title, summary, summary_detailed, keywords (array di stringhe), "
        "education (opzionale: subject, topic, key_concepts, definitions, questions_for_review), notes."
    )
    payload = {
        "macro_category": tax["macro_category"],
        "subcategory": tax["subcategory"],
        "current_title": title,
        "chunk_index": 1,
        "chunk_total": len(chunks),
        "document_text": chunks[0],
    }
    if len(chunks) > 1:
        payload["additional_chunk_previews"] = [c[:400] for c in chunks[1:]]
    import json
    user = json.dumps(payload, ensure_ascii=False)
    parsed, meta = await chat_json(
        system=system,
        user=user,
        model_cls=LLMDocumentEnrichment,
        session_id=f"ora-doc-{doc_id}",
        user_preference=user_preference,
    )
    data = parsed.model_dump()
    data["model"] = meta.get("model") or meta.get("provider") or llm_status().get("model")
    data["usage"] = {**meta, "chunks_sent": len(chunks)}
    return data
