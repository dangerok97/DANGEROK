"""Document classifier — Iterazione 22.

Assigns a ``type_key`` + ``type_label`` + ``confidence`` (0..100) to a
document using a **multi-signal deterministic score** — no LLM.

Signals combined per type:
  1. Keyword hits (weighted, from :data:`schema_registry.classifier_keywords`)
  2. Label coverage — how many alias-labels of the schema fields appear
     in the text (proxy for "does the layout look like this type?")
  3. Filename hint (weak) — e.g. ``fattura_2026.pdf``, ``cv.pdf``
  4. Coherence check — if the type declares ``coherence_required``
     fields, they must at least map to a plausible label/value in the
     text; used to demote borderline scores into "generic".

Thresholds:
  * >= 70  → specific type
  * 50-69  → specific type ONLY if coherence_required fields are covered
  * <  50  → ``generic``
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from documents.schema_registry import DocumentSchema, all_schemas, get_schema


# ---------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------
@dataclass
class ClassificationResult:
    type_key: str
    type_label: str
    confidence: int
    matched_rules: List[str]
    scores: Dict[str, float]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "type_key": self.type_key,
            "type_label": self.type_label,
            "confidence": self.confidence,
            "matched_rules": self.matched_rules,
            "scores": self.scores,
        }


# ---------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------
_WORD_BOUND_CACHE: Dict[str, re.Pattern] = {}


def _kw_pattern(kw: str) -> re.Pattern:
    if kw in _WORD_BOUND_CACHE:
        return _WORD_BOUND_CACHE[kw]
    # Match keyword as a phrase with soft boundaries; case-insensitive.
    esc = re.escape(kw.strip())
    esc = esc.replace(r"\ ", r"\s+")
    pat = re.compile(rf"(?<![\wàèéìòù]){esc}(?![\wàèéìòù])", re.IGNORECASE)
    _WORD_BOUND_CACHE[kw] = pat
    return pat


def _keyword_score(text_low: str, schema: DocumentSchema) -> Tuple[float, List[str]]:
    """Sum of weights for every classifier keyword that appears in text."""
    total = 0.0
    matched: List[str] = []
    for kw, weight in schema.classifier_keywords.items():
        if _kw_pattern(kw).search(text_low):
            total += weight
            matched.append(f"kw:{kw}")
    return total, matched


def _label_coverage(text_low: str, schema: DocumentSchema) -> Tuple[float, List[str]]:
    """Count how many field-aliases show up (weight 0.5 each)."""
    seen: set[str] = set()
    matched: List[str] = []
    for f in schema.fields:
        for alias in (f.aliases or []):
            key = alias.lower().strip()
            if not key or key in seen:
                continue
            if _kw_pattern(alias).search(text_low):
                seen.add(key)
                matched.append(f"label:{alias}")
                break  # count each field at most once
    return len(seen) * 0.5, matched


def _filename_bonus(filename: str, schema: DocumentSchema) -> Tuple[float, List[str]]:
    """Small bonus if the filename contains the type key or label token."""
    fname = (filename or "").lower()
    if not fname:
        return 0.0, []
    tokens = {
        "ticket": ("biglietto", "ticket", "concerto", "evento"),
        "invoice": ("fattura", "invoice"),
        "receipt": ("scontrino", "ricevuta", "receipt"),
        "contract": ("contratto", "contract"),
        "bill": ("bolletta", "bill", "utenza"),
        "medical": ("referto", "esame", "medic"),
        "certificate": ("certificato", "attestato"),
        "id_card": ("carta_identita", "carta-identita", "id_card"),
        "passport": ("passaporto", "passport"),
        "cv": ("curriculum", "cv", "resume"),
        "bank_statement": ("estratto", "conto", "statement"),
        "tax_doc": ("dichiarazione", "730", "unico", "cud"),
    }.get(schema.type_key, ())
    for t in tokens:
        if t in fname:
            return 1.5, [f"filename:{t}"]
    return 0.0, []


def _coherence_ok(text_low: str, schema: DocumentSchema) -> bool:
    """A borderline score is upgraded to the specific type only if every
    ``coherence_required`` field has at least one alias/label present."""
    if not schema.coherence_required:
        return True
    for req_key in schema.coherence_required:
        fld = next((f for f in schema.fields if f.key == req_key), None)
        if fld is None:
            continue
        aliases = fld.aliases or [fld.label]
        if not any(_kw_pattern(a).search(text_low) for a in aliases):
            return False
    return True


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def classify(text: str, filename: str = "", mime_type: str = "") -> ClassificationResult:
    """Return the winning :class:`ClassificationResult` for a document."""
    text_low = (text or "").lower()
    scores: Dict[str, float] = {}
    matched_by_type: Dict[str, List[str]] = {}

    for type_key, schema in all_schemas().items():
        if type_key == "generic":
            continue
        s1, m1 = _keyword_score(text_low, schema)
        s2, m2 = _label_coverage(text_low, schema)
        s3, m3 = _filename_bonus(filename, schema)
        total = s1 + s2 + s3
        # Scale to 0..100. Empirical constant; big docs won't overshoot
        # because we clamp; small docs never get >70 without strong signal.
        scaled = min(100.0, round(total * 12.0, 2))
        scores[type_key] = scaled
        matched_by_type[type_key] = m1 + m2 + m3

    if not scores:
        return _generic_result(filename, mime_type)

    # Pick the best candidate.
    best_key = max(scores, key=lambda k: scores[k])
    best_score = int(round(scores[best_key]))
    schema = get_schema(best_key)
    assert schema is not None  # by construction

    # Threshold logic per spec.
    if best_score >= 70:
        return ClassificationResult(
            best_key, schema.type_label, best_score,
            matched_by_type.get(best_key, []), scores,
        )
    if 50 <= best_score < 70 and _coherence_ok(text_low, schema):
        return ClassificationResult(
            best_key, schema.type_label, best_score,
            matched_by_type.get(best_key, []) + ["coherence:ok"], scores,
        )
    return _generic_result(filename, mime_type, scores=scores)


def _generic_result(
    filename: str,
    mime_type: str,
    scores: Dict[str, float] | None = None,
) -> ClassificationResult:
    label = _mime_generic_label(filename, mime_type)
    return ClassificationResult(
        type_key="generic",
        type_label=label,
        confidence=0,
        matched_rules=["fallback:generic"],
        scores=scores or {},
    )


def _mime_generic_label(filename: str, mime_type: str) -> str:
    mt = (mime_type or "").lower()
    if mt == "application/pdf":
        return "Documento PDF"
    if mt.startswith("image/"):
        return "Immagine / scansione"
    if mt.startswith("text/"):
        return "Documento di testo"
    return "Documento generico"
