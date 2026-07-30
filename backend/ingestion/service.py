"""IngestionService — public facade of the ingestion module."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .deduplication import DeduplicationService
from .event_model import IngestionEventRepository
from .normalizer import GoogleCalendarNormalizer, NormalizationError
from .pipeline import IngestionPipeline
from .routing import CalendarEventRouter
from .types import IngestionOutcome


class IngestionService:
    """Composition root — builds the ingestion pipeline once and hands
    it to callers (e.g. connectors)."""

    def __init__(self, db, *, life_graph, knowledge, decisions, auto_link):
        self.db = db
        self.repo = IngestionEventRepository(db)
        self.dedup = DeduplicationService(self.repo)
        self.router = CalendarEventRouter(
            life_graph=life_graph,
            knowledge=knowledge,
            decisions=decisions,
            auto_link=auto_link,
            db=db,
        )
        self.pipeline = IngestionPipeline(repo=self.repo, dedup=self.dedup, router=self.router)

    # ----- calendar-specific entrypoint -----
    async def ingest_calendar_events(
        self,
        *,
        user_id: str,
        connector_id: str,
        connector_instance_id: str,
        calendar_id: str,
        calendar_name: Optional[str],
        raw_events: List[Dict[str, Any]],
        correlation_id: Optional[str] = None,
    ) -> List[IngestionOutcome]:
        normalizer = GoogleCalendarNormalizer(
            connector_id=connector_id, connector_instance_id=connector_instance_id,
        )
        outcomes: List[IngestionOutcome] = []
        for raw in raw_events or []:
            ext_id = (raw or {}).get("id") or "unknown"
            try:
                normalized = normalizer.normalize(
                    raw=raw, calendar_id=calendar_id, calendar_name=calendar_name,
                )
            except NormalizationError as e:
                outcome = await self.pipeline.quarantine_malformed(
                    user_id=user_id,
                    connector_id=connector_id,
                    connector_instance_id=connector_instance_id,
                    external_id=ext_id,
                    error_code=e.code,
                    raw_reference={
                        "calendar_id": calendar_id,
                        "external_event_id": ext_id,
                    },
                    correlation_id=correlation_id,
                )
                outcomes.append(outcome)
                continue

            outcome = await self.pipeline.ingest_calendar_event(
                user_id=user_id,
                connector_id=connector_id,
                connector_instance_id=connector_instance_id,
                normalized=normalized,
                source_created_at=raw.get("created"),
                source_updated_at=raw.get("updated"),
                raw_reference={
                    "calendar_id": calendar_id,
                    "external_event_id": normalized.external_event_id,
                    "htmlLink": raw.get("htmlLink"),
                },
                correlation_id=correlation_id,
            )
            outcomes.append(outcome)
        return outcomes

    # ----- read-side helpers used by the routers -----
    async def list_events(
        self,
        user_id: str,
        *,
        connector_id: Optional[str] = None,
        connector_instance_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self.repo.list_for_user(
            user_id,
            connector_id=connector_id,
            connector_instance_id=connector_instance_id,
            status=status,
            limit=limit,
        )

    async def get_event(self, user_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        return await self.repo.get(user_id, event_id)

    async def stats(self, user_id: str) -> Dict[str, Any]:
        return await self.repo.stats(user_id)
