"""Type-specific dynamic actions — no dead/generic identical button sets."""
from __future__ import annotations

from typing import List

from .models import HomeAction, HomeItem


def actions_for(item: HomeItem) -> List[HomeAction]:
    t = item.type
    sid = item.source_id
    # Guided Action Engine entry — never an empty page
    guide = HomeAction(
        id="guide",
        label="Inizia",
        kind="guide",
        route="/action/open",
        params={"via": "action_engine"},
        primary=True,
    )
    organize = HomeAction(
        id="organize",
        label="Organizza",
        kind="guide",
        route="/action/open",
        params={"via": "action_engine"},
    )
    base_open = HomeAction(
        id="open_source",
        label="Apri",
        kind="guide",
        route="/action/open",
        params={"via": "action_engine"},
        primary=False,
    )
    snooze = HomeAction(id="snooze", label="Rimanda", kind="snooze")
    ignore = HomeAction(id="ignore", label="Ignora", kind="ignore")
    complete = HomeAction(id="complete", label="Fatto", kind="complete", primary=True)
    correct = HomeAction(id="correct", label="Correggi priorità", kind="correct")

    if item.source_type == "action_session":
        return [
            HomeAction(
                id="resume_ae", label="Continua", kind="resume",
                route=f"/action/{sid}", primary=True,
            ),
            ignore,
        ]

    if t == "event":
        acts = [
            HomeAction(id="open_event", label="Organizza", kind="guide", route="/action/open", primary=True),
            HomeAction(id="open_maps", label="Apri Maps", kind="maps", params={"query": item.location or item.title}),
            snooze,
        ]
        if item.location:
            return acts
        return [a for a in acts if a.id != "open_maps"]

    if t == "visit":
        acts = [
            HomeAction(id="open_visit", label="Organizza visita", kind="guide", route="/action/open", primary=True),
            snooze,
            ignore,
        ]
        if item.location:
            acts.insert(1, HomeAction(
                id="open_maps", label="Indicazioni", kind="maps",
                params={"query": item.location},
            ))
        return acts

    if t == "travel":
        return [
            HomeAction(id="open_travel", label="Organizza viaggio", kind="guide", route="/action/open", primary=True),
            HomeAction(id="open_maps", label="Apri Maps", kind="maps", params={"query": item.location or item.title}),
            snooze,
        ]

    if t in ("bill", "payment"):
        return [
            HomeAction(id="organize_bill", label="Organizza", kind="guide", route="/action/open", primary=True),
            HomeAction(id="mark_paid", label="Segna pagata", kind="complete"),
            HomeAction(id="open_doc", label="Apri documento", kind="navigate", route=f"/document/{sid}"),
            snooze,
            correct,
        ]

    if t == "study" and item.source_type == "study_plan":
        acts = [
            HomeAction(
                id="open_plan", label="Apri piano", kind="navigate",
                route=f"/study-plan/{sid}", primary=True,
            ),
        ]
        next_s = (item.meta or {}).get("next_session") or {}
        if next_s.get("id"):
            acts.append(HomeAction(
                id="start_session", label="Inizia sessione", kind="study",
                route=f"/study-plan/{sid}", params={"session_id": next_s["id"], "action": "start"},
            ))
        fc_ids = (item.meta or {}).get("flashcard_document_ids") or []
        iq_ids = (item.meta or {}).get("interrogami_document_ids") or []
        if fc_ids:
            acts.append(HomeAction(
                id="flashcards", label="Flashcard", kind="study",
                route=f"/document/{fc_ids[0]}", params={"mode": "flashcards"},
            ))
        if iq_ids:
            acts.append(HomeAction(
                id="quiz", label="Interrogami", kind="study",
                route=f"/document/{iq_ids[0]}", params={"mode": "quiz"},
            ))
        acts.append(snooze)
        return acts

    if t == "study":
        return [
            guide,
            HomeAction(id="flashcards", label="Flashcard", kind="study", route=f"/document/{sid}", params={"mode": "flashcards"}),
            HomeAction(id="quiz", label="Interrogami", kind="study", route=f"/document/{sid}", params={"mode": "quiz"}),
            snooze,
        ]

    if t in ("needs_review", "verify"):
        return [
            HomeAction(id="review", label="Verifica", kind="guide", route="/action/open", primary=True),
            HomeAction(id="open_doc", label="Apri documento", kind="navigate", route=f"/document/{sid}"),
            ignore,
        ]

    if t == "reply":
        return [
            HomeAction(id="reply", label="Organizza risposta", kind="guide", route="/action/open", primary=True),
            snooze,
            ignore,
        ]

    if t == "activity":
        return [guide, complete, snooze, ignore, correct]

    if t == "resume":
        route = _route_for(item)
        return [
            HomeAction(id="resume", label="Continua", kind="resume", route=route, primary=True),
            ignore,
        ]

    # generic — always guided, never empty
    return [guide, organize, complete, snooze, ignore]


def _route_for(item: HomeItem) -> str:
    st = item.source_type
    sid = item.source_id
    if st == "action_session":
        return f"/action/{sid}"
    if st == "action_project":
        return "/action/open"
    if st in ("document", "event_candidate", "document_action", "study", "admin"):
        return f"/document/{sid}"
    if st in ("decision",):
        return "/(tabs)"
    if st in ("life_node", "google_calendar", "internal_calendar"):
        return "/situazione"
    if st == "quiz_session":
        return f"/document/{item.meta.get('document_id', sid)}"
    return "/action/open"
