"""Non-destructive identity indexes + password identity backfill."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from .store import IdentityStore

log = logging.getLogger("ora.social_auth")


async def ensure_identity_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.user_identities.create_index(
        [("provider", 1), ("provider_subject", 1)],
        unique=True,
        name="uniq_provider_subject",
    )
    await db.user_identities.create_index([("user_id", 1)], name="idx_user_id")
    await db.user_identities.create_index(
        [("provider", 1), ("email", 1)],
        name="idx_provider_email",
        sparse=True,
    )


async def migrate_password_identities(db: AsyncIOMotorDatabase) -> dict[str, Any]:
    """Create password identities for existing users with password_hash.

    Does not delete or rewrite users. Safe to re-run.
    """
    store = IdentityStore(db)
    created = 0
    skipped = 0
    cursor = db.users.find(
        {"password_hash": {"$exists": True, "$ne": None}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    )
    async for user in cursor:
        uid = user.get("user_id")
        if not uid:
            continue
        existing = await store.find_password_for_user(uid)
        if existing:
            skipped += 1
            continue
        await store.create(
            provider="password",
            provider_subject=uid,
            user_id=uid,
            email=user.get("email"),
            email_verified=True,
            display_name=user.get("name"),
            avatar_url=None,
        )
        created += 1
    if created:
        log.info("password identity migration: created=%s skipped=%s", created, skipped)
    return {"created": created, "skipped": skipped, "at": datetime.now(timezone.utc).isoformat()}
