"""Attività — one read model over what ORA is asking, awaiting and has done.

Presentation only. Every section here is assembled from a system that already
decided something: Home decided what matters and in what order, Attention
decided whether a thing is a question or a proposal, Life Memory decided what
it is unsure of, and the item state store recorded what was finished. Nothing
in this module ranks, classifies or infers — it selects, labels and bounds.

The page it feeds is a trust surface, so two distinctions are load-bearing and
are enforced here rather than in the interface:

  * a question ORA is asking is not the same as an action ORA has prepared and
    will not take without a yes;
  * something a person chose to put off is not the same as something that
    genuinely cannot move yet.

Collapsing either one would make the page reassuring instead of true.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.activity")

# Bounded by construction: this is a page about what is going on now, not an
# archive. Every window here is small on purpose.
MAX_QUESTIONS = 6
MAX_WAITING = 6
MAX_UPDATES = 6
MAX_DEADLINES = 5
MAX_COMPLETED = 5
COMPLETED_WINDOW_DAYS = 21
UPDATE_WINDOW_DAYS = 21

# Attention's own delivery vocabulary. `ask_user` is ORA needing an answer;
# `propose_action` is ORA holding something it will not do unattended. They
# look similar and mean different things to a person, so they stay apart.
DELIVERY_QUESTION = "ask_user"
DELIVERY_CONSENT = "propose_action"
DELIVERY_DEFER = "defer"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _age_days(value: Optional[str], now: datetime) -> Optional[float]:
    d = _parse(value)
    if not d:
        return None
    return (now - d).total_seconds() / 86400.0


def _text(value: Any, limit: int = 200) -> str:
    return str(value or "").strip()[:limit]


# --- questions ---------------------------------------------------------------


def _open_question_rows(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What ORA is genuinely blocked on, from the questions themselves.

    These come before anything the attention layer merely thought worth
    surfacing, because they are the only rows on this page where an answer
    moves real work forward rather than acknowledging a notice. The id is
    namespaced so Home and Activity can dedupe against each other by identity
    instead of by wording.
    """
    rows: List[Dict[str, Any]] = []
    for q in questions or []:
        title = _text(q.get("question"), 300)
        if not title:
            continue
        rows.append({
            "id": f"question:{q.get('id')}",
            "title": title,
            "detail": _text(q.get("why_needed") or q.get("context_label")),
            "needs_consent": False,
            "kind": "question",
            # The opaque handle an interface needs to answer it, and the thread
            # the answer belongs to. Nothing about how the work is modelled.
            "question_id": _text(q.get("id"), 64),
            "session_id": _text(q.get("session_id"), 64) or None,
            "context_label": _text(q.get("context_label"), 160) or None,
            "route": None,
        })
    return rows


def _question_rows(home: Dict[str, Any]) -> List[Dict[str, Any]]:
    """What ORA is waiting for the user to answer or allow.

    Both kinds come from the same suggestion stream and are told apart only by
    the delivery mode Attention already assigned. `needs_consent` travels to the
    client as a fact about the item, never as a style: the interface has to be
    able to say "serve la tua conferma" without guessing.
    """
    rows: List[Dict[str, Any]] = []
    for s in home.get("ora_ti_consiglia") or []:
        delivery = str(((s.get("meta") or {}).get("delivery") or "")).strip()
        if delivery not in (DELIVERY_QUESTION, DELIVERY_CONSENT):
            continue
        title = _text(s.get("title"))
        if not title:
            continue
        rows.append({
            "id": f"suggestion:{s.get('id')}",
            "title": title,
            "detail": _text(s.get("description") or s.get("reason")),
            "needs_consent": delivery == DELIVERY_CONSENT,
            "kind": "suggestion",
            # The exact place the answer belongs, never a generic destination.
            "route": _text(s.get("route") or s.get("action_route"), 300) or None,
            "suggestion_id": _text(s.get("id"), 80) or None,
            "at": _text(s.get("created_at") or s.get("updated_at"), 40) or None,
        })
    return rows


