"""Maps adapter — surface AE maps proposals; no geocoding here."""
from __future__ import annotations

from typing import Any, Dict, List


class MapsAdapter:
    def artifacts_from_ae_session(self, ae: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for prop in ae.get("proposed_actions") or []:
            if prop.get("kind") == "maps" and prop.get("id"):
                out.append({
                    "kind": "maps",
                    "id": str(prop["id"]),
                    "label": prop.get("label") or "Mappa",
                })
        return out
