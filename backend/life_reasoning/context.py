"""Bounded context assembly for impact reasoning (V2.9.2).

Turns a batch of LifeChangeSignals into the bounded input the model reasons
over. Every retrieval path here is EXISTING infrastructure — there is no
second context loader:

* relationships come from `ContextGraphService.relevant_edges`, the same
  bounded API the Context Broker's `life_context_graph` source already uses;
* evidence comes from `ContextBroker.retrieve(stage="B", ...)`, the same
  Stage B path a conversational turn uses;
* time comes from `timezone_service.resolve_user_timezone`;
* the capability catalog comes from `ToolRegistry.list_public()`.

Nothing is dumped: the graph is walked at most two hops from the signal's own
refs, and the Context Broker enforces its own Stage B item budget.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from life_reasoning.models import MAX_REFS, sanitize_refs

logger = logging.getLogger("ora.life_reasoning.context")

# Graph expansion budget — deliberately the same order of magnitude as the
# Context Broker's own graph source, not a wider traversal.
GRAPH_SEED_LIMIT = 6
GRAPH_EDGE_LIMIT = 10
GRAPH_MAX_DEPTH = 2

# Context Broker Stage B item budget (its own cap is 8).
EVIDENCE_LIMIT = 8

# Prior conclusions surfaced for cross-session continuity.
PRIOR_LIMIT = 3


class ContextUnavailable(Exception):
    """Context retrieval failed. The caller must NOT proceed as if the
    context were merely empty — an empty life and an unreadable one are
    different things, and only the second one forbids a conclusion."""


def describe_changes(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bounded technical description of what changed. Refs and metadata only:
    the signal itself never carried content, and nothing is added here."""
    out: List[Dict[str, Any]] = []
    for s in signals[:8]:
        item = {
            "ref": s.get("source_ref"),
            "system": s.get("source_system"),
            "change": s.get("change_kind"),
            "occurred_at": s.get("occurred_at"),
        }
        affected = sanitize_refs(s.get("affected_refs"), limit=4)
        if affected:
            item["related_refs"] = affected
        if s.get("source_status"):
            item["sync_state"] = s.get("source_status")
        if s.get("authority"):
            item["authority"] = s.get("authority")
        out.append(item)
    return out


def focal_refs_for(signals: List[Dict[str, Any]]) -> List[str]:
    """Every canonical ref the batch is directly about."""
    refs: List[str] = []
    for s in signals:
        for candidate in [s.get("source_ref"), *(s.get("affected_refs") or [])]:
            ref = str(candidate or "").strip()
            if ref and ref not in refs:
                refs.append(ref)
    return sanitize_refs(refs, limit=MAX_REFS)


async def expand_relations(
    db, user_id: str, seed_refs: List[str]
) -> Tuple[List[str], List[str]]:
    """Bounded graph expansion from the signal's own refs.

    Returns `(relation_statements, discovered_refs)`. Depth ≤ 2, edges capped
    — this widens what the reasoning can see, it never traverses the graph
    globally and never creates a relation.
    """
    from context_graph.service import ContextGraphService

    seeds = sanitize_refs(seed_refs, limit=GRAPH_SEED_LIMIT)
    if not seeds:
        return [], []

    svc = ContextGraphService(db)
    edges = await svc.relevant_edges(user_id, seeds, limit=GRAPH_EDGE_LIMIT)

    if edges and GRAPH_MAX_DEPTH > 1:
        neighbours = {e.subject_ref for e in edges} | {e.object_ref for e in edges}
        neighbours -= set(seeds)
        if neighbours:
            try:
                more = await svc.relevant_edges(
                    user_id, list(neighbours)[:GRAPH_SEED_LIMIT], limit=GRAPH_EDGE_LIMIT
                )
                seen = {e.id for e in edges}
                for e in more:
                    if e.id not in seen and len(edges) < GRAPH_EDGE_LIMIT:
                        edges.append(e)
                        seen.add(e.id)
            except Exception as exc:
                logger.info("graph depth-2 soft-fail: %s", type(exc).__name__)

    statements: List[str] = []
    discovered: List[str] = []
    for edge in edges[:GRAPH_EDGE_LIMIT]:
        text = f"{edge.subject_ref} --{edge.predicate}--> {edge.object_ref}"
        if edge.semantic_summary:
            text += f" ({edge.semantic_summary})"
        statements.append(text[:240])
        for ref in (edge.subject_ref, edge.object_ref):
            if ref not in seeds and ref not in discovered:
                discovered.append(ref)
    return statements, sanitize_refs(discovered, limit=MAX_REFS)


