"""Governance — validates AI decisions without replacing cognition."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Set

from conversation_engine.ai_core.context_broker import validate_context_need
from conversation_engine.ai_core.models import (
    CognitiveDecision,
    ContextNeed,
    MemoryCandidate,
    ToolCall,
    UncertaintyState,
)
from conversation_engine.ai_core.tools.registry import ToolRegistry, tool_signature
from conversation_engine.ai_core.tools.sanitize import sanitize_external_query
from context_graph.models import ContextEdgeUpdate, is_recognized_ref
from situations.models import SituationUpdate

ALLOWED_MODES = frozenset({"answer", "ask", "tool", "act", "context", "finish"})
ALLOWED_STATUS = frozenset(
    {
        "enough_information",
        "needs_user_input",
        "needs_context",
        "needs_tool",
        "ready_to_act",
    }
)
ALLOWED_STATE_PATHS = frozenset(
    {
        "active_goal.summary",
        "active_goal.desired_outcome",
        "active_goal.status",
        "note",
        "current_facts.location",
        "current_facts.until",
        "current_facts.note",
    }
)

# Side effects allowed to auto-run without user confirmation in V2.2
AUTO_READ_SIDE_EFFECTS = frozenset({"READ_ONLY"})


class GovernanceResult:
    def __init__(
        self,
        ok: bool,
        decision: Optional[CognitiveDecision] = None,
        errors: Optional[List[str]] = None,
    ):
        self.ok = ok
        self.decision = decision
        self.errors = errors or []


def validate_decision(
    raw: Any,
    *,
    tools: ToolRegistry,
    recent_tool_signatures: Optional[Set[str]] = None,
    external_query_count: int = 0,
    max_external_queries: int = 2,
    clarification_attempts: Optional[Dict[str, int]] = None,
) -> GovernanceResult:
    """Validate schema, capability existence, risk, state paths. Soft-normalize."""
    errors: List[str] = []
    if raw is None:
        return GovernanceResult(False, errors=["null_decision"])
    if isinstance(raw, CognitiveDecision):
        data = raw.model_dump()
    elif isinstance(raw, dict):
        data = dict(raw)
    else:
        return GovernanceResult(False, errors=["not_object"])

    mode = str(data.get("response_mode") or "").strip().lower()
    if mode not in ALLOWED_MODES:
        errors.append("bad_mode")
        mode = "answer"

    status = str(data.get("reasoning_status") or "enough_information").strip().lower()
    if status not in ALLOWED_STATUS:
        status = "enough_information"

    question = data.get("question")
    message = data.get("message_to_user")
    tool_call_raw = data.get("tool_call")
    context_query = data.get("context_query")
    context_need = None
    raw_need = data.get("context_need")
    if raw_need is not None:
        try:
            context_need = ContextNeed.model_validate(raw_need)
        except Exception:
            errors.append("bad_context_need")
    uncertainty = None
    if data.get("uncertainty") is not None:
        try:
            uncertainty = UncertaintyState.model_validate(data.get("uncertainty"))
        except Exception:
            errors.append("bad_uncertainty")
    tool_call: Optional[Dict[str, Any]] = None

    if mode == "ask":
        if not (question and str(question).strip()):
            if message and str(message).strip().endswith("?"):
                question = message
            else:
                errors.append("ask_without_question")
                mode = "answer"
                if not message:
                    message = "Puoi darmi un dettaglio in più?"
        tool_call = None
        # Soft-block permission-fishing for read-only tools
        if message and _asks_permission_for_readonly(str(message)):
            errors.append("passive_readonly_ask")
        ask_refs = _missing_refs(uncertainty, strategy="ask")
        repeated = [
            ref
            for ref in ask_refs
            if max(
                int((clarification_attempts or {}).get(ref, 0)),
                int(
                    (clarification_attempts or {}).get(
                        clarification_ref_key(ref), 0
                    )
                ),
            )
            >= 1
        ]
        if repeated:
            errors.append("repeated_clarification")
            mode = "answer"
            question = None
            message = (
                "Non ti richiedo di nuovo lo stesso dettaglio. Posso continuare con "
                "un'ipotesi prudente e reversibile, oppure fermarmi qui."
            )
    elif mode == "tool":
        tool_call = _normalize_tool_call(tool_call_raw)
        if not tool_call or not tool_call.get("name"):
            errors.append("tool_without_call")
            mode = "answer"
            message = message or "Non riesco a usare lo strumento richiesto."
            tool_call = None
        else:
            cap = str(tool_call["name"])
            spec = tools.get(cap)
            if not spec:
                errors.append("unknown_tool")
                mode = "answer"
                message = message or "Quella capacità non è disponibile."
                tool_call = None
            elif spec.side_effect == "CONSEQUENTIAL_WRITE":
                errors.append("consequential_write_blocked")
                mode = "answer"
                message = message or "Questa azione non è ancora consentita."
                tool_call = None
            elif spec.side_effect not in ("READ_ONLY", "REVERSIBLE_WRITE"):
                errors.append("tool_risk_blocked")
                mode = "answer"
                message = message or "Questa azione non è ancora consentita."
                tool_call = None
            else:
                args = dict(tool_call.get("arguments") or {})
                # Sanitize external web queries
                if cap == "web_search":
                    if external_query_count >= max_external_queries:
                        errors.append("external_query_budget")
                        mode = "answer"
                        message = message or (
                            "Ho già fatto le verifiche esterne consentite per questo passo. "
                            "Posso continuare con ciò che so, o dimmi pure un dettaglio in più."
                        )
                        tool_call = None
                    else:
                        clean, reason = sanitize_external_query(
                            str(args.get("query") or "")
                        )
                        if not clean:
                            errors.append(f"bad_external_query:{reason}")
                            mode = "answer"
                            message = message or (
                                "Non posso cercare con una query troppo personale o vuota. "
                                "Posso riformulare in modo più essenziale, oppure dimmi cosa ti serve."
                            )
                            tool_call = None
                        else:
                            args["query"] = clean
                            tool_call["arguments"] = args
                if tool_call is not None:
                    sig = tool_signature(cap, args)
                    if recent_tool_signatures and sig in recent_tool_signatures:
                        errors.append("duplicate_tool_call")
                        # Same-turn execution safety only. Do NOT leak internal
                        # implementation language as the user-facing answer.
                        # Loop may reuse the prior observation and continue.
                        mode = "answer"
                        message = None
                        tool_call = None
                    elif spec.availability == "disabled":
                        errors.append("tool_disabled")
                        # Still allow execute path to return NOT_CONFIGURED observation
                        # so AI can re-enter honestly — keep tool mode
                        pass
                if (
                    tool_call is not None
                    and spec.side_effect != "READ_ONLY"
                    and _blocks_side_effect(uncertainty)
                ):
                    errors.append("blocking_uncertainty_for_write")
                    tool_call = None
                    if question and str(question).strip():
                        # Same as the blocked action above: the write cannot
                        # run, but the reasoning already wrote the question
                        # that would unblock it. Replacing it with an apology
                        # tells the person there is a problem and not what
                        # would solve it, and records nothing about what ORA
                        # is waiting for.
                        mode = "ask"
                        message = str(question).strip()
                    else:
                        mode = "answer"
                        message = (
                            "Mi manca un'informazione necessaria per eseguire questa "
                            "azione in modo affidabile."
                        )
    elif mode == "context":
        if context_need is None:
            if not (context_query and str(context_query).strip()):
                context_query = (
                    data.get("user_intent_summary") or "relevant personal facts"
                )
            context_need = ContextNeed(
                query=str(context_query),
                purpose=str(
                    data.get("user_intent_summary") or "current reasoning step"
                )[:240],
            )
        context_query = context_need.query
        ok_q, reason = validate_context_need(context_need)
        if not ok_q:
            errors.append(f"blocked_context_query:{reason}")
            mode = "answer"
            message = message or (
                "Non posso caricare tutto il tuo profilo in una volta. "
                "Dimmi pure cosa ti serve in particolare."
            )
            context_query = None
            context_need = None
            tool_call = None
        else:
            tool_call = None
    else:
        tool_call = None
        if mode == "act" and _blocks_side_effect(uncertainty):
            errors.append("blocking_uncertainty_for_action")
            if question and str(question).strip():
                # The action cannot run — but the reasoning already knows what
                # would unblock it, and asking that *is* the next step. Saying
                # "I am missing something necessary" instead is the internal
                # state read out loud: the person is told there is a problem
                # and not told what would solve it. It also skips the ask path
                # entirely, so nothing records what ORA is waiting for.
                mode = "ask"
                message = str(question).strip()
            else:
                mode = "answer"
                message = (
                    "Mi manca un'informazione necessaria per procedere in modo affidabile."
                )
        if mode in ("answer", "finish", "act") and not (
            message and str(message).strip()
        ):
            if question and str(question).strip():
                mode = "ask"
            else:
                message = "Ok."
                errors.append("empty_message")

    updates = []
    for u in data.get("state_updates") or []:
        if not isinstance(u, dict):
            continue
        path = str(u.get("path") or "")
        if path not in ALLOWED_STATE_PATHS:
            errors.append(f"blocked_state_path:{path}")
            continue
        updates.append(u)

    mem_cands = []
    for m in (data.get("memory_candidates") or [])[:3]:
        try:
            mem_cands.append(MemoryCandidate.model_validate(m).model_dump())
        except Exception:
            errors.append("bad_memory_candidate")

    message = _sanitize_copy(message)
    question = _sanitize_copy(question)

    situation_update = None
    raw_situation = data.get("situation_update")
    if raw_situation is not None:
        try:
            situation_update = SituationUpdate.model_validate(raw_situation)
            if situation_update.operation == "create" and situation_update.situation_id:
                errors.append("situation_create_with_id")
                situation_update = None
            elif (
                situation_update.operation in ("update", "cancel", "resolve")
                and not situation_update.situation_id
            ):
                errors.append("situation_update_without_id")
                situation_update = None
        except Exception:
            errors.append("bad_situation_update")

    graph_updates: List[ContextEdgeUpdate] = []
    for raw_u in (data.get("context_graph_updates") or [])[:2]:
        try:
            u = ContextEdgeUpdate.model_validate(raw_u)
        except Exception:
            errors.append("bad_context_graph_update")
            continue
        if u.operation == "none":
            continue
        if u.operation == "create":
            if u.edge_id:
                errors.append("context_graph_create_with_id")
                continue
            if not (u.subject_ref and u.predicate and u.object_ref):
                errors.append("context_graph_create_missing_fields")
                continue
            if not (is_recognized_ref(u.subject_ref) and is_recognized_ref(u.object_ref)):
                errors.append("context_graph_unrecognized_ref")
                continue
            if u.subject_ref == u.object_ref:
                errors.append("context_graph_self_loop")
                continue
        elif u.operation in ("update", "supersede", "deactivate"):
            if not u.edge_id:
                errors.append("context_graph_update_without_id")
                continue
        if not u.reversible and _blocks_side_effect(uncertainty):
            errors.append("blocking_uncertainty_for_graph_update")
            continue
        graph_updates.append(u)

    try:
        tc_model = ToolCall.model_validate(tool_call) if tool_call else None
        # V3.2 — where the user is on the goal. Validated here, at the same
        # boundary as everything else the model sends: governance rebuilds the
        # decision field by field on purpose, so anything unrecognised never
        # reaches the loop. A reconstruction that does not validate is dropped
        # rather than repaired — the previous one is better than a guess.
        goal_state = None
        raw_goal_state = data.get("goal_state")
        if isinstance(raw_goal_state, dict):
            try:
                from guidance.models import GoalState

                goal_state = GoalState.model_validate(raw_goal_state).model_dump()
            except Exception:
                errors.append("goal_state_invalid")

        decision = CognitiveDecision(
            response_mode=mode,  # type: ignore[arg-type]
            user_intent_summary=str(data.get("user_intent_summary") or "")[:400],
            active_goal_summary=(
                str(data["active_goal_summary"])[:400]
                if data.get("active_goal_summary") is not None
                else None
            ),
            reasoning_status=status,  # type: ignore[arg-type]
            message_to_user=message,
            question=question,
            tool_call=tc_model,
            context_query=str(context_query)[:240] if context_query else None,
            context_need=context_need,
            state_updates=updates,
            memory_candidates=mem_cands,
            confidence=_clamp_conf(data.get("confidence")),
            claim_grounding=data.get("claim_grounding"),
            situation_update=situation_update,
            uncertainty=uncertainty,
            context_graph_updates=graph_updates,
            goal_state=goal_state,
        )
    except Exception:
        return GovernanceResult(False, errors=errors + ["pydantic_fail"])

    ok = (
        mode in ALLOWED_MODES
        and (mode != "ask" or bool(decision.question))
        and (mode != "tool" or decision.tool_call is not None)
    )
    return GovernanceResult(ok=ok, decision=decision, errors=errors)


def _missing_refs(
    uncertainty: Optional[UncertaintyState], *, strategy: Optional[str] = None
) -> List[str]:
    if not uncertainty:
        return []
    return [
        item.ref
        for item in uncertainty.missing_information
        if strategy is None or item.strategy == strategy
    ]


def clarification_ref_key(ref: str) -> str:
    """Stable non-reversible key; session state never stores AI/user wording."""
    return hashlib.sha256(str(ref).strip().casefold().encode("utf-8")).hexdigest()


def _blocks_side_effect(uncertainty: Optional[UncertaintyState]) -> bool:
    if not uncertainty:
        return False
    if uncertainty.blocking:
        return True
    if any(item.blocking for item in uncertainty.missing_information):
        return True
    return any(a.consequential or not a.reversible for a in uncertainty.assumptions)


def memory_candidates_are_proposals_only(decision: CognitiveDecision) -> bool:
    return True


def _normalize_tool_call(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, ToolCall):
        d = raw.model_dump()
    elif isinstance(raw, dict):
        d = dict(raw)
    else:
        return None
    cap = (d.get("capability") or d.get("name") or "").strip()
    if not cap:
        return None
    return {
        "name": cap,
        "capability": cap,
        "operation": d.get("operation"),
        "arguments": dict(d.get("arguments") or {}),
        "reason": d.get("reason"),
    }


def _asks_permission_for_readonly(text: str) -> bool:
    t = (text or "").lower()
    return any(
        p in t
        for p in (
            "vuoi che verifichi",
            "vuoi che cerchi",
            "vuoi che controlli",
            "shall i search",
            "want me to check",
            "want me to search",
        )
    )


_LEAK = (
    "requirement",
    "readiness",
    "discriminator",
    "question_goal",
    "slot schema",
    "blocking field",
    "research target",
)


def _sanitize_copy(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    t = str(text).strip()
    low = t.lower()
    if any(x in low for x in _LEAK):
        return None if "?" not in t else t.split("?")[0].strip() + "?"
    while "Per Per:" in t:
        t = t.replace("Per Per:", "Per:")
    return t[:800] if t else None


def _clamp_conf(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        return max(0.0, min(1.0, f))
    except Exception:
        return None
