"""Decision gate — create a suggestion only if worth disturbing the user.

Ruthless: if a real personal assistant would not speak up, reject.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from proactive_engine.models import SuggestionCandidate
from proactive_engine.types import STUB_ONLY_TYPES


@dataclass
class GateContext:
    now: datetime
    active_count: int = 0
    recent_same_dedupe: int = 0
    recent_emitted_1h: int = 0
    quiet_hours: bool = False
    in_study_session: bool = False
    in_calendar_event: bool = False
    likely_driving: bool = False
    likely_sleep: bool = False
    learning_dismiss_rate: float = 0.0
    max_active: int = 8
    min_score: float = 0.42
    min_confidence: float = 0.45


@dataclass
class GateResult:
    accept: bool
    reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _hour_local(now: datetime, tz_offset_hours: int = 2) -> int:
    # Europe/Rome approx for heuristics without pytz dependency in gate
    local = now + timedelta(hours=tz_offset_hours)
    return local.hour


def detect_quiet_hours(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    h = _hour_local(now)
    return h >= 22 or h < 7


def detect_likely_sleep(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    h = _hour_local(now)
    return h >= 23 or h < 6


def build_gate_context_from_evidence(
    *,
    now: datetime,
    active_count: int,
    recent_same_dedupe: int,
    recent_emitted_1h: int,
    calendar_events: Optional[List[Dict[str, Any]]] = None,
    study_sessions: Optional[List[Dict[str, Any]]] = None,
    learning_dismiss_rate: float = 0.0,
) -> GateContext:
    in_event = False
    likely_driving = False
    for ev in calendar_events or []:
        try:
            start = datetime.fromisoformat(str(ev.get("starts_at") or ev.get("start_at") or "").replace("Z", "+00:00"))
            end_raw = ev.get("ends_at") or ev.get("end_at")
            end = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00")) if end_raw else start + timedelta(hours=1)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if start <= now <= end:
                in_event = True
                title = (ev.get("title") or ev.get("label") or "").lower()
                if any(k in title for k in ("guida", "driving", "autostrada", "in viaggio")):
                    likely_driving = True
        except Exception:
            continue

    in_study = False
    for s in study_sessions or []:
        if s.get("status") == "in_progress":
            in_study = True
            break
        try:
            if s.get("status") not in ("planned", "in_progress"):
                continue
            start = datetime.fromisoformat(str(s.get("starts_at")).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(s.get("ends_at")).replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if start <= now <= end:
                in_study = True
        except Exception:
            continue

    return GateContext(
        now=now,
        active_count=active_count,
        recent_same_dedupe=recent_same_dedupe,
        recent_emitted_1h=recent_emitted_1h,
        quiet_hours=detect_quiet_hours(now),
        in_study_session=in_study,
        in_calendar_event=in_event,
        likely_driving=likely_driving,
        likely_sleep=detect_likely_sleep(now),
        learning_dismiss_rate=learning_dismiss_rate,
    )


def would_assistant_speak(
    cand: SuggestionCandidate,
    *,
    score: float,
    confidence: float,
    ctx: GateContext,
) -> GateResult:
    notes: List[str] = []
    reasons: List[str] = []

    # Hard: stub types never invent
    if cand.type in STUB_ONLY_TYPES:
        reasons.append("stub_type_no_emit")
        return GateResult(False, reasons=reasons, notes=["Predisposed type — no invented content"])

    if not (cand.title or "").strip() or not (cand.reason or "").strip():
        reasons.append("missing_title_or_reason")
        return GateResult(False, reasons=reasons)

    if not cand.dedupe_key:
        reasons.append("missing_dedupe_key")
        return GateResult(False, reasons=reasons)

    # Evidence required for real generators
    if not cand.evidence and cand.type in ("study", "travel", "calendar", "documents"):
        reasons.append("no_grounded_evidence")
        return GateResult(False, reasons=reasons)

    if confidence < ctx.min_confidence:
        reasons.append("confidence_below_floor")
        return GateResult(False, reasons=reasons, notes=[f"confidence={confidence:.2f}"])

    if score < ctx.min_score:
        reasons.append("score_below_floor")
        return GateResult(False, reasons=reasons, notes=[f"score={score:.2f}"])

    if ctx.active_count >= ctx.max_active:
        reasons.append("active_cap")
        return GateResult(False, reasons=reasons)

    if ctx.recent_same_dedupe > 0:
        reasons.append("dedupe_recent")
        return GateResult(False, reasons=reasons, notes=["Same goal/source/action window"])

    # Anti-spam: max ~3 emissions per hour unless critical urgency
    if ctx.recent_emitted_1h >= 3 and float(cand.urgency_hint or 0) < 0.85:
        reasons.append("rate_limit_1h")
        return GateResult(False, reasons=reasons)

    # During study / events / driving — only high urgency interruptions
    if ctx.in_study_session and float(cand.urgency_hint or 0) < 0.8 and cand.type != "study":
        reasons.append("during_study_block")
        return GateResult(False, reasons=reasons)

    if ctx.likely_driving:
        reasons.append("during_driving")
        return GateResult(False, reasons=reasons, notes=["Defer — user likely driving"])

    if ctx.in_calendar_event and float(cand.urgency_hint or 0) < 0.75:
        reasons.append("during_event")
        return GateResult(False, reasons=reasons)

    # Quiet / sleep: still CREATE for Home — notification_policy defers push/batch.
    if ctx.quiet_hours or ctx.likely_sleep:
        notes.append("quiet_or_sleep: home_ok_push_deferred")

    # User often dismisses this type/source
    if ctx.learning_dismiss_rate >= 0.7 and score < 0.72:
        reasons.append("learning_suppress")
        return GateResult(False, reasons=reasons, notes=["User dismisses this pattern often"])

    # Assistant test: vague generic noise
    title_l = cand.title.lower()
    if cand.type == "generic" and score < 0.55:
        reasons.append("generic_low_value")
        return GateResult(False, reasons=reasons)
    if any(p in title_l for p in ("ricordati di respirare", "hai tempo libero", "motivational")):
        reasons.append("assistant_would_not_speak")
        return GateResult(False, reasons=reasons)

    notes.append("would_assistant_speak=yes")
    return GateResult(True, notes=notes)
