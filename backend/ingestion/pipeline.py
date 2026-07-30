"""Pipeline runner — receive → normalize → dedupe → route → process."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .deduplication import (
    DEDUP_ACTION_INSERT,
    DEDUP_ACTION_SKIP_UNCHANGED,
    DEDUP_ACTION_UPDATE_SUPERSEDED,
    DeduplicationService,
)
from .event_model import IngestionEventRepository, compute_payload_hash
from .routing import CalendarEventRouter
from .types import (
    INGESTION_STATUS_FAILED,
    INGESTION_STATUS_NORMALIZED,
    INGESTION_STATUS_PROCESSED,
    INGESTION_STATUS_QUARANTINED,
    INGESTION_STATUS_RECEIVED,
    INGESTION_STATUS_SKIPPED,
    CalendarEventNormalized,
    IngestionOutcome,
    RoutingActions,
)

logger = logging.getLogger("ora.ingestion.pipeline")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IngestionPipeline:
    def __init__(
        self,
        *,
        repo: IngestionEventRepository,
        dedup: DeduplicationService,
        router: CalendarEventRouter,
    ):
        self.repo = repo
        self.dedup = dedup
        self.router = router

    async def ingest_calendar_event(
        self,
        *,
        user_id: str,
        connector_id: str,
        connector_instance_id: str,
        normalized: CalendarEventNormalized,
        source_created_at: Optional[str],
        source_updated_at: Optional[str],
        raw_reference: Optional[Dict[str, Any]] = None,
        sensitivity: str = "personal",
        correlation_id: Optional[str] = None,
    ) -> IngestionOutcome:
        norm_dict = normalized.to_dict()
        # payload_hash MUST be stable across re-normalizations of the same
        # source payload. `normalized.source_hash` is computed from the raw
        # input fields ONLY, so it's the right identity here — the
        # `norm_dict` includes provenance timestamps (`observed_at`) that
        # change on every call and would defeat dedup.
        payload_hash = normalized.source_hash

        # 1) Deduplication decision
        decision = await self.dedup.decide(
            user_id=user_id,
            connector_instance_id=connector_instance_id,
            external_id=normalized.external_event_id,
            external_version=normalized.source_hash,
            payload_hash=payload_hash,
        )

        # 2) Insert IngestionEvent (received)
        event_doc = await self.repo.insert(
            user_id=user_id,
            connector_id=connector_id,
            connector_instance_id=connector_instance_id,
            external_id=normalized.external_event_id,
            external_version=normalized.source_hash,
            source_type=connector_id,
            source_record_type="calendar_event",
            raw_reference=raw_reference,
            normalized_payload=norm_dict,
            payload_hash=payload_hash,
            source_created_at=source_created_at,
            source_updated_at=source_updated_at,
            provenance={
                "connector_id": connector_id,
                "connector_instance_id": connector_instance_id,
                "source_type": connector_id,
            },
            sensitivity=sensitivity,
            status=INGESTION_STATUS_RECEIVED,
            correlation_id=correlation_id,
        )
        event_id = event_doc["id"]

        # 3) Mark normalized
        await self.repo.update_status(event_id, status=INGESTION_STATUS_NORMALIZED)

        # 4) Handle dedup outcomes
        if decision.action == DEDUP_ACTION_SKIP_UNCHANGED:
            await self.repo.update_status(
                event_id, status=INGESTION_STATUS_SKIPPED, processed_at=_now_iso(),
            )
            return IngestionOutcome(
                event_id=event_id, status=INGESTION_STATUS_SKIPPED,
                external_id=normalized.external_event_id,
                external_version=normalized.source_hash,
            )

        superseded_id: Optional[str] = None
        if decision.action == DEDUP_ACTION_UPDATE_SUPERSEDED and decision.previous_event_id:
            await self.repo.mark_superseded(decision.previous_event_id)
            superseded_id = decision.previous_event_id
            await self.repo.update_status(event_id, status=INGESTION_STATUS_NORMALIZED, supersedes_event_id=superseded_id)

        # 5) Route to ORA services
        try:
            actions: RoutingActions = await self.router.route(
                user_id=user_id,
                event=normalized,
                connector_id=connector_id,
                connector_instance_id=connector_instance_id,
                ingestion_event_id=event_id,
            )
        except Exception as e:
            logger.exception("routing failed for event=%s", event_id)
            await self.repo.update_status(
                event_id, status=INGESTION_STATUS_FAILED, error_code=str(e)[:200], processed_at=_now_iso(),
            )
            return IngestionOutcome(
                event_id=event_id, status=INGESTION_STATUS_FAILED,
                external_id=normalized.external_event_id,
                external_version=normalized.source_hash,
                error_code="routing_error",
                superseded_event_id=superseded_id,
            )

        # 6) Processed
        await self.repo.update_status(
            event_id, status=INGESTION_STATUS_PROCESSED, processed_at=_now_iso(),
        )

        outcome = IngestionOutcome(
            event_id=event_id,
            status=INGESTION_STATUS_PROCESSED,
            external_id=normalized.external_event_id,
            external_version=normalized.source_hash,
            routing=actions,
            superseded_event_id=superseded_id,
        )
        return outcome

    async def quarantine_malformed(
        self,
        *,
        user_id: str,
        connector_id: str,
        connector_instance_id: str,
        external_id: str,
        error_code: str,
        raw_reference: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> IngestionOutcome:
        doc = await self.repo.quarantine(
            user_id=user_id,
            connector_id=connector_id,
            connector_instance_id=connector_instance_id,
            external_id=external_id,
            error_code=error_code,
            raw_reference=raw_reference,
            correlation_id=correlation_id,
        )
        return IngestionOutcome(
            event_id=doc["id"],
            status=INGESTION_STATUS_QUARANTINED,
            external_id=external_id,
            external_version=None,
            error_code=error_code,
        )
