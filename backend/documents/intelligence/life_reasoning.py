"""AI Document Understanding for Life Experience.

Reuses Documents V2 (storage / OCR / extraction / classification / analysis) —
this module adds ONE extra structured reasoning step on top of an already
analyzed document. It is NOT a second pipeline: it reads `doc.extracted_text`
and `doc.analysis` (produced by `documents.intelligence.analyzer`) and writes
its result back onto the SAME document under `doc["life_reasoning"]`.

Output is always a validated `DocumentReasoning` (Pydantic) — never free JSON,
never chain-of-thought (only a short `reason_summary`). If Gemini / any LLM
provider is unavailable or returns invalid output, a deterministic fallback
is used and `ai_used=False` — the caller must never claim "compreso
dall'AI" in that case.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, Field, field_validator

from llm import LLMNotConfigured, chat_json, llm_status
from llm.errors import LLMQuotaError, LLMRateLimitError, LLMTimeoutError
from llm.structured import chunk_text

logger = logging.getLogger("ora.documents.life_reasoning")

LIFE_REASONING_VERSION = "life-doc-understanding-1.0"
PROMPT_VERSION = "life-doc-reasoning-1"

# Document types Life Experience actively reasons about (spec priority list).
DOCUMENT_TYPES = (
    "rogito",
    "contratto_locazione",
    "mutuo",
    "bolletta",
    "libretto",
    "polizza_auto",
    "polizza_casa",
    "polizza",
    "prestito_auto",
    "piano_di_studi",
    "dispensa",
    "calendario_esami",
    "contratto",
    "comunicazione",
    "fattura",
    "ricevuta",
    "altro",
)

DomainKey = Literal[
    "casa", "auto", "studio", "amministrativo", "assicurazioni", "finanze", "generico",
]

DateRole = Literal["reference", "deadline", "contract_start", "contract_end"]
AmountRole = Literal["total", "installment", "fee", "recurring"]


# --------------------------------------------------------------------------
# Generic structured reasoning
# --------------------------------------------------------------------------
class EntityRef(BaseModel):
    type: str
    value: str
    confidence: float = Field(ge=0, le=1, default=0.5)


class RelationshipItem(BaseModel):
    subject: str
    relation: str
    object: str
    confidence: float = Field(ge=0, le=1, default=0.5)


class DateItem(BaseModel):
    value: Optional[str] = None
    role: DateRole = "reference"
    label: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, v: Any) -> Optional[str]:
        return _coerce_optional_str(v)


class AmountItem(BaseModel):
    value: Optional[str] = None
    currency: str = "EUR"
    role: AmountRole = "total"
    label: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, v: Any) -> Optional[str]:
        return _coerce_optional_str(v)


class RecurringObligation(BaseModel):
    description: str
    frequency: Optional[str] = None  # monthly/annual/bimonthly/...
    amount: Optional[str] = None
    next_due: Optional[str] = None
    confidence: float = Field(ge=0, le=1, default=0.5)


class RecommendedActionItem(BaseModel):
    action_type: str  # e.g. create_reminder, draft_calendar_event, confirm_field, link_document
    title: str
    description: str = ""
    requires_consent: bool = True


class LinkedLifeObjectRef(BaseModel):
    object_type: str  # house/vehicle/supplier/course/insurance_policy
    identifier: str  # normalized key used for cross-document matching
    confidence: float = Field(ge=0, le=1, default=0.5)


class Ambiguity(BaseModel):
    field: str
    description: str


def _coerce_list(v: Any) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _coerce_optional_str(v: Any) -> Optional[str]:
    """Gemini sometimes emits numeric-looking fields (amounts, CFU, plates) as
    JSON numbers instead of strings — coerce rather than reject valid data."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)
    return str(v)


