"""
Places, from a fix on a map to something a person calls home.

The orchestration is deliberately dull, because every interesting decision
belongs to someone else. Code decides what is objective — is this the same spot
as that one, how many days has it appeared on, does this name resolve to
exactly one place. The model decides whether a pattern is worth a question. The
person decides what the place is.

Nothing here promotes a candidate on its own. There is no threshold that turns
observations into a place, and adding one later would be the moment this stops
being honest.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from places import analytics, geometry, presence
from places.models import (
    SAME_PLACE_METERS,
    UNUSABLE_ACCURACY_METERS,
    Coordinates,
    LifePlace,
    PlaceCandidate,
    PlaceResolution,
    PresenceObservation,
    ObservedRoutine,
    PresenceSession,
    PresenceZone,
)
from places.repository import PlacesRepository

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PlacesService:
    def __init__(self, db):
        self.db = db
        self.repo = PlacesRepository(db)

    # --- what the person keeps -----------------------------------------

    async def list_places(self, user_id: str) -> List[LifePlace]:
        places = await self.repo.list_places(user_id)
        return [p for p in places if p.state != "dismissed"]

    async def get_place(self, user_id: str, place_id: str) -> Optional[LifePlace]:
        return await self.repo.get_place(user_id, place_id)

    async def save_place(
        self,
        user_id: str,
        *,
        label: str,
        role: str = "other",
        coordinates: Optional[Coordinates] = None,
        address: str = "",
        locality: str = "",
        source: str = "user_stated",
        from_candidate_id: Optional[str] = None,
        role_confirmed_by_user: bool = True,
        currently_here: bool = False,
        google_place_id: str = "",
        location_source: str = "",
    ) -> LifePlace:
        """
        Write down a place the person named.

        `role_confirmed_by_user` defaults to true because everything that
        reaches this method came from somebody saying something. The one caller
        that passes false is the path where a role was merely inherited from an
        older record and nobody has re-confirmed it.
        """
        if role not in {"home", "work", "other"}:
            role = "other"

        place = LifePlace(
            user_id=user_id,
            label=label.strip()[:120],
            role=role,  # type: ignore[arg-type]
            role_confirmed_by_user=bool(role_confirmed_by_user) and role != "other",
            coordinates=coordinates,
            address=address.strip()[:240],
            locality=locality.strip()[:160],
            source=source,  # type: ignore[arg-type]
            google_place_id=google_place_id.strip()[:200],
            # Where the point came from. Inferred only when the caller did not
            # say: a place with coordinates and no story is at least honest
            # about having been picked rather than looked up.
            location_source=(  # type: ignore[arg-type]
                location_source
                if location_source
                in {"current_position", "google_place", "map_selection", "name_only"}
                else ("map_selection" if coordinates is not None else "name_only")
            ),
            from_candidate_id=from_candidate_id,
        )
        # Home and work are singular. A second one means the person moved or
        # changed jobs, so the previous one stops being the answer rather than
        # competing with the new one.
        if place.role in {"home", "work"} and place.role_confirmed_by_user:
            previous = await self.repo.place_by_role(user_id, place.role)
            if previous and previous.id != place.id:
                previous.role = "other"
                previous.role_confirmed_by_user = False
                await self.repo.save_place(previous)

        await self._link_to_life_graph(place)
        saved = await self.repo.save_place(place)

        if currently_here and saved.coordinates is not None:
            await self.confirm_current_presence(user_id, saved.id)
        return saved

    async def confirm_current_presence(
        self, user_id: str, place_id: str
    ) -> Optional[PresenceSession]:
        """
        Somebody said they are here. Believe them, now.

            LOCATION OBSERVATION != PRESENCE FACT
            EXPLICIT USER STATEMENT IS A LIFE FACT

        Dwell exists because a sensor reading is a guess that needs
        corroborating; a person telling you where they are is not a guess. Ten
        minutes of "non sei qui" after somebody has just said "sono qui" is ORA
        arguing with them about their own life.

        This does not weaken the GPS path. Nothing about `advance()` changes:
        inferred presence still needs hysteresis and dwell. This is a second,
        narrower door into the same state, and it is opened only by a
        statement.
        """
        place = await self.repo.get_place(user_id, place_id)
        if place is None or place.coordinates is None:
            return None

        # One stay per place, whichever door it came through. A confirmation
        # while already present is a no-op, not a second session.
        session = await self.repo.open_session(user_id, place_id)
        if session is None:
            session = await self.repo.save_session(
                PresenceSession(
                    user_id=user_id,
                    place_id=place_id,
                    entered_at=_now().isoformat(),
                    source="user_confirmation",
                )
            )

        state = await self.repo.get_state(user_id, place_id)
        state.status = "present"
        state.since = session.entered_at
        state.pending_since = None
        state.pending_samples = 0
        state.last_seen_at = _now().isoformat()
        await self.repo.save_state(state)

        # Being here means not being somewhere else: an old stay left open at
        # another place would make two places both say "sei qui".
        for other in await self.repo.list_places(user_id):
            if other.id == place_id:
                continue
            open_elsewhere = await self.repo.open_session(user_id, other.id)
            if open_elsewhere is not None:
                await self._close_stay(user_id, other.id, _now().isoformat())
                stale = await self.repo.get_state(user_id, other.id)
                stale.status = "outside"
                stale.since = None
                await self.repo.save_state(stale)
        return session

    async def relocate_place(
        self,
        user_id: str,
        place_id: str,
        *,
        coordinates: Coordinates,
        address: str = "",
        locality: str = "",
        google_place_id: str = "",
        location_source: str = "map_selection",
    ) -> Optional[LifePlace]:
        """
        Move a place to where the person says it is.

        The same operation the editor performs when creating one, so a place
        corrected later is indistinguishable from a place got right the first
        time. Presence history stays: they did go there, whatever the pin said.
        """
        place = await self.repo.get_place(user_id, place_id)
        if place is None:
            return None
        place.coordinates = coordinates
        if address:
            place.address = address.strip()[:240]
        if locality:
            place.locality = locality.strip()[:160]
        place.google_place_id = google_place_id.strip()[:200]
        if location_source in {
            "current_position", "google_place", "map_selection", "name_only"
        }:
            place.location_source = location_source  # type: ignore[assignment]
        # The zone was drawn around the old point; it has to follow.
        if place.zone is not None:
            place.zone = PresenceZone(
                center=coordinates,
                entry_radius_m=place.zone.entry_radius_m,
                exit_radius_m=place.zone.exit_radius_m,
                source=place.zone.source,
            )
        return await self.repo.save_place(place)

    async def rename_place(
        self, user_id: str, place_id: str, label: str
    ) -> Optional[LifePlace]:
        place = await self.repo.get_place(user_id, place_id)
        if place is None:
            return None
        place.label = label.strip()[:120] or place.label
        return await self.repo.save_place(place)

    async def remove_place(self, user_id: str, place_id: str) -> bool:
        place = await self.repo.get_place(user_id, place_id)
        if place is None:
            return False
        place.state = "deleted"
        await self.repo.save_place(place)
        # A place nobody keeps has no presence either: leaving the stays behind
        # would mean a history of visits to somewhere that no longer exists.
        await self.repo.forget_presence(user_id, place_id=place_id)
        return True

    async def _link_to_life_graph(self, place: LifePlace) -> None:
        """
        Attach a place to what the Life Graph already knows, if it knows it.

        Setup may already have recorded that somebody has a home; this gives
        that node a location rather than starting a second, competing idea of
        where the person lives. Best effort: a missing graph is not a reason to
        refuse to remember an address.
        """
        if place.role != "home" or not place.role_confirmed_by_user:
            return
        try:
            from life_graph import LifeGraphService

            graph = LifeGraphService(self.db)
            nodes = await graph.list_nodes(place.user_id, node_type="home")
            if nodes:
                place.life_node_id = nodes[0].get("id")
        except Exception:
            logger.info("life graph non collegato per questo luogo (non fatale)")

    # --- what the device notices ---------------------------------------

    async def record_observation(
        self,
        user_id: str,
        *,
        latitude: float,
        longitude: float,
        accuracy_meters: Optional[float] = None,
        dwell_seconds: Optional[int] = None,
        source: str = "foreground_device",
        observed_at: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        File one sighting: against a known place, or into a cluster.

        A fix too vague to tell two streets apart is dropped rather than
        recorded — an observation nobody can attach to anything is not evidence
        of anything, and keeping it would only make the counts look busier.
        """
        if accuracy_meters is not None and accuracy_meters > UNUSABLE_ACCURACY_METERS:
            return {"recorded": False, "reason": "accuracy_too_low"}

        # Before anything moves: a sighting delivered twice must not advance a
        # state machine twice, or a duplicated callback becomes a second stay.
        if await self.repo.already_seen(user_id, event_id):
            return {"recorded": False, "reason": "already_recorded", "duplicate": True}

        point = Coordinates(
            latitude=latitude, longitude=longitude, accuracy_meters=accuracy_meters
        )
        observation = PresenceObservation(
            user_id=user_id,
            coordinates=point,
            dwell_seconds=dwell_seconds,
            source=source,
            event_id=event_id,
            # Dwell is measured against the moment the fix was taken, not the
            # moment it arrived: a batch of readings uploaded when the app comes
            # back online describes the past, not the last five seconds.
            **({"observed_at": observed_at} if observed_at else {}),
        )

        places = [p for p in await self.repo.list_places(user_id) if p.coordinates]
        found = presence.hits(point, places)
        transitions = await self._advance_presence(user_id, observation, places, found)

        # Inside somewhere they already named? Then there is nothing to cluster.
        settled = presence.unambiguous(found)
        if settled is not None:
            observation.place_id = settled.place_id
            await self.repo.add_observation(observation)
            return {
                "recorded": True,
                "at_known_place": settled.place_id,
                "distance_m": settled.distance_m,
                **transitions,
            }

        if len([h for h in found if h.inside_entry]) > 1:
            # Two places claim the same point. That is a fact about the street,
            # not a decision to make: the sighting is kept, attached to nothing,
            # and no session is opened for either.
            observation.ambiguous = True
            await self.repo.add_observation(observation)
            return {
                "recorded": True,
                "ambiguous_between": [h.place_id for h in found if h.inside_entry],
                **transitions,
            }

        candidate = await self._cluster_into_candidate(user_id, observation)
        await self.repo.add_observation(observation)
        return {
            "recorded": True,
            "candidate_id": candidate.id,
            "times_seen": candidate.observation_count,
            **transitions,
        }

    async def _advance_presence(
        self,
        user_id: str,
        observation: PresenceObservation,
        places: List[LifePlace],
        found: List,
    ) -> Dict[str, Any]:
        """
        Move every place's state machine one step, and open or close stays.

        Every known place is evaluated, not only the one the fix is inside:
        leaving is something that happens to the place you are no longer at, so
        a machine that only saw the zones you are currently in would never
        notice a departure.
        """
        by_place = {h.place_id: h for h in found}
        entered: List[str] = []
        exited: List[str] = []

        for place in places:
            if presence.zone_of(place) is None:
                continue
            state = await self.repo.get_state(user_id, place.id)
            hit = by_place.get(place.id)
            # A place that shares the fix with another is not evidence for
            # either: an ambiguous sighting must not open a stay.
            if hit is not None and hit.inside_entry and len(
                [h for h in found if h.inside_entry]
            ) > 1:
                hit = None
            new_state, change = presence.advance(state, observation, hit)
            await self.repo.save_state(new_state)

            if change == "entered":
                await self._open_stay(user_id, place.id, new_state.since or observation.observed_at)
                entered.append(place.id)
            elif change == "exited":
                await self._close_stay(user_id, place.id, observation.observed_at)
                exited.append(place.id)
            elif new_state.status == "present":
                await self._extend_stay(user_id, place.id)

        out: Dict[str, Any] = {}
        if entered:
            out["entered"] = entered
        if exited:
            out["exited"] = exited
        return out

    async def _open_stay(self, user_id: str, place_id: str, entered_at: str) -> PresenceSession:
        """
        Start a stay, unless one is already under way.

        Idempotent on purpose: ten fixes in a kitchen are one evening at home,
        and a repeated "entered" must find the existing session rather than
        stack a second one on top of it.
        """
        existing = await self.repo.open_session(user_id, place_id)
        if existing is not None:
            return existing
        return await self.repo.save_session(
            PresenceSession(user_id=user_id, place_id=place_id, entered_at=entered_at)
        )

    async def _close_stay(self, user_id: str, place_id: str, exited_at: str) -> Optional[PresenceSession]:
        """Close the open stay, if there is one. A second exit closes nothing."""
        session = await self.repo.open_session(user_id, place_id)
        if session is None:
            return None
        session.exited_at = exited_at
        return await self.repo.save_session(session)

    async def _extend_stay(self, user_id: str, place_id: str) -> None:
        """Another fix while present: the same stay, one more reading behind it."""
        session = await self.repo.open_session(user_id, place_id)
        if session is None:
            return
        session.observation_count += 1
        await self.repo.save_session(session)

    # --- what a screen and the next sprint need to ask ------------------

    async def presence_summary(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Where the person is, per place, in the words a screen may use.

        The primitives the next sprint will build routines on: present or not,
        when the current stay began, when they last arrived and last left.
        Never a coordinate.
        """
        out: Dict[str, Dict[str, Any]] = {}
        for place in await self.repo.list_places(user_id):
            state = await self.repo.get_state(user_id, place.id)
            recent = await self.repo.sessions_for(user_id, place_id=place.id, limit=5)
            open_now = next((x for x in recent if x.exited_at is None), None)
            closed = [x for x in recent if x.exited_at]
            out[place.id] = {
                **presence.describe(state),
                "current_session_seconds": (
                    open_now.duration_seconds() if open_now else None
                ),
                "last_entered_at": recent[0].entered_at if recent else None,
                "last_exited_at": closed[0].exited_at if closed else None,
            }
        return out

    async def time_at_place(
        self, user_id: str, place_id: str, *, since: str, until: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        How long, in total, inside a bounded window.

        Bounded on purpose: an unbounded "how much of your life" is an
        analytics question, and this sprint deliberately stops at the
        primitive that such a question would be built from.
        """
        sessions = await self.repo.sessions_for(
            user_id, place_id=place_id, since=since, until=until
        )
        total = 0
        for session in sessions:
            seconds = session.duration_seconds(until=until)
            if seconds:
                total += seconds
        return {
            "place_id": place_id,
            "since": since,
            "until": until,
            "sessions": len(sessions),
            "total_seconds": total,
        }

    # --- presence history as context ------------------------------------

    async def time_at(
        self, user_id: str, place_id: str, *, period: str = "this_week"
    ) -> Dict[str, Any]:
        """
        How long, how many visits, and whether they are still there.

        `period` is a word — today, this_week, this_month, last_30_days — and
        which word a question means is a reading of the question, so the model
        picks it. Turning the word into two timestamps and the timestamps into
        a total is arithmetic, and stays here.
        """
        start, end = analytics.window(period)
        place = await self.repo.get_place(user_id, place_id)
        if place is None:
            return {"known_place": False}
        sessions = await self.repo.sessions_for(
            user_id, place_id=place_id, since=start.isoformat(), limit=400
        )
        return {
            "known_place": True,
            "place": place.for_ai(),
            "period": period,
            "from": start.isoformat(),
            "to": end.isoformat(),
            **analytics.time_at_place(sessions, start=start, end=end),
        }

    async def journeys_between(
        self,
        user_id: str,
        *,
        from_place_id: Optional[str] = None,
        to_place_id: Optional[str] = None,
        period: str = "last_30_days",
    ) -> Dict[str, Any]:
        """
        The trips somebody actually made between two of their places.

        Observed, never routed: the gap between leaving one place and arriving
        at the next includes the walk to the car and the queue at the bar, which
        is exactly what makes it a description of their life rather than of the
        road.
        """
        start, _ = analytics.window(period)
        sessions = await self.repo.sessions_for(
            user_id, since=start.isoformat(), limit=600
        )
        found = analytics.transitions(sessions)
        if from_place_id:
            found = [t for t in found if t["from_place_id"] == from_place_id]
        if to_place_id:
            found = [t for t in found if t["to_place_id"] == to_place_id]

        names = {p.id: p.label for p in await self.repo.list_places(user_id)}
        return {
            "period": period,
            "from_place": names.get(from_place_id or "") or None,
            "to_place": names.get(to_place_id or "") or None,
            "observed": analytics.journey_stats([t["duration_seconds"] for t in found]),
            "recent": [
                {
                    "from": names.get(t["from_place_id"], "?"),
                    "to": names.get(t["to_place_id"], "?"),
                    "departed_at": t["departed_at"],
                    "arrived_at": t["arrived_at"],
                    "duration_seconds": t["duration_seconds"],
                }
                for t in found[-8:]
            ],
        }

    async def where_now(self, user_id: str) -> Dict[str, Any]:
        """
        The one place they are in, if there is one, and for how long.

        Used before asking somebody where they are. A question ORA can answer
        from what it already holds is a question it should not be asking.
        """
        summary = await self.presence_summary(user_id)
        names = {p.id: p.label for p in await self.repo.list_places(user_id)}
        here = [pid for pid, info in summary.items() if info.get("present")]
        if len(here) != 1:
            return {"at_a_known_place": False, "places_known": len(names)}
        pid = here[0]
        return {
            "at_a_known_place": True,
            "place": names.get(pid),
            "place_id": pid,
            "since": summary[pid].get("since"),
            "seconds_here": summary[pid].get("current_session_seconds"),
        }

    async def routine_evidence(
        self, user_id: str, *, period: str = "last_30_days"
    ) -> Dict[str, Any]:
        """
        Everything countable about the shape of somebody's days.

        Days, sequences, times, durations and the journeys between. No verdict
        anywhere in it: whether this amounts to a routine is the next function's
        question, and the answer belongs to a model and then to a person.
        """
        start, _ = analytics.window(period)
        sessions = await self.repo.sessions_for(
            user_id, since=start.isoformat(), limit=600
        )
        places = await self.repo.list_places(user_id)
        return {
            "period": period,
            "place_names": {p.id: p.label for p in places},
            "days": analytics.day_shape(sessions),
            "journeys": analytics.transitions(sessions),
        }

    async def review_routines(
        self, user_id: str, *, period: str = "last_30_days", language: str = "it"
    ) -> Optional[Dict[str, Any]]:
        """
        Ask the model whether the days have a shape worth naming.

        No threshold creates a routine here. The evidence goes over, and what
        comes back is either nothing — the ordinary outcome — or one pattern
        with the model's own sentence about it, stored as a candidate.
        """
        from places.reasoning import read_the_shape_of_the_days

        evidence = await self.routine_evidence(user_id, period=period)
        if len(evidence["days"]) < 2:
            return None

        read = await read_the_shape_of_the_days(
            evidence["days"],
            place_names=evidence["place_names"],
            journeys=evidence["journeys"],
            language=language,
        )
        if read is None:
            return None

        routine = ObservedRoutine(
            user_id=user_id,
            place_sequence=read["place_ids"],
            weekdays=read["weekdays"],
            typical_start=read["typical_start"],
            typical_end=read["typical_end"],
            occurrences=read["occurrences"],
            interpretation=read["interpretation"],
            state="candidate",
        )
        await self.db.observed_routines.update_one(
            {"user_id": user_id, "place_sequence": routine.place_sequence},
            {"$set": routine.model_dump()},
            upsert=True,
        )
        return {
            "routine": routine.public(),
            "worth_asking": read["worth_asking"],
            "question": read["question"],
        }

    async def list_routines(self, user_id: str) -> List[Dict[str, Any]]:
        docs = await self.db.observed_routines.find(
            {"user_id": user_id}, {"_id": 0}
        ).to_list(20)
        return [ObservedRoutine.model_validate(d).public() for d in docs]

    async def set_zone(
        self, user_id: str, place_id: str, *, entry_radius_m: float, exit_radius_m: float
    ) -> Optional[LifePlace]:
        """Resize a place. The contract still holds: leaving is the wider circle."""
        place = await self.repo.get_place(user_id, place_id)
        if place is None or place.coordinates is None:
            return None
        place.zone = PresenceZone(
            center=place.coordinates,
            entry_radius_m=entry_radius_m,
            exit_radius_m=exit_radius_m,
            source="user_stated",
        )
        return await self.repo.save_place(place)

    async def forget_presence(
        self, user_id: str, *, place_id: Optional[str] = None
    ) -> Dict[str, int]:
        """Erase where somebody has been. The places they named stay."""
        return await self.repo.forget_presence(user_id, place_id=place_id)

    async def _cluster_into_candidate(
        self, user_id: str, observation: PresenceObservation
    ) -> PlaceCandidate:
        """Fold the sighting into a repeated spot, or start a new one."""
        candidates = await self.repo.list_candidates(
            user_id, outcomes=["pending", "asked"]
        )
        match = geometry.nearest(
            observation.coordinates, [(c.id, c.centroid) for c in candidates]
        )
        if match and match[1] <= SAME_PLACE_METERS:
            candidate = next(c for c in candidates if c.id == match[0])
            geometry.absorb(candidate, observation)
        else:
            candidate = PlaceCandidate(
                user_id=user_id,
                centroid=observation.coordinates,
                observation_count=1,
                total_dwell_seconds=int(observation.dwell_seconds or 0),
                first_seen=observation.observed_at,
                last_seen=observation.observed_at,
            )
        observation.candidate_id = candidate.id
        candidate.distinct_days = await self._distinct_days(user_id, candidate)
        candidate.spread_m = max(
            candidate.spread_m,
            round(geometry.distance_meters(candidate.centroid, observation.coordinates), 1),
        )
        return await self.repo.save_candidate(candidate)

    async def _distinct_days(self, user_id: str, candidate: PlaceCandidate) -> int:
        recent = await self.repo.recent_observations(user_id)
        mine = [o for o in recent if o.candidate_id == candidate.id]
        return max(candidate.distinct_days, geometry.distinct_days(mine) if mine else 1)

    # --- from a pattern to a question ----------------------------------

    async def review_candidates(self, user_id: str, *, language: str = "it") -> List[Dict[str, Any]]:
        """
        Ask the model whether any repeated spot is worth raising.

        The code contributes measurements and the identity of what it measured;
        it contributes no opinion about which of them matter. What comes back
        is turned into ordinary open questions — the same ones the rest of ORA
        uses — so a place question waits, dedupes and resumes like any other.
        """
        from places.reasoning import should_ask_about

        candidates = [
            c
            for c in await self.repo.list_candidates(user_id, outcomes=["pending"])
            if not c.muted
        ]
        if not candidates:
            return []

        places = await self.list_places(user_id)
        decisions = await should_ask_about(
            [c.evidence() for c in candidates],
            known_places=[p.for_ai() for p in places],
            language=language,
        )

        raised: List[Dict[str, Any]] = []
        by_id = {c.id: c for c in candidates}
        for decision in decisions:
            candidate = by_id.get(decision["candidate_id"])
            if candidate is None:
                continue
            question_id = await self._raise_question(candidate, decision)
            candidate.outcome = "asked"
            candidate.question_id = question_id
            await self.repo.save_candidate(candidate)
            raised.append(
                {
                    "candidate_id": candidate.id,
                    "question": decision["question"],
                    "question_id": question_id,
                }
            )
        return raised

    async def _raise_question(
        self, candidate: PlaceCandidate, decision: Dict[str, Any]
    ) -> Optional[str]:
        """
        Put the question where every other unanswered question lives.

        No new question engine: V3.1's open questions already handle waiting,
        deduplication and resuming, and a place question has no reason to be
        special.
        """
        try:
            from waiting.models import OpenQuestion
            from waiting.repository import OpenQuestionRepository

            question = OpenQuestion(
                user_id=candidate.user_id,
                question=decision["question"],
                why_needed=decision.get("why", ""),
                context_label="Luoghi",
                expected_answer_kind="free_text",
                dedupe_key=f"place_candidate:{candidate.id}",
            )
            repo = OpenQuestionRepository(self.db)
            existing = await repo.find_open_by_dedupe(candidate.user_id, question.dedupe_key)
            if existing:
                return existing.get("id")
            await repo.insert(question)
            return question.id
        except Exception:
            logger.exception("domanda sul luogo non registrata (non fatale)")
            return None

    async def answer_candidate(
        self, user_id: str, candidate_id: str, answer: str, *, language: str = "it"
    ) -> Dict[str, Any]:
        """
        What the person said about a repeated spot, and what follows from it.

        This is the only path from candidate to place, and it needs a human
        sentence to walk it.
        """
        from places.reasoning import interpret_answer

        candidate = await self.repo.get_candidate(user_id, candidate_id)
        if candidate is None:
            return {"ok": False, "reason": "unknown_candidate"}

        read = await interpret_answer(
            answer,
            question=f"candidate {candidate.id}",
            language=language,
        )
        if read is None or read["decision"] == "unclear":
            return {"ok": False, "reason": "unclear_answer"}

        if read["decision"] == "mute":
            # Not "no thanks" but "never ask me about this place again". It
            # survives a request to forget observations, because otherwise the
            # question would come back next week.
            candidate.muted = True
            candidate.outcome = "suppressed"
            await self.repo.save_candidate(candidate)
            return {"ok": True, "outcome": "suppressed"}

        if read["decision"] == "skip":
            candidate.outcome = "dismissed"
            await self.repo.save_candidate(candidate)
            return {"ok": True, "outcome": "dismissed"}

        place = await self.save_place(
            user_id,
            label=read["label"],
            role=read["role"],
            coordinates=candidate.centroid,
            locality=candidate.locality,
            address=candidate.address_hint,
            source="confirmed_candidate",
            from_candidate_id=candidate.id,
        )
        candidate.outcome = "confirmed"
        candidate.became_place_id = place.id
        await self.repo.save_candidate(candidate)
        return {"ok": True, "outcome": "confirmed", "place": place.public()}

    # --- naming a place out loud ---------------------------------------

    async def resolve_destination(self, user_id: str, spoken: str) -> PlaceResolution:
        """
        Work out which place somebody meant by what they called it.

        Exact on the name, then on a confirmed role. No fuzzy matching: a
        destination resolved by approximate string distance is how somebody
        gets sent to the wrong address, and being asked which one is a much
        smaller cost than being taken somewhere else.
        """
        wanted = (spoken or "").strip()
        if not wanted:
            return PlaceResolution(reason="nessuna destinazione indicata")

        places = [p for p in await self.list_places(user_id) if p.state == "confirmed"]
        if not places:
            return PlaceResolution(reason="non conosco ancora nessun luogo")

        exact = [p for p in places if p.label.casefold() == wanted.casefold()]
        if len(exact) == 1:
            return PlaceResolution(place=exact[0])
        if len(exact) > 1:
            return PlaceResolution(
                candidates=exact, reason="più luoghi hanno esattamente questo nome"
            )

        # A role is a thing the person confirmed, so "lavoro" may be resolved
        # by role rather than by name — but only against a role they set.
        role = {"casa": "home", "home": "home", "lavoro": "work", "work": "work"}.get(
            wanted.casefold()
        )
        if role:
            by_role = [
                p for p in places if p.role == role and p.role_confirmed_by_user
            ]
            if len(by_role) == 1:
                return PlaceResolution(place=by_role[0])

        return PlaceResolution(
            candidates=places[:6],
            reason=f"non ho un luogo che si chiama «{wanted}»",
        )

    async def forget_observations(self, user_id: str) -> Dict[str, int]:
        """Everything the device noticed, gone. Named places stay."""
        return await self.repo.forget_everything(user_id)
