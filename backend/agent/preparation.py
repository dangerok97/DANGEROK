"""Produce and persist a grounded draft; an intention is never a deliverable."""
import json
from agent.evidence import EvidenceStore, REAL_SOURCES
from agent.models import ResultProvenance


async def prepare(db, owner_id, goal, step):
    from agent.providers import CapabilityOutcome, Claim
    from agent.reasoning import _DISCIPLINE, _ask_model

    provenance = ResultProvenance(source_class="internal_observation",
        capability=step.capability_needed or "prepare", provider="generated_draft",
        freshness="fresh", certainty_note="Bozza generata dalle fonti: non è una verifica indipendente né un'azione eseguita.")
    def unavailable(kind, retryable=False):
        return CapabilityOutcome(status="unavailable", observation="Non ho ancora prodotto una bozza verificabile.",
            provenance=provenance, error_type=kind, retryable=retryable)
    if goal.owner_id != owner_id:
        return unavailable("preparation_owner_mismatch")
    evidence = [e for e in await EvidenceStore(db).for_goal(owner_id, goal.id)
                if e.provenance.source_class in REAL_SOURCES and e.provenance.provider != "generated_draft"][-12:]
    if not evidence:
        return unavailable("preparation_sources_required")
    rows = [{"id": e.id, "claim": e.claim, "source_class": e.provenance.source_class,
             "source_refs": e.provenance.source_refs[:4], "observed_at": e.observed_at,
             "limits": e.provenance.certainty_note[:180]} for e in evidence]
    payload = {"goal": goal.for_ai(), "step": step.for_ai(), "evidence": rows, "evidence_truncated": False}
    while len(json.dumps(payload, ensure_ascii=False, default=str)) > 9000 and len(rows) > 1:
        rows.pop(0)
        payload["evidence_truncated"] = True
    if len(json.dumps(payload, ensure_ascii=False, default=str)) > 9000:
        return unavailable("preparation_context_too_large")
    answer = await _ask_model(_DISCIPLINE + "\nProduce the actual useful draft requested by the step. "
        "Never just say it is ready or describe having read a source. State the useful findings, "
        "their implications and tradeoffs. When comparable costs are supplied, show the totals "
        "including fees and the difference, preserving time periods and constraints. "
        "Use only supplied evidence, preserve uncertainty and restrictions. "
        "Do not invent prices, sources or executed actions. This is a draft, not independent evidence. "
        "Return JSON {\"content\": \"the complete draft in Italian, maximum 4000 characters\", "
        "\"evidence_ids\": [\"IDs of supplied evidence actually used\"]}. "
        "If the evidence cannot support a useful draft return empty content.",
        json.dumps(payload, ensure_ascii=False, default=str))
    if not isinstance(answer, dict):
        return unavailable("preparation_model_unavailable", True)
    content = answer.get("content")
    refs = answer.get("evidence_ids")
    allowed = {row["id"] for row in rows}
    if (not isinstance(content, str) or not content.strip() or len(content) > 4000
            or not isinstance(refs, list) or not refs or len(refs) > 12
            or any(not isinstance(ref, str) or ref not in allowed for ref in refs)):
        return unavailable("preparation_ungrounded")
    content = content.strip()
    refs = list(dict.fromkeys(refs))
    saved = await db.agent_goals.update_one(
        {"id": goal.id, "owner_id": owner_id, "status": {"$in": ["active", "waiting"]}},
        {"$set": {"prepared_text": content, "prepared_sources": refs}},
    )
    if saved.matched_count != 1:
        return unavailable("preparation_goal_unavailable")
    goal.prepared_text, goal.prepared_sources = content, refs
    provenance.source_refs = refs
    return CapabilityOutcome(status="succeeded", observation="Bozza prodotta e salvata; nessuna azione esterna eseguita.",
        provenance=provenance, data_ref=f"goal:{goal.id}:preparation",
        claims=[Claim(text="Bozza generata (non prova indipendente):\n"+content[i:i+500], supports="contenuto della bozza salvata")
                for i in range(0, len(content), 500)])
