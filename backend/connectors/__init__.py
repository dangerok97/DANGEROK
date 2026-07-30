"""ORA Connectors module — stub registry (no real 3rd-party calls)."""
from .registry import (
    CONNECTORS,
    CONNECTOR_REGISTRY_VERSION,
    connector_by_id,
    connectors_for_platform,
)
from .service import ConnectorService

__all__ = [
    "CONNECTORS",
    "CONNECTOR_REGISTRY_VERSION",
    "connector_by_id",
    "connectors_for_platform",
    "ConnectorService",
]
