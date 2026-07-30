"""
DecisionService — the single facade the rest of the app talks to.

Owns:
- CRUD on the `decisions` collection.
- Migration from the legacy `tasks` collection (one-shot per user).
- Ranking pipeline (via injected evaluator + reasoner + ranking).
- Rich history log per decision.

Everything routes through this service so the rest of the app (server.py)
stays thin.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .context import DecisionContext
from .evaluator import DecisionEvaluator
from .ranking import DecisionRanking
from .reasoner import DecisionReasoner


# Map legacy Task.kind → Decision.category.
LEGACY_KIND_TO_CATEGORY = {
    "travel": "travel",
    "bill": "bill",
    "message": "communication",
    "health": "health",
    "finance": "insight",
    "generic": "generic",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"dec_{uuid.uuid4().hex[:12]}"


class DecisionService:
    def __init__(
        self,
        db,
        evaluator: Optional[DecisionEvaluator] = None,
        reasoner: Optional[DecisionReasoner] = None,
        ranking: Optional[DecisionRanking] = None,
    ):
        self.db = db
        self.evaluator = evaluator or DecisionEvaluator()
        self.reasoner = reasoner or DecisionReasoner()
        self.ranking = ranking or DecisionRanking(self.evaluator, self.reasoner)

    # ---------- collections ---------------------------------------------
    @property
    def col(self):
        return self.db.decisions

    @property
    def legacy_col(self):
        return self.db.tasks

    # ---------- migration -----------------------------------------------
    async def migrate_user_tasks(self, user_id: str) -> int:
        """Copy legacy tasks → decisions (once). Returns count migrated."""
        cursor = self.legacy_col.find(
            {"user_id": user_id, "$or": [{"migrated_to": {"$exists": False}}, {"migrated_to": None}]},
            {"_id": 0},
        )
        migrated = 0
        async for t in cursor:
            dec = self._task_to_decision(t)
            await self.col.insert_one(dec)
            await self.legacy_col.update_one(
                {"id": t["id"], "user_id": user_id},
                {"$set": {"migrated_to": dec["id"]}},
            )
            migrated += 1
        return migrated

    def _task_to_decision(self, t: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": _new_id(),
            "user_id": t["user_id"],
            "title": t.get("title") or "Senza titolo",
            "description": t.get("context") or "",
            "origin": "migration:task",
            "category": LEGACY_KIND_TO_CATEGORY.get(t.get("kind") or "generic", "generic"),
            "urgency": t.get("urgency", 5),
            "importance": t.get("importance", 5),
            "risk": t.get("risk", 3),
            "economic_impact": t.get("economic_impact", 3),
            "personal_impact": t.get("personal_impact", 5),
            "time_required_min": t.get("time_required_min", 15),
            "energy": t.get("energy", 3),
            "place": t.get("place"),
            "people": [],
            "starts_at": None,
            "deadline": _infer_deadline_from_metadata(t),
            "status": t.get("status", "open"),
            "linked_to": [],
            "metadata": t.get("metadata") or {},
            "last_resolution": t.get("last_resolution"),
            "history": [{"at": _now_iso(), "event": "migrated_from_task", "data": {"task_id": t.get("id")}}],
            "created_at": t.get("created_at") or _now_iso(),
        }

    # ---------- CRUD ----------------------------------------------------
    async def list_all(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self.col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1)
        return await cursor.to_list(length=500)

    async def list_open(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self.col.find({"user_id": user_id, "status": "open"}, {"_id": 0})
        return await cursor.to_list(length=500)

    async def get(self, user_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one({"id": decision_id, "user_id": user_id}, {"_id": 0})

    async def create(self, user_id: str, payload: Dict[str, Any], origin: str = "user") -> Dict[str, Any]:
        doc = {
            "id": _new_id(),
            "user_id": user_id,
            "title": payload.get("title") or "Senza titolo",
            "description": payload.get("description") or payload.get("context") or "",
            "origin": origin,
            "category": payload.get("category") or "generic",
            "urgency": payload.get("urgency", 5),
            "importance": payload.get("importance", 5),
            "risk": payload.get("risk", 3),
            "economic_impact": payload.get("economic_impact", 3),
            "personal_impact": payload.get("personal_impact", 5),
            "time_required_min": payload.get("time_required_min", 15),
            "energy": payload.get("energy", 3),
            "place": payload.get("place"),
            "people": payload.get("people") or [],
            "starts_at": payload.get("starts_at"),
            "deadline": payload.get("deadline"),
            "status": "open",
            "linked_to": payload.get("linked_to") or [],
            "metadata": payload.get("metadata") or {},
            "history": [{"at": _now_iso(), "event": "created", "data": {"origin": origin}}],
            "created_at": _now_iso(),
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def _update(self, user_id: str, decision_id: str, updates: Dict[str, Any], event: str, event_data: Optional[Dict[str, Any]] = None) -> bool:
        entry = {"at": _now_iso(), "event": event, "data": event_data or {}}
        res = await self.col.update_one(
            {"id": decision_id, "user_id": user_id},
            {"$set": updates, "$push": {"history": entry}},
        )
        return res.matched_count > 0

    async def dismiss(self, user_id: str, decision_id: str) -> bool:
        return await self._update(user_id, decision_id, {"status": "dismissed"}, "dismissed")

    async def complete(self, user_id: str, decision_id: str) -> bool:
        return await self._update(
            user_id,
            decision_id,
            {"status": "resolved", "resolved_at": _now_iso()},
            "resolved",
        )

    async def attach_resolution(self, user_id: str, decision_id: str, solution: str) -> bool:
        return await self._update(
            user_id,
            decision_id,
            {"last_resolution": solution, "last_resolved_at": _now_iso()},
            "ai_resolution_proposed",
            {"length": len(solution)},
        )

    # ---------- ranking -------------------------------------------------
    async def top(self, user_id: str, limit: int = 3, signals: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        open_docs = await self.list_open(user_id)
        ctx = DecisionContext.build(user_id, open_docs, signals=signals)
        ranked = self.ranking.rank(ctx)
        return ranked[:limit]

    async def ranked(self, user_id: str, signals: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        open_docs = await self.list_open(user_id)
        ctx = DecisionContext.build(user_id, open_docs, signals=signals)
        return self.ranking.rank(ctx)


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------
def _infer_deadline_from_metadata(t: Dict[str, Any]) -> Optional[str]:
    """Legacy tasks sometimes stashed 'due_days' or 'eta_min' in metadata.
    Convert to an ISO deadline so the reasoner can use it."""
    md = t.get("metadata") or {}
    now = datetime.now(timezone.utc)
    if isinstance(md.get("due_days"), (int, float)):
        return (now + timedelta(days=float(md["due_days"]))).isoformat()
    if isinstance(md.get("eta_min"), (int, float)):
        # eta_min is more a "starts_at" than a deadline — leave it null here.
        return None
    return None


# ============================================================
# Seed: rich, engine-friendly initial decisions.
# ============================================================
def build_seed_decisions(user_id: str) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)

    def iso_plus(days: float = 0, hours: float = 0, minutes: float = 0) -> str:
        return (now + timedelta(days=days, hours=hours, minutes=minutes)).isoformat()

    trip_id = _new_id()

    seeds: List[Dict[str, Any]] = [
        {
            "id": _new_id(),
            "title": "Esci tra 25 minuti.",
            "description": "Il traffico sta aumentando sul tuo tragitto verso l'ufficio.",
            "origin": "seed",
            "category": "travel",
            "urgency": 9, "importance": 8, "risk": 6, "time_required_min": 2,
            "energy": 1, "economic_impact": 2, "personal_impact": 7,
            "place": "Ufficio", "people": [],
            "starts_at": iso_plus(minutes=25),
            "deadline": None,
            "metadata": {"eta_min": 25},
        },
        {
            "id": _new_id(),
            "title": "La bolletta luce scade tra 3 giorni.",
            "description": "€ 87,40 · Enel Energia. Puoi pagarla in 5 minuti da home banking.",
            "origin": "seed",
            "category": "bill",
            "urgency": 7, "importance": 8, "risk": 7, "time_required_min": 5,
            "energy": 1, "economic_impact": 6, "personal_impact": 5,
            "place": None, "people": [],
            "starts_at": None,
            "deadline": iso_plus(days=3),
            "metadata": {"amount": 87.40, "provider": "Enel"},
        },
        {
            "id": trip_id,
            "title": "Volo per Milano domani mattina.",
            "description": "Partenza dalle 07:40 · Alitalia AZ2020.",
            "origin": "seed",
            "category": "travel",
            "urgency": 6, "importance": 8, "risk": 5, "time_required_min": 90,
            "energy": 6, "economic_impact": 3, "personal_impact": 8,
            "place": "Aeroporto Fiumicino", "people": [],
            "starts_at": iso_plus(days=1),
            "deadline": None,
            "metadata": {"flight": "AZ2020"},
        },
        {
            "id": _new_id(),
            "title": "Prepara la valigia.",
            "description": "1 notte a Milano. Riunione mattina + cena serale.",
            "origin": "seed",
            "category": "travel_prep",
            "urgency": 5, "importance": 6, "risk": 4, "time_required_min": 20,
            "energy": 3, "economic_impact": 1, "personal_impact": 6,
            "place": "Casa", "people": [],
            "starts_at": None,
            "deadline": iso_plus(hours=20),
            "linked_to": [trip_id],
            "metadata": {},
        },
        {
            "id": _new_id(),
            "title": "Marco aspetta ancora una tua risposta.",
            "description": "Messaggio ricevuto 2 giorni fa su WhatsApp.",
            "origin": "seed",
            "category": "communication",
            "urgency": 6, "importance": 6, "risk": 3, "time_required_min": 3,
            "energy": 2, "economic_impact": 1, "personal_impact": 8,
            "place": None, "people": ["Marco"],
            "starts_at": None,
            "deadline": None,
            "metadata": {"channel": "WhatsApp"},
        },
        {
            "id": _new_id(),
            "title": "Palestra oggi.",
            "description": "Allenamento serale programmato.",
            "origin": "seed",
            "category": "fitness",
            "urgency": 4, "importance": 5, "risk": 1, "time_required_min": 60,
            "energy": 7, "economic_impact": 0, "personal_impact": 5,
            "place": "Palestra", "people": [],
            "starts_at": iso_plus(hours=6),
            "deadline": None,
            "metadata": {},
        },
        {
            "id": _new_id(),
            "title": "Hai risparmiato 220 € questo mese.",
            "description": "+18% rispetto al mese scorso. Nessuna azione richiesta.",
            "origin": "seed",
            "category": "insight",
            "urgency": 2, "importance": 4, "risk": 1, "time_required_min": 1,
            "energy": 1, "economic_impact": 5, "personal_impact": 6,
            "place": None, "people": [],
            "starts_at": None,
            "deadline": None,
            "metadata": {"saved_eur": 220, "delta_pct": 18},
        },
    ]

    for s in seeds:
        s.setdefault("user_id", user_id)
        s.setdefault("status", "open")
        s.setdefault("linked_to", s.get("linked_to") or [])
        s.setdefault("history", [{"at": _now_iso(), "event": "seeded", "data": {}}])
        s.setdefault("created_at", _now_iso())
    return seeds
