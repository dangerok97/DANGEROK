"""In-process async job queue for document intelligence (single-instance local)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional, Set

logger = logging.getLogger("ora.documents.worker")

_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_recovery_task: Optional[asyncio.Task] = None
_started = False
_inflight: Set[str] = set()
_locks: dict[str, asyncio.Lock] = {}
MAX_ATTEMPTS = 3


def _get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


def _doc_lock(doc_id: str) -> asyncio.Lock:
    if doc_id not in _locks:
        _locks[doc_id] = asyncio.Lock()
    return _locks[doc_id]


async def enqueue_document_job(user_id: str, doc_id: str, *, reason: str = "upload") -> bool:
    """Enqueue if not already inflight. Returns False if skipped (dedupe)."""
    key = f"{user_id}:{doc_id}"
    if key in _inflight:
        return False
    await _get_queue().put({"user_id": user_id, "doc_id": doc_id, "reason": reason, "enqueued_at": time.time()})
    return True


async def _process_job(svc, job: dict[str, Any]) -> None:
    user_id = job["user_id"]
    doc_id = job["doc_id"]
    key = f"{user_id}:{doc_id}"
    lock = _doc_lock(doc_id)
    if lock.locked():
        logger.info("skip concurrent analysis doc_id=%s", doc_id)
        return
    async with lock:
        if key in _inflight:
            return
        _inflight.add(key)
        try:
            # Mark processing
            from documents.intelligence.pipeline import PipelineState
            doc = await svc.docs.get(user_id=user_id, doc_id=doc_id)
            attempts = int(doc.get("pipeline_attempts") or 0)
            if attempts > MAX_ATTEMPTS and doc.get("pipeline_status") == "failed":
                logger.info("max attempts reached doc_id=%s", doc_id)
                return
            upd = PipelineState.set_status(doc, "extracting")  # processing marker
            upd["pipeline_lock_at"] = time.time()
            await svc.db.documents.update_one(
                {"id": doc_id, "user_id": user_id},
                {"$set": upd},
            )
            await svc.run_pipeline(user_id=user_id, doc_id=doc_id)
        except Exception:
            logger.exception("document intelligence job failed doc_id=%s", doc_id)
            try:
                doc = await svc.docs.get(user_id=user_id, doc_id=doc_id)
                from documents.intelligence.pipeline import PipelineState
                await svc.db.documents.update_one(
                    {"id": doc_id, "user_id": user_id},
                    {"$set": PipelineState.set_status(doc, "failed", error="worker_exception")},
                )
            except Exception:
                pass
        finally:
            _inflight.discard(key)


async def _worker_loop() -> None:
    from documents.intelligence.service import IntelligenceService
    from deps import db, get_document_service

    q = _get_queue()
    svc = IntelligenceService(db, get_document_service())
    logger.info("document intelligence worker started")
    while True:
        job = await q.get()
        try:
            await _process_job(svc, job)
        finally:
            q.task_done()


async def recover_stale_jobs() -> int:
    """Re-queue docs stuck in queued/extracting/classifying/analyzing after restart."""
    from deps import db
    from documents.intelligence.pipeline import PipelineState

    stale = [
        "queued", "extracting", "classifying", "analyzing",
        "understanding", "generating_actions",
    ]
    cur = db.documents.find(
        {"deleted": {"$ne": True}, "pipeline_status": {"$in": stale}},
        {"_id": 0, "id": 1, "user_id": 1, "pipeline_attempts": 1, "pipeline_status": 1},
    ).limit(100)
    n = 0
    async for doc in cur:
        attempts = int(doc.get("pipeline_attempts") or 0)
        if attempts >= MAX_ATTEMPTS:
            await db.documents.update_one(
                {"id": doc["id"], "user_id": doc["user_id"]},
                {"$set": PipelineState.set_status(doc, "failed", error="max_attempts")},
            )
            continue
        ok = await enqueue_document_job(doc["user_id"], doc["id"], reason="recovery")
        if ok:
            n += 1
    if n:
        logger.info("recovered %s stale document jobs", n)
    return n


async def _recovery_loop() -> None:
    # Initial recovery after boot
    await asyncio.sleep(2)
    try:
        await recover_stale_jobs()
    except Exception:
        logger.exception("initial job recovery failed")
    while True:
        await asyncio.sleep(120)
        try:
            await recover_stale_jobs()
        except Exception:
            logger.exception("periodic job recovery failed")


def start_worker() -> None:
    """Start background worker once per process (FastAPI startup)."""
    global _worker_task, _recovery_task, _started
    if _started:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _worker_task = loop.create_task(_worker_loop(), name="ora-doc-intel-worker")
    _recovery_task = loop.create_task(_recovery_loop(), name="ora-doc-intel-recovery")
    _started = True


def worker_stats() -> dict[str, Any]:
    q = _queue
    return {
        "started": _started,
        "queue_size": q.qsize() if q is not None else 0,
        "inflight": len(_inflight),
        "max_attempts": MAX_ATTEMPTS,
        "mode": "in_process_single_instance",
    }
