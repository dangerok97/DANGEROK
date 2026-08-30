"""
Arithmetic over presence history. Sums, counts, medians — no conclusions.

    PRESENCE HISTORY BECOMES CONTEXT, NOT AUTOMATIC JUDGMENT.

Everything here answers a question that has a right answer: how many hours,
how many visits, how long between leaving one place and arriving at another,
what the middle value of those durations is. None of it decides whether any of
that matters, whether it constitutes a routine, or what it says about anybody.

The median rather than the mean, deliberately. Four commutes of 31, 32, 29 and
95 minutes have a mean of 47 — a number that describes none of the four
journeys and would be quoted back to somebody as "normally". The middle value
is 31.5, which is what actually happens on a normal day, and the 95 is still
reported as the maximum so nothing is hidden.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from places.models import PresenceSession


def _parse(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def overlap_seconds(
    session: PresenceSession, start: datetime, end: datetime
) -> int:
    """
    How much of a stay falls inside a window.

    A night at home that began yesterday and is still going counts towards
    today for the part that belongs to today. Clipping rather than including or
    excluding whole sessions is what makes "quanto sono stato a casa oggi"
    answerable without lying in either direction.
    """
    began = _parse(session.entered_at)
    if began is None:
        return 0
    # An open session runs up to now, never past it: the future is not time
    # somebody has already spent anywhere.
    finished = _parse(session.exited_at) or min(_now(), end)
    left = max(began, start)
    right = min(finished, end)
    return max(0, int((right - left).total_seconds()))


def time_at_place(
    sessions: List[PresenceSession], *, start: datetime, end: datetime
) -> Dict[str, Any]:
    """
    Total time, visits, and the shape of them, inside a window.

    `still_there` matters to how an answer is phrased: "sei stato a casa 6 ore"
    and "finora oggi sei stato a casa 6 ore" are different sentences, and only
    the history knows which one is true.
    """
    counted: List[Tuple[PresenceSession, int]] = []
    for session in sessions:
        seconds = overlap_seconds(session, start, end)
        if seconds > 0:
            counted.append((session, seconds))

    durations = [s for _, s in counted]
    total = sum(durations)
    open_now = [s for s, _ in counted if s.exited_at is None]

    arrivals = sorted(
        (_parse(s.entered_at) for s, _ in counted if _parse(s.entered_at)),
    )
    departures = sorted(
        (_parse(s.exited_at) for s, _ in counted if _parse(s.exited_at)),
    )

    return {
        "total_seconds": total,
        "visits": len(counted),
        "average_visit_seconds": int(total / len(counted)) if counted else 0,
        "longest_visit_seconds": max(durations) if durations else 0,
        "first_entered_at": arrivals[0].isoformat() if arrivals else None,
        "last_entered_at": arrivals[-1].isoformat() if arrivals else None,
        "last_exited_at": departures[-1].isoformat() if departures else None,
        "still_there": bool(open_now),
        "current_session_seconds": (
            open_now[0].duration_seconds() if open_now else None
        ),
    }


def transitions(
    sessions: List[PresenceSession], *, max_gap_seconds: int = 4 * 3600
) -> List[Dict[str, Any]]:
    """
    Journeys, inferred from leaving one place and arriving at the next.

    The gap between a departure and the following arrival is how long the trip
    took — observed, not routed: it includes the walk to the car and the coffee
    on the way, which is exactly why it is worth having and exactly why it is
    not a route duration.

    A gap longer than `max_gap_seconds` is not a journey between those two
    places. Somebody who left the office at six and reached the gym at eleven
    the next morning did something else in between, and pretending otherwise
    would put a five-hour "commute" into an average.
    """
    ordered = sorted(
        (s for s in sessions if s.exited_at),
        key=lambda s: s.exited_at or "",
    )
    arrivals = sorted(sessions, key=lambda s: s.entered_at)

    out: List[Dict[str, Any]] = []
    for left in ordered:
        left_at = _parse(left.exited_at)
        if left_at is None:
            continue
        for arrived in arrivals:
            if arrived.place_id == left.place_id:
                continue
            arrived_at = _parse(arrived.entered_at)
            if arrived_at is None or arrived_at < left_at:
                continue
            gap = int((arrived_at - left_at).total_seconds())
            if gap > max_gap_seconds:
                break
            out.append(
                {
                    "from_place_id": left.place_id,
                    "to_place_id": arrived.place_id,
                    "departed_at": left.exited_at,
                    "arrived_at": arrived.entered_at,
                    "duration_seconds": gap,
                }
            )
            break
    return out


def median(values: List[float]) -> Optional[float]:
    """The middle value. None for an empty sample, rather than zero."""
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile(values: List[float], p: float) -> Optional[float]:
    """Nearest-rank percentile. Small samples do not deserve interpolation."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(p / 100.0 * len(ordered) + 0.5)) - 1))
    return float(ordered[index])


