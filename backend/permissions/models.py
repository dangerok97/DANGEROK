"""Pydantic + typed models for the permissions module."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Wildcard applied when the user grants a capability across all instances
# of the connector (e.g. "all calendars", "all Gmail accounts").
INSTANCE_WILDCARD = "*"


class ConsentIn(BaseModel):
    capability_id: str
    connector_id: str
    connector_instance_id: str = INSTANCE_WILDCARD
    purpose_id: Optional[str] = None
    scopes: Optional[List[str]] = None
    notes: Optional[str] = None
    expires_at: Optional[str] = None
    # Optional bulk grant of many capabilities at once (server enforces
    # they all belong to the same connector).
    additional_capability_ids: Optional[List[str]] = None


class RevokeIn(BaseModel):
    reason: Optional[str] = None


class ConsentOut(BaseModel):
    id: str
    user_id: str
    capability_id: str
    connector_id: str
    connector_instance_id: str
    status: str  # active | revoked | expired
    purpose_id: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    granted_at: str
    revoked_at: Optional[str] = None
    expires_at: Optional[str] = None
    version: int = 1
    capability_registry_version: str = "1.0.0"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuditEventOut(BaseModel):
    event_id: str
    correlation_id: Optional[str] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    actor_type: str  # user | system | admin
    event_type: str
    capability_id: Optional[str] = None
    connector_id: Optional[str] = None
    connector_instance_id: Optional[str] = None
    purpose_id: Optional[str] = None
    decision_id: Optional[str] = None
    context_snapshot_id: Optional[str] = None
    success: bool
    reason_code: Optional[str] = None
    timestamp: str
    duration_ms: Optional[float] = None
    records_requested: Optional[int] = None
    records_returned: Optional[int] = None
    data_classification: Optional[str] = None
    retention_until: Optional[str] = None
