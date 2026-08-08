"""Document strategy — prefer upload when denser / more accurate than Q&A."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ai_life_strategist.models import RecommendedDocument

DOC_CATALOG: Dict[str, Dict[str, Any]] = {
    "rogito": {
        "label": "Rogito / atto di compravendita",
        "reason": (
            "posso ricavare io indirizzo e dati casa senza farti inserire tutto a mano. "
            "È un acceleratore, non un obbligo"
        ),
        "expected_fields": ["indirizzo", "data_rogito", "parti", "immobile"],
        "upload_hint": "PDF o foto nitida della prima pagina va bene.",
        "domains": ["casa", "documenti"],
    },
    "bolletta": {
        "label": "Bolletta utenze",
        "reason": (
            "posso collegare utenze, indirizzo e scadenze senza domande ripetute. "
            "Se preferisci, rispondi pure a voce"
        ),
        "expected_fields": ["fornitore", "importo", "scadenza", "indirizzo"],
        "upload_hint": "PDF della bolletta recente.",
        "domains": ["casa", "finanze", "internet"],
    },
    "libretto": {
        "label": "Libretto di circolazione",
        "reason": (
            "posso leggere targa e dati veicolo senza digitazione. "
            "Non è obbligatorio per iniziare"
        ),
        "expected_fields": ["targa", "marca", "modello", "telaio"],
        "upload_hint": "Foto di entrambe le facciate se possibile.",
        "domains": ["auto"],
    },
    "polizza_auto": {
        "label": "Polizza RC auto",
        "reason": (
            "posso ricordarti la scadenza senza chiederti il PIN della compagnia. "
            "Solo se ti fa comodo"
        ),
        "expected_fields": ["compagnia", "scadenza", "targa"],
        "upload_hint": "PDF o foto della polizza.",
        "domains": ["auto", "assicurazioni"],
    },
    "polizza_casa": {
        "label": "Polizza casa",
        "reason": "posso collegare copertura e rinnovo al tuo contesto casa, senza form",
        "expected_fields": ["compagnia", "scadenza", "immobile"],
        "upload_hint": "PDF della polizza.",
        "domains": ["casa", "assicurazioni"],
    },
    "polizza": {
        "label": "Polizza assicurativa",
        "reason": "posso tenere d’occhio scadenze e rinnovi senza un questionario",
        "expected_fields": ["tipo", "compagnia", "scadenza"],
        "upload_hint": "PDF o foto.",
        "domains": ["assicurazioni"],
    },
    "dispensa": {
        "label": "Dispensa / programma d’esame",
        "reason": "posso avviare un piano di studio da lì, senza form",
        "expected_fields": ["materia", "argomenti"],
        "upload_hint": "PDF o appunti.",
        "domains": ["studio"],
    },
    "piano_di_studi": {
        "label": "Piano di studi",
        "reason": (
            "posso ricavare esami e percorsi in un colpo solo, "
            "senza farti elencare tutto. Non è obbligatorio"
        ),
        "expected_fields": ["corso", "esami", "cfu", "anno"],
        "upload_hint": "PDF del piano di studi o del libretto universitario.",
        "domains": ["studio"],
    },
    "contratto_internet": {
        "label": "Contratto internet",
        "reason": (
            "posso ricavare io le informazioni utili su scadenze e operatore "
            "senza farti inserire tutto a mano"
        ),
        "expected_fields": ["operatore", "scadenza"],
        "upload_hint": "PDF contratto.",
        "domains": ["internet", "casa"],
    },
    "documento": {
        "label": "Documento importante",
        "reason": "posso estrarre ciò che serve e collegarlo al tema giusto — solo se ti aiuta",
        "expected_fields": [],
        "upload_hint": "PDF o immagine.",
        "domains": ["documenti"],
    },
    "referti": {
        "label": "Prenotazione / promemoria visita",
        "reason": "solo dati di appuntamento — non cartelle cliniche complete",
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
        label_it = doc_type.replace("_", " ")
        return RecommendedDocument(
            doc_type=doc_type,
            label=label_it,
            reason="posso ricavare io le informazioni utili senza farti inserire tutto a mano",
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
        keys.extend(["auto.owned", "doc.libretto", "auto.targa"])
    elif doc_type == "bolletta":
        keys.extend(["casa.utenze", "doc.bolletta"])
    elif doc_type == "piano_di_studi":
        keys.extend(["studio.active", "studio.universita", "doc.piano_di_studi"])
    elif doc_type == "dispensa":
        keys.extend(["studio.active", "doc.dispensa", "studio.esame"])
    elif doc_type in ("polizza_auto", "polizza_casa", "polizza"):
        keys.append(f"doc.{doc_type}")
        if doc_type == "polizza_casa":
            keys.append("casa.assicurazione")
        if doc_type == "polizza_auto":
            keys.append("auto.assicurazione_scadenza")
    return keys
