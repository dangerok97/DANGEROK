"""Durable, privacy-preserving fixed-window rate limits for sensitive endpoints."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

COLLECTION = "rate_limits"


@dataclass
class RateLimitExceeded(RuntimeError):
    retry_after: int

    def __str__(self) -> str:
        return "rate_limit_exceeded"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_subject(request) -> str:
    """Return an opaque network fingerprint; raw addresses are never stored."""
    peer = ""
    if getattr(request, "client", None) is not None:
        peer = str(getattr(request.client, "host", "") or "")
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    # Railway supplies forwarding metadata; retaining the peer as part of the
    # digest prevents the database from ever storing either address verbatim.
    return _digest(f"{peer}|{forwarded or '-'}")


async def ensure_indexes(db) -> None:
    await db[COLLECTION].create_index("expires_at", expireAfterSeconds=0)


async def consume(
    db,
    *,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int,
    now: Optional[datetime] = None,
) -> int:
    """Consume one slot and return the remaining allowance.

    The bucket id contains only hashes. A saturated bucket deliberately turns
    the upsert into a duplicate-key collision, which is atomic across workers.
    """
    if limit < 1 or window_seconds < 1:
        raise ValueError("invalid_rate_limit")
    moment = now or _now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    epoch = int(moment.timestamp())
    bucket = epoch // window_seconds
    bucket_end_epoch = (bucket + 1) * window_seconds
    retry_after = max(1, bucket_end_epoch - epoch)
    key = _digest(f"{scope}|{_digest(subject)}|{bucket}")
    expires_at = datetime.fromtimestamp(
        bucket_end_epoch + window_seconds, timezone.utc
    )
    try:
        row = await db[COLLECTION].find_one_and_update(
            {"_id": key, "count": {"$lt": limit}},
            {
                "$inc": {"count": 1},
                "$setOnInsert": {
                    "scope": scope[:80],
                    "expires_at": expires_at,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as exc:
        raise RateLimitExceeded(retry_after) from exc
    count = int((row or {}).get("count") or 1)
    return max(0, limit - count)


async def enforce_auth_limit(
    db,
    request,
    *,
    scope: str,
    identifier: str = "",
    network_limit: int,
    identifier_limit: int | None = None,
    window_seconds: int = 60,
) -> None:
    await consume(
        db,
        scope=f"{scope}:network",
        subject=request_subject(request),
        limit=network_limit,
        window_seconds=window_seconds,
    )
    if identifier and identifier_limit:
        await consume(
            db,
            scope=f"{scope}:identifier",
            subject=identifier.strip().casefold(),
            limit=identifier_limit,
            window_seconds=window_seconds,
        )
