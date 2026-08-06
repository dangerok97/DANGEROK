"""Document strategy — prefer upload when denser / more accurate than Q&A."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ai_life_strategist.models import RecommendedDocument

DOC_CATALOG: Dict[str, Dict[str, Any]] = {
    "rogito": {
        "label": "Rogito / atto di compravendita",
        "reason": "Dal rogito ORA estrae indirizzo e dati casa in un colpo solo.",
        "expected_fields": ["indirizzo", "data_rogito", "parti", "immobile"],
        "upload_hint": "PDF o foto nitida della prima pagina va bene.",
        "domains": ["casa", "documenti"],
    },
    "bolletta": {
        "label": "Bolletta utenze",
        "reason": "Una bolletta collega utenze, indirizzo e scadenze alla Casa.",
        "expected_fields": ["fornitore", "importo", "scadenza", "indirizzo"],
        "upload_hint": "PDF della bolletta recente.",
        "domains": ["casa", "finanze", "internet"],
    },
    "libretto": {
        "label": "Libretto di circolazione",
        "reason": "Dal libretto ORA legge targa e dati veicolo senza digitazione.",
        "expected_fields": ["targa", "marca", "modello", "telaio"],
        "upload_hint": "Foto di entrambe le facciate se possibile.",
        "domains": ["auto"],
    },
    "polizza_auto": {
        "label": "Polizza RC auto",
        "reason": "Serve a ricordarti la scadenza senza chiedere il PIN della compagnia.",
        "expected_fields": ["compagnia", "scadenza", "targa"],
        "upload_hint": "PDF o foto della polizza.",
        "domains": ["auto", "assicurazioni"],
    },
    "polizza_casa": {
        "label": "Polizza casa",
        "reason": "Collega copertura e rinnovo al profilo Casa.",
        "expected_fields": ["compagnia", "scadenza", "immobile"],
        "upload_hint": "PDF della polizza.",
        "domains": ["casa", "assicurazioni"],
    },
    "polizza": {
        "label": "Polizza assicurativa",
        "reason": "Una polizza permette scadenze e rinnovi senza questionario.",
        "expected_fields": ["tipo", "compagnia", "scadenza"],
        "upload_hint": "PDF o foto.",
        "domains": ["assicurazioni"],
    },
    "dispensa": {
        "label": "Dispensa / programma d’esame",
        "reason": "Da un documento di studio ORA può avviare un piano senza form.",
        "expected_fields": ["materia", "argomenti"],
        "upload_hint": "PDF o appunti.",
        "domains": ["studio"],
    },
    "contratto_internet": {
        "label": "Contratto internet",
        "reason": "Utile per scadenze e collegamento alle utenze casa.",
        "expected_fields": ["operatore", "scadenza"],
        "upload_hint": "PDF contratto.",
        "domains": ["internet", "casa"],
    },
    "documento": {
        "label": "Documento importante",
        "reason": "ORA estrae ciò che serve e lo collega al dominio giusto.",
        "expected_fields": [],
        "upload_hint": "PDF o immagine.",
        "domains": ["documenti"],
    },
    "referti": {
        "label": "Prenotazione / promemoria visita",
        "reason": "Solo dati di appuntamento — non cartelle cliniche complete.",
        "expected_fields": ["data", "tipo_visita"],
        "upload_hint": "Promemoria o prenotazione, non referti sensibili.",
        "domains": ["salute"],
    },
}


def recommend_document(
    doc_type: Optional[str],
    *,
    domain: Optional[str] = None,
) -> Optional[RecommendedDocument]:
    if not doc_type:
        return None
    meta = DOC_CATALOG.get(doc_type)
    if not meta:
        return RecommendedDocument(
            doc_type=doc_type,
            label=doc_type.replace("_", " ").title(),
            reason="Un documento riduce domande e aumenta l’accuratezza.",
            expected_fields=[],
            upload_hint="PDF o foto leggibile.",
        )
    if domain and domain not in meta.get("domains", []):
        # Still allow — catalog domains are hints
        pass
    return RecommendedDocument(
        doc_type=doc_type,
        label=meta["label"],
        reason=meta["reason"],
        expected_fields=list(meta.get("expected_fields") or []),
        upload_hint=meta.get("upload_hint"),
    )


def should_prefer_document(
    *,
    prefer_flag: bool,
    gap_key: str,
    already_have_doc_types: Optional[List[str]] = None,
) -> bool:
    have = set(already_have_doc_types or [])
    if gap_key.startswith("doc."):
        dtype = gap_key.split(".", 1)[-1]
        if dtype in have:
            return False
        return True
    return bool(prefer_flag)


def document_keys_from_upload(doc_type: str) -> List[str]:
    """Keys marked known after a successful upload path."""
    keys = [f"doc.{doc_type}"]
    if doc_type == "rogito":
        keys.extend(["casa.owned", "casa.purchased", "doc.rogito"])
    elif doc_type == "libretto":
        keys.extend(["auto.owned", "doc.libretto"])
    elif doc_type == "bolletta":
        keys.extend(["casa.utenze", "doc.bolletta"])
    elif doc_type in ("polizza_auto", "polizza_casa", "polizza"):
        keys.append(f"doc.{doc_type}")
        if doc_type == "polizza_casa":
            keys.append("casa.assicurazione")
        if doc_type == "polizza_auto":
            keys.append("auto.assicurazione_scadenza")
    return keys
