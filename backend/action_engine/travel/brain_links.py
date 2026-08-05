"""Brain relations: trip ↔ destination ↔ docs ↔ calendar ↔ maps ↔ people."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from action_engine.models import now_iso

logger = logging.getLogger("ora.action_engine.travel.brain")


def _escape(s: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "." for c in (s or ""))


async def _ensure_edge(
    db, life_graph, *, user_id: str, from_id: str, to_id: str, edge_type: str, dedupe: str, plan_id: str,
) -> Optional[str]:
    existing = await db.life_edges.find_one(
        {"user_id": user_id, "attributes.dedupe_key": dedupe},
        {"_id": 0, "id": 1},
    )
    if existing:
        return existing["id"]
    if hasattr(life_graph, "create_edge"):
        try:
            edge = await life_graph.create_edge(
                user_id,
                from_node=from_id,
                to_node=to_id,
                type=edge_type,
                attributes={"dedupe_key": dedupe, "travel_project_id": plan_id},
            )
            return edge.get("id") if isinstance(edge, dict) else str(edge)
        except Exception:
            pass
    eid = f"edge_{uuid.uuid4().hex[:12]}"
    await db.life_edges.update_one(
        {"user_id": user_id, "attributes.dedupe_key": dedupe},
        {"$setOnInsert": {
            "id": eid,
            "user_id": user_id,
            "from_node": from_id,
            "to_node": to_id,
            "type": edge_type,
            "attributes": {"dedupe_key": dedupe, "travel_project_id": plan_id},
            "created_at": now_iso(),
        }},
        upsert=True,
    )
    return eid


async def link_project_to_brain(
    *,
    life_graph,
    knowledge,
    db,
    user_id: str,
    project: dict,
    existing_brain_node_id: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"brain_node_id": existing_brain_node_id, "edges": [], "created": []}
    dest = project.get("destination") or "viaggio"
    title = project.get("title") or f"Vacanza: {dest}"
    if not life_graph:
        return out

    try:
        trip_id = existing_brain_node_id
        if not trip_id:
            found = await db.life_nodes.find_one(
                {
                    "user_id": user_id,
                    "type": {"$in": ["trip", "event"]},
                    "status": {"$ne": "deleted"},
                    "attributes.kind": "travel_project",
                    "label": {"$regex": f"{_escape(dest)}", "$options": "i"},
                },
                {"_id": 0, "id": 1},
            )
            if found:
                trip_id = found["id"]
            else:
                node = await life_graph.create_node(
                    user_id,
                    type="trip",
                    label=title[:120],
                    description="Travel Project ORA",
                    attributes={
                        "kind": "travel_project",
                        "destination": dest,
                        "start_date": project.get("start_date"),
                        "end_date": project.get("end_date"),
                        "travel_project_id": project.get("id"),
                    },
                    origin="action_engine_travel",
                )
                trip_id = node["id"]
                out["created"].append(trip_id)
        else:
            await db.life_nodes.update_one(
                {"id": trip_id, "user_id": user_id},
                {"$set": {
                    "attributes.destination": dest,
                    "attributes.start_date": project.get("start_date"),
                    "attributes.end_date": project.get("end_date"),
                    "attributes.travel_project_id": project.get("id"),
                    "updated_at": now_iso(),
                }},
            )
        out["brain_node_id"] = trip_id

        # Destination as generic place-like node (Life Graph has no place type)
        place = await db.life_nodes.find_one(
            {
                "user_id": user_id,
                "status": {"$ne": "deleted"},
                "attributes.kind": "travel_destination",
                "label": {"$regex": f"^{_escape(dest)}$", "$options": "i"},
            },
            {"_id": 0, "id": 1},
        )
        if not place:
            place = await life_graph.create_node(
                user_id,
                type="generic",
                label=dest[:120],
                attributes={"kind": "travel_destination"},
                origin="action_engine_travel",
            )
            out["created"].append(place["id"])
        eid = await _ensure_edge(
            db, life_graph,
            user_id=user_id, from_id=trip_id, to_id=place["id"],
            edge_type="related_to", dedupe=f"travel_dest:{trip_id}:{place['id']}",
            plan_id=project.get("id") or "",
        )
        if eid:
            out["edges"].append(eid)

        # Documents
        for doc_id in project.get("document_ids") or []:
            doc_node = await db.life_nodes.find_one(
                {"user_id": user_id, "attributes.document_id": doc_id, "status": {"$ne": "deleted"}},
                {"_id": 0, "id": 1},
            )
            if not doc_node:
                doc = await db.documents.find_one(
                    {"id": doc_id, "user_id": user_id},
                    {"_id": 0, "display_title": 1, "filename": 1},
                )
                doc_node = await life_graph.create_node(
                    user_id,
                    type="document",
                    label=(doc or {}).get("display_title") or (doc or {}).get("filename") or doc_id,
                    attributes={"document_id": doc_id, "kind": "travel_doc"},
                    origin="action_engine_travel",
                )
                out["created"].append(doc_node["id"])
            eid = await _ensure_edge(
                db, life_graph,
                user_id=user_id, from_id=trip_id, to_id=doc_node["id"],
                edge_type="documents",
                dedupe=f"travel_doc:{trip_id}:{doc_id}",
                plan_id=project.get("id") or "",
            )
            if eid:
                out["edges"].append(eid)

        # Maps link as knowledge property (no fake place)
        maps = project.get("maps") or {}
        if knowledge and trip_id:
            try:
                await knowledge.upsert_properties(
                    user_id, trip_id,
                    {
                        "travel_project_id": project.get("id"),
                        "destination": dest,
                        "departure_place": project.get("departure_place"),
                        "maps_deep_link": maps.get("deep_link"),
                        "transport": project.get("transport"),
                        "start_date": project.get("start_date"),
                        "end_date": project.get("end_date"),
                    },
                )
            except Exception:
                try:
                    from action_engine.brain import upsert_summary
                    await upsert_summary(
                        knowledge,
                        user_id=user_id,
                        node_id=trip_id,
                        summary=f"Viaggio {dest} {project.get('start_date')}–{project.get('end_date')}",
                        tags=["travel_project", "action_engine"],
                    )
                except Exception:
                    pass

        # Companion people (count only unless names provided)
        for name in project.get("companion_names") or []:
            if not name:
                continue
            person = await db.life_nodes.find_one(
                {
                    "user_id": user_id,
                    "type": "person",
                    "label": {"$regex": f"^{_escape(name)}$", "$options": "i"},
                    "status": {"$ne": "deleted"},
                },
                {"_id": 0, "id": 1},
            )
            if not person:
                person = await life_graph.create_node(
                    user_id,
                    type="person",
                    label=name[:80],
                    attributes={"kind": "travel_companion"},
                    origin="action_engine_travel",
                )
                out["created"].append(person["id"])
            eid = await _ensure_edge(
                db, life_graph,
                user_id=user_id, from_id=trip_id, to_id=person["id"],
                edge_type="related_to",
                dedupe=f"travel_person:{trip_id}:{person['id']}",
                plan_id=project.get("id") or "",
            )
            if eid:
                out["edges"].append(eid)

    except Exception as e:
        logger.info("travel brain link soft-fail: %s", type(e).__name__)
    return out
