from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError

import ops.backup_scheduler as scheduler


class Runs:
    def __init__(self):
        self.rows = {}
    async def create_index(self, *_args, **_kwargs):
        return None
    async def insert_one(self, row):
        key = row["_id"]
        if key in self.rows:
            raise DuplicateKeyError("duplicate")
        self.rows[key] = dict(row)
        return SimpleNamespace(inserted_id=key)
    async def find_one(self, query, _projection=None):
        row = self.rows.get(query["_id"])
        return dict(row) if row else None
    async def update_one(self, query, update):
        row = self.rows.get(query["_id"])
        if row is None:
            return SimpleNamespace(modified_count=0)
        expected = query.get("status")
        if expected is not None and row.get("status") != expected:
            return SimpleNamespace(modified_count=0)
        row.update(update.get("$set", {}))
        return SimpleNamespace(modified_count=1)


class Db:
    def __init__(self):
        self.backup_runs = Runs()


@pytest.mark.asyncio
async def test_daily_backup_runs_once_and_records_success(monkeypatch, tmp_path):
    db = Db()
    monkeypatch.setenv("BACKUP_ENABLED", "1")
    monkeypatch.setenv("BACKUP_HOUR_UTC", "2")
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path / "docs"))

    uploaded = []
    async def fake_create(_db, _docs, path):
        path.write_bytes(b"archive")
        return {"database": [{"collection": "users", "count": 1}], "document_files": 2}
    def fake_upload(path, key):
        uploaded.append((path.exists(), key))

    monkeypatch.setattr(scheduler, "create_archive", fake_create)
    monkeypatch.setattr(scheduler, "upload_archive", fake_upload)
    now = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)

    first = await scheduler.run_backup_if_due(db, now=now)
    second = await scheduler.run_backup_if_due(db, now=now)

    assert first["ran"] is True
    assert second == {"ran": False, "reason": "already_claimed", "day": "2026-10-04"}
    assert uploaded == [(True, "ora/daily/2026-10-04/ora-backup-2026-10-04.tar.gz")]
    assert db.backup_runs.rows["2026-10-04"]["status"] == "success"


@pytest.mark.asyncio
async def test_backup_waits_until_configured_hour(monkeypatch):
    db = Db()
    monkeypatch.setenv("BACKUP_ENABLED", "1")
    monkeypatch.setenv("BACKUP_HOUR_UTC", "5")
    out = await scheduler.run_backup_if_due(
        db, now=datetime(2026, 10, 4, 4, 59, tzinfo=timezone.utc)
    )
    assert out == {"ran": False, "reason": "not_due"}
    assert db.backup_runs.rows == {}


@pytest.mark.asyncio
async def test_failed_backup_can_retry_same_day(monkeypatch, tmp_path):
    db = Db()
    monkeypatch.setenv("BACKUP_ENABLED", "1")
    monkeypatch.setenv("BACKUP_HOUR_UTC", "0")
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path / "docs"))

    async def fake_create(_db, _docs, path):
        path.write_bytes(b"archive")
        return {"database": [], "document_files": 0}

    attempts = {"n": 0}
    def flaky_upload(_path, _key):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("temporary")

    monkeypatch.setattr(scheduler, "create_archive", fake_create)
    monkeypatch.setattr(scheduler, "upload_archive", flaky_upload)
    now = datetime(2026, 10, 4, 8, 0, tzinfo=timezone.utc)

    first = await scheduler.run_backup_if_due(db, now=now)
    second = await scheduler.run_backup_if_due(db, now=now)

    assert first["reason"] == "failed"
    assert second["ran"] is True
    assert attempts["n"] == 2
    assert db.backup_runs.rows["2026-10-04"]["status"] == "success"
