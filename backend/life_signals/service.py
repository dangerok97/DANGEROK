"""Life Change Signal service — the generic primitive.

Two responsibilities and nothing else:

1. `emit()` — record that a persisted mutation happened. Never raises, never
   rolls back, never calls an LLM, never triggers another mutation.
2. the consumer contract (`list_pending` / `mark_processed` / `mark_failed`)
   that a future V2.9.2 reasoner will read from. V2.9.1 ships no consumer and
   no worker: nothing polls this store yet.

This module knows nothing about Situation/Memory/Graph/Calendar outcome
shapes — that translation lives in `life_signals.emitters`, so the primitive
here stays domain-neutral.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from life_signals.models import (
    ChangeKind,
    LifeChangeSignal,
    SourceSystem,
    is_valid_dedupe_key,
    sanitize_refs,
)
from life_signals.repository import DuplicateSignal, LifeSignalRepository

from context_graph.models import is_recognized_ref

logger = logging.getLogger("ora.life_signals")

MAX_PENDING_RETURNED = 20


class LifeSignalService:
    def __init__(self, db):
        self.db = db
        self.repo = LifeSignalRepository(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    async def emit(
        self,
        *,
        user_id: str,
        source_ref: str,
        source_system: SourceSystem,
        change_kind: ChangeKind,
        dedupe_key: str,
        affected_refs: Optional[List[str]] = None,
        revision: Optional[int] = None,
        authority: Optional[str] = None,
        source_status: Optional[str] = None,
        occurred_at: Optional[str] = None,
        session_id: Optional[str] = None,
        reasoning_epoch: Optional[str] = None,
    ) -> Optional[str]:
        """Record one persisted mutation. Returns the signal id, or None when
        nothing was written (invalid input, idempotent replay, or storage
        failure).

        FAILURE ISOLATION: this must be called only AFTER the primary mutation
        is committed, and it never re-raises. A signal-layer failure leaves the
        user's real life state correct and merely loses an event — it must
        never roll back or corrupt the mutation that already succeeded. The
        failure stays observable through the returned None and the warning log
        below, never silently swallowed.
        """
        try:
            if not user_id or not is_recognized_ref(source_ref):
                return None
            if not is_valid_dedupe_key(dedupe_key):
                logger.warning(
                    "life_change_signal rejected: unstable dedupe key for %s",
                    source_system,
                )
                return None

            signal = LifeChangeSignal(
                user_id=user_id,
                source_ref=source_ref.strip(),
                source_system=source_system,
                change_kind=change_kind,
                affected_refs=sanitize_refs(affected_refs, exclude=source_ref.strip()),
                revision=revision,
                authority=(str(authority)[:40] if authority else None),
                source_status=(str(source_status)[:32] if source_status else None),
                dedupe_key=dedupe_key.strip(),
                session_id=session_id,
                reasoning_epoch=reasoning_epoch,
            )
            if occurred_at:
                signal.occurred_at = str(occurred_at)[:40]

            await self.repo.insert(signal)
            logger.info(
                "life_change_signal source_system=%s change_kind=%s ref_class=%s",
                source_system,
                change_kind,
                _ref_class(source_ref),
            )
            return signal.id
        except DuplicateSignal:
            # Idempotent replay of the same mutation identity — expected, not
            # an error. Counted separately so a dedupe storm stays visible.
            logger.info(
                "life_change_signal dedupe_hit source_system=%s change_kind=%s",
                source_system,
                change_kind,
            )
            return None
        except Exception as e:
            logger.warning(
                "life_change_signal persistence failed source_system=%s error=%s",
                source_system,
                type(e).__name__,
            )
            return None

    # --- Future consumer contract (no worker ships in V2.9.1) -------------

    async def list_pending(
        self, user_id: str, *, limit: int = MAX_PENDING_RETURNED
    ) -> List[Dict[str, Any]]:
        """Bounded, user-scoped, deterministically ordered pending signals.

        Read-only and retry-safe: it does not lock or mutate anything, so a
        consumer that crashes mid-batch simply sees the same signals again.
        Claiming/locking is deliberately not implemented — there is no worker
        yet, and a distributed lock would be premature here.
        """
        capped = max(1, min(int(limit or MAX_PENDING_RETURNED), MAX_PENDING_RETURNED))
        items = await self.repo.list_by_status(user_id, status="pending", limit=capped)
        return [item.public() for item in items]

    async def count_pending(self, user_id: str) -> int:
        return await self.repo.count_by_status(user_id, status="pending")

    async def mark_processed(self, user_id: str, signal_ids: List[str]) -> int:
        """Marks signals consumed. Touches ONLY the signal rows — never the
        source entity they point at."""
        return await self.repo.mark_processed(user_id, signal_ids)

    async def mark_failed(
        self, user_id: str, signal_ids: List[str], *, error_code: str = "UNKNOWN"
    ) -> int:
        return await self.repo.mark_failed(user_id, signal_ids, error_code=error_code)


def _ref_class(ref: str) -> str:
    """Prefix only (e.g. "calendar", "situation") — enough for aggregate
    observability, never the identifier itself and never content."""
    text = str(ref or "")
    return text.split(":", 1)[0][:24] if ":" in text else text.split("_", 1)[0][:24]
