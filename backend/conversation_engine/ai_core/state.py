"""Lightweight generic conversation state for AI Core."""
from __future__ import annotations

from typing import Any, Dict, List

from conversation_engine.ai_core.grounding.temporal import apply_current_fact, get_current_facts
from conversation_engine.ai_core.models import ActiveGoal, CognitiveDecision, StateUpdate
from conversation_engine.models import ConversationSession, now_iso


def get_ai_state(sess: ConversationSession) -> Dict[str, Any]:
    meta = sess.meta or {}
    state = dict(meta.get("ai_core") or {})
    if "active_goal" not in state:
        state["active_goal"] = ActiveGoal().model_dump()
    if "recent_turns" not in state:
        state["recent_turns"] = []
    if "observations" not in state:
        state["observations"] = []
    if "relevant_context_refs" not in state:
        state["relevant_context_refs"] = []
    if "artifacts" not in state:
        state["artifacts"] = []
    if "pending_tool" not in state:
        state["pending_tool"] = None
    if "last_ai_decision" not in state:
        state["last_ai_decision"] = None
    if "tool_signatures" not in state:
        state["tool_signatures"] = []
    if "turn_tool_signatures" not in state:
        state["turn_tool_signatures"] = []
    if "reasoning_epoch" not in state:
        state["reasoning_epoch"] = None
    if "last_mutations" not in state:
        state["last_mutations"] = []
    if "current_facts" not in state:
        state["current_facts"] = {}
    if "external_query_count_session" not in state:
        state["external_query_count_session"] = 0
    if "active_object_ref" not in state:
        state["active_object_ref"] = None
    if "recent_object_refs" not in state:
        state["recent_object_refs"] = []
    if "current_plan_item_ref" not in state:
        state["current_plan_item_ref"] = None
    if "object_ids" not in state:
        state["object_ids"] = []
    if "recent_object_interactions" not in state:
        state["recent_object_interactions"] = []
    return state


def save_ai_state(sess: ConversationSession, state: Dict[str, Any]) -> None:
    sess.meta = dict(sess.meta or {})
    sess.meta["ai_core"] = state
    sess.meta["ui_mode"] = "ai_core"
    sess.touch()


def append_turn(
    state: Dict[str, Any],
    *,
    role: str,
    text: str,
    kind: str = "message",
) -> None:
    turns = list(state.get("recent_turns") or [])
    turns.append({"role": role, "text": (text or "")[:600], "kind": kind, "at": now_iso()})
    state["recent_turns"] = turns[-20:]


def apply_state_updates(state: Dict[str, Any], updates: List[StateUpdate] | List[dict]) -> None:
    goal = dict(state.get("active_goal") or {})
    for u in updates or []:
        if isinstance(u, StateUpdate):
            path, value, op = u.path, u.value, u.op
        else:
            path, value, op = u.get("path"), u.get("value"), u.get("op") or "set"
        if path == "active_goal.summary":
            if op == "clear":
                goal["summary"] = ""
            else:
                goal["summary"] = str(value or "")[:240]
        elif path == "active_goal.desired_outcome":
            if op == "clear":
                goal["desired_outcome"] = ""
            else:
                goal["desired_outcome"] = str(value or "")[:240]
        elif path == "active_goal.status":
            if str(value) in ("active", "paused", "done", "abandoned"):
                goal["status"] = str(value)
        elif path == "note":
            notes = list(state.get("notes") or [])
            if op == "append":
                notes.append(str(value or "")[:240])
            else:
                notes = [str(value or "")[:240]]
            state["notes"] = notes[-10:]
        elif path and str(path).startswith("current_facts."):
            key = str(path).split(".", 1)[1]
            if op == "clear":
                facts = get_current_facts(state)
                facts.pop(key, None)
                state["current_facts"] = facts
            else:
                apply_current_fact(state, key=key, value=value, scope="temporary")
    state["active_goal"] = goal


def record_decision(state: Dict[str, Any], decision: CognitiveDecision) -> None:
    state["last_ai_decision"] = decision.model_dump()
