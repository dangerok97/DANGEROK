"""Goal-aware Home context — attach, dedupe, insights. No Goal UX surface."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from home.models import HomeItem, InsightItem, ReasonFactor

logger = logging.getLogger("ora.home.goal_context")


def _goal_engine_enabled() -> bool:
    try:
        from goal_engine.service import goal_engine_enabled
        return goal_engine_enabled()
    except Exception:
        return False


async def load_active_goals(db, user_id: str) -> List[Any]:
    """Load active-like Goals when flag ON; else empty (Home behavior unchanged)."""
    if not _goal_engine_enabled():
        return []
    try:
        from goal_engine.repository import GoalRepository
        return await GoalRepository(db).list_active(user_id, limit=80)
    except Exception:
        logger.warning("load_active_goals failed", exc_info=True)
        return []


class GoalIndex:
    """Lookup Goals by artifact / session / document links."""

    def __init__(self, goals: List[Any]):
        self.by_id: Dict[str, Any] = {}
        self.by_study_plan: Dict[str, Any] = {}
        self.by_travel: Dict[str, Any] = {}
        self.by_project: Dict[str, Any] = {}
        self.by_session: Dict[str, Any] = {}
        self.by_document: Dict[str, Any] = {}
        for g in goals:
            self.by_id[g.id] = g
            if g.study_plan_id:
                self.by_study_plan[g.study_plan_id] = g
            if g.travel_project_id:
                self.by_travel[g.travel_project_id] = g
            if g.project_id:
                self.by_project[g.project_id] = g
            if g.source_action_session_id:
                self.by_session[g.source_action_session_id] = g
            for doc_id in g.linked_documents or []:
                if doc_id and doc_id not in self.by_document:
                    self.by_document[doc_id] = g

    def match(self, item: HomeItem) -> Optional[Any]:
        meta = item.meta or {}
        gid = meta.get("goal_id") or item.goal_id
        if gid and gid in self.by_id:
            return self.by_id[gid]

        for key in (meta.get("study_plan_id"),):
            if key and key in self.by_study_plan:
                return self.by_study_plan[key]
        if item.source_type == "study_plan" and item.source_id in self.by_study_plan:
            return self.by_study_plan[item.source_id]

        for key in (meta.get("travel_project_id"),):
            if key and key in self.by_travel:
                return self.by_travel[key]
        if item.source_type == "travel_project" and item.source_id in self.by_travel:
            return self.by_travel[item.source_id]

        proj = meta.get("project_id")
        if proj and proj in self.by_project:
            return self.by_project[proj]
        if item.source_type == "action_project" and item.source_id in self.by_project:
            return self.by_project[item.source_id]

        if item.source_type == "action_session" and item.source_id in self.by_session:
            return self.by_session[item.source_id]

        doc_id = meta.get("document_id") or (
            item.source_id if item.source_type in ("study", "document", "quiz_session") else None
        )
        if doc_id and doc_id in self.by_document:
            return self.by_document[doc_id]

        return None


def _days_until(iso: Optional[str], now: datetime) -> Optional[int]:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00")[:10]).date()
        return (d - now.astimezone(timezone.utc).date()).days
    except Exception:
        return None


def _apply_goal_fields(item: HomeItem, goal: Any, now: datetime) -> HomeItem:
    it = item.model_copy(deep=True)
    pct = float(getattr(goal, "completion_percentage", None) or 0.0)
    prog = getattr(goal, "progress", None)
    label = getattr(prog, "label", None) if prog is not None else None
    target = getattr(goal, "target_date", None) or getattr(goal, "start_date", None)
    days = _days_until(target, now)
    next_action = getattr(goal, "next_action", None)
    # Prefer concrete next session title from study meta when Goal next_action empty
    if not next_action and (it.meta or {}).get("next_session"):
        ns = it.meta["next_session"]
        if isinstance(ns, dict):
            next_action = ns.get("title") or "Prossima sessione"

    it.goal_id = goal.id
    it.goal_title = goal.title
    it.goal_status = goal.status
    it.goal_progress = round(pct, 2)
    it.goal_progress_label = label
    it.goal_next_action = next_action
    it.meta = {
        **(it.meta or {}),
        "goal_id": goal.id,
        "goal_title": goal.title,
        "goal_status": goal.status,
        "goal_progress": round(pct, 2),
        "goal_progress_label": label,
        "goal_next_action": next_action,
        "goal_urgency": getattr(goal, "urgency", None),
        "goal_importance": getattr(goal, "importance", None),
        "goal_target_date": target,
        "goal_days_remaining": days,
        "goal_type": getattr(goal, "goal_type", None),
        # Shared dedupe key for goal-linked siblings
        "goal_dedupe_key": f"goal:{goal.id}",
    }
    return it


def attach_goal_context(
    items: List[HomeItem],
    goals: List[Any],
    *,
    now: Optional[datetime] = None,
) -> List[HomeItem]:
    """Stamp goal_* fields on related Home items. No-op when goals empty / flag off."""
    if not goals:
        return items
    now = now or datetime.now(timezone.utc)
    index = GoalIndex(goals)
    out: List[HomeItem] = []
    for item in items:
        g = index.match(item)
        if g:
            out.append(_apply_goal_fields(item, g, now))
        else:
            out.append(item)
    return out


def _concreteness(item: HomeItem) -> int:
    """Prefer next concrete action over bags / generic study docs."""
    meta = item.meta or {}
    subtype = item.subtype or ""
    if item.type == "resume":
        if subtype in ("study_plan_draft", "travel_project_draft"):
            return 95
        return 90
    if item.type == "study" and meta.get("next_session"):
        return 88
    if item.type == "travel" and meta.get("phase") in ("departure_day", "days_until", "during"):
        return 85
    if item.type == "study" and subtype == "study_plan":
        return 75
    if item.type == "travel" and subtype == "travel_project":
        return 70
    if item.type == "study" and (meta.get("quiz_incomplete") or meta.get("flashcard_incomplete")):
        return 60
    if subtype == "action_project":
        return 35  # bag — prefer domain artifact
    if item.type in ("study", "travel"):
        return 50
    return 40


def dedupe_by_goal(items: List[HomeItem]) -> List[HomeItem]:
    """
    Collapse items sharing the same goal_id into one representative per lane:
    - focus lane: non-resume items
    - resume lane: resume items
    Prefer concrete next action (session / departure / draft) over action_project bags.
    """
    if not any(i.goal_id for i in items):
        return items

    best: Dict[str, HomeItem] = {}
    for item in items:
        if not item.goal_id:
            continue
        lane = "resume" if item.type == "resume" else "focus"
        key = f"{item.goal_id}:{lane}"
        prev = best.get(key)
        if prev is None:
            best[key] = item
            continue
        cand = (
            _concreteness(item),
            float(item.score or 0),
            item.updated_at or "",
            item.id,
        )
        cur = (
            _concreteness(prev),
            float(prev.score or 0),
            prev.updated_at or "",
            prev.id,
        )
        if cand >= cur:
            best[key] = item

    emitted: set = set()
    out: List[HomeItem] = []
    for item in items:
        if not item.goal_id:
            out.append(item)
            continue
        lane = "resume" if item.type == "resume" else "focus"
        key = f"{item.goal_id}:{lane}"
        if key in emitted:
            continue
        out.append(best[key])
        emitted.add(key)
    return out


def enrich_resume_with_goal(item: Optional[HomeItem]) -> Optional[HomeItem]:
    """Mention Goal title on resume CTA when linked — no invented copy."""
    if not item or not item.goal_title:
        return item
    it = item.model_copy(deep=True)
    title = it.goal_title
    # Avoid duplicating if title already contains goal name
    blob = f"{it.title or ''} {it.description or ''}".lower()
    if title.lower() not in blob:
        base_desc = (it.description or "").strip()
        mention = f"Obiettivo: {title}"
        it.description = f"{base_desc} · {mention}" if base_desc else mention
    return it


def goal_score_delta(item: HomeItem, now: datetime) -> Tuple[float, List[ReasonFactor]]:
    """
    Slight deterministic boost from Goal urgency/importance/progress/stale.
    Only fires when goal_id is attached — never invents reasons.
    """
    if not item.goal_id:
        return 0.0, []
    factors: List[ReasonFactor] = []
    delta = 0.0
    meta = item.meta or {}

    importance = meta.get("goal_importance")
    urgency = meta.get("goal_urgency")
    if isinstance(importance, (int, float)) and importance > 0:
        w = min(6.0, float(importance) * 0.9)
        delta += w
        factors.append(ReasonFactor(
            code="goal_importance",
            label="Importanza obiettivo",
            weight=w,
            detail=item.goal_title,
        ))
    if isinstance(urgency, (int, float)) and urgency > 0:
        w = min(8.0, float(urgency) * 1.1)
        delta += w
        factors.append(ReasonFactor(
            code="goal_urgency",
            label="Urgenza obiettivo",
            weight=w,
            detail=item.goal_title,
        ))

    days = meta.get("goal_days_remaining")
    pct = item.goal_progress
    if days is not None and isinstance(days, (int, float)) and 0 <= days <= 14:
        # Stale / behind: deadline soon + low progress
        if pct is not None and pct < 50:
            w = 10.0 if days <= 7 else 7.0
            delta += w
            factors.append(ReasonFactor(
                code="goal_deadline_pressure",
                label="Scadenza obiettivo vicina",
                weight=w,
                detail=f"{int(days)}g · {pct:.0f}%",
            ))
        elif days <= 7:
            w = 5.0
            delta += w
            factors.append(ReasonFactor(
                code="goal_deadline_near",
                label="Obiettivo in scadenza",
                weight=w,
                detail=f"tra {int(days)} giorni",
            ))

    if item.goal_next_action:
        w = 4.0
        delta += w
        factors.append(ReasonFactor(
            code="goal_next_action",
            label="Prossima azione obiettivo",
            weight=w,
            detail=str(item.goal_next_action)[:80],
        ))
    elif item.goal_title:
        # Light presence factor so Perché adesso can cite the Goal
        w = 3.0
        delta += w
        factors.append(ReasonFactor(
            code="goal_context",
            label="Contesto obiettivo",
            weight=w,
            detail=item.goal_title,
        ))

    if pct is not None and item.goal_progress_label:
        factors.append(ReasonFactor(
            code="goal_progress",
            label=f"Progresso {pct:.0f}%",
            weight=2.0,
            detail=item.goal_progress_label,
        ))
        delta += 2.0

    return round(delta, 2), factors


def build_goal_insight_candidates(
    items: List[HomeItem],
    goals: List[Any],
    *,
    now: datetime,
) -> List[InsightItem]:
    """Honest Goal progress insights — max 1–2 slots shared with other insights."""
    if not goals:
        return []
    # Prefer goals that appear on Home (deduped representatives)
    linked_ids = {i.goal_id for i in items if i.goal_id}
    candidates: List[InsightItem] = []
    for g in goals:
        if g.id not in linked_ids and linked_ids:
            continue
        pct = float(getattr(g, "completion_percentage", 0) or 0)
        prog = getattr(g, "progress", None)
        label = getattr(prog, "label", None) if prog else None
        target = getattr(g, "target_date", None) or getattr(g, "start_date", None)
        days = _days_until(target, now)
        # Need something honest to say
        if pct <= 0 and days is None and not label:
            continue
        parts = []
        short = (g.title or "Obiettivo").strip()
        # Compact title for insight
        if len(short) > 40:
            short = short[:37] + "…"
        if pct > 0 or label:
            parts.append(f"{short} al {pct:.0f}%")
        else:
            parts.append(short)
        if days is not None and days >= 0:
            if getattr(g, "goal_type", None) == "study":
                parts.append(f"esame tra {days} giorni")
            elif getattr(g, "goal_type", None) == "travel":
                parts.append(f"partenza tra {days} giorni" if days > 0 else "partenza oggi")
            else:
                parts.append(f"tra {days} giorni")
        text = ", ".join(parts)
        if label and label not in text:
            text = f"{text} ({label})"
        candidates.append(InsightItem(
            id=f"ins_goal_{g.id}",
            text=text,
            source="goal_engine",
            action=None,
            status="active",
            created_at=now.isoformat(),
            valid_until=(now + timedelta(days=2)).isoformat(),
            dedupe_key=f"goal_progress:{g.id}",
        ))
        if len(candidates) >= 2:
            break
    return candidates
