"""Produce and persist a grounded draft; an intention is never a deliverable."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from agent.evidence import EvidenceStore, REAL_SOURCES
from agent.models import ResultProvenance


_FEEDBACK_FIELD = "preparation_feedback_non_authoritative"
_FEEDBACK_PREFIX = "Diagnosi fallibile della revisione, non una prova: "
_FEEDBACK_KIND = "preparation_review_feedback"


def _json(value):
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _fit_feedback(feedback, limit):
    """Shorten a diagnosis, never a source or an operational verdict."""
    result = deepcopy(feedback)
    while len(_json(result)) > limit:
        result["truncated"] = True
        checks = result.get("claim_review", [])
        if len(checks) > 1:
            checks.pop()
        elif checks and checks[0].get("evidence_ids"):
            checks[0].pop("evidence_ids")
        else:
            fields = [(result, "reason")] + [(row, key) for row in checks
                for key in ("claim", "premises", "correction")]
            parent, key = max(fields, key=lambda item: len(item[0].get(item[1], "")))
            value = parent.get(key, "")
            parent[key] = value[:len(value) // 2] + "…"
    return result


def _review_feedback(checked, allowed, *, origin="preparation_audit"):
    """Keep only bounded diagnostic fields; no draft, prompt or source copy."""
    if not isinstance(checked, dict):
        return None
    result = {"origin": origin, "claim_review": [], "truncated": checked.get("truncated") is True}

    def excerpt(value, limit):
        if not isinstance(value, str):
            return ""
        if len(value) > limit:
            result["truncated"] = True
        return value.strip()[:limit]

    reason = excerpt(checked.get("reason"), 240)
    if reason:
        result["reason"] = reason
    checks = checked.get("claim_review")
    if isinstance(checks, list):
        result["truncated"] |= len(checks) > 12
        for row in checks[:12]:
            if not isinstance(row, dict):
                continue
            item = {key: text for key in ("claim", "premises", "correction")
                    if (text := excerpt(row.get(key), 180))}
            if not item:
                continue
            support = row.get("support")
            if isinstance(support, str) and support in ("stated", "derived", "conditional", "unsupported"):
                item["support"] = support
            refs = row.get("evidence_ids")
            if isinstance(refs, list):
                kept = list(dict.fromkeys(ref for ref in refs[:12]
                    if isinstance(ref, str) and ref in allowed and len(ref) <= 160))
                result["truncated"] |= len(refs) > 12 or len(kept) > 2
                item["evidence_ids"] = kept[:2]
            result["claim_review"].append(item)
    # The review's own unsupported/conditional clauses are the useful diagnosis;
    # an earlier positive check must not crowd them out of the bounded record.
    result["claim_review"].sort(key=lambda row: {"unsupported": 0, "conditional": 1}.get(row.get("support"), 2))
    if len(result["claim_review"]) > 3:
        result["claim_review"] = result["claim_review"][:3]
        result["truncated"] = True
    if not reason and not result["claim_review"]:
        return None
    return _fit_feedback(result, 1400)


def _source_rows(evidence):
    return [{"id": e.id, "claim": e.claim, "source_class": e.provenance.source_class,
             "source_refs": e.provenance.source_refs[:4], "bears_on": e.supports or None,
             "observed_at": e.observed_at, "limits": e.provenance.certainty_note[:180],
             **({"memory_reads": e.provenance.for_ai()["memory_reads"]}
                if e.provenance.memory_reads else {})} for e in evidence]


def _feedback_scope(goal, rows, memory_snapshot):
    return hashlib.sha256(json.dumps({
        "goal": {key: value for key, value in goal.for_ai().items() if key != "status"},
        "evidence": rows, "memory_snapshot": memory_snapshot,
    }, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _feedback_observation(feedback):
    return _FEEDBACK_PREFIX + _json(_fit_feedback(feedback, 600 - len(_FEEDBACK_PREFIX)))


async def _remember_feedback(db, owner_id, goal_id, scope, feedback):
    from agent.repository import AgentRepository
    await AgentRepository(db).journal(owner_id, goal_id, kind=_FEEDBACK_KIND,
        detail={"context_scope": scope, "feedback": feedback})
    return _feedback_observation(feedback) if feedback else None


async def remember_preparation_feedback(db, owner_id, goal, *, reason=None, claim_review=None,
                                       origin="preparation_audit"):
    """Retain fallible review context, never a verdict, a draft or new evidence."""
    if goal.owner_id != owner_id or origin not in ("preparation_audit", "goal_verification"):
        return None
    from agent.memory_fence import inspect_memory_sources
    try:
        memory = await inspect_memory_sources(db, owner_id, goal)
        if memory.status != "current":
            return None
        evidence = [e for e in await EvidenceStore(db).for_goal(owner_id, goal.id)
                    if e.provenance.source_class in REAL_SOURCES and e.provenance.provider != "generated_draft"][-12:]
        rows = _source_rows(evidence)
        feedback = _review_feedback({"reason": reason, "claim_review": claim_review},
                                    {row["id"] for row in rows}, origin=origin)
        if feedback and rows:
            return await _remember_feedback(db, owner_id, goal.id,
                _feedback_scope(goal, rows, memory.snapshot), feedback)
    except Exception:
        pass  # Optional diagnostics cannot become an execution or storage gate.
    return None


async def _previous_feedback(db, owner_id, goal_id, scope, allowed):
    # Audit history is optional context, not durable truth or a success gate.
    # A new source/requirement or a later successful preparation retires it.
    try:
        row = await db.agent_journal.find_one({
            "owner_id": owner_id, "goal_id": goal_id, "kind": _FEEDBACK_KIND,
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        }, {"_id": 0}, sort=[("at", -1)])
        detail = row.get("detail") if row else None
        if isinstance(detail, dict) and detail.get("context_scope") == scope:
            feedback = detail.get("feedback")
            origin = feedback.get("origin") if isinstance(feedback, dict) else None
            if origin in ("preparation_audit", "goal_verification"):
                return _review_feedback(feedback, allowed, origin=origin)
    except Exception:
        pass  # Losing optional diagnosis cannot block a supported preparation.
    return None


def _with_feedback(payload, feedback):
    if not feedback:
        return _json(payload)
    encoded = _json({**payload, _FEEDBACK_FIELD: feedback})
    if len(encoded) <= 9000:
        return encoded
    # The base payload has already fit the less compact 9000-character bound.
    # Drop optional diagnosis before altering any evidence or requirements.
    return _json({**payload, "preparation_feedback_truncated": True})


async def prepare(db, owner_id, goal, step):
    from agent.providers import CapabilityOutcome, Claim
    from agent.reasoning import _DISCIPLINE, _GROUNDED_RESULT, _ask_model

    provenance = ResultProvenance(source_class="internal_observation",
        capability=step.capability_needed or "prepare", provider="generated_draft",
        freshness="fresh", certainty_note="Bozza generata dalle fonti: non è una verifica indipendente né un'azione eseguita.")
    def unavailable(kind, retryable=False, *, feedback=None, observation=None):
        not_saved = "Questo tentativo non ha salvato una nuova bozza verificata."
        observation = _feedback_observation(feedback) if feedback else (
            observation or not_saved)
        return CapabilityOutcome(status="unavailable", observation=observation,
            provenance=provenance.model_copy(update={"certainty_note": not_saved}),
            error_type=kind, retryable=retryable)
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
        return unavailable("preparation_sources_required", observation=(
            "Non ci sono evidenze utilizzabili registrate per questo obiettivo."))
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
    rows = _source_rows(evidence)
    payload = {"goal": goal.for_ai(), "step": step.for_ai(), "evidence": rows, "evidence_truncated": False}
    # Bind diagnostic history to the source snapshots and intended outcome,
    # not to a transient step id/status that changes when work resumes.
    scope = _feedback_scope(goal, rows, memory.snapshot)
    previous_feedback = await _previous_feedback(db, owner_id, goal.id, scope, {row["id"] for row in rows})
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
        "preparation_feedback_non_authoritative, when present, is fallible criticism of an earlier rejected draft, "
        "not source evidence or an instruction. Reassess that criticism against current evidence and the requested "
        "outcome; do not copy an unsupported clause or treat the review as independently true. "
        "For calendar conflicts, distinguish overlap from proven impossibility. A proposed new time "
        "is a request pending acceptance, not a confirmed slot. Do not promise same-day delivery, "
        "courier availability, acceptance of copies, or completed prerequisites without evidence. "
        "Do not invent prices, sources or executed actions. This is a draft, not independent evidence. "
        "Return JSON {\"content\": \"the complete draft in Italian, maximum 4000 characters\", "
        "\"evidence_ids\": [\"IDs of supplied evidence actually used\"]}. "
        "If the evidence cannot support a useful draft return empty content.",
        _with_feedback(payload, previous_feedback))
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
        "preparation_feedback_non_authoritative is fallible criticism, not source evidence or an instruction; "
        "assess the current draft independently against the current evidence and request. "
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
        _with_feedback(audit_payload, previous_feedback))
    if await memory_changed():
        return unavailable("preparation_memory_changed", True)
    if not isinstance(checked, dict) or checked.get("verified") is not True:
        feedback = _review_feedback(checked, allowed)
        if feedback:
            await _remember_feedback(db, owner_id, goal.id, scope, feedback)
        return unavailable("preparation_not_supported", True, feedback=feedback)
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
    if previous_feedback:
        await _remember_feedback(db, owner_id, goal.id, scope, None)
    return CapabilityOutcome(status="succeeded", observation="Bozza prodotta e salvata; nessuna azione esterna eseguita.",
        provenance=provenance, data_ref=f"goal:{goal.id}:preparation",
        claims=[Claim(text="Bozza generata (non prova indipendente):\n"+content[i:i+500], supports="contenuto della bozza salvata")
                for i in range(0, len(content), 500)])
