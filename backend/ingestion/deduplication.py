"""Deduplication service.

Uses (user_id, connector_instance_id, external_id, external_version|hash)
as the identity tuple. Returns a DedupDecision that the pipeline uses
to decide whether to insert a fresh event, mark the previous one as
superseded, or skip because nothing changed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .event_model import IngestionEventRepository

DEDUP_ACTION_INSERT = "insert"
DEDUP_ACTION_UPDATE_SUPERSEDED = "update_superseded"
DEDUP_ACTION_SKIP_UNCHANGED = "skip_unchanged"


@dataclass
class DedupDecision:
    action: str
    previous_event_id: Optional[str] = None


class DeduplicationService:
    def __init__(self, repo: IngestionEventRepository):
        self.repo = repo

    async def decide(
        self,
        *,
        user_id: str,
        connector_instance_id: str,
        external_id: str,
        external_version: Optional[str],
        payload_hash: str,
    ) -> DedupDecision:
        prev = await self.repo.find_latest_by_external(
            user_id=user_id,
            connector_instance_id=connector_instance_id,
            external_id=external_id,
        )
        if not prev:
            return DedupDecision(action=DEDUP_ACTION_INSERT)

        prev_hash = prev.get("payload_hash")
        prev_ver = prev.get("external_version")

        if external_version and prev_ver and external_version == prev_ver and payload_hash == prev_hash:
            return DedupDecision(action=DEDUP_ACTION_SKIP_UNCHANGED, previous_event_id=prev["id"])
        if payload_hash and payload_hash == prev_hash:
            return DedupDecision(action=DEDUP_ACTION_SKIP_UNCHANGED, previous_event_id=prev["id"])
        return DedupDecision(action=DEDUP_ACTION_UPDATE_SUPERSEDED, previous_event_id=prev["id"])