def journey_stats(durations_seconds: List[int]) -> Dict[str, Any]:
    """
    What a sample of journeys actually looks like.

    The median is offered as the typical one and the extremes are kept beside
    it, because a range is the honest way to say "about half an hour, but once
    it took ninety minutes". Nothing here labels the ninety an outlier and
    discards it: a bad day is a real day, and whether it is worth mentioning is
    a judgement.
    """
    if not durations_seconds:
        return {"samples": 0}
    values = [float(v) for v in durations_seconds]
    def minutes(seconds: float) -> int:
        return int(round(seconds / 60))

    typical = median(values) or 0
    return {
        "samples": len(values),
        "typical_seconds": int(typical),
        "fastest_seconds": int(min(values)),
        "slowest_seconds": int(max(values)),
        "usual_range_seconds": [
            int(percentile(values, 25) or 0),
            int(percentile(values, 75) or 0),
        ],
        "last_seconds": int(values[-1]),
        # The same figures in the unit a person speaks, and a word saying what
        # "typical" is. A payload of raw seconds invites a sentence like "in
        # media 1.920 secondi", which is both unreadable and wrong: this is the
        # middle journey, not the average of them.
        "typical_minutes": minutes(typical),
        "fastest_minutes": minutes(min(values)),
        "slowest_minutes": minutes(max(values)),
        "usual_range_minutes": [
            minutes(percentile(values, 25) or 0),
            minutes(percentile(values, 75) or 0),
        ],
        "typical_means": "la durata mediana, non la media",
    }


def day_shape(sessions: List[PresenceSession]) -> List[Dict[str, Any]]:
    """
    The sequence of places, day by day, with the times.

    This is the evidence a pattern would be made of, handed over as a list of
    days rather than as a claim about weeks. Whether "Casa → Lavoro → Casa on
    nine of eleven weekdays" is a routine is not a question arithmetic can
    answer, and this function does not try.
    """
    by_day: Dict[str, List[PresenceSession]] = {}
    for session in sorted(sessions, key=lambda s: s.entered_at):
        began = _parse(session.entered_at)
        if began is None:
            continue
        by_day.setdefault(began.date().isoformat(), []).append(session)

    out: List[Dict[str, Any]] = []
    for day, items in sorted(by_day.items()):
        out.append(
            {
                "day": day,
                "weekday": datetime.fromisoformat(day).strftime("%A").lower(),
                "sequence": [
                    {
                        "place_id": s.place_id,
                        "entered_at": s.entered_at,
                        "exited_at": s.exited_at,
                        "duration_seconds": s.duration_seconds(),
                    }
                    for s in items
                ],
            }
        )
    return out


def window(name: str, *, now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """
    A named stretch of time, in the ordinary sense of the words.

    The names a person uses — today, this week, this month — resolved here so
    the arithmetic is not left to a model. Which window a question means is a
    reading of the question, and that part stays with the model.
    """
    reference = now or _now()
    end = reference
    key = (name or "").strip().lower()

    if key in {"today", "oggi"}:
        start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    elif key in {"yesterday", "ieri"}:
        start = (reference - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(days=1)
    elif key in {"this_week", "settimana", "questa_settimana"}:
        start = (reference - timedelta(days=reference.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif key in {"this_month", "mese", "questo_mese"}:
        start = reference.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    elif key.startswith("last_") and key.endswith("_days"):
        try:
            days = int(key.split("_")[1])
        except (IndexError, ValueError):
            days = 7
        start = reference - timedelta(days=max(1, min(365, days)))
    else:
        start = reference - timedelta(days=7)
    return start, end
