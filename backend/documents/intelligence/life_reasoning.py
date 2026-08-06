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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from llm import LLMNotConfigured, chat_json, llm_status
from llm.errors import LLMQuotaError, LLMRateLimitError, LLMTimeoutError
from llm.structured import chunk_text

logger = logging.getLogger("ora.documents.life_reasoning")

LIFE_REASONING_VERSION = "life-doc-understanding-2.0"
PROMPT_VERSION = "life-doc-reasoning-2"

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
    "contratto_telefono",
    "contratto_luce",
    "comunicazione",
    "fattura",
    "ricevuta",
    "busta_paga",
    "verbale",
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
    model_config = ConfigDict(extra="ignore")
    type: str = ""
    value: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)

    @field_validator("type", "value", mode="before")
    @classmethod
    def _s(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


class RelationshipItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subject: str = ""
    relation: str = ""
    object: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)

    @field_validator("subject", "relation", "object", mode="before")
    @classmethod
    def _s(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


class DateItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: Optional[str] = None
    role: str = "reference"
    label: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)

    @field_validator("value", "label", mode="before")
    @classmethod
    def _coerce_value(cls, v: Any) -> Optional[str]:
        return _coerce_optional_str(v)

    @field_validator("role", mode="before")
    @classmethod
    def _role(cls, v: Any) -> str:
        s = str(v or "reference").strip().lower()
        return s if s in ("reference", "deadline", "contract_start", "contract_end") else "reference"

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


class AmountItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: Optional[str] = None
    currency: str = "EUR"
    role: str = "total"
    label: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)

    @field_validator("value", "label", "currency", mode="before")
    @classmethod
    def _coerce_value(cls, v: Any) -> Optional[str]:
        return _coerce_optional_str(v)

    @field_validator("role", mode="before")
    @classmethod
    def _role(cls, v: Any) -> str:
        s = str(v or "total").strip().lower()
        return s if s in ("total", "installment", "fee", "recurring") else "total"

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


