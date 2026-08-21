"""Bounded agentic reasoning loop — AI decides; tools/context observe."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from conversation_engine.ai_core.context_broker import (
    ContextBroker,
    context_payload_stats,
)
from conversation_engine.ai_core.context_sources import GRAPH_MAX_DEPTH
from conversation_engine.ai_core.fallback import (
    fallback_decision_after_malformed,
    provider_unavailable_result,
)
from conversation_engine.ai_core.governance import clarification_ref_key, validate_decision
from conversation_engine.ai_core.grounding.temporal import merge_context_with_current
from conversation_engine.ai_core.models import (
    ActiveGoal,
    CognitiveDecision,
    CognitiveTurnResult,
    ContextFact,
    Observation,
)
from conversation_engine.ai_core.prompt import (
    COGNITIVE_SYSTEM_PROMPT,
    build_user_payload,
)
from conversation_engine.ai_core import state as state_mod
from conversation_engine.ai_core.tools.registry import (
    ToolRegistry,
    new_reasoning_epoch,
    tool_signature,
)
from conversation_engine.ai_core.trace import add_step, new_trace, public_trace
from conversation_engine.models import ConversationSession, now_iso
from life_signals import emitters as life_signals

logger = logging.getLogger("ora.ai_core.loop")

MAX_STEPS = 8
MAX_TOOL_CALLS = 5
MAX_EXTERNAL_QUERIES = 2
MAX_CONTEXT_CALLS = 2
MAX_WRITE_CALLS = 4
MAX_OBJECT_GENERATIONS = 2
MAX_SOURCES_UI = 5

_CALENDAR_WRITE_CAPS = frozenset(
    {"create_calendar_event", "update_calendar_event", "cancel_calendar_event"}
)
_WRITE_CAPS = frozenset(
    {
        "create_plan",
        "update_plan",
        "create_actions",
        "create_object",
        "update_object",
        "record_object_interaction",
        "mark_plan_progress",
        "note_intention",
        *_CALENDAR_WRITE_CAPS,
    }
)
# Durable Life OS objects — note_intention alone does NOT satisfy persist-before-claim.
_LIFE_OS_PERSIST_CAPS = frozenset(
    {
        "create_plan",
        "update_plan",
        "create_actions",
        "create_object",
        "update_object",
        "mark_plan_progress",
    }
)

async def _emit_life_change(
    trace: Dict[str, Any],
    source_system: str,
    emit: Callable[[], Awaitable[Any]],
) -> None:
    """Record a LifeChangeSignal for a mutation that is ALREADY persisted
    (V2.9.1).

    Failure isolation: the primary mutation has already committed by the time
    this runs, so a signal-layer failure must never propagate — the user's real
    life state is correct and only the derived event is lost. The failure stays
    observable via the `life_change_signal_failures` trace counter instead of
    being silently swallowed. This never mutates a life entity and never emits
    a second signal, so there is no signal → mutation → signal recursion.
    """
    try:
        result = await emit()
    except Exception as e:
        trace["life_change_signal_failures"] = int(
            trace.get("life_change_signal_failures") or 0
        ) + 1
        logger.warning(
            "life_change_signal emit failed source_system=%s error=%s",
            source_system,
            type(e).__name__,
        )
        return
    emitted = len(result) if isinstance(result, list) else (1 if result else 0)
    if emitted:
        trace["life_change_signals"] = int(trace.get("life_change_signals") or 0) + emitted


# Soft re-entry when the model narrates durable Life OS writes without observations.
_PERSIST_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"ho\s+(creato|impostato|organizzato|preparato|generato|salvato)|"
    r"piano\s+(è|e)\s+pronto|piano\s+di\s+\d+|"
    r"ti\s+ho\s+preparato|materiale\s+per\s+oggi|"
    r"ho\s+fatto\s+un\s+piano|"
    r"i('|\u2019)?ve\s+(created|set\s+up|prepared|generated)|"
    r"here\s+is\s+(your|the)\s+(plan|material|session)"
    r")\b"
)
_DURABLE_MEMORY_CLAIM_RE = re.compile(
    r"(?i)\b(ho\s+memorizzato|ho\s+salvato\s+(in\s+)?memoria|"
    r"ho\s+preso\s+nota|terrò\s+presente\s+(in\s+futuro|d'ora\s+in\s+poi)|"
    r"ho\s+dimenticato|ho\s+rimosso\s+(dalla\s+)?memoria|"
    r"ho\s+rimosso\b.{0,100}\bmemorizzat[oa]|"
    r"i('|’)?ve\s+memorized|saved\s+(it\s+)?to\s+memory|"
    r"i('|’)?ve\s+forgotten|removed\s+(it\s+)?from\s+memory|"
    r"i('ll|\s+will)\s+remember\s+(it|that)\s+(in\s+the\s+future|going\s+forward))\b"
)
_GRAPH_LINK_CLAIM_RE = re.compile(
    r"(?i)\b(ho\s+collegat[oi]|li\s+ho\s+collegati|ho\s+associat[oi]|"
    r"ho\s+creato\s+(un\s+)?collegamento|ho\s+messo\s+in\s+relazione|"
    r"i('|’)?ve\s+linked|i('|’)?ve\s+connected|"
    r"i('|’)?ve\s+related)\b"
)
_CALENDAR_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"ho\s+(creato|aggiunto|inserito|messo|spostato|riprogrammato|cancellato|"
    r"eliminato|rimosso)\b.{0,60}\bcalendario|"
    r"(l'|lo\s+)?ho\s+(spostato|riprogrammato|cancellato|eliminato)\b.{0,40}\b(evento|impegno)|"
    r"aggiunto\s+al\s+(tuo\s+)?calendario|"
    r"i('|’)?ve\s+(created|added|scheduled|moved|rescheduled|cancel(l)?ed|deleted|removed)\b.{0,60}\b(calendar|event)"
    r")\b"
)
_MEMORY_NOT_FOUND_CLAIM_RE = re.compile(
    r"(?i)\b(non\s+ho\s+trovato.{0,120}\bmemoria|"
    r"non\s+c('|’|i\s+)è\s+alcun[ao].{0,100}\bda\s+dimenticare|"
    r"no\s+(matching|specific)\s+memory\s+(was\s+)?found|"
    r"there\s+is\s+nothing.{0,80}\bto\s+forget)\b"
)
# Current-location questions must go through location capabilities (consent bridge).
_LOCATION_NOW_ASK_RE = re.compile(
    r"(?i)\b("
    r"dove\s+sono(\s+adesso)?|"
    r"where\s+am\s+i|"
    r"posizione\s+attuale|"
    r"current\s+location|"
    r"my\s+location\s+now"
    r")\b"
)
_LOCATION_CAPS = frozenset(
    {
        "get_current_location",
        "get_current_presence",
        "get_recent_presence_context",
    }
)


def _has_terminal_location_obs(observations: List[Dict[str, Any]]) -> bool:
    """True when a location tool already returned a terminal (non-bridge) result."""
    for o in observations:
        if not isinstance(o, dict):
            continue
        if o.get("name") not in _LOCATION_CAPS:
            continue
        if o.get("status") == "needs_client":
            continue
        payload = o.get("payload") or {}
        pstatus = str(payload.get("status") or "")
        if pstatus in (
            "stale",
            "needs_client",
            "consent_required",
            "permission_required",
        ):
            continue
        if payload.get("needs_client") and pstatus not in (
            "ok",
            "denied",
            "unavailable",
            "timeout",
            "error",
        ):
            continue
        return True
    return False


# Claims that saved material was adapted — require update_object observation.
_ADAPT_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"ho\s+(semplificato|aggiornato|riscritto|modificato|ridotto|riorganizzato|accorciato)|"
    r"l('|\u2019)?ho\s+(semplificato|aggiornato|riscritto|modificato)|"
    r"materiale\s+(è|e)\s+(stato\s+)?(aggiornato|semplificato|modificato)|"
    r"oggetto\s+(è|e)\s+(stato\s+)?(aggiornato|semplificato)|"
    r"workspace\s+(è|e)\s+(aggiornato|semplificato)|"
    r"i('|\u2019)?ve\s+(simplified|updated|rewritten|shortened)|"
    r"i\s+simplified|i\s+updated\s+the\s+(material|object|workspace)"
    r")\b"
)

DecisionFn = Callable[[str, str], Awaitable[Dict[str, Any]]]


async def run_cognitive_loop(
    *,
    sess: ConversationSession,
    user_message: str,
    db=None,
    decision_fn: Optional[DecisionFn] = None,
    max_steps: int = MAX_STEPS,
    resume_client: bool = False,
) -> CognitiveTurnResult:
    t0 = time.perf_counter()
    trace = new_trace()
    tools = ToolRegistry(db)
    broker = ContextBroker(db)
    st = state_mod.get_ai_state(sess)

    # Client-resume continues the SAME user turn — do not duplicate recent_turns.
    if not resume_client:
        state_mod.append_turn(st, role="user", text=user_message)
        # New user message: allow another foreground refresh after timeout/unavailable.
        if db is not None and sess.user_id:
            try:
                from location.service import LocationService

                await LocationService(db).clear_transient_acquisition_error(
                    sess.user_id
                )
            except Exception:
                pass
    add_step(
        trace,
        event="TURN_RESUME" if resume_client else "TURN",
        user_message=user_message[:200],
    )

    context_facts = await broker.retrieve(
        user_id=sess.user_id,
        user_message=user_message,
        active_goal=st.get("active_goal"),
        stage="A",
        session_id=sess.id,
    )
    # Merge temporary current_facts (do not overwrite durable Profile)
    context_facts = merge_context_with_current(context_facts, st)
    # Normalize any dict extras from temporal merge
    normalized: List[ContextFact] = []
    for f in context_facts:
        if isinstance(f, ContextFact):
            normalized.append(f)
        elif isinstance(f, dict):
            try:
                normalized.append(ContextFact.model_validate(f))
            except Exception:
                continue
    context_facts = normalized

    trace["context_calls"] = int(trace.get("context_calls") or 0) + 1
    stats_a = context_payload_stats(context_facts)
    trace["context_item_count"] = stats_a["item_count"]
    trace["context_payload_chars"] = stats_a["payload_chars"]
    add_step(
        trace,
        event="CONTEXT_A",
        refs=[f.ref for f in context_facts],
        n=len(context_facts),
        payload_chars=stats_a["payload_chars"],
        sources=[f.source for f in context_facts],
    )

    observations: List[Dict[str, Any]] = list(st.get("observations") or [])
    # V2.6.2 — mutation idempotency is TURN-SCOPED (reasoning epoch).
    # Session-persisted signatures must NOT ban legitimate cross-turn replanning
    # when the user provides new facts/evidence that change persisted state.
    epoch = str(st.get("reasoning_epoch") or "") if resume_client else ""
    if not epoch:
        epoch = new_reasoning_epoch()
    st["reasoning_epoch"] = epoch
    recent_tool_sigs: Set[str] = set()
    st["turn_tool_signatures"] = []
    turn_obs_by_sig: Dict[str, Dict[str, Any]] = {}
    last_decision: Optional[CognitiveDecision] = None
    ai_calls = 0
    tool_calls = 0
    external_queries = 0
    write_calls = 0
    object_gens = 0
    public_sources: List[Dict[str, str]] = []
    working_hint: Optional[str] = None
    persist_nudge_used = False
    location_nudge_used = False
    life_os_writes_this_turn = 0
    update_object_ok_this_turn = False
    situation_result: Optional[Dict[str, Any]] = None
    situation_plan_nudge_used = False
    linked_plan_pending_id: Optional[str] = None
    linked_plan_reconciled_this_turn = False
    memory_governance_rounds = 0
    memory_write_confirmed_this_turn = False
    memory_write_decisions_this_turn: List[str] = []
    memory_claim_nudge_used = False
    memory_result_nudge_used = False
    graph_write_confirmed_this_turn = False
    graph_claim_nudge_used = False
    calendar_write_confirmed_this_turn = False
    calendar_claim_nudge_used = False
    clarification_attempts = {
        str(item.get("key")): int(item.get("attempts") or 0)
        for item in (st.get("clarification_history") or [])
        if isinstance(item, dict) and item.get("key")
    }

    # Hydrate plan/object conversational focus for linked sessions
    from conversation_engine.ai_core.life_os_context import (
        build_life_os_ai_payload,
        set_active_object_ref,
    )

    for step in range(max(1, max_steps)):
        life_os_payload = await build_life_os_ai_payload(db, sess, st)
        payload = build_user_payload(
            user_message=user_message,
            recent_turns=st.get("recent_turns") or [],
            active_goal=st.get("active_goal"),
            context_facts=[f.model_dump() for f in context_facts],
            tools=tools.list_public(),
            observations=observations[-6:],
            current_facts=st.get("current_facts") or {},
            life_os=life_os_payload,
        )
        raw = await _call_ai(
            decision_fn=decision_fn,
            system=COGNITIVE_SYSTEM_PROMPT,
            user=payload,
        )
        ai_calls += 1
        trace["ai_calls"] = ai_calls

        if raw is None:
            add_step(trace, event="PROVIDER_FAIL")
            state_mod.save_ai_state(sess, st)
            out = provider_unavailable_result(session_id=sess.id)
            out.ai_calls = ai_calls
            out.tool_calls = tool_calls
            out.context_calls = int(trace.get("context_calls") or 0)
            out.external_queries = external_queries
            out.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            out.trace = public_trace(trace)
            return out

        gov = validate_decision(
            raw,
            tools=tools,
            recent_tool_signatures=recent_tool_sigs,
            external_query_count=external_queries,
            max_external_queries=MAX_EXTERNAL_QUERIES,
            clarification_attempts=clarification_attempts,
        )
        validated_raw: Any = raw
        if not gov.ok or not gov.decision:
            raw2 = await _call_ai(
                decision_fn=decision_fn,
                system=COGNITIVE_SYSTEM_PROMPT
                + "\nPrevious output was invalid. Return valid JSON only.",
                user=payload,
            )
            ai_calls += 1
            trace["ai_calls"] = ai_calls
            gov = validate_decision(
                raw2,
                tools=tools,
                recent_tool_signatures=recent_tool_sigs,
                external_query_count=external_queries,
                max_external_queries=MAX_EXTERNAL_QUERIES,
                clarification_attempts=clarification_attempts,
            )
            validated_raw = raw2
            if not gov.ok or not gov.decision:
                decision = fallback_decision_after_malformed()
                add_step(trace, event="MALFORMED_FALLBACK", errors=gov.errors)
            else:
                decision = gov.decision
                add_step(trace, event="AI_DECISION_RETRY", mode=decision.response_mode)
        else:
            decision = gov.decision
            add_step(
                trace,
                event="AI_DECISION",
                mode=decision.response_mode,
                status=decision.reasoning_status,
                tool=(
                    decision.tool_call.resolved_capability
                    if decision.tool_call
                    else None
                ),
                has_question=bool(decision.question),
            )

        last_decision = decision
        if "repeated_clarification" in gov.errors:
            trace["repeated_question_prevented"] = int(
                trace.get("repeated_question_prevented") or 0
            ) + 1
            add_step(trace, event="REPEATED_QUESTION_PREVENTED")
        # Same-turn duplicate: reuse prior observation; never surface internal guard UX
        if "duplicate_tool_call" in (gov.errors or []):
            # Recover signature from raw tool call if governance cleared it
            raw_tc = None
            if isinstance(validated_raw, dict):
                raw_tc = validated_raw.get("tool_call")
            elif hasattr(validated_raw, "tool_call"):
                raw_tc = validated_raw.tool_call
            cap_try = ""
            args_try: Dict[str, Any] = {}
            if isinstance(raw_tc, dict):
                cap_try = str(raw_tc.get("capability") or raw_tc.get("name") or "")
                args_try = dict(raw_tc.get("arguments") or {})
            elif raw_tc is not None:
                cap_try = str(
                    getattr(raw_tc, "capability", None)
                    or getattr(raw_tc, "name", None)
                    or ""
                )
                args_try = dict(getattr(raw_tc, "arguments", None) or {})
            # Mirror active plan/object injection used on execute path
            if cap_try in (
                "update_plan",
                "create_actions",
                "create_object",
                "update_object",
                "get_object",
                "record_object_interaction",
                "mark_plan_progress",
                "get_active_plan",
            ):
                if not args_try.get("plan_id") and not args_try.get("plan_ref"):
                    if st.get("active_plan_id"):
                        args_try["plan_id"] = st["active_plan_id"]
                if (
                    cap_try
                    in (
                        "update_object",
                        "get_object",
                        "record_object_interaction",
                    )
                    and not args_try.get("object_id")
                    and not args_try.get("id")
                ):
                    oid = (st.get("active_object_ref") or {}).get("id")
                    if oid:
                        args_try["object_id"] = oid
            sig_try = tool_signature(cap_try, args_try) if cap_try else ""
            prior = turn_obs_by_sig.get(sig_try) if sig_try else None
            if prior and step + 1 < max_steps:
                observations.append(
                    {
                        **prior,
                        "name": prior.get("name") or cap_try or "tool",
                        "payload": {
                            **dict(prior.get("payload") or {}),
                            "deduped": True,
                            "reused_from_turn": True,
                            "honesty": (
                                "Identical mutation already succeeded this turn — "
                                "reuse observation; do not claim a second write."
                            ),
                        },
                    }
                )
                add_step(trace, event="DUPLICATE_REUSED", capability=cap_try)
                continue
            # No reusable obs — ask model to continue without leaking guard copy
            if decision.response_mode == "answer" and not (
                decision.message_to_user and str(decision.message_to_user).strip()
            ):
                observations.append(
                    Observation(
                        kind="system",
                        name="duplicate_tool_call",
                        status="info",
                        payload={
                            "failure_code": "DUPLICATE_SAME_TURN",
                            "reason": (
                                "Identical tool call already ran in this turn. "
                                "Answer from existing observations, or call a "
                                "different mutation if new facts require it."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="DUPLICATE_SOFT", capability=cap_try)
                if step + 1 < max_steps:
                    continue
        state_mod.apply_state_updates(st, decision.state_updates)
        if decision.situation_update and decision.situation_update.operation != "none":
            try:
                from situations.service import SituationService

                situation_result = await SituationService(db).apply(
                    user_id=sess.user_id,
                    session_id=sess.id,
                    update=decision.situation_update,
                    reasoning_epoch=epoch,
                )
                st["active_situation_ref"] = dict(
                    situation_result.get("situation") or {}
                )
                observations.append(
                    Observation(
                        kind="tool",
                        name="situation_mutation",
                        status="ok",
                        payload=situation_result,
                        provenance=list(
                            decision.situation_update.source_refs
                            or ["user_conversation"]
                        ),
                    ).model_dump()
                )
                add_step(
                    trace,
                    event="SITUATION_MUTATION",
                    operation=decision.situation_update.operation,
                )
                await _emit_life_change(
                    trace,
                    "situation",
                    lambda: life_signals.emit_situation_signal(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        operation=decision.situation_update.operation,
                        result=situation_result,
                    ),
                )
                linked_plan = ((situation_result or {}).get("situation") or {}).get(
                    "linked_plan_id"
                )
                if decision.situation_update.operation == "cancel" and linked_plan:
                    linked_plan_pending_id = str(linked_plan)
            except Exception as e:
                code = str(getattr(e, "code", "PERSISTENCE_ERROR"))[:80]
                observations.append(
                    Observation(
                        kind="error",
                        name="situation_mutation",
                        status="error",
                        payload={
                            "failure_code": code,
                            "reason": "Situation state was not persisted. Do not claim it was updated. Recover from context or explain honestly.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="SITUATION_MUTATION_FAIL", code=code)
                if step + 1 < max_steps:
                    continue
        if decision.context_graph_updates:
            try:
                from context_graph.service import ContextGraphService

                graph_results = await ContextGraphService(db).apply(
                    user_id=sess.user_id,
                    session_id=sess.id,
                    updates=list(decision.context_graph_updates),
                    reasoning_epoch=epoch,
                )
                trace["context_graph_updates_proposed"] = int(
                    trace.get("context_graph_updates_proposed") or 0
                ) + len(decision.context_graph_updates)
                trace["context_graph_updates_persisted"] = int(
                    trace.get("context_graph_updates_persisted") or 0
                ) + sum(1 for r in graph_results if r.get("persisted"))
                trace["context_graph_conflicts_detected"] = int(
                    trace.get("context_graph_conflicts_detected") or 0
                ) + sum(
                    1
                    for r in graph_results
                    if r.get("decision") == "REQUIRES_SUPERSESSION"
                )
                trace["context_graph_supersessions"] = int(
                    trace.get("context_graph_supersessions") or 0
                ) + sum(1 for r in graph_results if r.get("decision") == "SUPERSEDED")
                graph_write_confirmed_this_turn = any(
                    r.get("persisted") for r in graph_results
                )
                observations.append(
                    Observation(
                        kind="tool",
                        name="context_graph_mutation",
                        status="ok",
                        payload={
                            "results": graph_results,
                            "reason": (
                                "Durable graph relationships exist only where persisted=true. "
                                "REQUIRES_SUPERSESSION means an active edge with the same "
                                "subject+predicate already exists with a different object — "
                                "decide supersede or coexists_with_refs, do not silently retry "
                                "the same create. Never claim a link was made without persisted=true."
                            ),
                        },
                        provenance=[
                            r.get("edge_id") for r in graph_results if r.get("edge_id")
                        ],
                    ).model_dump()
                )
                add_step(
                    trace,
                    event="CONTEXT_GRAPH_MUTATION",
                    outcomes=[r.get("decision") for r in graph_results],
                )
                await _emit_life_change(
                    trace,
                    "context_graph",
                    lambda: life_signals.emit_context_graph_signals(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        results=graph_results,
                    ),
                )
            except Exception as e:
                code = str(getattr(e, "code", "PERSISTENCE_ERROR"))[:80]
                graph_write_confirmed_this_turn = False
                observations.append(
                    Observation(
                        kind="error",
                        name="context_graph_mutation",
                        status="error",
                        payload={
                            "failure_code": code,
                            "reason": "Graph relationship was not persisted. Do not claim it was linked/connected. Recover from context or explain honestly.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="CONTEXT_GRAPH_MUTATION_FAIL", code=code)
                if step + 1 < max_steps:
                    continue
        if decision.memory_candidates and memory_governance_rounds < 2:
            memory_governance_rounds += 1
            try:
                from life_memory.governance import MemoryGovernanceService

                memory_outcomes = await MemoryGovernanceService(db).process(
                    user_id=sess.user_id,
                    session_id=sess.id,
                    reasoning_epoch=epoch,
                    candidates=list(decision.memory_candidates),
                )
                memory_write_confirmed_this_turn = any(
                    item.persisted for item in memory_outcomes
                )
                memory_write_decisions_this_turn = [
                    item.decision for item in memory_outcomes if item.persisted
                ]
                observations.append(
                    Observation(
                        kind="tool",
                        name="memory_governance",
                        status="ok",
                        payload={
                            "outcomes": [item.public() for item in memory_outcomes],
                            "reason": (
                                "Durable Memory changes exist only where persisted=true. "
                                "CLARIFY requires a natural user question; REJECT means keep the "
                                "information conversational/Situation-only. Never claim an unpersisted write."
                            ),
                        },
                        provenance=["user_conversation"],
                    ).model_dump()
                )
                add_step(
                    trace,
                    event="MEMORY_GOVERNANCE",
                    outcomes=[item.decision for item in memory_outcomes],
                )
                await _emit_life_change(
                    trace,
                    "life_memory",
                    lambda: life_signals.emit_memory_signals(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        outcomes=memory_outcomes,
                    ),
                )
            except Exception as e:
                code = str(getattr(e, "code", "MEMORY_PERSISTENCE_ERROR"))[:80]
                observations.append(
                    Observation(
                        kind="error",
                        name="memory_governance",
                        status="error",
                        payload={
                            "failure_code": code,
                            "reason": (
                                "No durable Memory change was confirmed. Do not say it was saved; "
                                "continue honestly or ask the user to retry."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="MEMORY_GOVERNANCE_FAIL", code=code)
            if step + 1 < max_steps:
                continue
        # Refresh context merge after current_facts updates
        context_facts = merge_context_with_current(
            [
                f
                for f in context_facts
                if not (f.ref or "").startswith("current_facts:")
            ],
            st,
        )
        context_facts = [
            f if isinstance(f, ContextFact) else ContextFact.model_validate(f)
            for f in context_facts
            if isinstance(f, (ContextFact, dict))
        ]

        if decision.active_goal_summary:
            goal = dict(st.get("active_goal") or {})
            if not goal.get("summary"):
                goal["summary"] = decision.active_goal_summary
                st["active_goal"] = goal
        state_mod.record_decision(st, decision)

        mode = decision.response_mode
        if mode in ("answer", "ask", "finish", "act"):
            if linked_plan_pending_id and not linked_plan_reconciled_this_turn:
                first_nudge = not situation_plan_nudge_used
                situation_plan_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="linked_plan_reconciliation",
                        status="nudge",
                        payload={
                            "failure_code": "LINKED_PLAN_DECISION_REQUIRED",
                            "plan_id": linked_plan_pending_id,
                            "reason": (
                                "The contextual Situation is cancelled but its linked plan was not changed. "
                                "Decide whether that plan still serves a valid outcome. If the abandoned activity "
                                "made the plan obsolete, call update_plan on the same id with patch.status=cancelled. "
                                "Otherwise preserve/adapt it and state that distinction honestly. "
                                "Do not repeat the Situation mutation; it already succeeded."
                            ),
                            "repeated_after_ignored_nudge": not first_nudge,
                        },
                    ).model_dump()
                )
                add_step(trace, event="SITUATION_PLAN_NUDGE")
                if step + 1 < max_steps:
                    continue
                decision.response_mode = "answer"
                decision.question = None
                decision.message_to_user = (
                    "Ho aggiornato la situazione, ma non sono riuscita a riconciliare il piano "
                    "collegato. Il piano potrebbe essere ancora attivo: non lo considero annullato."
                )
            ora = _compose_user_text(decision)
            if decision.uncertainty:
                trace["uncertainty_turns"] = int(trace.get("uncertainty_turns") or 0) + 1
                trace["unresolved_uncertainty"] = bool(
                    decision.uncertainty.blocking
                    or decision.uncertainty.missing_information
                    or decision.uncertainty.ambiguities
                )
                if decision.uncertainty.assumptions:
                    trace["assumptions_used"] = int(
                        trace.get("assumptions_used") or 0
                    ) + len(decision.uncertainty.assumptions)
            if (
                memory_write_confirmed_this_turn
                and not memory_result_nudge_used
                and _MEMORY_NOT_FOUND_CLAIM_RE.search(ora or "")
                and step + 1 < max_steps
            ):
                memory_result_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="memory_result_consistency",
                        status="nudge",
                        payload={
                            "failure_code": "MEMORY_RESULT_CONTRADICTION",
                            "persisted_decisions": memory_write_decisions_this_turn,
                            "reason": (
                                "A Memory governance operation was persisted in this turn. "
                                "Answer from that persisted outcome; do not claim that no matching "
                                "memory existed merely because a later active-only lookup is empty."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="MEMORY_RESULT_NUDGE")
                continue
            unpersisted_memory_claim = (
                mode in ("answer", "finish", "act")
                and not memory_write_confirmed_this_turn
                and _DURABLE_MEMORY_CLAIM_RE.search(ora or "")
            )
            if (
                unpersisted_memory_claim
                and not memory_claim_nudge_used
                and step + 1 < max_steps
            ):
                memory_claim_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="memory_persist_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "MEMORY_PERSIST_REQUIRED",
                            "reason": (
                                "No persisted Memory governance outcome exists for this turn. "
                                "If durable learning is warranted, emit a bounded memory_candidate "
                                "and wait for memory_governance. Otherwise answer without claiming "
                                "that anything was remembered, saved, forgotten, or noted for future use."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="MEMORY_PERSIST_NUDGE")
                continue
            if unpersisted_memory_claim:
                # The model exhausted its reasoning budget without a persisted
                # governance outcome. Never let a final-turn wording bypass the
                # persist-before-claim invariant.
                decision.message_to_user = (
                    "Non sono riuscita a salvare questa informazione in memoria "
                    "in questo momento. Possiamo riprovare."
                )
                decision.question = None
                mode = "answer"
                ora = _compose_user_text(decision)
                add_step(trace, event="MEMORY_CLAIM_BLOCKED_TERMINAL")
            unconfirmed_graph_claim = (
                mode in ("answer", "finish", "act")
                and not graph_write_confirmed_this_turn
                and _GRAPH_LINK_CLAIM_RE.search(ora or "")
            )
            if (
                unconfirmed_graph_claim
                and not graph_claim_nudge_used
                and step + 1 < max_steps
            ):
                graph_claim_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="context_graph_persist_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "CONTEXT_GRAPH_PERSIST_REQUIRED",
                            "reason": (
                                "No persisted context_graph_updates outcome exists for this "
                                "turn. If a durable relationship is warranted, emit a bounded "
                                "context_graph_updates entry and wait for its result. Otherwise "
                                "answer without claiming that anything was linked or connected."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="CONTEXT_GRAPH_PERSIST_NUDGE")
                continue
            if unconfirmed_graph_claim:
                decision.message_to_user = (
                    "Non sono riuscita a salvare questo collegamento in questo momento. "
                    "Possiamo riprovare."
                )
                decision.question = None
                mode = "answer"
                ora = _compose_user_text(decision)
                add_step(trace, event="CONTEXT_GRAPH_CLAIM_BLOCKED_TERMINAL")
            unconfirmed_calendar_claim = (
                mode in ("answer", "finish", "act")
                and not calendar_write_confirmed_this_turn
                and _CALENDAR_CLAIM_RE.search(ora or "")
            )
            if (
                unconfirmed_calendar_claim
                and not calendar_claim_nudge_used
                and step + 1 < max_steps
            ):
                calendar_claim_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="calendar_persist_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "CALENDAR_PERSIST_REQUIRED",
                            "reason": (
                                "No successful calendar tool observation (status=ok) exists "
                                "for this turn. If a calendar change is warranted, call the "
                                "appropriate calendar capability and wait for its result. "
                                "Otherwise answer without claiming an event was created, "
                                "moved, or cancelled."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="CALENDAR_PERSIST_NUDGE")
                continue
            if unconfirmed_calendar_claim:
                decision.message_to_user = (
                    "Non sono riuscita a confermare questa modifica al calendario in questo "
                    "momento. Possiamo riprovare."
                )
                decision.question = None
                mode = "answer"
                ora = _compose_user_text(decision)
                add_step(trace, event="CALENDAR_CLAIM_BLOCKED_TERMINAL")
            if (
                decision.situation_update
                and decision.situation_update.operation != "none"
                and _DURABLE_MEMORY_CLAIM_RE.search(ora or "")
                and step + 1 < max_steps
            ):
                observations.append(
                    Observation(
                        kind="system",
                        name="situation_memory_separation",
                        status="nudge",
                        payload={
                            "failure_code": "SITUATION_IS_NOT_MEMORY",
                            "reason": (
                                "The Situation mutation succeeded only as contextual state. "
                                "Do not say it was memorized or saved to durable Memory. "
                                "Answer naturally that you are keeping the current situation in view."
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="SITUATION_MEMORY_NUDGE")
                continue
            # Location-before-claim: current-location asks (and pending refresh retries)
            # must call location caps so the FE consent / geolocation bridge can run.
            pending_loc = st.get("pending_client_capability") or {}
            pending_loc_cap = str(pending_loc.get("capability") or "")
            force_loc = pending_loc_cap in _LOCATION_CAPS
            has_loc_obs = _has_terminal_location_obs(observations)
            if (
                mode in ("answer", "ask", "finish")
                and not location_nudge_used
                and not has_loc_obs
                and step + 1 < max_steps
                and (force_loc or _LOCATION_NOW_ASK_RE.search(user_message or ""))
            ):
                location_nudge_used = True
                observations.append(
                    Observation(
                        kind="system",
                        name="location_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "LOCATION_CAPABILITY_REQUIRED",
                            "reason": (
                                "A current-location capability is still pending or the user "
                                "asked for current device location. Call get_current_location "
                                "(response_mode=tool) before answering. "
                                "STALE/needs_client observations are not final — refresh via the "
                                "client bridge. Do not claim permission is disabled unless the "
                                "observation status is denied. "
                                "requires_consent means the client will show ORA consent."
                            ),
                            "pending_capability": pending_loc_cap
                            or "get_current_location",
                        },
                    ).model_dump()
                )
                add_step(trace, event="LOCATION_NUDGE")
                continue
            # Persist-before-claim: one soft re-entry if AI narrates durable writes
            # without a successful write observation this turn.
            if (
                mode in ("answer", "act", "finish")
                and not persist_nudge_used
                and life_os_writes_this_turn == 0
                and step + 1 < max_steps
                and (
                    _claims_unverified_life_os_persist(
                        ora, has_active_plan=bool(st.get("active_plan_id"))
                    )
                    or (
                        not update_object_ok_this_turn
                        and _claims_unverified_object_adapt(
                            ora,
                            has_active_object=bool(
                                (st.get("active_object_ref") or {}).get("id")
                            ),
                        )
                    )
                )
            ):
                persist_nudge_used = True
                has_obj = bool((st.get("active_object_ref") or {}).get("id"))
                observations.append(
                    Observation(
                        kind="system",
                        name="persist_before_claim",
                        status="nudge",
                        payload={
                            "failure_code": "PERSIST_REQUIRED",
                            "reason": (
                                (
                                    "You claimed a durable object adaptation without a successful "
                                    "update_object observation. If the user wanted saved material "
                                    "changed, call update_object (same object_id from "
                                    "life_os.active_object_ref), then answer from observations. "
                                    "If you only explained conversationally, do not claim the "
                                    "workspace was updated."
                                )
                                if has_obj
                                and _claims_unverified_object_adapt(
                                    ora, has_active_object=True
                                )
                                else (
                                    "You claimed a durable Life OS plan/object without a successful "
                                    "create_plan / create_actions / create_object / update_object "
                                    "observation. note_intention is NOT enough. Call the Life OS "
                                    "capability (response_mode=tool), then answer from observations."
                                )
                            ),
                            "active_object_id": (
                                (st.get("active_object_ref") or {}).get("id")
                            ),
                        },
                    ).model_dump()
                )
                add_step(trace, event="PERSIST_NUDGE")
                continue
            state_mod.append_turn(st, role="ora", text=ora, kind=mode)
            if mode == "ask" and decision.uncertainty:
                asked_refs = [
                    item.ref
                    for item in decision.uncertainty.missing_information
                    if item.strategy == "ask"
                ]
                history = list(st.get("clarification_history") or [])
                for ref in asked_refs:
                    key = clarification_ref_key(ref)
                    clarification_attempts[key] = clarification_attempts.get(key, 0) + 1
                    history = [
                        item
                        for item in history
                        if not (isinstance(item, dict) and item.get("key") == key)
                    ]
                    history.append(
                        {
                            "key": key,
                            "attempts": clarification_attempts[key],
                            "reasoning_epoch": epoch,
                        }
                    )
                st["clarification_history"] = history[-12:]
                trace["clarifications_requested"] = int(
                    trace.get("clarifications_requested") or 0
                ) + len(asked_refs)
            elif mode in ("answer", "finish", "act"):
                # A terminal non-question represents progress, deferral or refusal
                # handling. Do not turn semantic refs into permanent session bans.
                st["clarification_history"] = []
            st["observations"] = observations[-12:]
            state_mod.save_ai_state(sess, st)
            add_step(trace, event="FINAL", mode=mode)
            return CognitiveTurnResult(
                ok=True,
                mode=mode,  # type: ignore[arg-type]
                ora_text=ora,
                question=decision.question if mode == "ask" else None,
                session_id=sess.id,
                active_goal=ActiveGoal.model_validate(st.get("active_goal") or {}),
                memory_candidates=list(decision.memory_candidates or []),
                trace=public_trace(trace),
                ai_calls=ai_calls,
                tool_calls=tool_calls,
                context_calls=int(trace.get("context_calls") or 0),
                external_queries=external_queries,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                sources=public_sources[:MAX_SOURCES_UI],
                working_hint=None,
                situation=(situation_result or {}).get("situation")
                or st.get("active_situation_ref"),
            )

        if mode == "context":
            cq = (decision.context_query or "").strip()
            if int(trace.get("context_calls") or 0) >= MAX_CONTEXT_CALLS:
                observations.append(
                    Observation(
                        kind="context",
                        name="context_broker",
                        status="budget_exhausted",
                        payload={
                            "failure_code": "CONTEXT_BUDGET_EXHAUSTED",
                            "reason": "No more personal-context retrieval calls are allowed this turn.",
                        },
                    ).model_dump()
                )
                add_step(trace, event="CONTEXT_BUDGET")
                if step + 1 < max_steps:
                    continue
                break
            more = await broker.retrieve(
                user_id=sess.user_id,
                user_message=user_message,
                active_goal=st.get("active_goal"),
                query=cq or user_message,
                context_need=decision.context_need,
                stage="B",
                session_id=sess.id,
            )
            trace["context_calls"] = int(trace.get("context_calls") or 0) + 1
            existing = {f.ref or f.statement or f.fact for f in context_facts}
            for f in more:
                key = f.ref or f.statement or f.fact
                if key not in existing:
                    context_facts.append(f)
                    existing.add(key)
            stats_b = context_payload_stats(context_facts)
            trace["context_item_count"] = stats_b["item_count"]
            trace["context_payload_chars"] = stats_b["payload_chars"]
            report = broker.last_report.public()
            trace["context_sources"] = report.get("queried_sources") or []
            trace["context_candidate_count"] = report.get("candidate_count") or 0
            trace["context_final_count"] = report.get("final_count") or 0
            trace["context_failure_status"] = report.get("status")
            graph_facts = [f for f in more if f.source == "life_context_graph"]
            if "life_context_graph" in (report.get("queried_sources") or []):
                trace["context_graph_calls"] = int(
                    trace.get("context_graph_calls") or 0
                ) + 1
                trace["context_graph_depth"] = GRAPH_MAX_DEPTH
                trace["context_graph_returned_edge_count"] = int(
                    trace.get("context_graph_returned_edge_count") or 0
                ) + len(graph_facts)
                trace["context_graph_payload_chars"] = int(
                    trace.get("context_graph_payload_chars") or 0
                ) + sum(len(f.statement) for f in graph_facts)
                if not graph_facts:
                    trace["context_graph_failure_status"] = str(
                        report.get("status") or "no_relevant_evidence"
                    )
            obs = Observation(
                kind="context",
                name="context_broker",
                status=(
                    "ok"
                    if more
                    else str(report.get("status") or "no_relevant_evidence")
                ),
                payload={
                    "facts": [f.model_dump() for f in more],
                    "context_need": (
                        decision.context_need.model_dump()
                        if decision.context_need
                        else {"query": cq}
                    ),
                    "item_count": len(more),
                    "grounding": "PERSONAL_CONTEXT",
                    "retrieval": report,
                },
                provenance=[f.ref for f in more if f.ref],
            )
            observations.append(obs.model_dump())
            if decision.uncertainty and any(
                item.strategy == "retrieve"
                for item in decision.uncertainty.missing_information
            ):
                trace["clarification_context_attempts"] = int(
                    trace.get("clarification_context_attempts") or 0
                ) + 1
            add_step(
                trace,
                event="CONTEXT_B",
                n=len(more),
                query=(cq or "")[:120],
                payload_chars=stats_b["payload_chars"],
                sources=[f.source for f in more],
            )
            continue

        if mode == "tool" and decision.tool_call:
            cap = decision.tool_call.resolved_capability
            if tool_calls >= MAX_TOOL_CALLS:
                observations.append(
                    Observation(
                        kind="system",
                        name="tool_budget",
                        status="blocked",
                        payload={
                            "failure_code": "UNSUPPORTED",
                            "reason": "max_tool_calls",
                        },
                    ).model_dump()
                )
                add_step(trace, event="TOOL_BUDGET")
                continue
            if cap in _WRITE_CAPS and write_calls >= MAX_WRITE_CALLS:
                observations.append(
                    Observation(
                        kind="system",
                        name="write_budget",
                        status="blocked",
                        payload={
                            "failure_code": "UNSUPPORTED",
                            "reason": "max_write_calls",
                        },
                    ).model_dump()
                )
                add_step(trace, event="WRITE_BUDGET")
                continue
            if cap == "create_object" and object_gens >= MAX_OBJECT_GENERATIONS:
                observations.append(
                    Observation(
                        kind="system",
                        name="object_budget",
                        status="blocked",
                        payload={
                            "failure_code": "UNSUPPORTED",
                            "reason": "max_object_generations",
                        },
                    ).model_dump()
                )
                add_step(trace, event="OBJECT_BUDGET")
                continue

            args = dict(decision.tool_call.arguments or {})
            # Prefer active plan / object from state when AI omits ids
            if cap in (
                "update_plan",
                "create_actions",
                "create_object",
                "update_object",
                "list_goal_objects",
                "mark_plan_progress",
                "get_active_plan",
                "get_object",
                "record_object_interaction",
            ):
                if not args.get("plan_id") and not args.get("plan_ref"):
                    if st.get("active_plan_id"):
                        args["plan_id"] = st["active_plan_id"]
                        if cap == "create_object":
                            args["plan_ref"] = st["active_plan_id"]
                if (
                    cap
                    in (
                        "update_object",
                        "get_object",
                        "record_object_interaction",
                    )
                    and not args.get("object_id")
                    and not args.get("id")
                ):
                    oid = (st.get("active_object_ref") or {}).get("id")
                    if oid:
                        args["object_id"] = oid
            sig = tool_signature(cap, args)
            working_hint = "Controllo…" if cap == "web_search" else "Organizzo…"
            obs = await tools.execute(
                cap,
                args,
                runtime={
                    "user_id": sess.user_id,
                    "session_id": sess.id,
                    "db": db,
                    "reasoning_epoch": epoch,
                    "platform": "web",
                },
            )
            tool_calls += 1
            trace["tool_calls"] = tool_calls
            # Client-side capability bridge (foreground location) — pause for FE
            if obs.status == "needs_client":
                ca = (obs.payload or {}).get("client_action")
                # Defensive: STALE historically set needs_client without client_action
                if not (isinstance(ca, dict) and ca.get("type")):
                    if (obs.payload or {}).get("needs_client") or (
                        (obs.payload or {}).get("status")
                        in (
                            "stale",
                            "needs_client",
                            "consent_required",
                        )
                    ):
                        ca = {
                            "type": "request_foreground_location",
                            "reason": "Refresh foreground location for this turn.",
                            "refresh": True,
                        }
                if isinstance(ca, dict) and ca.get("type"):
                    observations.append(obs.model_dump())
                    st["pending_client_resume_message"] = user_message
                    st["pending_client_capability"] = {
                        "capability": cap,
                        "action": str(ca.get("type"))[:64],
                        "refresh": bool(ca.get("refresh")),
                    }
                    # Generic pending-turn contract (survives Home → /ora navigation)
                    st["pending_turn"] = {
                        "id": f"pt_{uuid.uuid4().hex[:12]}",
                        "status": "awaiting_client",
                        "capability": cap,
                        "client_actions": [ca],
                        "user_message_preview": (user_message or "")[:80],
                        "created_at": now_iso(),
                    }
                    st["observations"] = observations[-12:]
                    state_mod.save_ai_state(sess, st)
                    add_step(
                        trace,
                        event="CLIENT_ACTION",
                        name=str(ca.get("type"))[:64],
                    )
                    return CognitiveTurnResult(
                        ok=True,
                        mode="answer",
                        ora_text="",
                        session_id=sess.id,
                        active_goal=ActiveGoal.model_validate(
                            st.get("active_goal") or {}
                        ),
                        memory_candidates=[],
                        trace=public_trace(trace),
                        ai_calls=ai_calls,
                        tool_calls=tool_calls,
                        context_calls=int(trace.get("context_calls") or 0),
                        external_queries=external_queries,
                        elapsed_ms=int((time.perf_counter() - t0) * 1000),
                        sources=[],
                        working_hint="Posizione…",
                        client_actions=[ca],
                    )
            # Fresh CURRENT/RECENT location — clear pending bridge so retries stop
            if (
                cap in _LOCATION_CAPS
                and obs.status == "ok"
                and not (obs.payload or {}).get("needs_client")
            ):
                st.pop("pending_client_capability", None)
                st.pop("pending_client_resume_message", None)
                st.pop("pending_client_actions", None)
                pt = dict(st.get("pending_turn") or {})
                if pt:
                    pt["status"] = "completed"
                    pt.pop("client_actions", None)
                    st["pending_turn"] = pt
            if cap == "web_search":
                external_queries += 1
                trace["external_queries"] = external_queries
                st["external_query_count_session"] = (
                    int(st.get("external_query_count_session") or 0) + 1
                )
            if cap in _WRITE_CAPS:
                write_calls += 1
                trace["write_calls"] = write_calls
            if cap in _CALENDAR_WRITE_CAPS and (
                obs.status == "ok" and (obs.payload or {}).get("status") == "ok"
            ):
                calendar_write_confirmed_this_turn = True
            if cap in _CALENDAR_WRITE_CAPS:
                # Emitted for "partial" too: local ORA state really changed
                # even when the Google-side sync stayed unconfirmed.
                await _emit_life_change(
                    trace,
                    "calendar",
                    lambda: life_signals.emit_calendar_signal(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        capability=cap,
                        observation_status=obs.status,
                        payload=obs.payload or {},
                    ),
                )
            if cap in _LIFE_OS_PERSIST_CAPS and (
                obs.status in ("ok", "success")
                or (obs.payload or {}).get("status") == "success"
            ):
                life_os_writes_this_turn += 1
                await _emit_life_change(
                    trace,
                    "life_os",
                    lambda: life_signals.emit_life_os_signal(
                        db,
                        user_id=sess.user_id,
                        session_id=sess.id,
                        reasoning_epoch=epoch,
                        capability=cap,
                        payload=obs.payload or {},
                    ),
                )
                if (
                    cap == "update_plan"
                    and linked_plan_pending_id
                    and str(args.get("plan_id") or "") == linked_plan_pending_id
                ):
                    linked_plan_reconciled_this_turn = True
            if cap == "create_object":
                object_gens += 1
                trace["object_generations"] = object_gens
                trace["artifact_generations"] = object_gens  # compat alias
            recent_tool_sigs.add(sig)
            st["turn_tool_signatures"] = list(recent_tool_sigs)[-20:]
            # Observability only — NOT used to ban cross-turn adaptation
            hist = list(st.get("last_mutations") or [])
            hist.append(
                {
                    "epoch": epoch,
                    "capability": cap,
                    "sig": sig[:240],
                    "status": obs.status,
                    "at": __import__(
                        "conversation_engine.models", fromlist=["now_iso"]
                    ).now_iso(),
                }
            )
            st["last_mutations"] = hist[-12:]
            # Clear legacy cross-turn ban list (keep empty / epoch-tagged)
            st["tool_signatures"] = []
            obs_dump = obs.model_dump()
            turn_obs_by_sig[sig] = obs_dump
            observations.append(obs_dump)

            # Persist active plan/goal refs for Continue / later turns
            payload = obs.payload or {}
            if payload.get("plan_id") and (
                obs.status in ("ok", "success") or payload.get("status") == "success"
            ):
                st["active_plan_id"] = payload["plan_id"]
            if payload.get("goal_id") and (
                obs.status in ("ok", "success") or payload.get("status") == "success"
            ):
                st["active_goal_id"] = payload["goal_id"]
            if payload.get("object_id") and payload.get("status") == "success":
                objs = list(st.get("object_ids") or [])
                oid = str(payload["object_id"])
                objs = [x for x in objs if x != oid]
                objs.insert(0, oid)
                st["object_ids"] = objs[:20]
                st["artifact_ids"] = st["object_ids"]  # compat
                if cap in ("create_object", "update_object", "get_object"):
                    set_active_object_ref(
                        st,
                        {
                            "id": oid,
                            "title": payload.get("title"),
                            "object_kind": payload.get("object_kind"),
                            "revision": payload.get("revision"),
                            "updated_at": payload.get("updated_at"),
                            "plan_id": payload.get("plan_id")
                            or st.get("active_plan_id"),
                        },
                    )
                if cap == "update_object":
                    update_object_ok_this_turn = True

            for s in payload.get("public_sources") or []:
                if isinstance(s, dict) and (s.get("title") or s.get("url")):
                    public_sources.append(
                        {
                            "title": str(s.get("title") or "")[:80],
                            "url": str(s.get("url") or "")[:300],
                        }
                    )

            for f in payload.get("facts") or []:
                if isinstance(f, dict) and (f.get("fact") or f.get("statement")):
                    context_facts.append(ContextFact.model_validate(f))

            add_step(
                trace,
                event="TOOL",
                name=cap,
                status=obs.status,
                failure=payload.get("failure_code")
                or ((payload.get("external") or {}).get("failure_code")),
            )
            continue

        break

    ora = (
        (last_decision.message_to_user if last_decision else None)
        or (last_decision.question if last_decision else None)
        or "Sto ancora ragionando su questo — dimmi pure se vuoi aggiungere qualcosa."
    )
    if linked_plan_pending_id and not linked_plan_reconciled_this_turn:
        ora = (
            "Ho aggiornato la situazione, ma non sono riuscita a riconciliare il piano "
            "collegato. Il piano potrebbe essere ancora attivo: non lo considero annullato."
        )
    state_mod.append_turn(st, role="ora", text=ora, kind="answer")
    st["observations"] = observations[-12:]
    state_mod.save_ai_state(sess, st)
    add_step(trace, event="LOOP_BOUND")
    return CognitiveTurnResult(
        ok=True,
        mode="answer",
        ora_text=ora,
        session_id=sess.id,
        active_goal=ActiveGoal.model_validate(st.get("active_goal") or {}),
        memory_candidates=list(
            (last_decision.memory_candidates if last_decision else []) or []
        ),
        trace=public_trace(trace),
        ai_calls=ai_calls,
        tool_calls=tool_calls,
        context_calls=int(trace.get("context_calls") or 0),
        external_queries=external_queries,
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
        sources=public_sources[:MAX_SOURCES_UI],
        working_hint=working_hint,
        error="loop_bound" if ai_calls >= max_steps else None,
        situation=(situation_result or {}).get("situation")
        or st.get("active_situation_ref"),
    )


def _claims_unverified_life_os_persist(text: str, *, has_active_plan: bool) -> bool:
    """True when user-facing copy asserts durable Life OS objects without writes."""
    if not (text or "").strip() or not _PERSIST_CLAIM_RE.search(text):
        return False
    # Material/session claims need create_object this turn when plan already exists.
    if re.search(
        r"(?i)\b(materiale|sessione|ripasso|workspace|oggetto|cards?|deck)\b",
        text,
    ):
        return True
    # Plan/organize claims need create_plan when none is active yet.
    return not has_active_plan


def _claims_unverified_object_adapt(text: str, *, has_active_object: bool) -> bool:
    """True when copy asserts saved material was adapted without update_object."""
    if not has_active_object or not (text or "").strip():
        return False
    return bool(_ADAPT_CLAIM_RE.search(text))


async def _call_ai(
    *,
    decision_fn: Optional[DecisionFn],
    system: str,
    user: str,
) -> Optional[Dict[str, Any]]:
    if decision_fn is not None:
        try:
            return await decision_fn(system, user)
        except Exception:
            return None
    try:
        from llm.manager import get_manager

        mgr = get_manager()
        res = await mgr.chat(system=system, user=user, json_mode=True)
        text = getattr(res, "text", None) or ""
        return _parse_json(text)
    except Exception as e:
        logger.info("ai_core llm soft-fail: %s", type(e).__name__)
        return None


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:].strip()
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except Exception:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(t[start : end + 1])
                return data if isinstance(data, dict) else None
            except Exception:
                return None
        return None


def _compose_user_text(decision: CognitiveDecision) -> str:
    if decision.response_mode == "ask":
        parts = []
        if decision.message_to_user and decision.message_to_user != decision.question:
            parts.append(decision.message_to_user.strip())
        if decision.question:
            parts.append(decision.question.strip())
        return "\n\n".join(p for p in parts if p)[:800]
    return (decision.message_to_user or "").strip()[:800] or "Ok."
