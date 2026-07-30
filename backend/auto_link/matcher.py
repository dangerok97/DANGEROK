"""
Matching strategies for the Auto-Link Engine.

Each strategy is a pure function with the same signature:

    strategy(decision, node, knowledge, graph_ctx, decision_text) -> List[MatchSignal]

Strategies are independent, testable, and swappable. They never mutate their
inputs and never read/write MongoDB. All I/O happens in the repository.

Sensitive knowledge values (`sensitivity in {sensitive, highly_sensitive}`)
NEVER appear inside a MatchSignal.description; the tag is enough to explain
what fired without leaking data.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Set

from .types import (
    CATEGORY_TYPE_COMPAT,
    MatchSignal,
    VERIFIABLE_TAGS,
)


# ------------------------------------------------------------------
# text helpers
# ------------------------------------------------------------------
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return _NON_ALNUM.sub(" ", s.lower()).strip()


def tokenize(s: Optional[str]) -> Set[str]:
    return set(x for x in normalize_text(s).split() if len(x) > 1)


def decision_text(decision: Dict[str, Any]) -> str:
    parts = [decision.get("title") or "", decision.get("description") or ""]
    md = decision.get("metadata") or {}
    for v in md.values():
        if isinstance(v, str):
            parts.append(v)
    return normalize_text(" ".join(parts))


def _prop_value(knowledge: Optional[Dict[str, Any]], key: str) -> Any:
    """Read the primitive value from a possibly-enveloped knowledge property."""
    if not knowledge:
        return None
    props = knowledge.get("properties") or {}
    entry = props.get(key)
    if entry is None:
        return None
    if isinstance(entry, dict) and "value" in entry and "value_type" in entry:
        return entry.get("value")
    return entry


def _prop_sensitivity(knowledge: Optional[Dict[str, Any]], key: str) -> str:
    if not knowledge:
        return "personal"
    props = knowledge.get("properties") or {}
    entry = props.get(key)
    if isinstance(entry, dict) and "sensitivity" in entry:
        return entry.get("sensitivity") or "personal"
    return "personal"


def _redact_display(value: Any, sensitivity: str) -> str:
    """Return a safe string for descriptions. Sensitive/highly-sensitive
    values are replaced by `<redacted>`. Non-sensitive scalars are stringified."""
    if sensitivity in ("sensitive", "highly_sensitive"):
        return "<redacted>"
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)[:64]
    return "<complex>"


# ------------------------------------------------------------------
# strategies
# ------------------------------------------------------------------
def s_explicit_link(decision: Dict[str, Any], node: Dict[str, Any], **_kw) -> List[MatchSignal]:
    """User already declared the link."""
    node_id = node["id"]
    out: List[MatchSignal] = []
    if node_id in (decision.get("node_ids") or []):
        out.append(MatchSignal(
            tag="EXPLICIT_LINK",
            description="Collegamento già dichiarato dall'utente",
            contribution=1.0,
            verifiable=True,
        ))
    if node_id in (decision.get("linked_to") or []):
        out.append(MatchSignal(
            tag="EXPLICIT_LINKED_TO",
            description="Decision collegata a questo elemento tramite linked_to",
            contribution=0.9,
            verifiable=True,
        ))
    return out


def s_verifiable_identifiers(decision: Dict[str, Any], node: Dict[str, Any], knowledge: Optional[Dict[str, Any]] = None, **_kw) -> List[MatchSignal]:
    """Cross-check decision.metadata with node knowledge for unique identifiers.
    A match here is enough to auto-accept."""
    signals: List[MatchSignal] = []
    md = decision.get("metadata") or {}
    if not isinstance(md, dict):
        return signals

    def _match_id(md_key: str, know_key: str, tag: str, human: str) -> None:
        md_val = md.get(md_key)
        if md_val is None:
            return
        node_val = _prop_value(knowledge, know_key)
        if node_val is None:
            return
        if str(md_val).strip().lower() == str(node_val).strip().lower():
            signals.append(MatchSignal(tag=tag, description=human, contribution=1.0, verifiable=True))

    _match_id("plate", "plate", "VERIFIABLE_PLATE", "Targa corrispondente")
    _match_id("contract_id", "contract_id", "VERIFIABLE_CONTRACT", "Contratto corrispondente")
    _match_id("document_id", "document_id", "VERIFIABLE_DOCUMENT", "Documento corrispondente")
    _match_id("iban", "iban_masked", "VERIFIABLE_IBAN", "IBAN corrispondente")

    # Provider is semi-verifiable (not globally unique but strong).
    md_provider = md.get("provider")
    know_provider = _prop_value(knowledge, "provider")
    if md_provider and know_provider and str(md_provider).strip().lower() == str(know_provider).strip().lower():
        signals.append(MatchSignal(
            tag="VERIFIABLE_PROVIDER",
            description=f"Fornitore corrispondente: {str(know_provider)[:32]}",
            contribution=0.55,
            verifiable=False,
        ))
    return signals


def s_category_type(decision: Dict[str, Any], node: Dict[str, Any], **_kw) -> List[MatchSignal]:
    """Structural compatibility: decision.category ↔ node.type."""
    cat = decision.get("category") or "generic"
    compat = CATEGORY_TYPE_COMPAT.get(cat, frozenset())
    if node.get("type") in compat:
        return [MatchSignal(
            tag="CATEGORY_TYPE",
            description=f"Categoria '{cat}' compatibile con tipo '{node['type']}'",
            contribution=0.30,
        )]
    return []


# Which knowledge keys, when their value appears in the decision text, are
# semantically strong. Values are per-key contribution weights.
_KNOWLEDGE_TEXT_KEYS = {
    "provider":    (0.45, "KNOWLEDGE_PROVIDER", "Fornitore compare nella descrizione"),
    "plate":       (0.55, "KNOWLEDGE_PLATE",    "Targa citata nella Decision"),
    "address":     (0.45, "KNOWLEDGE_ADDRESS",  "Indirizzo citato nella Decision"),
    "name":        (0.40, "KNOWLEDGE_NAME",     "Nome persona citato nella Decision"),
    "institution": (0.40, "KNOWLEDGE_INSTITUTION", "Ateneo citato nella Decision"),
    "brand":       (0.25, "KNOWLEDGE_KEY_MATCH", "Marca citata nella Decision"),
    "model":       (0.25, "KNOWLEDGE_KEY_MATCH", "Modello citato nella Decision"),
    "vendor":      (0.30, "KNOWLEDGE_KEY_MATCH", "Venditore citato nella Decision"),
    "bank":        (0.35, "KNOWLEDGE_KEY_MATCH", "Banca citata nella Decision"),
    "company":     (0.30, "KNOWLEDGE_KEY_MATCH", "Azienda citata nella Decision"),
    "program":     (0.30, "KNOWLEDGE_KEY_MATCH", "Corso di laurea citato nella Decision"),
    "doc_type":    (0.20, "KNOWLEDGE_KEY_MATCH", "Tipo documento citato nella Decision"),
}


def s_knowledge_text_match(decision: Dict[str, Any], node: Dict[str, Any], knowledge: Optional[Dict[str, Any]] = None, decision_text: str = "", **_kw) -> List[MatchSignal]:
    if not knowledge:
        return []
    signals: List[MatchSignal] = []
    props = knowledge.get("properties") or {}
    for key, (weight, tag, human) in _KNOWLEDGE_TEXT_KEYS.items():
        if key not in props:
            continue
        val = _prop_value(knowledge, key)
        if not val:
            continue
        # Only scalar strings are checked here.
        if not isinstance(val, (str, int, float)):
            continue
        sensitivity = _prop_sensitivity(knowledge, key)
        normalized = normalize_text(str(val))
        if len(normalized) < 3:
            continue
        if normalized in decision_text:
            display = _redact_display(val, sensitivity)
            desc = human if display in ("<redacted>", "") else f"{human}: {display}"
            signals.append(MatchSignal(
                tag=tag,
                description=desc,
                contribution=weight,
            ))
    return signals


def s_node_label(decision: Dict[str, Any], node: Dict[str, Any], decision_text: str = "", **_kw) -> List[MatchSignal]:
    label = node.get("label") or ""
    n = normalize_text(label)
    if len(n) >= 3 and n in decision_text:
        return [MatchSignal(
            tag="NODE_LABEL",
            description=f"Il nome del nodo '{label[:40]}' compare nella Decision",
            contribution=0.35,
        )]
    return []


# ------------------------------------------------------------------
# Keyword fallback — weakest, never leads to auto-accept alone.
# ------------------------------------------------------------------
_CATEGORY_KEYWORDS: Dict[str, Set[str]] = {
    "bill":          {"bolletta", "fattura", "pagamento", "scadenza", "utenza"},
    "subscription":  {"abbonamento", "rinnovo", "canone"},
    "communication": {"rispondere", "messaggio", "richiamare", "chiamare"},
    "travel":        {"viaggio", "volo", "treno", "partire", "aeroporto", "trasferta"},
    "health":        {"visita", "medico", "farmacia", "esame", "controllo", "cardio", "dentista"},
    "fitness":       {"palestra", "allenamento", "corsa"},
    "exam":          {"esame", "studio", "appello"},
    "purchase":      {"comprare", "acquistare", "ordinare"},
}


def s_keywords(decision: Dict[str, Any], node: Dict[str, Any], decision_text: str = "", **_kw) -> List[MatchSignal]:
    cat = decision.get("category") or "generic"
    if node.get("type") not in CATEGORY_TYPE_COMPAT.get(cat, frozenset()):
        return []
    kws = _CATEGORY_KEYWORDS.get(cat, set())
    if not kws:
        return []
    tokens = set(decision_text.split())
    hit = kws & tokens
    if not hit:
        return []
    return [MatchSignal(
        tag="KEYWORD_ONLY",
        description=f"Parole chiave rilevate: {', '.join(sorted(hit))[:80]}",
        contribution=0.12,
    )]


# ------------------------------------------------------------------
# Graph relation — reads the pre-computed `neighbors` map (repo).
# Contribution is 0 at first pass; the confidence combiner boosts a candidate
# whose neighbor already has a strong non-graph confidence.
# ------------------------------------------------------------------
def s_graph_direct(node: Dict[str, Any], neighbor_confidences: Dict[str, float], **_kw) -> List[MatchSignal]:
    best = 0.0
    for nb_id, nb_conf in neighbor_confidences.items():
        if nb_conf > best:
            best = nb_conf
    if best < 0.60:
        return []
    return [MatchSignal(
        tag="GRAPH_DIRECT",
        description="Nodo direttamente collegato a un elemento fortemente pertinente",
        contribution=round(min(0.35, best * 0.45), 2),
    )]


# ------------------------------------------------------------------
# Convenience: run all strategies on a single (decision, node) pair.
# ------------------------------------------------------------------
def evaluate_pair(
    decision: Dict[str, Any],
    node: Dict[str, Any],
    knowledge: Optional[Dict[str, Any]],
    dtext: str,
) -> List[MatchSignal]:
    signals: List[MatchSignal] = []
    signals.extend(s_explicit_link(decision, node))
    signals.extend(s_verifiable_identifiers(decision, node, knowledge=knowledge))
    signals.extend(s_category_type(decision, node))
    signals.extend(s_knowledge_text_match(decision, node, knowledge=knowledge, decision_text=dtext))
    signals.extend(s_node_label(decision, node, decision_text=dtext))
    signals.extend(s_keywords(decision, node, decision_text=dtext))
    return signals


def has_verifiable(signals: List[MatchSignal]) -> bool:
    return any(s.verifiable for s in signals)
