"""Assembly pipeline: providers → dedup → conflicts → hash → snapshot doc."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from .calendar_provider import calendar_provider
from .daily_summary_provider import daily_summary_provider
from .permissions_provider import permissions_provider
from .behavior_provider import behavior_profile_provider as _behavior_signals
from .providers import (
    auto_link_provider,
    decision_provider,
    graph_provider,
    knowledge_provider,
    linked_nodes_provider,
    system_provider,
)
from .redaction import redact_for_hash
from .types import (
    ASSEMBLER_VERSION,
    CATEGORY_ALLOWED_NODE_TYPES,
    ContextConflict,
    ProviderResult,
    SOURCE_RELIABILITY,
    Signal,
)


logger = logging.getLogger("ora.context")

PROVIDER_TIMEOUT_SEC = 8.0
MAX_SIGNALS_PER_SNAPSHOT = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"ctx_{uuid.uuid4().hex[:12]}"


def _decision_signature(decision: Dict[str, Any]) -> str:
    payload = {
        "title": decision.get("title"),
        "description": decision.get("description"),
        "category": decision.get("category"),
        "metadata": decision.get("metadata") or {},
        "node_ids": sorted(decision.get("node_ids") or []),
        "linked_to": sorted(decision.get("linked_to") or []),
        "starts_at": decision.get("starts_at"),
        "deadline": decision.get("deadline"),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


async def run_provider_safe(coro, name: str) -> ProviderResult:
    try:
        return await asyncio.wait_for(coro, timeout=PROVIDER_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.warning("provider %s timed out", name)
        return ProviderResult(name=name, error="timeout")
    except Exception as e:
        logger.exception("provider %s failed", name)
        return ProviderResult(name=name, error=f"{type(e).__name__}")


def dedupe_and_conflicts(signals: List[Signal]) -> Tuple[List[Signal], List[ContextConflict]]:
    """Group by key. Same value → keep the most reliable one. Different values → conflict."""
    by_key: Dict[str, List[Signal]] = {}
    for s in signals:
        by_key.setdefault(s.key, []).append(s)

    kept: List[Signal] = []
    conflicts: List[ContextConflict] = []

    for key, group in by_key.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        # Bucket by canonical value repr (using redacted form to avoid leaking).
        buckets: Dict[str, List[Signal]] = {}
        for s in group:
            canon = json.dumps(redact_for_hash(s.value, s.sensitivity), sort_keys=True, ensure_ascii=False, default=str)
            buckets.setdefault(canon, []).append(s)
        if len(buckets) == 1:
            # All same value → keep most reliable
            group.sort(key=lambda x: -SOURCE_RELIABILITY.get(x.reliability_tier, 0))
            kept.append(group[0])
        else:
            # Different values → conflict, keep all but flag it
            for bucket in buckets.values():
                bucket.sort(key=lambda x: -SOURCE_RELIABILITY.get(x.reliability_tier, 0))
                kept.append(bucket[0])
            conflicts.append(ContextConflict(key=key, signals=[b[0] for b in buckets.values()], detected_at=_now()))

    return kept, conflicts


def compute_hash(signals: List[Signal], assembler_version: str, decision_signature: str, knowledge_versions: Dict[str, int]) -> str:
    """Compute a stable hash. System (ambient) signals are excluded because
    values like `now_iso` change on every call and would break idempotence.
    Semantic changes still propagate via decision_signature + knowledge_versions
    + non-system signals."""
    hashable = [s for s in signals if s.source_module != "system"]
    payload = {
        "assembler_version": assembler_version,
        "decision_signature": decision_signature,
        "knowledge_versions": dict(sorted(knowledge_versions.items())),
        "signals": sorted(
            [
                {
                    "key": s.key,
                    "value": redact_for_hash(s.value, s.sensitivity),
                    "source_module": s.source_module,
                    "reliability_tier": s.reliability_tier,
                    "verified": s.verified,
                }
                for s in hashable
            ],
            key=lambda x: (x["key"], x["source_module"]),
        ),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


async def assemble_pipeline(repo, user_id: str, decision: Dict[str, Any], *, allow_highly_sensitive: bool = False) -> Dict[str, Any]:
    """Return a ready-to-persist snapshot dict + telemetry."""
    allowed_types = set(CATEGORY_ALLOWED_NODE_TYPES.get(decision.get("category") or "generic", frozenset())) or {"generic"}

    # Provider 1 (Decision) — cannot fail meaningfully.
    p_decision = await run_provider_safe(decision_provider(repo, user_id, decision), "decision")

    # Provider 2 (LinkedNodes) — filters by allowed_types.
    p_linked = await run_provider_safe(linked_nodes_provider(repo, user_id, decision, allowed_types), "linked_nodes")
    kept_node_ids = p_linked.linked_node_ids

    # Provider 3 (Knowledge) — only for kept nodes.
    p_know = await run_provider_safe(knowledge_provider(repo, user_id, kept_node_ids, allow_highly_sensitive=allow_highly_sensitive), "knowledge")

    # Provider 4 (Graph) — bounded traversal from kept nodes.
    p_graph = await run_provider_safe(graph_provider(repo, user_id, kept_node_ids, depth=1, allowed_types=allowed_types), "graph")

    # Provider 5 (AutoLink) — accepted proposals for this decision.
    p_auto = await run_provider_safe(auto_link_provider(repo, user_id, decision["id"]), "auto_link")

    # Provider 6 (System) — deterministic env context.
    p_system = await run_provider_safe(system_provider(repo, user_id), "system")

    # Provider 7 (Permissions) — feature-flagged (PERMISSIONS_CONTEXT_ENABLED).
    # When the flag is OFF the provider is a strict no-op: zero signals,
    # zero DB reads. Included in `providers_run` telemetry either way.
    p_perms = await run_provider_safe(permissions_provider(user_id), "permissions")

    # Provider 8 (Calendar) — feature-flagged (CALENDAR_CONTEXT_ENABLED).
    # When the flag is OFF the provider is a strict no-op: zero signals,
    # zero DB reads.
    p_cal = await run_provider_safe(calendar_provider(repo, user_id), "calendar")

    # Provider 9 (Daily Summary) — feature-flagged (DAILY_SUMMARY_ENABLED).
    # OFF by default → strict no-op. When ON emits deterministic day-level
    # metadata (no titles).
    p_daily = await run_provider_safe(daily_summary_provider(repo.db, user_id), "daily_summary")

    # Provider 10 (Behavior Profile) — feature-flagged (BEHAVIOR_PROFILE_ENABLED).
    # OFF by default → strict no-op (zero signals, zero DB reads).
    # NEVER modifies ranking, Decision Engine or Explainability.
    p_bhv = await run_provider_safe(_behavior_signals(repo.db, user_id), "behavior_profile")

    all_results = [p_decision, p_linked, p_know, p_graph, p_auto, p_system, p_perms, p_cal, p_daily, p_bhv]

    # Merge signals, cap total.
    raw_signals: List[Signal] = []
    for r in all_results:
        if r.error:
            continue
        raw_signals.extend(r.signals)
    if len(raw_signals) > MAX_SIGNALS_PER_SNAPSHOT:
        raw_signals = raw_signals[:MAX_SIGNALS_PER_SNAPSHOT]

    signals, conflicts = dedupe_and_conflicts(raw_signals)

    # Semantic groupings for the snapshot doc.
    facts, constraints, risks, people, locations, financial, temporal, dependencies = _group_signals(signals)

    warnings: List[str] = []
    for c in conflicts:
        warnings.append(f"conflict:{c.key}")
    for r in all_results:
        if r.error:
            warnings.append(f"provider_error:{r.name}:{r.error}")

    kversions = {**p_know.knowledge_versions}
    decision_signature = _decision_signature(decision)
    context_hash = compute_hash(signals, ASSEMBLER_VERSION, decision_signature, kversions)

    redaction_summary = {
        "sensitive_omitted": sum(1 for s in raw_signals if s.sensitivity in ("sensitive", "highly_sensitive")),
        "highly_sensitive_excluded_by_default": not allow_highly_sensitive,
    }

    snapshot = {
        "id": _new_id(),
        "user_id": user_id,
        "decision_id": decision["id"],
        "decision_version": decision_signature,
        "generated_at": _now(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        "assembler_version": ASSEMBLER_VERSION,
        "linked_node_ids": kept_node_ids,
        "signals": [s.to_dict() for s in signals],
        "facts": facts,
        "constraints": constraints,
        "risks": risks,
        "dependencies": dependencies,
        "people": people,
        "locations": locations,
        "financial_context": financial,
        "temporal_context": temporal,
        "knowledge_versions": kversions,
        "freshness": {s.key: s.freshness for s in signals if s.freshness and s.freshness != "unknown"},
        "warnings": warnings,
        "provenance": {
            "providers_run": [r.name for r in all_results if not r.error],
            "providers_failed": [r.name for r in all_results if r.error],
            "durations_ms": {r.name: round(r.duration_ms, 2) for r in all_results},
            "signal_counts": {r.name: len(r.signals) for r in all_results if not r.error},
            "conflict_count": len(conflicts),
        },
        "redaction_summary": redaction_summary,
        "context_hash": context_hash,
        "conflicts": [c.to_dict() for c in conflicts],
        "status": "active",
    }
    return snapshot


def _group_signals(signals: List[Signal]) -> tuple:
    facts: List[Dict[str, Any]] = []
    constraints: List[Dict[str, Any]] = []
    risks: List[Dict[str, Any]] = []
    people: List[Dict[str, Any]] = []
    locations: List[Dict[str, Any]] = []
    financial: List[Dict[str, Any]] = []
    temporal: List[Dict[str, Any]] = []
    dependencies: List[Dict[str, Any]] = []

    for s in signals:
        d = s.to_dict()
        k = s.key
        if k in ("deadline_hours", "deadline_iso", "starts_at_iso", "starts_in_hours", "now_iso", "weekday", "hour_of_day"):
            temporal.append(d)
        elif k in ("place",) or k.endswith(".address"):
            locations.append(d)
        elif k in ("people_involved",) or k.endswith(".name") or k.endswith(".relation") or k.endswith(".residents"):
            people.append(d)
        elif k in ("risk",) or k.endswith(".mot") or k.endswith(".expires_at"):
            risks.append(d)
        elif k.endswith(".amount") or k.endswith(".balance") or k.endswith(".value") or k.endswith(".currency") or k.endswith(".provider") or k.endswith(".plan"):
            financial.append(d)
        elif k in ("graph_edge", "graph_neighbor", "accepted_link"):
            dependencies.append(d)
        elif k in ("urgency", "importance", "time_required_min", "energy_required"):
            constraints.append(d)
        else:
            facts.append(d)

    return facts, constraints, risks, people, locations, financial, temporal, dependencies
