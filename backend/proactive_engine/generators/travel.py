"""Travel generator — N days to departure → packing/prep (grounded)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from proactive_engine.dedupe import make_dedupe_key, window_label
from proactive_engine.models import SuggestionAction, SuggestionCandidate


def _parse(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def generate_travel_candidates(
    db, user_id: str, *, now: Optional[datetime] = None,
) -> List[SuggestionCandidate]:
    now = now or datetime.now(timezone.utc)
    projects = await db.travel_projects.find(
        {"user_id": user_id, "status": {"$in": ["active", "confirmed", "planning"]}},
        {"_id": 0},
    ).to_list(40)
    if not projects:
        # also accept common statuses from AE
        projects = await db.travel_projects.find(
            {"user_id": user_id, "status": {"$nin": ["cancelled", "archived", "draft"]}},
            {"_id": 0},
        ).to_list(40)

    goals = await db.goals.find(
        {"user_id": user_id, "goal_type": "travel", "status": {"$nin": ["cancelled", "archived", "merged"]}},
        {"_id": 0},
    ).to_list(80)
    goal_by_tp = {g.get("travel_project_id"): g for g in goals if g.get("travel_project_id")}

    out: List[SuggestionCandidate] = []
    win = window_label(now, 24)

    for tp in projects:
        if tp.get("status") in ("cancelled", "archived"):
            continue
        start = _parse(tp.get("start_date") or tp.get("period_start") or (tp.get("period") or {}).get("start"))
        if not start:
            continue
        days = (start.date() - now.date()).days
        # Speak up at 7, 3, 1 days — not months away noise
        if days < 0 or days > 7:
            continue

        prep = tp.get("prep_items") or tp.get("prep") or []
        incomplete = []
        for p in prep:
            if isinstance(p, dict):
                if not p.get("done") and not p.get("completed"):
                    incomplete.append(p.get("label") or p.get("id") or "prep")
            elif isinstance(p, str):
                incomplete.append(p)

        # Without prep list still suggest packing if departure soon — grounded on trip itself
        dest = tp.get("destination") or tp.get("title") or "viaggio"
        goal = goal_by_tp.get(tp.get("id"))
        goal_id = goal.get("id") if goal else None

        if days <= 1:
            title = f"Partenza imminente per {dest}: prepara valigia e documenti"
            urgency = 0.9
        elif days <= 3:
            title = f"Tra {days} giorni parti per {dest}: checklist prep"
            urgency = 0.75
        else:
            title = f"Tra {days} giorni: {dest} — inizia a preparare"
            urgency = 0.55

        if incomplete:
            desc = (
                f"Mancano ancora {len(incomplete)} preparativi"
                + (f" (es. {incomplete[0]})" if incomplete else "")
                + ". Meglio sistemarli prima della partenza."
            )
            importance = 0.78
        else:
            desc = (
                f"Il viaggio a {dest} è tra {days} giorni. "
                "Controlla documenti, bagaglio e dettagli partenza."
            )
            importance = 0.65

        out.append(SuggestionCandidate(
            title=title,
            description=desc,
            reason=f"Partenza tra {days} giorni — prep viaggio",
            type="travel",
            source="travel_project",
            goal_id=goal_id,
            project_id=tp.get("project_id") or (goal.get("project_id") if goal else None),
            travel_project_id=tp.get("id"),
            action=SuggestionAction(
                kind="prep",
                label="Apri prep viaggio",
                route=f"/travel-project/{tp.get('id')}",
                params={"travel_project_id": tp.get("id"), "days_to_departure": days},
            ),
            dedupe_key=make_dedupe_key(
                suggestion_type="travel",
                source="travel_project",
                goal_id=goal_id,
                action_kind="prep",
                entity_id=tp.get("id"),
                window=win,
            ),
            expires_at=(start + timedelta(hours=6)).isoformat(),
            importance_hint=importance,
            urgency_hint=urgency,
            confidence=0.86,
            evidence={
                "travel_project_id": tp.get("id"),
                "departure_at": start.isoformat(),
                "deadline": start.isoformat(),
                "days_to_departure": days,
                "incomplete_prep": incomplete[:8],
            },
            meta={"destination": dest},
        ))
    return out
