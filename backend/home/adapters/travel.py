"""Home V2 adapter — Travel Projects with phase evolution."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id

_PHASE_LABEL = {
    "upcoming": "Vacanza in programma",
    "days_until": "Vacanza in arrivo",
    "departure_day": "Partenza oggi",
    "during": "In vacanza",
    "welcome_back": "Bentornato",
}


def _phase(start: str | None, end: str | None) -> tuple[str, int | None]:
    today = datetime.now(timezone.utc).date()
    days_until = None
    try:
        sd = datetime.fromisoformat((start or "")[:10]).date() if start else None
        ed = datetime.fromisoformat((end or "")[:10]).date() if end else None
    except Exception:
        return "upcoming", None
    if not sd:
        return "upcoming", None
    days_until = (sd - today).days
    if ed and today > ed:
        return "welcome_back", days_until
    if ed and sd <= today <= ed:
        if today == sd:
            return "departure_day", 0
        return "during", days_until
    if today == sd:
        return "departure_day", 0
    if 0 < days_until <= 14:
        return "days_until", days_until
    return "upcoming", days_until


async def load_travel_state(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    items: List[HomeItem] = []
    warnings: List[ConnectionWarning] = []

    try:
        plans = await db.travel_projects.find(
            {
                "user_id": user_id,
                "status": {"$in": ["active", "paused", "awaiting_confirmation", "draft"]},
            },
            {"_id": 0},
        ).sort("updated_at", -1).limit(20).to_list(20)
    except Exception:
        plans = []

    for p in plans:
        status = p.get("status")
        dest = p.get("destination") or "viaggio"
        title = p.get("title") or f"Vacanza: {dest}"
        phase, days_until = _phase(p.get("start_date"), p.get("end_date"))
        phase_label = _PHASE_LABEL.get(phase, "Vacanza")

        if status in ("draft", "awaiting_confirmation") and p.get("action_session_id"):
            items.append(HomeItem(
                id=stable_id("travel_draft", user_id, p["id"]),
                type="resume",
                subtype="travel_project_draft",
                title=f"Continua viaggio: {dest}",
                description="Bozza salvata — riprendi le domande",
                source_type="action_session",
                source_id=p.get("action_session_id"),
                location=dest,
                due_at=p.get("start_date"),
                status="open",
                created_at=p.get("created_at") or now_iso(),
                updated_at=p.get("updated_at") or now_iso(),
                meta={
                    "dedupe_key": f"travel_project_draft:{p['id']}",
                    "travel_project_id": p["id"],
                    "resume_kind": "travel_project",
                    "phase": phase,
                    "why_now_factors": [
                        {"code": "draft_resume", "label": "Viaggio in bozza", "weight": 0.9},
                        {"code": "travel_countdown", "label": f"Partenza tra {days_until}g", "weight": 0.75}
                        if days_until is not None and days_until >= 0
                        else {"code": "travel", "label": "Viaggio", "weight": 0.5},
                    ],
                },
            ))
            continue

        desc_parts = [phase_label]
        if phase == "days_until" and days_until is not None:
            desc_parts = [f"Partenza tra {days_until} giorni"]
        elif phase == "departure_day":
            desc_parts = ["Partenza oggi"]
        elif phase == "during":
            desc_parts = [f"A {dest}"]
        elif phase == "welcome_back":
            desc_parts = ["Bentornato — chiudi il viaggio"]
        if p.get("transport"):
            desc_parts.append(str(p["transport"]))
        maps = p.get("maps") or {}
        if maps.get("duration_label"):
            desc_parts.append(maps["duration_label"])

        weight = 0.7
        if phase == "departure_day":
            weight = 0.98
        elif phase == "days_until" and days_until is not None and days_until <= 3:
            weight = 0.95
        elif phase == "during":
            weight = 0.85
        elif phase == "welcome_back":
            weight = 0.6

        items.append(HomeItem(
            id=stable_id("travel_project", user_id, p["id"]),
            type="travel",
            subtype="travel_project",
            title=title,
            description=" · ".join(desc_parts),
            source_type="travel_project",
            source_id=p["id"],
            location=dest,
            due_at=p.get("start_date"),
            status="open" if status == "active" else status,
            created_at=p.get("created_at") or now_iso(),
            updated_at=p.get("updated_at") or now_iso(),
            meta={
                "dedupe_key": f"travel_project:{p['id']}",
                "travel_project_id": p["id"],
                "phase": phase,
                "days_until": days_until,
                "transport": p.get("transport"),
                "maps": maps,
                "google_sync": p.get("google_sync") or {},
                "calendar_sync": p.get("calendar_sync"),
                "why_now_factors": [
                    {"code": f"travel_{phase}", "label": phase_label, "weight": weight},
                ],
            },
        ))

    return items, warnings
