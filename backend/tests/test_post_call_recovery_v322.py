"""V3.22 / V3.15.2 — governed post-call application recovery."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import telephone.application as app


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
    def __aiter__(self):
        async def gen():
            for row in self.rows:
                yield dict(row)
        return gen()


class _Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
    def find(self, query, projection=None):
        rows = [
            r for r in self.rows
            if r.get("application_status") == "failed"
            and r.get("retryable") is True
            and int(r.get("attempt_count") or 0) < app.MAX_ATTEMPTS
        ]
        return _Cursor(rows)
    async def update_one(self, query, change, **kwargs):
        for row in self.rows:
            if row.get("_id") == query.get("_id"):
                row.update(change.get("$set") or {})
                return


class _DB:
    def __init__(self, record):
        self.apps = _Collection([{**record.model_dump(), "_id": record.idempotency_key}])
    def __getitem__(self, name):
        if name == app.APPLICATIONS:
            return self.apps
        raise KeyError(name)


def _record(**updates):
    base = app.CallMissionApplication(
        mission_id="m1", call_id="c1", owner_id="u1",
        target_domain="calendar", target_entity_id="e1",
        operation="reschedule", outcome_status="success",
        application_status="failed", idempotency_key="m1|reschedule|e1",
        attempt_count=1, retryable=True,
        retry_after=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
        error="provider down",
    )
    return base.model_copy(update=updates)


@pytest.mark.asyncio
async def test_retry_failure_backs_off_then_stops_after_max():
    rec = _record(attempt_count=2)
    db = _DB(rec)
    verdict = SimpleNamespace(
        status="failed", writes=[], error="still down",
        retryable=True, error_kind="provider_unavailable",
    )
    out = await app._settle(
        db, rec, verdict, increment_attempt=True,
        now=datetime.now(timezone.utc),
    )
    assert out.attempt_count == app.MAX_ATTEMPTS
    assert out.retryable is False
    assert out.retry_after == ""
    assert out.error_kind == "provider_unavailable"


def test_retry_schedule_is_bounded_and_monotonic():
    now = "2026-09-25T00:00:00+00:00"
    a = datetime.fromisoformat(app._retry_at(1, now=now))
    b = datetime.fromisoformat(app._retry_at(2, now=now))
    c = datetime.fromisoformat(app._retry_at(3, now=now))
    origin = datetime.fromisoformat(now)
    assert (a-origin).total_seconds() == 60
    assert (b-origin).total_seconds() == 300
    assert (c-origin).total_seconds() == 900


def test_calendar_provider_failure_declares_retryable():
    import inspect
    import telephone.domains.calendar as calendar
    source = inspect.getsource(calendar._apply_reschedule)
    assert "retryable=True" in source
    assert 'error_kind="sync_unconfirmed"' in source


def test_retry_path_reconciles_before_any_new_write():
    import inspect
    source = inspect.getsource(app._retry_one)
    assert ".reconcile(" in source
    assert ".apply(" not in source
    assert "increment_attempt=True" in source


def test_recovery_loop_handles_failed_and_stale():
    import inspect
    import telephone.recovery as recovery
    source = inspect.getsource(recovery._one_pass)
    assert "recover_stale" in source
    assert "recover_failed" in source
    assert "application_metrics" in source
