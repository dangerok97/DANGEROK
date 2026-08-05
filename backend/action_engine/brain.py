"""Brain integration — Life Graph + Knowledge without duplicate facts."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("ora.action_engine.brain")


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


async def find_similar_goal(
    db,
    user_id: str,
    title: str,
    *,
    flow: str,
) -> Optional[dict]:
    """Find an existing action_project / goal with similar title."""
    needle = _norm(title)
    if not needle:
        return None
    # Prefer action_projects collection
    cur = db.action_projects.find(
        {"user_id": user_id, "status": {"$in": ["active", "open"]}},
        {"_id": 0},
    )
    projects = await cur.to_list(80)
    for p in projects:
        pt = _norm(p.get("title") or "")
        if not pt:
            continue
        if pt == needle or needle in pt or pt in needle:
            if not flow or p.get("flow") in (None, flow, "generic"):
                return p
    # Fallback: life_nodes goals
    nodes = await db.life_nodes.find(
        {"user_id": user_id, "status": "active", "type": "goal"},
        {"_id": 0},
    ).to_list(80)
    for n in nodes:
        pt = _norm(n.get("label") or "")
        if pt and (pt == needle or needle in pt or pt in needle):
            return {
                "id": n["id"],
                "title": n.get("label"),
                "life_node_id": n["id"],
                "origin": "life_node",
            }
    return None


async def ensure_brain_node(
    life_graph,
    knowledge,
    *,
    user_id: str,
    title: str,
    flow: str,
    existing_node_id: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
) -> str:
    if existing_node_id:
        node = await life_graph.get_node(user_id, existing_node_id) if hasattr(life_graph, "get_node") else None
        if node:
            return existing_node_id
        # soft check
        found = await life_graph.nodes_col.find_one(
            {"id": existing_node_id, "user_id": user_id}, {"_id": 0, "id": 1},
        )
        if found:
            return existing_node_id

    node = await life_graph.create_node(
        user_id,
        type="goal",
        label=title[:120],
        description=f"Flusso Action Engine: {flow}",
        attributes={
            "action_engine_flow": flow,
            "source_type": source_type,
            "source_id": source_id,
        },
        origin="action_engine",
    )
    await knowledge.merge(
        user_id,
        node["id"],
        {
            "summary": f"Priorità guidata ORA ({flow}): {title}",
            "tags": ["action_engine", flow],
        },
        source_type="action_engine",
        actor_type="system",
        actor_id="action_engine",
        reason="session_open",
    )
    return node["id"]


async def record_answer(
    knowledge,
    *,
    user_id: str,
    node_id: str,
    brain_key: Optional[str],
    value: Any,
    turn_id: str,
) -> None:
    if not brain_key or node_id is None:
        return
    # Store under notes-friendly + _extra for schema-tolerant keys
    doc = await knowledge.get(user_id, node_id)
    if doc:
        props = doc.get("properties") or {}
        extra = props.get("_extra") if isinstance(props.get("_extra"), dict) else {}
        # _extra may be plain or nested after reads
        raw_extra = extra
        if isinstance(extra, dict) and "value" not in extra:
            pass
        env = props.get(brain_key) or (raw_extra.get(brain_key) if isinstance(raw_extra, dict) else None)
        if isinstance(env, dict) and "value" in env:
            from knowledge.provenance import value_of
            try:
                current = value_of(env)
            except Exception:
                current = env.get("value")
            if current == value:
                return
        elif env == value:
            return

    # Prefer _extra for custom action-engine keys to avoid schema friction
    patch: Dict[str, Any] = {"_extra": {brain_key: value}}
    try:
        await knowledge.merge(
            user_id,
            node_id,
            patch,
            source_type="action_engine",
            actor_type="user",
            actor_id=user_id,
            reason=f"answer:{turn_id}",
        )
    except Exception as e:
        logger.warning("brain record_answer failed: %s", type(e).__name__)


async def upsert_summary(
    knowledge,
    *,
    user_id: str,
    node_id: str,
    summary: str,
    tags: Optional[list] = None,
) -> None:
    patch: Dict[str, Any] = {"summary": summary}
    if tags:
        patch["tags"] = tags
    try:
        await knowledge.merge(
            user_id,
            node_id,
            patch,
            source_type="action_engine",
            actor_type="system",
            actor_id="action_engine",
            reason="session_complete",
        )
    except Exception as e:
        logger.warning("brain summary failed: %s", type(e).__name__)