class RecurringObligation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    description: str = ""
    frequency: Optional[str] = None  # monthly/annual/bimonthly/...
    amount: Optional[str] = None
    next_due: Optional[str] = None
    confidence: float = Field(ge=0, le=1, default=0.5)

    @field_validator("description", "frequency", "amount", "next_due", mode="before")
    @classmethod
    def _s(cls, v: Any) -> Optional[str]:
        return _coerce_optional_str(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


class RecommendedActionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action_type: str = "generic_action"
    title: str = ""
    description: str = ""
    motivo: str = ""
    beneficio: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)
    origine: str = "ai"
    documento: str = ""
    spiegazione: str = ""
    priority: str = "medium"
    requires_consent: bool = True

    @field_validator("title", "description", "motivo", "beneficio", "origine",
                      "documento", "spiegazione", "action_type", "priority", mode="before")
    @classmethod
    def _str_fields(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    @field_validator("requires_consent", mode="before")
    @classmethod
    def _boolish(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return True
        return str(v).strip().lower() not in ("0", "false", "no", "off")


class LinkedLifeObjectRef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    object_type: str = ""  # house/vehicle/supplier/course/insurance_policy
    identifier: str = ""  # normalized key used for cross-document matching
    confidence: float = Field(ge=0, le=1, default=0.5)

    @field_validator("object_type", "identifier", mode="before")
    @classmethod
    def _s(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


class Ambiguity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str = ""
    description: str = ""

    @field_validator("field", "description", mode="before")
    @classmethod
    def _s(cls, v: Any) -> str:
        return "" if v is None else str(v)


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


class DocumentKnowledge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    keywords: List[str] = Field(default_factory=list)
    facts: List[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("keywords", "facts", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> List[Any]:
        return [str(x) for x in _coerce_list(v) if x]

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, v: Any) -> str:
        return "" if v is None else str(v)


class RelatedDocRef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    document_id: str = ""
    relation: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)
    ask_user: bool = False

    @field_validator("document_id", "relation", mode="before")
    @classmethod
    def _s(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _c(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    @field_validator("ask_user", mode="before")
    @classmethod
    def _b(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        return str(v).strip().lower() in ("1", "true", "yes", "on")


class DocumentReasoning(BaseModel):
    """Validated structured document understanding — Pydantic only, no free JSON."""

    model_config = ConfigDict(extra="ignore")

    document_id: str = ""
    document_type: str = "altro"
    document_subtype: Optional[str] = None
    domain: str = "generico"
    purpose: str = ""
    title: str = ""
    summary: str = ""
    context: str = ""  # life context: why this doc matters to the user
    benefit: str = ""  # concrete benefit for the user
    entities: List[EntityRef] = Field(default_factory=list)
    relationships: List[RelationshipItem] = Field(default_factory=list)
    dates: List[DateItem] = Field(default_factory=list)
    amounts: List[AmountItem] = Field(default_factory=list)
    recurring_obligations: List[RecurringObligation] = Field(default_factory=list)
    recommended_actions: List[RecommendedActionItem] = Field(default_factory=list)
    linked_life_objects: List[LinkedLifeObjectRef] = Field(default_factory=list)
    related_docs: List[RelatedDocRef] = Field(default_factory=list)
    ambiguities: List[Ambiguity] = Field(default_factory=list)
    knowledge: DocumentKnowledge = Field(default_factory=DocumentKnowledge)
    type_specific: Dict[str, Any] = Field(default_factory=dict)
    priority: str = "medium"
    criticality: str = "none"
    deadlines: List[DateItem] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.4)
    reason_summary: str = ""  # short, user-facing rationale — never chain-of-thought
    provider: str = "local-deterministic"
    model: str = "local-deterministic"
    analysis_version: int = 1  # integer revision counter — never a "2.0" string
    analysis_schema_version: str = "2.0"
    ai_used: bool = False
    content_hash: str = ""
    created_at: str = ""

    @field_validator("entities", "relationships", "dates", "amounts", "recurring_obligations",
                      "recommended_actions", "linked_life_objects", "related_docs",
                      "ambiguities", "deadlines", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> List[Any]:
        items = _coerce_list(v)
        # Drop bare strings / nulls that Gemini sometimes emits in list slots
        return [x for x in items if isinstance(x, dict) or hasattr(x, "model_dump")]

    @field_validator("type_specific", mode="before")
    @classmethod
    def _type_specific(cls, v: Any) -> Dict[str, Any]:
        if v is None or v == "":
            return {}
        if isinstance(v, dict):
            return v
        return {"raw": str(v)[:500]}

    @field_validator("knowledge", mode="before")
    @classmethod
    def _knowledge(cls, v: Any) -> Any:
        if v is None:
            return {}
        if isinstance(v, list):
            return {"facts": [str(x) for x in v if x]}
        if isinstance(v, str):
            return {"notes": v}
        return v

    @field_validator("priority", mode="before")
    @classmethod
    def _priority(cls, v: Any) -> str:
        s = str(v or "medium").strip().lower()
        return s if s in ("low", "medium", "high", "critical") else "medium"

    @field_validator("criticality", mode="before")
    @classmethod
    def _criticality(cls, v: Any) -> str:
        s = str(v or "none").strip().lower()
        return s if s in ("none", "low", "medium", "high", "critical") else "none"

    @field_validator("domain", mode="before")
    @classmethod
    def _domain(cls, v: Any) -> str:
        s = str(v or "generico").strip().lower()
        allowed = ("casa", "auto", "studio", "amministrativo", "assicurazioni", "finanze", "generico")
        return s if s in allowed else "generico"

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence(cls, v: Any) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.4
        return max(0.0, min(1.0, f))

    @field_validator("analysis_version", mode="before")
    @classmethod
    def _analysis_version(cls, v: Any) -> int:
        from documents.intelligence.versions import coerce_analysis_revision
        return coerce_analysis_revision(v) or 1


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
    if any(k in blob for k in ("contratto luce", "contratto energia", "fornitura energia elettrica")):
        return "contratto_luce"
    if any(k in blob for k in ("contratto telefon", "contratto mobile", "sim ", "piano tariffario")):
        return "contratto_telefono"
    if any(k in blob for k in ("busta paga", "cedolino", "retribuzione")):
        return "busta_paga"
    if any(k in blob for k in ("verbale d'esame", "verbale di esame", "verbale esame", "esito esame")):
        return "verbale"
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
    "contratto_luce": "casa",
    "libretto": "auto",
    "polizza_auto": "assicurazioni",
    "polizza_casa": "assicurazioni",
    "polizza": "assicurazioni",
    "prestito_auto": "auto",
    "piano_di_studi": "studio",
    "dispensa": "studio",
    "calendario_esami": "studio",
    "verbale": "studio",
    "contratto": "amministrativo",
    "contratto_telefono": "amministrativo",
    "comunicazione": "amministrativo",
    "fattura": "finanze",
    "ricevuta": "finanze",
    "busta_paga": "finanze",
    "altro": "generico",
}


def _system_prompt() -> str:
    return (
        "Sei l'assistente personale di ORA: organizzatore amministrativo e segretario di fiducia. "
        "Il tuo compito è capire documenti reali della vita dell'utente e strutturare ciò che serve "
        "per agire (scadenze, obblighi, collegamenti casa/auto/studio), senza chiacchiere. "
        "Rispondi SOLO con JSON valido conforme allo schema — mai testo libero, mai markdown, "
        "mai catena di ragionamento interna (solo un breve reason_summary utente-facing). "
        "REGOLE ASSOLUTE: non inventare date, importi, scadenze, nomi o fatti assenti dal testo del documento; "
        "se manca un dato, ometti il campo o lascialo vuoto. "
        "Non includere MAI password, PIN, OTP, codici di accesso, IBAN completi o dati di carte di pagamento. "
        "Usa il contesto vita (profilo/obiettivi/calendario/documenti noti) SOLO per collegare e contestualizzare, "
        "mai per inventare contenuti del documento. "
        "Ipotesi di vita (es. proprietà vs affitto da una bolletta) vanno in ambiguities o come linked_life_objects "
        "con confidence bassa — mai come fatti certi. "
        "Per i titoli dei promemoria preferisci 'Pagamento bolletta Enel' / 'Pagamento rata mutuo Intesa' "
        "quando fornitore/istituto è noto, non 'Scadenza pagamento 87 EUR'. "
        "Distingui date deadline vs reference/contract_start/contract_end; "
        "importi total vs installment/fee/recurring. "
        "Campi JSON: document_type, document_subtype, domain, purpose, title, summary, context, benefit, "
        "entities[{type,value,confidence}], relationships[{subject,relation,object,confidence}], "
        "dates[{value,role,label,confidence}], amounts[{value,currency,role,label,confidence}], "
        "deadlines[{value,role,label,confidence}], recurring_obligations[...], "
        "recommended_actions[{action_type,title,description,motivo,beneficio,confidence,origine,spiegazione,requires_consent}], "
        "linked_life_objects[{object_type,identifier,confidence}], related_docs[{document_id,relation,confidence,ask_user}], "
        "ambiguities[{field,description}], knowledge[{keywords,facts,notes}], "
        "type_specific, priority, criticality, confidence (0-1), reason_summary."
    )


async def run_life_document_reasoning(
    doc: Dict[str, Any],
    *,
    user: Optional[Dict[str, Any]] = None,
    doc_type_hint: Optional[str] = None,
    force: bool = False,
    user_preference: Optional[str] = None,
    db: Any = None,
) -> Dict[str, Any]:
    """Run (or reuse cached) AI Document Understanding for a Documents V2 document.

    Returns a dict: {"reasoning": DocumentReasoning.model_dump(), "cached": bool,
    "telemetry": {...no content, no prompt, no secrets...}}.
    """
    from documents.intelligence.versions import next_analysis_revision

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
    next_rev = next_analysis_revision(prev.get("analysis_version"))

    if _env_enabled() and text.strip():
        try:
            reasoning, meta = await _llm_reason(
                doc=doc, text=text, doc_type=doc_type, domain=domain,
                content_hash=content_hash, user_preference=user_preference,
                db=db, user=user, analysis_revision=next_rev,
            )
            telemetry.update({
                "provider": meta.get("provider"),
                "model": meta.get("model"),
                "latency_ms": meta.get("latency_ms"),
                "prompt_tokens": meta.get("prompt_tokens") or meta.get("approx_tokens_in"),
                "completion_tokens": meta.get("completion_tokens") or meta.get("approx_tokens_out"),
                "fallback_used": meta.get("fallback_used", False),
                "ai_used": True,
                "context_attached": bool(meta.get("context_attached")),
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

    reasoning = _deterministic_fallback(
        doc=doc, doc_type=doc_type, domain=domain, content_hash=content_hash,
        analysis_revision=next_rev,
    )
    telemetry["ai_used"] = False
    telemetry["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    dump = reasoning.model_dump()
    dump["analysis_version_tag"] = LIFE_REASONING_VERSION
    dump["computed_at"] = _now()
    return {"reasoning": dump, "cached": False, "telemetry": telemetry}


async def _llm_reason(
    *, doc: Dict[str, Any], text: str, doc_type: str, domain: str,
    content_hash: str, user_preference: Optional[str] = None,
    db: Any = None, user: Optional[Dict[str, Any]] = None,
    analysis_revision: int = 1,
) -> tuple[DocumentReasoning, Dict[str, Any]]:
    chunks = chunk_text(text)
    if not chunks:
        raise LLMNotConfigured("nessun testo utile")
    analysis = doc.get("analysis") or {}
    import json
    from documents.intelligence.document_context import assemble_document_context

    life_ctx = await assemble_document_context(
        doc, user=user, db=db, doc_type_hint=doc_type,
        estimated_category=analysis.get("macro_category"),
    )
    payload = {
        "document_type_hint": doc_type,
        "domain_hint": domain,
        "macro_category": analysis.get("macro_category"),
        "subcategory": analysis.get("subcategory"),
        "filename": doc.get("original_filename") or doc.get("filename"),
        "document_text": chunks[0],
        "chunk_total": len(chunks),
        "life_context": life_ctx,
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
    parsed.analysis_version = analysis_revision
    parsed.analysis_schema_version = "2.0"
    # Mirror deadline-role dates into deadlines if model omitted the dedicated list
    if not parsed.deadlines:
        parsed.deadlines = [d for d in parsed.dates if d.role == "deadline"]
    for action in parsed.recommended_actions:
        if not action.documento:
            action.documento = parsed.document_id
        if not action.origine:
            action.origine = "ai"
    # Best-effort validation of type_specific against the known schema (never fatal).
    schema_cls = TYPE_SCHEMAS.get(parsed.document_type)
    if schema_cls is not None and parsed.type_specific:
        try:
            parsed.type_specific = schema_cls.model_validate(parsed.type_specific).model_dump()
        except Exception:
            parsed.ambiguities.append(
                Ambiguity(field="type_specific", description="Campi specifici non pienamente validati.")
            )
    meta = dict(meta or {})
    meta["context_attached"] = True
    return parsed, meta


def _deterministic_fallback(
    *, doc: Dict[str, Any], doc_type: str, domain: str, content_hash: str,
    analysis_revision: int = 1,
) -> DocumentReasoning:
    """No Gemini available/valid — build a conservative reasoning from existing
    Documents V2 analysis fields. Never claims AI understanding."""
    analysis = doc.get("analysis") or {}
    admin = doc.get("admin_analysis") or {}
    edu = doc.get("education_analysis") or {}
    events = doc.get("event_candidates") or []
    text = doc.get("extracted_text") or ""
    sender = admin.get("sender") or ""

    dates: List[DateItem] = []
    deadlines: List[DateItem] = []
    if admin.get("due_date"):
        d = DateItem(value=admin["due_date"], role="deadline", label="Scadenza", confidence=0.5)
        dates.append(d)
        deadlines.append(d)
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
        if doc_type == "bolletta":
            rem_title = f"Pagamento bolletta{(' ' + sender) if sender else ''}".strip()
        elif doc_type == "mutuo":
            rem_title = f"Pagamento rata mutuo{(' ' + sender) if sender else ''}".strip()
        else:
            rem_title = "Proponi promemoria scadenza"
        recommended.append(RecommendedActionItem(
            action_type="draft_calendar_event",
            title=rem_title[:160],
            description="Creare un promemoria per la scadenza rilevata (richiede conferma).",
            motivo="Scadenza o importo rilevati localmente dal documento",
            beneficio="Ricorda l'adempimento senza creare eventi irreversibili",
            confidence=0.45,
            origine="local-assist",
            documento=doc.get("id") or "",
            spiegazione="Fallback locale: Gemini non disponibile o output non valido.",
            priority="high",
            requires_consent=True,
        ))
    if edu.get("subject"):
        recommended.append(RecommendedActionItem(
            action_type="study_plan",
            title="Avvia percorso di studio",
            description=f"Collegare {edu.get('subject')} a un piano di studio.",
            motivo="Materia rilevata nel documento",
            beneficio="Organizzare lo studio con ORA",
            confidence=0.4,
            origine="local-assist",
            documento=doc.get("id") or "",
            spiegazione="Fallback locale su analisi education.",
            requires_consent=True,
        ))

    summary = admin.get("simple_explanation") or edu.get("summary_short") or analysis.get("summary") or ""
    title = analysis.get("suggested_title") or doc.get("filename") or "Documento"
    ambiguities: List[Ambiguity] = []
    if doc_type == "bolletta":
        ambiguities.append(Ambiguity(
            field="casa.ownership_hypothesis",
            description="La bolletta suggerisce un'utenza domestica: proprietà o affitto vanno confermati (ipotesi, non fatto).",
        ))

    return DocumentReasoning(
        document_id=doc.get("id") or "",
        document_type=doc_type,
        domain=domain,  # type: ignore[arg-type]
        purpose="Analisi locale deterministica (nessuna comprensione AI disponibile).",
        title=str(title)[:160],
        summary=(summary or text[:280])[:600],
        context="Contesto vita non arricchito: provider AI assente.",
        benefit="Campi e scadenze base estratti localmente; conferma richiesta prima di azioni.",
        dates=dates,
        deadlines=deadlines,
        amounts=amounts,
        recommended_actions=recommended,
        ambiguities=ambiguities,
        knowledge=DocumentKnowledge(
            keywords=[doc_type, domain],
            facts=[],
            notes="Fallback locale — non AI.",
        ),
        priority="high" if deadlines else "medium",
        criticality="medium" if deadlines else "none",
        confidence=0.35,
        reason_summary="Analisi locale: nessun provider AI disponibile o testo insufficiente.",
        provider="local-deterministic",
        model="local-deterministic",
        analysis_version=analysis_revision,
        analysis_schema_version="2.0",
        ai_used=False,
        content_hash=content_hash,
        created_at=_now(),
    )
