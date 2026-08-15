"""DEV cognitive traces — no secrets / full profile dumps."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


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
    # Strip oversized payloads
    safe = {}
    for k, v in fields.items():
        if k in ("profile_dump", "raw_document", "secrets"):
            continue
        if isinstance(v, str) and len(v) > 500:
            safe[k] = v[:500] + "…"
        elif isinstance(v, list) and len(v) > 12:
            safe[k] = v[:12]
        else:
            safe[k] = v
    trace.setdefault("steps", []).append(safe)


def public_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
    # Always expose aggregate budgets (no secrets). Full steps only when TRACE on.
    base = {
        "ai_calls": trace.get("ai_calls", 0),
        "tool_calls": trace.get("tool_calls", 0),
        "context_calls": trace.get("context_calls", 0),
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
            in ("PERSIST_NUDGE", "WRITE_BUDGET", "TOOL_BUDGET", "OBJECT_BUDGET", "ARTIFACT_BUDGET")
        ][-6:],
    }
    if not tracing_enabled():
        return base
    out = dict(trace)
    out.update(base)
    return out
