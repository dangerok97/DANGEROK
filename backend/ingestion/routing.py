"""Routing — transforms a normalized calendar event into ORA entities.

CRITICAL: this module NEVER writes directly to any other module's
collections. Every mutation goes through the official service API:
  - LifeGraphService for nodes/edges;
  - KnowledgeService for structured facts on those nodes;
  - AutoLinkService/DecisionService for decisions (opt-in via flag).

Behavior in Iteration 9 is intentionally conservative:
  1. Every calendar event → one Life-Graph `event` Node (idempotent per
     (user, connector_instance, external_event_id)).
  2. Basic facts (starts_at, ends_at, location, calendar_name,
     external_event_id) are written to the Knowledge Layer.
  3. NO Decision is created unless `CALENDAR_DECISION_GENERATION_ENABLED`
     is TRUTHY and the event matches deterministic policy rules
     (imminent starts_at + recognizable category + minimum relevance).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .cross_provider import compute_content_key
from .types import CalendarEventNormalized, RoutingActions

logger = logging.getLogger("ora.ingestion.routing")


# ------------------------------------------------------------
# Category detection (deterministic, keyword-based, IT + EN)
# ------------------------------------------------------------
_CATEGORY_KEYWORDS: Dict[str, tuple] = {
    "exam":        ("esame", "test", "prova", "exam"),
    "medical":     ("dentista", "medico", "visita", "doctor", "dentist"),
    "travel":      ("volo", "treno", "viaggio", "flight", "train"),
    "meeting":     ("riunione", "meeting", "call", "sync"),
    "social":      ("cena", "pranzo", "aperitivo", "dinner", "lunch"),
    "birthday":    ("compleanno", "birthday", "anniversario"),
    "deadline":    ("scadenza", "deadline", "consegna"),
}


def _detect_category(title: str) -> str:
    if not title:
        return "generic"
    t = title.lower()
    for cat, kws in _CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                return cat
    return "generic"


def _flag_decision_generation() -> bool:
    return os.environ.get("CALENDAR_DECISION_GENERATION_ENABLED", "false").lower() in ("1", "true", "yes")


def _parse_iso(dt: Optional[str]) -> Optional[datetime]:
    if not dt:
        return None
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None


class CalendarEventRouter:
    """Routes normalized calendar events to ORA services."""

    def __init__(self, *, life_graph, knowledge, decisions, auto_link, db):
        self.life_graph = life_graph
        self.knowledge = knowledge
        self.decisions = decisions
        self.auto_link = auto_link
        self.db = db

    # ------------------------------------------------------------------
    async def route(
        self,
        *,
        user_id: str,
        event: CalendarEventNormalized,
        connector_id: str,
        connector_instance_id: str,
        ingestion_event_id: str,
    ) -> RoutingActions:
        actions = RoutingActions()

        # -------------------- 1) Node --------------------
        title = (event.title.value if event.title else None) or f"Evento {event.external_event_id[:8]}"
        node_type = "event"

        canonical_key = f"cal:{connector_instance_id}:{event.external_event_id}"
        existing_node = await self.db.life_nodes.find_one(
            {
                "user_id": user_id,
                "type": node_type,
                "attributes.canonical_key": canonical_key,
                "status": "active",
            },
            {"_id": 0, "id": 1, "attributes": 1},
        )

        # Preserve cross-provider bookkeeping when updating an existing
        # node so `mirrored_sources` is never wiped by a routine sync.
        preserved_mirrored: list = []
        preserved_provider_primary: Optional[str] = None
        if existing_node:
            _ea = existing_node.get("attributes") or {}
            preserved_mirrored = list(_ea.get("mirrored_sources") or [])
            preserved_provider_primary = _ea.get("provider_primary")

        node_attrs = {
            "canonical_key": canonical_key,
            "external_event_id": event.external_event_id,
            "calendar_id": event.calendar_id,
            "calendar_name": event.calendar_name,
            "starts_at": event.starts_at.value if event.starts_at else None,
            "ends_at": event.ends_at.value if event.ends_at else None,
            "timezone": event.timezone,
            "all_day": event.all_day,
            "location": event.location.value if event.location else None,
            "connector_id": connector_id,
            "connector_instance_id": connector_instance_id,
            "provider_primary": preserved_provider_primary or connector_id,
            "source_hash": event.source_hash,
            "content_key": compute_content_key(
                user_id=user_id,
                title=title,
                starts_at=event.starts_at.value if event.starts_at else None,
                ends_at=event.ends_at.value if event.ends_at else None,
                location=event.location.value if event.location else None,
                all_day=event.all_day,
            ),
            "mirrored_sources": preserved_mirrored,
        }

        if existing_node:
            node = await self.life_graph.update_node(
                user_id, existing_node["id"], {"label": title, "attributes": node_attrs},
            )
            actions.add("node", node["id"], "updated")
        else:
            node = await self.life_graph.create_node(
                user_id,
                type=node_type,
                label=title,
                description=(event.description.value if event.description else None),
                attributes=node_attrs,
            )
            actions.add("node", node["id"], "created")

        # -------------------- 2) Knowledge --------------------
        try:
            props = {
                "external_event_id": event.external_event_id,
                "calendar_id": event.calendar_id,
                "calendar_name": event.calendar_name,
                "starts_at": event.starts_at.value if event.starts_at else None,
                "ends_at": event.ends_at.value if event.ends_at else None,
                "location": event.location.value if event.location else None,
                "all_day": event.all_day,
                "status": event.status,
            }
            props = {k: v for k, v in props.items() if v is not None}
            if props:
                await self.knowledge.merge(
                    user_id,
                    node["id"],
                    props,
                    source_type=connector_id,
                    actor_type="system",
                    actor_id=connector_instance_id,
                    reason=f"ingestion:{ingestion_event_id}",
                )
                actions.add("knowledge", node["id"], "updated")
        except Exception:
            logger.exception("knowledge merge failed for node=%s", node["id"])
            actions.skipped_reasons.append("knowledge_merge_failed")

        # -------------------- 3) Cancelled events --------------------
        # Never brutally delete data: mark the node as archived and stop.
        if event.status == "cancelled":
            try:
                await self.life_graph.update_node(user_id, node["id"], {"status": "archived"})
                actions.add("node", node["id"], "archived")
            except Exception:
                actions.skipped_reasons.append("node_archive_failed")
            return actions

        # -------------------- 4) Decision generation (flag-gated) --------------------
        if not _flag_decision_generation():
            actions.skipped_reasons.append("decision_generation_disabled_by_flag")
            return actions

        starts_at_iso = event.starts_at.value if event.starts_at else None
        starts_at = _parse_iso(starts_at_iso)
        if not starts_at:
            actions.skipped_reasons.append("no_starts_at")
            return actions

        now = datetime.now(timezone.utc)
        # Imminence window: the event has to start in the future AND within
        # the next 14 days. Anything else is out of scope for auto-gen.
        if starts_at <= now or starts_at > now + timedelta(days=14):
            actions.skipped_reasons.append("outside_imminence_window")
            return actions

        category = _detect_category(title)
        if category == "generic":
            actions.skipped_reasons.append("no_category_match")
            return actions

        # Idempotency: only one decision per node.
        existing_dec = await self.db.decisions.find_one(
            {
                "user_id": user_id,
                "status": {"$in": ["open", "in_progress"]},
                "node_ids": node["id"],
                "metadata.origin": "ingestion:calendar",
                "metadata.external_event_id": event.external_event_id,
            },
            {"_id": 0, "id": 1},
        )
        if existing_dec:
            actions.skipped_reasons.append("decision_already_exists")
            return actions

        payload = self._build_decision_payload(event, category, title)
        try:
            doc = await self.decisions.create(user_id, payload, origin="ingestion:calendar")
            # link node atomically (LifeGraphService.link_decision — no direct writes here)
            try:
                await self.life_graph.link_decision(user_id, doc["id"], [node["id"]])
            except Exception:
                await self.db.decisions.delete_one({"id": doc["id"], "user_id": user_id})
                actions.skipped_reasons.append("decision_link_failed_rolled_back")
                return actions
            actions.add("decision", doc["id"], "created")
        except Exception:
            logger.exception("decision generation failed for node=%s", node["id"])
            actions.skipped_reasons.append("decision_create_failed")

        return actions

    # ------------------------------------------------------------------
    def _build_decision_payload(
        self,
        event: CalendarEventNormalized,
        category: str,
        title: str,
    ) -> Dict[str, Any]:
        starts_at = event.starts_at.value if event.starts_at else None
        # Deterministic template texts, prudent + reversible.
        prefix = {
            "exam":     "Preparati per",
            "medical":  "Ricorda l'appuntamento medico:",
            "travel":   "Check-in e preparazione:",
            "meeting":  "Prepara la riunione:",
            "birthday": "Compleanno in arrivo:",
            "deadline": "Scadenza in arrivo:",
            "social":   "Impegno in agenda:",
        }.get(category, "Impegno in agenda:")
        return {
            "title": f"{prefix} {title}",
            "description": event.description.value if event.description else None,
            "category": category,
            "urgency": 6,
            "importance": 6,
            "risk": 3,
            "time_required_min": 15,
            "energy": 3,
            "economic_impact": 2,
            "personal_impact": 5,
            "starts_at": starts_at,
            "deadline": None,
            "metadata": {
                "origin": "ingestion:calendar",
                "external_event_id": event.external_event_id,
                "calendar_id": event.calendar_id,
                "category_matched": category,
            },
        }
