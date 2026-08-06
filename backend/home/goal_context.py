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
    """Lookup Goals by artifact / session / document / calendar links."""

    def __init__(self, goals: List[Any]):
        self.by_id: Dict[str, Any] = {}
        self.by_study_plan: Dict[str, Any] = {}
        self.by_travel: Dict[str, Any] = {}
        self.by_project: Dict[str, Any] = {}
        self.by_session: Dict[str, Any] = {}
        self.by_document: Dict[str, Any] = {}
        self.by_calendar: Dict[str, Any] = {}
        self.by_conversation: Dict[str, Any] = {}
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
            for cal_id in getattr(g, "linked_calendar_events", None) or []:
                if cal_id and cal_id not in self.by_calendar:
                    self.by_calendar[cal_id] = g
            # Conversation sessions stamped on Goal meta / artifacts
            for cid in (getattr(g, "linked_conversation_sessions", None) or []):
                if cid and cid not in self.by_conversation:
                    self.by_conversation[cid] = g
            art = getattr(g, "artifacts", None) or {}
            if isinstance(art, dict):
                for cid in art.get("conversation_session_ids") or []:
                    if cid and cid not in self.by_conversation:
                        self.by_conversation[cid] = g

    def match(self, item: HomeItem) -> Optional[Any]:
        meta = item.meta or {}
        gid = meta.get("goal_id") or item.goal_id or meta.get("ora_goal_id")
        if gid and gid in self.by_id:
            return self.by_id[gid]

        for key in (
            meta.get("study_plan_id"),
            meta.get("ora_study_plan_id"),
            meta.get("plan_id"),
        ):
            if key and key in self.by_study_plan:
                return self.by_study_plan[key]
        if item.source_type == "study_plan" and item.source_id in self.by_study_plan:
            return self.by_study_plan[item.source_id]

        for key in (
            meta.get("travel_project_id"),
            meta.get("ora_travel_project_id"),
        ):
            if key and key in self.by_travel:
                return self.by_travel[key]
        if item.source_type == "travel_project" and item.source_id in self.by_travel:
            return self.by_travel[item.source_id]

        proj = meta.get("project_id") or meta.get("action_project_id")
        if proj and proj in self.by_project:
            return self.by_project[proj]
        if item.source_type == "action_project" and item.source_id in self.by_project:
            return self.by_project[item.source_id]

        for sid in (
            item.source_id if item.source_type == "action_session" else None,
            meta.get("action_session_id"),
            meta.get("source_action_session_id"),
        ):
            if sid and sid in self.by_session:
                return self.by_session[sid]

        for cid in (
            item.source_id if item.source_type == "conversation_session" else None,
            meta.get("conversation_session_id"),
        ):
            if cid and cid in self.by_conversation:
                return self.by_conversation[cid]

        doc_id = meta.get("document_id") or (
            item.source_id if item.source_type in ("study", "document", "quiz_session") else None
        )
        if doc_id and doc_id in self.by_document:
            return self.by_document[doc_id]

        # Calendar / life_node / Google via linked ids or study_session refs
        for cal_key in (
            item.source_id if item.source_type in ("life_node", "google_calendar", "internal_calendar") else None,
            meta.get("calendar_node_id"),
            meta.get("life_node_id"),
            meta.get("external_id"),
            meta.get("ora_event_id"),
        ):
            if cal_key and cal_key in self.by_calendar:
                return self.by_calendar[cal_key]

        # Study session id → plan via attributes stamped by Action Engine
        sess = meta.get("study_session_id")
        if sess:
            for g in self.by_study_plan.values():
                # soft: if session id appears in goal artifacts
                arts = getattr(g, "artifacts", None) or {}
                if isinstance(arts, dict) and sess in (arts.get("session_ids") or []):
                    return g

        return None


def _days_until(iso: Optional[str], now: datetime) -> Optional[int]:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00")[:10]).date()
        return (d - now.astimezone(timezone.utc).date()).days
    except Exception:
        return None


def _hours_since(iso: Optional[str], now: datetime) -> Optional[float]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
    except Exception:
        return None


