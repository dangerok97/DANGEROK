"""Narrative memory — tellable life story of the object (not technical log)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_objects.knowledge_model.models import MemoryEvent, now_iso


# Map document / assimilation kinds → tellable memory kinds + timeline groups
_DOC_MEMORY = {
    "rogito": ("purchase", "purchase_path", "Acquisto immobile"),
    "contratto_locazione": ("lease", "purchase_path", "Contratto di locazione"),
    "mutuo": ("mortgage", "mortgage_path", "Mutuo acceso"),
    "surroga": ("mortgage_surrogacy", "mortgage_path", "Surroga mutuo"),
    "estinzione_mutuo": ("mortgage_extinction", "mortgage_path", "Estinzione mutuo"),
    "bolletta": ("utility_bill", "utility_path", "Bolletta registrata"),
    "contratto_luce": ("utility_contract", "utility_path", "Contratto utenza"),
    "cambio_fornitore": ("supplier_change", "utility_path", "Cambio fornitore"),
    "polizza_casa": ("insurance", "insurance_path", "Assicurazione casa"),
    "assicurazione_casa": ("insurance", "insurance_path", "Assicurazione casa"),
    "fotovoltaico": ("solar", "solar_path", "Impianto fotovoltaico"),
    "libretto": ("vehicle_identity", "vehicle_path", "Libretto veicolo"),
    "polizza_auto": ("vehicle_insurance", "vehicle_path", "Polizza auto"),
}


def memory_kind_for_document(document_type: str) -> tuple:
    dt = str(document_type or "").strip().lower()
    return _DOC_MEMORY.get(dt, ("life_event", "general", "Aggiornamento"))


def append_memory(
    memory: List[MemoryEvent],
    event: MemoryEvent,
    *,
    max_entries: int = 300,
    dedupe_key: Optional[str] = None,
) -> List[MemoryEvent]:
    bag = list(memory or [])
    if dedupe_key:
        for m in bag:
            if (m.meta or {}).get("dedupe_key") == dedupe_key:
                return bag
    if not event.at:
        event.at = now_iso()
    bag.append(event)
    return bag[-max_entries:]


def narrative_for_document(
    *,
    document_type: str,
    properties: Optional[Dict[str, Any]] = None,
    object_title: str = "",
) -> MemoryEvent:
    kind, group, title = memory_kind_for_document(document_type)
    props = properties or {}
    bits: List[str] = []
    if kind == "purchase":
        addr = props.get("address") or props.get("property_address") or object_title
        bits.append(f"Hai acquisito {addr}." if addr else "Hai registrato un acquisto immobiliare.")
    elif kind == "mortgage":
        lender = props.get("lender") or "la banca"
        rata = props.get("monthly_installment")
        bits.append(f"Hai collegato un mutuo con {lender}.")
        if rata:
            bits.append(f"Rata indicata: {rata}.")
    elif kind in ("utility_bill", "utility_contract"):
        supplier = props.get("utility_supplier") or props.get("supplier")
        bits.append(
            f"Bolletta/utenza da {supplier}." if supplier else "Hai registrato una bolletta."
        )
    elif kind == "supplier_change":
        supplier = props.get("utility_supplier") or props.get("supplier")
        bits.append(
            f"Hai cambiato fornitore: ora {supplier}." if supplier else "Hai cambiato fornitore energia."
        )
    elif kind == "insurance":
        company = props.get("insurance_company") or props.get("company")
        bits.append(
            f"Assicurazione con {company}." if company else "Hai aggiunto un'assicurazione."
        )
    elif kind == "solar":
        bits.append("Hai aggiunto un impianto fotovoltaico.")
    elif kind == "mortgage_surrogacy":
        bits.append("Hai surrogato il mutuo.")
    elif kind == "mortgage_extinction":
        bits.append("Hai estinto il mutuo.")
    else:
        bits.append(title + (f" — {object_title}" if object_title else ""))

    return MemoryEvent(
        kind=kind,
        title=title,
        narrative=" ".join(bits).strip(),
        timeline_group=group,
        meta={"document_type": document_type, "dedupe_key": None},
    )


def narrative_for_supplier_change(
    *,
    old_supplier: Any,
    new_supplier: Any,
    object_title: str = "",
) -> MemoryEvent:
    return MemoryEvent(
        kind="supplier_change",
        title="Cambio fornitore energia",
        narrative=(
            f"Il fornitore energia di {object_title or 'questa casa'} "
            f"è passato da {old_supplier} a {new_supplier}."
        ),
        timeline_group="utility_path",
        meta={"old_supplier": old_supplier, "new_supplier": new_supplier},
    )


def serialize_memory(memory: List[MemoryEvent]) -> List[Dict[str, Any]]:
    return [m.model_dump() for m in (memory or [])]
