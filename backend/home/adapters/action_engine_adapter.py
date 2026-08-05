"""Surface Action Engine projects / next steps on Home."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

from home.actions_catalog import actions_for
from home.models import ConnectionWarning, HomeAction, HomeItem, ReasonFactor


async def load_action_engine_items(db, user_id: str) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    items: List[HomeItem] = []
    now = datetime.now(timezone.utc)

    sessions = await db.action_sessions.find(
        {"user_id": user_id, "status": "active"},
        {"_id": 0},
    ).to_list(20)
    for s in sessions:
        it = HomeItem(
            id=f"ae_session_{s['id']}",
            type="resume",
            subtype=s.get("flow"),
            title=f"Continua: {s.get('title') or 'guida ORA'}",
            description="Flusso guidato in corso",
            source_type="action_session",
            source_id=s["id"],
            priority="today",
            urgency="soon",
            status="open",
            reason_factors=[ReasonFactor(
                code="action_engine_resume", label="Guida in corso", weight=0.7,
            )],
            reason_summary="Hai una guida Action Engine da completare",
            meta={
                "dedupe_key": f"ae_session:{s['id']}",
                "flow": s.get("flow"),
                "goal_id": s.get("goal_id"),
            },
            created_at=s.get("created_at"),
            updated_at=s.get("updated_at"),
            actions=[
                HomeAction(
                    id="resume_ae",
                    label="Continua",
                    kind="resume",
                    route=f"/action/{s['id']}",
                    primary=True,
                ),
            ],
        )
        items.append(it)

    projects = await db.action_projects.find(
        {
            "user_id": user_id,
            "status": "active",
            "next_focus_hint": {"$exists": True, "$ne": None},
        },
        {"_id": 0},
    ).to_list(30)
    for p in projects:
        hint = p.get("next_focus_hint") or p.get("title")
        flow = p.get("flow") or "generic"
        item_type = {
            "study": "study",
            "event": "event",
            "travel": "travel",
            "medical": "visit",
            "admin": "bill",
        }.get(flow, "activity")
        it = HomeItem(
            id=f"ae_proj_{p['id']}",
            type=item_type,  # type: ignore[arg-type]
            subtype="action_project",
            title=hint,
            description=p.get("title"),
            source_type="action_project",
            source_id=p["id"],
            priority="today" if flow in ("study", "medical", "admin") else "this_week",
            urgency="upcoming",
            status="open",
            reason_factors=[ReasonFactor(
                code="action_engine_project",
                label="Piano Action Engine",
                weight=0.55,
            )],
            reason_summary="Prossimo passo dal flusso guidato ORA",
            meta={
                "dedupe_key": f"ae_proj:{p['id']}",
                "flow": flow,
                "project_id": p["id"],
                "goal_id": p.get("goal_id"),
            },
            created_at=p.get("created_at"),
            updated_at=p.get("updated_at") or now.isoformat(),
        )
        it.actions = actions_for(it)
        items.append(it)

    return items, []
