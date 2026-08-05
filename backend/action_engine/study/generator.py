"""Deterministic study plan generator. Gemini optional for topic split only."""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from action_engine.study.models import (
    DEFAULT_TZ,
    Intensity,
    StudySessionItem,
    TimeRange,
    _uid,
    now_iso,
)

logger = logging.getLogger("ora.action_engine.study.generator")

_INTENSITY_FACTOR = {
    "light": 0.7,
    "distributed": 1.0,
    "intensive": 1.35,
    "custom": 1.0,
}


def _tz(name: str = DEFAULT_TZ) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def _parse_exam_local(exam_date_iso: str, tz_name: str) -> date:
    dt = datetime.fromisoformat(exam_date_iso.replace("Z", "+00:00"))
    return dt.astimezone(_tz(tz_name)).date()


def _default_ranges() -> List[TimeRange]:
    return [TimeRange(start="18:00", end="20:00")]


def _session_types_for_tools(tools: Sequence[str], idx: int, total: int) -> str:
    tools = list(tools) or ["study", "review"]
    if idx == total - 1 and "review" in tools:
        return "review"
    if idx == total - 2 and "interrogami" in tools:
        return "interrogami"
    if idx % 3 == 2 and "flashcards" in tools:
        return "flashcards"
    if "exam_questions" in tools and idx == max(0, total - 3):
        return "exam_questions"
    return "study" if "study" in tools else tools[0]


async def maybe_split_topics(
    *,
    subject: str,
    exam_name: str,
    document_titles: Optional[List[str]] = None,
) -> List[str]:
    """Optional Gemini topic split — deterministic fallback always works."""
    base = [t for t in (document_titles or []) if t][:8]
    if not base:
        base = [
            f"Fondamenti di {subject or exam_name}",
            f"Approfondimento {subject or exam_name}",
            "Esercizi e casi",
            "Ripasso generale",
        ]

    if not os.environ.get("EMERGENT_LLM_KEY") and not os.environ.get("GEMINI_API_KEY"):
        return base

    try:
        # Best-effort optional LLM — never required for plan validity
        from llm.client import complete_json  # type: ignore
        prompt = (
            f"Dividi lo studio di «{exam_name}» (materia: {subject}) "
            f"in 4-8 argomenti brevi in italiano. Materiali: {', '.join(base[:6])}. "
            'Rispondi JSON {{"topics": ["..."]}}'
        )
        data = await complete_json(prompt, max_tokens=400)
        topics = data.get("topics") if isinstance(data, dict) else None
        if isinstance(topics, list) and topics:
            return [str(t)[:80] for t in topics if t][:10]
    except Exception as e:
        logger.info("gemini topic split skipped: %s", type(e).__name__)
    return base


