"""Documents adapter — pass-through refs only."""
from __future__ import annotations

from typing import Any, Dict, List


class DocumentsAdapter:
    def __init__(self, db):
        self.db = db

    def artifacts_from_ae_session(self, ae: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        meta = ae.get("meta") or {}
        for d in meta.get("study_documents") or meta.get("travel_documents") or []:
            did = d.get("id") if isinstance(d, dict) else None
            if did:
                out.append({
                    "kind": "document",
                    "id": did,
                    "label": (d.get("title") if isinstance(d, dict) else None) or "Documento",
                })
        return out
