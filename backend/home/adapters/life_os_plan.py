"""Home adapter for generic Life OS plans — canonical execution, no StudyFlow."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

from home.models import ConnectionWarning, HomeItem
from home.temporal import (
    TEMPORAL_ACTIVE,
    TEMPORAL_EXPIRED_STALE,
    TEMPORAL_UPCOMING,
    classify_temporal_state,
)

from ._util import now_iso, stable_id


async def load_life_os_plans(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    items: List[HomeItem] = []
    warnings: List[ConnectionWarning] = []
    try:
        plans = (
            await db.life_os_plans.find(
                {"user_id": user_id, "status": {"$in": ["active", "paused"]}},
                {"_id": 0},
            )
            .sort("updated_at", -1)
            .limit(15)
            .to_list(15)
        )
    except Exception:
        return items, warnings

    today = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc)
    for p in plans:
        plan_id = p.get("id") or ""
        summary = p.get("summary") or "Piano attivo"
        # Only an exact day reaches `due_at`, because everything downstream —
        # ranking, urgency, the countdown a person reads — treats it as a
        # deadline. A period keeps its own words instead: "quest'anno" is
        # shown as "quest'anno", not as a date six months past the year they
        # named.
        target = (p.get("target_date") or "")[:10] or None
        when_said = str(((p.get("target") or {}).get("as_said") or ""))[:120]
        when_precision = str(((p.get("target") or {}).get("precision") or "none"))
        plan_items = p.get("items") or []
        next_it = None
        today_n = 0
        open_n = 0
        for it in sorted(plan_items, key=lambda x: (x.get("order") or 0, x.get("due_date") or "")):
            st = it.get("status") or "not_started"
            if st in ("not_started", "in_progress"):
                open_n += 1
                if not next_it:
                    next_it = it
                if (it.get("due_date") or "")[:10] == today:
                    today_n += 1
        done = sum(1 for it in plan_items if it.get("status") == "completed")
        total = len(plan_items)
        progress = round(done / total, 3) if total else 0.0
        countdown = None
        if target:
            try:
                countdown = (
                    datetime.fromisoformat(target).date()
                    - datetime.now(timezone.utc).date()
                ).days
            except Exception:
                countdown = None

        actionable_now = bool(next_it) and p.get("status") == "active"
        has_open = open_n > 0
        due_for_rank = (next_it or {}).get("due_date") or target
        temporal = classify_temporal_state(
            due_at=due_for_rank or target,
            now=now,
            actionable_now=actionable_now,
            has_open_work=has_open,
            recovery_debt=False,
            status=str(p.get("status") or "active"),
            past_due_is_stale=True,
        )
        # Future target with open work stays ACTIVE/UPCOMING even if next due is today
        if actionable_now and temporal == TEMPORAL_EXPIRED_STALE:
            temporal = TEMPORAL_ACTIVE
        if actionable_now and countdown is not None and countdown > 3:
            # Prefer ACTIVE when there is work today, else UPCOMING
            temporal = TEMPORAL_ACTIVE if today_n else TEMPORAL_UPCOMING

        desc_parts = []
        if countdown is not None:
            desc_parts.append(
                f"Scadenza tra {countdown}g" if countdown >= 0 else "Scadenza passata"
            )
        if next_it:
            desc_parts.append(next_it.get("title") or "Prossimo passo")
        if today_n:
            desc_parts.append(f"{today_n} oggi")
        if total:
            desc_parts.append(f"{done}/{total}")

        sess = p.get("conversation_session_id")
        route = f"/goal-workspace/{plan_id}"
        base_meta = {
            "goal_id": p.get("goal_id"),
            "life_os_plan_id": plan_id,
            "plan_shell": True,
            "canonical_execution": True,
            "ownership": "canonical",
            "actionable_now": actionable_now,
            "has_open_near_term": has_open,
            "temporal_state": temporal,
            "goal_target_date": target,
            "goal_target_said": when_said,
            "goal_target_precision": when_precision,
            "current_item_id": (next_it or {}).get("id"),
            "current_item_title": (next_it or {}).get("title"),
            "next_step": (next_it or {}).get("title"),
            "progress_ratio": progress,
            "session_today": today_n > 0,
            "route": route,
            "avoid_action_engine": True,
            "conversation_session_id": sess,
            "freshness": p.get("updated_at") or p.get("created_at"),
            "object_ids": list((p.get("meta") or {}).get("object_ids") or [])[:12],
        }

        if sess:
            items.append(
                HomeItem(
                    id=stable_id("life_os_resume", user_id, plan_id),
                    type="resume",
                    subtype="life_os_plan",
                    title=f"Continua: {summary}",
                    description=" · ".join(desc_parts) or "Riprendi il piano",
                    source_type="life_os_plan",
                    source_id=plan_id,
                    due_at=target,
                    status="open",
                    created_at=p.get("created_at") or now_iso(),
                    updated_at=p.get("updated_at") or now_iso(),
                    meta={
                        **base_meta,
                        "dedupe_key": f"life_os_plan:{plan_id}",
                        "resume_kind": "life_os_plan",
                        "why_now_factors": [
                            {
                                "code": "active_plan",
                                "label": "Piano attivo",
                                "weight": 0.85,
                            },
                            {
                                "code": "deadline",
                                "label": f"Tra {countdown}g",
                                "weight": 0.7,
                            }
                            if countdown is not None
                            else {"code": "plan", "label": "Piano", "weight": 0.5},
                        ],
                    },
                )
            )

        # Daily Focus shell — current step is the actionable unit
        focus_title = summary
        focus_desc = " · ".join(desc_parts) or (p.get("desired_outcome") or None)
        if next_it and (next_it.get("title") or "").strip():
            focus_desc = next_it.get("title")
            if countdown is not None and countdown >= 0:
                focus_desc = f"{next_it.get('title')} · tra {countdown}g"

        items.append(
            HomeItem(
                id=stable_id("life_os_plan", user_id, plan_id),
                type="activity",
                subtype="life_os_plan",
                title=focus_title,
                description=focus_desc,
                source_type="life_os_plan",
                source_id=plan_id,
                due_at=due_for_rank,
                start_at=(next_it or {}).get("due_date"),
                status="open",
                created_at=p.get("created_at") or now_iso(),
                updated_at=p.get("updated_at") or now_iso(),
                meta={
                    **base_meta,
                    "dedupe_key": f"life_os_focus:{plan_id}",
                    "why_now_factors": [
                        {
                            "code": "canonical_execution",
                            "label": "Piano Life OS",
                            "weight": 0.9,
                        },
                        {
                            "code": "today_items",
                            "label": f"{today_n} oggi",
                            "weight": 0.9,
                        }
                        if today_n
                        else {
                            "code": "next_step",
                            "label": "Prossimo passo",
                            "weight": 0.7,
                        },
                    ],
                },
            )
        )
    return items, warnings