def generate_plan_sessions(
    *,
    user_id: str,
    plan_id: str,
    exam_name: str,
    subject: Optional[str],
    exam_date_iso: str,
    daily_minutes: int,
    available_days: List[int],
    preferred_ranges: Optional[List[TimeRange]] = None,
    intensity: Intensity = "distributed",
    tools: Optional[List[str]] = None,
    document_ids: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    tz_name: str = DEFAULT_TZ,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Pure deterministic schedule builder.

    Returns {ok, sessions, preview, error?, message?}
    """
    ranges = preferred_ranges or _default_ranges()
    days = available_days if available_days is not None else [0, 1, 2, 3, 4]
    if not days:
        return {
            "ok": False,
            "error": "no_days",
            "message": "Seleziona almeno un giorno disponibile.",
            "sessions": [],
            "preview": {},
        }
    if daily_minutes < 15:
        return {
            "ok": False,
            "error": "too_short",
            "message": "Serve almeno 15 minuti al giorno.",
            "sessions": [],
            "preview": {},
        }

    try:
        exam_local = _parse_exam_local(exam_date_iso, tz_name)
    except Exception:
        return {
            "ok": False,
            "error": "invalid_exam_date",
            "message": "Data esame non valida.",
            "sessions": [],
            "preview": {},
        }

    now_utc = now or datetime.now(timezone.utc)
    today_local = now_utc.astimezone(_tz(tz_name)).date()
    if exam_local <= today_local:
        return {
            "ok": False,
            "error": "exam_too_soon",
            "message": "L'esame è troppo vicino o già passato per costruire un piano.",
            "sessions": [],
            "preview": {},
        }

    days_until = (exam_local - today_local).days
    factor = _INTENSITY_FACTOR.get(intensity, 1.0)
    # Target study-days before exam
    usable = [d for d in range(days_until) if (today_local + timedelta(days=d)).weekday() in days]
    if not usable:
        return {
            "ok": False,
            "error": "impossible_schedule",
            "message": "Nei giorni selezionati non ci sono slot prima dell'esame. Cambia giorni o data.",
            "sessions": [],
            "preview": {},
        }

    # Cap sessions by intensity & horizon
    max_sessions = min(len(usable), 24)
    if intensity == "light":
        target = max(2, min(max_sessions, max(2, days_until // 4)))
    elif intensity == "intensive":
        target = max(3, min(max_sessions, len(usable)))
    elif intensity == "custom":
        target = max(2, min(max_sessions, max(3, int(len(usable) * 0.6))))
    else:  # distributed
        target = max(3, min(max_sessions, max(3, days_until // 3)))

    target = max(2, min(target, len(usable)))
    # Pick evenly spaced day offsets from usable
    if target == 1:
        chosen = [usable[0]]
    else:
        chosen = []
        for i in range(target):
            idx = int(round(i * (len(usable) - 1) / (target - 1)))
            chosen.append(usable[idx])
        # unique preserve order
        seen = set()
        uniq = []
        for c in chosen:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        chosen = uniq

    # Intensive packs more near the end
    if intensity == "intensive" and len(usable) >= target:
        chosen = usable[-target:]

    topic_list = topics or [f"{subject or exam_name}"]
    tools_l = list(tools or ["study", "review"])
    duration = max(15, int(daily_minutes * factor / max(factor, 1.0)))
    # Keep duration close to daily_minutes (intensity affects count more than length)
    duration = max(15, min(180, daily_minutes))

    sessions: List[StudySessionItem] = []
    rng = ranges[0]
    try:
        sh, sm = [int(x) for x in rng.start.split(":")[:2]]
    except Exception:
        sh, sm = 18, 0

    for i, day_off in enumerate(chosen):
        local_day = today_local + timedelta(days=day_off)
        start_local = datetime(local_day.year, local_day.month, local_day.day, sh, sm, tzinfo=_tz(tz_name))
        end_local = start_local + timedelta(minutes=duration)
        # Don't schedule after exam morning
        if start_local.date() >= exam_local:
            start_local = datetime(
                exam_local.year, exam_local.month, exam_local.day, sh, sm, tzinfo=_tz(tz_name),
            ) - timedelta(days=1)
            end_local = start_local + timedelta(minutes=duration)
        stype = _session_types_for_tools(tools_l, i, len(chosen))
        topic = topic_list[i % len(topic_list)]
        label = {
            "study": "Studio",
            "review": "Ripasso",
            "flashcards": "Flashcard",
            "interrogami": "Interrogami",
            "exam_questions": "Domande d'esame",
        }.get(stype, "Studio")
        sessions.append(StudySessionItem(
            id=_uid("ssn"),
            plan_id=plan_id,
            user_id=user_id,
            session_type=stype,  # type: ignore[arg-type]
            status="planned",
            title=f"{label}: {exam_name}",
            topic=topic,
            starts_at=start_local.astimezone(timezone.utc).isoformat(),
            ends_at=end_local.astimezone(timezone.utc).isoformat(),
            duration_minutes=duration,
            document_ids=list(document_ids or []),
            meta={"index": i + 1, "intensity": intensity},
        ))

    if not sessions:
        return {
            "ok": False,
            "error": "impossible_schedule",
            "message": "Impossibile generare sessioni con questi vincoli.",
            "sessions": [],
            "preview": {},
        }

    load_hours = round(sum(s.duration_minutes for s in sessions) / 60.0, 1)
    preview = {
        "exam_name": exam_name,
        "subject": subject,
        "exam_date": exam_date_iso,
        "exam_label": f"{exam_local.day}/{exam_local.month}/{exam_local.year}",
        "intensity": intensity,
        "daily_minutes": daily_minutes,
        "available_days": days,
        "preferred_ranges": [r.model_dump() for r in ranges],
        "session_count": len(sessions),
        "total_hours": load_hours,
        "document_ids": list(document_ids or []),
        "tools": tools_l,
        "topics": topic_list,
        "sessions_summary": [
            {
                "id": s.id,
                "title": s.title,
                "type": s.session_type,
                "starts_at": s.starts_at,
                "duration_minutes": s.duration_minutes,
                "topic": s.topic,
            }
            for s in sessions
        ],
        "generated_at": now_iso(),
        "generator": "deterministic_v1",
    }
    return {"ok": True, "sessions": sessions, "preview": preview, "topics": topic_list}
