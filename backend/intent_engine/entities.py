"""Entity extraction from free text — deterministic, language-aware (IT)."""
from __future__ import annotations

import re
from typing import Optional

from intent_engine.knowledge import SUBJECT_PATTERNS
from intent_engine.models import IntentEntities

_AMOUNT_RE = re.compile(
    r"(?:€\s*|euro\s*|eur\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:€|euro|eur)?",
    re.I,
)
_DATE_RE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
    r"(?:luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica)|"
    r"(?:domani|dopodomani|oggi)|"
    r"(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)"
    r"(?:\s+\d{1,2})?)\b",
    re.I,
)
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
_PLACE_RE = re.compile(
    r"\b(?:a|ad|in|da|per)\s+([A-ZÀÈÉÌÒÙ][\wàèéìòù'\-]{2,30})"
)
_PERSON_RE = re.compile(
    r"\b(?:con|dal|dalla|dal dott\.?|dott\.?|dr\.?|prof\.?)\s+([A-ZÀÈÉÌÒÙ][\wàèéìòù'\-]{2,30})",
)
_UNI_RE = re.compile(
    r"\b(universit[aà]\s+[\wàèéìòù'\- ]{2,40}|uni\s+[\wàèéìòù'\-]{2,30})\b",
    re.I,
)
_DOC_RE = re.compile(
    r"\b([\w\-]+\.(?:pdf|docx?|pptx?|jpg|png))\b",
    re.I,
)


def _title_case_it(s: str) -> str:
    s = (s or "").strip(" .,;:!?'\"")
    if not s:
        return s
    # Keep short prepositions lower when multi-word
    parts = re.split(r"\s+", s)
    out = []
    for i, p in enumerate(parts):
        if i > 0 and p.lower() in ("di", "de", "del", "della", "e", "ed"):
            out.append(p.lower())
        else:
            out.append(p[:1].upper() + p[1:].lower() if p else p)
    return " ".join(out)


def extract_subject(text: str) -> Optional[str]:
    raw = text or ""
    for pat in SUBJECT_PATTERNS:
        m = re.search(pat, raw, flags=re.I)
        if m:
            subj = m.group(1)
            # Filter noise words
            if subj.lower() in ("esame", "esami", "studio", "studiare", "devo", "l"):
                continue
            return _title_case_it(subj)
    # "l'esame di psicologia" style with apostrophe already in patterns
    m = re.search(
        r"esame\s+di\s+([a-zàèéìòù][\wàèéìòù'\-]{2,40})",
        raw,
        flags=re.I,
    )
    if m:
        return _title_case_it(m.group(1))
    return None


def extract_entities(text: str, *, intent: Optional[str] = None) -> IntentEntities:
    t = text or ""
    ent = IntentEntities()

    subj = extract_subject(t)
    if subj:
        ent.subject = subj
        if intent == "study" or (intent is None and re.search(r"esame|stud", t, re.I)):
            ent.exam = subj
            ent.goal = "Preparare esame"

    am = _AMOUNT_RE.search(t)
    if am and re.search(r"€|euro|eur|pagare|fattura|bolletta|bonifico", t, re.I):
        ent.amount = am.group(0).strip()

    dm = _DATE_RE.search(t)
    if dm:
        ent.date = dm.group(1)
        if intent in ("study", "payment", "administrative", None):
            ent.deadline = dm.group(1)

    tm = _TIME_RE.search(t)
    if tm:
        ent.time = f"{tm.group(1)}:{tm.group(2)}"

    pm = _PERSON_RE.search(t)
    if pm:
        ent.person = _title_case_it(pm.group(1))

    pl = _PLACE_RE.search(t)
    if pl:
        cand = pl.group(1)
        if cand.lower() not in ("casa", "lavoro", "studio", "esame", "visita"):
            ent.place = _title_case_it(cand)

    um = _UNI_RE.search(t)
    if um:
        ent.university = um.group(1).strip()

    doc = _DOC_RE.search(t)
    if doc:
        ent.document = doc.group(1)

    if intent == "travel" or re.search(r"vacanza|viaggio|volare", t, re.I):
        dest = re.search(
            r"(?:a|in|per)\s+([A-ZÀÈÉÌÒÙ][\wàèéìòù'\-]{2,40}(?:\s+[A-ZÀÈÉÌÒÙ][\wàèéìòù'\-]{2,30})?)",
            t,
        )
        if dest:
            ent.travel = _title_case_it(dest.group(1))
            ent.place = ent.place or ent.travel
        # Multi-word destinations like "Vibo Marina" without preposition
        if not ent.travel:
            m_vac = re.search(
                r"(?:vacanza|viaggio)\s+(?:a\s+|in\s+|per\s+)?([A-ZÀÈÉÌÒÙ][\wàèéìòù'\- ]{2,40})",
                t,
            )
            if m_vac:
                cand = m_vac.group(1).strip()
                # Stop at date words
                cand = re.split(
                    r"\s+(?:dal|da|il|dal\s+\d)", cand, maxsplit=1, flags=re.I,
                )[0].strip()
                if cand and cand.lower() not in ("dal", "da"):
                    ent.travel = _title_case_it(cand)
                    ent.place = ent.place or ent.travel
        try:
            from action_engine.travel.period_parser import extract_period_from_text
            period = extract_period_from_text(t)
            if period.get("ok"):
                ent.start_date = period.get("start_date")
                ent.end_date = period.get("end_date")
                ent.period = period.get("label")
                ent.date = ent.date or period.get("start_date")
        except Exception:
            pass

    if intent == "event" or re.search(r"concerto|biglietto|spettacolo", t, re.I):
        em = re.search(
            r"(?:concerto|spettacolo|evento)\s+(?:di\s+|dei\s+|dei\s+)?(.+?)(?:\s+a\s+|\s+il\s+|$)",
            t,
            re.I,
        )
        if em:
            ent.event = em.group(1).strip()[:80]

    return ent
