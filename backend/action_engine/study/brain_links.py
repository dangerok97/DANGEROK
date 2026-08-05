"""Brain relations for study plans — no duplicate nodes; user corrections win."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from action_engine.models import now_iso

logger = logging.getLogger("ora.action_engine.study.brain")


async def link_plan_to_brain(
    *,
    life_graph,
    knowledge,
    db,
    user_id: str,
    plan: dict,
    existing_brain_node_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ensure exam/subject/goal nodes and edges; prefer user corrections."""
    out: Dict[str, Any] = {"brain_node_id": existing_brain_node_id, "edges": [], "created": []}
    subject = plan.get("subject") or plan.get("exam_name")
    exam_name = plan.get("exam_name") or subject
    if not life_graph:
        return out

    try:
        # Reuse AE brain node if present
        goal_id = existing_brain_node_id
        if not goal_id:
            # Search existing goal by label
            found = await db.life_nodes.find_one(
                {
                    "user_id": user_id,
                    "type": "goal",
                    "status": {"$ne": "deleted"},
                    "label": {"$regex": f"^{_escape(exam_name)}$", "$options": "i"},
                },
                {"_id": 0, "id": 1},
            )
            if found:
                goal_id = found["id"]
            else:
                node = await life_graph.create_node(
                    user_id,
                    type="goal",
                    label=f"Studio: {exam_name}"[:120],
                    description="Piano di studio ORA",
                    attributes={
                        "kind": "study_plan",
                        "subject": subject,
                        "exam_date": plan.get("exam_date"),
                        "plan_id": plan.get("id"),
                    },
                    origin="action_engine_study",
                )
                goal_id = node["id"]
                out["created"].append(goal_id)
        else:
            # User corrections win — update attributes
            await db.life_nodes.update_one(
                {"id": goal_id, "user_id": user_id},
                {"$set": {
                    "attributes.subject": subject,
                    "attributes.exam_date": plan.get("exam_date"),
                    "attributes.plan_id": plan.get("id"),
                    "updated_at": now_iso(),
                }},
            )

        out["brain_node_id"] = goal_id

        # Link documents without duplicating edges
        for doc_id in plan.get("document_ids") or []:
            edge_key = f"study_doc:{goal_id}:{doc_id}"
            existing_edge = await db.life_edges.find_one(
                {"user_id": user_id, "attributes.dedupe_key": edge_key},
                {"_id": 0, "id": 1},
            )
            if existing_edge:
                out["edges"].append(existing_edge["id"])
                continue
            # Find or create document node
            doc_node = await db.life_nodes.find_one(
                {
                    "user_id": user_id,
                    "attributes.document_id": doc_id,
                    "status": {"$ne": "deleted"},
                },
                {"_id": 0, "id": 1},
            )
            if not doc_node and hasattr(life_graph, "create_node"):
                doc = await db.documents.find_one(
                    {"id": doc_id, "user_id": user_id},
                    {"_id": 0, "display_title": 1, "filename": 1},
                )
                created = await life_graph.create_node(
                    user_id,
                    type="document",
                    label=(doc or {}).get("display_title") or (doc or {}).get("filename") or doc_id,
                    attributes={"document_id": doc_id, "kind": "study_material"},
                    origin="action_engine_study",
                )
                doc_node = created
                out["created"].append(created["id"])
            if doc_node and hasattr(life_graph, "create_edge"):
                try:
                    edge = await life_graph.create_edge(
                        user_id,
                        from_node=goal_id,
                        to_node=doc_node["id"],
                        type="uses_material",
                        attributes={"dedupe_key": edge_key, "plan_id": plan.get("id")},
                    )
                    out["edges"].append(edge.get("id") if isinstance(edge, dict) else edge)
                except Exception:
                    # Fallback raw insert if create_edge signature differs
                    import uuid
                    eid = f"edge_{uuid.uuid4().hex[:12]}"
                    await db.life_edges.update_one(
                        {"user_id": user_id, "attributes.dedupe_key": edge_key},
                        {"$setOnInsert": {
                            "id": eid,
                            "user_id": user_id,
                            "from_node": goal_id,
                            "to_node": doc_node["id"],
                            "type": "uses_material",
                            "attributes": {"dedupe_key": edge_key, "plan_id": plan.get("id")},
                            "created_at": now_iso(),
                        }},
                        upsert=True,
                    )
                    out["edges"].append(eid)

        if knowledge and goal_id:
            try:
                await knowledge.upsert_properties(
                    user_id, goal_id,
                    {
                        "study_plan_id": plan.get("id"),
                        "exam_date": plan.get("exam_date"),
                        "subject": subject,
                        "intensity": plan.get("intensity"),
                    },
                )
            except Exception:
                try:
                    from action_engine.brain import upsert_summary
                    await upsert_summary(
                        knowledge,
                        user_id=user_id,
                        node_id=goal_id,
                        summary=f"Piano studio {exam_name} — {plan.get('intensity')}",
                        tags=["study_plan", "action_engine"],
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.info("brain link soft-fail: %s", type(e).__name__)
    return out


def _escape(s: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "." for c in (s or ""))
