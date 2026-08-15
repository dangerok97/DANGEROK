"""
Home Presentation Aggregation Layer.

Collapses multi-artifact Goal streams into ONE presentation card per goal_id.
Non-destructive: never mutates source plans/sessions/events/suggestions —
only aggregates for GET /api/home presentation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from home.models import HomeAction, HomeItem, PRESENTATION_VERSION, now_iso

logger = logging.getLogger("ora.home.presentation")

# Preference order for primary representation within a Goal cluster
# 1 concrete imminent → 2 blocker → 3 recovery → 4 next session → 5 synthetic → 6 resume
_PREF_IMMINENT = 100
_PREF_BLOCKER = 90
_PREF_RECOVERY = 80
_PREF_NEXT_SESSION = 70
_PREF_SYNTHETIC = 60
_PREF_RESUME = 50
_PREF_OTHER = 20


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _hours_until(value: Optional[str], now: datetime) -> Optional[float]:
    dt = _parse_dt(value)
    if dt is None:
        return None
    return (dt - now).total_seconds() / 3600.0


def representation_rank(item: HomeItem, now: datetime) -> Tuple[int, float, str]:
    """Higher tuple wins as the Goal's primary card shell."""
    meta = item.meta or {}
    hrs = _hours_until(item.due_at or item.start_at, now)
    score = float(item.score or 0)

    # 1. Concrete imminent action
    if item.goal_status == "blocked" or (item.goal_blockers and item.goal_status == "blocked"):
        return (_PREF_BLOCKER, score, item.id)
    if meta.get("session_today") or (hrs is not None and 0 <= hrs <= 24):
        if item.type != "resume" or meta.get("next_session"):
            return (_PREF_IMMINENT, score, item.id)
    if item.type == "travel" and meta.get("phase") in ("departure_day", "during"):
        return (_PREF_IMMINENT, score, item.id)
    # Expired plan shells must NOT win cluster shell as "imminent"
    tstate = meta.get("temporal_state")
    if tstate in ("EXPIRED_STALE", "SUPERSEDED"):
        return (_PREF_SYNTHETIC - 20, score, item.id)
    if meta.get("canonical_execution") and meta.get("actionable_now"):
        return (_PREF_IMMINENT + 2, score + 8, item.id)
    if (
        hrs is not None
        and hrs < 0
        and item.type in ("study", "travel", "event", "bill", "payment")
        and tstate != "EXPIRED_STALE"
        and not meta.get("plan_shell")
    ):
        return (_PREF_IMMINENT, score + 5, item.id)
    if (
        hrs is not None
        and hrs < 0
        and item.type in ("bill", "payment")
    ):
        return (_PREF_IMMINENT, score + 5, item.id)

    # 2. Blocker (non-blocked status but has blockers / missing prep)
    if item.goal_blockers or meta.get("missing_prep"):
        return (_PREF_BLOCKER - 5, score, item.id)

    # 3. Recovery (skipped / missed sessions)
    try:
        skipped = int(meta.get("skipped_sessions") or 0)
    except (TypeError, ValueError):
        skipped = 0
    try:
        missed = int(meta.get("missed_sessions") or 0)
    except (TypeError, ValueError):
        missed = 0
    if skipped > 0 or missed > 0:
        return (_PREF_RECOVERY, score, item.id)

    # 4. Next session
    if meta.get("next_session") or (item.type == "study" and item.source_type == "study_plan"):
        return (_PREF_NEXT_SESSION, score, item.id)
    if item.type == "travel" and item.source_type == "travel_project":
        return (_PREF_NEXT_SESSION - 2, score, item.id)

    # 5. Synthetic Goal card (plan/project shells)
    if item.source_type in ("study_plan", "travel_project", "life_os_plan"):
        return (_PREF_SYNTHETIC + (10 if meta.get("canonical_execution") else 0), score, item.id)
    if item.subtype == "action_project":
        return (_PREF_SYNTHETIC - 10, score, item.id)

    # 6. Resume
    if item.type == "resume":
        return (_PREF_RESUME, score, item.id)

    return (_PREF_OTHER, score, item.id)


