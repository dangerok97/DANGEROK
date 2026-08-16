"""Mongo persistence for location signals + presence + preference."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from location.models import (
    SIGNAL_TTL_SECONDS,
    LocationPreference,
    LocationSignal,
    PresenceContext,
)


class LocationRepository:
    SIGNALS = "location_signals"
    PRESENCE = "user_presence"
    # Preference stored on users collection under settings.location_mode

    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        col = self.db[self.SIGNALS]
        await col.create_index([("user_id", 1), ("timestamp", -1)], name="user_ts")
        await col.create_index([("user_id", 1), ("id", 1)], unique=True, name="user_sig_id")
        # Real Mongo TTL — first in repo for raw sensor evidence
        await col.create_index(
            "expires_at",
            expireAfterSeconds=0,
            name="ttl_expires_at",
        )
        await self.db[self.PRESENCE].create_index("user_id", unique=True, name="presence_user")

    async def insert_signal(self, signal: LocationSignal) -> None:
        doc = signal.model_dump()
        if signal.expires_at is None:
            doc["expires_at"] = datetime.now(timezone.utc) + timedelta(
                seconds=SIGNAL_TTL_SECONDS
            )
        await self.db[self.SIGNALS].insert_one(doc)

    async def latest_signal(self, user_id: str) -> Optional[LocationSignal]:
        doc = await self.db[self.SIGNALS].find_one(
            {"user_id": user_id},
            {"_id": 0},
            sort=[("timestamp", -1)],
        )
        if not doc:
            return None
        try:
            return LocationSignal.model_validate(doc)
        except Exception:
            return None

    async def update_signal_place(self, signal: LocationSignal) -> None:
        """Update semantic place fields only (coords/timestamp unchanged)."""
        await self.db[self.SIGNALS].update_one(
            {"user_id": signal.user_id, "id": signal.id},
            {
                "$set": {
                    "place_label": signal.place_label,
                    "place_locality": signal.place_locality,
                    "place_municipality": signal.place_municipality,
                    "place_region": signal.place_region,
                    "place_country": signal.place_country,
                    "place_label_precision": signal.place_label_precision,
                    "place_resolver_version": signal.place_resolver_version,
                }
            },
            upsert=False,
        )

    async def upsert_presence(self, presence: PresenceContext) -> None:
        doc = presence.model_dump()
        await self.db[self.PRESENCE].update_one(
            {"user_id": presence.user_id},
            {"$set": doc},
            upsert=True,
        )

    async def get_presence(self, user_id: str) -> Optional[PresenceContext]:
        doc = await self.db[self.PRESENCE].find_one({"user_id": user_id}, {"_id": 0})
        if not doc:
            return None
        try:
            return PresenceContext.model_validate(doc)
        except Exception:
            return None

    async def get_preference(self, user_id: str) -> LocationPreference:
        user = await self.db.users.find_one(
            {"user_id": user_id}, {"_id": 0, "settings": 1}
        )
        settings = (user or {}).get("settings") or {}
        mode = str(settings.get("location_mode") or "off").strip().lower()
        if mode == "while_using":
            return "while_using"
        return "off"

    async def set_preference(self, user_id: str, mode: LocationPreference) -> None:
        safe: LocationPreference = "while_using" if mode == "while_using" else "off"
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"settings.location_mode": safe}},
            upsert=True,
        )
