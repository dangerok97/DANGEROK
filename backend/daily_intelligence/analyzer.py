"""Pure functions that turn a list of canonical events into a DailySummary.

No I/O, no side effects, no LLM. Fully deterministic — given the same
input list you always get the same output.

Event input contract (`CanonicalEvent`):
    {
      "id": str,                # opaque, used for stability
      "title": Optional[str],
      "starts_at": Optional[datetime],
      "ends_at": Optional[datetime],
      "all_day": bool,
      "location": Optional[str],
      "status": str,            # "confirmed" | "tentative" | "cancelled"
      "source": str,            # "calendar_google" | "user" | ...
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .types import DAILY_SUMMARY_VERSION, DailySummary, EnergyLevel, TimeSlot


# ---------- knobs ----------
DAY_WINDOW_START = time(hour=8, minute=0)   # local time
DAY_WINDOW_END = time(hour=22, minute=0)
BACK_TO_BACK_GAP_MIN = 15                   # ≤ 15 min gap → considered back-to-back
BUSY_HIGH_MIN = 6 * 60                      # ≥ 6 h of events → busy day
BUSY_EXTREME_MIN = 9 * 60                   # ≥ 9 h → extreme
MANY_MEETINGS_MIN = 4                       # ≥ 4 meetings → many_meetings
MANY_TRAVEL_MIN = 3 * 60                    # ≥ 3 h travel → many_travel_hours
MANY_STUDY_MIN = 4 * 60
MANY_WORK_MIN = 6 * 60
FREE_MORNING_MIN = 3 * 60                   # ≥ 3 h free before 12:00 → free_morning
FREE_AFTERNOON_MIN = 3 * 60
LONG_LUNCH_MIN = 90                         # ≥ 90 min free between 12:00-14:30


# Deterministic Italian holidays (date-only, no religious calendar).
# Fixed-date-only. Easter is intentionally NOT auto-computed here to keep
# the layer deterministic and free of algorithmic ambiguity.
_ITALIAN_FIXED_HOLIDAYS = {
    (1, 1),    # Capodanno
    (1, 6),    # Epifania
    (4, 25),   # Festa della Liberazione
    (5, 1),    # Festa del Lavoro
    (6, 2),    # Festa della Repubblica
    (8, 15),   # Ferragosto
    (11, 1),   # Ognissanti
    (12, 8),   # Immacolata
    (12, 25),  # Natale
    (12, 26),  # Santo Stefano
}


# ---------- category detection ----------
_CATEGORY_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "meeting":   ("riunione", "meeting", "call", "sync", "standup", "1:1", "1-1"),
    "travel":    ("volo", "flight", "treno", "train", "viaggio", "trasferimento", "trasferta", "check-in", "boarding"),
    "study":     ("esame", "test", "prova", "studio", "study", "lezione", "corso", "class"),
    "work":      ("sprint", "review", "planning", "retrospective", "workshop", "lavoro"),
    "social":    ("cena", "pranzo", "aperitivo", "dinner", "lunch", "brunch"),
    "medical":   ("dentista", "medico", "visita", "doctor", "dentist"),
    "fitness":   ("palestra", "yoga", "gym", "corsa", "running", "run", "allenamento"),
    "vacation":  ("ferie", "vacanze", "vacation", "holiday", "pto"),
    "birthday":  ("compleanno", "birthday", "anniversario"),
}


def _detect_category(title: Optional[str]) -> str:
    if not title:
        return "personal"
    t = title.lower()
    # Ordered iteration keeps the mapping deterministic.
    for cat, kws in _CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                return cat
    return "personal"


# ---------- time helpers ----------
def _to_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return _to_aware_utc(dt).isoformat().replace("+00:00", "Z")


def _day_bounds(target_date: date, tz: timezone = timezone.utc) -> Tuple[datetime, datetime]:
    """Return [day_start, day_end) in the given tz, both aware."""
    start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def _clip(interval: Tuple[datetime, datetime], bounds: Tuple[datetime, datetime]) -> Optional[Tuple[datetime, datetime]]:
    s = max(interval[0], bounds[0])
    e = min(interval[1], bounds[1])
    if s >= e:
        return None
    return (s, e)


def _merge_intervals(intervals: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    if not intervals:
        return []
    sorted_i = sorted(intervals, key=lambda x: x[0])
    merged: List[Tuple[datetime, datetime]] = [sorted_i[0]]
    for s, e in sorted_i[1:]:
        prev_s, prev_e = merged[-1]
        if s <= prev_e:
            merged[-1] = (prev_s, max(prev_e, e))
        else:
            merged.append((s, e))
    return merged


def _invert_intervals(
    intervals: List[Tuple[datetime, datetime]],
    bounds: Tuple[datetime, datetime],
) -> List[Tuple[datetime, datetime]]:
    """Return the complement of `intervals` inside `bounds`."""
    if not intervals:
        return [bounds]
    free: List[Tuple[datetime, datetime]] = []
    cursor = bounds[0]
    for s, e in intervals:
        if s > cursor:
            free.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < bounds[1]:
        free.append((cursor, bounds[1]))
    return free


def _mins(interval: Tuple[datetime, datetime]) -> int:
    return int((interval[1] - interval[0]).total_seconds() // 60)


def _slot(interval: Tuple[datetime, datetime], kind: str, category: Optional[str] = None) -> Dict[str, Any]:
    return TimeSlot(
        start=_iso(interval[0]),
        end=_iso(interval[1]),
        duration_min=_mins(interval),
        kind=kind,
        category=category,
    ).to_dict()


# ---------- main analyzer ----------
@dataclass
class _EventNorm:
    id: str
    title: Optional[str]
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    location: Optional[str]
    category: str
    source: str


def _normalize_events(
    events: Iterable[Dict[str, Any]],
    *,
    day_start: datetime,
    day_end: datetime,
) -> List[_EventNorm]:
    """Filter, tz-normalize and clip events to the target day. Skip
    cancelled events entirely."""
    out: List[_EventNorm] = []
    for e in events or []:
        if not isinstance(e, dict):
            continue
        if (e.get("status") or "confirmed") == "cancelled":
            continue
        s_raw = e.get("starts_at")
        en_raw = e.get("ends_at")
        if not s_raw:
            continue
        try:
            s = _to_aware_utc(s_raw if isinstance(s_raw, datetime) else datetime.fromisoformat(str(s_raw).replace("Z", "+00:00")))
        except Exception:
            continue
        try:
            en = _to_aware_utc(en_raw if isinstance(en_raw, datetime) else datetime.fromisoformat(str(en_raw).replace("Z", "+00:00"))) if en_raw else s + timedelta(minutes=30)
        except Exception:
            en = s + timedelta(minutes=30)

        # Overlap with the day?
        if en <= day_start or s >= day_end:
            continue
        # Clip
        s = max(s, day_start)
        en = min(en, day_end)
        if s >= en:
            continue
        out.append(_EventNorm(
            id=str(e.get("id") or e.get("external_event_id") or ""),
            title=e.get("title"),
            starts_at=s,
            ends_at=en,
            all_day=bool(e.get("all_day")),
            location=e.get("location"),
            category=_detect_category(e.get("title")),
            source=e.get("source") or "calendar_google",
        ))
    # deterministic order (by start, then id)
    out.sort(key=lambda x: (x.starts_at, x.id))
    return out


def _confidence_from_counts(total_events: int, calendar_sync_hint: bool) -> str:
    """Deterministic confidence classifier."""
    if total_events == 0:
        return "low" if not calendar_sync_hint else "medium"
    if total_events >= 3:
        return "high"
    return "medium"


def analyze_day(
    *,
    target_date: date,
    events: List[Dict[str, Any]],
    tz_name: str = "UTC",
    calendar_sync_hint: bool = False,
) -> DailySummary:
    """Pure function — one input, one output. No I/O.

    `tz_name` is used ONLY as a label on the output; input datetimes are
    expected in aware ISO-8601 (or UTC-naive). Local day bucketing is
    done in UTC in this iteration (avoids a mandatory `zoneinfo` dep).
    """
    day_start, day_end = _day_bounds(target_date)
    # Focused "day window" for free-slot detection (default 08:00-22:00 UTC)
    window_start = day_start.replace(hour=DAY_WINDOW_START.hour, minute=DAY_WINDOW_START.minute)
    window_end = day_start.replace(hour=DAY_WINDOW_END.hour, minute=DAY_WINDOW_END.minute)

    normalized = _normalize_events(events, day_start=day_start, day_end=day_end)

    total_events = len(normalized)
    all_day_events = sum(1 for e in normalized if e.all_day)
    is_weekend = target_date.weekday() >= 5
    is_holiday = (target_date.month, target_date.day) in _ITALIAN_FIXED_HOLIDAYS
    is_vacation_day = any(e.category == "vacation" and e.all_day for e in normalized)

    # Busy intervals (merged), excluding all-day events from time bookkeeping
    timed_events = [e for e in normalized if not e.all_day]
    busy_intervals = _merge_intervals([(e.starts_at, e.ends_at) for e in timed_events])

    busy_minutes = sum(_mins(iv) for iv in busy_intervals)
    total_window_min = _mins((window_start, window_end))
    # Free slots limited to the day window
    busy_in_window = [iv for iv in (
        _clip(iv, (window_start, window_end)) for iv in busy_intervals
    ) if iv]
    free_intervals = _invert_intervals(busy_in_window, (window_start, window_end))
    free_minutes = sum(_mins(iv) for iv in free_intervals)

    # By-category minutes
    by_category: Dict[str, int] = {}
    for e in timed_events:
        by_category[e.category] = by_category.get(e.category, 0) + _mins((e.starts_at, e.ends_at))

    # Consecutive (back-to-back) count + total break time between events
    consecutive_events = 0
    total_break_minutes = 0
    sorted_evs = sorted(timed_events, key=lambda x: x.starts_at)
    for i in range(1, len(sorted_evs)):
        prev = sorted_evs[i - 1]
        cur = sorted_evs[i]
        gap = int((cur.starts_at - prev.ends_at).total_seconds() // 60)
        if gap < 0:
            # overlap
            consecutive_events += 1
        elif gap <= BACK_TO_BACK_GAP_MIN:
            consecutive_events += 1
        else:
            total_break_minutes += gap

    # Signals / warnings / opportunities — deterministic rules
    signals: List[str] = []
    warnings: List[str] = []
    opportunities: List[str] = []

    if total_events == 0:
        signals.append("empty_day")
    if is_weekend:
        signals.append("weekend")
    if is_holiday:
        signals.append("holiday")
    if is_vacation_day:
        signals.append("vacation")

    meeting_count = sum(1 for e in timed_events if e.category == "meeting")
    travel_min = by_category.get("travel", 0)
    study_min = by_category.get("study", 0)
    work_min = by_category.get("work", 0) + by_category.get("meeting", 0)

    if meeting_count >= MANY_MEETINGS_MIN:
        signals.append("many_meetings")
    if travel_min >= MANY_TRAVEL_MIN:
        signals.append("many_travel_hours")
    if study_min >= MANY_STUDY_MIN:
        signals.append("many_study_hours")
    if work_min >= MANY_WORK_MIN:
        signals.append("many_work_hours")
    if busy_minutes >= BUSY_EXTREME_MIN:
        warnings.append("very_busy_day")
        signals.append("stressful_day")
    elif busy_minutes >= BUSY_HIGH_MIN:
        signals.append("busy_day")
    if total_events > 0 and consecutive_events >= 3:
        warnings.append("back_to_back_marathon")
        if "stressful_day" not in signals:
            signals.append("stressful_day")
    if total_events > 0 and total_break_minutes < 30 and busy_minutes >= 3 * 60:
        warnings.append("no_break")

    if total_events == 0 and not is_weekend and not is_holiday:
        signals.append("relaxed_day")
    if total_events == 0 or busy_minutes <= 90:
        if not is_weekend and not is_holiday and not is_vacation_day:
            signals.append("light_day")

    # Opportunities — find free-window slices
    def _free_in_range(start_h: int, end_h: int) -> int:
        rng_start = day_start.replace(hour=start_h, minute=0)
        rng_end = day_start.replace(hour=end_h, minute=0)
        clipped_busy = [iv for iv in (
            _clip(iv, (rng_start, rng_end)) for iv in busy_intervals
        ) if iv]
        free = _invert_intervals(clipped_busy, (rng_start, rng_end))
        return sum(_mins(iv) for iv in free)

    if _free_in_range(8, 12) >= FREE_MORNING_MIN:
        opportunities.append("free_morning")
    if _free_in_range(14, 18) >= FREE_AFTERNOON_MIN:
        opportunities.append("free_afternoon")
    if _free_in_range(18, 22) >= FREE_AFTERNOON_MIN:
        opportunities.append("free_evening")
    if _free_in_range(12, 14) + _free_in_range(13, 15) >= LONG_LUNCH_MIN:
        opportunities.append("long_lunch_available")

    # Slots serialization (sorted, deterministic)
    busy_slots = [_slot(iv, "busy") for iv in busy_intervals]
    # Attach the dominant category to each busy slot when possible.
    for slot_dict in busy_slots:
        s_dt = datetime.fromisoformat(slot_dict["start"].replace("Z", "+00:00"))
        e_dt = datetime.fromisoformat(slot_dict["end"].replace("Z", "+00:00"))
        cats = [
            e.category for e in timed_events
            if e.starts_at < e_dt and e.ends_at > s_dt
        ]
        if cats:
            slot_dict["category"] = max(set(cats), key=cats.count)
    free_slots = [_slot(iv, "free") for iv in free_intervals]

    # Score (0..100) — 100 means calm, 0 crushed.
    # Deterministic weighted formula.
    load_ratio = min(busy_minutes / max(total_window_min, 1), 1.0)
    consec_penalty = min(consecutive_events * 8, 40)
    break_bonus = min(total_break_minutes // 15, 20)
    holiday_bonus = 15 if is_holiday or is_vacation_day else 0
    weekend_bonus = 10 if is_weekend else 0
    raw = 100 - int(load_ratio * 60) - consec_penalty + break_bonus + holiday_bonus + weekend_bonus
    score = max(0, min(100, raw))

    # Energy estimation (rules-only)
    energy_reasons: List[str] = []
    energy_score = 100
    energy_score -= int(load_ratio * 50)
    if consecutive_events >= 3:
        energy_score -= 20
        energy_reasons.append("back_to_back_marathon")
    if travel_min >= MANY_TRAVEL_MIN:
        energy_score -= 15
        energy_reasons.append("many_travel_hours")
    if meeting_count >= MANY_MEETINGS_MIN:
        energy_score -= 10
        energy_reasons.append("many_meetings")
    if is_weekend or is_holiday or is_vacation_day:
        energy_score += 10
        energy_reasons.append("rest_day")
    energy_score = max(0, min(100, energy_score))
    if energy_score >= 66:
        energy_level = "high"
    elif energy_score >= 33:
        energy_level = "medium"
    else:
        energy_level = "low"
    energy = EnergyLevel(level=energy_level, score=energy_score, reasons=energy_reasons)

    # Confidence
    confidence = _confidence_from_counts(total_events, calendar_sync_hint)

    first_event_at = _iso(sorted_evs[0].starts_at) if sorted_evs else None
    last_event_at = _iso(sorted_evs[-1].ends_at) if sorted_evs else None

    return DailySummary(
        date=target_date.isoformat(),
        timezone=tz_name,
        generated_at=_iso(datetime.now(timezone.utc)),
        score=score,
        confidence=confidence,
        total_events=total_events,
        all_day_events=all_day_events,
        is_weekend=is_weekend,
        is_holiday=is_holiday,
        is_vacation_day=is_vacation_day,
        busy_minutes=busy_minutes,
        free_minutes=free_minutes,
        consecutive_events=consecutive_events,
        total_break_minutes=total_break_minutes,
        first_event_at=first_event_at,
        last_event_at=last_event_at,
        by_category=by_category,
        busy_slots=busy_slots,
        free_slots=free_slots,
        signals=sorted(set(signals)),
        warnings=sorted(set(warnings)),
        opportunities=sorted(set(opportunities)),
        energy_estimation=energy.to_dict(),
        source_counts={"input_events": len(events or []), "considered_events": total_events},
    )
