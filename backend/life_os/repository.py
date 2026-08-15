"""Mongo persistence for Life OS plans, generative objects & legacy artifacts."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_os.generative_models import GenerativeObject
from life_os.models import LifeOsArtifact, LifeOsPlan, now_iso


class LifeOsRepository:
    PLANS = "life_os_plans"
    ARTIFACTS = "life_os_artifacts"  # V2.3 legacy — read-only compat
    OBJECTS = "life_os_objects"

    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db[self.PLANS].create_index("id", unique=True)
        await self.db[self.PLANS].create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
        await self.db[self.PLANS].create_index([("user_id", 1), ("goal_id", 1)])
        await self.db[self.ARTIFACTS].create_index("id", unique=True)
        await self.db[self.ARTIFACTS].create_index(
            [("user_id", 1), ("plan_id", 1), ("type", 1)]
        )
        await self.db[self.OBJECTS].create_index("id", unique=True)
        await self.db[self.OBJECTS].create_index(
            [("user_id", 1), ("plan_id", 1), ("updated_at", -1)]
        )
        await self.db[self.OBJECTS].create_index([("user_id", 1), ("goal_id", 1)])

    async def insert_plan(self, plan: LifeOsPlan) -> None:
        await self.db[self.PLANS].insert_one(plan.model_dump())

    async def save_plan(self, plan: LifeOsPlan) -> None:
        plan.touch()
        await self.db[self.PLANS].update_one(
            {"user_id": plan.user_id, "id": plan.id},
            {"$set": plan.model_dump()},
            upsert=True,
        )

    async def get_plan(self, user_id: str, plan_id: str) -> Optional[LifeOsPlan]:
        doc = await self.db[self.PLANS].find_one(
            {"user_id": user_id, "id": plan_id}, {"_id": 0}
        )
        return LifeOsPlan.model_validate(doc) if doc else None

    async def get_plan_by_session(
        self, user_id: str, conversation_session_id: str
    ) -> Optional[LifeOsPlan]:
        if not conversation_session_id:
            return None
        cur = (
            self.db[self.PLANS]
            .find(
                {
                    "user_id": user_id,
                    "conversation_session_id": conversation_session_id,
                    "status": {"$in": ["active", "paused"]},
                },
                {"_id": 0},
            )
            .sort("updated_at", -1)
            .limit(1)
        )
        docs = await cur.to_list(1)
        return LifeOsPlan.model_validate(docs[0]) if docs else None

    async def list_active_plans(self, user_id: str, *, limit: int = 20) -> List[LifeOsPlan]:
        cur = (
            self.db[self.PLANS]
            .find(
                {"user_id": user_id, "status": {"$in": ["active", "paused"]}},
                {"_id": 0},
            )
            .sort("updated_at", -1)
            .limit(limit)
        )
        docs = await cur.to_list(limit)
        return [LifeOsPlan.model_validate(d) for d in docs]

    async def insert_artifact(self, art: LifeOsArtifact) -> None:
        await self.db[self.ARTIFACTS].insert_one(art.model_dump())

    async def save_artifact(self, art: LifeOsArtifact) -> None:
        art.updated_at = now_iso()
        await self.db[self.ARTIFACTS].update_one(
            {"user_id": art.user_id, "id": art.id},
            {"$set": art.model_dump()},
            upsert=True,
        )

    async def get_artifact(self, user_id: str, artifact_id: str) -> Optional[LifeOsArtifact]:
        doc = await self.db[self.ARTIFACTS].find_one(
            {"user_id": user_id, "id": artifact_id}, {"_id": 0}
        )
        return LifeOsArtifact.model_validate(doc) if doc else None

    async def list_artifacts_for_plan(
        self, user_id: str, plan_id: str, *, limit: int = 40
    ) -> List[LifeOsArtifact]:
        cur = (
            self.db[self.ARTIFACTS]
            .find({"user_id": user_id, "plan_id": plan_id}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cur.to_list(limit)
        return [LifeOsArtifact.model_validate(d) for d in docs]

    async def insert_object(self, obj: GenerativeObject) -> None:
        await self.db[self.OBJECTS].insert_one(obj.model_dump())

    async def save_object(self, obj: GenerativeObject) -> None:
        obj.touch()
        await self.db[self.OBJECTS].update_one(
            {"user_id": obj.user_id, "id": obj.id},
            {"$set": obj.model_dump()},
            upsert=True,
        )

    async def get_object(self, user_id: str, object_id: str) -> Optional[GenerativeObject]:
        doc = await self.db[self.OBJECTS].find_one(
            {"user_id": user_id, "id": object_id}, {"_id": 0}
        )
        return GenerativeObject.model_validate(doc) if doc else None

    async def list_objects_for_plan(
        self, user_id: str, plan_id: str, *, limit: int = 40
    ) -> List[GenerativeObject]:
        cur = (
            self.db[self.OBJECTS]
            .find({"user_id": user_id, "plan_id": plan_id}, {"_id": 0})
            .sort("updated_at", -1)
            .limit(limit)
        )
        docs = await cur.to_list(limit)
        return [GenerativeObject.model_validate(d) for d in docs]

    async def list_objects_for_goal(
        self, user_id: str, goal_id: str, *, limit: int = 40
    ) -> List[GenerativeObject]:
        cur = (
            self.db[self.OBJECTS]
            .find({"user_id": user_id, "goal_id": goal_id}, {"_id": 0})
            .sort("updated_at", -1)
            .limit(limit)
        )
        docs = await cur.to_list(limit)
        return [GenerativeObject.model_validate(d) for d in docs]
