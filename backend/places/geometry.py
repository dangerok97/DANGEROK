"""
Distance and clustering. Arithmetic only, and no opinions.

Everything here answers questions that have right answers: how far apart are
two points, do these observations fall in the same spot, where is the middle of
them. Nothing here decides whether a spot matters, what it is for, or whether
it is worth mentioning. That is the model's job and then the person's.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from places.models import (
    SAME_PLACE_METERS,
    Coordinates,
    PlaceCandidate,
    PresenceObservation,
)

EARTH_RADIUS_M = 6_371_000.0


def distance_meters(a: Coordinates, b: Coordinates) -> float:
    """Great-circle distance. Haversine — metres, over the distances we care about."""
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def same_place(a: Coordinates, b: Coordinates, *, within: float = SAME_PLACE_METERS) -> bool:
    """
    Whether two fixes are the same place to a person.

    The threshold is generous on purpose. A phone put down inside a building
    wanders; treating each wander as a new place would produce a list of
    near-duplicates that means nothing to anybody.
    """
    return distance_meters(a, b) <= within


def nearest(point: Coordinates, options: Iterable[Tuple[str, Coordinates]]) -> Optional[Tuple[str, float]]:
    """The closest of a set, with its distance. None when the set is empty."""
    best: Optional[Tuple[str, float]] = None
    for key, coords in options:
        d = distance_meters(point, coords)
        if best is None or d < best[1]:
            best = (key, d)
    return best


def recentre(centroid: Coordinates, count: int, incoming: Coordinates) -> Coordinates:
    """
    Move a cluster's centre to include one more observation.

    A running mean, so a cluster settles on where somebody actually is rather
    than on wherever they first happened to be standing. Accuracy is kept as
    the best any contributing fix offered — an accurate fix should not be
    diluted by a vague one.
    """
    n = max(1, count)
    lat = (centroid.latitude * n + incoming.latitude) / (n + 1)
    lon = (centroid.longitude * n + incoming.longitude) / (n + 1)
    accuracies = [
        v for v in (centroid.accuracy_meters, incoming.accuracy_meters) if v is not None
    ]
    return Coordinates(
        latitude=lat,
        longitude=lon,
        accuracy_meters=min(accuracies) if accuracies else None,
        precision=centroid.precision,
    )


def _day(iso: str) -> str:
    """The calendar day of a timestamp, for counting distinct days."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError):
        return iso[:10]


def distinct_days(observations: Iterable[PresenceObservation]) -> int:
    """
    How many separate days a place was seen on.

    Ten fixes in one afternoon is one afternoon. Ten fixes across ten days is
    a pattern — and the difference between those two is exactly the sort of
    thing a threshold in code would flatten, so it is counted and handed over
    rather than judged here.
    """
    return len({_day(o.observed_at) for o in observations})


def cluster(
    observations: List[PresenceObservation], *, within: float = SAME_PLACE_METERS
) -> List[Dict[str, object]]:
    """
    Group observations that share a spot.

    Single-pass and order-dependent, which is honest for what this is: a way of
    noticing repetition, not a spatial statistics library. Each group carries
    its centre, its size, its span and the days it touched, and says nothing
    about what any of it means.
    """
    groups: List[Dict[str, object]] = []
    for observation in sorted(observations, key=lambda o: o.observed_at):
        placed = False
        for group in groups:
            if same_place(group["centroid"], observation.coordinates, within=within):
                group["centroid"] = recentre(
                    group["centroid"], int(group["count"]), observation.coordinates
                )
                group["count"] = int(group["count"]) + 1
                group["members"].append(observation)  # type: ignore[union-attr]
                group["last_seen"] = observation.observed_at
                group["dwell_seconds"] = int(group["dwell_seconds"]) + int(
                    observation.dwell_seconds or 0
                )
                placed = True
                break
        if not placed:
            groups.append(
                {
                    "centroid": observation.coordinates,
                    "count": 1,
                    "members": [observation],
                    "first_seen": observation.observed_at,
                    "last_seen": observation.observed_at,
                    "dwell_seconds": int(observation.dwell_seconds or 0),
                }
            )
    for group in groups:
        group["distinct_days"] = distinct_days(group["members"])  # type: ignore[arg-type]
    return groups


def absorb(candidate: PlaceCandidate, observation: PresenceObservation) -> PlaceCandidate:
    """Fold one more sighting into an existing cluster."""
    candidate.centroid = recentre(
        candidate.centroid, candidate.observation_count, observation.coordinates
    )
    candidate.observation_count += 1
    candidate.total_dwell_seconds += int(observation.dwell_seconds or 0)
    if observation.observed_at > candidate.last_seen:
        candidate.last_seen = observation.observed_at
    if observation.observed_at < candidate.first_seen:
        candidate.first_seen = observation.observed_at
    candidate.touch()
    return candidate
