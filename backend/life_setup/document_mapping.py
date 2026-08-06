"""Declarative Life Profile mappers — DocumentReasoning → profile fields.

Every mapped field carries full provenance (source_document_id, confidence,
provider, model, analysis_version) so `LifeProfileService` can apply the
correct field status (extracted / suggested / confirmed / corrected /
rejected) and never silently overwrite a user-confirmed value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

HIGH_CONFIDENCE = 0.80
MEDIUM_CONFIDENCE = 0.50


def confidence_thresholds() -> Dict[str, float]:
    import os
    return {
        "high": float(os.environ.get("LIFE_DOC_CONFIDENCE_HIGH", str(HIGH_CONFIDENCE))),
        "medium": float(os.environ.get("LIFE_DOC_CONFIDENCE_MEDIUM", str(MEDIUM_CONFIDENCE))),
    }


def status_for_confidence(confidence: float) -> str:
    """Confidence bands drive the UI behaviour:
    high    -> extracted (auto-use, shown in "Dati trovati")
    medium  -> suggested (quick-confirm, shown in "Dati da verificare")
    low     -> suggested (explicit-correction required)
    """
    t = confidence_thresholds()
    if confidence >= t["high"]:
        return "extracted"
    return "suggested"


@dataclass
class MappedField:
    domain: str
    key: str
    value: Any
    raw_value: Any = None
    confidence: float = 0.5
    source_page: Optional[int] = None
    label: str = ""
    status: str = field(default="")

    def __post_init__(self) -> None:
        if not self.status:
            self.status = status_for_confidence(self.confidence)
        if self.raw_value is None:
            self.raw_value = self.value


def _entity_value(reasoning: Dict[str, Any], etype: str) -> Optional[str]:
    for e in reasoning.get("entities") or []:
        if e.get("type") == etype and e.get("value"):
            return e.get("value")
    return None


def _date_by_role(reasoning: Dict[str, Any], role: str) -> Optional[Dict[str, Any]]:
    for d in reasoning.get("dates") or []:
        if d.get("role") == role and d.get("value"):
            return d
    return None


def _amount_by_role(reasoning: Dict[str, Any], role: str) -> Optional[Dict[str, Any]]:
    for a in reasoning.get("amounts") or []:
        if a.get("role") == role and a.get("value"):
            return a
    return None


def map_rogito(reasoning: Dict[str, Any]) -> List[MappedField]:
    ts = reasoning.get("type_specific") or {}
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("casa", "casa.owned", True, confidence=conf, label="Proprietà casa"),
        MappedField("casa", "casa.purchased", True, confidence=conf, label="Casa acquistata"),
        MappedField("documenti", "doc.rogito", True, confidence=conf, label="Rogito caricato"),
    ]
    if ts.get("address"):
        out.append(MappedField("casa", "casa.indirizzo", ts["address"], confidence=conf, label="Indirizzo casa"))
    if ts.get("price"):
        out.append(MappedField("casa", "casa.valore_acquisto", ts["price"], confidence=conf, label="Valore di acquisto"))
    if ts.get("deed_date"):
        out.append(MappedField("casa", "casa.data_rogito", ts["deed_date"], confidence=conf, label="Data rogito"))
    if ts.get("property_type"):
        out.append(MappedField("casa", "casa.tipo_immobile", ts["property_type"], confidence=conf, label="Tipo immobile"))
    return out


def map_contratto_locazione(reasoning: Dict[str, Any]) -> List[MappedField]:
    ts = reasoning.get("type_specific") or {}
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("casa", "casa.owned", False, confidence=conf, label="Casa in affitto"),
        MappedField("casa", "casa.affitto", True, confidence=conf, label="Contratto di locazione"),
        MappedField("documenti", "doc.contratto_locazione", True, confidence=conf, label="Contratto locazione caricato"),
    ]
    if ts.get("address"):
        out.append(MappedField("casa", "casa.indirizzo", ts["address"], confidence=conf, label="Indirizzo casa"))
    end = _date_by_role(reasoning, "contract_end")
    if end:
        out.append(MappedField("casa", "casa.affitto_scadenza", end["value"], confidence=float(end.get("confidence") or conf), label="Scadenza contratto"))
    return out


def map_mutuo(reasoning: Dict[str, Any]) -> List[MappedField]:
    ts = reasoning.get("type_specific") or {}
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("casa", "casa.mutuo", True, confidence=conf, label="Mutuo attivo"),
        MappedField("documenti", "doc.mutuo", True, confidence=conf, label="Contratto mutuo caricato"),
    ]
    if ts.get("lender"):
        out.append(MappedField("casa", "casa.mutuo_istituto", ts["lender"], confidence=conf, label="Istituto mutuo"))
    if ts.get("principal_amount"):
        out.append(MappedField("casa", "casa.mutuo_importo", ts["principal_amount"], confidence=conf, label="Importo mutuo"))
    if ts.get("monthly_installment"):
        out.append(MappedField("casa", "casa.mutuo_rata", ts["monthly_installment"], confidence=conf, label="Rata mensile"))
    if ts.get("end_date"):
        out.append(MappedField("casa", "casa.mutuo_scadenza", ts["end_date"], confidence=conf, label="Fine mutuo"))
    elif ts.get("property_address"):
        out.append(MappedField("casa", "casa.indirizzo", ts["property_address"], confidence=conf, label="Indirizzo immobile"))
    return out


def map_bolletta(reasoning: Dict[str, Any]) -> List[MappedField]:
    ts = reasoning.get("type_specific") or {}
    conf = float(reasoning.get("confidence") or 0.5)
    # Energy/utility contract is fairly grounded; ownership/rental is only a hypothesis.
    hyp_conf = min(0.45, conf * 0.6)
    out: List[MappedField] = [
        MappedField("casa", "casa.utenze", True, confidence=conf, label="Utenze collegate"),
        MappedField(
            "casa", "casa.contratto_energia", True,
            confidence=min(conf, 0.75), label="Contratto energia (ipotesi da bolletta)",
            status="suggested",
        ),
        MappedField(
            "casa", "casa.ownership_hypothesis", "owned_or_rental_unknown",
            confidence=hyp_conf,
            label="Ipotesi possesso abitazione (da confermare)",
            status="suggested",
        ),
        MappedField("documenti", "doc.bolletta", True, confidence=conf, label="Bolletta caricata"),
    ]
    if ts.get("supplier"):
        out.append(MappedField("casa", "casa.bolletta_fornitore", ts["supplier"], confidence=conf, label="Fornitore"))
    if ts.get("utility_type"):
        out.append(MappedField("casa", "casa.bolletta_tipo", ts["utility_type"], confidence=conf, label="Tipo utenza"))
    if ts.get("amount_total"):
        out.append(MappedField("casa", "casa.bolletta_importo", ts["amount_total"], confidence=conf, label="Importo bolletta"))
    if ts.get("due_date"):
        out.append(MappedField("casa", "casa.bolletta_scadenza", ts["due_date"], confidence=conf, label="Scadenza bolletta"))
    if ts.get("address"):
        out.append(MappedField("casa", "casa.indirizzo", ts["address"], confidence=conf, label="Indirizzo casa"))
    return out


def map_libretto(reasoning: Dict[str, Any]) -> List[MappedField]:
    ts = reasoning.get("type_specific") or {}
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("auto", "auto.owned", True, confidence=conf, label="Proprietà auto"),
        MappedField("documenti", "doc.libretto", True, confidence=conf, label="Libretto caricato"),
    ]
    if ts.get("plate"):
        out.append(MappedField("auto", "auto.targa", ts["plate"], confidence=conf, label="Targa"))
    if ts.get("brand") or ts.get("model"):
        modello = " ".join(x for x in (ts.get("brand"), ts.get("model")) if x)
        out.append(MappedField("auto", "auto.modello", modello, confidence=conf, label="Marca e modello"))
    if ts.get("vin"):
        out.append(MappedField("auto", "auto.telaio", ts["vin"], confidence=conf, label="Numero di telaio"))
    if ts.get("first_registration_date"):
        out.append(MappedField("auto", "auto.immatricolazione", ts["first_registration_date"], confidence=conf, label="Data immatricolazione"))
    return out


def map_polizza(reasoning: Dict[str, Any]) -> List[MappedField]:
    ts = reasoning.get("type_specific") or {}
    conf = float(reasoning.get("confidence") or 0.5)
    doc_type = reasoning.get("document_type") or "polizza"
    domain = "auto" if doc_type == "polizza_auto" else ("casa" if doc_type == "polizza_casa" else "assicurazioni")
    out: List[MappedField] = [
        MappedField("documenti", f"doc.{doc_type}", True, confidence=conf, label="Polizza caricata"),
    ]
    if doc_type == "polizza_auto":
        out.append(MappedField("auto", "auto.assicurazione", True, confidence=conf, label="Auto assicurata"))
    elif doc_type == "polizza_casa":
        out.append(MappedField("casa", "casa.assicurazione", True, confidence=conf, label="Casa assicurata"))
    else:
        out.append(MappedField("assicurazioni", "assicurazioni.tipo", ts.get("coverage_type") or doc_type, confidence=conf, label="Tipo polizza"))
    if ts.get("company"):
        out.append(MappedField(domain, f"{domain}.polizza_compagnia", ts["company"], confidence=conf, label="Compagnia"))
    if ts.get("end_date"):
        key = "auto.assicurazione_scadenza" if doc_type == "polizza_auto" else (
            "casa.polizza_scadenza" if doc_type == "polizza_casa" else "assicurazioni.scadenza"
        )
        out.append(MappedField(domain, key, ts["end_date"], confidence=conf, label="Scadenza polizza"))
    return out


def map_prestito_auto(reasoning: Dict[str, Any]) -> List[MappedField]:
    ts = reasoning.get("type_specific") or {}
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("auto", "auto.finanziamento", True, confidence=conf, label="Finanziamento auto attivo"),
        MappedField("documenti", "doc.prestito_auto", True, confidence=conf, label="Contratto finanziamento caricato"),
    ]
    if ts.get("monthly_installment"):
        out.append(MappedField("auto", "auto.finanziamento_rata", ts["monthly_installment"], confidence=conf, label="Rata mensile"))
    if ts.get("end_date"):
        out.append(MappedField("auto", "auto.finanziamento_scadenza", ts["end_date"], confidence=conf, label="Fine finanziamento"))
    return out


def map_piano_di_studi(reasoning: Dict[str, Any]) -> List[MappedField]:
    ts = reasoning.get("type_specific") or {}
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("studio", "studio.active", True, confidence=conf, label="Percorso di studio attivo"),
        MappedField("documenti", "doc.piano_di_studi", True, confidence=conf, label="Piano di studi caricato"),
    ]
    if ts.get("institution"):
        out.append(MappedField("studio", "studio.universita", ts["institution"], confidence=conf, label="Istituto"))
    if ts.get("course_name"):
        out.append(MappedField("studio", "studio.corso", ts["course_name"], confidence=conf, label="Corso di studi"))
    if ts.get("exams"):
        out.append(MappedField("studio", "studio.esami", ts["exams"], confidence=conf, label="Esami del piano"))
    if ts.get("academic_year"):
        out.append(MappedField("studio", "studio.anno_accademico", ts["academic_year"], confidence=conf, label="Anno accademico"))
    return out


def map_dispensa(reasoning: Dict[str, Any]) -> List[MappedField]:
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("studio", "studio.active", True, confidence=conf, label="Percorso di studio attivo"),
        MappedField("documenti", "doc.dispensa", True, confidence=conf, label="Dispensa caricata"),
    ]
    subj = _entity_value(reasoning, "subject") or _entity_value(reasoning, "materia")
    if subj:
        out.append(MappedField("studio", "studio.esame", subj, confidence=conf, label="Materia"))
    return out


def map_calendario_esami(reasoning: Dict[str, Any]) -> List[MappedField]:
    ts = reasoning.get("type_specific") or {}
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("studio", "studio.active", True, confidence=conf, label="Percorso di studio attivo"),
        MappedField("documenti", "doc.calendario_esami", True, confidence=conf, label="Calendario esami caricato"),
    ]
    if ts.get("exams"):
        out.append(MappedField("studio", "studio.esami", ts["exams"], confidence=conf, label="Esami calendario"))
    deadline = _date_by_role(reasoning, "deadline")
    if deadline:
        out.append(MappedField("studio", "studio.data_esame", deadline["value"], confidence=float(deadline.get("confidence") or conf), label="Prossimo esame"))
    return out


def map_generic_admin(reasoning: Dict[str, Any]) -> List[MappedField]:
    conf = float(reasoning.get("confidence") or 0.4)
    doc_type = reasoning.get("document_type") or "documento"
    out: List[MappedField] = [
        MappedField("documenti", f"doc.{doc_type}", True, confidence=conf, label="Documento caricato"),
    ]
    total = _amount_by_role(reasoning, "total")
    if total:
        out.append(MappedField("finanze", "finanze.importo_documento", total["value"], confidence=float(total.get("confidence") or conf), label="Importo"))
    deadline = _date_by_role(reasoning, "deadline")
    if deadline:
        out.append(MappedField("finanze", "finanze.scadenza_documento", deadline["value"], confidence=float(deadline.get("confidence") or conf), label="Scadenza"))
    return out


def map_contratto_luce(reasoning: Dict[str, Any]) -> List[MappedField]:
    base = map_bolletta(reasoning)
    conf = float(reasoning.get("confidence") or 0.5)
    base.append(MappedField(
        "documenti", "doc.contratto_luce", True, confidence=conf, label="Contratto luce caricato",
    ))
    return base


def map_contratto_telefono(reasoning: Dict[str, Any]) -> List[MappedField]:
    conf = float(reasoning.get("confidence") or 0.5)
    ts = reasoning.get("type_specific") or {}
    out: List[MappedField] = [
        MappedField("amministrativo", "amministrativo.contratto_telefono", True, confidence=conf, label="Contratto telefono"),
        MappedField("documenti", "doc.contratto_telefono", True, confidence=conf, label="Contratto telefono caricato"),
    ]
    supplier = ts.get("supplier") or _entity_value(reasoning, "supplier")
    if supplier:
        out.append(MappedField("amministrativo", "amministrativo.telco", supplier, confidence=conf, label="Operatore"))
    return out


def map_busta_paga(reasoning: Dict[str, Any]) -> List[MappedField]:
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("finanze", "finanze.busta_paga", True, confidence=conf, label="Busta paga caricata"),
        MappedField("documenti", "doc.busta_paga", True, confidence=conf, label="Busta paga"),
    ]
    total = _amount_by_role(reasoning, "total")
    if total:
        out.append(MappedField("finanze", "finanze.stipendio", total["value"], confidence=float(total.get("confidence") or conf), label="Retribuzione", status="suggested"))
    return out


def map_verbale(reasoning: Dict[str, Any]) -> List[MappedField]:
    conf = float(reasoning.get("confidence") or 0.5)
    out: List[MappedField] = [
        MappedField("studio", "studio.active", True, confidence=conf, label="Percorso di studio attivo"),
        MappedField("documenti", "doc.verbale", True, confidence=conf, label="Verbale esame caricato"),
    ]
    subj = _entity_value(reasoning, "subject") or _entity_value(reasoning, "materia")
    if subj:
        out.append(MappedField("studio", "studio.esame", subj, confidence=conf, label="Materia verbale"))
    return out


MAPPERS = {
    "rogito": map_rogito,
    "contratto_locazione": map_contratto_locazione,
    "mutuo": map_mutuo,
    "bolletta": map_bolletta,
    "contratto_luce": map_contratto_luce,
    "contratto_telefono": map_contratto_telefono,
    "libretto": map_libretto,
    "polizza_auto": map_polizza,
    "polizza_casa": map_polizza,
    "polizza": map_polizza,
    "prestito_auto": map_prestito_auto,
    "piano_di_studi": map_piano_di_studi,
    "dispensa": map_dispensa,
    "calendario_esami": map_calendario_esami,
    "verbale": map_verbale,
    "busta_paga": map_busta_paga,
    "contratto": map_generic_admin,
    "comunicazione": map_generic_admin,
    "fattura": map_generic_admin,
    "ricevuta": map_generic_admin,
    "altro": map_generic_admin,
}


def map_document_reasoning(reasoning: Dict[str, Any]) -> List[MappedField]:
    doc_type = reasoning.get("document_type") or "altro"
    mapper = MAPPERS.get(doc_type, map_generic_admin)
    return mapper(reasoning)
