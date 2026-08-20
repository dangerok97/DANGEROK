"""DEV cognitive traces — no secrets / full profile dumps."""
from __future__ import annotations

import os
from typing import Any, Dict


def tracing_enabled() -> bool:
    return (os.environ.get("AI_CORE_TRACE") or os.environ.get("DEV") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def new_trace() -> Dict[str, Any]:
    return {
        "steps": [],
        "ai_calls": 0,
        "tool_calls": 0,
        "context_calls": 0,
    }


def add_step(trace: Dict[str, Any], **fields: Any) -> None:
    # Strip oversized payloads + exact coordinates
    safe = {}
    for k, v in fields.items():
        if k in ("profile_dump", "raw_document", "secrets", "latitude", "longitude", "coordinates"):
            continue
        if isinstance(v, str) and len(v) > 500:
            safe[k] = v[:500] + "…"
        elif isinstance(v, list) and len(v) > 12:
            safe[k] = v[:12]
        elif isinstance(v, dict):
            safe[k] = _redact_coords(v)
        else:
            safe[k] = v
    trace.setdefault("steps", []).append(safe)


def _redact_coords(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in ("latitude", "longitude", "lat", "lon", "lng", "coordinates"):
                out[k] = "[redacted]"
            else:
                out[k] = _redact_coords(v)
        return out
    if isinstance(obj, list):
        return [_redact_coords(x) for x in obj[:12]]
    return obj


def public_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
    # Always expose aggregate budgets (no secrets). Full steps only when TRACE on.
    base = {
        "ai_calls": trace.get("ai_calls", 0),
        "tool_calls": trace.get("tool_calls", 0),
        "context_calls": trace.get("context_calls", 0),
        "context_sources": list(trace.get("context_sources") or [])[:8],
        "context_candidate_count": trace.get("context_candidate_count", 0),
        "context_final_count": trace.get("context_final_count", 0),
        "context_payload_chars": trace.get("context_payload_chars", 0),
        "context_failure_status": trace.get("context_failure_status"),
        "uncertainty_turns": trace.get("uncertainty_turns", 0),
        "clarifications_requested": trace.get("clarifications_requested", 0),
        "clarification_context_attempts": trace.get(
            "clarification_context_attempts", 0
        ),
        "assumptions_used": trace.get("assumptions_used", 0),
        "repeated_question_prevented": trace.get(
            "repeated_question_prevented", 0
        ),
        "unresolved_uncertainty": bool(trace.get("unresolved_uncertainty", False)),
        "context_graph_calls": trace.get("context_graph_calls", 0),
        "context_graph_seed_count": trace.get("context_graph_seed_count", 0),
        "context_graph_candidate_edge_count": trace.get(
            "context_graph_candidate_edge_count", 0
        ),
        "context_graph_returned_edge_count": trace.get(
            "context_graph_returned_edge_count", 0
        ),
        "context_graph_depth": trace.get("context_graph_depth", 0),
        "context_graph_payload_chars": trace.get("context_graph_payload_chars", 0),
        "context_graph_failure_status": trace.get("context_graph_failure_status"),
        "context_graph_updates_proposed": trace.get(
            "context_graph_updates_proposed", 0
        ),
        "context_graph_updates_persisted": trace.get(
            "context_graph_updates_persisted", 0
        ),
        "context_graph_conflicts_detected": trace.get(
            "context_graph_conflicts_detected", 0
        ),
        "context_graph_supersessions": trace.get("context_graph_supersessions", 0),
        "external_queries": trace.get("external_queries", 0),
        "write_calls": trace.get("write_calls", 0),
        "object_generations": trace.get("object_generations", 0),
        "artifact_generations": trace.get(
            "object_generations", trace.get("artifact_generations", 0)
        ),
        "tool_names": [
            s.get("name")
            for s in (trace.get("steps") or [])
            if s.get("event") == "TOOL" and s.get("name")
        ][-8:],
        "events": [
            s.get("event")
            for s in (trace.get("steps") or [])
            if s.get("event")
            in (
                "PERSIST_NUDGE",
                "WRITE_BUDGET",
                "TOOL_BUDGET",
                "OBJECT_BUDGET",
                "ARTIFACT_BUDGET",
                "CLIENT_ACTION",
            )
        ][-6:],
    }
    if not tracing_enabled():
        return base
    out = _redact_coords(dict(trace))
    out.update(base)
    return out
