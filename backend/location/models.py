"""LocationSignal + PresenceContext — domain-neutral sensor semantics."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

PresenceFreshness = Literal["CURRENT", "RECENT", "STALE", "UNKNOWN"]
LocationSource = Literal[
    "foreground_device",
    "background_device",
    "user_stated",
    "derived",
]
PermissionState = Literal[
    "not_requested",
    "granted_foreground",
    "denied",
    "unavailable",
]
# User preference for device location (settings). Background not offered in V2.7.1.
LocationPreference = Literal["off", "while_using"]

# Freshness windows (generic, not place-specific)
CURRENT_MAX_AGE_SEC = 5 * 60  # 5 minutes
RECENT_MAX_AGE_SEC = 30 * 60  # 30 minutes

# Raw signal TTL — minimal retention for sensor evidence (not Memory).
# Shorter than permissions registry's illustrative 7-day intent for coarse consent metadata.
SIGNAL_TTL_SECONDS = 2 * 60 * 60  # 2 hours


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_signal_id() -> str:
    return f"lcs_{secrets.token_hex(8)}"


class LocationSignal(BaseModel):
    """Short-lived sensor evidence. Never written to Life Memory."""

    id: str = Field(default_factory=new_signal_id)
    user_id: str
    timestamp: str = Field(default_factory=now_iso)
    latitude: float
    longitude: float
    accuracy_meters: Optional[float] = None
    source: LocationSource = "foreground_device"
    permission_state: PermissionState = "granted_foreground"
    freshness: PresenceFreshness = "CURRENT"
    session_id: Optional[str] = None
    goal_ref: Optional[str] = None
    # Mongo TTL field (datetime)
    expires_at: Optional[datetime] = None
    # Coarse human label from reverse-geocode (optional; never invented)
    # Compat: display_label; structured parts optional
    place_label: Optional[str] = None
    place_locality: Optional[str] = None
    place_municipality: Optional[str] = None
    place_region: Optional[str] = None
    place_country: Optional[str] = None
    place_label_precision: Optional[str] = None
    # Which place_label resolver produced the semantic fields (semantic cache version)
    place_resolver_version: Optional[str] = None
    # Redacted for traces — never log full coords in DEV
    created_at: str = Field(default_factory=now_iso)

    def public_coords(self, *, include_precise: bool = False) -> Dict[str, Any]:
        if include_precise:
            return {
                "latitude": round(self.latitude, 5),
                "longitude": round(self.longitude, 5),
                "accuracy_meters": self.accuracy_meters,
            }
        # Coarse for AI payload when label exists — still allow coords for routing tools
        return {
            "latitude": round(self.latitude, 4),
            "longitude": round(self.longitude, 4),
            "accuracy_meters": self.accuracy_meters,
        }


class PresenceContext(BaseModel):
    """What cognition consumes instead of raw GPS history."""

    user_id: str
    freshness: PresenceFreshness = "UNKNOWN"
    last_seen_at: Optional[str] = None
    accuracy_meters: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    place_label: Optional[str] = None
    place_locality: Optional[str] = None
    place_municipality: Optional[str] = None
    place_region: Optional[str] = None
    place_country: Optional[str] = None
    place_label_precision: Optional[str] = None
    place_resolver_version: Optional[str] = None
    source: Optional[str] = None
    permission_state: Optional[PermissionState] = None
    source_refs: List[str] = Field(default_factory=list)
    preference: LocationPreference = "off"
    # Last acquisition failure (timeout / position_unavailable / …) — not Memory
    acquisition_error: Optional[str] = None
    updated_at: str = Field(default_factory=now_iso)

    def for_ai(self) -> Dict[str, Any]:
        """Minimized presence for Context Broker / capability payload."""
        out: Dict[str, Any] = {
            "freshness": self.freshness,
            "last_seen_at": self.last_seen_at,
            "source": self.source,
            "permission_state": self.permission_state,
            "preference": self.preference,
        }
        if self.acquisition_error:
            out["acquisition_error"] = self.acquisition_error
        place: Dict[str, Any] = {}
        if self.place_label:
            place["display_label"] = self.place_label
            out["place_label"] = self.place_label  # compat
        if self.place_locality:
            place["locality"] = self.place_locality
        if self.place_municipality:
            place["municipality"] = self.place_municipality
        if self.place_region:
            place["region"] = self.place_region
        if self.place_country:
            place["country"] = self.place_country
        if self.place_label_precision:
            place["label_precision"] = self.place_label_precision
        if self.place_resolver_version:
            place["resolver_version"] = self.place_resolver_version
        if place:
            out["place"] = place
        if self.freshness in ("CURRENT", "RECENT") and self.latitude is not None:
            out["coordinates"] = {
                "latitude": round(float(self.latitude), 4),
                "longitude": round(float(self.longitude or 0), 4),
            }
            out["accuracy_meters"] = self.accuracy_meters
        elif self.freshness == "STALE":
            out["note"] = "Last device location is stale — do not present as current."
        elif self.freshness == "UNKNOWN":
            out["note"] = "No usable device location."
        return out

    def for_broker(self) -> Dict[str, Any]:
        """Even smaller slice for broker (no precise trail / no street)."""
        d: Dict[str, Any] = {
            "freshness": self.freshness,
            "last_seen_at": self.last_seen_at,
            "source": self.source,
        }
        if self.place_label:
            d["label"] = self.place_label
        if self.place_locality:
            d["locality"] = self.place_locality
        if self.place_municipality:
            d["municipality"] = self.place_municipality
        if self.place_region:
            d["region"] = self.place_region
        if self.place_country:
            d["country"] = self.place_country
        if (
            not self.place_label
            and self.freshness in ("CURRENT", "RECENT")
            and self.latitude is not None
        ):
            d["coordinates"] = {
                "latitude": round(float(self.latitude), 4),
                "longitude": round(float(self.longitude or 0), 4),
            }
        return d
