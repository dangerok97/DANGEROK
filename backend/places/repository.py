"""
Storage for places, candidates and observations.

Every read is scoped to an owner. A place list is a map of somebody's life, so
there is no query here that can return another person's by accident: the
user_id is a parameter of every method rather than something a caller might
remember to add.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from places.models import (
    LifePlace,
    PlaceCandidate,
    PresenceObservation,
    PresenceSession,
    PresenceState,
)

logger = logging.getLogger(__name__)

PLACES = "life_places"
CANDIDATES = "place_candidates"
OBSERVATIONS = "presence_observations"
SESSIONS = "presence_sessions"
STATES = "presence_states"

# Observations are the aggregable residue of sensor evidence, not a history.
# Long enough to notice that somewhere keeps coming back, short enough that
# nobody's movements sit in a database for a year.
OBSERVATION_TTL_DAYS = 30


class PlacesRepository:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[PLACES].create_index([("user_id", 1), ("state", 1)])
            await self.db[PLACES].create_index([("user_id", 1), ("role", 1)])
            await self.db[PLACES].create_index("id", unique=True)
            await self.db[CANDIDATES].create_index([("user_id", 1), ("outcome", 1)])
            await self.db[CANDIDATES].create_index("id", unique=True)
            await self.db[OBSERVATIONS].create_index([("user_id", 1), ("observed_at", -1)])
            await self.db[OBSERVATIONS].create_index("expires_at", expireAfterSeconds=0)
            await self.db[OBSERVATIONS].create_index([("user_id", 1), ("event_id", 1)])
            await self.db[SESSIONS].create_index([("user_id", 1), ("place_id", 1), ("exited_at", 1)])
            await self.db[SESSIONS].create_index([("user_id", 1), ("entered_at", -1)])
            await self.db[SESSIONS].create_index("id", unique=True)
            await self.db[STATES].create_index([("user_id", 1), ("place_id", 1)], unique=True)
        except Exception:
            logger.exception("indici places non creati (non fatale)")

    # --- places ---------------------------------------------------------

    async def save_place(self, place: LifePlace) -> LifePlace:
        place.touch()
        await self.db[PLACES].update_one(
            {"id": place.id, "user_id": place.user_id},
            {"$set": place.model_dump()},
            upsert=True,
        )
        return place

    async def get_place(self, user_id: str, place_id: str) -> Optional[LifePlace]:
        doc = await self.db[PLACES].find_one(
            {"id": place_id, "user_id": user_id}, {"_id": 0}
        )
        return LifePlace.model_validate(doc) if doc else None

    async def list_places(
        self, user_id: str, *, include_deleted: bool = False
    ) -> List[LifePlace]:
        query: Dict[str, Any] = {"user_id": user_id}
        if not include_deleted:
            query["state"] = {"$ne": "deleted"}
        docs = await self.db[PLACES].find(query, {"_id": 0}).to_list(200)
        return [LifePlace.model_validate(d) for d in docs]

    async def place_by_role(self, user_id: str, role: str) -> Optional[LifePlace]:
        doc = await self.db[PLACES].find_one(
            {
                "user_id": user_id,
                "role": role,
                "role_confirmed_by_user": True,
                "state": "confirmed",
            },
            {"_id": 0},
        )
        return LifePlace.model_validate(doc) if doc else None

    # --- candidates -----------------------------------------------------

    async def save_candidate(self, candidate: PlaceCandidate) -> PlaceCandidate:
        candidate.touch()
        await self.db[CANDIDATES].update_one(
            {"id": candidate.id, "user_id": candidate.user_id},
            {"$set": candidate.model_dump()},
            upsert=True,
        )
        return candidate

    async def get_candidate(self, user_id: str, candidate_id: str) -> Optional[PlaceCandidate]:
        doc = await self.db[CANDIDATES].find_one(
            {"id": candidate_id, "user_id": user_id}, {"_id": 0}
        )
        return PlaceCandidate.model_validate(doc) if doc else None

    async def list_candidates(
        self, user_id: str, *, outcomes: Optional[List[str]] = None
    ) -> List[PlaceCandidate]:
        query: Dict[str, Any] = {"user_id": user_id}
        if outcomes:
            query["outcome"] = {"$in": outcomes}
        docs = await self.db[CANDIDATES].find(query, {"_id": 0}).to_list(100)
        return [PlaceCandidate.model_validate(d) for d in docs]

    # --- observations ---------------------------------------------------

    async def add_observation(self, observation: PresenceObservation) -> PresenceObservation:
        observation.expires_at = datetime.now(timezone.utc) + timedelta(
            days=OBSERVATION_TTL_DAYS
        )
        await self.db[OBSERVATIONS].insert_one(observation.model_dump())
        return observation

    async def already_seen(self, user_id: str, event_id: Optional[str]) -> bool:
        """
        Whether this exact sighting has already been filed.

        A phone may deliver the same background callback twice, and a batch
        that failed halfway may be retried whole. Ten deliveries of one arrival
        must remain one evening at home.
        """
        if not event_id:
            return False
        found = await self.db[OBSERVATIONS].find_one(
            {"user_id": user_id, "event_id": event_id}, {"_id": 1}
        )
        return found is not None

    async def recent_observations(
        self, user_id: str, *, limit: int = 400
    ) -> List[PresenceObservation]:
        docs = (
            await self.db[OBSERVATIONS]
            .find({"user_id": user_id}, {"_id": 0})
            .sort("observed_at", -1)
            .to_list(limit)
        )
        return [PresenceObservation.model_validate(d) for d in docs]

    # --- presence --------------------------------------------------------

    async def get_state(self, user_id: str, place_id: str) -> PresenceState:
        """The state machine's memory for one place. Absent means outside."""
        doc = await self.db[STATES].find_one(
            {"user_id": user_id, "place_id": place_id}, {"_id": 0}
        )
        if doc:
            return PresenceState.model_validate(doc)
        return PresenceState(user_id=user_id, place_id=place_id)

    async def save_state(self, state: PresenceState) -> PresenceState:
        state.touch()
        await self.db[STATES].update_one(
            {"user_id": state.user_id, "place_id": state.place_id},
            {"$set": state.model_dump()},
            upsert=True,
        )
        return state

    async def open_session(self, user_id: str, place_id: str) -> Optional[PresenceSession]:
        """The stay currently under way here, if there is one."""
        doc = await self.db[SESSIONS].find_one(
            {"user_id": user_id, "place_id": place_id, "exited_at": None}, {"_id": 0}
        )
        return PresenceSession.model_validate(doc) if doc else None

    async def save_session(self, session: PresenceSession) -> PresenceSession:
        session.touch()
        await self.db[SESSIONS].update_one(
            {"id": session.id, "user_id": session.user_id},
            {"$set": session.model_dump()},
            upsert=True,
        )
        return session

    async def sessions_for(
        self,
        user_id: str,
        *,
        place_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> List[PresenceSession]:
        query: Dict[str, Any] = {"user_id": user_id}
        if place_id:
            query["place_id"] = place_id
        if since or until:
            # A stay counts if it overlaps the window at all: somebody who was
            # home from last night until this morning was home this morning.
            window: Dict[str, Any] = {}
            if until:
                window["$lte"] = until
            if window:
                query["entered_at"] = window
            if since:
                query["$or"] = [{"exited_at": None}, {"exited_at": {"$gte": since}}]
        docs = (
            await self.db[SESSIONS]
            .find(query, {"_id": 0})
            .sort("entered_at", -1)
            .to_list(limit)
        )
        return [PresenceSession.model_validate(d) for d in docs]

    async def forget_presence(
        self, user_id: str, *, place_id: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Erase where somebody has been, keeping the places they named.

        Scoped to one place when asked: "forget that I have been going there"
        is a smaller and more common request than "forget everywhere".
        """
        query: Dict[str, Any] = {"user_id": user_id}
        if place_id:
            query["place_id"] = place_id
        sessions = await self.db[SESSIONS].delete_many(dict(query))
        states = await self.db[STATES].delete_many(dict(query))
        obs_query: Dict[str, Any] = {"user_id": user_id}
        if place_id:
            obs_query["place_id"] = place_id
        observations = await self.db[OBSERVATIONS].delete_many(obs_query)
        return {
            "sessions_deleted": sessions.deleted_count,
            "states_deleted": states.deleted_count,
            "observations_deleted": observations.deleted_count,
        }

    async def forget_everything(self, user_id: str) -> Dict[str, int]:
        """
        Erase every trace of where this person has been.

        Turning location off must be able to mean it. Places the person typed
        in are theirs and survive; what the device observed does not.
        """
        obs = await self.db[OBSERVATIONS].delete_many({"user_id": user_id})
        # A candidate the person told ORA to stop asking about survives being
        # forgotten: "never ask me about this again" is an instruction, and
        # erasing it would mean asking again next week.
        cands = await self.db[CANDIDATES].delete_many(
            {"user_id": user_id, "outcome": {"$ne": "suppressed"}}
        )
        sessions = await self.db[SESSIONS].delete_many({"user_id": user_id})
        states = await self.db[STATES].delete_many({"user_id": user_id})
        return {
            "observations_deleted": obs.deleted_count,
            "candidates_deleted": cands.deleted_count,
            "sessions_deleted": sessions.deleted_count,
            "states_deleted": states.deleted_count,
        }
