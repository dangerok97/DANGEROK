"""Complete the first provider read before returning from OAuth.

Failures retain the authorized connection and schedule a durable retry.
No interpretation, messages or external writes are performed here.
"""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def after_connect(db, *, user_id, instance_id, sync):
    from connected.sources import ATTEMPTS

    # Enqueue first: cancellation/restart must not lose the new source, even
    # if this owner already has other sources in the polling schedule.
    await db[ATTEMPTS].update_one(
        {"owner_id": user_id, "source_id": instance_id},
        {"$set": {"next_attempt_at": datetime.now(timezone.utc).isoformat(),
                  "failures": 0}}, upsert=True,
    )
    try:
        result = await asyncio.wait_for(
            sync(user_id=user_id, instance_id=instance_id), timeout=30,
        )
        if (result.get("totals") or {}).get("failed"):
            return {"ok": False, "retry_pending": True}
        # Keep the scheduled pass due: it also materializes connected signals
        # from the now-ingested records without delaying the OAuth response.
        return {"ok": True, "retry_pending": False}
    except Exception as exc:
        logger.warning("Initial connector sync deferred: %s", type(exc).__name__)
        return {"ok": False, "retry_pending": True}
