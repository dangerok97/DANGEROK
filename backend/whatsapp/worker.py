"""Single bounded async inbox worker per API process, with Mongo claim leases."""
from __future__ import annotations

import asyncio
import logging

from whatsapp.cloud import CloudConfig
from whatsapp.service import WhatsAppService
from whatsapp.alerts import AlertWorker

log = logging.getLogger("ora.whatsapp.worker")
_task: asyncio.Task | None = None


async def _loop(db) -> None:
    service = WhatsAppService(db)
    alerts = AlertWorker(db)
    while True:
        try:
            inbound = await service.process_one()
            outgoing = await alerts.process_one()
            if not (inbound or outgoing):
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("WhatsApp worker iteration failed: category=%s", type(exc).__name__)
            await asyncio.sleep(5)


def start_worker(db) -> bool:
    global _task
    if not CloudConfig.available():
        return False
    if _task and not _task.done():
        return False
    _task = asyncio.create_task(_loop(db), name="ora-whatsapp-inbox")
    return True


async def stop_worker() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
