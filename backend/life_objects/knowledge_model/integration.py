"""Wire Knowledge Model into assimilation / Life Object upsert (non-breaking)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_objects.knowledge_model.decisions import (
    filter_suppressed_questions,
    filter_suppressed_suggestions,
    propose_decision,
)
from life_objects.knowledge_model.facts import add_fact, current_fact_for_type
from life_objects.knowledge_model.hypotheses import add_hypothesis
from life_objects.knowledge_model.memory_events import (
    append_memory,
    narrative_for_document,
    narrative_for_supplier_change,
)
from life_objects.knowledge_model.migration import migrate_identity_state_to_knowledge
from life_objects.knowledge_model.models import (
    KnowledgeDecision,
    KnowledgeFact,
    KnowledgeHypothesis,
    now_iso,
)

# Fact types written from verified / high-confidence document paths
_VERIFIED_FACT_KEYS = frozenset({
    "address", "property_address", "cadastral_data", "cadastral",
    "pod", "pdr", "plate", "vin", "brand", "model",
    "lender", "loan_number", "monthly_installment", "interest_rate",
    "utility_supplier", "supplier", "utility_type", "utility_amount",
    "utility_due_date", "amount_total", "contract_code",
    "insurance_company", "policy_number", "coverage", "expiry",
    "institution", "employer",
})

_SUPPLIER_KEYS = frozenset({"utility_supplier", "supplier"})

# Confidence thresholds
FACT_CONFIDENCE_MIN = 0.70
HYPOTHESIS_BELOW = 0.70


def _coerce_lists(obj) -> None:
    """Ensure LifeObject has typed knowledge lists (in-place)."""
    from life_objects.knowledge_model.models import (
        KnowledgeDecision,
        KnowledgeFact,
        KnowledgeHypothesis,
        MemoryEvent,
    )

    def _as(cls, items):
        out = []
        for x in items or []:
            if isinstance(x, cls):
                out.append(x)
            elif isinstance(x, dict):
                out.append(cls.model_validate(x))
        return out

    obj.facts = _as(KnowledgeFact, getattr(obj, "facts", None) or [])
    obj.hypotheses = _as(KnowledgeHypothesis, getattr(obj, "hypotheses", None) or [])
    obj.decisions = _as(KnowledgeDecision, getattr(obj, "decisions", None) or [])
    obj.memory = _as(MemoryEvent, getattr(obj, "memory", None) or [])


def ensure_knowledge_migrated(obj) -> Dict[str, Any]:
    """One-shot non-destructive migration from identity/state."""
    _coerce_lists(obj)
    if getattr(obj, "knowledge_migrated", False):
        return {"skipped": True, "reason": "already_migrated"}
    # Migrate if we have identity/state but empty facts
    if obj.facts and len(obj.facts) > 0:
        obj.knowledge_migrated = True
        return {"skipped": True, "reason": "facts_present"}
    bag_f, bag_h, meta = migrate_identity_state_to_knowledge(
        identity=dict(obj.identity or {}),
        state=dict(obj.state or {}),
        properties=dict(obj.properties or {}),
        facts=list(obj.facts or []),
        hypotheses=list(obj.hypotheses or []),
        life_object_id=obj.id,
    )
    obj.facts = bag_f
    obj.hypotheses = bag_h
    obj.knowledge_migrated = True
    return meta


def _is_verified_path(
    *,
    source: str,
    confidence: float,
    link_state: Optional[str],
    verified: bool,
) -> bool:
    """True → write Fact; False → Hypothesis.

    LINK_CONFIRMED and LINK_PROBABLE are quiet assimilate paths (backend already
    merges into state) → Facts when confidence is high enough.
    LINK_UNCERTAIN / REAL_CONFLICT → Hypotheses only.
    """
    if verified:
        return True
    if source in ("user", "manual", "api", "calendar", "api_create"):
        return confidence >= 0.6
    if source == "document":
        if link_state in ("LINK_UNCERTAIN", "REAL_CONFLICT"):
            return False
        # LINK_CONFIRMED / LINK_PROBABLE / None → Fact when confident
        if confidence >= FACT_CONFIDENCE_MIN:
            return True
    return False


def ingest_properties_into_knowledge(
    obj,
    *,
    properties: Optional[Dict[str, Any]],
    source: str,
    source_id: Optional[str] = None,
    document_type: str = "",
    confidence: float = 0.5,
    link_state: Optional[str] = None,
    verified: bool = False,
    reason_summary: str = "",
) -> Dict[str, Any]:
    """Write Facts (verified path) or Hypotheses (ambiguous). Update memory."""
    _coerce_lists(obj)
    ensure_knowledge_migrated(obj)

    props = {k: v for k, v in (properties or {}).items() if v not in (None, "", [], {})}
    if not props:
        return {"facts_written": 0, "hypotheses_written": 0}

    verified_path = _is_verified_path(
        source=source, confidence=confidence, link_state=link_state, verified=verified,
    )
    facts_n = 0
    hyps_n = 0
    supplier_changed = None

    for key, value in props.items():
        if key.startswith("_") or key in ("document_type", "domain"):
            continue
        ftype = "utility_supplier" if key == "supplier" else key
        if ftype not in _VERIFIED_FACT_KEYS and key not in _VERIFIED_FACT_KEYS:
            # Unknown keys → hypothesis only (never invent Fact)
            if not verified_path or confidence < FACT_CONFIDENCE_MIN:
                obj.hypotheses = add_hypothesis(
                    obj.hypotheses,
                    KnowledgeHypothesis(
                        type=ftype,
                        value=value,
                        confidence=min(confidence, 0.55),
                        reason=reason_summary or "Campo ambiguo da documento",
                        evidence=[source_id] if source_id else [source],
                        question_to_confirm=f"Confermi {ftype} = {value}?",
                        source=source,
                        source_id=source_id,
                        life_object_id=obj.id,
                    ),
                )
                hyps_n += 1
            continue

        if verified_path:
            old = current_fact_for_type(obj.facts, ftype)
            if old and ftype in _SUPPLIER_KEYS and str(old.value) != str(value):
                supplier_changed = (old.value, value)
            fact = KnowledgeFact(
                type=ftype,
                value=value,
                source=source,
                source_id=source_id,
                confidence=max(confidence, FACT_CONFIDENCE_MIN),
                verified=True,
                verified_by="document" if source == "document" else source,
                verified_at=now_iso(),
                origin="document" if source == "document" else "manual",  # type: ignore[arg-type]
                explanation=reason_summary or f"Confermato da {source}",
                life_object_id=obj.id,
            )
            obj.facts = add_fact(obj.facts, fact, supersede_same_type=True)
            facts_n += 1
        else:
            obj.hypotheses = add_hypothesis(
                obj.hypotheses,
                KnowledgeHypothesis(
                    type=ftype,
                    value=value,
                    confidence=min(confidence, HYPOTHESIS_BELOW - 0.01),
                    reason=reason_summary or f"Ipotesi da {source} (non verificato)",
                    evidence=[source_id] if source_id else [source],
                    missing_information=["conferma utente"] if confidence < 0.5 else [],
                    question_to_confirm=f"Confermi che {ftype} è {value}?",
                    source=source,
                    source_id=source_id,
                    life_object_id=obj.id,
                ),
            )
            hyps_n += 1

    # Narrative memory for document assimilation
    if document_type:
        mem = narrative_for_document(
            document_type=document_type,
            properties=props,
            object_title=obj.title or "",
        )
        mem.life_object_id = obj.id
        mem.source = source
        mem.source_id = source_id
        mem.meta["dedupe_key"] = f"{document_type}:{source_id or ''}:{mem.kind}"
        obj.memory = append_memory(
            obj.memory, mem, dedupe_key=mem.meta.get("dedupe_key"),
        )

    if supplier_changed:
        old_s, new_s = supplier_changed
        sm = narrative_for_supplier_change(
            old_supplier=old_s, new_supplier=new_s, object_title=obj.title or "",
        )
        sm.life_object_id = obj.id
        sm.source = source
        sm.source_id = source_id
        obj.memory = append_memory(obj.memory, sm)

    return {
        "facts_written": facts_n,
        "hypotheses_written": hyps_n,
        "verified_path": verified_path,
        "supplier_changed": bool(supplier_changed),
    }


def elevate_suggestions_to_decisions(obj, titles: List[str], *, ai_reasoning: str = "") -> int:
    """Important suggestions → Decision records (respect never_ask_again)."""
    _coerce_lists(obj)
    created = 0
    for title in titles or []:
        if not title:
            continue
        res = propose_decision(
            obj.decisions,
            KnowledgeDecision(
                life_object_id=obj.id,
                title=str(title),
                reason=str(title),
                benefit="",
                risk="",
                ai_reasoning=ai_reasoning or "Suggerimento da documento/reasoner",
                outcome="pending",
                kind="suggestion",
            ),
        )
        obj.decisions = res["decisions"]
        if res.get("created"):
            created += 1
    return created


def apply_never_ask_filters(obj) -> None:
    """Quietly drop re-proposed suggestions/questions blocked by never_ask_again."""
    _coerce_lists(obj)
    from life_objects.models import PendingQuestion, SuggestedAction

    kept_actions = []
    for a in obj.suggested_actions or []:
        title = a.title if hasattr(a, "title") else (a.get("title") if isinstance(a, dict) else "")
        filtered = filter_suppressed_suggestions(obj.decisions, [str(title or "")])
        if filtered:
            kept_actions.append(a if isinstance(a, SuggestedAction) else SuggestedAction.model_validate(a))
    obj.suggested_actions = kept_actions

    obj.pending_questions = filter_suppressed_questions(
        obj.decisions, list(obj.pending_questions or []),
    )
    # Coerce back to PendingQuestion
    coerced = []
    for q in obj.pending_questions:
        if isinstance(q, PendingQuestion):
            coerced.append(q)
        elif isinstance(q, dict):
            coerced.append(PendingQuestion.model_validate(q))
    obj.pending_questions = coerced
