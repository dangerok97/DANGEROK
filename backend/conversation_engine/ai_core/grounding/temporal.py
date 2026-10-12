"""Durable vs current/temporary vs goal-specific facts (domain-neutral)."""
from __future__ import annotations

from typing import Any, Dict, List


def _origin_metadata(origin: str) -> Dict[str, Any]:
    """Code-owned authorship, not evidence supporting the stored proposition."""
    if origin == "model_state_update":
        return {
            "source": "model",
            "authority": "inferred",
            "status": "inferred",
            "grounding": "INFERENCE",
            "provenance": ["ai_core.state_updates"],
        }
    return {
        "source": "unknown",
        "authority": "unknown",
        "status": "unknown",
        "grounding": None,
        "provenance": [],
    }


def _recorded_origin(raw: Any) -> Dict[str, Any]:
    # This is the only attested envelope currently written by this helper.
    # Legacy records contain only value/scope. Arbitrary or nested tags do
    # not establish that the user said something or that a tool verified it.
    model_origin = _origin_metadata("model_state_update")
    if isinstance(raw, dict) and all(raw.get(k) == v for k, v in model_origin.items()):
        return model_origin
    return _origin_metadata("unknown")


def get_current_facts(state: Dict[str, Any]) -> Dict[str, Any]:
    raw = state.get("current_facts")
    return dict(raw) if isinstance(raw, dict) else {}


def apply_current_fact(
    state: Dict[str, Any],
    *,
    key: str,
    value: Any,
    scope: str = "temporary",
    origin: str = "unknown",
) -> None:
    """
    Store a conversation-current fact without rewriting durable Profile.
    scope: temporary | goal — never durable_profile.
    origin is supplied by the code caller, never extracted from value.
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
        **_origin_metadata(origin),
    }
    state["current_facts"] = facts


def current_facts_as_context(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Keep temporal scope and recorded authorship; never invent user evidence."""
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
                "statement": f"Contesto corrente ({scope}): {k} = {val}",
                "fact": f"{k}={val}",
                **_recorded_origin(raw),
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
