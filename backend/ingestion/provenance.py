"""Provenance helper — builds provenance stamps for normalized fields."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_provenance(
    *,
    connector_id: str,
    connector_instance_id: str,
    source_type: str,
    source_id: str,
    field_path: str,
    source_updated_at: Optional[str] = None,
    confidence: float = 1.0,
    reliability_tier: str = "official",
    verified: bool = True,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    p = {
        "connector_id": connector_id,
        "connector_instance_id": connector_instance_id,
        "source_type": source_type,
        "source_id": source_id,
        "field_path": field_path,
        "source_updated_at": source_updated_at,
        "observed_at": _now_iso(),
        "confidence": float(confidence),
        "reliability_tier": reliability_tier,
        "verified": bool(verified),
    }
    if extra:
        p.update(extra)
    return p
