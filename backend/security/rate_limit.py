"""Small durable fixed-window limiter for public authentication surfaces."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:128]
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "") or "unknown")[:128]


def _bucket_id(scope: str, identity: str, *, window_seconds: int, now: float | None = None) -> tuple[str, datetime]:
    ts = float(time.time() if now is None else now)
    bucket = int(ts // window_seconds)
    raw = f"{scope}|{identity}|{window_seconds}|{bucket}".encode("utf-8")
    key = hashlib.sha256(raw).hexdigest()
    expires = datetime.fromtimestamp((bucket + 2) * window_seconds, tz=timezone.utc)
    return key, expires


async def ensure_rate_limit_indexes(db: Any) -> None:
    await db.rate_limit_buckets.create_index("expires_at", expireAfterSeconds=0)


async def enforce_rate_limit(
    db: Any,
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: int,
) -> None:
    identity = _client_ip(request)
    key, expires = _bucket_id(scope, identity, window_seconds=window_seconds)
    row = await db.rate_limit_buckets.find_one_and_update(
        {"_id": key},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {
                "scope": scope,
                "identity_hash": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                "expires_at": expires,
            },
        },
        upsert=True,
        return_document=True,
    )
    count = int((row or {}).get("count") or 1)
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail="Troppe richieste. Riprova tra poco.",
            headers={"Retry-After": str(window_seconds)},
        )
