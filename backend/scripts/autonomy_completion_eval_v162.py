"""Explicit, isolated source-to-Home autonomy acceptance.

The production admission, persisted wakes, Ambient worker, planner, executor,
evidence, preparation, completion and visibility outbox stay connected. Only
one fictional account and a recorded internal note exist. Allowed capabilities
are information.read and document.create; external effects are blocked.

Scripted mode is the mandatory offline contract. Live mode uses the configured
LLM with the same synthetic sources, and fails explicitly when unavailable.
Neither mode claims live third-party facts, a process restart or device receipt;
the separate v162 Mongo/process test establishes restart persistence.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import os
from pathlib import Path
import re
import time
from typing import Any
from unittest.mock import patch

from scripts import phase2_goal_outcome_eval_v140 as baseline
from scripts.phase1_read_provider_eval import _ReadBoundary, _safe_text

VERSION = "autonomy-completion-v162"
FIXTURE_REVISION = "personal_outcome_v1"
OWNER = "ora-synthetic-autonomy-owner-v162"
SCENARIOS = ("completed_result", "planning_outage", "home_write_retry",
             "source_revoked", "memory_revoked", "memory_corrected",
             "source_change_crash", "already_resolved", "irrelevant")
NO_GOAL_SCENARIOS = frozenset({"already_resolved", "irrelevant"})
LLM_KEYS = ("GEMINI_API_KEY", "GEMINI2_API_KEY", "GEMINI_API_KEY_2", "OPENAI_API_KEY",
            "GROQ_API_KEY", "MISTRAL_API_KEY")
ALLOWED = frozenset(baseline.EXPECTED.values())
MAX_MODEL_CALLS = 40
MAX_MODEL_HTTP_REQUESTS = 80
MAX_MODEL_FAILURES_REPORTED = 8
MODEL_PROVIDER_NAMES = frozenset({"gemini", "gemini2", "groq", "mistral", "openai", "ollama", "emergent"})
MODEL_FAILURE_KINDS = frozenset({"llm_error", "not_configured", "provider_unavailable", "quota",
    "rate_limit", "timeout", "network", "authentication", "configuration", "model_unavailable",
    "invalid_response", "internal", "cooldown"})
CASE_TIMEOUT_SECONDS = 240
MAX_DECISION_OBSERVATIONS = 12
DECISION_TEXT_LIMIT = 400
MAX_DIAGNOSTIC_PROPOSALS = 3
MAX_DIAGNOSTIC_PLAN_STEPS = 6
MAX_ASSESSMENT_REFS = 8
ASSESSMENT_TEXT_LIMIT = 280
MAX_DIAGNOSTIC_ADMISSIONS = 3
MAX_DIAGNOSTIC_SCANS = 3
MAX_DIAGNOSTIC_PLANNING = 4
PLANNING_ERROR_FIELDS = frozenset({"step", "parameters", "step_type", "effect_type",
    "reversibility", "intent", "capability_needed", "expected_result", "effect_target",
    "asks", "external_effect", "reaches_somebody_else", "input_refs", "ask_kind"})
PLANNING_ERROR_ISSUES = frozenset({"wrong_type", "unsupported_field", "conflicting_alias",
    "missing", "unsupported_value", "empty", "invalid_shape"})
PREPARATION_TEXT_LIMIT = 4000
MAX_PREPARATION_CLAIMS = 12
PREPARATION_CLAIM_TEXT_LIMIT = 280
MAX_PREPARATION_SOURCE_QUOTES = 3
FIXTURE_CONTEXT = (
    "Uso il mensile e prevedo di tenere l'archivio per 12 mesi; sto valutando le due formule "
    "e mi manca il confronto scritto di costi e vincoli. "
)
FIXTURE_NOTE = FIXTURE_CONTEXT + baseline.FACT
RESOLVED_FIXTURE_NOTE = (
    "Ho già ricevuto il confronto scritto dei costi e dei vincoli e ho scelto il mensile; "
    "non ho dubbi o verifiche aperte sulle due formule. " + baseline.FACT
)
WHY_NOW = (
    "Il confronto utile alla scelta sulle due formule è ancora da ricevere; "
    "non è documentata una scadenza."
)


class EvaluationFailure(RuntimeError):
    """Only fixed diagnostic codes, never provider errors or prompt contents."""


def require(condition, code):
    if not condition:
        raise EvaluationFailure(code)


@dataclass
class Probe:
    model_calls: list[dict[str, Any]] = field(default_factory=list)
    model_call_outcomes: list[dict[str, Any]] = field(default_factory=list)
    model_attempts: int = 0
    model_http_requests: int = 0
    structured_decisions: list[dict[str, Any]] = field(default_factory=list)
    structured_decisions_omitted: int = 0
    admission_observations: list[dict[str, Any]] = field(default_factory=list)
    planning_observations: list[dict[str, Any]] = field(default_factory=list)
    planning_observations_omitted: int = 0
    last_planning_run: tuple[str, str] | None = None  # Internal owned goal/run binding; never exported.
    discovery_results: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    ticks: list[dict[str, int]] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)
    blocked_effects: int = 0
    push_attempts: int = 0
    network: Any = None
    database: Any = None  # Evaluator-created DB only; never serialized.


def model_observations(probe):
    return {"real_model_executed": bool(probe.model_calls),
            "model_calls": probe.model_calls,
            "model_call_outcomes": probe.model_call_outcomes,
            "model_call_outcomes_scope": "manager_reported_final_chain",
            "model_call_elapsed_scope": "logical_call_including_fallbacks_and_pacing",
            "model_attempts": probe.model_attempts,
            "model_http_requests": probe.model_http_requests,
            "model_http_requests_scope": "httpx_async_send_attempts_including_runner_selected_gemini_sdk",
            "global_socket_dns_sandbox": False,
            "structured_decisions": probe.structured_decisions,
            "structured_decisions_omitted": probe.structured_decisions_omitted,
            "admission_observations": probe.admission_observations,
            "planning_observations": probe.planning_observations,
            "planning_observations_omitted": probe.planning_observations_omitted,
            "discovery_results": probe.discovery_results,
            "executed_capabilities": (probe.steps if len(probe.steps) <= MAX_DECISION_OBSERVATIONS
                                      else probe.steps[:2] + probe.steps[-(MAX_DECISION_OBSERVATIONS - 2):]),
            "executed_capabilities_omitted": max(0, len(probe.steps) - MAX_DECISION_OBSERVATIONS),
            # Failed calls may still be billable without returning usage.
            "token_usage_scope": "successful_responses_with_provider_usage_only"}


def _model_call_outcome(sequence, result, error, elapsed_ms):
    """Only fixed metadata from this response/exception, never error messages.

    Successful usage does not include cooldown skips or earlier pacing chains.
    The manager's process-level last-attempt list can belong to an older call
    and must not be borrowed to fill those observational gaps.
    """
    def allowed(value, choices):
        return value if type(value) is str and value in choices else "unknown"

    usage = getattr(result, "usage", None)
    failures = (getattr(error, "attempts", ()) if error is not None
                else usage.get("failover_errors", ()) if isinstance(usage, dict) else ())
    fallbacks = []
    if isinstance(failures, (list, tuple)):
        for item in failures[:MAX_MODEL_FAILURES_REPORTED]:
            if error is None and type(item) is str:
                parts = item.split(":")
                if len(parts) != 2:
                    continue
                provider, kind = parts
            elif error is not None and isinstance(item, dict):
                provider, kind = item.get("provider"), item.get("failure_kind")
            else:
                continue
            fallbacks.append({"provider": allowed(provider, MODEL_PROVIDER_NAMES),
                              "failure_kind": allowed(kind, MODEL_FAILURE_KINDS)})
    return {
        "sequence": sequence,
        "outcome": "cancelled" if isinstance(error, asyncio.CancelledError) else "failed" if error else "succeeded",
        "provider": allowed(getattr(result, "provider", None), MODEL_PROVIDER_NAMES),
        "failure_kind": allowed(getattr(error, "kind", None), MODEL_FAILURE_KINDS) if error else None,
        "elapsed_ms": round(elapsed_ms, 1) if math.isfinite(elapsed_ms) and elapsed_ms >= 0 else None,
        "fallbacks": fallbacks,
    }


def _response_kind(value):
    return ("object" if isinstance(value, dict) else "array" if isinstance(value, list)
            else "none" if value is None else "text" if isinstance(value, str) else "other")


def _decision_fields(value, fields, *, limit=DECISION_TEXT_LIMIT):
    """Allowlisted synthetic decision fields, never raw model/provider payloads."""
    if not isinstance(value, dict):
        return {"response_kind": _response_kind(value)}
    out = {key: _safe_text(value[key], limit) for key in fields
           if type(value.get(key)) is str}
    shortened = [key for key in fields if type(value.get(key)) is str
                 and len(value[key]) > limit]
    if shortened:
        out["truncated_fields"] = shortened
    return out


def _outcome_assessment(value):
    """Observe a bounded decision summary without interpreting or enforcing it."""
    out = {"response_kind": _response_kind(value)}
    if not isinstance(value, dict):
        return out
    out.update(_decision_fields(value, (
        "desired_outcome", "outcome_state", "remaining_internal_work",
    ), limit=ASSESSMENT_TEXT_LIMIT))
    for key in ("supporting_refs", "completion_refs"):
        refs = value.get(key)
        if not isinstance(refs, list):
            continue
        out[key] = [_safe_text(ref, 160) for ref in refs[:MAX_ASSESSMENT_REFS]
                    if type(ref) is str]
        out[key + "_omitted"] = max(0, len(refs) - MAX_ASSESSMENT_REFS)
    return out


def _diagnostic_refs(value, key):
    refs = value.get(key)
    out = {key + "_kind": _response_kind(refs)}
    if isinstance(refs, list):
        out.update({key: [_safe_text(ref, 160) for ref in refs[:MAX_ASSESSMENT_REFS]
                          if type(ref) is str],
                    key + "_count": len(refs),
                    key + "_omitted": max(0, len(refs) - MAX_ASSESSMENT_REFS)})
    return out


def _preparation_text_fields(value, key):
    content = value.get(key)
    out = {key + "_kind": _response_kind(content)}
    if type(content) is str:
        redacted = _safe_text(content, PREPARATION_TEXT_LIMIT + 1)
        out.update({key: redacted[:PREPARATION_TEXT_LIMIT], key + "_characters": len(content),
                    key + "_truncated": len(redacted) > PREPARATION_TEXT_LIMIT})
    return out


def _error_code(value):
    return (_safe_text(value, 80) if type(value) is str
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", value) else None)


def _preparation_claim_review(value):
    rows = value.get("claim_review")
    out = {"claim_review_kind": _response_kind(rows)}
    if isinstance(rows, list):
        out.update({"claim_review_count": len(rows),
                    "claim_review_omitted": max(0, len(rows) - MAX_PREPARATION_CLAIMS),
                    "claim_review": []})
        for item in rows[:MAX_PREPARATION_CLAIMS]:
            observed = _decision_fields(item, ("claim", "premises", "support", "correction"),
                                        limit=PREPARATION_CLAIM_TEXT_LIMIT)
            if isinstance(item, dict):
                observed.update(_diagnostic_refs(item, "evidence_ids"))
                quotes = item.get("source_quotes")
                observed["source_quotes_kind"] = _response_kind(quotes)
                if isinstance(quotes, list):
                    observed.update({"source_quotes_count": len(quotes),
                        "source_quotes_omitted": max(0, len(quotes) - MAX_PREPARATION_SOURCE_QUOTES),
                        "source_quotes": []})
                    for quote in quotes[:MAX_PREPARATION_SOURCE_QUOTES]:
                        quoted = {"response_kind": _response_kind(quote)}
                        if isinstance(quote, dict):
                            for key, limit in (("evidence_id", 160), ("quote", PREPARATION_CLAIM_TEXT_LIMIT)):
                                if type(quote.get(key)) is str:
                                    redacted = _safe_text(quote[key], limit + 1)
                                    quoted.update({key: redacted[:limit],
                                        key + "_characters": len(quote[key]),
                                        key + "_truncated": len(redacted) > limit})
                        observed["source_quotes"].append(quoted)
            out["claim_review"].append(observed)
    return out


def _admission_fields(source):
    from agent.reasoning import GOAL_DECISION_FIELDS
    out = _decision_fields(source, ("id", "agent_review_revision"), limit=80)
    for key in ("state", "outcome", "error_kind"):
        value = source.get("agent_review_" + key)
        # These are code-owned enum/error names, never exception messages.
        out[key] = (_safe_text(value, 80) if type(value) is str
                    and re.fullmatch(r"[A-Za-z_]{0,80}", value) else None)
    attempts = source.get("agent_review_attempts")
    out["attempts"] = attempts if type(attempts) is int and attempts >= 0 else None
    out["has_due"] = bool(source.get("agent_review_due"))
    out["has_question"] = bool(source.get("agent_review_question"))
    fields = source.get("agent_review_invalid_fields")
    out["invalid_fields"] = list(dict.fromkeys(
        item for item in fields if type(item) is str and item in GOAL_DECISION_FIELDS
    ))[:10] if isinstance(fields, list) else []
    return out


async def _synthetic_diagnostics_allowed(db, owner):
    if owner != OWNER:
        return False
    try:
        return bool(await db.eval_guards.find_one({"_id": VERSION, "owner": OWNER}))
    except Exception:
        return False


async def _planning_error(db, goal, *, observed_run=None):
    """Observe a current owned protocol failure; missing diagnostics are harmless."""
    from agent.service import MAX_PLAN_STEPS, MAX_PLANNING_ATTEMPTS

    if (not isinstance(goal, dict) or goal.get("owner_id") != OWNER
            or type(goal.get("id")) is not str or goal.get("planning_unavailable") is not True):
        return None
    if (not isinstance(observed_run, tuple) or len(observed_run) != 2
            or observed_run[0] != goal["id"] or type(observed_run[1]) is not str
            or not re.fullmatch(r"run_[0-9a-f]{16}", observed_run[1])):
        return None
    attempt = goal.get("planning_attempts")
    if type(attempt) is not int or not 1 <= attempt <= MAX_PLANNING_ATTEMPTS:
        return None
    if not await _synthetic_diagnostics_allowed(db, OWNER):
        return None
    try:
        row = await db.agent_journal.find_one({
            "owner_id": OWNER, "goal_id": goal["id"], "kind": "planning_protocol_invalid",
            "detail.run_id": observed_run[1], "detail.attempt": attempt,
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        }, {"_id": 0, "detail.validation_errors": 1}, sort=[("at", -1)])
        errors = (row or {}).get("detail", {}).get("validation_errors")
        if not isinstance(errors, list):
            return None
        allowed = [{"index": error["index"], "field": error["field"], "issue": error["issue"]}
            for error in errors[:1] if isinstance(error, dict)
            and type(error.get("index")) is int and 0 <= error["index"] < MAX_PLAN_STEPS
            and type(error.get("field")) is str and error["field"] in PLANNING_ERROR_FIELDS
            and type(error.get("issue")) is str and error["issue"] in PLANNING_ERROR_ISSUES]
        return {"attempt": attempt, "has_due": bool(goal.get("next_run_at")),
                "validation_errors": allowed} if allowed else None
    except Exception:
        return None


def _scan_result_fields(result):
    from opportunities.models import ScanResult
    if not isinstance(result, ScanResult):
        return {"response_kind": _response_kind(result)}
    known = {"proposta non leggibile", "identità non stabile", "senza cosa o senza perché",
             "nessun fatto reale a sostegno", "proposta fuori contratto",
             "partenze distinte richiedono evidenze separate",
             "routine distinte richiedono evidenze separate"}
    known.update("già chiusa come «" + status + "»" for status in (
        "dismissed", "suppressed", "resolved", "expired"))
    skipped = result.skipped
    return {"silence": result.silence, "unavailable": result.unavailable,
            "created_count": len(result.created), "updated_count": len(result.updated),
            "skipped_count": len(skipped),
            "skipped": [{"reason": _safe_text(item["reason"], 160)
                         if type(item.get("reason")) is str and item["reason"] in known else "unrecognized_reason"}
                        for item in skipped[:MAX_ASSESSMENT_REFS]],
            "skipped_omitted": max(0, len(skipped) - MAX_ASSESSMENT_REFS)}


def _decision_result(stage, value):
    out = {"response_kind": _response_kind(value)}
    if not isinstance(value, dict):
        return out
    out.update(_decision_fields(value, (
        "outcome", "reasoning", "objective", "desired_outcome", "question", "reason_for_silence",
        "planning_outcome", "plan_summary", "expected_outcome", "what_is_missing", "decision", "step_id",
    )))
    if "outcome_assessment" in value:
        out["outcome_assessment"] = _outcome_assessment(value["outcome_assessment"])
    if stage == "reconsider":
        for key, expected_type, kind in (
            ("wait_minutes", int, "integer"), ("wait_until", str, "text"),
            ("requires_user_input", bool, "boolean"), ("requires_user_authority", bool, "boolean"),
            ("ask_kind", str, "text"),
        ):
            if key in value:
                out[key + "_kind"] = kind if type(value[key]) is expected_type else _response_kind(value[key])
                if type(value[key]) is expected_type:
                    out[key] = _safe_text(value[key], 80) if expected_type is str else value[key]
        if "asks" in value:
            out["asks_kind"] = _response_kind(value["asks"])
            if type(value["asks"]) is str:
                out["has_asks"] = bool(value["asks"].strip())
        if "revised_steps" in value:
            steps = value["revised_steps"]
            out["revised_steps_kind"] = _response_kind(steps)
            if isinstance(steps, list):
                out["revised_steps_count"] = len(steps)
                out["revised_steps"] = [_decision_fields(item, (
                    "step_type", "type", "capability_needed", "intent", "expected_result",
                ), limit=160) for item in steps[:MAX_DIAGNOSTIC_PLAN_STEPS]]
                out["revised_steps_omitted"] = max(0, len(steps) - MAX_DIAGNOSTIC_PLAN_STEPS)
        if "replace_step_ids" in value:
            out.update(_diagnostic_refs(value, "replace_step_ids"))
    if stage in ("preparation_generation", "preparation_audit"):
        out.update(_preparation_text_fields(value, "content"))
        out.update(_diagnostic_refs(value, "evidence_ids"))
        out["verified_kind"] = ("boolean" if type(value.get("verified")) is bool
                                else _response_kind(value.get("verified")))
        if type(value.get("verified")) is bool:
            out["verified"] = value["verified"]
        if stage == "preparation_audit":
            out.update(_decision_fields(value, ("reason",)))
            out.update(_preparation_claim_review(value))
    if stage == "make_plan":
        steps = value.get("steps")
        out["steps_kind"] = _response_kind(steps)
        if isinstance(steps, list):
            out["steps_count"] = len(steps)
            out["steps"] = [_decision_fields(item, (
                "step_type", "capability_needed", "intent", "expected_result",
            ), limit=160) for item in steps[:MAX_DIAGNOSTIC_PLAN_STEPS]]
            out["steps_omitted"] = max(0, len(steps) - MAX_DIAGNOSTIC_PLAN_STEPS)
    if stage in ("opportunity_scan", "opportunity_audit"):
        out["verified_kind"] = ("boolean" if type(value.get("verified")) is bool
                                else _response_kind(value.get("verified")))
        if type(value.get("verified")) is bool:
            out["verified"] = value["verified"]
        proposals = value.get("opportunities")
        out["opportunities_kind"] = _response_kind(proposals)
        if isinstance(proposals, list):
            out["opportunities_count"] = len(proposals)
            out["opportunities"] = []
            for item in proposals[:MAX_DIAGNOSTIC_PROPOSALS]:
                observed = _decision_fields(item, (
                    "identity_key", "what", "initiative", "why_it_matters", "what_i_can_do",
                ))
                if isinstance(item, dict) and "outcome_assessment" in item:
                    observed["outcome_assessment"] = _outcome_assessment(item["outcome_assessment"])
                if isinstance(item, dict):
                    observed.update(_diagnostic_refs(item, "evidence_refs"))
                out["opportunities"].append(observed)
            out["opportunities_omitted"] = max(0, len(proposals) - MAX_DIAGNOSTIC_PROPOSALS)
    return out


def _decision_input(stage, value, kwargs):
    """Shapes and lengths explain missing context without exporting source text."""
    if not isinstance(value, dict):
        return {"input_kind": _response_kind(value)}
    if stage == "decide_goal":
        context = value.get("source_context")
        return {"source_context_count": len(context) if isinstance(context, list) else None,
                "source_context_unavailable": value.get("source_context_unavailable")
                if type(value.get("source_context_unavailable")) is bool else None}
    if stage in ("preparation_generation", "preparation_audit"):
        evidence = value.get("evidence")
        out = {"evidence_kind": _response_kind(evidence),
               "evidence_count": len(evidence) if isinstance(evidence, list) else None,
               "evidence_truncated": value.get("evidence_truncated")
               if type(value.get("evidence_truncated")) is bool else None}
        if isinstance(evidence, list):
            out.update(_diagnostic_refs({"evidence_ids": [row.get("id") for row in evidence
                                                         if isinstance(row, dict)]}, "evidence_ids"))
        out.update(_decision_fields(kwargs.get("execution"), ("goal_id", "step_id"), limit=80))
        if stage == "preparation_audit":
            out.update(_preparation_text_fields(value, "draft"))
        return out
    if stage not in ("opportunity_scan", "opportunity_audit"):
        out = _decision_fields(value, ("status",), limit=60)
        if stage == "reconsider":
            event = kwargs.get("what_happened")
            out["what_happened_kind"] = _response_kind(event)
            if isinstance(event, dict):
                technical = {}
                step = event.get("step")
                if isinstance(step, dict):
                    technical.update(_decision_fields({"step_id": step.get("id"), "step_type": step.get("type")},
                                                       ("step_id", "step_type"), limit=80))
                result = event.get("result")
                if isinstance(result, dict):
                    technical.update(_decision_fields(result, ("status",), limit=40))
                    technical["error_type"] = _error_code(result.get("problem"))
                    if type(result.get("worth_retrying")) is bool:
                        technical["retryable"] = result["worth_retrying"]
                out["what_happened"] = technical
        evidence = kwargs.get("evidence")
        out["evidence_kind"] = _response_kind(evidence)
        if isinstance(evidence, (list, dict)):
            out["evidence_entries"] = len(evidence)
        plan = kwargs.get("plan")
        if isinstance(plan, dict):
            out["plan"] = _decision_fields(plan, ("status",), limit=60)
            steps = plan.get("steps")
            if isinstance(steps, list):
                out["plan"]["steps_count"] = len(steps)
                out["plan"]["steps"] = [_decision_fields(item, (
                    "id", "step_type", "type", "capability_needed", "status",
                ), limit=100) for item in steps[:MAX_DIAGNOSTIC_PLAN_STEPS]]
                out["plan"]["steps_omitted"] = max(0, len(steps) - MAX_DIAGNOSTIC_PLAN_STEPS)
        return out
    counts = {key: len(value[key]) for key in (
        "memories", "documents", "calendar", "money", "life_profile", "what_changed",
        "unavailable_sources", "unavailable_memory_refs",
    ) if isinstance(value.get(key), (list, dict))}
    changes = value.get("what_changed")
    out = {"collection_counts": counts,
            "change_after_lengths": [len(item["from_to"]["after"]) for item in
                (changes[:MAX_DIAGNOSTIC_PROPOSALS] if isinstance(changes, list) else [])
                if isinstance(item, dict) and isinstance(item.get("from_to"), dict)
                and type(item["from_to"].get("after")) is str]}
    if stage == "opportunity_audit":
        out["proposed"] = _decision_result("opportunity_scan", kwargs.get("proposed"))
    return out


def _prepared_text_fields(value):
    original = value if isinstance(value, str) else ""
    # Redact before the boundary; one extra character tells whether the
    # exported copy was cut even if redaction expanded a short credential.
    redacted = _safe_text(original, 6001)
    return {"prepared_text": redacted[:6000],
            "prepared_text_truncated": len(redacted) > 6000,
            "prepared_text_characters": len(original)}


async def failure_state(probe):
    """Read bounded synthetic state after a gate fails; never change that state."""
    db = probe.database
    if db is None:
        return {"available": False, "reason": "NO_EVALUATOR_DATABASE"}
    try:
        if not await db.eval_guards.find_one({"_id": VERSION, "owner": OWNER}):
            return {"available": False, "reason": "SYNTHETIC_DIAGNOSTIC_GUARD_MISSING"}
        query = {"owner_id": OWNER}
        goals = await db.agent_goals.find(query, {"_id": 0}).to_list(2)
        rows = []
        for goal in goals:
            goal_query = {"owner_id": OWNER, "goal_id": goal["id"]}
            row = _decision_fields(goal, ("status", "rationale", "desired_outcome"))
            for key in ("success_criteria", "source_refs", "prepared_sources"):
                row.update(_diagnostic_refs(goal, key))
            row.update({
                "requires_user_input": goal.get("requires_user_input") is True,
                "requires_user_authority": goal.get("requires_user_authority") is True,
                "has_next_run_at": bool(goal.get("next_run_at")),
                "planning_unavailable": goal.get("planning_unavailable") is True,
                **_prepared_text_fields(goal.get("prepared_text")),
                "source_refs_count": len(goal.get("source_refs") or []),
                "prepared_sources_count": len(goal.get("prepared_sources") or []),
                "evidence_count": await db.agent_evidence.count_documents(goal_query),
                "current_evidence_count": await db.agent_evidence.count_documents(
                    {**goal_query, "superseded": {"$ne": True}}),
            })
            planning_error = await _planning_error(db, goal, observed_run=probe.last_planning_run)
            if planning_error is not None:
                row["planning_error"] = planning_error
            plans = await db.agent_plans.find(goal_query, {"_id": 0}).sort("updated_at", -1).to_list(2)
            row["plans"] = []
            for plan in plans:
                item = _decision_fields(plan, ("status", "plan_summary"))
                steps = plan.get("steps") or []
                counts = {}
                for step in steps:
                    status = step.get("status")
                    if status in ("pending", "running", "waiting", "succeeded", "failed", "skipped", "blocked", "cancelled"):
                        counts[status] = counts.get(status, 0) + 1
                item.update({
                    "steps_count": len(steps), "step_status_counts": counts,
                    "steps": [_decision_fields(step, (
                        "step_type", "capability_needed", "status", "note",
                    ), limit=160) for step in steps[:MAX_DIAGNOSTIC_PLAN_STEPS]],
                    "steps_omitted": max(0, len(steps) - MAX_DIAGNOSTIC_PLAN_STEPS),
                })
                row["plans"].append(item)
            row["plans_count"] = await db.agent_plans.count_documents(goal_query)
            rows.append(row)
        sources = await db.opportunities.find(query, {"_id": 0}).to_list(MAX_DIAGNOSTIC_ADMISSIONS)
        return {"available": True, "goals_count": await db.agent_goals.count_documents(query), "goals": rows,
                "admission_sources_count": await db.opportunities.count_documents(query),
                "admission_sources": [_admission_fields(source) for source in sources]}
    except Exception as exc:
        return {"available": False, "reason": type(exc).__name__[:80]}


class BlockedPush:
    name = "evaluation_no_device"

    def __init__(self, probe):
        self.probe = probe

    async def send(self, **kwargs):
        self.probe.push_attempts += 1
        raise EvaluationFailure("DEVICE_SEND_FORBIDDEN")

    async def cancel(self, **kwargs):
        return {"ok": True, "provider": self.name}


@contextmanager
def isolated_engine(db, *, mode="scripted", scenario="completed_result", probe=None):
    """Bound effects without replacing the worker, persistence or Home handoff."""
    from agent import preparation, reasoning
    from agent.capabilities import CapabilityResolver
    from agent.execution import StepExecutor
    from agent.models import AgentBudget
    from agent.service import AgentService
    from delivery import provider, reasoning as delivery_reasoning
    from delivery.service import DeliveryService
    from llm.manager import ProviderManager
    from opportunities import reasoning as opportunity_reasoning
    from opportunities.service import OpportunityService

    require(mode in ("scripted", "live"), "UNKNOWN_MODE")
    require(scenario in SCENARIOS, "UNKNOWN_SCENARIO")
    probe = probe or Probe()
    # Scope is normally blocked; only ProviderManager.chat may enable the
    # exact HTTPS model endpoints already audited by the public-read harness.
    boundary = _ReadBoundary(model_live=mode == "live", provider_reply=None)
    probe.network = boundary
    original_chat, original_step = ProviderManager.chat, StepExecutor.run
    original_advance, original_note = AgentService.advance, DeliveryService.note_activity
    original_build_plan = AgentService._build_plan
    original_scan = OpportunityService.scan
    original_decide_goal, original_discover = reasoning.decide_goal, opportunity_reasoning.scan
    original_audit = opportunity_reasoning.audit_proposals
    scan_owner = ContextVar("autonomy_eval_scan_owner", default=None)
    original_prepare = preparation.prepare
    original_prepare_model = baseline.scripted_draft if mode == "scripted" else reasoning._ask_model
    preparation_context = ContextVar("autonomy_eval_preparation", default=None)
    original_service_reconsider, original_reconsider = AgentService._reconsider, reasoning.reconsider
    reconsider_context = ContextVar("autonomy_eval_reconsider", default=False)
    base_plan = baseline.scripted_make_plan if mode == "scripted" else reasoning.make_plan
    base_verify = baseline.scripted_verify if mode == "scripted" else reasoning.verify_goal
    base_choose = baseline.scripted_choose if mode == "scripted" else reasoning.choose_next_action

    async def observed_chat(self, *args, **kwargs):
        probe.model_attempts += 1
        require(mode == "live", "SCRIPTED_CALLED_REAL_MODEL")
        if probe.model_attempts > MAX_MODEL_CALLS:
            boundary.blocked.append("MODEL_CALL_BOUND_EXCEEDED")
            raise EvaluationFailure("MODEL_CALL_BOUND_EXCEEDED")
        http_before = probe.model_http_requests
        sequence, started = probe.model_attempts, time.perf_counter()
        result, error = None, None
        token = boundary.scope.set("model")
        try:
            result = await original_chat(self, *args, **kwargs)
            usage = result.usage if isinstance(getattr(result, "usage", None), dict) else {}
            probe.model_calls.append({
                "provider": str(result.provider)[:50], "model": str(result.model)[:100],
                "usage": {key: value for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                          if type(value := usage.get(key)) is int and value >= 0},
            })
            if probe.model_http_requests <= http_before:
                # A pre-existing SDK client or another transport must not
                # produce green evidence with an unobserved request budget.
                boundary.blocked.append("MODEL_HTTP_NOT_OBSERVED")
                raise EvaluationFailure("MODEL_HTTP_NOT_OBSERVED")
            return result
        except BaseException as exc:
            error = exc
            raise
        finally:
            boundary.scope.reset(token)
            if len(probe.model_call_outcomes) < MAX_MODEL_CALLS:
                probe.model_call_outcomes.append(_model_call_outcome(
                    sequence, result, error, (time.perf_counter() - started) * 1000,
                ))

    async def observed_decision(stage, call, *args, **kwargs):
        input_key = ("situation" if stage == "decide_goal" else "snapshot"
                     if stage in ("opportunity_scan", "opportunity_audit") else "goal")
        payload = args[0] if args else kwargs.get(input_key)
        observation = {"stage": stage, "model_attempts_before": probe.model_attempts,
                       "input": _decision_input(stage, payload, kwargs)}
        try:
            result = await call(*args, **kwargs)
        except BaseException as exc:
            # Keep cancellation/error identity; never export an exception message.
            observation.update({"response_kind": "raised", "exception_type": type(exc).__name__[:80]})
            raise
        else:
            observation.update(_decision_result(stage, result))
            return result
        finally:
            observation["model_attempts_after"] = probe.model_attempts
            observation["sequence"] = len(probe.structured_decisions) + probe.structured_decisions_omitted + 1
            if len(probe.structured_decisions) >= MAX_DECISION_OBSERVATIONS:
                # Keep the initial context and latest preparation stages as
                # separate observations, not an assumed generation/audit pair.
                evict = min(2, MAX_DECISION_OBSERVATIONS - 1)
                if MAX_DECISION_OBSERVATIONS >= 5:
                    protected = {0, 1}
                    for saved_stage in ("preparation_generation", "preparation_audit"):
                        if stage == saved_stage:
                            continue  # The incoming observation supersedes it.
                        for index in range(len(probe.structured_decisions) - 1, -1, -1):
                            if probe.structured_decisions[index].get("stage") == saved_stage:
                                protected.add(index)
                                break
                    evict = next(index for index in range(len(probe.structured_decisions)) if index not in protected)
                probe.structured_decisions.pop(evict)
                probe.structured_decisions_omitted += 1
            probe.structured_decisions.append(observation)

    async def available(self, owner_id):
        require(self.db is db and owner_id == OWNER, "CAPABILITY_OWNER_BOUNDARY")
        return [{"capability": cap, "status": "available_real", "can_be_used_now": True,
                 "really_does_something": True, "changes_something_in_the_world": False,
                 "why_not": None} for cap in sorted(ALLOWED)]


    async def build_plan(self, owner_id, goal, run, *args, **kwargs):
        # Attempt numbers restart after a new source or explicit retry. The
        # existing AgentRun identity prevents that cycle from borrowing an
        # older protocol error; missing observation means no attribution.
        if self.db is db and owner_id == goal.owner_id == OWNER:
            probe.last_planning_run = None
            if (run.owner_id == OWNER and run.goal_id == goal.id
                    and await _synthetic_diagnostics_allowed(db, owner_id)):
                probe.last_planning_run = (goal.id, run.id)
        return await original_build_plan(self, owner_id, goal, run, *args, **kwargs)

    async def step(self, owner_id, goal, item, **kwargs):
        same_owner = self.db is db and owner_id == OWNER and goal.owner_id == OWNER
        marked = same_owner and await _synthetic_diagnostics_allowed(db, owner_id)
        identity = (_decision_fields({"capability": item.capability_needed, "step_id": item.id,
                                      "step_type": item.step_type},
                                     ("capability", "step_id", "step_type"), limit=80) if marked else {})
        local_prepare = item.step_type == "prepare" and item.capability_needed == "" and marked
        if (not same_owner or (item.capability_needed not in ALLOWED and not local_prepare)
                or item.step_type == "execute"):
            probe.blocked_effects += 1
            probe.steps.append({**identity, "status": "blocked", "error_type": "STEP_EFFECT_OR_OWNER_BOUNDARY",
                                "retryable": False, "exception_type": "EvaluationFailure"})
            raise EvaluationFailure("STEP_EFFECT_OR_OWNER_BOUNDARY")
        try:
            result = await original_step(self, owner_id, goal, item, **kwargs)
        except BaseException as exc:
            probe.steps.append({**identity, "status": "raised", "error_type": _error_code(type(exc).__name__),
                                "retryable": None, "exception_type": type(exc).__name__[:80]})
            raise
        # Existing unit callers have no evaluator marker. Keep their minimal
        # code-owned capability/status trace; source-linked diagnostics are
        # available only in the marked synthetic account.
        observed = {**(identity if marked else {"capability": item.capability_needed}),
                    "status": _safe_text(getattr(result, "status", ""), 80)}
        if marked:
            observed.update({"error_type": _error_code(getattr(result, "error_type", None)),
                             "retryable": result.retryable
                             if type(getattr(result, "retryable", None)) is bool else None})
        probe.steps.append(observed)
        return result

    async def prepare(prepare_db, owner_id, goal, item):
        enabled = (prepare_db is db and owner_id == goal.owner_id == OWNER
                   and await _synthetic_diagnostics_allowed(db, owner_id))
        token = preparation_context.set({"goal_id": goal.id, "step_id": item.id} if enabled else None)
        try:
            return await original_prepare(prepare_db, owner_id, goal, item)
        finally:
            preparation_context.reset(token)

    async def prepare_model(system, user, *, response_schema=None):
        schema_kwargs = {"response_schema": response_schema} if response_schema is not None else {}
        context = preparation_context.get()
        if context is None or not await _synthetic_diagnostics_allowed(db, OWNER):
            return await original_prepare_model(system, user, **schema_kwargs)
        try:
            payload = json.loads(user)
        except (TypeError, ValueError):
            payload = None
        stage = ("preparation_audit" if isinstance(payload, dict) and "draft" in payload and "evidence" in payload
                 else "preparation_generation" if isinstance(payload, dict)
                 and all(key in payload for key in ("goal", "step", "evidence")) else "preparation_call")

        async def call(_payload, **_kwargs):
            return await original_prepare_model(system, user, **schema_kwargs)

        return await observed_decision(stage, call, payload, execution=context)

    async def service_reconsider(self, owner_id, goal, *args, **kwargs):
        enabled = (self.db is db and owner_id == getattr(goal, "owner_id", None) == OWNER
                   and await _synthetic_diagnostics_allowed(db, owner_id))
        token = reconsider_context.set(enabled)
        try:
            return await original_service_reconsider(self, owner_id, goal, *args, **kwargs)
        finally:
            reconsider_context.reset(token)

    async def reconsider(*args, **kwargs):
        if not reconsider_context.get() or not await _synthetic_diagnostics_allowed(db, OWNER):
            return await original_reconsider(*args, **kwargs)
        return await observed_decision("reconsider", original_reconsider, *args, **kwargs)

    async def bounded_first_read(self, owner_id, goal_id, **kwargs):
        # A documented technical interruption after one real read proves that
        # completion comes from a subsequent persisted wake, not a single call.
        if self.db is db and owner_id == OWNER and not await db.agent_evidence.count_documents({
            "owner_id": OWNER, "goal_id": goal_id, "provenance.capability": "information.read",
        }):
            kwargs["budget"] = AgentBudget(max_steps=1)
        return await original_advance(self, owner_id, goal_id, **kwargs)

    async def plan_result(*args, **kwargs):
        if scenario == "planning_outage" and "planning_unavailable_once" not in probe.faults:
            probe.faults.append("planning_unavailable_once")
            return None
        result = await base_plan(*args, **kwargs)
        if mode == "scripted" and "memory_corrected_between_wakes" in probe.faults:
            for item in (result or {}).get("steps", []):
                item["expected_result"] = item.get("expected_result", "").replace(
                    "120 euro", "150 euro").replace("60 euro", "30 euro")
        return result

    async def plan(*args, **kwargs):
        return await observed_decision("make_plan", plan_result, *args, **kwargs)

    async def verify(*args, **kwargs):
        return await observed_decision("verify_goal", base_verify, *args, **kwargs)

    async def choose(*args, **kwargs):
        return await observed_decision("choose_next_action", base_choose, *args, **kwargs)

    async def note(self, *args, **kwargs):
        provenance = kwargs.get("provenance") or {}
        current = await db.agent_goals.find_one({
            "owner_id": OWNER, "id": provenance.get("goal"), "status": "completed",
        }) if provenance.get("agent") == "visibility" else None
        if (scenario == "home_write_retry" and current
                and "home_write_failed_once" not in probe.faults):
            probe.faults.append("home_write_failed_once")
            raise ConnectionError("synthetic_home_write_failure")
        return await original_note(self, *args, **kwargs)

    async def scripted_goal_decision(*args, **kwargs):
        if scenario == "irrelevant":
            return {"outcome": "no_goal", "reasoning": "Nessun bisogno documentato."}
        if scenario == "already_resolved":
            return {"outcome": "no_goal", "reasoning": "Confronto già ricevuto e scelta conclusa, senza lavoro residuo."}
        answer = baseline.scripted_goal()
        answer["why_now"] = WHY_NOW
        answer["stop_conditions"] = ["La nota viene ritirata o revocata", "Il confronto non è più utile"]
        return answer

    async def scan(self, *args, **kwargs):
        owner = args[0] if args else kwargs.get("user_id")
        token = scan_owner.set(owner if self.db is db else None)
        enabled = self.db is db and await _synthetic_diagnostics_allowed(db, owner)
        try:
            if scenario == "source_change_crash" and "source_scan_cancelled_once" not in probe.faults:
                probe.faults.append("source_scan_cancelled_once")
                raise asyncio.CancelledError()
            result = await original_scan(self, *args, **kwargs)
        except BaseException as exc:
            if enabled and len(probe.discovery_results) < MAX_DIAGNOSTIC_SCANS:
                probe.discovery_results.append({"response_kind": "raised", "exception_type": type(exc).__name__[:80]})
            raise
        else:
            if enabled and len(probe.discovery_results) < MAX_DIAGNOSTIC_SCANS:
                probe.discovery_results.append(_scan_result_fields(result))
            return result
        finally:
            scan_owner.reset(token)

    async def audit(snapshot, proposed):
        if not await _synthetic_diagnostics_allowed(db, scan_owner.get()):
            return await original_audit(snapshot, proposed)
        return await observed_decision("opportunity_audit", original_audit, snapshot, proposed=proposed)

    async def discover(snapshot, **kwargs):
        refs = [row["ref"] for row in snapshot.get("what_changed", [])
                if str(row.get("ref") or "").startswith("mem_")]
        require(len(refs) == 1, "DISCOVERY_LOST_CANONICAL_SOURCE")
        return {"opportunities": [{
            "identity_key": "v162:fictional-archive-cost-review",
            "what": "La persona usa il mensile e valuta le due formule su dodici mesi; manca il confronto scritto.",
            "why_it_matters": "Rendere disponibili costi e vincoli per la scelta ancora aperta.",
            "why_now": WHY_NOW,
            "initiative": "prepare", "evidence_refs": refs,
            "what_i_can_do": "Leggere la nota e preparare un confronto, senza modificare il contratto.",
        }]}

    async def decide_goal(*args, **kwargs):
        call = scripted_goal_decision if mode == "scripted" else original_decide_goal
        return await observed_decision("decide_goal", call, *args, **kwargs)

    async def discover_decision(*args, **kwargs):
        call = discover if mode == "scripted" else original_discover
        if not await _synthetic_diagnostics_allowed(db, scan_owner.get()):
            return await call(*args, **kwargs)
        return await observed_decision("opportunity_scan", call, *args, **kwargs)

    async def visible(goal, **kwargs):
        if goal.get("status") != "completed":
            return {"outcome": "silent", "reasoning": "Il risultato non è ancora pronto."}
        return {"outcome": "inform_user", "headline": "Il confronto dei costi per dodici mesi è pronto in ORA.",
                "reasoning": "La nota è stata letta e il confronto è disponibile.", "about": "confronto dodici mesi"}

    async def in_app(*args, **kwargs):
        return {"mode": "in_app", "timing": "now", "requires_recheck": False,
                "reason_to_open": "Il confronto verificato è consultabile.",
                "what_decided_the_mode": "Nessuna urgenza o invio necessario."}

    with ExitStack() as stack:
        # mongomock re-finds an updated document by its old filter when _id
        # was projected out; a real atomic Mongo claim does not. Keep _id for
        # that internal mock lookup, then restore the requested projection.
        # This adapter never affects Motor or the separate real-Mongo gate.
        from mongomock.collection import Collection
        mock_update = Collection.find_one_and_update

        def project_after_mock_claim(self, *args, **kwargs):
            projection = kwargs.get("projection")
            hide_id = isinstance(projection, dict) and projection.get("_id") == 0
            if hide_id:
                projection = {key: value for key, value in projection.items() if key != "_id"}
                kwargs["projection"] = projection or None
            result = mock_update(self, *args, **kwargs)
            if result is not None and hide_id:
                result.pop("_id", None)
            return result

        stack.enter_context(patch.object(Collection, "find_one_and_update", project_after_mock_claim))
        boundary.install(stack)
        # The manager can retry or fall back inside one logical call. Bound
        # those actual HTTP requests too, before any transport can spend.
        import httpx
        checked_send = httpx.AsyncClient.send

        async def bounded_model_send(client, request, **kwargs):
            if boundary.scope.get() == "model" and mode == "live":
                if probe.model_http_requests >= MAX_MODEL_HTTP_REQUESTS:
                    boundary.blocked.append("MODEL_HTTP_BOUND_EXCEEDED")
                    raise EvaluationFailure("MODEL_HTTP_BOUND_EXCEEDED")
                probe.model_http_requests += 1
            return await checked_send(client, request, **kwargs)

        stack.enter_context(patch.object(httpx.AsyncClient, "send", bounded_model_send))
        stack.enter_context(patch.object(ProviderManager, "chat", observed_chat))
        stack.enter_context(patch.object(CapabilityResolver, "available", available))
        stack.enter_context(patch.object(StepExecutor, "run", step))
        stack.enter_context(patch.object(AgentService, "advance", bounded_first_read))
        stack.enter_context(patch.object(AgentService, "_build_plan", build_plan))
        stack.enter_context(patch.object(AgentService, "_reconsider", service_reconsider))
        stack.enter_context(patch.object(DeliveryService, "note_activity", note))
        stack.enter_context(patch.object(provider, "get_provider", lambda: BlockedPush(probe)))
        stack.enter_context(patch.object(reasoning, "make_plan", plan))
        stack.enter_context(patch.object(reasoning, "verify_goal", verify))
        stack.enter_context(patch.object(reasoning, "choose_next_action", choose))
        stack.enter_context(patch.object(reasoning, "reconsider", reconsider))
        stack.enter_context(patch.object(OpportunityService, "scan", scan))
        stack.enter_context(patch.object(reasoning, "decide_goal", decide_goal))
        stack.enter_context(patch.object(opportunity_reasoning, "scan", discover_decision))
        stack.enter_context(patch.object(opportunity_reasoning, "audit_proposals", audit))
        stack.enter_context(patch.object(preparation, "prepare", prepare))
        stack.enter_context(patch.object(reasoning, "_ask_model", prepare_model))
        if mode == "scripted":
            if scenario == "memory_corrected":
                stack.enter_context(patch.object(baseline, "DRAFT", baseline.DRAFT.replace(
                    "120 euro", "150 euro").replace("60 euro", "30 euro")))
            stack.enter_context(patch.object(reasoning, "decide_visibility", visible))
            stack.enter_context(patch.object(delivery_reasoning, "decide_delivery", in_app))
        yield probe


async def seed_case(db, scenario):
    """Called only with a newly-created evaluator database, never app Mongo."""
    from agent.service import AgentService
    from ambient.repository import AmbientRepository
    from conversation_engine.ai_core.models import MemoryCandidate
    from life_memory.governance import MemoryGovernanceService
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    require(scenario in SCENARIOS, "UNKNOWN_SCENARIO")
    require(await db.users.count_documents({}) == 0, "EVALUATOR_DATABASE_NOT_EMPTY")
    await db.eval_guards.insert_one({"_id": VERSION, "owner": OWNER})
    await db.users.insert_one({"id": OWNER, "user_id": OWNER, "name": "Utente sintetico",
                               "settings": {"timezone": "Europe/Rome", "notifications_enabled": False}})
    await OpportunityRepository(db).ensure_indexes()
    await AgentService(db).ensure_indexes()
    await AmbientRepository(db).ensure_indexes()
    governance = MemoryGovernanceService(db)
    await governance.ensure_indexes()
    note = RESOLVED_FIXTURE_NOTE if scenario == "already_resolved" else FIXTURE_NOTE
    memory = await governance.apply(
        user_id=OWNER, session_id="synthetic-autonomy-evaluation",
        reasoning_epoch=VERSION, candidate_index=0,
        candidate=MemoryCandidate(
            summary=note, kind="service_contract_note",
            identity_key="v162:fictional-archive-note", confidence=0.95,
            authority="user_stated", epistemic_status="confirmed",
            provenance=["user_conversation"], permanence="indefinite",
            reason_for_future_utility="Conservare costi, vincoli e stato della scelta descritti nella nota.",
            user_authorized=True,
        ),
    )
    require(memory.persisted and memory.memory_id, "CANONICAL_MEMORY_NOT_PERSISTED")
    if scenario == "source_change_crash":
        from opportunities.discovery import OpportunityDiscovery
        discovery = OpportunityDiscovery(db)
        await discovery.ensure_indexes()
        changed = await discovery.note(
            OWNER, source="conversation", kind="constraint.changed",
            entity_ref=memory.memory_id, after=note, wake=False,
        )
        require(changed.get("outcome") == "accepted", "SOURCE_CHANGE_NOT_RECORDED")
        return ""
    opportunity = Opportunity(
        owner_id=OWNER, identity_key="v162:fictional-archive-cost-review", status="active",
        semantic_summary=("La persona usa il mensile e prevede di tenere l'archivio per dodici mesi. "
                          "Sta valutando le due formule e non ha ancora ricevuto il confronto "
                          "scritto dei costi e dei vincoli necessario alla scelta."),
        why_it_matters="Rendere disponibili costi e vincoli per la scelta ancora aperta.",
        why_now=WHY_NOW,
        what_ora_can_do=("Leggere la nota salvata e preparare un confronto dei costi per dodici mesi "
                         "con i vincoli e i dati ancora da verificare. Nessun pagamento, invio o modifica."),
        initiative="prepare", evidence=[EvidenceRef(kind="memory", ref=memory.memory_id,
            summary="Nota interna sui costi e vincoli delle due opzioni di archivio.")],
    )
    if scenario == "already_resolved":
        opportunity.semantic_summary = (
            "La persona ha già ricevuto il confronto scritto dei costi e dei vincoli "
            "e ha scelto il mensile; non ha dubbi o verifiche aperte sulle due formule."
        )
        opportunity.why_it_matters = "La scelta fra le due formule risulta conclusa nella nota."
        opportunity.why_now = "La nota attesta il confronto già ricevuto e la scelta conclusa, senza esiti aperti."
        opportunity.what_ora_can_do = "Il confronto e la scelta sono già documentati; non risultano verifiche residue."
        opportunity.initiative = "inform"
    if scenario == "irrelevant":
        opportunity.semantic_summary = "Newsletter pubblicitaria generica per un accessorio non richiesto."
        opportunity.why_it_matters = "Nessun bisogno, interesse, obbligo o scadenza documentato."
        opportunity.why_now = "Nessuna urgenza."
        opportunity.what_ora_can_do = "Nessun lavoro utile richiesto o necessario."
        opportunity.initiative = "inform"
        opportunity.evidence = []
    await OpportunityRepository(db).save(opportunity)
    return opportunity.id


async def discover_after_crash(db, probe):
    """Source claims survive a cancelled scan before normal goal admission."""
    from opportunities.discovery import OpportunityDiscovery
    try:
        await OpportunityDiscovery(db).review(OWNER)
    except asyncio.CancelledError:
        pass
    else:
        raise EvaluationFailure("SOURCE_SCAN_FAULT_NOT_EXERCISED")
    require("source_scan_cancelled_once" in probe.faults, "SOURCE_SCAN_FAULT_NOT_EXERCISED")
    require(await db.meaningful_changes.count_documents({"owner_id": OWNER, "status": "pending"}) == 1,
            "CANCELLED_SCAN_LOST_SOURCE_CHANGE")
    require(await db.opportunities.count_documents({"owner_id": OWNER}) == 0,
            "INTERRUPTED_SCAN_INVENTED_OPPORTUNITY")
    resumed = await OpportunityDiscovery(db).review(OWNER)
    require(resumed.ran and not resumed.unavailable and resumed.scan
            and len(resumed.scan.created) == 1, "SOURCE_DISCOVERY_DID_NOT_RECOVER")
    require(await db.meaningful_changes.count_documents({"owner_id": OWNER, "status": "consumed"}) == 1,
            "RECOVERED_SCAN_NOT_ACKNOWLEDGED")
    return resumed.scan.created[0].id


async def admit(db, scenario, probe=None):
    from agent.admission import MAX_ATTEMPTS, drain
    require(await _synthetic_diagnostics_allowed(db, OWNER), "SYNTHETIC_CLOCK_GUARD_MISSING")
    source = await db.opportunities.find_one({"owner_id": OWNER})
    require(source and source.get("id") and source.get("agent_review_revision"), "ADMISSION_SOURCE_MISSING")
    fence = {"owner_id": OWNER, "id": source["id"], "agent_review_revision": source["agent_review_revision"]}
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            require(await _synthetic_diagnostics_allowed(db, OWNER), "SYNTHETIC_CLOCK_GUARD_MISSING")
            due = source.get("agent_review_due")
            try:
                when = datetime.fromisoformat(due) if type(due) is str else None
            except ValueError:
                when = None
            require(when and when.tzinfo, "DURABLE_ADMISSION_RETRY_MISSING")
            changed = await db.opportunities.update_one({
                **fence, "agent_review_state": "pending", "agent_review_outcome": "unavailable",
                "agent_review_attempts": source["agent_review_attempts"], "agent_review_due": due,
                "agent_review_token": {"$exists": False}, "agent_review_lease_until": {"$exists": False},
            }, {"$set": {"agent_review_due": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}})
            require(changed.modified_count == 1, "ADMISSION_RETRY_SOURCE_CHANGED")
        require(await drain(db, owner_id=OWNER, limit=1) == 1, "ADMISSION_NOT_PROCESSED")
        source = await db.opportunities.find_one(fence)
        require(source is not None, "ADMISSION_RETRY_SOURCE_CHANGED")
        if probe is not None and len(probe.admission_observations) < MAX_DIAGNOSTIC_ADMISSIONS:
            probe.admission_observations.append(_admission_fields(source))
        if source.get("agent_review_outcome") != "unavailable":
            break
        attempts = source.get("agent_review_attempts")
        require(type(attempts) is int and 0 < attempts < MAX_ATTEMPTS, "ADMISSION_RETRIES_EXHAUSTED")
        require(source.get("agent_review_state") == "pending", "DURABLE_ADMISSION_RETRY_MISSING")
    goals = await db.agent_goals.find({"owner_id": OWNER}, {"_id": 0}).to_list(3)
    if scenario in NO_GOAL_SCENARIOS:
        code = "ALREADY_RESOLVED" if scenario == "already_resolved" else "IRRELEVANT"
        require(not goals, code + "_GOAL_CREATED")
        require(await db.ambient_wakes.count_documents({"owner_id": OWNER}) == 0, code + "_WAKE_CREATED")
        source = await db.opportunities.find_one({"owner_id": OWNER})
        require(source.get("agent_review_outcome") == "no_goal", "SILENCE_NOT_DECIDED")
        return None
    require(len(goals) == 1 and goals[0]["status"] == "active", "ONE_ACTIVE_GOAL_REQUIRED")
    goal_id = goals[0]["id"]
    require(await db.ambient_wakes.count_documents({
        "owner_id": OWNER, "source_ref": "goal:" + goal_id, "status": "pending",
    }) == 1, "ADMITTED_GOAL_WAKE_MISSING")
    return goal_id


async def fire_due(db, goal_id, probe):
    """Expedite only marked synthetic checkpoints, then let the real worker claim."""
    from agent.background import recover_due
    from ambient.runtime import tick
    guard = await db.eval_guards.find_one({"_id": VERSION, "owner": OWNER})
    require(guard is not None, "SYNTHETIC_CLOCK_GUARD_MISSING")
    due = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    # A missing continuation is a failure, not something the test repairs.
    current = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
    require(current and current.get("next_run_at"), "DURABLE_CONTINUATION_MISSING")
    try:
        saved_due = datetime.fromisoformat(current["next_run_at"])
    except (TypeError, ValueError):
        saved_due = None
    require(saved_due and saved_due.tzinfo, "DURABLE_CONTINUATION_INVALID")
    # A changed source or user decision must not have its new clock moved by
    # an observation of the old checkpoint. Counters are never reset here.
    fence = {"owner_id": OWNER, "id": goal_id, **{key: current.get(key) for key in (
        "next_run_at", "status", "background_runs", "opportunity_revision",
        "requires_user_input", "requires_user_authority", "user_deferred_until",
    )}}
    moved = await db.agent_goals.update_one(fence, {"$set": {"next_run_at": due}})
    require(moved.matched_count == 1, "CONTINUATION_CHECKPOINT_CHANGED")
    await recover_due(db, now=datetime.now(timezone.utc), limit=2, admit=False)
    # Recovery may create a missing wake with the scheduler's minimum lead
    # time. Expedite it too, after production recovery has proved it exists.
    await db.ambient_wakes.update_many({"owner_id": OWNER, "source_ref": "goal:" + goal_id,
                                        "status": "pending"}, {"$set": {"scheduled_for": due}})
    out = await tick(db, now=datetime.now(timezone.utc), limit=2)
    probe.ticks.append(out)
    require(out["claimed"] >= 1 and out["failed"] == 0, "PERSISTED_WAKE_NOT_HANDLED")
    current = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id}, {"_id": 0})
    observation = await _planning_error(db, current, observed_run=probe.last_planning_run)
    if observation is not None:
        if len(probe.planning_observations) < MAX_DIAGNOSTIC_PLANNING:
            probe.planning_observations.append(observation)
        else:
            probe.planning_observations_omitted += 1
    return current


async def complete_due_work(db, goal_id, probe):
    """Observe existing active continuations within the production run cap.

    One wake need not finish an outcome after a transient provider failure.
    This evaluator may expedite at most three saved active checkpoints; the
    runtime's persisted background_runs limit remains authoritative. Model
    waits, user deferrals and requests for knowledge/authority are not clocks
    this completion probe can advance into a different decision.
    """
    require(await _synthetic_diagnostics_allowed(db, OWNER), "SYNTHETIC_CLOCK_GUARD_MISSING")
    for _ in range(3):
        current = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
        require(current is not None, "COMPLETION_GOAL_MISSING")
        if current.get("status") == "completed":
            return current
        require(current.get("status") == "active"
                and not current.get("requires_user_input")
                and not current.get("requires_user_authority")
                and not current.get("user_deferred_until"), "COMPLETION_NEEDS_NEW_DECISION")
        attempts = current.get("background_runs")
        require(type(attempts) is int and 0 <= attempts < 3, "COMPLETION_BUDGET_EXHAUSTED")
        require(current.get("next_run_at"), "DURABLE_CONTINUATION_MISSING")
        await fire_due(db, goal_id, probe)
    current = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
    require(current and current.get("status") == "completed", "COMPLETION_BUDGET_EXHAUSTED")
    return current


async def first_read(db, goal_id, probe, *, planning_outage=False):
    from agent.service import MAX_PLANNING_ATTEMPTS

    current = await fire_due(db, goal_id, probe)
    if planning_outage:
        require(current["status"] == "active" and current.get("next_run_at"), "PLANNING_OUTAGE_KILLED_WORK")
        require(not current.get("prepared_text"), "OUTAGE_INVENTED_RESULT")
    previous_attempt = 0
    # Planning failure does not consume a background run. Observe only its
    # existing, bounded retry checkpoints; never repair a plan or advance a
    # model wait, question, authority request or explicit user deferral.
    for _ in range(MAX_PLANNING_ATTEMPTS - 1):
        if current.get("planning_unavailable") is not True:
            break
        require(current.get("status") == "active"
                and not current.get("requires_user_input")
                and not current.get("requires_user_authority")
                and not current.get("user_deferred_until"), "PLANNING_RETRY_NEEDS_NEW_DECISION")
        attempt = current.get("planning_attempts")
        require(type(attempt) is int and previous_attempt < attempt < MAX_PLANNING_ATTEMPTS,
                "PLANNING_RETRIES_EXHAUSTED")
        previous_attempt = attempt
        current = await fire_due(db, goal_id, probe)
    require(current["status"] == "active" and current.get("next_run_at"), "UNFINISHED_WORK_LOST")
    require(not current.get("prepared_text"), "RESULT_CREATED_BEFORE_RESUME")
    require(await db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": goal_id,
        "provenance.capability": "information.read"}) == 1, "OWNED_SOURCE_NOT_READ_ONCE")


def review_comparison(text, *, values=(180, 120, 60)):
    """A fixture-specific independent check, not another self-approved draft."""
    text = str(text or "")
    reasons = []
    for value in values:
        if not re.search(rf"(?<!\d){value}(?:[.,]00)?(?!\d)", text):
            reasons.append(f"MISSING_COMPARISON_VALUE_{value}")
    if not re.search(r"\b12\b|dodici", text, re.I):
        reasons.append("PERIOD_NOT_PRESERVED")
    if not re.search(r"\bnota\b|\bnote\s+(?:salvate|interne|registrate|dell['’]utente)\b|"
                     r"dati.{0,35}(?:intern|utente)", text, re.I):
        reasons.append("INTERNAL_SOURCE_NOT_ATTRIBUTED")
    if not re.search(r"non.{0,35}rimbors|senza.{0,20}rimborso|nessun.{0,20}rimborso", text, re.I):
        reasons.append("NONREFUNDABLE_CONSTRAINT_MISSING")
    if not re.search(r"non\s+(?:(?:è|sono)\s+)?(?:ancora\s+)?(?:stat\w*\s+)?"
                     r"(?:verificat\w*|confermat\w*)|"
                     r"non\s+(?:costituisc\w*|rappresent\w*)\s+(?:una?\s+)?"
                     r"(?:conferma|verifica)\b|"
                     r"(?:da|senza)\s+(?:verific\w*|conferm\w*)|"
                     r"richied\w*.{0,20}(?:conferma|verifica)", text, re.I):
        reasons.append("SOURCE_VERIFICATION_LIMIT_MISSING")
    return {"passed": not reasons, "reasons": reasons, "status": "bounded_check",
            "human_review_still_required": True}


async def recover_home(db):
    from agent.visibility import VisibilityService
    require(await db.eval_guards.find_one({"_id": VERSION, "owner": OWNER}),
            "SYNTHETIC_CLOCK_GUARD_MISSING")
    await db.agent_updates.update_many({"owner_id": OWNER, "home_pending": True}, {"$set": {
        "home_due_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    }})
    return await VisibilityService(db).recover_pending_home()


async def verify_result(db, goal_id, probe, *, recover=True, source_corrected=False):
    from agent.service import AgentService
    from delivery.service import DeliveryService
    goal = await AgentService(db).repo.get_goal(OWNER, goal_id)
    require(goal and goal.status == "completed", "GOAL_NOT_COMPLETED")
    plan = await AgentService(db).repo.plan_for(OWNER, goal_id)
    require(plan and plan.status == "completed", "PLAN_NOT_COMPLETED")
    # A recovered failed attempt is terminal history, not unfinished work.
    # Goal/plan completion and the result's evidence are checked separately;
    # pending, running, blocked and waiting steps must still be retired.
    require(all(step.status in ("succeeded", "skipped", "failed") for step in plan.steps), "UNFINISHED_PLAN_STEPS")
    require(goal.prepared_text and goal.prepared_sources, "GROUNDED_RESULT_MISSING")
    evidence = await AgentService(db).evidence.for_goal(OWNER, goal_id)
    require(set(goal.prepared_sources).issubset({item.id for item in evidence}), "UNOWNED_RESULT_EVIDENCE")
    require(sum(item.provenance.capability == "information.read" for item in evidence) == 1, "READ_REPEATED_AFTER_RESUME")
    total_reads = await db.agent_evidence.count_documents({"owner_id": OWNER, "goal_id": goal_id,
                                                         "provenance.capability": "information.read"})
    require(total_reads == (2 if source_corrected else 1), "UNEXPECTED_TOTAL_SOURCE_READS")
    semantic = review_comparison(goal.prepared_text, values=(180, 150, 30) if source_corrected else (180, 120, 60))
    require(semantic["passed"], "SEMANTIC_RESULT_REJECTED:" + ",".join(semantic["reasons"]))
    if recover:
        await recover_home(db)
    updates = await db.agent_updates.find({"owner_id": OWNER, "goal_id": goal_id}, {"_id": 0}).to_list(8)
    require(any(not row.get("home_pending") and row.get("home_delivered_at") for row in updates), "HOME_OUTBOX_NOT_DELIVERED")
    activities = await db.ambient_activity.find({"owner_id": OWNER, "visibility": "ambient",
        "cognitive_provenance.agent": "visibility", "cognitive_provenance.goal": goal_id}, {"_id": 0}).to_list(8)
    require(activities, "VALIDATED_HOME_ACTIVITY_MISSING")
    home = await DeliveryService(db).ambient_line(OWNER)
    require(home and any(home["id"] == row["id"] for row in activities), "RESULT_NOT_RETRIEVABLE_FROM_HOME")
    before = await snapshot_counts(db, goal_id)
    model_before = probe.model_attempts
    replay = await AgentService(db).advance(OWNER, goal_id, worker_id="ambient:v162-replay")
    require(replay.get("state") == "completed", "TERMINAL_REPLAY_CHANGED_STATE")
    await recover_home(db)
    require(await snapshot_counts(db, goal_id) == before and probe.model_attempts == model_before, "REPLAY_DUPLICATED_WORK")
    foreign = await AgentService(db).advance("another-synthetic-owner", goal_id)
    require(foreign.get("reason") == "unknown_goal", "CROSS_OWNER_ACCESS")
    return {"state": goal.status, "read_reused": not source_corrected,
            "corrected_source_reread": source_corrected, "prepared": True,
            **_prepared_text_fields(goal.prepared_text),
            "home_delivered": True, "replay_idempotent": True, "owner_isolation": True,
            "semantic_review": semantic, "counts": before}


async def snapshot_counts(db, goal_id):
    return {name: await db[name].count_documents({"owner_id": OWNER}) for name in (
        "agent_evidence", "agent_updates", "ambient_activity", "agent_needs", "agent_action_attempts",
    )}


async def change_memory(db, goal_id, *, correction=False):
    """A real canonical change between wakes, inside the marked synthetic DB."""
    from conversation_engine.ai_core.models import MemoryCandidate
    from life_memory.governance import MemoryGovernanceService
    require(await db.eval_guards.find_one({"_id": VERSION, "owner": OWNER}),
            "SYNTHETIC_MEMORY_GUARD_MISSING")
    goal = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
    refs = [ref for ref in (goal or {}).get("source_refs", []) if ref.startswith("mem_")]
    require(len(refs) == 1, "CANONICAL_SOURCE_REFERENCE_MISSING")
    operation = "correct" if correction else "forget"
    changed = await MemoryGovernanceService(db).apply(
        user_id=OWNER, session_id="synthetic-autonomy-evaluation",
        reasoning_epoch=VERSION + ":" + operation, candidate_index=0,
        candidate=MemoryCandidate(operation=operation,
            summary=FIXTURE_NOTE.replace("120 euro", "150 euro") if correction else "Dimentica la nota ritirata.",
            existing_memory_ref=refs[0], user_authorized=True,
            kind="service_contract_note", identity_key="v162:fictional-archive-note",
            authority="user_stated", epistemic_status="confirmed", confidence=0.95,
            permanence="indefinite", provenance=["user_conversation"],
            reason_for_future_utility="Conservare costi, vincoli e stato della scelta descritti nella nota."),
    )
    require(changed.persisted, "MEMORY_CHANGE_NOT_PERSISTED")
    return {"old": refs[0], "current": changed.memory_id}


async def run_case(scenario, *, mode="scripted", probe=None):
    from mongomock_motor import AsyncMongoMockClient
    from opportunities.service import OpportunityService
    from agent.service import AgentService
    require(scenario in SCENARIOS, "UNKNOWN_SCENARIO")
    db = AsyncMongoMockClient()["autonomy_v162_" + scenario]
    probe = probe or Probe()
    probe.database = db
    with isolated_engine(db, mode=mode, scenario=scenario, probe=probe) as probe:
        source_id = await seed_case(db, scenario)
        if scenario == "source_change_crash":
            source_id = await discover_after_crash(db, probe)
        goal_id = await admit(db, scenario, probe)
        result = {"state": "no_goal"}
        if goal_id:
            await first_read(db, goal_id, probe, planning_outage=scenario == "planning_outage")
            if scenario == "source_revoked":
                before_steps = len(probe.steps)
                await OpportunityService(db).dismiss(OWNER, source_id)
                current = await AgentService(db).repo.get_goal(OWNER, goal_id)
                require(current and current.status == "cancelled" and not current.next_run_at, "REVOKED_WORK_NOT_STOPPED")
                require(not current.prepared_text and len(probe.steps) == before_steps, "REVOKED_SOURCE_PRODUCED_RESULT")
                require(await db.ambient_wakes.count_documents({"owner_id": OWNER,
                    "source_ref": "goal:" + goal_id, "status": "pending"}) == 0, "REVOKED_WAKE_SURVIVED")
                before = await snapshot_counts(db, goal_id)
                from ambient.runtime import tick
                idle = await tick(db, now=datetime.now(timezone.utc), limit=2)
                replay = await AgentService(db).advance(OWNER, goal_id, worker_id="ambient:v162-cancel-replay")
                require(not idle["claimed"] and replay.get("state") == "cancelled"
                        and await snapshot_counts(db, goal_id) == before,
                        "REVOKED_SOURCE_REPLAYED_WORK")
                result = {"state": "cancelled", "stopped_on_source_revocation": True,
                          "replay_idempotent": True}
            elif scenario == "memory_revoked":
                await change_memory(db, goal_id)
                before_steps = len(probe.steps)
                current = await AgentService(db).repo.get_goal(OWNER, goal_id)
                if current.next_run_at:
                    await fire_due(db, goal_id, probe)
                current = await AgentService(db).repo.get_goal(OWNER, goal_id)
                require(current.status == "abandoned" and not current.prepared_text,
                        "WITHDRAWN_MEMORY_PRODUCED_RESULT")
                require(not any(step["capability"] == "document.create" and step["status"] == "succeeded"
                                for step in probe.steps[before_steps:]), "WITHDRAWN_EVIDENCE_REUSED")
                result = {"state": current.status, "stopped_on_memory_revocation": True}
            elif scenario == "memory_corrected":
                changed = await change_memory(db, goal_id, correction=True)
                probe.faults.append("memory_corrected_between_wakes")
                await complete_due_work(db, goal_id, probe)
                evidence = await AgentService(db).evidence.for_goal(OWNER, goal_id)
                reads = [row for row in evidence if row.provenance.capability == "information.read"]
                require(reads and all(changed["current"] in row.provenance.source_refs
                                     and changed["old"] not in row.provenance.source_refs for row in reads),
                        "SUPERSEDED_MEMORY_USED_AS_CURRENT")
                result = await verify_result(db, goal_id, probe, source_corrected=True)
            else:
                await complete_due_work(db, goal_id, probe)
                if scenario == "home_write_retry":
                    require(await db.agent_updates.count_documents({"owner_id": OWNER, "home_pending": True}) == 1,
                            "FAILED_HOME_HANDOFF_NOT_DURABLE")
                result = await verify_result(db, goal_id, probe)
        require(await db.agent_action_attempts.count_documents({}) == 0, "WORLD_ACTION_ATTEMPT_CREATED")
        require(await db.action_intents.count_documents({}) == 0, "WORLD_ACTION_INTENT_CREATED")
        require(not probe.blocked_effects and not probe.push_attempts and not probe.network.blocked, "ISOLATION_BOUNDARY_ATTEMPTED")
        require(mode != "live" or bool(probe.model_calls), "LIVE_MODEL_NOT_OBSERVED")
        require(mode != "scripted" or not probe.model_attempts, "OFFLINE_MODEL_CALL")
        return {"version": VERSION, "fixture_revision": FIXTURE_REVISION,
                "scenario": scenario, "mode": mode, "passed": True,
                "scope": "synthetic_internal_note_to_home_no_external_effects",
                "model_mode": "real_llm" if mode == "live" else "scripted",
                "source_mode": "synthetic_owned_record_real_reader", "live_provider_reads": 0,
                "storage": "in_memory", "process_restart_tested": False,
                "synthetic_checkpoints_expedited": True,
                **model_observations(probe),
                "worker_ticks": probe.ticks,
                "source_change_discovery_tested": scenario == "source_change_crash",
                "injected_faults": probe.faults, "external_effects": 0, "result": result}


async def main(*, mode="scripted", scenario="all", output=""):
    started_at = datetime.now(timezone.utc).isoformat()
    selected = SCENARIOS if scenario == "all" else (scenario,)
    if mode == "live" and not any(os.environ.get(key) for key in LLM_KEYS):
        report = {"version": VERSION, "mode": mode, "status": "blocked", "passed": False,
                  "reason": "LIVE_MODEL_CREDENTIALS_UNAVAILABLE", "real_model_executed": False, "cases": []}
        code = 3
    else:
        cases = []
        for name in selected:
            probe = Probe()
            try:
                case = await asyncio.wait_for(run_case(name, mode=mode, probe=probe),
                                              timeout=CASE_TIMEOUT_SECONDS)
            except Exception as exc:
                case = {"scenario": name, "mode": mode, "passed": False,
                        **model_observations(probe),
                        "failure_state": await failure_state(probe),
                        "reason": str(exc) if isinstance(exc, EvaluationFailure) else type(exc).__name__}
            cases.append(case)
            # Emit only fixed case identity/outcome and bounded counters while
            # the remaining real-model cases run. No source text or prompts.
            print("ORA_AUTONOMY_COMPLETION_CASE " + json.dumps({
                "scenario": name, "mode": mode, "passed": case["passed"],
                "model_attempts": probe.model_attempts,
                "model_http_requests": probe.model_http_requests,
                # Only a short machine-readable diagnostic: never a raw prompt,
                # provider exception body or source text in the live log.
                "failure_code": (
                    re.sub(r"[^A-Z0-9_:,]", "_", str(case.get("reason") or "").upper())[:160]
                    if not case["passed"] else None
                ),
            }, ensure_ascii=False), flush=True)
        passed = all(case["passed"] for case in cases)
        report = {"version": VERSION, "mode": mode, "status": "passed" if passed else "failed",
                  "passed": passed, "real_model_executed": mode == "live" and all(
                      case.get("real_model_executed") for case in cases), "cases": cases}
        code = 0 if passed else 1
    revision = os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("GITHUB_SHA") or ""
    report.update({"fixture_revision": FIXTURE_REVISION,
                   "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
                   "limits": {"cases": len(selected), "case_timeout_seconds": CASE_TIMEOUT_SECONDS,
                              "model_calls_per_case": MAX_MODEL_CALLS,
                              "model_call_outcomes_per_case": MAX_MODEL_CALLS,
                              "model_failures_reported_per_call": MAX_MODEL_FAILURES_REPORTED,
                              "model_http_requests_per_case": MAX_MODEL_HTTP_REQUESTS,
                              "structured_decisions_per_case": MAX_DECISION_OBSERVATIONS,
                              "admission_observations_per_case": MAX_DIAGNOSTIC_ADMISSIONS,
                              "planning_observations_per_case": MAX_DIAGNOSTIC_PLANNING,
                              "discovery_results_per_case": MAX_DIAGNOSTIC_SCANS,
                              "preparation_text_characters": PREPARATION_TEXT_LIMIT,
                              "preparation_claims_per_audit": MAX_PREPARATION_CLAIMS,
                              "preparation_claim_text_characters": PREPARATION_CLAIM_TEXT_LIMIT,
                              "preparation_source_quotes_per_claim": MAX_PREPARATION_SOURCE_QUOTES,
                              "executor_observations_per_case": MAX_DECISION_OBSERVATIONS,
                              "decision_text_characters": DECISION_TEXT_LIMIT,
                              "proposals_per_decision": MAX_DIAGNOSTIC_PROPOSALS,
                              "plan_steps_per_decision": MAX_DIAGNOSTIC_PLAN_STEPS,
                              "outcome_assessment_text_characters": ASSESSMENT_TEXT_LIMIT,
                              "outcome_assessment_refs_per_field": MAX_ASSESSMENT_REFS,
                              "model_calls_total": len(selected) * MAX_MODEL_CALLS,
                              "model_http_requests_total": len(selected) * MAX_MODEL_HTTP_REQUESTS},
                   "code_revision": revision if re.fullmatch(r"[0-9a-fA-F]{40}", revision) else None,
                   "revision_source": "deployment_or_ci_metadata" if re.fullmatch(r"[0-9a-fA-F]{40}", revision) else None})
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ORA_AUTONOMY_COMPLETION_SUMMARY " + json.dumps(report, ensure_ascii=False), flush=True)
    return code


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("scripted", "live"), default="scripted")
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(mode=args.mode, scenario=args.scenario, output=args.output)))
