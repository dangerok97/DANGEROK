"""
Where a person's life happens, and the difference between seeing and knowing.

Three objects, and the distance between them is the whole point.

`PresenceObservation` is what the device noticed: coordinates, a moment, how
long. It is evidence and nothing more. `PlaceCandidate` is what arithmetic can
say about a pile of those: the same spot, this many times, over this long. It
is still not a fact about anyone's life — "the same coordinates on eleven
weekday evenings" is a measurement, and calling it a gym is a guess. And
`LifePlace` is what the person confirmed: this is my home, that is where I
work, that one is my mother's house.

    GPS OBSERVES. AI UNDERSTANDS. USER CONFIRMS.

So nothing here promotes itself. A candidate does not become a place because a
counter passed a threshold; it becomes a place when somebody says what it is.
The role is a small, open set because a person's places are not an
enumeration — the human label stays free text, and "Palestra", "Casa di mamma"
and "Università" are all just names.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# What the person said this place is to them. Deliberately tiny: `other`
# carries everything that is not the two roles ORA reasons about structurally,
# and the name is what actually distinguishes places from one another.
SemanticRole = Literal["home", "work", "other"]

# How ORA came to hold this place at all.
PlaceSource = Literal[
    "user_stated",        # typed or dictated it
    "current_position",   # "use where I am now"
    "confirmed_candidate",  # a pattern the person then named
    "life_profile",       # already known from setup, given coordinates later
]

PlaceState = Literal["confirmed", "candidate", "dismissed", "deleted"]

# Where the final coordinates came from.
#
#     ADDRESS != LOCATION
#
# An address is a readable description; the point is where the person actually
# means. `map_selection` exists because those two disagree often enough to
# matter: Google puts the pin on the street, and the entrance is round the
# back. When somebody moves the map, that is the answer.
LocationSource = Literal[
    "current_position",   # "sono qui adesso"
    "google_place",       # an address they picked, pin where Google put it
    "map_selection",      # they moved the map: their point wins
    "name_only",          # a name with nowhere attached yet
]

# A candidate's fate, decided by a person and not by a counter.
# `dismissed` is "not this time". `suppressed` is "never ask me about this
# place again" — a different answer, and one that has to survive.
CandidateOutcome = Literal[
    "pending", "asked", "confirmed", "dismissed", "suppressed", "muted"
]

# How precisely we can speak about where something is.
CoordinatePrecision = Literal["exact", "approximate", "locality_only"]

# Anything closer than this is the same place as far as a person is concerned:
# a building, a car park, a door on the other side of it.
SAME_PLACE_METERS = 120.0

# Below this a fix is too vague to attach to a place at all.
UNUSABLE_ACCURACY_METERS = 500.0

# The default size of a place, when nobody has said how big it is. A home is
# a building with a courtyard and a bit of street, not a pin: 90 metres is
# generous enough to survive an ordinary urban fix and tight enough that the
# building next door is not "home".
DEFAULT_ENTRY_RADIUS_M = 90.0
# Leaving is measured against a wider circle than arriving. The gap is the
# hysteresis: it is what a stationary phone's drift has to exceed before ORA
# believes somebody went out.
DEFAULT_EXIT_RADIUS_M = 140.0
MIN_RADIUS_M = 25.0
MAX_RADIUS_M = 2000.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_place_id() -> str:
    return f"plc_{secrets.token_hex(8)}"


def new_candidate_id() -> str:
    return f"pcd_{secrets.token_hex(8)}"


def new_observation_id() -> str:
    return f"pob_{secrets.token_hex(8)}"


def new_session_id() -> str:
    return f"pses_{secrets.token_hex(8)}"


class Coordinates(BaseModel):
    """A point, and how much to trust it."""

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    accuracy_meters: Optional[float] = None
    precision: CoordinatePrecision = "approximate"

    def coarse(self) -> Dict[str, Any]:
        """
        Rounded, for anything that is not routing.

        Four decimals is roughly eleven metres — enough to tell two places
        apart, not enough to point at a window. Routing asks for the precise
        pair explicitly, so the coarse form is what everything else sees.
        """
        return {
            "latitude": round(self.latitude, 4),
            "longitude": round(self.longitude, 4),
            "accuracy_meters": self.accuracy_meters,
            "precision": self.precision,
        }

    def precise(self) -> Dict[str, float]:
        return {"latitude": self.latitude, "longitude": self.longitude}


class PresenceZone(BaseModel):
    """
    The shape of a place: a centre and two radii.

        A PLACE IS A ZONE, NOT A POINT.

    Entering is judged against `entry_radius_m` and leaving against the wider
    `exit_radius_m`. The gap between them is not slack, it is the mechanism:
    with one radius for both, a phone sitting still on a table crosses back and
    forth over the same line and produces a night of arrivals and departures.

    Sizes are per place, never per kind. A flat and a hospital campus are not
    the same size, and a rule that made homes 90 metres because they are homes
    would be a domain detector with a tape measure.
    """

    center: Coordinates
    entry_radius_m: float = Field(
        default=DEFAULT_ENTRY_RADIUS_M, ge=MIN_RADIUS_M, le=MAX_RADIUS_M
    )
    exit_radius_m: float = Field(
        default=DEFAULT_EXIT_RADIUS_M, ge=MIN_RADIUS_M, le=MAX_RADIUS_M
    )
    # How the size was arrived at: a default, what the person set, or what the
    # observations themselves suggested.
    source: str = Field(default="default", max_length=40)

    @model_validator(mode="after")
    def _exit_must_be_wider(self) -> "PresenceZone":
        if self.exit_radius_m <= self.entry_radius_m:
            raise ValueError(
                "il raggio di uscita deve essere più largo di quello di ingresso: "
                "senza quel margine il rumore GPS produce entrate e uscite continue"
            )
        return self

    @classmethod
    def around(cls, center: Coordinates, **over: Any) -> "PresenceZone":
        return cls(center=center, **over)


class ZoneHit(BaseModel):
    """One zone a fix falls inside, and how far in."""

    place_id: str
    distance_m: float
    inside_entry: bool
    inside_exit: bool
    zone: PresenceZone


PresenceStatus = Literal["outside", "pending_enter", "present", "pending_exit"]


class PresenceState(BaseModel):
    """
    Where somebody stands with respect to one place, right now.

    The two `pending` states are the whole defence against a single reading.
    Crossing a boundary starts a suspicion; only time and further readings turn
    it into presence, and a suspicion that stops being true simply evaporates
    without ever having been a fact.
    """

    user_id: str
    place_id: str
    status: PresenceStatus = "outside"
    # When the current presence began — set only once `present` is real.
    since: Optional[str] = None
    # When the current suspicion began.
    pending_since: Optional[str] = None
    pending_samples: int = 0
    last_seen_at: Optional[str] = None
    # Readings too vague to say anything about this zone. Counted, not used.
    ignored_fixes: int = 0
    updated_at: str = Field(default_factory=now_iso)

    def touch(self) -> None:
        self.updated_at = now_iso()


class PresenceSession(BaseModel):
    """
    A stay: when it began, when it ended, and nothing about what it meant.

    An open session has no `exited_at`. There is at most one open per place per
    person, and duplicate observations extend it rather than starting another —
    ten fixes in a kitchen are one evening at home.
    """

    id: str = Field(default_factory=new_session_id)
    user_id: str
    place_id: str
    entered_at: str
    exited_at: Optional[str] = None
    # How this stay began. `user_confirmation` is a person saying "sono qui
    # adesso"; everything else is a sensor being believed after dwell. The
    # distinction matters afterwards: a stay somebody stated is not something
    # to second-guess when a fix drifts.
    source: str = "foreground_device"
    # How many readings supported it, and how many were too vague to count.
    observation_count: int = 1
    weak_fixes: int = 0
    # True when more than one zone contained the fixes: the stay happened, but
    # which place it belongs to is not settled.
    ambiguous: bool = False
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def duration_seconds(self, *, until: Optional[str] = None) -> Optional[int]:
        """
        How long the stay lasted, or has lasted so far.

        An open session is measured against now, because "you have been home
        for three hours" is a fact about an unfinished stay, not a missing one.
        """
        end = self.exited_at or until or now_iso()
        try:
            a = datetime.fromisoformat(self.entered_at.replace("Z", "+00:00"))
            b = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return max(0, int((b - a).total_seconds()))

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "place_id": self.place_id,
            "entered_at": self.entered_at,
            "exited_at": self.exited_at,
            "open": self.exited_at is None,
            "duration_seconds": self.duration_seconds(),
            "ambiguous": self.ambiguous,
        }


class PresenceObservation(BaseModel):
    """
    The device was here, then. Evidence, with an expiry.

    Deliberately thin, and deliberately not a trail: what survives is enough to
    notice that somewhere keeps coming back, not enough to reconstruct where
    somebody went last Tuesday. Raw signals already expire in `location`; these
    are the aggregable residue, and they expire too.
    """

    id: str = Field(default_factory=new_observation_id)
    user_id: str
    coordinates: Coordinates
    observed_at: str = Field(default_factory=now_iso)
    dwell_seconds: Optional[int] = Field(default=None, ge=0)
    # Filled only when a confirmed place already covers this point.
    place_id: Optional[str] = None
    # Filled once a cluster has formed around it.
    candidate_id: Optional[str] = None
    source: str = "foreground_device"
    # The id the device gave this sighting. An OS can deliver the same callback
    # twice, and a queued batch can be sent twice after a failed flush; this is
    # what makes the second delivery the same sighting instead of a new one.
    event_id: Optional[str] = Field(default=None, max_length=64)
    # True when more than one zone contained this fix: kept as evidence,
    # attached to nothing, because guessing which would be the fragile rule.
    ambiguous: bool = False
    expires_at: Optional[datetime] = None
    created_at: str = Field(default_factory=now_iso)


class PlaceCandidate(BaseModel):
    """
    Somewhere that keeps happening, with no claim about what it is.

    Every field here is something arithmetic can establish: a centre, a count,
    a first and last sighting, how long the person tends to stay. None of it
    says "gym", and nothing in this file ever will — the question of what a
    place *is* goes to the model, and the answer goes to the person.
    """

    id: str = Field(default_factory=new_candidate_id)
    user_id: str
    centroid: Coordinates
    observation_count: int = Field(default=0, ge=0)
    distinct_days: int = Field(default=0, ge=0)
    total_dwell_seconds: int = Field(default=0, ge=0)
    first_seen: str = Field(default_factory=now_iso)
    last_seen: str = Field(default_factory=now_iso)
    # Coarse label from reverse geocoding, when there is one. Never invented,
    # and never treated as meaning: "Via Tommaseo" is an address, not a life.
    locality: str = Field(default="", max_length=160)
    address_hint: str = Field(default="", max_length=240)

    # How spread out the sightings are: the observed size of the place, which
    # is what a zone should be built from if this ever becomes one.
    spread_m: float = 0.0

    outcome: CandidateOutcome = "pending"
    # The question ORA raised about it, if it decided one was worth asking.
    question_id: Optional[str] = None
    # Set when the person said "stop asking about this one".
    muted: bool = False
    became_place_id: Optional[str] = None

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def evidence(self) -> Dict[str, Any]:
        """
        What the model is shown. Measurements, phrased as measurements.

        No verdict, no score, no "significance": if the pattern is worth a
        question, that is a judgement, and judgement is not the counter's job.
        """
        return {
            "candidate_id": self.id,
            "times_seen": self.observation_count,
            "distinct_days": self.distinct_days,
            "typical_dwell_minutes": (
                round(self.total_dwell_seconds / max(1, self.observation_count) / 60)
                if self.total_dwell_seconds
                else None
            ),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "locality": self.locality or None,
            "address_hint": self.address_hint or None,
            "already_asked": self.outcome == "asked",
        }


class LifePlace(BaseModel):
    """
    A place the person confirmed, in their own words.

    The name is theirs and free. The role is the small structural fact ORA can
    reason with — where you live, where you work, or neither — and it is only
    ever set because somebody said so.

    `life_node_id` is the link back to what the Life Graph already knows. Home
    is not invented here: if setup already recorded a residence, this gives
    that node coordinates rather than starting a second, competing idea of
    where the person lives.
    """

    id: str = Field(default_factory=new_place_id)
    user_id: str

    label: str = Field(min_length=1, max_length=120)
    role: SemanticRole = "other"
    # True only when a person answered, never when code inferred.
    role_confirmed_by_user: bool = False

    coordinates: Optional[Coordinates] = None
    # How big this place is. None means nobody has said, and the default
    # applies — the size is a property of the place, never of its kind.
    zone: Optional[PresenceZone] = None
    address: str = Field(default="", max_length=240)
    locality: str = Field(default="", max_length=160)
    # What Google calls this address, when an address was chosen. Kept so the
    # same place can be recognised again; never used as the position, which is
    # `coordinates` and only ever `coordinates`.
    google_place_id: str = Field(default="", max_length=200)
    # How the coordinates were arrived at. Not a duplicate of `source`: that
    # says how the place entered ORA, this says where the point came from.
    location_source: LocationSource = "name_only"

    source: PlaceSource = "user_stated"
    state: PlaceState = "confirmed"
    # Where it came from, when it came from a pattern.
    from_candidate_id: Optional[str] = None
    # What the Life Graph already calls this, when it already calls it
    # something. Set on link, never guessed.
    life_node_id: Optional[str] = None

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def public(self) -> Dict[str, Any]:
        """
        What an interface may see.

        Precise coordinates are not in here. A list of places is a map of
        somebody's life; the screen needs a name, a locality and a state, and
        the exact pair only leaves the server when something is actually being
        routed to.
        """
        return {
            "id": self.id,
            "label": self.label,
            "role": self.role,
            "role_confirmed_by_user": self.role_confirmed_by_user,
            "address": self.address or None,
            "locality": self.locality or None,
            "source": self.source,
            "location_source": self.location_source,
            # Whether this place is tied to an address Google knows. The id
            # itself stays on the server: a screen has no use for it.
            "from_address": bool(self.google_place_id),
            "state": self.state,
            "has_coordinates": self.coordinates is not None,
            # Coarse centre and the exit radius, so the device can ask the OS
            # to wake it near here. Deliberately the wider circle: being woken
            # slightly early costs a callback, being woken late costs an
            # arrival. The decision still happens on the server.
            "zone_center": (
                {
                    **self.coordinates.coarse(),
                    # The pair above has been rounded, so it is no longer the
                    # exact fix whatever the source said it was. Carrying the
                    # original label here would describe eleven metres of
                    # uncertainty as certainty.
                    "precision": "approximate",
                    "exit_radius_m": (
                        self.zone.exit_radius_m if self.zone else DEFAULT_EXIT_RADIUS_M
                    ),
                }
                if self.coordinates is not None
                else None
            ),
            "from_candidate": bool(self.from_candidate_id),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def for_ai(self) -> Dict[str, Any]:
        """What reasoning is shown: names and roles, not a coordinate list."""
        return {
            "place_id": self.id,
            "name": self.label,
            "role": self.role if self.role_confirmed_by_user else None,
            "locality": self.locality or None,
            "reachable": self.coordinates is not None,
        }


RoutineState = Literal["candidate", "accepted", "dismissed", "stale"]


def new_routine_id() -> str:
    return f"rtn_{secrets.token_hex(8)}"


class ObservedRoutine(BaseModel):
    """
    A shape somebody's days keep taking, as read by the model.

        ROUTINE OBSERVATION != ROUTINE FACT.

    A projection over presence sessions, never a copy of them: the sessions
    stay where they are and this points at them. It exists only once the model
    has looked at the evidence and said there is something here — no counter
    creates one, and `candidate` is where every one of them starts.

    `interpretation` is the model's sentence about the pattern, kept in its own
    words. It is not a promise and not a rule: a routine that stops happening
    goes `stale` rather than being defended.
    """

    id: str = Field(default_factory=new_routine_id)
    user_id: str
    # The places, in the order they keep appearing.
    place_sequence: List[str] = Field(default_factory=list, max_length=8)
    # When in the day it tends to happen, in the person's own clock.
    typical_start: str = Field(default="", max_length=20)
    typical_end: str = Field(default="", max_length=20)
    weekdays: List[str] = Field(default_factory=list, max_length=7)

    occurrences: int = 0
    first_observed: str = Field(default_factory=now_iso)
    last_observed: str = Field(default_factory=now_iso)
    # The stays this was read from. Pointers, not duplicates.
    session_ids: List[str] = Field(default_factory=list, max_length=60)

    interpretation: str = Field(default="", max_length=400)
    state: RoutineState = "candidate"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "places": self.place_sequence,
            "typical_start": self.typical_start or None,
            "typical_end": self.typical_end or None,
            "weekdays": self.weekdays,
            "occurrences": self.occurrences,
            "what_ora_thinks": self.interpretation or None,
            "state": self.state,
        }


class PlaceResolution(BaseModel):
    """
    The answer to "which place did they mean", and how sure that is.

    Ambiguity is reported rather than resolved by picking the first match: two
    places called something similar is a question for the person, not a coin
    toss.
    """

    place: Optional[LifePlace] = None
    candidates: List[LifePlace] = Field(default_factory=list)
    reason: str = Field(default="", max_length=200)

    @property
    def resolved(self) -> bool:
        return self.place is not None
