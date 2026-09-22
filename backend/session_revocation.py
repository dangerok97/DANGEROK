"""Durable per-token revocation; never store bearer credentials."""
import hashlib
from datetime import datetime, timezone


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def revoke(db, token: str, expires_at: float):
    await db.revoked_sessions.update_one(
        {"_id": token_digest(token)},
        {"$set": {"expires_at": datetime.fromtimestamp(expires_at, timezone.utc)}},
        upsert=True,
    )


async def is_revoked(db, token: str) -> bool:
    return await db.revoked_sessions.find_one({"_id": token_digest(token)}, {"_id": 1}) is not None


async def ensure_indexes(db):
    await db.revoked_sessions.create_index("expires_at", expireAfterSeconds=0)
