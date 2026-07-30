"""AppleCalendarService — connector orchestration.

Unlike Google Calendar (server-side polling via HTTP), Apple Calendar
is device-native: the iOS/iPadOS client reads events through EventKit
using `expo-calendar` and uploads a sanitized batch to
`POST /instances/{id}/sync`. The backend NEVER contacts Apple; it only:

  1. maintains the ConnectorInstance metadata (per device);
  2. normalizes the incoming payload with `AppleCalendarNormalizer`;
  3. runs cross-provider dedup (first-write wins) before ingestion so
     the same event synced by both Google and Apple never produces a
     duplicate node/knowledge/decision;
  4. hands normalized events to the shared Ingestion pipeline for
     primary events, and attaches mirrored sources on existing nodes
     otherwise.

Enable only through env flag `APPLE_CALENDAR_ENABLED=true`.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ingestion import (
    CrossProviderDedupService,
    INGESTION_STATUS_SKIPPED,
    IngestionOutcome,
)
from ingestion.event_model import IngestionEventRepository
from ingestion.normalizer import NormalizationError
from permissions import ConsentDenied
from permissions.models import INSTANCE_WILDCARD

from ..instances import ConnectorInstanceService
from .normalizer import AppleCalendarNormalizer
from .scopes import (
    APPLE_CALENDAR_CAPABILITY_ID,
    APPLE_CALENDAR_CONNECTOR_ID,
    APPLE_CALENDAR_SCOPES,
    is_apple_calendar_enabled,
)

logger = logging.getLogger("ora.connectors.apple_calendar")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


class AppleCalendarFeatureDisabled(Exception):
    """Raised when APPLE_CALENDAR_ENABLED is false but the caller tried
    to use the connector."""


class AppleCalendarService:
    def __init__(self, *, db, permissions, ingestion):
        self.db = db
        self.permissions = permissions
        self.ingestion = ingestion
        self.instances = ConnectorInstanceService(db)
        self.cross_provider = CrossProviderDedupService(db)
        self.ingestion_repo = IngestionEventRepository(db)

    # ------------------------------------------------------------------
    # Feature-flag guard
    # ------------------------------------------------------------------
    def _require_enabled(self) -> None:
        if not is_apple_calendar_enabled():
            raise AppleCalendarFeatureDisabled(
                "Apple Calendar connector is disabled (APPLE_CALENDAR_ENABLED=false)."
            )

    # ------------------------------------------------------------------
    async def config_status(self) -> Dict[str, Any]:
        """Diagnostic — reports whether the connector is available. Safe
        to call without authentication in list_available? no: called
        from an authenticated endpoint."""
        env_hint = os.environ.get("ENVIRONMENT", "").strip().lower()
        if env_hint in ("production", "prod"):
            environment = "production"
        elif env_hint in ("test", "testing", "ci"):
            environment = "test"
        else:
            environment = "preview"
        return {
            "enabled": is_apple_calendar_enabled(),
            "connector_id": APPLE_CALENDAR_CONNECTOR_ID,
            "capability_id": APPLE_CALENDAR_CAPABILITY_ID,
            "requires_native_build": True,
            "platforms": ["ios", "ipados"],
            "environment": environment,
            "notes": (
                "Legge il calendario nativo tramite EventKit. Non disponibile "
                "in Expo Go: richiede una build EAS (dev o produzione) su iPhone/iPad."
            ),
        }

    # ------------------------------------------------------------------
    # Instance lifecycle
    # ------------------------------------------------------------------
    async def connect_device(
        self,
        *,
        user_id: str,
        device_id: str,
        device_name: Optional[str] = None,
        platform: Optional[str] = None,
        calendars: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create (or refresh) the connector-instance bound to a device.

        `device_id` MUST be a stable identifier chosen by the client
        (e.g. `Application.getIosIdForVendorAsync()` on iOS). It's used
        as the "provider account id" so a user can have distinct
        instances per iPhone / iPad.
        """
        self._require_enabled()
        if not device_id or not isinstance(device_id, str):
            raise ValueError("device_id required")

        display_label = device_name or "Apple Calendar"
        selected_ids: Optional[List[str]] = None
        cal_meta: Optional[List[Dict[str, Any]]] = None
        if calendars:
            cal_meta = [
                {
                    "id": str(c.get("id")),
                    "title": c.get("title") or c.get("summary"),
                    "color": c.get("color"),
                    "allowsModifications": bool(c.get("allowsModifications") or False),
                    "source": c.get("source"),
                }
                for c in calendars if isinstance(c, dict) and c.get("id")
            ]
            selected_ids = [c["id"] for c in cal_meta]

        instance = await self.instances.upsert(
            user_id=user_id,
            connector_id=APPLE_CALENDAR_CONNECTOR_ID,
            provider_account_id=device_id,
            display_label=display_label,
            platform=(platform or "ios"),
            authorized_scopes=list(APPLE_CALENDAR_SCOPES),
            selected_resource_ids=selected_ids,
            sync_mode="client_push",
            secret_reference=None,  # no tokens on server side
            status="connected",
            metadata={
                "device_id": device_id,
                "device_name": device_name,
                "calendars": cal_meta or [],
                "provider_mode": "eventkit",
                "requires_native_build": True,
            },
            poll_interval_min=0,
            window_past_days=int(os.environ.get("APPLE_CALENDAR_WINDOW_PAST_DAYS", "30")),
            window_future_days=int(os.environ.get("APPLE_CALENDAR_WINDOW_FUTURE_DAYS", "180")),
        )

        # Grant ORA-side consent for calendar.read on this instance.
        try:
            await self.permissions.grant(
                user_id=user_id,
                capability_id=APPLE_CALENDAR_CAPABILITY_ID,
                connector_id=APPLE_CALENDAR_CONNECTOR_ID,
                connector_instance_id=instance["id"],
                purpose_id="context_assembly",
                scopes=list(APPLE_CALENDAR_SCOPES),
                actor_type="user",
            )
        except Exception:
            logger.exception("apple_calendar: permissions grant failed")

        await self.permissions.audit.log(
            user_id=user_id,
            event_type="connector.connect",
            connector_id=APPLE_CALENDAR_CONNECTOR_ID,
            connector_instance_id=instance["id"],
            capability_id=APPLE_CALENDAR_CAPABILITY_ID,
            success=True,
            reason_code="apple_calendar_connected",
            data_classification="personal",
            details={"device_id_hash": instance.get("provider_account_id_hash")},
        )
        return instance

    async def list_instances(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.instances.list(user_id, connector_id=APPLE_CALENDAR_CONNECTOR_ID)

    async def get_instance(self, user_id: str, instance_id: str) -> Optional[Dict[str, Any]]:
        return await self.instances.get(user_id, instance_id)

    async def status(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")
        consent_ok = await self.permissions.check_access(
            user_id=user_id,
            capability_id=APPLE_CALENDAR_CAPABILITY_ID,
            connector_id=APPLE_CALENDAR_CONNECTOR_ID,
            connector_instance_id=instance_id,
            audit=False,
        )
        return {
            "instance": instance,
            "enabled": is_apple_calendar_enabled(),
            "consent_active": consent_ok,
            "connector_id": APPLE_CALENDAR_CONNECTOR_ID,
        }

    async def select_calendars(
        self, *, user_id: str, instance_id: str, calendar_ids: List[str],
    ) -> Dict[str, Any]:
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")
        updated = await self.instances.update(
            user_id, instance_id, {"selected_resource_ids": list(calendar_ids)},
        )
        await self.permissions.audit.log(
            user_id=user_id, event_type="calendar.select",
            connector_id=APPLE_CALENDAR_CONNECTOR_ID,
            connector_instance_id=instance_id,
            capability_id=APPLE_CALENDAR_CAPABILITY_ID,
            success=True, records_requested=len(calendar_ids),
            details={"selected_count": len(calendar_ids)},
        )
        return updated

    # ------------------------------------------------------------------
    # Sync — the ONLY data-write endpoint (the client pushes events)
    # ------------------------------------------------------------------
    async def sync(
        self,
        *,
        user_id: str,
        instance_id: str,
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Ingest a batch of raw EventKit events. Cross-provider dedup
        is applied per-event: if an existing life-node already carries
        the same content (matched by title+start+end+location+all_day),
        we ATTACH a mirrored-source entry rather than creating a new
        node. Otherwise we hand the event to the shared ingestion
        pipeline as a primary event with connector_id=`calendar_apple`.
        """
        self._require_enabled()
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")

        consent_ok = await self.permissions.check_access(
            user_id=user_id,
            capability_id=APPLE_CALENDAR_CAPABILITY_ID,
            connector_id=APPLE_CALENDAR_CONNECTOR_ID,
            connector_instance_id=instance_id,
        )
        if not consent_ok:
            raise ConsentDenied(
                capability_id=APPLE_CALENDAR_CAPABILITY_ID,
                connector_id=APPLE_CALENDAR_CONNECTOR_ID,
                connector_instance_id=instance_id,
            )

        await self.instances.mark_status(user_id, instance_id, "syncing")

        totals = {
            "received": len(events or []),
            "processed": 0,
            "skipped": 0,
            "mirrored": 0,
            "quarantined": 0,
            "failed": 0,
        }
        outcomes: List[Dict[str, Any]] = []

        normalizer = AppleCalendarNormalizer(
            connector_id=APPLE_CALENDAR_CONNECTOR_ID,
            connector_instance_id=instance_id,
        )

        for raw in events or []:
            ext_id = (raw or {}).get("id") or (raw or {}).get("eventIdentifier") or "unknown"
            try:
                normalized = normalizer.normalize(raw=raw)
            except NormalizationError as e:
                q = await self.ingestion.pipeline.quarantine_malformed(
                    user_id=user_id,
                    connector_id=APPLE_CALENDAR_CONNECTOR_ID,
                    connector_instance_id=instance_id,
                    external_id=ext_id,
                    error_code=e.code,
                    raw_reference={"external_event_id": ext_id},
                )
                totals["quarantined"] += 1
                outcomes.append({"external_id": ext_id, "status": "quarantined", "error_code": e.code, "event_id": q.event_id})
                continue

            # Cross-provider dedup lookup.
            match = await self.cross_provider.find_existing_primary_node(
                user_id=user_id,
                event=normalized,
                incoming_connector_id=APPLE_CALENDAR_CONNECTOR_ID,
                incoming_external_id=normalized.external_event_id,
            )

            if match and match.provider_primary != APPLE_CALENDAR_CONNECTOR_ID:
                # Another provider owns the primary node. Attach or
                # refresh the Apple mirrored source.
                res = await self.cross_provider.attach_mirrored_source(
                    user_id=user_id,
                    node_id=match.node_id,
                    provider=APPLE_CALENDAR_CONNECTOR_ID,
                    connector_instance_id=instance_id,
                    calendar_id=normalized.calendar_id,
                    calendar_name=normalized.calendar_name,
                    external_id=normalized.external_event_id,
                    source_hash=normalized.source_hash,
                )
                # Audit trail: a `skipped` ingestion event with a
                # descriptive reason so the pipeline stays queryable.
                doc = await self.ingestion_repo.insert(
                    user_id=user_id,
                    connector_id=APPLE_CALENDAR_CONNECTOR_ID,
                    connector_instance_id=instance_id,
                    external_id=normalized.external_event_id,
                    external_version=normalized.source_hash,
                    source_type=APPLE_CALENDAR_CONNECTOR_ID,
                    source_record_type="calendar_event",
                    raw_reference={
                        "external_event_id": normalized.external_event_id,
                        "cross_provider_match_node_id": match.node_id,
                        "primary_provider": match.provider_primary,
                    },
                    normalized_payload=None,
                    payload_hash=normalized.source_hash,
                    source_created_at=None,
                    source_updated_at=normalized.source_updated_at,
                    provenance={
                        "connector_id": APPLE_CALENDAR_CONNECTOR_ID,
                        "connector_instance_id": instance_id,
                        "source_type": APPLE_CALENDAR_CONNECTOR_ID,
                        "cross_provider_action": res["action"],
                    },
                    sensitivity="personal",
                    status=INGESTION_STATUS_SKIPPED,
                )
                await self.ingestion_repo.update_status(
                    doc["id"],
                    status=INGESTION_STATUS_SKIPPED,
                    error_code="cross_provider_duplicate",
                    processed_at=_now_iso(),
                )
                totals["mirrored"] += 1
                outcomes.append({
                    "external_id": normalized.external_event_id,
                    "status": "mirrored",
                    "node_id": match.node_id,
                    "primary_provider": match.provider_primary,
                    "event_id": doc["id"],
                })
                continue

            # Either no match, or Apple is already the primary — go
            # through the normal ingestion pipeline.
            outcome: IngestionOutcome = await self.ingestion.pipeline.ingest_calendar_event(
                user_id=user_id,
                connector_id=APPLE_CALENDAR_CONNECTOR_ID,
                connector_instance_id=instance_id,
                normalized=normalized,
                source_created_at=None,
                source_updated_at=normalized.source_updated_at,
                raw_reference={
                    "external_event_id": normalized.external_event_id,
                    "calendar_id": normalized.calendar_id,
                },
            )
            if outcome.status == "processed":
                totals["processed"] += 1
            elif outcome.status == "skipped":
                totals["skipped"] += 1
            elif outcome.status == "quarantined":
                totals["quarantined"] += 1
            elif outcome.status == "failed":
                totals["failed"] += 1
            outcomes.append({
                "external_id": normalized.external_event_id,
                "status": outcome.status,
                "event_id": outcome.event_id,
            })

        await self.instances.mark_status(user_id, instance_id, "connected", extra={"last_sync_at": _now_iso()})
        await self.permissions.audit.log(
            user_id=user_id, event_type="calendar.sync",
            connector_id=APPLE_CALENDAR_CONNECTOR_ID,
            connector_instance_id=instance_id,
            capability_id=APPLE_CALENDAR_CAPABILITY_ID,
            success=True,
            records_returned=totals["received"],
            data_classification="personal",
            details={k: v for k, v in totals.items()},
        )
        return {"instance_id": instance_id, "totals": totals, "outcomes": outcomes}

    # ------------------------------------------------------------------
    # Disconnect (soft revoke)
    # ------------------------------------------------------------------
    async def disconnect(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")

        # 1) Revoke ORA-side consent for this instance.
        await self.permissions.revoke(
            user_id=user_id,
            capability_id=APPLE_CALENDAR_CAPABILITY_ID,
            connector_id=APPLE_CALENDAR_CONNECTOR_ID,
            connector_instance_id=instance_id,
            reason="user_revoked",
        )

        # 2) Detach any Apple mirrored-source entries from primary nodes
        #    owned by other providers — never delete the node itself.
        detached_nodes = await self.cross_provider.detach_mirrored_sources_by_instance(
            user_id=user_id, connector_instance_id=instance_id,
        )

        # 3) Detach ingestion events created by this instance so
        #    downstream consumers can see they're no longer live.
        await self.db.ingestion_events.update_many(
            {"user_id": user_id, "connector_instance_id": instance_id},
            {"$set": {"source_status": "detached", "updated_at": _now_iso()}},
        )

        # 4) DataRevocationPlan for auditability.
        await self.db.data_revocation_plans.insert_one({
            "id": f"drp_{instance_id}",
            "user_id": user_id,
            "connector_id": APPLE_CALENDAR_CONNECTOR_ID,
            "connector_instance_id": instance_id,
            "created_at": _now_iso(),
            "policy": "detach",
            "notes": (
                "Apple Calendar disconnected. Mirrored-source entries removed from "
                "life-graph nodes owned by other providers. Primary Apple nodes are "
                "kept as detached data (user-verified facts preserved)."
            ),
        })

        # 5) Mark the instance revoked.
        updated = await self.instances.mark_status(user_id, instance_id, "revoked")

        await self.permissions.audit.log(
            user_id=user_id, event_type="connector.revoke",
            connector_id=APPLE_CALENDAR_CONNECTOR_ID,
            connector_instance_id=instance_id,
            capability_id=APPLE_CALENDAR_CAPABILITY_ID,
            success=True,
            reason_code="user_revoked",
            details={"detached_mirrored_nodes": detached_nodes},
        )
        return {
            "ok": True,
            "instance": updated,
            "detached_mirrored_nodes": detached_nodes,
        }