def _clarification_rows(memory: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Beliefs ORA holds but is not sure of, and can resolve by asking."""
    rows: List[Dict[str, Any]] = []
    for m in (memory or {}).get("memories") or []:
        if m.get("status") != "ambiguous" or not m.get("clarifiable"):
            continue
        # The phrasing written for a person, never the goal written for the core.
        statement = _text(m.get("statement")) or _text(m.get("belief_statement"))
        if not statement:
            continue
        rows.append({
            "id": f"memory:{m.get('id')}",
            "title": statement,
            "detail": "",
            "needs_consent": False,
            "kind": "memory_clarification",
            "memory_id": _text(m.get("id"), 80),
            "at": _text(m.get("updated_at") or m.get("learned_at"), 40) or None,
        })
    return rows


# --- waiting -----------------------------------------------------------------


def _waiting_rows(home: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    """Things that genuinely cannot move yet — and nothing else.

    A future date is not a dependency: an exam on the 12th is not "waiting" for
    anything, it is simply not due yet, and that belongs in PROSSIME SCADENZE.
    Confusing the two would make this section as wide as "everything with a
    date attached", which is not what a trust page can afford to be vague
    about.

    Two structured signals qualify a row instead. `goal_blockers` is a named
    obstacle Home already records on the goal. `status == "waiting"` is the
    item's own state, set deliberately by the adapters that own a real
    dependency — a postponed decision, a deferred document action, a
    "remind me later" calendar reply — never inferred from a date. The one
    thing that also produces `status == "waiting"` without meaning any of that
    is the user's own snooze, marked by `meta.snoozed_until`; that is a choice
    about attention, not a blocker, so it is excluded explicitly rather than
    trusted to look different from the rest.
    """
    rows: List[Dict[str, Any]] = []
    for group in home.get("priorities") or []:
        for item in group.get("items") or []:
            title = _text(item.get("title"))
            if not title:
                continue

            blockers = [b for b in (item.get("goal_blockers") or []) if _text(b)]
            if blockers:
                rows.append({
                    "id": f"item:{item.get('id')}",
                    "title": title,
                    "waiting_for": _text(blockers[0], 140),
                    "when": None,
                    "route": _route_for_item(item),
                })
                continue

            meta = item.get("meta") or {}
            if item.get("status") == "waiting" and not meta.get("snoozed_until"):
                rows.append({
                    "id": f"item:{item.get('id')}",
                    "title": title,
                    "waiting_for": "",
                    "when": None,
                    "route": _route_for_item(item),
                })
    return rows[:MAX_WAITING]


def _route_for_item(item: Dict[str, Any]) -> Optional[str]:
    """Where this item already lives — Attività never invents a destination."""
    for action in item.get("actions") or []:
        route = _text(action.get("route"), 300)
        if route:
            return route
    plan_id = (item.get("meta") or {}).get("life_os_plan_id")
    return f"/goal-workspace/{plan_id}" if plan_id else None


# --- updates and completions -------------------------------------------------


def _update_rows(
    memory: Optional[Dict[str, Any]],
    home: Dict[str, Any],
    now: datetime,
) -> List[Dict[str, Any]]:
    """What has actually changed lately, told as events a person recognises.

    `actor` is the honest part. ORA authoring something and ORA noticing that
    something changed are different claims, and the copy the client writes
    depends on which one this is — so the distinction is decided here, from
    where the record came from, rather than being guessed from wording.
    """
    rows: List[Dict[str, Any]] = []

    for m in (memory or {}).get("memories") or []:
        if m.get("status") == "superseded":
            continue
        statement = _text(m.get("belief_statement")) or _text(m.get("statement"))
        at = _text(m.get("updated_at") or m.get("learned_at"), 40)
        if not statement or not at:
            continue
        age = _age_days(at, now)
        if age is None or age > UPDATE_WINDOW_DAYS:
            continue
        rows.append({
            "id": f"memory:{m.get('id')}",
            "title": statement,
            "context": _text(m.get("group_label"), 80),
            # ORA learned this; it did not do it. "Risulta" is the true verb.
            "actor": "observed",
            "at": at,
            "route": None,
        })

    for s in home.get("ora_ti_consiglia") or []:
        delivery = str(((s.get("meta") or {}).get("delivery") or "")).strip()
        if delivery in (DELIVERY_QUESTION, DELIVERY_CONSENT):
            continue  # already a question, not an update
        title = _text(s.get("title"))
        at = _text(s.get("created_at") or s.get("updated_at"), 40)
        if not title or not at:
            continue
        age = _age_days(at, now)
        if age is None or age > UPDATE_WINDOW_DAYS:
            continue
        rows.append({
            "id": f"suggestion:{s.get('id')}",
            "title": title,
            "context": _text(s.get("reason"), 120),
            # ORA prepared this one itself.
            "actor": "ora",
            "at": at,
            "route": _text(s.get("route"), 300) or None,
        })

    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows[:MAX_UPDATES]


# --- deadlines ---------------------------------------------------------------


def _deadline_rows(home: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    """Dates that are coming, chronologically, from what Home already holds."""
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    pools = [[home.get("primary_focus")] if home.get("primary_focus") else []]
    pools += [group.get("items") or [] for group in home.get("priorities") or []]
    for pool in pools:
        for item in pool:
            if not item:
                continue
            when = _parse(item.get("due_at") or item.get("start_at"))
            title = _text(item.get("title"))
            if not when or not title or when < now:
                continue
            key = str(item.get("id"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "id": f"item:{item.get('id')}",
                "title": title,
                "at": when.isoformat(),
                "route": _route_for_item(item),
            })
    rows.sort(key=lambda r: r["at"])
    return rows[:MAX_DEADLINES]


async def _completed_rows(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """What was finished recently.

    The one thing no existing surface can answer. Completion is recorded on the
    item state (`status: completed`), and Home then filters those items out of
    every payload — correctly, since a finished thing is not a priority — which
    leaves the record real but unreachable and titleless. The titles live in the
    Home snapshot that was current when the item existed, so the two are joined
    here. Bounded by a short window and a small count: this is "recently", not a
    history.
    """
    rows: List[Dict[str, Any]] = []
    try:
        cursor = (
            db.home_item_state.find(
                {"user_id": user_id, "status": "completed"},
                {"_id": 0, "item_id": 1, "updated_at": 1},
            )
            .sort("updated_at", -1)
            .limit(MAX_COMPLETED * 4)
        )
        states = await cursor.to_list(MAX_COMPLETED * 4)
    except Exception:
        logger.info("activity completed state read soft-fail")
        return rows

    fresh = []
    for st in states:
        age = _age_days(st.get("updated_at"), now)
        if age is not None and age <= COMPLETED_WINDOW_DAYS:
            fresh.append(st)
    if not fresh:
        return rows

    titles: Dict[str, str] = {}
    wanted = {str(s.get("item_id")) for s in fresh}
    try:
        # Ask for the snapshots that actually contain these items rather than
        # the most recent few and hoping. Home drops a completed item from every
        # subsequent build, so its title only survives in snapshots taken while
        # it was still open — which are not necessarily the latest ones. Still
        # bounded: at most a handful of documents, matched on an indexed user
        # plus a direct array membership test.
        snaps = (
            await db.home_snapshots.find(
                {"user_id": user_id, "items.id": {"$in": list(wanted)}},
                {"_id": 0, "items": 1, "generated_at": 1},
            )
            .sort("generated_at", -1)
            .limit(5)
            .to_list(5)
        )
        for snap in snaps:
            for item in snap.get("items") or []:
                iid = str(item.get("id") or "")
                if iid not in wanted or iid in titles:
                    continue
                # A résumé card is an invitation back into an open
                # conversation, not an outcome — it says "Continua", and
                # closing that conversation later is not something the person
                # did on purpose that ORA should report as a result. Only
                # entity-backed work items belong in a completed list.
                if item.get("type") == "resume" or item.get("source_type") == "conversation_session":
                    continue
                title = _text(item.get("title"))
                if title:
                    titles[iid] = title
    except Exception:
        logger.info("activity completed title read soft-fail")

    for st in fresh:
        iid = str(st.get("item_id"))
        title = titles.get(iid)
        if not title:
            continue  # a completion we cannot name is not one we can show
        rows.append({
            "id": f"item:{iid}",
            "title": title,
            "at": _text(st.get("updated_at"), 40),
        })
        if len(rows) >= MAX_COMPLETED:
            break
    return rows


# --- assembly ----------------------------------------------------------------


def _dedupe(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per real identity.

    Identity only: the composed `id` carries the source system and that
    system's own key, so the same record reached through two paths collapses
    and two genuinely different records never do. Nothing here compares titles.
    """
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = str(row.get("id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


async def build_activity(db, user_id: str) -> Dict[str, Any]:
    """The whole page, from systems that already exist.

    Resilient by section: a source that fails costs its own rows and marks the
    payload partial, never the page. Attività is where a user checks whether
    anything is waiting on them — going blank because one store hiccuped would
    be the least honest possible failure.
    """
    now = _now()
    partial: List[str] = []

    home: Dict[str, Any] = {}
    try:
        from home.router import get_home_service

        home = (await get_home_service().build_home(user_id)).model_dump()
    except Exception as e:
        logger.warning("activity home source failed: %s", type(e).__name__)
        partial.append("home")

    memory: Optional[Dict[str, Any]] = None
    try:
        from life_memory.service import get_life_memory_service

        memory = (await get_life_memory_service().get_life_memory(user_id)).model_dump()
    except Exception as e:
        logger.warning("activity memory source failed: %s", type(e).__name__)
        partial.append("life_memory")

    questions = _dedupe(
        _open_question_rows(home.get("open_questions") or [])
        + _question_rows(home)
        + _clarification_rows(memory)
    )[:MAX_QUESTIONS]
    waiting = _dedupe(_waiting_rows(home, now))
    updates = _dedupe(_update_rows(memory, home, now))
    deadlines = _dedupe(_deadline_rows(home, now))
    completed = _dedupe(await _completed_rows(db, user_id, now))

    focus = home.get("primary_focus")
    attention = None
    if focus and _text(focus.get("title")):
        attention = {
            "id": f"item:{focus.get('id')}",
            "item_id": _text(focus.get("id"), 80),
            "title": _text(focus.get("title")),
            "detail": _text(focus.get("description") or focus.get("reason_summary")),
            # The actions Home already offers; Attività adds none of its own.
            "actions": [
                {
                    "kind": _text(a.get("kind"), 40),
                    "label": _text(a.get("label"), 60),
                    "route": _text(a.get("route"), 300) or None,
                }
                for a in (focus.get("actions") or [])
                if _text(a.get("kind"))
            ],
            "visual": focus.get("visual"),
        }

    # Only what is countable from what is on the page above it.
    # `icon` is a presentation hint emitted next to the row it belongs to, so
    # the client never has to read the label to decide what to draw — matching
    # words would be a classifier in the interface, and a fragile one.
    summary: List[Dict[str, Any]] = []
    todo = len(questions) + (1 if attention else 0)
    if todo:
        summary.append({"label": "Da fare", "value": todo, "icon": "todo"})
    if waiting:
        summary.append({"label": "In attesa", "value": len(waiting), "icon": "waiting"})
    if completed:
        summary.append({
            "label": "Completate di recente",
            "value": len(completed),
            "icon": "done",
        })

    return {
        "ok": True,
        "attention": attention,
        "questions": questions,
        "waiting": waiting,
        "updates": updates,
        "deadlines": deadlines,
        "completed": completed,
        "summary": summary,
        "partial": bool(partial),
        "partial_sources": partial,
        "generated_at": now.isoformat(),
    }