async def retrieve_evidence(
    db, user_id: str, *, changes: List[Dict[str, Any]], refs: List[str]
) -> List[Dict[str, Any]]:
    """Bounded evidence via the EXISTING Context Broker Stage B path.

    Raises `ContextUnavailable` when retrieval itself fails, so the caller can
    tell "nothing to say about this life" apart from "could not read this
    life" and refuse to draw a confident conclusion in the second case.
    """
    from conversation_engine.ai_core.context_broker import ContextBroker
    from conversation_engine.ai_core.models import ContextNeed

    # A neutral, ref-anchored query: the refs and the technical change kinds,
    # never a domain word and never invented user text.
    ref_part = " ".join(refs[:GRAPH_SEED_LIMIT])
    kind_part = " ".join(sorted({str(c.get("change") or "") for c in changes}))
    systems = sorted({str(c.get("system") or "") for c in changes if c.get("system")})

    need = ContextNeed(
        query=f"{ref_part} {kind_part}".strip()[:400] or "recent life state change",
        purpose="assess the consequences of a recent change in the user's life state",
        source_hints=_source_hints(systems),
        max_items=EVIDENCE_LIMIT,
    )

    try:
        facts = await ContextBroker(db).retrieve(
            user_id=user_id, context_need=need, stage="B",
        )
    except Exception as exc:
        logger.info("impact context retrieval failed: %s", type(exc).__name__)
        raise ContextUnavailable(type(exc).__name__) from exc

    out: List[Dict[str, Any]] = []
    for fact in facts[:EVIDENCE_LIMIT]:
        item = {
            "statement": (fact.statement or fact.fact or "")[:280],
            "source": fact.source,
            "authority": fact.authority,
            "status": fact.status,
        }
        if fact.ref:
            item["ref"] = fact.ref
        if fact.temporal_scope:
            item["temporal_scope"] = fact.temporal_scope
        if fact.confidence is not None:
            item["confidence"] = fact.confidence
        out.append(item)
    return out


def _source_hints(systems: List[str]) -> List[str]:
    """Map the signal's own subsystem names onto registered Context Broker
    source hints. Hints are advisory in the Broker and never mandatory
    routing, so an imperfect mapping degrades gracefully."""
    mapping = {
        "situation": "situations",
        "life_memory": "memory",
        "context_graph": "life_context_graph",
        "life_os": "life_os",
        "calendar": "calendar",
    }
    hints: List[str] = []
    for system in systems:
        hint = mapping.get(system)
        if hint and hint not in hints:
            hints.append(hint)
    # The graph is always worth consulting for consequences, even when the
    # change itself did not come from it.
    if "life_context_graph" not in hints:
        hints.append("life_context_graph")
    return hints[:5]


def capability_catalog(db=None) -> List[str]:
    """Capability NAMES only — the model may point at one, never call it, and
    never sees input schemas or provider brands."""
    try:
        from conversation_engine.ai_core.tools.registry import ToolRegistry

        return sorted(
            str(c.get("capability") or c.get("name") or "")
            for c in ToolRegistry(db=db).list_public()
            if (c.get("capability") or c.get("name"))
        )
    except Exception as exc:
        logger.info("capability catalog unavailable: %s", type(exc).__name__)
        return []


async def prior_conclusions(db, user_id: str, refs: List[str]) -> List[str]:
    """Bounded cross-session continuity: what ORA already concluded about
    these refs, as short statements — so the model can build on or revise
    prior reasoning instead of rediscovering it every time."""
    from life_reasoning.repository import ImpactAssessmentRepository

    repo = ImpactAssessmentRepository(db)
    seen: List[str] = []
    for ref in refs[:3]:
        try:
            for assessment in await repo.list_for_ref(user_id, ref, limit=PRIOR_LIMIT):
                for impact in assessment.impacts[:2]:
                    text = f"[{impact.kind}] {impact.statement}"[:240]
                    if text not in seen:
                        seen.append(text)
                    if len(seen) >= PRIOR_LIMIT:
                        return seen
        except Exception as exc:
            logger.info("prior conclusions soft-fail: %s", type(exc).__name__)
            return seen
    return seen


async def temporal_context(db, user_id: str) -> Tuple[str, str]:
    """Resolved local time via the existing timezone service — never a
    hardcoded zone and never an invented clock."""
    from timezone_service import resolve_user_timezone

    try:
        resolved = await resolve_user_timezone(db, user_id)
        tz_name = resolved.tz_name
    except Exception as exc:
        logger.info("timezone resolve soft-fail: %s", type(exc).__name__)
        tz_name = "UTC"
    try:
        from zoneinfo import ZoneInfo

        now_local = datetime.now(ZoneInfo(tz_name)).isoformat(timespec="minutes")
    except Exception:
        from datetime import timezone as _tz

        now_local = datetime.now(_tz.utc).isoformat(timespec="minutes")
        tz_name = "UTC"
    return now_local, tz_name
