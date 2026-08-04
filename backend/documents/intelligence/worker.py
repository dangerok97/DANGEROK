"""In-process async job queue for document intelligence (no cloud)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger("ora.documents.worker")

_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_started = False


def _get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def enqueue_document_job(user_id: str, doc_id: str, *, reason: str = "upload") -> None:
    await _get_queue().put({"user_id": user_id, "doc_id": doc_id, "reason": reason})


async def _worker_loop() -> None:
    from documents.intelligence.service import IntelligenceService
    from deps import db, get_document_service

    q = _get_queue()
    svc = IntelligenceService(db, get_document_service())
    logger.info("document intelligence worker started")
    while True:
        job = await q.get()
        try:
            await svc.run_pipeline(user_id=job["user_id"], doc_id=job["doc_id"])
        except Exception:
            logger.exception(
                "document intelligence job failed doc_id=%s",
                job.get("doc_id"),
            )
        finally:
            q.task_done()


def start_worker() -> None:
    """Start background worker once per process (FastAPI startup)."""
    global _worker_task, _started
    if _started:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _worker_task = loop.create_task(_worker_loop(), name="ora-doc-intel-worker")
    _started = True


def worker_stats() -> dict[str, Any]:
    q = _queue
    return {
        "started": _started,
        "queue_size": q.qsize() if q is not None else 0,
    }
