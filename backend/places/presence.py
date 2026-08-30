"""
Being somewhere, as opposed to having been measured near it.

    A PLACE IS A ZONE, NOT A POINT.
    ENTER/EXIT USE HYSTERESIS + DWELL.

A GPS fix is not a position; it is a claim about a position, with a radius of
doubt attached. Treating one as arrival produces a life history in which
somebody entered and left their own home eleven times while asleep, because
the phone's idea of where it was drifted across a line.

Two things stop that, and both are geometry rather than judgement.

**Hysteresis.** Entering is decided against a tighter circle than leaving. Once
inside, drifting a little does not put you outside — you have to actually go,
past a boundary that is deliberately further out than the one you crossed to
get in. One threshold for both directions is what makes a stationary person
flicker.

**Dwell.** Crossing a line is not staying. A car passing the end of the street
enters the circle and leaves it, and neither event is a visit, so a crossing
opens a *pending* state that only becomes presence if it is still true a while
later. The same in reverse: a fix that jumps outside is a suspicion, not a
departure.

None of this is the model's business. Whether twelve seconds of GPS is
physically inside a circle has a right answer and code computes it. What the
presence *means* — whether a pattern deserves attention, whether it is worth
asking about — is reasoning, and lives elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from places.geometry import distance_meters
from places.models import (
    Coordinates,
    LifePlace,
    PresenceObservation,
    PresenceState,
    PresenceZone,
    ZoneHit,
)

# How long a crossing has to hold before it counts. Conservative on the way in,
# more patient on the way out: mistakenly recording a visit invents a fact,
# while being slow to notice somebody left only delays one.
ENTER_DWELL_SECONDS = 180
EXIT_DWELL_SECONDS = 300

# How many fixes must agree before a crossing is anything. One is a reading;
# two apart in time is the beginning of a story.
MIN_ENTER_SAMPLES = 2
MIN_EXIT_SAMPLES = 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return _now()


def zone_of(place: LifePlace) -> Optional[PresenceZone]:
    """The zone a place stands for, or None when nobody gave it a location."""
    if place.coordinates is None:
        return None
    return place.zone or PresenceZone.around(place.coordinates)


def hits(point: Coordinates, places: List[LifePlace]) -> List[ZoneHit]:
    """
    Every zone this fix could be inside, nearest first.

    Returns candidates, not an answer. Two zones can genuinely overlap — a bar
    next door to an office is not a modelling error, it is a street — and
    picking the nearer centre by a few metres would be a fragile rule dressed
    up as a fact.
    """
    found: List[ZoneHit] = []
    for place in places:
        zone = zone_of(place)
        if zone is None:
            continue
        distance = distance_meters(point, zone.center)
        if distance <= zone.exit_radius_m:
            found.append(
                ZoneHit(
                    place_id=place.id,
                    distance_m=round(distance, 1),
                    inside_entry=distance <= zone.entry_radius_m,
                    inside_exit=True,
                    zone=zone,
                )
            )
    return sorted(found, key=lambda h: h.distance_m)


def unambiguous(found: List[ZoneHit]) -> Optional[ZoneHit]:
    """
    The one zone this fix is in, when there is exactly one.

    When several zones claim the same point, this returns nothing and the
    caller records an ambiguous observation. An ambiguous presence is a true
    statement about an uncertain situation; a confident wrong one is not.
    """
    inside = [h for h in found if h.inside_entry]
    if len(inside) == 1:
        return inside[0]
    return None


def fix_is_usable(observation: PresenceObservation, zone: PresenceZone) -> bool:
    """
    Whether a reading is precise enough to say anything about this zone.

    A fix accurate to fifty metres tells you plenty about a hundred-metre
    circle and nothing at all about a twenty-metre one. Rather than a single
    global threshold — which would be wrong for both — the doubt is compared
    with the zone it is being used against: a reading whose error is larger
    than the zone's entry radius cannot distinguish inside from outside, so it
    is kept as evidence and refused as proof.
    """
    accuracy = observation.coordinates.accuracy_meters
    if accuracy is None:
        return True
    return accuracy <= zone.entry_radius_m


def advance(
    state: PresenceState,
    observation: PresenceObservation,
    hit: Optional[ZoneHit],
) -> Tuple[PresenceState, Optional[str]]:
    """
    One observation against one place's state. Pure, and the only mover.

    Returns the new state and, when the world actually changed, what changed:
    `"entered"` or `"exited"`. Everything else is a state edging towards one of
    those, which is the point — most observations should change nothing.
    """
    at = _parse(observation.observed_at)
    inside_entry = bool(hit and hit.inside_entry)
    inside_exit = bool(hit and hit.inside_exit)

    # A reading too vague to separate inside from outside decides nothing. It
    # neither confirms a pending crossing nor cancels one: it is simply not
    # evidence about this zone.
    if hit is not None and not fix_is_usable(observation, hit.zone):
        state = state.model_copy(deep=True)
        state.last_seen_at = observation.observed_at
        state.ignored_fixes += 1
        return state, None

    state = state.model_copy(deep=True)
    state.last_seen_at = observation.observed_at

    if state.status == "outside":
        if inside_entry:
            state.status = "pending_enter"
            state.pending_since = observation.observed_at
            state.pending_samples = 1
        return state, None

    if state.status == "pending_enter":
        if not inside_entry:
            # It was a pass, not an arrival. Nothing to record and nothing to
            # remember: the whole point of pending is that it can evaporate.
            state.status = "outside"
            state.pending_since = None
            state.pending_samples = 0
            return state, None
        state.pending_samples += 1
        held = (at - _parse(state.pending_since or observation.observed_at)).total_seconds()
        if held >= ENTER_DWELL_SECONDS and state.pending_samples >= MIN_ENTER_SAMPLES:
            state.status = "present"
            state.since = state.pending_since
            state.pending_since = None
            state.pending_samples = 0
            return state, "entered"
        return state, None

    if state.status == "present":
        if not inside_exit:
            state.status = "pending_exit"
            state.pending_since = observation.observed_at
            state.pending_samples = 1
        return state, None

    if state.status == "pending_exit":
        if inside_exit:
            # Drift, not departure. Back to present, and the clock resets —
            # this branch is the one that stops a stationary phone from
            # producing a night of arrivals and departures.
            state.status = "present"
            state.pending_since = None
            state.pending_samples = 0
            return state, None
        state.pending_samples += 1
        held = (at - _parse(state.pending_since or observation.observed_at)).total_seconds()
        if held >= EXIT_DWELL_SECONDS and state.pending_samples >= MIN_EXIT_SAMPLES:
            state.status = "outside"
            state.since = None
            state.pending_since = None
            state.pending_samples = 0
            return state, "exited"
        return state, None

    return state, None


def describe(state: PresenceState) -> Dict[str, object]:
    """
    What a screen may say about this. Never a coordinate.

    `pending_enter` deliberately reads as not present: somebody who has been
    inside the circle for ninety seconds has not arrived anywhere yet, and
    telling them "sei qui" would be the single-sample mistake wearing a nicer
    hat.
    """
    return {
        "present": state.status == "present",
        "status": state.status,
        "since": state.since,
        "last_seen_at": state.last_seen_at,
    }
