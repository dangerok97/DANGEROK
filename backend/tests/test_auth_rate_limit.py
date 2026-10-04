from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from security.rate_limit import _bucket_id, _client_ip, enforce_rate_limit


class FakeBuckets:
    def __init__(self):
        self.rows = {}

    async def find_one_and_update(self, query, update, *, upsert, return_document):
        key = query["_id"]
        row = self.rows.get(key)
        if row is None:
            row = {"_id": key, "count": 0, **update["$setOnInsert"]}
            self.rows[key] = row
        row["count"] += update["$inc"]["count"]
        return dict(row)


class FakeDb:
    def __init__(self):
        self.rate_limit_buckets = FakeBuckets()


def request(*, forwarded: str = "", host: str = "10.0.0.1"):
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_forwarded_ip_is_preferred_and_trimmed():
    assert _client_ip(request(forwarded="203.0.113.9, 10.0.0.1")) == "203.0.113.9"
    assert _client_ip(request(host="192.0.2.7")) == "192.0.2.7"


def test_bucket_changes_only_across_time_window():
    first, first_expiry = _bucket_id("auth.login", "203.0.113.9", window_seconds=60, now=120.0)
    same, same_expiry = _bucket_id("auth.login", "203.0.113.9", window_seconds=60, now=179.9)
    next_key, _ = _bucket_id("auth.login", "203.0.113.9", window_seconds=60, now=180.0)
    assert first == same
    assert first_expiry == same_expiry
    assert next_key != first


@pytest.mark.asyncio
async def test_limiter_allows_limit_then_returns_429():
    db = FakeDb()
    req = request(forwarded="198.51.100.5")
    await enforce_rate_limit(db, req, scope="auth.login", limit=2, window_seconds=300)
    await enforce_rate_limit(db, req, scope="auth.login", limit=2, window_seconds=300)
    with pytest.raises(HTTPException) as exc:
        await enforce_rate_limit(db, req, scope="auth.login", limit=2, window_seconds=300)
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "300"


@pytest.mark.asyncio
async def test_scopes_do_not_share_counters():
    db = FakeDb()
    req = request(host="192.0.2.44")
    await enforce_rate_limit(db, req, scope="auth.login", limit=1, window_seconds=300)
    await enforce_rate_limit(db, req, scope="auth.apple", limit=1, window_seconds=300)
