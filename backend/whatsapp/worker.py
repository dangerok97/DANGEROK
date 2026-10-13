"""Independent bounded inbox and opt-in alert workers with Mongo leases."""
from __future__ import annotations

import asyncio
import logging

from whatsapp.cloud import CloudConfig
from whatsapp.service import WhatsAppService
from whatsapp.alerts import AlertWorker

log = logging.getLogger("ora.whatsapp.worker")
_task: asyncio.Task | None = None
_alert_task: asyncio.Task | None = None


async def _loop(db) -> None:
    """Interactive replies must not wait behind a slow Meta alert call."""
    service = WhatsAppService(db)
    while True:
        try:
            if not await service.process_one():
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("WhatsApp inbox iteration failed: category=%s", type(exc).__name__)
            await asyncio.sleep(5)


async def _alert_loop(db) -> None:
    """Sender and source fences are enforced inside AlertWorker.process_one."""
    alerts = AlertWorker(db)
    while True:
        try:
            if not await alerts.process_one():
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("WhatsApp alert iteration failed: category=%s", type(exc).__name__)
            await asyncio.sleep(5)


def start_worker(db) -> bool:
    global _task, _alert_task
    if not CloudConfig.available():
        return False
    if _task and not _task.done():
        return False
    _task = asyncio.create_task(_loop(db), name="ora-whatsapp-inbox")
    _alert_task = asyncio.create_task(_alert_loop(db), name="ora-whatsapp-alerts")
    return True


async def stop_worker() -> None:
    global _task, _alert_task
    for task in (_task, _alert_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _task = None
    _alert_task = None