class DocumentReasoning(BaseModel):
    """Validated structured document understanding — Pydantic only, no free JSON."""

    document_id: str = ""
    document_type: str = "altro"
    document_subtype: Optional[str] = None
    domain: DomainKey = "generico"
    purpose: str = ""
    title: str = ""
    summary: str = ""
    entities: List[EntityRef] = Field(default_factory=list)
    relationships: List[RelationshipItem] = Field(default_factory=list)
    dates: List[DateItem] = Field(default_factory=list)
    amounts: List[AmountItem] = Field(default_factory=list)
    recurring_obligations: List[RecurringObligation] = Field(default_factory=list)
    recommended_actions: List[RecommendedActionItem] = Field(default_factory=list)
    linked_life_objects: List[LinkedLifeObjectRef] = Field(default_factory=list)
    ambiguities: List[Ambiguity] = Field(default_factory=list)
    type_specific: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1, default=0.4)
    reason_summary: str = ""  # short, user-facing rationale — never chain-of-thought
    provider: str = "local-deterministic"
    model: str = "local-deterministic"
    analysis_version: int = 1
    ai_used: bool = False
    content_hash: str = ""
    created_at: str = ""

    @field_validator("entities", "relationships", "dates", "amounts", "recurring_obligations",
                      "recommended_actions", "linked_life_objects", "ambiguities", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> List[Any]:
        return _coerce_list(v)


# --------------------------------------------------------------------------
# Type-specific detail schemas (best-effort validation of type_specific)
# --------------------------------------------------------------------------
class _NumericStrCoercedMixin(BaseModel):
    """Coerces every Optional[str] field so a Gemini JSON number never fails
    validation — money/CFU/plate-like fields are frequently emitted as numbers."""

    @field_validator("*", mode="before")
    @classmethod
    def _coerce_all_str_fields(cls, v: Any, info: Any) -> Any:
        field = cls.model_fields.get(info.field_name)
        if field is not None and field.annotation in (Optional[str], str):
            return _coerce_optional_str(v)
        return v


class RogitoDetails(_NumericStrCoercedMixin):
    address: Optional[str] = None
    cadastral_data: Optional[str] = None
    price: Optional[str] = None
    buyer: Optional[str] = None
    seller: Optional[str] = None
    notary: Optional[str] = None
    deed_date: Optional[str] = None
    property_type: Optional[str] = None


class MutuoDetails(_NumericStrCoercedMixin):
    lender: Optional[str] = None
    principal_amount: Optional[str] = None
    interest_rate: Optional[str] = None
    duration_months: Optional[int] = None
    monthly_installment: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    property_address: Optional[str] = None


class BollettaDetails(_NumericStrCoercedMixin):
    supplier: Optional[str] = None
    utility_type: Optional[str] = None  # energia/gas/acqua/internet
    amount_total: Optional[str] = None
    due_date: Optional[str] = None
    billing_period: Optional[str] = None
    contract_code: Optional[str] = None
    address: Optional[str] = None
    consumption: Optional[str] = None


class LibrettoDetails(_NumericStrCoercedMixin):
    plate: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    vin: Optional[str] = None
    first_registration_date: Optional[str] = None
    owner: Optional[str] = None
    fuel_type: Optional[str] = None


class PolizzaDetails(_NumericStrCoercedMixin):
    company: Optional[str] = None
    policy_number: Optional[str] = None
    coverage_type: Optional[str] = None
    premium_amount: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    insured_object: Optional[str] = None  # plate / address / person


class PianoStudiDetails(_NumericStrCoercedMixin):
    institution: Optional[str] = None
    course_name: Optional[str] = None
    exams: List[str] = Field(default_factory=list)
    total_cfu: Optional[str] = None
    academic_year: Optional[str] = None
    expected_graduation: Optional[str] = None

    @field_validator("exams", mode="before")
    @classmethod
    def _exams(cls, v: Any) -> List[str]:
        return [str(x) for x in _coerce_list(v) if x]


TYPE_SCHEMAS: Dict[str, Type[BaseModel]] = {
    "rogito": RogitoDetails,
    "contratto_locazione": RogitoDetails,
    "mutuo": MutuoDetails,
    "prestito_auto": MutuoDetails,
    "bolletta": BollettaDetails,
    "libretto": LibrettoDetails,
    "polizza_auto": PolizzaDetails,
    "polizza_casa": PolizzaDetails,
    "polizza": PolizzaDetails,
    "piano_di_studi": PianoStudiDetails,
    "calendario_esami": PianoStudiDetails,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_fingerprint(text: str, filename: str = "") -> str:
    h = hashlib.sha256()
    h.update((filename or "").encode("utf-8", errors="replace"))
    h.update(b"\0")
    h.update((text or "").encode("utf-8", errors="replace"))
    return h.hexdigest()[:32]


def _env_enabled() -> bool:
    return os.environ.get("LIFE_DOCUMENT_UNDERSTANDING_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


def guess_document_type(doc: Dict[str, Any], hint: Optional[str] = None) -> str:
    if hint and hint in DOCUMENT_TYPES:
        return hint
    macro = ((doc.get("analysis") or {}).get("macro_category") or "").lower()
    sub = ((doc.get("analysis") or {}).get("subcategory") or "").lower()
    text = (doc.get("extracted_text") or "").lower()
    filename = (doc.get("original_filename") or doc.get("filename") or "").lower()
    blob = f"{sub} {filename} {text[:2000]}"
    if any(k in blob for k in ("rogito", "atto di compravendita", "compravendita")):
        return "rogito"
    if any(k in blob for k in ("contratto di locazione", "locazione", "affitto")):
        return "contratto_locazione"
    if any(k in blob for k in ("mutuo", "finanziamento immobiliare")):
        return "mutuo"
    if any(k in blob for k in ("bolletta", "fattura energia", "fattura gas", "consumo kwh", "consumo smc")):
        return "bolletta"
    if any(k in blob for k in ("libretto di circolazione", "carta di circolazione")):
        return "libretto"
    if "polizza" in blob and any(k in blob for k in ("auto", "rc auto", "targa")):
        return "polizza_auto"
    if "polizza" in blob and "casa" in blob:
        return "polizza_casa"
    if "polizza" in blob:
        return "polizza"
    if "prestito" in blob and "auto" in blob:
        return "prestito_auto"
    if any(k in blob for k in ("piano di studi", "libretto universitario")):
        return "piano_di_studi"
    if any(k in blob for k in ("calendario esami", "programma esami", "sessione esami")):
        return "calendario_esami"
    if any(k in blob for k in ("dispensa", "appunti", "lezione")):
        return "dispensa"
    if any(k in blob for k in ("fattura",)):
        return "fattura"
    if any(k in blob for k in ("ricevuta", "scontrino")):
        return "ricevuta"
    if macro == "administrative" or any(k in blob for k in ("comunicazione", "avviso", "raccomandata")):
        return "comunicazione"
    if any(k in blob for k in ("contratto",)):
        return "contratto"
    return "altro"


DOMAIN_BY_TYPE: Dict[str, DomainKey] = {
    "rogito": "casa",
    "contratto_locazione": "casa",
    "mutuo": "casa",
    "bolletta": "casa",
    "libretto": "auto",
    "polizza_auto": "assicurazioni",
    "polizza_casa": "assicurazioni",
    "polizza": "assicurazioni",
    "prestito_auto": "auto",
    "piano_di_studi": "studio",
    "dispensa": "studio",
    "calendario_esami": "studio",
    "contratto": "amministrativo",
    "comunicazione": "amministrativo",
    "fattura": "finanze",
    "ricevuta": "finanze",
    "altro": "generico",
}


def _system_prompt() -> str:
    return (
        "Sei il modulo AI Document Understanding di ORA per la Life Experience. "
        "Rispondi SOLO con JSON valido conforme allo schema richiesto — mai testo libero, "
        "mai markdown, mai catena di ragionamento (solo un breve reason_summary finale). "
        "Non inventare fatti assenti dal testo: se un dato non è presente, ometti il campo o lascialo vuoto. "
        "Non includere MAI password, PIN, OTP, codici di accesso, IBAN completi o dati di carte di pagamento "
        "anche se presenti nel testo: ometti sempre questi valori. "
        "Distingui esplicitamente le date che sono scadenze/azioni (role=deadline) da date puramente "
        "informative (role=reference, contract_start, contract_end). "
        "Distingui gli importi totali (role=total) da rate/canoni (role=installment), spese accessorie "
        "(role=fee) e importi ricorrenti (role=recurring). "
        "Campi JSON richiesti: document_type, document_subtype, domain, purpose, title, summary, "
        "entities[{type,value,confidence}], relationships[{subject,relation,object,confidence}], "
        "dates[{value,role,label,confidence}], amounts[{value,currency,role,label,confidence}], "
        "recurring_obligations[{description,frequency,amount,next_due,confidence}], "
        "recommended_actions[{action_type,title,description,requires_consent}], "
        "linked_life_objects[{object_type,identifier,confidence}], ambiguities[{field,description}], "
        "type_specific (oggetto con i campi specifici del tipo documento), confidence (0-1), reason_summary."
    )


async def run_life_document_reasoning(
    doc: Dict[str, Any],
    *,
    user: Optional[Dict[str, Any]] = None,
    doc_type_hint: Optional[str] = None,
    force: bool = False,
    user_preference: Optional[str] = None,
) -> Dict[str, Any]:
    """Run (or reuse cached) AI Document Understanding for a Documents V2 document.

    Returns a dict: {"reasoning": DocumentReasoning.model_dump(), "cached": bool,
    "telemetry": {...no content, no prompt, no secrets...}}.
    """
    text = doc.get("extracted_text") or ""
    filename = doc.get("original_filename") or doc.get("filename") or "documento"
    content_hash = content_fingerprint(text, filename)
    doc_type = guess_document_type(doc, doc_type_hint)
    domain = DOMAIN_BY_TYPE.get(doc_type, "generico")

    prev = doc.get("life_reasoning") or {}
    if (
        not force
        and prev.get("content_hash") == content_hash
        and prev.get("analysis_version_tag") == LIFE_REASONING_VERSION
    ):
        return {"reasoning": prev, "cached": True, "telemetry": {"cached": True}}

    t0 = time.perf_counter()
    telemetry: Dict[str, Any] = {"doc_type": doc_type, "domain": domain}

    if _env_enabled() and text.strip():
        try:
            reasoning, meta = await _llm_reason(
                doc=doc, text=text, doc_type=doc_type, domain=domain,
                content_hash=content_hash, user_preference=user_preference,
            )
            telemetry.update({
                "provider": meta.get("provider"),
                "model": meta.get("model"),
                "latency_ms": meta.get("latency_ms"),
                "prompt_tokens": meta.get("prompt_tokens") or meta.get("approx_tokens_in"),
                "completion_tokens": meta.get("completion_tokens") or meta.get("approx_tokens_out"),
                "fallback_used": meta.get("fallback_used", False),
                "ai_used": True,
            })
            dump = reasoning.model_dump()
            dump["analysis_version_tag"] = LIFE_REASONING_VERSION
            dump["computed_at"] = _now()
            return {"reasoning": dump, "cached": False, "telemetry": telemetry}
        except LLMNotConfigured:
            telemetry["fallback_reason"] = "not_configured"
        except (LLMRateLimitError, LLMTimeoutError, LLMQuotaError) as e:
            telemetry["fallback_reason"] = type(e).__name__
        except Exception:
            logger.warning("life document reasoning LLM call failed; using deterministic fallback")
            telemetry["fallback_reason"] = "exception"
    else:
        telemetry["fallback_reason"] = "disabled_or_no_text"

    reasoning = _deterministic_fallback(doc=doc, doc_type=doc_type, domain=domain, content_hash=content_hash)
    telemetry["ai_used"] = False
    telemetry["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    dump = reasoning.model_dump()
    dump["analysis_version_tag"] = LIFE_REASONING_VERSION
    dump["computed_at"] = _now()
    return {"reasoning": dump, "cached": False, "telemetry": telemetry}


async def _llm_reason(
    *, doc: Dict[str, Any], text: str, doc_type: str, domain: str,
    content_hash: str, user_preference: Optional[str] = None,
) -> tuple[DocumentReasoning, Dict[str, Any]]:
    chunks = chunk_text(text)
    if not chunks:
        raise LLMNotConfigured("nessun testo utile")
    analysis = doc.get("analysis") or {}
    import json
    payload = {
        "document_type_hint": doc_type,
        "domain_hint": domain,
        "macro_category": analysis.get("macro_category"),
        "subcategory": analysis.get("subcategory"),
        "filename": doc.get("original_filename") or doc.get("filename"),
        "document_text": chunks[0],
        "chunk_total": len(chunks),
    }
    if len(chunks) > 1:
        payload["additional_chunk_previews"] = [c[:400] for c in chunks[1:]]
    user_msg = json.dumps(payload, ensure_ascii=False)
    parsed, meta = await chat_json(
        system=_system_prompt(),
        user=user_msg,
        model_cls=DocumentReasoning,
        session_id=f"ora-life-doc-{doc.get('id')}",
        user_preference=user_preference,
    )
    parsed.document_id = doc.get("id") or ""
    if not parsed.document_type or parsed.document_type not in DOCUMENT_TYPES:
        parsed.document_type = doc_type
    if not parsed.domain:
        parsed.domain = domain  # type: ignore[assignment]
    parsed.provider = meta.get("provider") or "gemini"
    parsed.model = meta.get("model") or llm_status().get("model") or "unknown"
    parsed.ai_used = True
    parsed.content_hash = content_hash
    parsed.created_at = _now()
    parsed.analysis_version = int((doc.get("life_reasoning") or {}).get("analysis_version") or 0) + 1
    # Best-effort validation of type_specific against the known schema (never fatal).
    schema_cls = TYPE_SCHEMAS.get(parsed.document_type)
    if schema_cls is not None and parsed.type_specific:
        try:
            parsed.type_specific = schema_cls.model_validate(parsed.type_specific).model_dump()
        except Exception:
            parsed.ambiguities.append(
                Ambiguity(field="type_specific", description="Campi specifici non pienamente validati.")
            )
    return parsed, meta


def _deterministic_fallback(
    *, doc: Dict[str, Any], doc_type: str, domain: str, content_hash: str,
) -> DocumentReasoning:
    """No Gemini available/valid — build a conservative reasoning from existing
    Documents V2 analysis fields. Never claims AI understanding."""
    analysis = doc.get("analysis") or {}
    admin = doc.get("admin_analysis") or {}
    edu = doc.get("education_analysis") or {}
    events = doc.get("event_candidates") or []
    text = doc.get("extracted_text") or ""

    dates: List[DateItem] = []
    if admin.get("due_date"):
        dates.append(DateItem(value=admin["due_date"], role="deadline", label="Scadenza", confidence=0.5))
    if admin.get("issue_date"):
        dates.append(DateItem(value=admin["issue_date"], role="reference", label="Data emissione", confidence=0.4))
    for ev in events[:5]:
        if ev.get("start_datetime"):
            dates.append(DateItem(
                value=ev["start_datetime"], role="deadline",
                label=ev.get("title") or "Evento", confidence=float(ev.get("confidence") or 0.4),
            ))

    amounts: List[AmountItem] = []
    if admin.get("amount"):
        amounts.append(AmountItem(
            value=admin.get("amount"), currency=admin.get("currency") or "EUR",
            role="total", label="Importo", confidence=0.5,
        ))
    for mv in (analysis.get("monetary_values") or [])[:5]:
        amounts.append(AmountItem(value=str(mv), role="total", label="Importo rilevato", confidence=0.35))

    recommended: List[RecommendedActionItem] = []
    if admin.get("due_date") or admin.get("amount"):
        recommended.append(RecommendedActionItem(
            action_type="draft_calendar_event",
            title="Proponi promemoria scadenza",
            description="Creare un promemoria per la scadenza rilevata (richiede conferma).",
            requires_consent=True,
        ))
    if edu.get("subject"):
        recommended.append(RecommendedActionItem(
            action_type="study_plan",
            title="Avvia percorso di studio",
            description=f"Collegare {edu.get('subject')} a un piano di studio.",
            requires_consent=True,
        ))

    summary = admin.get("simple_explanation") or edu.get("summary_short") or analysis.get("summary") or ""
    title = analysis.get("suggested_title") or doc.get("filename") or "Documento"

    return DocumentReasoning(
        document_id=doc.get("id") or "",
        document_type=doc_type,
        domain=domain,  # type: ignore[arg-type]
        purpose="Analisi locale deterministica (nessuna comprensione AI disponibile).",
        title=str(title)[:160],
        summary=(summary or text[:280])[:600],
        dates=dates,
        amounts=amounts,
        recommended_actions=recommended,
        confidence=0.35,
        reason_summary="Analisi locale: nessun provider AI disponibile o testo insufficiente.",
        provider="local-deterministic",
        model="local-deterministic",
        analysis_version=int((doc.get("life_reasoning") or {}).get("analysis_version") or 0) + 1,
        ai_used=False,
        content_hash=content_hash,
        created_at=_now(),
    )