def _source_ref(item: HomeItem) -> Dict[str, str]:
    return {
        "type": item.source_type,
        "id": item.source_id,
        "item_id": item.id,
        "title": (item.title or "")[:120],
    }


def _detail_from_item(item: HomeItem) -> Optional[Dict[str, Any]]:
    """Turn a collapsed artifact into a supporting_detail row (not a priority card)."""
    meta = item.meta or {}
    kind = item.source_type
    label = item.title or item.description or kind
    detail: Dict[str, Any] = {
        "kind": kind,
        "label": label[:160],
        "source_type": item.source_type,
        "source_id": item.source_id,
    }
    if item.start_at:
        detail["when"] = item.start_at
    if item.due_at and not item.start_at:
        detail["when"] = item.due_at
    if meta.get("next_session") and isinstance(meta["next_session"], dict):
        detail["next_session"] = meta["next_session"].get("title")
    if meta.get("phase"):
        detail["phase"] = meta["phase"]
    if meta.get("exam_countdown_days") is not None:
        detail["exam_in_days"] = meta["exam_countdown_days"]
    if meta.get("days_until") is not None:
        detail["days_until"] = meta["days_until"]
    if meta.get("skipped_sessions"):
        detail["skipped"] = meta["skipped_sessions"]
    if meta.get("missing_prep"):
        detail["missing_prep"] = meta["missing_prep"][:3] if isinstance(meta["missing_prep"], list) else meta["missing_prep"]
    if item.type == "resume":
        detail["resume_kind"] = meta.get("resume_kind") or item.subtype
    return detail


def _study_title(item: HomeItem, members: List[HomeItem]) -> str:
    title = item.goal_title or item.title or "Studio"
    # Prefer "Preparare l'esame di X" shape when we have exam name
    exam = None
    for m in members:
        if m.source_type == "study_plan":
            raw = (m.title or "").replace("Studio:", "").strip()
            exam = raw or exam
            break
    if exam and "preparare" not in title.lower():
        return f"Preparare l'esame di {exam}"
    if item.goal_title and "esame" not in (item.goal_title or "").lower():
        if exam:
            return f"Preparare l'esame di {exam}"
    return title


def _travel_title(item: HomeItem) -> str:
    return item.goal_title or item.title or "Viaggio"


def _build_subtitle(primary: HomeItem, members: List[HomeItem], card_type: str) -> str:
    parts: List[str] = []
    meta = primary.meta or {}
    if card_type == "study":
        cd = meta.get("exam_countdown_days")
        if cd is not None:
            parts.append(f"Esame tra {cd} giorni")
        ns = meta.get("next_session")
        if isinstance(ns, dict) and ns.get("title"):
            parts.append(f"Prossima: {ns['title']}")
        elif primary.goal_next_action:
            parts.append(str(primary.goal_next_action))
        # Session progress from any study_plan member
        for m in members:
            if m.source_type == "study_plan":
                desc = m.description or ""
                if "/" in desc and "sessioni" in desc:
                    for seg in desc.split(" · "):
                        if "sessioni" in seg:
                            parts.append(seg)
                            break
                break
        if meta.get("skipped_sessions"):
            parts.append(f"{meta['skipped_sessions']} saltate")
    elif card_type == "travel":
        if meta.get("phase") == "departure_day":
            parts.append("Partenza oggi")
        elif meta.get("days_until") is not None:
            parts.append(f"Partenza tra {meta['days_until']} giorni")
        prep = meta.get("missing_prep") or []
        if prep:
            first = prep[0] if isinstance(prep, list) else prep
            parts.append(f"Manca: {first}")
        elif primary.goal_next_action:
            parts.append(str(primary.goal_next_action))
    else:
        if primary.goal_next_action:
            parts.append(str(primary.goal_next_action))
        elif primary.description:
            parts.append(primary.description[:120])

    if primary.goal_blockers:
        block = primary.goal_blockers[0]
        if not any(block.lower() in p.lower() for p in parts):
            parts.insert(0, f"Blocco: {block}")

    # Dedupe
    seen = set()
    out: List[str] = []
    for p in parts:
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return " · ".join(out[:4]) if out else (primary.description or primary.reason_summary or "")


