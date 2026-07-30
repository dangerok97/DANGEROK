"""ContextAssemblerService — public facade."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .assembler import assemble_pipeline
from .repository import ContextRepository
from .types import ASSEMBLER_VERSION


logger = logging.getLogger("ora.context")


def _flag_enabled() -> bool:
    return os.environ.get("CONTEXT_ASSEMBLER_ENABLED", "false").lower() in ("1", "true", "yes")


class ContextAssemblerService:
    def __init__(self, db):
        self.repo = ContextRepository(db)

    async def assemble(self, user_id: str, decision_id: str, *, force: bool = False, allow_highly_sensitive: bool = False) -> Optional[Dict[str, Any]]:
        decision = await self.repo.get_decision(user_id, decision_id)
        if not decision:
            return None

        snapshot = await assemble_pipeline(self.repo, user_id, decision, allow_highly_sensitive=allow_highly_sensitive)

        # Idempotence: if an active snapshot with the same hash exists, reuse.
        existing = await self.repo.find_by_hash(user_id, decision_id, snapshot["context_hash"])
        if existing and not force:
            return existing

        # Persist and supersede others.
        await self.repo.insert(snapshot)
        snapshot.pop("_id", None)  # insert_one mutated the dict
        await self.repo.supersede_others(user_id, decision_id, keep_id=snapshot["id"])
        logger.info(
            "context.assemble user=%s decision=%s hash=%s signals=%d conflicts=%d providers_ok=%d providers_fail=%d",
            user_id, decision_id, snapshot["context_hash"][:8],
            len(snapshot["signals"]), len(snapshot["conflicts"]),
            len(snapshot["provenance"]["providers_run"]),
            len(snapshot["provenance"]["providers_failed"]),
        )
        return snapshot

    async def refresh(self, user_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        return await self.assemble(user_id, decision_id, force=True)

    async def latest(self, user_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        return await self.repo.find_latest_active(user_id, decision_id)

    async def get_snapshot(self, user_id: str, snapshot_id: str) -> Optional[Dict[str, Any]]:
        return await self.repo.get_snapshot(user_id, snapshot_id)

    async def history(self, user_id: str, decision_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return await self.repo.list_history(user_id, decision_id, limit=limit)

    def is_enabled(self) -> bool:
        """Feature flag: when False, the adapter (below) is a no-op."""
        return _flag_enabled()

    def attach_to_decision_context(self, decision_ctx, snapshot: Optional[Dict[str, Any]]) -> None:
        """Adapter: with flag enabled and a snapshot present, expose it under
        `DecisionContext.signals["assembled_context"]`. Decision Engine rules
        currently do NOT consult this key, so ranking stays byte-stable."""
        if not self.is_enabled() or not snapshot:
            return
        try:
            decision_ctx.signals["assembled_context"] = snapshot
        except Exception:
            pass
