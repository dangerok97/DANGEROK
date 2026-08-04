"""Document field resolver — Iterazione 22.

Given the extracted entities + the resolved schema, pick the best value
for each ``SchemaField`` and attach a **confidence 0..100** score plus a
minimal ``source_snippet`` (limited to the surrounding line to avoid
exposing unrelated content).

Deterministic. No LLM. Fully schema-driven — adding a new document type
requires zero changes here: register a schema and it just works.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from documents.schema_registry import DocumentSchema, get_schema
from documents.person_detector import filter_persons, looks_like_person, looks_like_single_name


# ---------------------------------------------------------------------
# Config — thresholds are configurable via env
# ---------------------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


VISIBLE_THRESHOLD = _env_int("DOCUMENT_INSIGHTS_CONFIDENCE_THRESHOLD", 60)
HIDDEN_LOWER = _env_int("DOCUMENT_INSIGHTS_HIDDEN_LOWER_THRESHOLD", 40)


# ---------------------------------------------------------------------
# Public model
# ---------------------------------------------------------------------
@dataclass
class ResolvedField:
    field_key: str
    label: str
    value: str
    confidence: int
    source_snippet: str = ""
    source_page: Optional[int] = None
    resolver_rule: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "field_key": self.field_key,
            "label": self.label,
            "value": self.value,
            "confidence": self.confidence,
            "source_snippet": self.source_snippet,
            "source_page": self.source_page,
            "resolver_rule": self.resolver_rule,
        }


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
_ACCENT = "àèéìòùáíóúâêîôû"


def _iter_lines_with_offsets(text: str) -> List[Tuple[int, int, str]]:
    """Return [(start, end, line_text_lowered)] for each non-empty line."""
    out: List[Tuple[int, int, str]] = []
    pos = 0
    for ln in text.splitlines(keepends=True):
        low = ln.lower()
        out.append((pos, pos + len(ln), low))
        pos += len(ln)
    return out


def _find_label_positions(text_low: str, aliases: Iterable[str]) -> List[Tuple[int, int, str]]:
    """Return all label match positions in the text (case-insensitive)."""
    out: List[Tuple[int, int, str]] = []
    for a in aliases:
        pat = a.strip().lower()
        if not pat:
            continue
        # Word-boundary aware — supports multi-word labels ("data emissione")
        esc = re.escape(pat).replace(r"\ ", r"\s+")
        rx = re.compile(rf"(?<![\w{_ACCENT}]){esc}(?![\w{_ACCENT}])", re.IGNORECASE)
        for m in rx.finditer(text_low):
            out.append((m.start(), m.end(), pat))
    return out


def _line_at(offset: int, lines: List[Tuple[int, int, str]]) -> Optional[Tuple[int, int, str]]:
    for s, e, low in lines:
        if s <= offset < e:
            return (s, e, low)
    return None


def _snippet(text: str, start: int, end: int, radius: int = 60) -> str:
    a = max(0, start - radius)
    b = min(len(text), end + radius)
    snip = text[a:b].replace("\n", " ").replace("\r", " ")
    snip = re.sub(r"\s+", " ", snip).strip()
    if len(snip) > 160:
        snip = snip[:157] + "…"
    return snip


# Separator chars that may legitimately sit between a label and its value:
# ``:``, ``-``, ``–``, ``—``, ``·``, ``|``, ``.``, ``\t`` and whitespace.
_LABEL_SEP_STRIP = " \t:.\-\u2013\u2014·|"


def _strip_label_prefix(value: str, aliases: List[str]) -> str:
    """Iterazione 23 micro-fix.

    Rimuove dalla testa di ``value`` una eventuale label (alias del campo)
    seguita da separatori tipici (``:``, ``-``, ``–``, ``—``, ``|``, ``·``,
    ``.``, spazi/tab). Applicato SOLO ai campi label-aware di tipo
    ``text``/``person``/``place`` (per gli altri semantic types il valore
    non contiene mai la label, dato che l'estrazione avviene su entità
    specifiche o via regex con gruppo di cattura).

    Regole:
      * matching case-insensitive, boundary sui caratteri Unicode di parola
      * rimozione UNA sola volta (no ricorsione, evita ambiguità)
      * se la label NON è presente all'inizio → valore restituito invariato
      * preserva i caratteri accentati e le sequenze di più parole
        (es. ``Partita IVA``).
    """
    v = (value or "").strip()
    if not v or not aliases:
        return v
    low = v.lower()
    # Try longest aliases first — evita che "iva" mangi il prefisso di "partita iva".
    for alias in sorted({a.strip() for a in aliases if a and a.strip()},
                        key=len, reverse=True):
        a_low = alias.lower()
        if not low.startswith(a_low):
            continue
        end = len(a_low)
        if end >= len(v):
            # La stringa è ESATTAMENTE la label → non è un contenuto utile.
            return v
        # Richiede un separatore ESPLICITO fra label e valore
        # (``:`` ``-`` ``–`` ``—`` ``|`` ``·`` ``.``), eventualmente seguito
        # da altri caratteri di separazione/whitespace. Uno spazio da solo
        # NON basta: preserva espressioni come ``Fornitura elettrica`` dove
        # ``Fornitura`` combacia con la label ma è parte del contenuto.
        m = re.match(r"[ \t]*[:\-\u2013\u2014·|.]+[ \t]*", v[end:])
        if not m:
            continue
        stripped = v[end + m.end():].strip()
        return stripped or v
    return v


def _value_is_already_typed(value: str, entities: Dict[str, List[str]]) -> bool:
    """Detect values that were already classified by the deterministic
    pipeline with a stronger semantic type. Prevents a `text` field from
    absorbing a P.IVA/CF/phone/IBAN/order-ID/technical-ID that happened
    to sit in the tail of a label line."""
    if not value:
        return True
    v = value.strip()
    # Trim trailing punctuation to align with entity bucket normalisation.
    v_stripped = v.rstrip(" ,.;:!?")
    for bucket in ("tax_ids", "phones", "iban", "order_ids",
                   "technical_ids", "emails", "urls", "amounts"):
        for x in entities.get(bucket, []):
            if x == v or x == v_stripped or x in v or v in x:
                return True
    # Very-long pure-digit tails are almost never a text field.
    digits = re.sub(r"\D", "", v)
    if len(digits) >= 9 and re.fullmatch(r"[\d\s./\-()+]+", v):
        return True
    return False


# ---------------------------------------------------------------------
# Entity source pools (per semantic field type)
# ---------------------------------------------------------------------
def _pool_for(field_type: str, entities: Dict[str, List[str]]) -> List[str]:
    return {
        "date": entities.get("dates") or [],
        "time": entities.get("times") or [],
        "amount": entities.get("amounts") or [],
        "iban": entities.get("iban") or [],
        "tax_id": entities.get("tax_ids") or [],
        "phone": entities.get("phones") or [],
        "email": entities.get("emails") or [],
        "url": entities.get("urls") or [],
        "person": entities.get("persons") or [],
        "place": entities.get("places") or [],
        "number": (entities.get("order_ids") or []) + (entities.get("numbers") or []),
        "text": [],  # text fields require label-adjacent extraction
    }.get(field_type, [])


# ---------------------------------------------------------------------
# Candidate scoring
# ---------------------------------------------------------------------
def _score_candidate(
    value: str,
    positions_in_text: List[int],
    label_positions: List[Tuple[int, int, str]],
    context_labels_lower: List[str],
    lines: List[Tuple[int, int, str]],
    field_priority: int,
) -> Tuple[int, str, int, int]:
    """Return (confidence 0..100, reason, best_value_pos, best_label_pos)."""
    if not positions_in_text:
        return 0, "no-position", -1, -1

    best_conf = 0
    best_reason = "no-label"
    best_v_pos = positions_in_text[0]
    best_l_pos = -1

    for v_pos in positions_in_text:
        # Label proximity (same line or ≤ 40 chars before)
        line = _line_at(v_pos, lines)
        best_label_here = -1
        label_dist = 999
        for ls, le, _ in label_positions:
            if line and ls >= line[0] and ls < line[1] and le <= v_pos:
                d = v_pos - le
                if d < label_dist:
                    label_dist = d
                    best_label_here = ls
            elif 0 <= (v_pos - le) < 40:
                d = v_pos - le
                if d < label_dist:
                    label_dist = d
                    best_label_here = ls

        conf = 0
        reason = "no-label"
        if best_label_here >= 0:
            # Strong: same-line label immediately before
            if label_dist <= 3:
                conf = 92
                reason = "label-adjacent"
            elif label_dist <= 12:
                conf = 85
                reason = "label-near"
            else:
                conf = 72
                reason = "label-same-line"
        else:
            # No label at all — rely on context words within the line
            if line and any(cl in line[2] for cl in context_labels_lower):
                conf = 62
                reason = "context-line"
            else:
                # First plausible candidate in doc gets a low base score
                # (fine for `order_number` fallback, etc.)
                conf = 40
                reason = "positional-only"

        # Field-priority nudges — high-priority fields get +3 to break ties
        conf = min(100, conf + max(0, (field_priority - 50) // 20))

        if conf > best_conf:
            best_conf = conf
            best_reason = reason
            best_v_pos = v_pos
            best_l_pos = best_label_here

    return best_conf, best_reason, best_v_pos, best_l_pos


def _find_all_positions(text: str, value: str) -> List[int]:
    if not value:
        return []
    # case-sensitive first — exact match. Then fall back to case-insensitive.
    positions: List[int] = []
    start = 0
    v = value
    while True:
        i = text.find(v, start)
        if i < 0:
            break
        positions.append(i)
        start = i + max(1, len(v))
    if not positions:
        low_text = text.lower()
        low_v = value.lower()
        start = 0
        while True:
            i = low_text.find(low_v, start)
            if i < 0:
                break
            positions.append(i)
            start = i + max(1, len(low_v))
    return positions


def _extract_text_field(
    text: str,
    text_low: str,
    lines: List[Tuple[int, int, str]],
    label_positions: List[Tuple[int, int, str]],
    max_len: int = 80,
) -> Tuple[Optional[str], int, str, int]:
    """For `text` fields, extract the tail of the line following the label."""
    if not label_positions:
        return None, 0, "no-label", -1
    # Pick the earliest label occurrence.
    ls, le, _ = min(label_positions, key=lambda x: x[0])
    line = _line_at(ls, lines)
    if not line:
        return None, 0, "no-line", -1
    l_start, l_end, _ = line
    raw = text[le:l_end].strip(" \t:.-—–")
    raw = raw.rstrip("\n\r")
    if not raw:
        # Next line — but only if reasonably short
        nxt_idx = l_end
        if nxt_idx < len(text):
            nxt_line = _line_at(nxt_idx, lines)
            if nxt_line:
                raw = text[nxt_line[0]:nxt_line[1]].strip()
    if not raw:
        return None, 0, "empty-after-label", ls
    if len(raw) > max_len:
        raw = raw[:max_len].rstrip() + "…"
    return raw, 82, "label-tail", ls


# ---------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------
def resolve_fields(
    text: str,
    entities: Dict[str, List[str]],
    type_key: str,
) -> Tuple[List[ResolvedField], List[ResolvedField], Dict[str, List[int]]]:
    """Resolve the schema's fields.

    Returns ``(visible, hidden, used_positions)``:
      * ``visible`` — confidence ≥ VISIBLE_THRESHOLD (default 60)
      * ``hidden``  — HIDDEN_LOWER ≤ confidence < VISIBLE_THRESHOLD
      * ``used_positions`` — {entity_pool_key: [char_positions]} for entities
        that got pulled into a resolved field (used to hide them from the
        generic buckets in the payload builder).
    """
    schema: Optional[DocumentSchema] = get_schema(type_key)
    if schema is None or not schema.fields:
        return [], [], {}

    text_low = text.lower()
    lines = _iter_lines_with_offsets(text)

    visible: List[ResolvedField] = []
    hidden: List[ResolvedField] = []
    used_value_by_pool: Dict[str, set[str]] = {}

    for f in schema.fields:
        label_positions = _find_label_positions(text_low, [f.label, *f.aliases])
        context_labels_lower = [c.lower() for c in (f.context_labels or [])]

        if f.type == "text":
            val, conf, reason, l_pos = _extract_text_field(
                text, text_low, lines, label_positions,
            )
            if val is None:
                continue
            # Iter23 fix: strip residual label prefix if the picker
            # captured "Label: value" (e.g. next-line fallback).
            val = _strip_label_prefix(val, [f.label, *f.aliases])
            # Skip tail values that were already classified with a stronger
            # semantic type — e.g. "P.IVA emittente: 12345678901" would
            # otherwise pull the digits into a text "Emittente" field.
            if _value_is_already_typed(val, entities):
                continue
            snippet = _snippet(text, l_pos if l_pos >= 0 else 0,
                               (l_pos + len(val)) if l_pos >= 0 else len(val))
            rf = ResolvedField(
                field_key=f.key, label=f.label, value=val,
                confidence=conf, source_snippet=snippet,
                source_page=None, resolver_rule=reason,
            )
            _bucketise(rf, visible, hidden)
            continue

        candidates = _pool_for(f.type, entities)

        # For `person` fields, filter with the person detector.
        if f.type == "person":
            candidates = filter_persons(candidates)

        # Iter23 fix: for label-aware semantic types (place/person) the
        # entity pool may contain values with the label baked in (e.g.
        # entities.places on line "Luogo: Ippodromo Capannelle"). Strip
        # the label prefix so the resolved value is clean.
        if f.type in ("place", "person") and candidates:
            candidates = [
                _strip_label_prefix(c, [f.label, *f.aliases]) for c in candidates
            ]
            # drop empties produced by the strip
            candidates = [c for c in candidates if c]

        # Try to score candidates first; if none reaches HIDDEN_LOWER (or
        # the pool is empty), for person fields we fall back to label-tail
        # extraction ("Cognome: ROSSI", "Titolare: Mario Rossi").
        best_from_pool: Optional[ResolvedField] = None
        if candidates:
            best_conf = -1
            for cand in candidates:
                positions = _find_all_positions(text, cand)
                if not positions:
                    continue
                conf, reason, v_pos, l_pos = _score_candidate(
                    cand, positions, label_positions,
                    context_labels_lower, lines, f.priority,
                )
                if conf > best_conf:
                    best_conf = conf
                    snip = _snippet(
                        text,
                        l_pos if l_pos >= 0 else v_pos,
                        v_pos + len(cand),
                    )
                    best_from_pool = ResolvedField(
                        field_key=f.key, label=f.label, value=cand,
                        confidence=conf, source_snippet=snip,
                        source_page=None, resolver_rule=reason,
                    )

        if f.type == "person" and (best_from_pool is None or best_from_pool.confidence < VISIBLE_THRESHOLD):
            val, conf, reason, l_pos = _extract_text_field(
                text, text_low, lines, label_positions,
            )
            # Iter23 fix: even the label-tail path may include the label
            # (rare, but happens with next-line fallback).
            if val:
                val = _strip_label_prefix(val, [f.label, *f.aliases])
            validator = (
                looks_like_single_name
                if f.key in ("name", "surname", "given_name", "family_name")
                else looks_like_person
            )
            if val and validator(val):
                snippet = _snippet(text, l_pos if l_pos >= 0 else 0,
                                   (l_pos + len(val)) if l_pos >= 0 else len(val))
                rf = ResolvedField(
                    field_key=f.key, label=f.label, value=val,
                    confidence=conf, source_snippet=snippet,
                    source_page=None, resolver_rule=f"person-label-tail:{reason}",
                )
                # Prefer the label-tail result over any weak pool candidate.
                if best_from_pool is None or rf.confidence > best_from_pool.confidence:
                    used = used_value_by_pool.setdefault(f.type, set())
                    if rf.value in used:
                        continue
                    used.add(rf.value)
                    _bucketise(rf, visible, hidden)
                    continue
            # No good text-tail candidate — drop the weak pool value.
            if best_from_pool is None or best_from_pool.confidence < VISIBLE_THRESHOLD:
                continue

        best = best_from_pool
        if best is None or best.confidence < HIDDEN_LOWER:
            continue

        # Prevent the same value being used by two different fields
        # (highest-priority-first ordering ensures the strongest field wins).
        pool_key = f.type
        used = used_value_by_pool.setdefault(pool_key, set())
        if best.value in used:
            continue
        used.add(best.value)

        _bucketise(best, visible, hidden)

    # Sort visible by schema's info_order (fallback to priority).
    order_index = {k: i for i, k in enumerate(schema.info_order or [])}
    visible.sort(key=lambda rf: order_index.get(rf.field_key, 10_000 - _priority_for(schema, rf.field_key)))

    used_positions: Dict[str, List[int]] = {
        pool: sorted({idx for v in vals for idx in _find_all_positions(text, v)})
        for pool, vals in used_value_by_pool.items()
    }
    return visible, hidden, used_positions


def _bucketise(rf: ResolvedField, visible: List[ResolvedField], hidden: List[ResolvedField]) -> None:
    if rf.confidence >= VISIBLE_THRESHOLD:
        visible.append(rf)
    elif rf.confidence >= HIDDEN_LOWER:
        hidden.append(rf)
    # Else: drop entirely (too weak).


def _priority_for(schema: DocumentSchema, field_key: str) -> int:
    for f in schema.fields:
        if f.key == field_key:
            return f.priority
    return 0


# Public re-exports used by the payload builder
__all__ = [
    "ResolvedField",
    "resolve_fields",
    "VISIBLE_THRESHOLD",
    "HIDDEN_LOWER",
]