def _merge_actions(
    primary: HomeItem,
    members: List[HomeItem],
    *,
    conversation: Optional[HomeItem] = None,
    suggestion: Optional[Dict[str, Any]] = None,
) -> List[HomeAction]:
    """Primary Continua/open + secondary plan/flashcard/maps — no dead buttons."""
    acts: List[HomeAction] = []
    seen_ids: set = set()

    def _add(a: HomeAction) -> None:
        if a.id in seen_ids:
            return
        seen_ids.add(a.id)
        acts.append(a)

    # Prefer concrete primary actions first
    for a in primary.actions or []:
        _add(a)

    # Study enrichments from plan / docs
    plan = next((m for m in members if m.source_type == "study_plan"), None)
    if plan:
        sid = plan.source_id
        if "open_plan" not in seen_ids:
            _add(HomeAction(
                id="open_plan", label="Apri piano", kind="navigate",
                route=f"/study-plan/{sid}",
            ))
        next_s = (plan.meta or {}).get("next_session") or {}
        if next_s.get("id") and "start_session" not in seen_ids:
            _add(HomeAction(
                id="continua_studio", label="Continua", kind="study",
                route=f"/study-plan/{sid}",
                params={"session_id": next_s["id"], "action": "start"},
                primary=True,
            ))
        fc = (plan.meta or {}).get("flashcard_document_ids") or []
        iq = (plan.meta or {}).get("interrogami_document_ids") or []
        # Also harvest from linked study docs
        for m in members:
            if m.source_type == "study":
                if not fc and m.meta.get("flashcard_incomplete"):
                    fc = [m.source_id]
                if not iq and m.meta.get("quiz_incomplete"):
                    iq = [m.source_id]
        if fc and "flashcards" not in seen_ids:
            _add(HomeAction(
                id="flashcards", label="Flashcard", kind="study",
                route=f"/document/{fc[0]}", params={"mode": "flashcards"},
            ))
        if iq and "quiz" not in seen_ids:
            _add(HomeAction(
                id="quiz", label="Interrogami", kind="study",
                route=f"/document/{iq[0]}", params={"mode": "quiz"},
            ))
        if "snooze" not in seen_ids:
            _add(HomeAction(id="snooze", label="Rimanda", kind="snooze"))

    travel = next((m for m in members if m.source_type == "travel_project"), None)
    if travel:
        tid = travel.source_id
        if "open_travel_project" not in seen_ids:
            _add(HomeAction(
                id="open_travel_project", label="Preparativi", kind="navigate",
                route=f"/travel-project/{tid}",
            ))
        maps = (travel.meta or {}).get("maps") or {}
        if (maps.get("deep_link") or travel.location) and "open_maps" not in seen_ids:
            _add(HomeAction(
                id="open_maps", label="Percorso", kind="maps",
                params={"query": travel.location or travel.title, "url": maps.get("deep_link")},
            ))
        if "open_calendar" not in seen_ids:
            _add(HomeAction(
                id="open_calendar", label="Calendario", kind="navigate", route="/situazione",
            ))
        docs = [m for m in members if m.source_type in ("document", "study") or m.meta.get("document_id")]
        if docs and "open_docs" not in seen_ids:
            doc_id = docs[0].meta.get("document_id") or docs[0].source_id
            _add(HomeAction(
                id="open_docs", label="Documenti", kind="navigate", route=f"/document/{doc_id}",
            ))
        if "continua_travel" not in seen_ids:
            _add(HomeAction(
                id="continua_travel", label="Continua", kind="navigate",
                route=f"/travel-project/{tid}", primary=True,
            ))

    # Conversation resume → action on Goal card (not a separate card)
    if conversation:
        route = None
        for a in conversation.actions or []:
            if a.route:
                route = a.route
                break
        route = route or f"/conversation?resume={conversation.source_id}"
        label = "Continua organizzazione" if (conversation.subtype in ("travel", "study") or primary.goal_type in ("travel", "study")) else "Riprendi conversazione"
        _add(HomeAction(
            id="resume_conversation",
            label=label,
            kind="resume",
            route=route,
            params={"conversation_session_id": conversation.source_id},
            primary=not any(a.primary for a in acts),
        ))

    # Suggestion may replace / enrich next_action as an action
    if suggestion and suggestion.get("action"):
        sa = suggestion["action"]
        _add(HomeAction(
            id=f"suggestion_{suggestion.get('id', 'x')}",
            label=sa.get("label") or "Suggerimento ORA",
            kind=sa.get("kind") or "navigate",
            route=sa.get("route"),
            params=sa.get("params") or {},
        ))

    # Ensure at least one primary
    if acts and not any(a.primary for a in acts):
        acts[0] = acts[0].model_copy(update={"primary": True})

    # Cap to avoid clutter — Continua + key secondaries
    return acts[:6]


