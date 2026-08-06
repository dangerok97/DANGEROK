"""Study generator — skipped sessions → recovery suggestion (grounded)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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


async def generate_study_candidates(
    db, user_id: str, *, now: Optional[datetime] = None,
) -> List[SuggestionCandidate]:
    now = now or datetime.now(timezone.utc)
    plans = await db.study_plans.find(
        {"user_id": user_id, "status": {"$in": ["active", "paused"]}},
        {"_id": 0},
    ).to_list(40)
    if not plans:
        return []

    goals = await db.goals.find(
        {"user_id": user_id, "status": {"$nin": ["cancelled", "archived", "merged"]}},
        {"_id": 0},
    ).to_list(80)
    goal_by_plan = {
        g.get("study_plan_id"): g for g in goals if g.get("study_plan_id")
    }

    out: List[SuggestionCandidate] = []
    win = window_label(now, 24)

    for plan in plans:
        plan_id = plan.get("id")
        sessions = await db.study_sessions.find(
            {"user_id": user_id, "plan_id": plan_id},
            {"_id": 0},
        ).to_list(200)
        skipped = [s for s in sessions if s.get("status") == "skipped"]
        if not skipped:
            continue

        # Recent skips matter more — at least one skip in last 7 days OR any skip with upcoming exam
        recent_skips = []
        for s in skipped:
            ts = _parse(s.get("updated_at") or s.get("starts_at"))
            if ts and (now - ts) <= timedelta(days=7):
                recent_skips.append(s)
        use_skips = recent_skips or skipped
        n = len(use_skips)
        if n < 1:
            continue

        exam_name = plan.get("exam_name") or plan.get("subject") or "esame"
        exam_dt = _parse(plan.get("exam_date"))
        goal = goal_by_plan.get(plan_id)
        goal_id = goal.get("id") if goal else None

        # Concrete helpful text — assistant-worthy
        if n == 1:
            title = f"Recupera la sessione saltata di {exam_name}"
            desc = (
                f"Hai saltato 1 sessione di studio per {exam_name}. "
                "Posso inserire una sessione di recupero nel prossimo slot libero."
            )
        else:
            title = f"Recupera {n} sessioni saltate — {exam_name}"
            desc = (
                f"Hai saltato {n} sessioni per {exam_name}. "
                "Un piano di recupero breve riduce il rischio di arrivare indietro all'esame."
            )

        urgency = 0.55 + min(0.3, 0.08 * n)
        if exam_dt:
            days = (exam_dt - now).total_seconds() / 86400.0
            if days <= 7:
                urgency = max(urgency, 0.85)
            elif days <= 14:
                urgency = max(urgency, 0.7)

        entity = use_skips[-1].get("id") or plan_id
        out.append(SuggestionCandidate(
            title=title,
            description=desc,
            reason=f"{n} sessioni saltate sul piano {exam_name}",
            type="study",
            source="study_plan",
            goal_id=goal_id,
            project_id=plan.get("project_id") or (goal.get("project_id") if goal else None),
            study_plan_id=plan_id,
            action=SuggestionAction(
                kind="recover_session",
                label="Crea sessione di recupero",
                route=f"/study-plan/{plan_id}",
                params={
                    "plan_id": plan_id,
                    "skipped_count": n,
                    "skipped_session_ids": [s.get("id") for s in use_skips if s.get("id")],
                },
            ),
            dedupe_key=make_dedupe_key(
                suggestion_type="study",
                source="study_plan",
                goal_id=goal_id,
                action_kind="recover_session",
                entity_id=plan_id,
                window=win,
            ),
            expires_at=(now + timedelta(hours=48)).isoformat(),
            importance_hint=0.72,
            urgency_hint=urgency,
            confidence=0.88,
            evidence={
                "plan_id": plan_id,
                "skipped_count": n,
                "exam_date": plan.get("exam_date"),
                "deadline": plan.get("exam_date"),
                "skipped_session_ids": [s.get("id") for s in use_skips if s.get("id")],
            },
            meta={"exam_name": exam_name},
        ))
    return out
