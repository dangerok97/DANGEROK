"""Produce and persist a grounded draft; an intention is never a deliverable."""
import json
from agent.evidence import EvidenceStore, REAL_SOURCES
from agent.models import ResultProvenance


async def prepare(db, owner_id, goal, step):
    from agent.providers import CapabilityOutcome, Claim
    from agent.reasoning import _DISCIPLINE, _GROUNDED_RESULT, _ask_model

    provenance = ResultProvenance(source_class="internal_observation",
        capability=step.capability_needed or "prepare", provider="generated_draft",
        freshness="fresh", certainty_note="Bozza generata dalle fonti: non è una verifica indipendente né un'azione eseguita.")
    def unavailable(kind, retryable=False):
        return CapabilityOutcome(status="unavailable", observation="Non ho ancora prodotto una bozza verificabile.",
            provenance=provenance, error_type=kind, retryable=retryable)
    if goal.owner_id != owner_id:
        return unavailable("preparation_owner_mismatch")
    from agent.memory_fence import inspect_memory_sources, memory_result_current, MemorySourcesUnavailable
    try:
        memory = await inspect_memory_sources(db, owner_id, goal)
    except MemorySourcesUnavailable:
        return unavailable("preparation_source_check_unavailable", True)
    if memory.status != "current":
        return unavailable("preparation_memory_changed", True)
    async def memory_changed():
        try:
            return not await memory_result_current(db, owner_id, goal, memory.snapshot)
        except MemorySourcesUnavailable:
            return True  # A failed read cannot authorise saving the old text.
    evidence = [e for e in await EvidenceStore(db).for_goal(owner_id, goal.id)
                if e.provenance.source_class in REAL_SOURCES and e.provenance.provider != "generated_draft"][-12:]
    if not evidence:
        return unavailable("preparation_sources_required")
    from agent.calendar_conflict import overlap_draft, is_home_calendar_pair
    overlap = await overlap_draft(db, owner_id, goal, evidence)
    if await memory_changed():
        return unavailable("preparation_source_check_unavailable", True)
    if overlap:
        content, refs = overlap
        saved = await db.agent_goals.update_one(
            {"id": goal.id, "owner_id": owner_id, "status": {"$in": ["active", "waiting"]}},
            {"$set": {"prepared_text": content, "prepared_sources": refs}},
        )
        if saved.matched_count != 1:
            return unavailable("preparation_goal_unavailable")
        goal.prepared_text, goal.prepared_sources = content, refs
        provenance.provider, provenance.source_refs = "calendar_overlap_draft", refs
        return CapabilityOutcome(status="succeeded", observation="Proposta basata sugli orari attuali; nessuna azione esterna eseguita.",
            provenance=provenance, data_ref=f"goal:{goal.id}:preparation",
            claims=[Claim(text="Bozza generata (non prova indipendente):\n"+content[i:i+500], supports="contenuto della bozza salvata")
                    for i in range(0, len(content), 500)])
    if is_home_calendar_pair(goal):
        return unavailable("preparation_calendar_changed", True)
    rows = [{"id": e.id, "claim": e.claim, "source_class": e.provenance.source_class,
             "source_refs": e.provenance.source_refs[:4], "bears_on": e.supports or None,
             "observed_at": e.observed_at,
             "limits": e.provenance.certainty_note[:180],
             **({"memory_reads": e.provenance.for_ai()["memory_reads"]}
                if e.provenance.memory_reads else {})} for e in evidence]
    payload = {"goal": goal.for_ai(), "step": step.for_ai(), "evidence": rows, "evidence_truncated": False}
    while len(json.dumps(payload, ensure_ascii=False, default=str)) > 9000 and len(rows) > 1:
        rows.pop(0)
        payload["evidence_truncated"] = True
    if len(json.dumps(payload, ensure_ascii=False, default=str)) > 9000:
        return unavailable("preparation_context_too_large")
    answer = await _ask_model(_DISCIPLINE + "\n" + _GROUNDED_RESULT + "\nProduce the actual useful draft requested by the step. "
        "Never just say it is ready or describe having read a source. State the useful findings, "
        "their implications and tradeoffs. When comparable costs are supplied, show the totals "
        "including supplied fees and the difference, preserving time periods and constraints. "
        "Use only supplied evidence, preserve uncertainty and restrictions. "
        "For calendar conflicts, distinguish overlap from proven impossibility. A proposed new time "
        "is a request pending acceptance, not a confirmed slot. Do not promise same-day delivery, "
        "courier availability, acceptance of copies, or completed prerequisites without evidence. "
        "Do not invent prices, sources or executed actions. This is a draft, not independent evidence. "
        "Return JSON {\"content\": \"the complete draft in Italian, maximum 4000 characters\", "
        "\"evidence_ids\": [\"IDs of supplied evidence actually used\"]}. "
        "If the evidence cannot support a useful draft return empty content.",
        json.dumps(payload, ensure_ascii=False, default=str))
    if await memory_changed():
        return unavailable("preparation_memory_changed", True)
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
    audit_rows = list(rows)
    # The audit needs the intended deliverable, not only the draft's own
    # selection of facts. Preserve requirements whole, while carrying the
    # existing source-refresh qualification: old derived targets are not
    # independent facts or newly invented user requirements.
    prior_goal = payload["goal"]
    refresh_reason = str((prior_goal.get("current_source_situation") or {}).get("memory_refresh_reason") or "")[:300]
    request = {
        "objective": prior_goal["objective"], "desired_outcome": prior_goal["desired_outcome"],
        "success_criteria": prior_goal["success_criteria"],
        "user_clarifications_not_authority": prior_goal["user_clarifications_not_authority"],
        "step_intent": step.intent, "expected_result": step.expected_result,
        "goal_origin": goal.origin, "source_update_reason": refresh_reason or None,
        "previous_interpretation_may_be_obsolete": bool(refresh_reason),
    }
    audit_payload = {"request": request, "draft": content, "evidence": audit_rows,
                     "evidence_truncated": payload["evidence_truncated"]}
    while len(json.dumps(audit_payload, ensure_ascii=False, default=str)) > 9000:
        unused = next((index for index, row in enumerate(audit_rows) if row["id"] not in refs), None)
        if unused is None:
            # A source-consistency audit may not silently lose requirements,
            # the draft's cited claims or their read limits. This is a bounded-context
            # problem for reconsideration, not a transient retry request.
            return unavailable("preparation_context_too_large")
        audit_rows.pop(unused)
        audit_payload["evidence_truncated"] = True
    allowed = {row["id"] for row in audit_rows}
    checked = await _ask_model(_DISCIPLINE + "\n" + _GROUNDED_RESULT + "\nAudit this draft against the supplied evidence only. "
        "Check every factual claim, calculation, comparison and obligation. A person's intention "
        "or preference is NOT a contractual requirement. Verify ratios and percentage descriptions from the supplied numbers. "
        "Check every explanatory clause and conditional conclusion, not only cited IDs or numerical totals. "
        "A correct calculation does not validate a surrounding unsupported claim. The earlier draft's "
        "wording is not additional evidence. "
        "request describes the intended work; earlier model interpretations and derived targets "
        "in it are not source evidence. If previous_interpretation_may_be_obsolete is true, "
        "reconcile those earlier assumptions with current evidence, preserving the person's "
        "outcome, explicit requirements and authority limits. Do not preserve an obsolete "
        "calculated value as a requirement or invent a replacement goal. "
        "Before the verdict, return claim_review covering the actual material clauses, including "
        "qualitative consequences. In premises, identify the short source passages that establish "
        "each factual premise and distinguish any unstated assumption or category default. "
        "An evidence ID or a category label alone does not establish the premise. Test a derived "
        "claim against a counterexample compatible with ALL those source passages. If such a case "
        "remains possible, record the missing premise and make it explicitly conditional or remove "
        "the claim; do not label it established or derived. A caveat cannot turn an assumed premise "
        "into a sourced one. Make minimal corrections against request: retain supported findings, "
        "calculations, comparison differences, time horizons and limitations. Check the corrected "
        "wording too; no material clause may escape review by being grouped with supported numbers. "
        "Review proposed options too: do not relax a stated minimum requirement, invent extra "
        "resources, turn unavailable time into available time, or invent a restriction. "
        "A proposal requiring a changed condition must explicitly say so; it is not feasible "
        "under the current conditions. Do not assert probabilities or causal benefits without "
        "evidence. Preserve what is unknown instead of telling the person to rely on a guess. "
        "In a rescheduling draft, remove invented fallback services and delivery guarantees. "
        "An overlap alone does not prove attendance is impossible. Preserve explicit opening "
        "hours and original-document prerequisites. Frame unconfirmed alternatives as questions "
        "requiring the recipient's acceptance; do not imply a time is free or travel is feasible. "
        "Return one complete JSON object, positive or negative: "
        "{\"claim_review\": [{\"claim\": \"actual material clause, short\", "
        "\"evidence_ids\": [\"supplied supporting IDs\"], "
        "\"premises\": \"source passages, missing premises and any compatible counterexample, short\", "
        "\"support\": \"stated|derived|conditional|unsupported\", "
        "\"correction\": \"needed correction or limitation, empty if none\"}], "
        "\"verified\": true, \"content\": \"corrected complete draft, max 4000 characters\", "
        "\"evidence_ids\": [\"supplied IDs supporting it\"], \"reason\": \"short reason for the verdict\"}. "
        "Keep claim_review to at most 12 brief checks; group only claims that share the same "
        "premises without concealing a different condition. The verdict applies to the complete "
        "corrected content returned, not the original draft. If no useful corrected draft is "
        "supported, return verified=false, content empty, evidence_ids empty, and explain the "
        "specific missing support in claim_review and reason. Missing support for one optional "
        "claim can be handled by removing or qualifying that claim, without withholding supported work. "
        "This checks consistency with sources, not whether sources are independently true.",
        json.dumps(audit_payload, ensure_ascii=False, default=str))
    if await memory_changed():
        return unavailable("preparation_memory_changed", True)
    if not isinstance(checked, dict) or checked.get("verified") is not True:
        return unavailable("preparation_not_supported", True)
    content, refs = checked.get("content"), checked.get("evidence_ids")
    if (not isinstance(content, str) or not content.strip() or len(content) > 4000
            or not isinstance(refs, list) or not refs or len(refs) > 12
            or any(not isinstance(ref, str) or ref not in allowed for ref in refs)):
        return unavailable("preparation_review_invalid")
    content, refs = content.strip(), list(dict.fromkeys(refs))
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
