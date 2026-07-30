"""ORA Ingestion Core.

Generic ingest → normalize → dedupe → route → process pipeline.
No connector-specific logic lives here; sources plug into it.
"""
from .service import IngestionService
from .types import (
    INGESTION_STATUS_DEDUPLICATED,
    INGESTION_STATUS_FAILED,
    INGESTION_STATUS_NORMALIZED,
    INGESTION_STATUS_PROCESSED,
    INGESTION_STATUS_QUARANTINED,
    INGESTION_STATUS_RECEIVED,
    INGESTION_STATUS_SKIPPED,
    INGESTION_STATUS_SUPERSEDED,
    INGESTION_STATUSES,
    CalendarEventNormalized,
    IngestionOutcome,
    RoutedEntity,
    RoutingActions,
)

__all__ = [
    "IngestionService",
    "CalendarEventNormalized",
    "IngestionOutcome",
    "RoutedEntity",
    "RoutingActions",
    "INGESTION_STATUSES",
    "INGESTION_STATUS_RECEIVED",
    "INGESTION_STATUS_NORMALIZED",
    "INGESTION_STATUS_PROCESSED",
    "INGESTION_STATUS_SUPERSEDED",
    "INGESTION_STATUS_SKIPPED",
    "INGESTION_STATUS_FAILED",
    "INGESTION_STATUS_QUARANTINED",
]
