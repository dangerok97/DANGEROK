"""Mongo persistence for the `life_objects` collection."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from life_objects.models import LifeObject, now_iso

logger = logging.getLogger("ora.life_objects.repository")


class LifeObjectRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.life_objects

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index([("user_id", 1), ("type", 1), ("status", 1)])
        await self.col.create_index([("user_id", 1), ("updated_at", -1)])
        await self.col.create_index([("user_id", 1), ("documents", 1)], sparse=True)
        await self.col.create_index([("user_id", 1), ("goals", 1)], sparse=True)
        # Identity key indexes for dedup (sparse — not every object has every key)
        for key in (
            "identity_keys.address_norm",
            "identity_keys.cadastral",
            "identity_keys.pod",
            "identity_keys.pdr",
            "identity_keys.plate",
            "identity_keys.vin",
            "identity_keys.lender_property",
            "identity_keys.coords",
            "identity_keys.institution",
            "identity_keys.employer",
            "identity_keys.travel_dest_period",
        ):
            await self.col.create_index([("user_id", 1), (key, 1)], sparse=True, name=f"lo_{key.replace('.', '_')}")

    async def get(self, user_id: str, object_id: str) -> Optional[LifeObject]:
        doc = await self.col.find_one({"id": object_id, "user_id": user_id}, {"_id": 0})
        return LifeObject(**doc) if doc else None

    async def list_by_type(
        self,
        user_id: str,
        *,
        object_type: Optional[str] = None,
        status: Optional[str] = "active",
        limit: int = 80,
    ) -> List[LifeObject]:
        filt: Dict[str, Any] = {"user_id": user_id}
        if object_type:
            filt["type"] = object_type
        if status:
            filt["status"] = status
        docs = await self.col.find(filt, {"_id": 0}).sort("updated_at", -1).to_list(limit)
        return [LifeObject(**d) for d in docs]

    async def find_by_identity_key(
        self,
        user_id: str,
        *,
        object_type: str,
        key: str,
        value: str,
    ) -> Optional[LifeObject]:
        if not value:
            return None
        field = f"identity_keys.{key}"
        doc = await self.col.find_one(
            {
                "user_id": user_id,
                "type": object_type,
                "status": {"$in": ["active", "proposed", "uncertain"]},
                field: value,
            },
            {"_id": 0},
        )
        return LifeObject(**doc) if doc else None

    async def find_candidates(
        self,
        user_id: str,
        *,
        object_type: str,
        identity_keys: Dict[str, str],
        limit: int = 20,
    ) -> List[LifeObject]:
        """Find active objects of same type that share any strong identity key."""
        if not identity_keys:
            return []
        ors = []
        for k, v in identity_keys.items():
            if v:
                ors.append({f"identity_keys.{k}": v})
        if not ors:
            return []
        docs = await self.col.find(
            {
                "user_id": user_id,
                "type": object_type,
                "status": {"$in": ["active", "proposed", "uncertain"]},
                "$or": ors,
            },
            {"_id": 0},
        ).limit(limit).to_list(limit)
        return [LifeObject(**d) for d in docs]

    async def search(
        self,
        user_id: str,
        *,
        q: Optional[str] = None,
        object_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 40,
    ) -> List[LifeObject]:
        filt: Dict[str, Any] = {"user_id": user_id}
        if object_type:
            filt["type"] = object_type
        if status:
            filt["status"] = status
        if q and q.strip():
            rx = re.compile(re.escape(q.strip()), re.IGNORECASE)
            filt["$or"] = [
                {"title": rx},
                {"summary": rx},
                {"ai_summary": rx},
                {"identity_keys.address_norm": rx},
                {"identity_keys.plate": rx},
            ]
        docs = await self.col.find(filt, {"_id": 0}).sort("updated_at", -1).to_list(
            max(1, min(limit, 100))
        )
        return [LifeObject(**d) for d in docs]

    async def upsert(self, obj: LifeObject) -> LifeObject:
        obj.touch()
        await self.col.update_one(
            {"id": obj.id, "user_id": obj.user_id},
            {"$set": obj.model_dump()},
            upsert=True,
        )
        return obj

    async def delete(self, user_id: str, object_id: str, *, soft: bool = True) -> bool:
        if soft:
            res = await self.col.update_one(
                {"id": object_id, "user_id": user_id},
                {"$set": {"status": "archived", "updated_at": now_iso()}},
            )
            return res.matched_count > 0
        res = await self.col.delete_one({"id": object_id, "user_id": user_id})
        return res.deleted_count > 0
