"""
PermissionsContextProvider — feature-flagged, behind PERMISSIONS_CONTEXT_ENABLED.

When the flag is OFF (default), the provider is a NO-OP: it returns an
empty ProviderResult and adds ZERO signals. Snapshot hashes therefore
stay byte-stable across the flag boundary as long as no consents exist.

When enabled, it emits ONLY METADATA signals about the user's currently
active consents (capability_id, connector_id, connector_instance_id,
sensitivity). No sensitive payload leaks into the snapshot.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from .types import ProviderResult, Signal


def _flag_enabled() -> bool:
    return os.environ.get("PERMISSIONS_CONTEXT_ENABLED", "false").lower() in ("1", "true", "yes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def permissions_provider(user_id: str) -> ProviderResult:
    t0 = time.perf_counter()
    if not _flag_enabled():
        return ProviderResult(name="permissions", duration_ms=(time.perf_counter() - t0) * 1000)

    # Lazy import to avoid circular deps and to keep the provider fully
    # opt-in: importing this module has zero side-effects.
    try:
        from deps import get_permissions_service  # type: ignore
    except Exception:
        return ProviderResult(name="permissions", error="deps_unavailable", duration_ms=(time.perf_counter() - t0) * 1000)

    perms = get_permissions_service()
    active = await perms.consents.list_for_user(user_id, status="active")

    signals: List[Signal] = []
    for c in active:
        cap_id = c.get("capability_id")
        cap_meta: Dict[str, Any] = {}
        try:
            from permissions import capability_by_id
            cap = capability_by_id(cap_id) or {}
            cap_meta = {
                "sensitivity": cap.get("sensitivity"),
                "data_categories": list(cap.get("data_categories") or []),
                "connector_domain": cap.get("connector_domain"),
            }
        except Exception:
            pass

        signals.append(Signal(
            key="active_consent",
            value={
                "capability_id": cap_id,
                "connector_id": c.get("connector_id"),
                "connector_instance_id": c.get("connector_instance_id"),
                "purpose_id": c.get("purpose_id"),
                **cap_meta,
            },
            value_type="object",
            source_module="permissions",
            source_id=c.get("id"),
            confidence=1.0,
            verified=True,
            sensitivity="personal",
            observed_at=c.get("granted_at") or _now(),
            reliability_tier="user_verified",
        ))

    signals.append(Signal(
        key="permissions_enabled",
        value=True,
        value_type="boolean",
        source_module="permissions",
        confidence=1.0,
        verified=True,
        sensitivity="public",
        observed_at=_now(),
        reliability_tier="official",
    ))

    return ProviderResult(name="permissions", signals=signals, duration_ms=(time.perf_counter() - t0) * 1000)