def _derive_blockers(goal: Any, item: HomeItem) -> List[str]:
    """Honest blocker strings from Goal status + artifact meta — never invented."""
    out: List[str] = []
    status = getattr(goal, "status", None)
    current = (getattr(goal, "current_state", None) or "").strip()
    if status == "blocked":
        out.append(current or "Obiettivo bloccato")
    elif status == "waiting" and current:
        out.append(current)

    meta = item.meta or {}
    skipped = meta.get("skipped_sessions") or 0
    try:
        skipped_n = int(skipped)
    except (TypeError, ValueError):
        skipped_n = 0
    if skipped_n > 0:
        out.append(f"{skipped_n} sessioni saltate")

    missed = meta.get("missed_sessions") or 0
    try:
        missed_n = int(missed)
    except (TypeError, ValueError):
        missed_n = 0
    if missed_n > 0:
        out.append(f"{missed_n} sessioni mancate")

    missing_prep = meta.get("missing_prep")
    if isinstance(missing_prep, list):
        for p in missing_prep[:3]:
            if isinstance(p, str) and p.strip():
                out.append(p.strip())
            elif isinstance(p, dict):
                label = (p.get("label") or p.get("title") or "").strip()
                if label:
                    out.append(label)
    elif isinstance(missing_prep, str) and missing_prep.strip():
        out.append(missing_prep.strip())

    # Deduplicate preserving order
    seen = set()
    uniq: List[str] = []
    for b in out:
        key = b.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(b)
    return uniq


def _progress_public(goal: Any) -> Tuple[Optional[float], Optional[str]]:
    """
    Reliable progress for Home cards.
    Study session ratios → numeric % + label OK.
    Travel soft phase → phase/checklist label only (no precise %).
    """
    pct = float(getattr(goal, "completion_percentage", None) or 0.0)
    prog = getattr(goal, "progress", None)
    label = getattr(prog, "label", None) if prog is not None else None
    source = getattr(prog, "source", None) if prog is not None else None
    phase = getattr(prog, "phase", None) if prog is not None else None
    gtype = getattr(goal, "goal_type", None)

    if source == "travel_phase" or (gtype == "travel" and source not in ("travel_prep", "study_sessions")):
        # Soft qualitative progress — phase / checklist, not a fake precise %
        return None, label or (f"fase: {phase}" if phase else None)

    if source == "travel_prep" and label:
        return round(pct, 2), label

    if pct > 0 or label:
        return round(pct, 2), label
    return (round(pct, 2) if pct else None), label


