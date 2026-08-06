"""Calendar adapter — surface AE calendar effects; no inventing events."""
from __future__ import annotations

from typing import Any, Dict, List


class CalendarAdapter:
    def __init__(self, db):
        self.db = db

    def artifacts_from_ae_session(self, ae: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        effects = ae.get("effects") or {}
        for ev_id in effects.get("calendar_event_ids") or []:
            out.append({"kind": "calendar", "id": str(ev_id), "label": "Evento calendario"})
        for prop in ae.get("proposed_actions") or []:
            if prop.get("kind") == "calendar" and prop.get("id"):
                out.append({
                    "kind": "calendar",
                    "id": str(prop["id"]),
                    "label": prop.get("label") or "Proposta calendario",
                })
        return out