def _card_type(primary: HomeItem, members: List[HomeItem]) -> str:
    if primary.goal_type in ("study", "travel"):
        return primary.goal_type
    if any(m.source_type == "study_plan" or m.type == "study" for m in members):
        return "study"
    if any(m.source_type == "travel_project" or m.type == "travel" for m in members):
        return "travel"
    return primary.type or "generic"


def _next_action_text(
    primary: HomeItem,
    *,
    suggestion: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    if suggestion and (suggestion.get("title") or suggestion.get("description")):
        # Better suggestion can replace next_action copy
        return suggestion.get("title") or suggestion.get("description")
    return primary.goal_next_action or (
        (primary.meta or {}).get("next_session") or {}
    ).get("title") if isinstance((primary.meta or {}).get("next_session"), dict) else primary.goal_next_action


def aggregate_goal_cluster(
    members: List[HomeItem],
    *,
    now: datetime,
    suggestion: Optional[Dict[str, Any]] = None,
) -> HomeItem:
    """Build ONE presentation HomeItem from all artifacts sharing a goal_id."""
    assert members
    goal_id = members[0].goal_id
    assert goal_id

    # Split conversation resumes — incorporate as actions, not competing primaries
    conversations = [
        m for m in members
        if m.source_type == "conversation_session" or (m.type == "resume" and (m.meta or {}).get("resume_kind") == "conversation")
    ]
    focus_pool = [m for m in members if m not in conversations]
    if not focus_pool:
        focus_pool = list(members)

    ranked = sorted(focus_pool, key=lambda m: representation_rank(m, now), reverse=True)
    primary = ranked[0].model_copy(deep=True)
    card_type = _card_type(primary, members)

    if card_type == "study":
        primary.title = _study_title(primary, members)
    elif card_type == "travel":
        primary.title = _travel_title(primary)

    subtitle = _build_subtitle(primary, members, card_type)
    primary.description = subtitle

    # Supporting details from non-primary artifacts
    details: List[Dict[str, Any]] = []
    for m in members:
        if m.id == primary.id:
            continue
        if m in conversations:
            details.append({
                "kind": "conversation",
                "label": m.title or "Conversazione in corso",
                "source_type": m.source_type,
                "source_id": m.source_id,
            })
            continue
        d = _detail_from_item(m)
        if d:
            details.append(d)

    # Also surface plan-level badges on the primary itself
    badges: List[str] = []
    meta = primary.meta or {}
    if meta.get("exam_countdown_days") is not None:
        badges.append(f"esame_{meta['exam_countdown_days']}g")
    if meta.get("session_today"):
        badges.append("sessione_oggi")
    if meta.get("flashcard_document_ids") or any(
        (m.meta or {}).get("flashcard_incomplete") for m in members
    ):
        badges.append("flashcard")
    if meta.get("missing_prep"):
        badges.append("prep_mancante")
    if conversations:
        badges.append("conversazione")

    conversation = conversations[0] if conversations else None
    primary.actions = _merge_actions(
        primary, members, conversation=conversation, suggestion=suggestion,
    )

    next_action = _next_action_text(primary, suggestion=suggestion)
    if next_action:
        primary.goal_next_action = next_action

    source_refs = [_source_ref(m) for m in members]
    hidden = max(0, len(members) - 1)

    presentation_id = f"pres_goal_{goal_id}"
    primary.id = presentation_id
    primary.meta = {
        **(primary.meta or {}),
        "presentation_id": presentation_id,
        "presentation_version": PRESENTATION_VERSION,
        "card_type": card_type,
        "subtitle": subtitle,
        "next_action": next_action,
        "supporting_details": details[:12],
        "source_refs": source_refs,
        "hidden_artifact_count": hidden,
        "presentation_badges": badges,
        "aggregated_member_ids": [m.id for m in members],
        "aggregated_at": now_iso(),
        "goal_dedupe_key": f"goal:{goal_id}",
        "dedupe_key": f"presentation:{goal_id}",
    }
    # Keep type aligned with domain for FE labels
    if card_type in ("study", "travel") and primary.type != card_type:
        primary.type = card_type  # type: ignore[assignment]
    return primary


def aggregate_presentation(
    items: List[HomeItem],
    *,
    now: Optional[datetime] = None,
    suggestions: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[HomeItem], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Collapse Goal-linked artifacts into one card per goal_id.

    Returns:
      - presentation items (ungrouped + one card per Goal)
      - filtered suggestions (those not incorporated into a Goal card)
      - audit stats
    """
    now = now or datetime.now(timezone.utc)
    suggestions = list(suggestions or [])

    by_goal: Dict[str, List[HomeItem]] = {}
    ungrouped: List[HomeItem] = []
    for it in items:
        gid = it.goal_id or (it.meta or {}).get("goal_id")
        if gid:
            by_goal.setdefault(str(gid), []).append(it)
        else:
            ungrouped.append(it)

    # Map suggestions to goals
    sug_by_goal: Dict[str, Dict[str, Any]] = {}
    leftover_suggestions: List[Dict[str, Any]] = []
    for s in suggestions:
        gid = s.get("goal_id")
        if gid and gid in by_goal and gid not in sug_by_goal:
            sug_by_goal[gid] = s
        else:
            leftover_suggestions.append(s)

    out: List[HomeItem] = []
    for gid, members in by_goal.items():
        try:
            card = aggregate_goal_cluster(
                members, now=now, suggestion=sug_by_goal.get(gid),
            )
            out.append(card)
        except Exception:
            logger.warning("presentation aggregate failed for goal %s", gid, exc_info=True)
            # Safe fallback: keep highest-scoring member only
            best = max(members, key=lambda m: (float(m.score or 0), m.updated_at or ""))
            out.append(best)

    # Ungrouped: still apply source-level uniqueness (already done upstream)
    out.extend(ungrouped)

    # Sort by score again
    out.sort(key=lambda x: (-float(x.score or 0), x.start_at or x.due_at or "", x.id))

    stats = {
        "goal_clusters": len(by_goal),
        "presentation_cards": len(by_goal),
        "ungrouped": len(ungrouped),
        "suggestions_incorporated": len(sug_by_goal),
        "suggestions_remaining": len(leftover_suggestions),
        "presentation_version": PRESENTATION_VERSION,
    }
    return out, leftover_suggestions, stats


def enforce_one_card_per_goal(items: List[HomeItem]) -> List[HomeItem]:
    """Hard invariant: at most one non-resume surface item per goal_id."""
    seen: set = set()
    out: List[HomeItem] = []
    for it in items:
        gid = it.goal_id
        if not gid:
            out.append(it)
            continue
        if gid in seen:
            continue
        seen.add(gid)
        out.append(it)
    return out


def goal_ids_on_surface(primary: Optional[HomeItem], priorities: List[HomeItem], resume: Optional[HomeItem]) -> Dict[str, str]:
    """Map goal_id → where it appears (for cross-lane dedupe)."""
    loc: Dict[str, str] = {}
    if primary and primary.goal_id:
        loc[primary.goal_id] = "primary"
    for it in priorities:
        if it.goal_id and it.goal_id not in loc:
            loc[it.goal_id] = "priority"
    if resume and resume.goal_id and resume.goal_id not in loc:
        loc[resume.goal_id] = "resume"
    return loc
