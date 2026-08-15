"""Durable vs current/temporary vs goal-specific facts (domain-neutral)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_current_facts(state: Dict[str, Any]) -> Dict[str, Any]:
    raw = state.get("current_facts")
    return dict(raw) if isinstance(raw, dict) else {}


def apply_current_fact(
    state: Dict[str, Any],
    *,
    key: str,
    value: Any,
    scope: str = "temporary",
) -> None:
    """
    Store a conversation-current fact without rewriting durable Profile.
    scope: temporary | goal — never durable_profile.
    """
    if scope == "durable_profile":
        return  # refuse silent profile overwrite
    key = (key or "").strip()[:64]
    if not key:
        return
    facts = get_current_facts(state)
    facts[key] = {
        "value": value,
        "scope": scope if scope in ("temporary", "goal") else "temporary",
    }
    state["current_facts"] = facts


def current_facts_as_context(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expose current_facts to the AI payload with clear temporal grounding."""
    out: List[Dict[str, Any]] = []
    for k, raw in get_current_facts(state).items():
        if isinstance(raw, dict):
            val = raw.get("value")
            scope = raw.get("scope") or "temporary"
        else:
            val, scope = raw, "temporary"
        if val in (None, ""):
            continue
        out.append(
            {
                "statement": f"Fatto corrente ({scope}): {k} = {val}",
                "fact": f"{k}={val}",
                "source": "conversation",
                "authority": "user_stated",
                "status": "known",
                "grounding": "USER_STATED",
                "temporal_scope": scope,
                "ref": f"current_facts:{k}",
            }
        )
    return out


def merge_context_with_current(
    context_facts: List[Any],
    state: Dict[str, Any],
) -> List[Any]:
    """
    For active reasoning, current/temporary facts sit alongside durable ones.
    They do not delete durable Profile — AI sees both with different grounding.
    """
    extras = current_facts_as_context(state)
    if not extras:
        return context_facts
    # Prefer listing current facts first so they are visible for overrides
    return extras + list(context_facts)
