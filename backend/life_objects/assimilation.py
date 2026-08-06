"""Real Merge / Assimilation Engine.

When identity is confirmed (LINK_CONFIRMED / LINK_PROBABLE):
- mutuo UPDATES HOME.state (lender, monthly_installment, loan_number…)
- bolletta UPDATES HOME.state (utility_supplier, utility_amount, utility_due_date, POD…)
Object grows; do NOT accumulate merge_proposals for clear same-object updates.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from life_objects.link_states import LinkState, should_assimilate
from life_objects.models import LifeObject, now_iso
from life_objects.property_registry import map_properties, merge_mapped_into

# Doc types that assimilate into HOME (not separate MORTGAGE/UTILITY objects when HOME exists)
HOME_ASSIMILATING_DOCS: Set[str] = {
    "mutuo", "bolletta", "contratto_luce", "polizza_casa", "contratto_locazione",
    "assicurazione_casa", "fotovoltaico", "cambio_fornitore",
}

MORTGAGE_STATE_FIELDS = (
    "lender", "monthly_installment", "loan_number", "interest_rate", "mortgage_years_left",
)
UTILITY_STATE_FIELDS = (
    "utility_supplier", "utility_amount", "utility_due_date", "utility_type",
    "consumption", "contract_code", "pod", "pdr",
)
INSURANCE_STATE_FIELDS = (
    "insurance_company", "policy_number", "coverage", "expiry",
)


def document_assimilates_into_home(document_type: str) -> bool:
    return str(document_type or "").strip().lower() in HOME_ASSIMILATING_DOCS


def assimilation_kind(document_type: str) -> str:
    dt = str(document_type or "").strip().lower()
    if dt == "mutuo":
        return "mortgage"
    if dt in ("bolletta", "contratto_luce", "cambio_fornitore"):
        return "utility"
    if dt in ("polizza_casa", "assicurazione_casa"):
        return "insurance"
    if dt == "fotovoltaico":
        return "solar"
    if dt in ("rogito", "contratto_locazione"):
        return "identity"
    return "generic"


def assimilate_document_into_object(
    obj: LifeObject,
    *,
    document_type: str,
    properties_delta: Optional[Dict[str, Any]],
    document_id: Optional[str] = None,
    link_state: LinkState = "LINK_CONFIRMED",
) -> Dict[str, Any]:
    """Apply document facts into object identity/state. Returns assimilation meta."""
    if not should_assimilate(link_state):
        return {
            "assimilated": False,
            "reason": f"link_state={link_state}",
            "kind": assimilation_kind(document_type),
        }

    mapped = map_properties(properties_delta or {})
    kind = assimilation_kind(document_type)
    id_out, st_out, props_out = merge_mapped_into(
        identity=dict(obj.identity or {}),
        state=dict(obj.state or {}),
        properties=dict(obj.properties or {}),
        delta=mapped,
    )

    # Track assimilation ledger on state (non-destructive)
    ledger = dict(st_out.get("_assimilation") or {})
    if not isinstance(ledger, dict):
        ledger = {}
    kinds: List[str] = list(ledger.get("kinds") or [])
    if kind not in kinds:
        kinds.append(kind)
    docs: List[str] = list(ledger.get("document_ids") or [])
    if document_id and document_id not in docs:
        docs.append(document_id)
    ledger.update({
        "kinds": kinds,
        "document_ids": docs,
        "last_kind": kind,
        "last_document_id": document_id,
        "last_at": now_iso(),
        "last_link_state": link_state,
    })
    if kind == "mortgage":
        ledger["mortgage_assimilated"] = True
    if kind == "utility":
        ledger["utility_assimilated"] = True
    if kind == "insurance":
        ledger["insurance_assimilated"] = True
    st_out["_assimilation"] = ledger

    # Explicit mirrors for health/gap engines
    if kind == "mortgage":
        st_out["mortgage_assimilated"] = True
    if kind == "utility":
        st_out["utility_assimilated"] = True

    obj.identity = id_out
    obj.state = st_out
    obj.properties = props_out

    # Clear quiet/probable merge piles when assimilating confirmed update
    if link_state == "LINK_CONFIRMED" and obj.merge_proposals:
        obj.merge_proposals = [
            p for p in (obj.merge_proposals or [])
            if isinstance(p, dict) and p.get("link_state") == "REAL_CONFLICT"
        ]

    applied_fields = [k for k in mapped.keys() if mapped.get(k) not in (None, "", [], {})]
    return {
        "assimilated": True,
        "kind": kind,
        "fields": applied_fields,
        "mortgage_assimilated": bool(st_out.get("mortgage_assimilated")),
        "utility_assimilated": bool(st_out.get("utility_assimilated")),
        "document_id": document_id,
        "link_state": link_state,
    }


def mortgage_assimilated(obj: LifeObject) -> bool:
    st = obj.state or {}
    if st.get("mortgage_assimilated"):
        return True
    ledger = st.get("_assimilation") or {}
    if isinstance(ledger, dict) and ledger.get("mortgage_assimilated"):
        return True
    return bool(st.get("lender") or st.get("monthly_installment") or st.get("loan_number"))


def utility_assimilated(obj: LifeObject) -> bool:
    st = obj.state or {}
    if st.get("utility_assimilated"):
        return True
    ledger = st.get("_assimilation") or {}
    if isinstance(ledger, dict) and ledger.get("utility_assimilated"):
        return True
    return bool(
        st.get("utility_supplier")
        or st.get("supplier")
        or st.get("utility_amount")
        or st.get("amount_total")
    )


def open_real_conflicts(obj: LifeObject) -> int:
    n = 0
    for p in obj.merge_proposals or []:
        if not isinstance(p, dict):
            continue
        if p.get("link_state") == "REAL_CONFLICT" or p.get("conflict") is True:
            n += 1
    return n
