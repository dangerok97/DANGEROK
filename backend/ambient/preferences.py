"""
What a person has said about being interrupted, and about one thing in particular.

Two settings and one veto, deliberately small.

The setting is a **fact given to the judgement**, never a switch that bypasses
it. `if level == "minimal": never_push()` would be the fastest way to lose
everything this phase is built on: somebody who asked for less noise has not
asked to be kept in the dark about the one thing that would have mattered, and
only a judgement can tell those apart. So the preference travels into the
context in the person's own words and the model weighs it.

The veto is different, and it is a veto. "Non notificarmi per questa cosa" is
specific, it names a concern, and it is not the same as dismissing that
concern — somebody can want to keep seeing something on Home and want it to
stop reaching their pocket. Code enforces that one, because a person saying
"stop" should not depend on a model agreeing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PREFERENCES = "notification_preferences"
SUPPRESSIONS = "delivery_suppressions"

# How much somebody wants to be reached. Words, not thresholds — and the
# default is the middle one because nobody should have to answer this before
# they have seen what ORA does.
NotificationLevel = Literal["minimal", "balanced", "proactive"]

# What each one means, in the person's own words. Sent to the model exactly as
# written here, so what it weighs is what somebody chose rather than a label.
LEVEL_MEANING: Dict[str, str] = {
    "minimal": "Vuole essere interrotto solo quando conta davvero.",
    "balanced": "Vuole essere interrotto quando è utile, senza esagerare.",
    "proactive": "È disposto a essere interrotto più spesso, se serve.",
}

# How long a suppression lasts before it is worth asking again. Not forever:
# "not this, now" is usually what people mean, and a permanent veto set in a
# bad moment is a thing nobody remembers having set.
SUPPRESSION_DAYS = 90

# How long delivery history is kept. Enough for fatigue and for an audit;
# not a permanent record of everything ORA ever said to somebody.
HISTORY_RETENTION_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return _now().isoformat()


class QuietHours(BaseModel):
    """
    When somebody would rather not hear from anybody.

    Off unless set. Times are local hours in their own timezone, because a
    quiet window stored in UTC is a quiet window that moves when they travel.
    """

    enabled: bool = False
    start_hour: int = Field(default=22, ge=0, le=23)
    end_hour: int = Field(default=7, ge=0, le=23)

    def covers(self, local_hour: int) -> bool:
        """Whether this hour falls inside the window, including across midnight."""
        if not self.enabled:
            return False
        if self.start_hour == self.end_hour:
            return False
        if self.start_hour < self.end_hour:
            return self.start_hour <= local_hour < self.end_hour
        return local_hour >= self.start_hour or local_hour < self.end_hour

    def human(self) -> Optional[str]:
        if not self.enabled:
            return None
        return f"dalle {self.start_hour}:00 alle {self.end_hour}:00"


class NotificationPreferences(BaseModel):
    """Two settings, and nothing else pretending to be a setting."""

    owner_id: str
    level: NotificationLevel = "balanced"
    quiet_hours: QuietHours = Field(default_factory=QuietHours)
    updated_at: str = Field(default_factory=now_iso)
    # False until somebody actually chooses. A default is not a decision, and
    # the model should know which one it is looking at.
    chosen_by_user: bool = False

    def for_ai(self, *, local_hour: Optional[int] = None) -> Dict[str, Any]:
        """
        What the judgement is told. A fact about this person, not a rule.

        `they_chose_this` matters: weighing a default as though somebody had
        picked it would be reading a preference into silence.
        """
        out: Dict[str, Any] = {
            "how_much_they_want_to_be_interrupted": LEVEL_MEANING.get(
                self.level, LEVEL_MEANING["balanced"]
            ),
            "they_chose_this": self.chosen_by_user,
            "quiet_hours": self.quiet_hours.human(),
        }
        if local_hour is not None and self.quiet_hours.enabled:
            out["inside_their_quiet_hours"] = self.quiet_hours.covers(local_hour)
        return out

    def public(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "chosen_by_user": self.chosen_by_user,
            "quiet_hours": {
                "enabled": self.quiet_hours.enabled,
                "start_hour": self.quiet_hours.start_hour,
                "end_hour": self.quiet_hours.end_hour,
            },
        }


class DeliverySuppression(BaseModel):
    """
    "Non notificarmi per questa cosa."

    Scoped to one concern, and deliberately not a dismissal: the opportunity
    can stay exactly as active and as visible as it was. What stops is the
    part that reaches somebody where they are.
    """

    id: str = Field(default_factory=lambda: f"sup_{uuid.uuid4().hex[:16]}")
    owner_id: str
    # The opportunity, by handle. Owner-bound at every read.
    target: str = Field(max_length=64)
    scope: Literal["opportunity"] = "opportunity"
    source: Literal["user", "model"] = "user"
    created_at: str = Field(default_factory=now_iso)
    expires_at: Optional[datetime] = None


class PreferenceService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[PREFERENCES].create_index("owner_id", unique=True)
            await self.db[SUPPRESSIONS].create_index(
                [("owner_id", 1), ("target", 1)], unique=True
            )
            await self.db[SUPPRESSIONS].create_index("expires_at", expireAfterSeconds=0)
        except Exception:
            logger.exception("indici preferenze non creati (non fatale)")

    # --- settings ---------------------------------------------------------

    async def get(self, owner_id: str) -> NotificationPreferences:
        doc = await self.db[PREFERENCES].find_one({"owner_id": owner_id}, {"_id": 0})
        return (
            NotificationPreferences.model_validate(doc)
            if doc
            else NotificationPreferences(owner_id=owner_id)
        )

    async def set_level(self, owner_id: str, level: str) -> Dict[str, Any]:
        if level not in ("minimal", "balanced", "proactive"):
            return {"ok": False, "reason": "unknown_level"}
        prefs = await self.get(owner_id)
        prefs.level = level  # type: ignore[assignment]
        prefs.chosen_by_user = True
        prefs.updated_at = now_iso()
        await self._save(prefs)
        return {"ok": True, "preferences": prefs.public()}

    async def set_quiet_hours(
        self, owner_id: str, *, enabled: bool, start_hour: int = 22, end_hour: int = 7
    ) -> Dict[str, Any]:
        prefs = await self.get(owner_id)
        prefs.quiet_hours = QuietHours(
            enabled=enabled,
            start_hour=max(0, min(23, int(start_hour))),
            end_hour=max(0, min(23, int(end_hour))),
        )
        prefs.chosen_by_user = True
        prefs.updated_at = now_iso()
        await self._save(prefs)
        return {"ok": True, "preferences": prefs.public()}

    async def _save(self, prefs: NotificationPreferences) -> None:
        await self.db[PREFERENCES].update_one(
            {"owner_id": prefs.owner_id}, {"$set": prefs.model_dump()}, upsert=True
        )

    # --- the veto ---------------------------------------------------------

    async def suppress(
        self, owner_id: str, target: str, *, source: str = "user"
    ) -> Dict[str, Any]:
        """
        Stop reaching them about this one thing.

        Not a dismissal: nothing about the opportunity itself changes, and it
        goes on appearing wherever it was appearing. Only the pocket goes
        quiet.
        """
        if not target:
            return {"ok": False, "reason": "missing_target"}
        suppression = DeliverySuppression(
            owner_id=owner_id, target=target, source=source  # type: ignore[arg-type]
        )
        doc = suppression.model_dump()
        doc["expires_at"] = _now() + timedelta(days=SUPPRESSION_DAYS)
        await self.db[SUPPRESSIONS].update_one(
            {"owner_id": owner_id, "target": target}, {"$set": doc}, upsert=True
        )

        # Anything already intending to arrive about it is now wrong.
        try:
            from delivery.service import DeliveryService

            await DeliveryService(self.db).cancel_for_opportunity(
                owner_id, target, reason="l'utente ha chiesto di non essere avvisato"
            )
        except Exception as e:
            logger.info("suppression cancel soft-fail: %s", type(e).__name__)

        return {"ok": True, "target": target}

    async def unsuppress(self, owner_id: str, target: str) -> Dict[str, Any]:
        result = await self.db[SUPPRESSIONS].delete_one(
            {"owner_id": owner_id, "target": target}
        )
        return {"ok": True, "removed": result.deleted_count}

    async def is_suppressed(self, owner_id: str, target: str) -> bool:
        """Owner-bound by construction: the filter carries both halves."""
        if not target:
            return False
        found = await self.db[SUPPRESSIONS].find_one(
            {"owner_id": owner_id, "target": target}, {"_id": 0, "id": 1}
        )
        return found is not None

    async def suppressed_targets(self, owner_id: str, *, limit: int = 20) -> List[str]:
        docs = await self.db[SUPPRESSIONS].find(
            {"owner_id": owner_id}, {"_id": 0, "target": 1}
        ).to_list(limit)
        return [d["target"] for d in docs]

    async def forget_all(self, owner_id: str) -> Dict[str, int]:
        prefs = await self.db[PREFERENCES].delete_many({"owner_id": owner_id})
        sup = await self.db[SUPPRESSIONS].delete_many({"owner_id": owner_id})
        return {
            "preferences_deleted": prefs.deleted_count,
            "suppressions_deleted": sup.deleted_count,
        }