def _apply_goal_fields(item: HomeItem, goal: Any, now: datetime) -> HomeItem:
    it = item.model_copy(deep=True)
    target = getattr(goal, "target_date", None) or getattr(goal, "start_date", None)
    days = _days_until(target, now)
    next_action = getattr(goal, "next_action", None)
    # Prefer concrete next session title from study meta when Goal next_action empty
    if not next_action and (it.meta or {}).get("next_session"):
        ns = it.meta["next_session"]
        if isinstance(ns, dict):
            next_action = ns.get("title") or "Prossima sessione"

    pct, label = _progress_public(goal)
    blockers = _derive_blockers(goal, it)
    project_id = getattr(goal, "project_id", None)
    gtype = getattr(goal, "goal_type", None)
    progress_src = getattr(getattr(goal, "progress", None), "source", None)
    last_advance = (
        getattr(getattr(goal, "progress", None), "updated_at", None)
        or getattr(goal, "updated_at", None)
    )
    hours_stale = _hours_since(last_advance, now)
    cal_n = len(getattr(goal, "linked_calendar_events", None) or [])

    it.goal_id = goal.id
    it.goal_title = goal.title
    it.goal_type = gtype
    it.goal_status = goal.status
    it.goal_progress = pct
    it.goal_progress_label = label
    it.goal_next_action = next_action
    it.goal_target_date = target
    it.goal_blockers = blockers or None
    it.goal_project_id = project_id
    it.meta = {
        **(it.meta or {}),
        "goal_id": goal.id,
        "goal_title": goal.title,
        "goal_type": gtype,
        "goal_status": goal.status,
        "goal_progress": pct,
        "goal_progress_label": label,
        "goal_next_action": next_action,
        "goal_target_date": target,
        "goal_blockers": blockers,
        "goal_project_id": project_id,
        "goal_urgency": getattr(goal, "urgency", None),
        "goal_importance": getattr(goal, "importance", None),
        "goal_days_remaining": days,
        "goal_progress_source": progress_src,
        "goal_hours_since_advance": hours_stale,
        "goal_calendar_links": cal_n,
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
    """Prefer next concrete action / blockers over bags / generic study docs."""
    meta = item.meta or {}
    subtype = item.subtype or ""
    if item.goal_blockers and item.goal_status == "blocked":
        return 96
    if item.type == "resume":
        if subtype in ("study_plan_draft", "travel_project_draft"):
            return 95
        return 90
    if item.type == "study" and meta.get("next_session"):
        return 88
    if item.type == "travel" and meta.get("phase") in ("departure_day", "days_until", "during"):
        return 85
    if item.type == "travel" and meta.get("missing_prep"):
        return 82
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
    blob = f"{it.title or ''} {it.description or ''}".lower()
    if title.lower() not in blob:
        base_desc = (it.description or "").strip()
        mention = f"Obiettivo: {title}"
        it.description = f"{base_desc} · {mention}" if base_desc else mention
    return it


def enrich_focus_with_goal(item: Optional[HomeItem]) -> Optional[HomeItem]:
    """
    Primary focus: concrete next action + Goal as context.
    If blocked → surface blocker. Never invent narrative.
    """
    if not item or not item.goal_id:
        return item
    it = item.model_copy(deep=True)
    parts: List[str] = []
    base = (it.description or "").strip()
    if base:
        parts.append(base)

    if it.goal_blockers:
        block = it.goal_blockers[0]
        if block.lower() not in (base or "").lower():
            parts.append(f"Blocco: {block}")
    elif it.goal_next_action:
        na = str(it.goal_next_action).strip()
        if na and na.lower() not in (base or "").lower():
            # Prefer imminent concrete action in the description when not already present
            if (it.meta or {}).get("next_session") or it.type in ("study", "travel"):
                parts.append(na)

    if it.goal_title:
        mention = f"Obiettivo: {it.goal_title}"
        blob = " ".join(parts).lower()
        if "obiettivo:" not in blob and it.goal_title.lower() not in blob:
            parts.append(mention)

    if parts:
        # Dedupe consecutive identical segments
        cleaned: List[str] = []
        for p in parts:
            if not cleaned or cleaned[-1] != p:
                cleaned.append(p)
        it.description = " · ".join(cleaned)
    return it


def proposal_from_idle_goals(
    goals: List[Any],
    *,
    now: Optional[datetime] = None,
) -> Optional[HomeItem]:
    """
    Goals exist but no actionable Home artifact → useful proposal (not empty card).
    Opens plan/travel/project — never a Goal page.
    """
    if not goals:
        return None
    now = now or datetime.now(timezone.utc)

    def sort_key(g: Any):
        urg = getattr(g, "urgency", None) or 0
        imp = getattr(g, "importance", None) or 0
        days = _days_until(getattr(g, "target_date", None) or getattr(g, "start_date", None), now)
        days_score = 0 if days is None else max(0, 30 - days)
        return (int(urg), int(imp), days_score, getattr(g, "updated_at", "") or "")

    ranked = sorted(goals, key=sort_key, reverse=True)
    g = ranked[0]
    title = (getattr(g, "next_action", None) or "").strip() or f"Avanza: {g.title}"
    blockers = []
    if g.status == "blocked":
        blockers = [getattr(g, "current_state", None) or "Obiettivo bloccato"]
    desc_parts = [f"Obiettivo: {g.title}"]
    if blockers:
        desc_parts.insert(0, f"Blocco: {blockers[0]}")

    source_type = "action_project"
    source_id = g.project_id or g.id
    item_type = "generic"
    subtype = "goal_next"
    if g.study_plan_id:
        source_type = "study_plan"
        source_id = g.study_plan_id
        item_type = "study"
        subtype = "study_plan"
    elif g.travel_project_id:
        source_type = "travel_project"
        source_id = g.travel_project_id
        item_type = "travel"
        subtype = "travel_project"
    elif g.source_action_session_id:
        source_type = "action_session"
        source_id = g.source_action_session_id
        item_type = "resume"
        subtype = "action_session"

    from home.adapters._util import stable_id

    pct, label = _progress_public(g)
    target = getattr(g, "target_date", None) or getattr(g, "start_date", None)
    item = HomeItem(
        id=stable_id("goal_idle", g.user_id, g.id),
        type=item_type,  # type: ignore[arg-type]
        subtype=subtype,
        title=title,
        description=" · ".join(desc_parts),
        source_type=source_type,
        source_id=source_id,
        due_at=target,
        status="open",
        created_at=getattr(g, "created_at", None) or now.isoformat(),
        updated_at=getattr(g, "updated_at", None) or now.isoformat(),
        goal_id=g.id,
        goal_title=g.title,
        goal_type=getattr(g, "goal_type", None),
        goal_status=g.status,
        goal_progress=pct,
        goal_progress_label=label,
        goal_next_action=getattr(g, "next_action", None) or title,
        goal_target_date=target,
        goal_blockers=blockers or None,
        goal_project_id=getattr(g, "project_id", None),
        meta={
            "dedupe_key": f"goal_idle:{g.id}",
            "goal_dedupe_key": f"goal:{g.id}",
            "idle_goal_proposal": True,
            "goal_id": g.id,
        },
    )
    return item


def goal_score_delta(item: HomeItem, now: datetime) -> Tuple[float, List[ReasonFactor]]:
    """
    Deterministic boost from Goal importance/urgency/status/progress/blockers/
    stale advance/skipped/missing prep/calendar. Only when goal_id attached.
    Brain is never a score input here.
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

    status = item.goal_status or meta.get("goal_status")
    if status == "blocked":
        w = 14.0
        delta += w
        detail = (item.goal_blockers or ["bloccato"])[0]
        factors.append(ReasonFactor(
            code="goal_blocked",
            label="Obiettivo bloccato",
            weight=w,
            detail=str(detail)[:80],
        ))
    elif status == "waiting":
        w = 5.0
        delta += w
        factors.append(ReasonFactor(
            code="goal_waiting",
            label="Obiettivo in attesa",
            weight=w,
            detail=item.goal_title,
        ))
    elif status == "paused":
        w = 3.0
        delta += w
        factors.append(ReasonFactor(
            code="goal_paused",
            label="Obiettivo in pausa",
            weight=w,
        ))

    if item.goal_blockers and status != "blocked":
        w = min(10.0, 4.0 + 2.0 * len(item.goal_blockers))
        delta += w
        factors.append(ReasonFactor(
            code="goal_blockers",
            label="Blocchi obiettivo",
            weight=w,
            detail="; ".join(item.goal_blockers[:2]),
        ))

    days = meta.get("goal_days_remaining")
    pct = item.goal_progress
    if days is not None and isinstance(days, (int, float)) and 0 <= days <= 14:
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
    elif item.goal_progress_label and pct is None:
        # Travel soft progress — cite phase/checklist, not a fake %
        factors.append(ReasonFactor(
            code="goal_progress_phase",
            label="Avanzamento obiettivo",
            weight=2.0,
            detail=item.goal_progress_label,
        ))
        delta += 2.0

    hours_stale = meta.get("goal_hours_since_advance")
    if isinstance(hours_stale, (int, float)) and hours_stale >= 72:
        w = 8.0 if hours_stale >= 168 else 5.0
        delta += w
        factors.append(ReasonFactor(
            code="goal_stale",
            label="Nessun avanzamento recente",
            weight=w,
            detail=f"{int(hours_stale / 24)}g",
        ))

    skipped = meta.get("skipped_sessions") or 0
    try:
        skipped_n = int(skipped)
    except (TypeError, ValueError):
        skipped_n = 0
    if skipped_n > 0:
        w = min(12.0, 5.0 + skipped_n * 2.0)
        delta += w
        factors.append(ReasonFactor(
            code="goal_skipped_sessions",
            label="Sessioni saltate",
            weight=w,
            detail=str(skipped_n),
        ))

    if meta.get("missing_prep"):
        w = 9.0
        delta += w
        prep = meta["missing_prep"]
        detail = prep[0] if isinstance(prep, list) and prep else "prep mancante"
        if isinstance(detail, dict):
            detail = detail.get("label") or "prep mancante"
        factors.append(ReasonFactor(
            code="goal_missing_prep",
            label="Preparazione mancante",
            weight=w,
            detail=str(detail)[:80],
        ))

    cal_n = meta.get("goal_calendar_links") or 0
    try:
        cal_n = int(cal_n)
    except (TypeError, ValueError):
        cal_n = 0
    if cal_n > 0:
        w = 2.0
        delta += w
        factors.append(ReasonFactor(
            code="goal_calendar",
            label="Collegato al calendario",
            weight=w,
            detail=f"{cal_n} eventi",
        ))

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
    linked_ids = {i.goal_id for i in items if i.goal_id}
    candidates: List[InsightItem] = []
    for g in goals:
        if g.id not in linked_ids and linked_ids:
            continue
        pct = float(getattr(g, "completion_percentage", 0) or 0)
        prog = getattr(g, "progress", None)
        label = getattr(prog, "label", None) if prog else None
        source = getattr(prog, "source", None) if prog else None
        target = getattr(g, "target_date", None) or getattr(g, "start_date", None)
        days = _days_until(target, now)
        # Need something honest to say
        if pct <= 0 and days is None and not label:
            continue
        parts = []
        short = (g.title or "Obiettivo").strip()
        if len(short) > 40:
            short = short[:37] + "…"
        # Travel soft: prefer phase label over fake %
        if source == "travel_phase" or (
            getattr(g, "goal_type", None) == "travel" and source != "travel_prep"
        ):
            parts.append(f"{short}" + (f" ({label})" if label else ""))
        elif pct > 0 or label:
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
        if label and label not in text and source != "travel_phase":
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
