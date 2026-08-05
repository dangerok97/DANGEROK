"""Side effects after flow completion — calendar, reminders, decisions, study hooks."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from action_engine.models import ProposedAction, now_iso
from action_engine.projects import update_project_links

logger = logging.getLogger("ora.action_engine.effects")


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _parse_window(code: str) -> datetime:
    now = datetime.now(timezone.utc)
    mapping = {
        "in_3_days": 3,
        "in_1_week": 7,
        "in_2_weeks": 14,
        "in_1_month": 30,
        "already_set": 14,
    }
    days = mapping.get(str(code), 7)
    return now + timedelta(days=days)


def _reminder_offset(code: str) -> Optional[timedelta]:
    return {
        "1h": timedelta(hours=1),
        "2h": timedelta(hours=2),
        "3h": timedelta(hours=3),
        "1d": timedelta(days=1),
        "3d": timedelta(days=3),
        "due_morning": timedelta(days=0),
        "morning": timedelta(hours=8),
        "none": None,
    }.get(str(code), timedelta(days=1))


async def _create_life_event(
    life_graph,
    *,
    user_id: str,
    title: str,
    starts_at: datetime,
    location: Optional[str] = None,
    attributes: Optional[dict] = None,
) -> dict:
    attrs = {
        "starts_at": starts_at.isoformat(),
        "start_at": starts_at.isoformat(),
        **(attributes or {}),
    }
    if location:
        attrs["location"] = location
    return await life_graph.create_node(
        user_id,
        type="event",
        label=title[:120],
        description="Creato da Action Engine",
        attributes=attrs,
        origin="action_engine",
    )


async def _create_reminder(
    db,
    *,
    user_id: str,
    title: str,
    due_at: datetime,
    meta: Optional[dict] = None,
) -> dict:
    doc = {
        "id": _uid("rem"),
        "user_id": user_id,
        "title": title[:160],
        "status": "open",
        "due_at": due_at.isoformat(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "origin": "action_engine",
        "meta": meta or {},
    }
    await db.reminders.insert_one(doc)
    return doc


async def _create_decision(
    decisions,
    *,
    user_id: str,
    title: str,
    kind: str,
    due_at: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    try:
        payload = {
            "title": title[:160],
            "category": kind,
            "urgency": 3,
            "importance": 3,
            "metadata": {**(metadata or {}), "action_engine_kind": kind},
        }
        if due_at:
            payload["deadline"] = due_at
        return await decisions.create(user_id, payload, origin="action_engine")
    except Exception as e:
        logger.warning("decision create failed: %s", type(e).__name__)
        return None


async def apply_completion_effects(
    *,
    db,
    life_graph,
    knowledge,
    decisions,
    session: dict,
) -> Tuple[List[ProposedAction], Dict[str, Any]]:
    """Run category-specific side effects. Honest about blocked hooks."""
    flow = session.get("flow") or "generic"
    answers = session.get("answers") or {}
    title = session.get("title") or "Priorità"
    user_id = session["user_id"]
    location = session.get("meta", {}).get("location") or session.get("location")
    project_id = (session.get("project") or {}).get("project_id")
    actions: List[ProposedAction] = []
    effects: Dict[str, Any] = {"calendar_ids": [], "reminder_ids": [], "decision_ids": [], "study": {}}
    next_hint = None

    if flow == "study":
        exam_at = _parse_window(answers.get("exam_date", "in_1_week"))
        hours = float(answers.get("hours_per_day") or 1)
        pace = answers.get("pace") or "distributed"
        # Build 2–4 study sessions before exam
        days_until = max(1, (exam_at - datetime.now(timezone.utc)).days)
        n_sessions = 4 if pace == "distributed" else 3 if pace == "mixed" else 2
        session_ids = []
        for i in range(n_sessions):
            # Spread sessions; last one day before exam
            if pace == "intense":
                offset = max(0, days_until - (n_sessions - i))
            else:
                offset = int((days_until / (n_sessions + 1)) * (i + 1))
            start = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=offset)
            if start >= exam_at:
                start = exam_at - timedelta(hours=24)
            node = await _create_life_event(
                life_graph,
                user_id=user_id,
                title=f"Sessione {i + 1}: {title}",
                starts_at=start,
                attributes={
                    "duration_minutes": int(hours * 60),
                    "kind": "study_session",
                    "action_session_id": session.get("id"),
                },
            )
            session_ids.append(node["id"])
            actions.append(ProposedAction(
                id=f"cal_{node['id']}",
                kind="calendar",
                label=f"Sessione {i + 1} in calendario",
                detail=start.isoformat(),
                status="done",
                meta={"node_id": node["id"]},
            ))
        effects["calendar_ids"] = session_ids
        rem = await _create_reminder(
            db, user_id=user_id,
            title=f"Ripasso: {title}",
            due_at=exam_at - timedelta(days=1),
            meta={"kind": "study_review"},
        )
        effects["reminder_ids"].append(rem["id"])
        actions.append(ProposedAction(
            id=f"rem_{rem['id']}", kind="reminder", label="Promemoria ripasso",
            status="done", meta={"reminder_id": rem["id"]},
        ))

        # Study tools on linked document when requested
        tools = answers.get("tools")
        use_doc = answers.get("use_uploaded", True)
        doc_id = session.get("source_id") if session.get("source_type") in (
            "document", "study", "document_action", "quiz_session",
        ) else None
        if doc_id and use_doc and tools in ("plan_flash", "quiz"):
            try:
                from deps import get_intelligence_service
                intel = get_intelligence_service()
                if tools == "plan_flash":
                    res = await intel.study_action(user_id=user_id, doc_id=doc_id, action="flashcards")
                    effects["study"]["flashcards"] = True
                    actions.append(ProposedAction(
                        id="study_flash", kind="study", label="Flashcard generate",
                        status="done" if res else "blocked",
                        meta={"document_id": doc_id},
                    ))
                elif tools == "quiz":
                    res = await intel.study_action(user_id=user_id, doc_id=doc_id, action="quiz_start")
                    effects["study"]["quiz"] = True
                    actions.append(ProposedAction(
                        id="study_quiz", kind="study", label="Quiz pronto",
                        status="done" if res else "blocked",
                        meta={"document_id": doc_id},
                    ))
            except Exception as e:
                logger.info("study hook blocked: %s", type(e).__name__)
                actions.append(ProposedAction(
                    id="study_blocked", kind="study",
                    label="Studio collegato non disponibile ora",
                    detail="Apri il documento per flashcard/quiz manualmente.",
                    status="blocked",
                ))

        if session_ids:
            first = await db.life_nodes.find_one({"id": session_ids[0]}, {"_id": 0})
            when = (first or {}).get("attributes", {}).get("starts_at")
            next_hint = f"Sessione 1 oggi/prossimamente" if when else f"Piano studio: {title}"
            # More precise hint
            try:
                st = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
                today = datetime.now(timezone.utc).date()
                if st.date() == today:
                    next_hint = f"Sessione 1 oggi {st.strftime('%H:%M')}"
                else:
                    days = (st.date() - today).days
                    next_hint = f"Sessione 1 tra {days}g · esame tra {days_until}g"
            except Exception:
                pass

        dec = await _create_decision(
            decisions, user_id=user_id,
            title=f"Studio: {title}",
            kind="study",
            due_at=exam_at.isoformat(),
            metadata={"action_session_id": session.get("id"), "project_id": project_id},
        )
        if dec:
            effects["decision_ids"].append(dec.get("id"))

    elif flow == "event":
        start_raw = session.get("meta", {}).get("start_at") or session.get("start_at")
        try:
            start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00")) if start_raw else datetime.now(timezone.utc) + timedelta(days=1)
        except Exception:
            start = datetime.now(timezone.utc) + timedelta(days=1)
        if answers.get("add_calendar") in (True, "yes") or answers.get("add_calendar") is True:
            node = await _create_life_event(
                life_graph, user_id=user_id, title=title, starts_at=start, location=location,
                attributes={"kind": "event", "action_session_id": session.get("id")},
            )
            effects["calendar_ids"].append(node["id"])
            actions.append(ProposedAction(
                id=f"cal_{node['id']}", kind="calendar", label="Evento in calendario",
                status="done", meta={"node_id": node["id"]},
            ))
        rem_code = answers.get("reminder")
        off = _reminder_offset(rem_code) if rem_code else None
        if off is not None and str(rem_code) != "none":
            rem = await _create_reminder(
                db, user_id=user_id, title=f"Promemoria: {title}",
                due_at=start - off, meta={"kind": "event"},
            )
            effects["reminder_ids"].append(rem["id"])
            actions.append(ProposedAction(
                id=f"rem_{rem['id']}", kind="reminder", label="Promemoria evento",
                status="done",
            ))
        leave = answers.get("leave_time")
        if leave and leave not in ("no", False, None):
            try:
                mins = int(leave)
            except Exception:
                mins = 30
            leave_at = start - timedelta(minutes=mins)
            rem = await _create_reminder(
                db, user_id=user_id, title=f"Parti per: {title}",
                due_at=leave_at, meta={"kind": "leave_time"},
            )
            effects["reminder_ids"].append(rem["id"])
            actions.append(ProposedAction(
                id=f"leave_{rem['id']}", kind="reminder", label="Orario partenza",
                detail=leave_at.isoformat(), status="done",
            ))
        if answers.get("need_route") in (True, "yes"):
            actions.append(ProposedAction(
                id="maps", kind="maps", label="Apri Maps",
                status="proposed",
                meta={"query": location or title},
            ))
        next_hint = f"Evento: {title}"

    elif flow == "travel":
        dest = answers.get("destination") or location or title
        if dest == "from_title":
            dest = title
        start = datetime.now(timezone.utc) + timedelta(days=3)
        if answers.get("prep") in ("calendar", "all"):
            node = await _create_life_event(
                life_graph, user_id=user_id,
                title=f"Viaggio: {dest}",
                starts_at=start,
                location=str(dest),
                attributes={"kind": "travel", "transport": answers.get("transport")},
            )
            effects["calendar_ids"].append(node["id"])
            actions.append(ProposedAction(
                id=f"cal_{node['id']}", kind="calendar", label="Viaggio in calendario",
                status="done",
            ))
            rem = await _create_reminder(
                db, user_id=user_id, title=f"Prepara viaggio: {dest}",
                due_at=start - timedelta(days=1), meta={"kind": "travel"},
            )
            effects["reminder_ids"].append(rem["id"])
        if answers.get("prep") in ("luggage", "all"):
            dec = await _create_decision(
                decisions, user_id=user_id,
                title=f"Lista bagagli: {dest}",
                kind="travel",
                metadata={"checklist": ["documenti", "caricatore", "farmaci base", "abbigliamento"]},
            )
            if dec:
                effects["decision_ids"].append(dec.get("id"))
                actions.append(ProposedAction(
                    id=f"dec_{dec.get('id')}", kind="decision", label="Lista bagagli",
                    status="done",
                ))
        if answers.get("prep") in ("docs", "all"):
            actions.append(ProposedAction(
                id="travel_docs", kind="document",
                label="Controlla documenti di viaggio",
                detail="Passaporto/CI/biglietti — verifica sui tuoi documenti ORA se presenti.",
                status="proposed",
            ))
        # Weather: honest placeholder without credentials
        actions.append(ProposedAction(
            id="weather", kind="blocked",
            label="Meteo destinazione",
            detail="Richiede integrazione meteo (non configurata).",
            status="blocked",
        ))
        next_hint = f"Viaggio: {dest}"

    elif flow == "medical":
        # NEVER medical advice — logistics only
        if answers.get("confirm_visit") == "cancel":
            actions.append(ProposedAction(
                id="cancelled", kind="decision", label="Visita archiviata dalla guida",
                status="done",
            ))
            next_hint = None
        else:
            start_raw = session.get("meta", {}).get("start_at") or session.get("start_at")
            try:
                start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00")) if start_raw else datetime.now(timezone.utc) + timedelta(days=2)
            except Exception:
                start = datetime.now(timezone.utc) + timedelta(days=2)
            if answers.get("add_calendar") in (True, "yes") or answers.get("add_calendar") is True:
                node = await _create_life_event(
                    life_graph, user_id=user_id, title=f"Visita: {title}",
                    starts_at=start, location=location,
                    attributes={"kind": "visit", "medical_advice": False},
                )
                effects["calendar_ids"].append(node["id"])
                actions.append(ProposedAction(
                    id=f"cal_{node['id']}", kind="calendar", label="Visita in calendario",
                    status="done",
                ))
            if answers.get("need_maps") in (True, "yes"):
                actions.append(ProposedAction(
                    id="maps", kind="maps", label="Indicazioni",
                    status="proposed", meta={"query": location or title},
                ))
            if answers.get("documents") in (True, "yes", "on_ora"):
                rem = await _create_reminder(
                    db, user_id=user_id,
                    title=f"Documenti per visita: {title}",
                    due_at=start - timedelta(hours=12),
                    meta={"kind": "visit_docs", "no_medical_advice": True},
                )
                effects["reminder_ids"].append(rem["id"])
            rem_code = answers.get("reminder")
            off = _reminder_offset(rem_code) if rem_code else None
            if off is not None and str(rem_code) != "none":
                rem = await _create_reminder(
                    db, user_id=user_id, title=f"Promemoria visita: {title}",
                    due_at=start - off, meta={"kind": "visit", "no_medical_advice": True},
                )
                effects["reminder_ids"].append(rem["id"])
            next_hint = f"Visita: {title}"
            actions.append(ProposedAction(
                id="no_advice", kind="document",
                label="Solo logistica — nessun consiglio medico",
                status="done",
            ))

    elif flow == "admin":
        due_raw = session.get("meta", {}).get("due_at") or session.get("due_at")
        try:
            due = datetime.fromisoformat(str(due_raw).replace("Z", "+00:00")) if due_raw else datetime.now(timezone.utc) + timedelta(days=3)
        except Exception:
            due = datetime.now(timezone.utc) + timedelta(days=3)
        if answers.get("payment_status") == "done":
            actions.append(ProposedAction(
                id="paid", kind="decision", label="Segnato come già fatto", status="done",
            ))
        else:
            if answers.get("calendar") in (True, "yes") or answers.get("calendar") is True:
                node = await _create_life_event(
                    life_graph, user_id=user_id, title=f"Scadenza: {title}",
                    starts_at=due, attributes={"kind": "admin_deadline"},
                )
                effects["calendar_ids"].append(node["id"])
                actions.append(ProposedAction(
                    id=f"cal_{node['id']}", kind="calendar", label="Scadenza in calendario",
                    status="done",
                ))
            rem_code = answers.get("reminder")
            off = _reminder_offset(rem_code) if rem_code else None
            if off is not None and str(rem_code) != "none":
                rem = await _create_reminder(
                    db, user_id=user_id, title=f"Promemoria: {title}",
                    due_at=due - off if off else due, meta={"kind": "admin"},
                )
                effects["reminder_ids"].append(rem["id"])
            if answers.get("understand") == "explain":
                actions.append(ProposedAction(
                    id="explain", kind="document",
                    label="Apri documento per spiegazione",
                    detail="Usa l'analisi documenti esistente — nessuna invenzione.",
                    status="proposed",
                    meta={"document_id": session.get("source_id")},
                ))
            dec = await _create_decision(
                decisions, user_id=user_id, title=f"Admin: {title}",
                kind="admin", due_at=due.isoformat(),
                metadata={"action_session_id": session.get("id")},
            )
            if dec:
                effects["decision_ids"].append(dec.get("id"))
        next_hint = f"Pratica: {title}"

    else:  # generic
        intent = answers.get("intent") or "organize"
        when = answers.get("when") or "today"
        days = {"now": 0, "today": 0, "this_week": 3, "later": 7}.get(str(when), 1)
        due = datetime.now(timezone.utc) + timedelta(days=days)
        if intent == "done":
            actions.append(ProposedAction(
                id="done", kind="decision", label="Puoi segnare fatto da Home", status="proposed",
            ))
        else:
            if answers.get("support") in ("reminder", "checklist", "project") or intent == "remind":
                rem = await _create_reminder(
                    db, user_id=user_id, title=title, due_at=due, meta={"kind": "generic"},
                )
                effects["reminder_ids"].append(rem["id"])
                actions.append(ProposedAction(
                    id=f"rem_{rem['id']}", kind="reminder", label="Promemoria creato", status="done",
                ))
            if intent == "calendar" or answers.get("support") == "project":
                node = await _create_life_event(
                    life_graph, user_id=user_id, title=title, starts_at=due,
                    attributes={"kind": "generic"},
                )
                effects["calendar_ids"].append(node["id"])
            if answers.get("support") == "checklist":
                dec = await _create_decision(
                    decisions, user_id=user_id, title=f"Checklist: {title}",
                    kind="generic", metadata={"checklist": ["Definisci il prossimo passo", "Raccogli ciò che serve", "Esegui"]},
                )
                if dec:
                    effects["decision_ids"].append(dec.get("id"))
        next_hint = title

    if project_id:
        await update_project_links(
            db, project_id, user_id,
            calendar_event_ids=effects.get("calendar_ids"),
            reminder_ids=effects.get("reminder_ids"),
            decision_ids=effects.get("decision_ids"),
            flashcard_doc_ids=[session["source_id"]] if effects.get("study", {}).get("flashcards") else None,
            answers=answers,
            next_focus_hint=next_hint,
        )

    effects["next_focus_hint"] = next_hint
    effects["home_invalidate"] = True
    return actions, effects
