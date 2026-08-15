"""Bounded agentic reasoning loop — AI decides; tools/context observe."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from conversation_engine.ai_core.context_broker import ContextBroker, context_payload_stats
from conversation_engine.ai_core.fallback import (
    fallback_decision_after_malformed,
    provider_unavailable_result,
)
from conversation_engine.ai_core.governance import validate_decision
from conversation_engine.ai_core.grounding.temporal import merge_context_with_current
from conversation_engine.ai_core.models import (
    ActiveGoal,
    CognitiveDecision,
    CognitiveTurnResult,
    ContextFact,
    Observation,
)
from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT, build_user_payload
from conversation_engine.ai_core import state as state_mod
from conversation_engine.ai_core.tools.registry import (
    ToolRegistry,
    new_reasoning_epoch,
    tool_signature,
)
from conversation_engine.ai_core.trace import add_step, new_trace, public_trace
from conversation_engine.models import ConversationSession

logger = logging.getLogger("ora.ai_core.loop")

MAX_STEPS = 8
MAX_TOOL_CALLS = 5
MAX_EXTERNAL_QUERIES = 2
MAX_WRITE_CALLS = 4
MAX_OBJECT_GENERATIONS = 2
MAX_SOURCES_UI = 5

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
) -> CognitiveTurnResult:
    t0 = time.perf_counter()
    trace = new_trace()
    tools = ToolRegistry(db)
    broker = ContextBroker(db)
    st = state_mod.get_ai_state(sess)

    state_mod.append_turn(st, role="user", text=user_message)
    add_step(trace, event="TURN", user_message=user_message[:200])

    context_facts = await broker.retrieve(
        user_id=sess.user_id,
        user_message=user_message,
        active_goal=st.get("active_goal"),
        stage="A",
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
    life_os_writes_this_turn = 0
    update_object_ok_this_turn = False

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
                    decision.tool_call.resolved_capability if decision.tool_call else None
                ),
                has_question=bool(decision.question),
            )

        last_decision = decision
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
                if cap_try in (
                    "update_object",
                    "get_object",
                    "record_object_interaction",
                ) and not args_try.get("object_id") and not args_try.get("id"):
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
        # Refresh context merge after current_facts updates
        context_facts = merge_context_with_current(
            [f for f in context_facts if not (f.ref or "").startswith("current_facts:")],
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
            ora = _compose_user_text(decision)
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
                                and _claims_unverified_object_adapt(ora, has_active_object=True)
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
            )

        if mode == "context":
            cq = (decision.context_query or "").strip()
            more = await broker.retrieve(
                user_id=sess.user_id,
                user_message=user_message,
                active_goal=st.get("active_goal"),
                query=cq or user_message,
                stage="B",
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
            obs = Observation(
                kind="context",
                name="context_broker",
                status="ok" if more else "empty",
                payload={
                    "facts": [f.model_dump() for f in more],
                    "context_query": cq,
                    "item_count": len(more),
                    "grounding": "PERSONAL_CONTEXT",
                },
                provenance=[f.ref for f in more if f.ref],
            )
            observations.append(obs.model_dump())
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
                        payload={"failure_code": "UNSUPPORTED", "reason": "max_tool_calls"},
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
                        payload={"failure_code": "UNSUPPORTED", "reason": "max_write_calls"},
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
                if cap in (
                    "update_object",
                    "get_object",
                    "record_object_interaction",
                ) and not args.get("object_id") and not args.get("id"):
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
                },
            )
            tool_calls += 1
            trace["tool_calls"] = tool_calls
            if cap == "web_search":
                external_queries += 1
                trace["external_queries"] = external_queries
                st["external_query_count_session"] = int(
                    st.get("external_query_count_session") or 0
                ) + 1
            if cap in _WRITE_CAPS:
                write_calls += 1
                trace["write_calls"] = write_calls
            if cap in _LIFE_OS_PERSIST_CAPS and (
                obs.status in ("ok", "success")
                or (obs.payload or {}).get("status") == "success"
            ):
                life_os_writes_this_turn += 1
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
                obs.status in ("ok", "success")
                or payload.get("status") == "success"
            ):
                st["active_plan_id"] = payload["plan_id"]
            if payload.get("goal_id") and (
                obs.status in ("ok", "success")
                or payload.get("status") == "success"
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
                            "plan_id": payload.get("plan_id") or st.get("active_plan_id"),
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
