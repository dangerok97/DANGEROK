"""Deterministic Italian entity extraction — primary path (no LLM)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional

from semantic_engine.dates import extract_dates_from_text, format_it
from semantic_engine.models import CONFIDENCE_HIGH, EntityValue, DEFAULT_TZ

_TRANSPORT = {
    r"\bin\s+auto\b|\bin\s+macchina\b|\bguidando\b": ("car", "Auto"),
    r"\bin\s+treno\b|\bcol\s+treno\b": ("train", "Treno"),
    r"\bin\s+aereo\b|\bvolare\b|\bvolo\b": ("plane", "Aereo"),
    r"\bin\s+bus\b|\bin\s+pullman\b": ("bus", "Bus"),
}

_AMOUNT = re.compile(
    r"(?:€\s*|euro\s*)?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:€|euro|eur)?",
    re.I,
)


def _ev(
    raw: Any,
    normalized: Any,
    confidence: float,
    *,
    status: str = "known",
    source: str = "deterministic",
    timezone: Optional[str] = None,
    ambiguity: Optional[Dict[str, Any]] = None,
    label: Optional[str] = None,
) -> EntityValue:
    if status == "known" and confidence < 0.60:
        status = "low_confidence"
    return EntityValue(
        raw=raw,
        normalized=normalized,
        confidence=confidence,
        status=status,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        timezone=timezone,
        ambiguity=ambiguity,
        label=label,
    )


def _title(s: str) -> str:
    parts = re.split(r"\s+", (s or "").strip(" .,;:!?'\""))
    out = []
    for i, p in enumerate(parts):
        if i > 0 and p.lower() in ("di", "de", "del", "della", "e", "ed", "a", "in"):
            out.append(p.lower())
        else:
            out.append(p[:1].upper() + p[1:] if p else p)
    return " ".join(out)


def extract_destination(text: str) -> Optional[EntityValue]:
    t = text or ""
    # vado a / parto per / vacanza a / in
    patterns = [
        r"(?:vado|andiamo|parto|partiamo|volo|viaggio)\s+(?:a|in|per)\s+"
        r"([A-ZÀÈÉÌÒÙ][\wàèéìòù'\-]+(?:\s+[A-ZÀÈÉÌÒÙ][\wàèéìòù'\-]+)?)",
        r"(?:a|in)\s+([A-ZÀÈÉÌÒÙ][\wàèéìòù'\-]+(?:\s+[A-ZÀÈÉÌÒÙ][\wàèéìòù'\-]+)?)"
        r"(?:\s+in\s+(?:auto|treno|aereo|macchina))?",
        r"(?:vacanza|viaggio)\s+(?:a|in|per)\s+"
        r"([A-ZÀÈÉÌÒÙ][\wàèéìòù'\- ]{2,40})",
    ]
    stop = {
        "casa", "lavoro", "auto", "treno", "aereo", "macchina", "due", "tre",
        "settimane", "giorni", "mesi", "agosto", "settembre", "luglio",
    }
    for pat in patterns:
        m = re.search(pat, t)
        if not m:
            continue
        cand = m.group(1).strip()
        cand = re.split(r"\s+(?:dal|da|il|in\s+auto|in\s+treno)", cand, maxsplit=1, flags=re.I)[0].strip()
        if not cand or cand.lower() in stop:
            continue
        # reject month-only
        if cand.lower() in stop:
            continue
        return _ev(cand, _title(cand), 0.92, label=_title(cand))
    return None


def extract_transport(text: str) -> Optional[EntityValue]:
    t = (text or "").lower()
    for pat, (code, label) in _TRANSPORT.items():
        if re.search(pat, t):
            return _ev(label, code, 0.95, label=label)
    return None


def extract_subject(text: str) -> Optional[EntityValue]:
    t = text or ""
    m = re.search(
        r"(?:esame|esame\s+di|preparare|studio)\s+(?:di\s+|l['']?)?"
        r"([A-Za-zÀ-ù][\wàèéìòù'\-]{2,40})",
        t,
        re.I,
    )
    if m:
        subj = m.group(1)
        if subj.lower() not in ("esame", "esami", "studio", "devo", "per"):
            return _ev(subj, _title(subj), 0.93, label=_title(subj))
    # "Psicologia il 18 settembre"
    m2 = re.search(
        r"\b(psicologia|matematica|fisica|storia|diritto|economia|biologia|chimica|"
        r"informatica|filosofia|sociologia|pedagogia|anatomia)\b",
        t,
        re.I,
    )
    if m2 and re.search(r"esame|studio|prepar", t, re.I):
        return _ev(m2.group(1), _title(m2.group(1)), 0.9, label=_title(m2.group(1)))
    return None


def extract_medical(text: str) -> Dict[str, EntityValue]:
    out: Dict[str, EntityValue] = {}
    t = text or ""
    tl = t.lower()
    if "dentista" in tl:
        out["appointment_type"] = _ev("dentista", "dentista", 0.96, label="Dentista")
    elif "visita" in tl:
        m = re.search(r"visita\s+(\w+)", tl)
        if m:
            out["appointment_type"] = _ev(m.group(0), m.group(1), 0.85, label=_title(m.group(1)))
    return out


def extract_payment(text: str) -> Dict[str, EntityValue]:
    out: Dict[str, EntityValue] = {}
    t = text or ""
    tl = t.lower()
    # Word-boundary payees — avoid 'tim' matching inside 'settimane'
    for name in ("enel", "acea", "vodafone", "windtre", "sky", "netflix", "tim"):
        if re.search(rf"\b{re.escape(name)}\b", tl):
            out["payee"] = _ev(
                name,
                name.upper() if name == "enel" else _title(name),
                0.94,
                label=name.upper() if name == "enel" else _title(name),
            )
            break
    if "bolletta" in tl or "fattura" in tl or "pagare" in tl:
        am = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|euro|eur)\b", t, re.I)
        if not am:
            am = re.search(r"(?:€)\s*(\d+(?:[.,]\d{1,2})?)", t)
        if am:
            raw = am.group(0).strip()
            num = am.group(1).replace(".", "").replace(",", ".") if "," in am.group(1) and "." not in am.group(1) else am.group(1).replace(",", ".")
            # Italian: 87 euro — simple int/float
            try:
                val = float(am.group(1).replace(",", "."))
                out["amount"] = _ev(raw, val, 0.93, label=f"€ {val:.2f}")
            except ValueError:
                out["amount"] = _ev(raw, raw, 0.8, label=raw)
    return out


def extract_lodging_hint(text: str) -> Optional[EntityValue]:
    tl = (text or "").lower()
    if re.search(r"\b(hotel|airbnb|b&b|alloggio|prenotato)\b", tl):
        if "prenotato" in tl or "già" in tl:
            return _ev("già prenotato", "booked", 0.9, label="Già prenotato")
        return _ev("alloggio", "need", 0.75, label="Alloggio da definire")
    return None


def _infer_intent_hint(text: str, intent: Optional[str]) -> Optional[str]:
    """Prefer explicit payment/medical/study over travel when cues are strong."""
    if intent:
        return intent
    tl = (text or "").lower()
    if re.search(r"\b(bolletta|fattura|pagare|pagamento)\b", tl) or re.search(
        r"\b(enel|acea|vodafone|windtre)\b", tl
    ):
        return "payment"
    if re.search(r"\b(dentista|medico|visita|ospedale|ambulatorio)\b", tl):
        return "medical"
    if re.search(r"\b(esame|studiare|universit)\b", tl):
        return "study"
    if re.search(r"\b(parto|partiamo|vacanza|viaggio|vado\s+a)\b", tl):
        return "travel"
    return None


def deterministic_extract(
    text: str,
    *,
    intent: Optional[str] = None,
    timezone: str = DEFAULT_TZ,
    now: Optional[datetime] = None,
) -> Dict[str, EntityValue]:
    """Extract entities from Italian free text. Never invent return date from departure-only."""
    entities: Dict[str, EntityValue] = {}
    t = text or ""
    intent = _infer_intent_hint(t, (intent or "").lower() or None)

    dates = extract_dates_from_text(t, tz_name=timezone, now=now)
    dep = dates.get("departure_date")
    ret = dates.get("return_date")
    ambiguous = bool(dates.get("ambiguous"))
    amb = dates.get("ambiguity")

    if dep:
        status = "ambiguous" if ambiguous and not ret else "known"
        conf = 0.45 if status == "ambiguous" else float(
            (dates.get("range") or dates.get("single") or {}).get("confidence") or 0.9
        )
        label = None
        try:
            from datetime import date as date_cls
            label = format_it(date_cls.fromisoformat(str(dep)[:10]))
        except Exception:
            label = str(dep)
        entities["departure_date"] = _ev(
            (dates.get("range") or dates.get("single") or {}).get("raw") or dep,
            dep,
            conf,
            status=status,
            timezone=timezone,
            ambiguity=amb if status == "ambiguous" else None,
            label=label,
        )
        entities["start_date"] = entities["departure_date"]

    if ret:
        try:
            from datetime import date as date_cls
            label_r = format_it(date_cls.fromisoformat(str(ret)[:10]))
        except Exception:
            label_r = str(ret)
        entities["return_date"] = _ev(
            (dates.get("range") or {}).get("raw") or ret,
            ret,
            float((dates.get("range") or {}).get("confidence") or 0.95),
            timezone=timezone,
            label=label_r,
        )
        entities["end_date"] = entities["return_date"]

    # Full period only when BOTH known
    if dep and ret:
        entities["period"] = _ev(
            (dates.get("range") or {}).get("raw") or f"{dep} – {ret}",
            {"start_date": dep, "end_date": ret},
            0.95,
            timezone=timezone,
            label=(dates.get("range") or {}).get("label") or f"{dep} – {ret}",
        )

    if dates.get("time"):
        tm = dates["time"]
        entities["time"] = _ev(
            tm.get("raw"),
            tm.get("normalized") or f"{tm['hour']:02d}:{tm['minute']:02d}",
            float(tm.get("confidence") or 0.9),
            label=tm.get("label"),
        )
        entities["appointment_time"] = entities["time"]

    # Domain-scoped extraction — avoid cross-domain pollution
    if intent in ("travel", "vacation") or (
        intent is None and re.search(r"parto|vacanza|viaggio|vado\s+a|andiamo", t, re.I)
    ):
        dest = extract_destination(t)
        if dest:
            entities["destination"] = dest
            entities["travel"] = dest
            entities["place"] = dest
        tr = extract_transport(t)
        if tr:
            entities["transport"] = tr
        lod = extract_lodging_hint(t)
        if lod:
            entities["lodging"] = lod

    if intent in ("study", "exam_preparation") or (
        intent is None and re.search(r"esame|stud", t, re.I)
    ):
        subj = extract_subject(t)
        if subj:
            entities["subject"] = subj
            entities["exam"] = subj
        if dep and (intent in ("study", "exam_preparation") or re.search(r"esame", t, re.I)):
            if "exam_date" not in entities and not re.search(r"parto|vacanza|viaggio", t, re.I):
                entities["exam_date"] = entities.get("departure_date") or _ev(dep, dep, 0.9, timezone=timezone)
                if intent == "study" or (
                    re.search(r"esame", t, re.I) and not re.search(r"parto|vacanza", t, re.I)
                ):
                    entities.pop("departure_date", None)
                    entities.pop("start_date", None)
                    entities.pop("period", None)

    if intent == "medical" or (intent is None and re.search(r"dentista|visita|medico|ospedale", t, re.I)):
        entities.update(extract_medical(t))
        if "appointment_type" in entities and dep and "appointment_date" not in entities:
            if not re.search(r"parto|vacanza|esame", t, re.I):
                entities["appointment_date"] = entities.get("departure_date") or _ev(
                    dep, dep, 0.9, timezone=timezone
                )
                if intent == "medical" or "dentista" in t.lower():
                    entities.pop("departure_date", None)
                    entities.pop("start_date", None)

    if intent == "payment" or (
        intent is None and re.search(r"bolletta|pagare|fattura", t, re.I)
    ):
        entities.update(extract_payment(t))
        # Payment due date from relative/weekday — not travel departure
        if dep and "due_date" not in entities:
            entities["due_date"] = _ev(dep, dep, 0.9, timezone=timezone)
            entities.pop("departure_date", None)
            entities.pop("start_date", None)
            entities.pop("destination", None)
            entities.pop("travel", None)
            entities.pop("place", None)

    # Goal update phrases — mark as goal entity touch
    if re.search(r"\b(aggiorna|modifica|sposta|cambia)\b.+\b(goal|obiettivo|esame|viaggio)\b", t, re.I):
        entities["goal_update"] = _ev(t[:80], True, 0.85, label="Aggiornamento obiettivo")

    return entities
