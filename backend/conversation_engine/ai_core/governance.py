"""Governance — validates AI decisions without replacing cognition."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from conversation_engine.ai_core.context_broker import validate_context_query
from conversation_engine.ai_core.models import CognitiveDecision, MemoryCandidate, ToolCall
from conversation_engine.ai_core.tools.registry import ToolRegistry, tool_signature
from conversation_engine.ai_core.tools.sanitize import sanitize_external_query

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
                        clean, reason = sanitize_external_query(str(args.get("query") or ""))
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
    elif mode == "context":
        if not (context_query and str(context_query).strip()):
            context_query = data.get("user_intent_summary") or "relevant personal facts"
        ok_q, reason = validate_context_query(str(context_query))
        if not ok_q:
            errors.append(f"blocked_context_query:{reason}")
            mode = "answer"
            message = message or (
                "Non posso caricare tutto il tuo profilo in una volta. "
                "Dimmi pure cosa ti serve in particolare."
            )
            context_query = None
            tool_call = None
        else:
            tool_call = None
    else:
        tool_call = None
        if mode in ("answer", "finish", "act") and not (message and str(message).strip()):
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
    for m in data.get("memory_candidates") or []:
        if isinstance(m, dict) and str(m.get("fact_summary") or "").strip():
            mem_cands.append(m)
        elif isinstance(m, MemoryCandidate) and m.fact_summary.strip():
            mem_cands.append(m.model_dump())

    message = _sanitize_copy(message)
    question = _sanitize_copy(question)

    try:
        tc_model = ToolCall.model_validate(tool_call) if tool_call else None
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
            state_updates=updates,
            memory_candidates=mem_cands,
            confidence=_clamp_conf(data.get("confidence")),
            claim_grounding=data.get("claim_grounding"),
        )
    except Exception:
        return GovernanceResult(False, errors=errors + ["pydantic_fail"])

    ok = mode in ALLOWED_MODES and (
        mode != "ask" or bool(decision.question)
    ) and (
        mode != "tool" or decision.tool_call is not None
    )
    return GovernanceResult(ok=ok, decision=decision, errors=errors)


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
