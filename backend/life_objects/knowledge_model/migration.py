"""Non-destructive migration of identity/state into facts/hypotheses."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from life_objects.knowledge_model.facts import add_fact, current_fact_for_type
from life_objects.knowledge_model.hypotheses import add_hypothesis
from life_objects.knowledge_model.models import KnowledgeFact, KnowledgeHypothesis, now_iso

# Identity keys → high-confidence Facts (object-defining, already persisted)
_IDENTITY_FACT_TYPES = (
    "address", "property_address", "cadastral_data", "cadastral",
    "pod", "pdr", "plate", "vin", "brand", "model",
    "institution", "employer", "company_vat", "iban_last4",
)

# Clear state fields with known values → Facts (migrated from existing state)
_STATE_FACT_TYPES = (
    "lender", "loan_number", "monthly_installment", "interest_rate",
    "utility_supplier", "supplier", "utility_type", "utility_amount",
    "insurance_company", "policy_number", "contract_code",
)


def migrate_identity_state_to_knowledge(
    *,
    identity: Dict[str, Any],
    state: Dict[str, Any],
    properties: Dict[str, Any],
    facts: List[KnowledgeFact],
    hypotheses: List[KnowledgeHypothesis],
    life_object_id: str = "",
    confidence_floor: float = 0.75,
) -> Tuple[List[KnowledgeFact], List[KnowledgeHypothesis], Dict[str, Any]]:
    """Fill facts/hypotheses from identity/state where clear. Never deletes."""
    bag_f = list(facts or [])
    bag_h = list(hypotheses or [])
    migrated: List[str] = []

    def _take(bucket: Dict[str, Any], key: str) -> Any:
        v = bucket.get(key)
        if v in (None, "", [], {}):
            return None
        return v

    # Identity → Facts (verified migration)
    for key in _IDENTITY_FACT_TYPES:
        val = _take(identity, key) or _take(properties, key)
        if val is None:
            continue
        if current_fact_for_type(bag_f, key):
            continue
        bag_f = add_fact(
            bag_f,
            KnowledgeFact(
                type=key,
                value=val,
                source="migration",
                confidence=confidence_floor,
                verified=True,
                verified_by="system",
                verified_at=now_iso(),
                origin="migration",
                explanation="Migrato da identity/properties esistenti",
                life_object_id=life_object_id,
            ),
            supersede_same_type=True,
        )
        migrated.append(f"fact:{key}")

    # Clear state → Facts
    for key in _STATE_FACT_TYPES:
        val = _take(state, key) or _take(properties, key)
        if val is None:
            continue
        # Canonicalize supplier alias
        ftype = "utility_supplier" if key == "supplier" else key
        if current_fact_for_type(bag_f, ftype):
            continue
        bag_f = add_fact(
            bag_f,
            KnowledgeFact(
                type=ftype,
                value=val,
                source="migration",
                confidence=confidence_floor,
                verified=True,
                verified_by="system",
                verified_at=now_iso(),
                origin="migration",
                explanation="Migrato da state/properties esistenti",
                life_object_id=life_object_id,
            ),
            supersede_same_type=True,
        )
        migrated.append(f"fact:{ftype}")

    # Ambiguous leftovers in properties that look uncertain → Hypothesis only
    for key, val in (properties or {}).items():
        if val in (None, "", [], {}):
            continue
        if key.startswith("_"):
            continue
        if key in _IDENTITY_FACT_TYPES or key in _STATE_FACT_TYPES or key == "supplier":
            continue
        if current_fact_for_type(bag_f, key):
            continue
        # Skip technical noise
        if key in ("document_type", "domain", "goal_id", "goal_type", "status_detail"):
            continue
        # Only create hypothesis if no active one
        bag_h = add_hypothesis(
            bag_h,
            KnowledgeHypothesis(
                type=key,
                value=val,
                confidence=0.35,
                reason="Campo presente ma non verificato come Fact (migrazione soft)",
                evidence=["properties_bag"],
                question_to_confirm=f"Confermi che {key} = {val}?",
                status="active",
                source="migration",
                life_object_id=life_object_id,
            ),
            dedupe=True,
        )
        migrated.append(f"hypothesis:{key}")

    return bag_f, bag_h, {"migrated": migrated, "count": len(migrated)}
