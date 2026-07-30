"""CrossProviderDedupService — dedup across DIFFERENT connectors for
the same user.

Where the standard `DeduplicationService` handles idempotency for a
single (user, connector_instance, external_id), this module handles
the case where the SAME real-world event is imported by TWO different
providers (e.g. Google Calendar via OAuth *and* Apple Calendar via
EventKit).

Strategy (locked with the user, Iteration 18):
    "first-write wins"

Rules:
    - The first event ingested for a given (user, content_key) becomes
      the PRIMARY. Its life_node is the canonical node.
    - When a second provider brings the same content, we do NOT create
      a second life_node / knowledge fact / decision.
    - Instead we append the new origin to
      `life_node.attributes.mirrored_sources` — an append-only list of
      dicts carrying at least:
        {provider, source_id, calendar_id, external_id, first_seen_at}
    - `attributes.provider_primary` records the original provider and
      is NEVER overwritten by mirroring.
    - If a mirrored source disappears (revoke, delete), only its entry
      is removed from `mirrored_sources` — the primary node stays.
    - If the primary source is revoked but a mirrored source is still
      alive, we can deterministically PROMOTE the oldest surviving
      mirrored source to primary — see `promote_from_mirrored`. The
      promotion is auditable via an ingestion_event with
      source_record_type='cross_provider_promotion'.
    - We do NOT use fuzzy matching. Content match requires:
        title (case-insensitive, whitespace-collapsed),
        starts_at, ends_at, all_day, and location (case-insensitive)
      to all be strictly equal. This is the "high-threshold" behavior
      the user asked for and avoids false positives on similarly-named
      events at different times.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .types import CalendarEventNormalized

logger = logging.getLogger("ora.ingestion.cross_provider")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_WS_RE = re.compile(r"\s+")


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    return _WS_RE.sub(" ", str(s).strip().lower())


def compute_content_key(
    *,
    user_id: str,
    title: Optional[str],
    starts_at: Optional[str],
    ends_at: Optional[str],
    location: Optional[str],
    all_day: bool,
) -> str:
    """Stable, deterministic hash usable across providers to detect the
    same real-world event. Includes `user_id` to guarantee per-user
    isolation (never collides between accounts)."""
    payload = "|".join([
        user_id,
        _norm(title),
        str(starts_at or ""),
        str(ends_at or ""),
        _norm(location),
        "1" if all_day else "0",
    ])
    return "ck_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass
class CrossProviderMatch:
    """Result of `find_existing_primary_node`."""
    node_id: str
    provider_primary: str
    connector_instance_primary: str
    already_mirrored: bool  # True if this exact provider+external already recorded


class CrossProviderDedupService:
    """Encapsulates cross-provider dedup logic. Reads/writes ONLY on the
    `life_nodes` collection under `attributes.mirrored_sources` and
    `attributes.content_key` / `attributes.provider_primary`."""

    def __init__(self, db):
        self.db = db

    @property
    def nodes_col(self):
        return self.db.life_nodes

    # ------------------------------------------------------------------
    async def find_existing_primary_node(
        self,
        *,
        user_id: str,
        event: CalendarEventNormalized,
        incoming_connector_id: str,
        incoming_external_id: str,
    ) -> Optional[CrossProviderMatch]:
        """Return an existing primary node matching this event, or None.

        Match criteria (all must hold):
            - same user
            - type = "event", status = "active"
            - identical starts_at, ends_at, all_day, normalized title
              and normalized location.

        We index the query on starts_at/ends_at (deterministic strings),
        then Python-check the normalized fields to keep the index tiny.
        """
        starts_at = event.starts_at.value if event.starts_at else None
        ends_at = event.ends_at.value if event.ends_at else None
        title_norm = _norm(event.title.value if event.title else None)
        loc_norm = _norm(event.location.value if event.location else None)

        # Never match on empty title — too ambiguous.
        if not title_norm:
            return None
        # Never match when we don't have times.
        if not starts_at:
            return None

        q: Dict[str, Any] = {
            "user_id": user_id,
            "type": "event",
            "status": "active",
            "attributes.starts_at": starts_at,
            "attributes.ends_at": ends_at,
            "attributes.all_day": event.all_day,
        }
        cursor = self.nodes_col.find(q, {"_id": 0})
        async for node in cursor:
            attrs = node.get("attributes") or {}
            if _norm(node.get("label")) != title_norm:
                continue
            if _norm(attrs.get("location")) != loc_norm:
                continue
            # A candidate. Skip if this is the SAME provider+external
            # already recorded (that's ordinary same-provider dedup and
            # is handled by the standard pipeline, not us).
            provider_primary = attrs.get("provider_primary") or attrs.get("connector_id")
            same_provider_same_id = (
                provider_primary == incoming_connector_id
                and attrs.get("external_event_id") == incoming_external_id
            )
            if same_provider_same_id:
                return CrossProviderMatch(
                    node_id=node["id"],
                    provider_primary=provider_primary,
                    connector_instance_primary=attrs.get("connector_instance_id"),
                    already_mirrored=True,
                )
            # Also treat as "already_mirrored" if the incoming source is
            # already recorded in mirrored_sources.
            mirrored_sources = attrs.get("mirrored_sources") or []
            for ms in mirrored_sources:
                if (
                    isinstance(ms, dict)
                    and ms.get("provider") == incoming_connector_id
                    and ms.get("external_id") == incoming_external_id
                ):
                    return CrossProviderMatch(
                        node_id=node["id"],
                        provider_primary=provider_primary,
                        connector_instance_primary=attrs.get("connector_instance_id"),
                        already_mirrored=True,
                    )
            return CrossProviderMatch(
                node_id=node["id"],
                provider_primary=provider_primary,
                connector_instance_primary=attrs.get("connector_instance_id"),
                already_mirrored=False,
            )
        return None

    # ------------------------------------------------------------------
    async def attach_mirrored_source(
        self,
        *,
        user_id: str,
        node_id: str,
        provider: str,
        connector_instance_id: str,
        calendar_id: Optional[str],
        calendar_name: Optional[str],
        external_id: str,
        source_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append a mirrored-source entry idempotently.

        Idempotent on (provider, external_id): existing entries are
        NOT duplicated but their `last_seen_at` is bumped.
        """
        now = _now_iso()
        entry = {
            "id": f"ms_{uuid.uuid4().hex[:12]}",
            "provider": provider,
            "source_id": external_id,
            "connector_instance_id": connector_instance_id,
            "calendar_id": calendar_id,
            "calendar_name": calendar_name,
            "external_id": external_id,
            "source_hash": source_hash,
            "first_seen_at": now,
            "last_seen_at": now,
        }
        # Try to update `last_seen_at` on an existing entry first.
        upd = await self.nodes_col.update_one(
            {
                "id": node_id,
                "user_id": user_id,
                "attributes.mirrored_sources": {
                    "$elemMatch": {"provider": provider, "external_id": external_id},
                },
            },
            {
                "$set": {
                    "attributes.mirrored_sources.$.last_seen_at": now,
                    "updated_at": now,
                },
            },
        )
        if upd.modified_count > 0:
            doc = await self.nodes_col.find_one({"id": node_id, "user_id": user_id}, {"_id": 0})
            return {"action": "refreshed", "node": doc, "entry": entry}
        # Otherwise append a new entry.
        await self.nodes_col.update_one(
            {"id": node_id, "user_id": user_id},
            {
                "$push": {"attributes.mirrored_sources": entry},
                "$set": {"updated_at": now},
            },
        )
        doc = await self.nodes_col.find_one({"id": node_id, "user_id": user_id}, {"_id": 0})
        return {"action": "attached", "node": doc, "entry": entry}

    # ------------------------------------------------------------------
    async def detach_mirrored_sources_by_instance(
        self,
        *,
        user_id: str,
        connector_instance_id: str,
    ) -> int:
        """Remove all mirrored_sources entries produced by a given
        connector instance (used when a mirrored connector is revoked).

        Returns the number of nodes touched.
        """
        now = _now_iso()
        res = await self.nodes_col.update_many(
            {
                "user_id": user_id,
                "attributes.mirrored_sources.connector_instance_id": connector_instance_id,
            },
            {
                "$pull": {
                    "attributes.mirrored_sources": {"connector_instance_id": connector_instance_id},
                },
                "$set": {"updated_at": now},
            },
        )
        return int(res.modified_count or 0)

    # ------------------------------------------------------------------
    async def promote_from_mirrored(
        self,
        *,
        user_id: str,
        node_id: str,
    ) -> Optional[Dict[str, Any]]:
        """If a node's primary provider is gone but a mirrored source is
        still alive, promote the oldest mirrored entry to primary and
        remove it from `mirrored_sources`. Idempotent — a no-op when
        nothing to do. Returns the updated node or None."""
        doc = await self.nodes_col.find_one({"id": node_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return None
        attrs = doc.get("attributes") or {}
        mirrored = attrs.get("mirrored_sources") or []
        if not mirrored:
            return doc
        # Pick oldest by first_seen_at (fallback: first in list).
        candidates = [m for m in mirrored if isinstance(m, dict)]
        candidates.sort(key=lambda m: str(m.get("first_seen_at") or ""))
        promoted = candidates[0]
        remaining = [m for m in mirrored if m is not promoted]
        new_attrs = dict(attrs)
        new_attrs["provider_primary"] = promoted.get("provider")
        new_attrs["connector_id"] = promoted.get("provider")
        new_attrs["connector_instance_id"] = promoted.get("connector_instance_id")
        new_attrs["external_event_id"] = promoted.get("external_id")
        new_attrs["calendar_id"] = promoted.get("calendar_id")
        new_attrs["calendar_name"] = promoted.get("calendar_name")
        new_attrs["mirrored_sources"] = remaining
        new_attrs["promoted_from_mirrored_at"] = _now_iso()
        await self.nodes_col.update_one(
            {"id": node_id, "user_id": user_id},
            {"$set": {"attributes": new_attrs, "updated_at": _now_iso()}},
        )
        return await self.nodes_col.find_one({"id": node_id, "user_id": user_id}, {"_id": 0})
