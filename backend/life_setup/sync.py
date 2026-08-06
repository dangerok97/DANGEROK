"""Sync Life Profile → Life Graph / Brain / Goal / Proactive hooks."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.life_setup.sync")

DOMAIN_NODE_TYPE = {
    "casa": "home",
    "auto": "car",
    "studio": "university",
    "lavoro": "job",
    "salute": "health",
    "famiglia": "person",
    "animali": "pet",
    "viaggi": "trip",
    "finanze": "finance",
    "documenti": "document",
    "assicurazioni": "contract",
    "abbonamenti": "subscription",
    "internet": "subscription",
    "servizi": "generic",
}

DOMAIN_GOAL_TITLE = {
    "casa": "Casa",
    "auto": "Auto",
    "studio": "Studio",
    "lavoro": "Lavoro",
    "salute": "Salute",
    "famiglia": "Famiglia",
    "animali": "Animali",
    "viaggi": "Viaggi",
    "finanze": "Finanze",
    "assicurazioni": "Assicurazioni",
}


async def sync_domain_to_life_graph(
    life_graph,
    user_id: str,
    domain: str,
    *,
    label: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    existing_node_id: Optional[str] = None,
) -> Optional[str]:
    if life_graph is None:
        return existing_node_id
    try:
        ntype = DOMAIN_NODE_TYPE.get(domain, "generic")
        lbl = label or DOMAIN_GOAL_TITLE.get(domain) or domain.title()
        attrs = {"life_setup_domain": domain, **(attributes or {})}
        if existing_node_id:
            try:
                await life_graph.update_node(
                    user_id,
                    existing_node_id,
                    {"attributes": attrs, "label": lbl},
                )
            except Exception:
                pass
            return existing_node_id
        node = await life_graph.create_node(
            user_id,
            type=ntype,
            label=lbl,
            description=f"Dominio {domain} da conversazione Life Setup",
            attributes=attrs,
            origin="life_setup",
        )
        return node.get("id") if isinstance(node, dict) else None
    except Exception:
        logger.exception("life graph sync failed for %s", domain)
        return existing_node_id


async def sync_domain_goal(
    db,
    user_id: str,
    domain: str,
    *,
    brain_node_id: Optional[str] = None,
    linked_documents: Optional[List[str]] = None,
    existing_goal_id: Optional[str] = None,
) -> Optional[str]:
    """Shadow goal from domain — idea/planning, not irreversible."""
    try:
        from goal_engine import GoalService
        from goal_engine.models import Goal
        from deps import knowledge as _kn, life_graph as _lg

        svc = GoalService(db, life_graph=_lg, knowledge=_kn)
        title = DOMAIN_GOAL_TITLE.get(domain) or domain.title()
        idem = f"life_setup:{user_id}:{domain}"
        if existing_goal_id:
            return existing_goal_id
        # Try find by idempotency
        existing = await db.goals.find_one(
            {"user_id": user_id, "idempotency_key": idem},
            {"_id": 0, "id": 1},
        )
        if existing:
            return existing["id"]
        gtype = "generic"
        if domain == "studio":
            gtype = "study"
        elif domain == "viaggi":
            gtype = "travel"
        elif domain == "salute":
            gtype = "medical"
        goal = Goal(
            user_id=user_id,
            goal_type=gtype,  # type: ignore[arg-type]
            title=title,
            description=f"Obiettivo ombra dal dominio {domain} (Life Setup conversation)",
            status="idea",
            brain_node_id=brain_node_id,
            linked_documents=list(linked_documents or []),
            idempotency_key=idem,
            created_from={
                "source_type": "life_setup",
                "domain": domain,
                "shadow": True,
            },
        )
        # Prefer upsert API if present
        if hasattr(svc, "upsert"):
            res = await svc.upsert(goal)
            if isinstance(res, dict):
                return res.get("id") or goal.id
            if hasattr(res, "id"):
                return res.id
        await db.goals.update_one(
            {"user_id": user_id, "idempotency_key": idem},
            {"$set": goal.model_dump()},
            upsert=True,
        )
        return goal.id
    except Exception:
        logger.exception("goal sync failed for %s", domain)
        return existing_goal_id


async def link_document_knowledge(
    knowledge,
    user_id: str,
    node_id: Optional[str],
    *,
    facts: Dict[str, Any],
) -> None:
    if not knowledge or not node_id:
        return
    try:
        if hasattr(knowledge, "upsert_facts"):
            await knowledge.upsert_facts(user_id, node_id, facts)
        elif hasattr(knowledge, "merge"):
            await knowledge.merge(user_id, node_id, facts)
    except Exception:
        logger.exception("knowledge link failed")


async def emit_proactive_resume_if_needed(db, user_id: str, suggestion: Dict[str, Any]) -> Optional[str]:
    """Store a single soft resume suggestion — not «Completa il profilo»."""
    try:
        dedupe = f"life_setup_resume:{user_id}"
        existing = await db.proactive_suggestions.find_one(
            {"user_id": user_id, "dedupe_key": dedupe, "status": {"$nin": ["dismissed", "completed"]}},
            {"_id": 0, "id": 1},
        )
        if existing:
            return existing.get("id")
        from proactive_engine.models import Suggestion, SuggestionAction
        from datetime import datetime, timezone

        sug = Suggestion(
            user_id=user_id,
            title=suggestion.get("title") or "ORA può aiutarti ancora di più",
            description=suggestion.get("description"),
            reason=suggestion.get("reason") or "",
            type="life",  # type: ignore[arg-type]
            source="life_setup_interrupt",
            action=SuggestionAction(
                kind=(suggestion.get("action") or {}).get("kind") or "resume_life_conversation",
                label=(suggestion.get("action") or {}).get("label") or "Continua con ORA",
                route=(suggestion.get("action") or {}).get("route") or "/life-setup?resume=1",
            ),
            status="active",
            dedupe_key=dedupe,
            importance=0.55,
            urgency=0.3,
            confidence=0.8,
            score=0.55,
            meta={"life_setup": True, "wizard": False},
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        await db.proactive_suggestions.update_one(
            {"user_id": user_id, "dedupe_key": dedupe},
            {"$set": sug.model_dump()},
            upsert=True,
        )
        return sug.id
    except Exception:
        logger.exception("proactive resume emit failed")
        return None
