from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from mongomock_motor import AsyncMongoMockClient

from security.rate_limit import (
    COLLECTION,
    RateLimitExceeded,
    consume,
    enforce_auth_limit,
    ensure_indexes,
)


@pytest.mark.asyncio
async def test_fixed_window_blocks_atomically_without_storing_subject():
    db = AsyncMongoMockClient().auth_rate_limit
    await ensure_indexes(db)
    now = datetime(2026, 10, 4, 12, 0, 15, tzinfo=timezone.utc)

    assert await consume(
        db, scope="login", subject="person@example.com",
        limit=2, window_seconds=60, now=now,
    ) == 1
    assert await consume(
        db, scope="login", subject="person@example.com",
        limit=2, window_seconds=60, now=now,
    ) == 0
    with pytest.raises(RateLimitExceeded) as caught:
        await consume(
            db, scope="login", subject="person@example.com",
            limit=2, window_seconds=60, now=now,
        )
    assert caught.value.retry_after == 45

    stored = await db[COLLECTION].find_one({}, {"_id": 0})
    assert stored["count"] == 2
    assert "person@example.com" not in str(stored)


@pytest.mark.asyncio
async def test_new_window_and_different_subject_have_independent_allowance():
    db = AsyncMongoMockClient().auth_rate_limit_windows
    now = datetime(2026, 10, 4, 12, 0, 59, tzinfo=timezone.utc)

    await consume(db, scope="login", subject="a", limit=1, window_seconds=60, now=now)
    assert await consume(
        db, scope="login", subject="b", limit=1, window_seconds=60, now=now,
    ) == 0
    assert await consume(
        db, scope="login", subject="a", limit=1, window_seconds=60,
        now=now + timedelta(seconds=2),
    ) == 0


@pytest.mark.asyncio
async def test_auth_limit_applies_network_and_identifier_buckets():
    db = AsyncMongoMockClient().auth_rate_limit_auth
    request = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.5"),
        headers={"x-forwarded-for": "203.0.113.10"},
    )

    await enforce_auth_limit(
        db, request, scope="login", identifier="USER@Example.com",
        network_limit=10, identifier_limit=1, window_seconds=60,
    )
    with pytest.raises(RateLimitExceeded):
        await enforce_auth_limit(
            db, request, scope="login", identifier="user@example.com",
            network_limit=10, identifier_limit=1, window_seconds=60,
        )

    docs = await db[COLLECTION].find({}, {"_id": 0}).to_list(10)
    assert docs
    serialized = str(docs)
    assert "USER@Example.com" not in serialized
    assert "user@example.com" not in serialized
    assert "203.0.113.10" not in serialized
