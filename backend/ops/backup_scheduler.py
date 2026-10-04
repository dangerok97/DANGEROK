"""Daily backup scheduler owned by the backend process.

The backend is the only service that can see both Mongo and /data/documents.
The run is idempotent per UTC day and catches up after a restart.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo.errors import DuplicateKeyError

from ops.backup_restore import create_archive, upload_archive

logger = logging.getLogger("ora.backup")

_task: asyncio.Task | None = None


def _enabled() -> bool:
    return (os.environ.get("BACKUP_ENABLED") or "").strip().lower() in {"1", "true", "yes"}


def _hour_utc() -> int:
    try:
        return min(23, max(0, int(os.environ.get("BACKUP_HOUR_UTC", "2"))))
    except ValueError:
        return 2


async def ensure_backup_indexes(db: Any) -> None:
    await db.backup_runs.create_index("created_at")
    await db.backup_runs.create_index("status")


async def _claim_day(db: Any, day: str, now: datetime) -> bool:
    try:
        await db.backup_runs.insert_one({
            "_id": day,
            "status": "running",
            "created_at": now,
            "updated_at": now,
        })
        return True
    except DuplicateKeyError:
        row = await db.backup_runs.find_one({"_id": day}, {"status": 1})
        if not row or row.get("status") != "failed":
            return False
        result = await db.backup_runs.update_one(
            {"_id": day, "status": "failed"},
            {"$set": {"status": "running", "updated_at": now}},
        )
        return bool(result.modified_count)


async def run_backup_if_due(db: Any, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if not _enabled():
        return {"ran": False, "reason": "disabled"}
    if now.hour < _hour_utc():
        return {"ran": False, "reason": "not_due"}

    day = now.astimezone(timezone.utc).date().isoformat()
    if not await _claim_day(db, day, now):
        return {"ran": False, "reason": "already_claimed", "day": day}

    documents = Path(os.environ.get("DOCUMENT_STORAGE_DIR", "/data/documents"))
    key = f"ora/daily/{day}/ora-backup-{day}.tar.gz"
    archive_path = None
    try:
        fd, raw_path = tempfile.mkstemp(prefix="ora-backup-", suffix=".tar.gz")
        os.close(fd)
        archive_path = Path(raw_path)
        manifest = await create_archive(db, documents, archive_path)
        upload_archive(archive_path, key)
        await db.backup_runs.update_one(
            {"_id": day},
            {"$set": {
                "status": "success",
                "updated_at": datetime.now(timezone.utc),
                "object_key": key,
                "manifest": manifest,
            }},
        )
        logger.info(
            "daily backup completed day=%s collections=%s documents=%s",
            day,
            len(manifest.get("database") or []),
            manifest.get("document_files", 0),
        )
        return {"ran": True, "day": day, "key": key, "manifest": manifest}
    except Exception as exc:
        await db.backup_runs.update_one(
            {"_id": day},
            {"$set": {
                "status": "failed",
                "updated_at": datetime.now(timezone.utc),
                "error_type": type(exc).__name__,
            }},
        )
        logger.exception("daily backup failed day=%s", day)
        return {"ran": False, "reason": "failed", "day": day, "error_type": type(exc).__name__}
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)


async def _loop(db: Any) -> None:
    while True:
        try:
            await run_backup_if_due(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("backup scheduler iteration failed")
        await asyncio.sleep(900)


def start_backup_scheduler(db: Any) -> bool:
    global _task
    if not _enabled() or (_task is not None and not _task.done()):
        return False
    _task = asyncio.create_task(_loop(db), name="ora-daily-backup")
    return True


async def stop_backup_scheduler() -> None:
    global _task
    task = _task
    _task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
