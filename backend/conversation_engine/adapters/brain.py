"""Brain / knowledge adapter — read-only link helpers (no domain duplication)."""
from __future__ import annotations

from typing import Any, Dict, Optional


class BrainAdapter:
    def __init__(self, db, *, knowledge=None):
        self.db = db
        self.knowledge = knowledge

    async def link_ref(self, node_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not node_id:
            return None
        return {"kind": "brain", "id": node_id}
