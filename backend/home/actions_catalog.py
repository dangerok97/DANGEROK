"""Type-specific dynamic actions — no dead/generic identical button sets."""
from __future__ import annotations

from typing import List

from .models import HomeAction, HomeItem


def actions_for(item: HomeItem) -> List[HomeAction]:
    t = item.type
    sid = item.source_id
    base_open = HomeAction(
        id="open_source",
        label="Apri",
        kind="open",
        route=_route_for(item),
        primary=False,
    )
    snooze = HomeAction(id="snooze", label="Rimanda", kind="snooze")
    ignore = HomeAction(id="ignore", label="Ignora", kind="ignore")
    complete = HomeAction(id="complete", label="Fatto", kind="complete", primary=True)
    correct = HomeAction(id="correct", label="Correggi priorità", kind="correct")

    if t == "event":
        acts = [
            HomeAction(id="open_event", label="Apri evento", kind="navigate", route=_route_for(item), primary=True),
            HomeAction(id="open_maps", label="Apri Maps", kind="maps", params={"query": item.location or item.title}),
            HomeAction(id="open_calendar", label="Calendario", kind="navigate", route="/settings"),
            snooze,
        ]
        if item.location:
            return acts
        return [a for a in acts if a.id != "open_maps"]

    if t == "visit":
        acts = [
            HomeAction(id="open_visit", label="Dettagli visita", kind="navigate", route=_route_for(item), primary=True),
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
            HomeAction(id="open_travel", label="Vedi viaggio", kind="navigate", route=_route_for(item), primary=True),
            HomeAction(id="open_maps", label="Apri Maps", kind="maps", params={"query": item.location or item.title}),
            snooze,
        ]

    if t in ("bill", "payment"):
        return [
            HomeAction(id="mark_paid", label="Segna pagata", kind="complete", primary=True),
            HomeAction(id="open_doc", label="Apri documento", kind="navigate", route=f"/document/{sid}"),
            snooze,
            correct,
        ]

    if t == "study":
        return [
            HomeAction(id="flashcards", label="Flashcard", kind="study", route=f"/document/{sid}", params={"mode": "flashcards"}, primary=True),
            HomeAction(id="quiz", label="Interrogami", kind="study", route=f"/document/{sid}", params={"mode": "quiz"}),
            HomeAction(id="open_doc", label="Apri materiale", kind="navigate", route=f"/document/{sid}"),
            snooze,
        ]

    if t in ("needs_review", "verify"):
        return [
            HomeAction(id="review", label="Verifica", kind="navigate", route=f"/document/{sid}", primary=True),
            HomeAction(id="confirm_event", label="Conferma", kind="confirm", route=f"/document/{sid}"),
            ignore,
        ]

    if t == "reply":
        return [
            HomeAction(id="reply", label="Rispondi", kind="navigate", route=_route_for(item), primary=True),
            snooze,
            ignore,
        ]

    if t == "activity":
        return [complete, snooze, ignore, correct]

    if t == "resume":
        return [
            HomeAction(id="resume", label="Continua", kind="resume", route=_route_for(item), primary=True),
            ignore,
        ]

    # generic — minimal real actions only
    return [complete, base_open, snooze, ignore]


def _route_for(item: HomeItem) -> str:
    st = item.source_type
    sid = item.source_id
    if st in ("document", "event_candidate", "document_action", "study", "admin"):
        return f"/document/{sid}"
    if st in ("decision",):
        return "/(tabs)"
    if st in ("life_node", "google_calendar", "internal_calendar"):
        return "/situazione"
    if st == "quiz_session":
        return f"/document/{item.meta.get('document_id', sid)}"
    return "/(tabs)"
