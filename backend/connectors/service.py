"""ConnectorService — stub-only. Lists connectors, reports consent state
for the current user. In this iteration it performs ZERO external calls."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .registry import (
    CONNECTORS,
    CONNECTOR_REGISTRY_VERSION,
    as_dict,
    connector_by_id,
    connectors_for_platform,
)


class ConnectorService:
    def __init__(self, db, permissions):
        self.db = db
        self.permissions = permissions  # permissions.PermissionService

    def registry_version(self) -> str:
        return CONNECTOR_REGISTRY_VERSION

    def list_all(self, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        items = connectors_for_platform(platform) if platform else list(CONNECTORS)
        return [as_dict(c) for c in items]

    def get(self, connector_id: str) -> Optional[Dict[str, Any]]:
        c = connector_by_id(connector_id)
        return as_dict(c) if c else None

    async def status_for_user(self, user_id: str, connector_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Per-connector consent snapshot for a specific user.

        Response shape (per connector):
            {
              "connector": {...registry doc...},
              "consents": [ {capability_id, connector_instance_id, status, ...}, ... ],
              "summary": {
                  "total_required": int,
                  "granted": int,
                  "missing_capabilities": [cap_id, ...],
                  "instances": [connector_instance_id, ...],
              }
            }
        """
        conns = [connector_by_id(connector_id)] if connector_id else list(CONNECTORS)
        conns = [c for c in conns if c]

        out: List[Dict[str, Any]] = []
        for conn in conns:
            required = list(conn["required_capabilities"])
            consents = await self.permissions.consents.list_for_user(
                user_id, connector_id=conn["id"], status="active",
            )
            granted_ids = {c["capability_id"] for c in consents}
            missing = [cid for cid in required if cid not in granted_ids]
            instances = sorted({c["connector_instance_id"] for c in consents})
            out.append({
                "connector": as_dict(conn),
                "consents": consents,
                "summary": {
                    "total_required": len(required),
                    "granted": len(granted_ids & set(required)),
                    "missing_capabilities": missing,
                    "instances": instances,
                    "ready": len(missing) == 0 and conn["status"] in ("available",),
                    "status": conn["status"],
                },
            })
        return out
