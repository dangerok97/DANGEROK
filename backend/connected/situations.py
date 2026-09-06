"""
Where several sources turn out to be talking about the same thing.

    MULTIPLE SOURCES CAN REFER TO THE SAME THING IN A PERSON'S LIFE.

An appointment in a calendar, an email about it, and the document it asks
somebody to bring are three readings of one afternoon. Until now ORA held
them as three unrelated arrivals, which is not a small imprecision: it is the
difference between "you have three notifications" and "the visit moved, and
what they asked you to bring is already in your documents".

This module does the half of that which is code's to do, and stops.

**Code gathers candidates.** What else is going on around this signal —
appointments near it in time, documents recently filed, situations already
known. Each candidate is a handful of facts with its own provenance and its
own freshness. Nothing here is scored, ranked or filtered by resemblance: a
candidate set is a retrieval bound, not an opinion, and the bounds used are
time and count because those are the two that are not about meaning.

**The model decides the relationship.** Same situation, related, new,
irrelevant, or — the answer that must remain available — uncertain. There is
deliberately no code path that picks a target when the model declines to:
a link nobody was confident about is worse than no link, because everything
downstream then reasons about a conversation that was never had.

    NO LINK IS EVER MADE BY A STRING MATCH.

**Disagreements are recorded, never resolved.** When a linked pair state
different times for the same thing, both statements are kept with when each
was observed and how directly each knows. Which one is true is a judgement,
and a judgement made by a table of source weights would be a system that
quietly believes email over calendars, or the reverse, forever.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from connected.models import ConnectedSignal, now_iso

logger = logging.getLogger("ora.connected.situations")

LINKS = "connected_situation_links"

# Il fuso in cui vive la persona. Sta qui perche' e' dove si mettono a
# confronto le parole di un messaggio con l'ora di un calendario, e le due
# cose non si possono confrontare in fusi diversi.
_HOME_TZ = os.environ.get("ORA_DEFAULT_TZ", "Europe/Rome")

# How far around a signal to look for something it might be about. Wide
# because an email about an appointment arrives days before it and a
# confirmation days after; bounded because this is a retrieval window and not
# a search of somebody's whole life.
LOOK_BACK_DAYS = 3
LOOK_FORWARD_DAYS = 45

# Quanti candidati per tipo arrivano al giudizio. E' un limite di costo,
# applicato per vicinanza nel tempo — un fatto sui candidati, non una
# supposizione su quale conti.
#
#     UN LIMITE TROPPO STRETTO ESCLUDE LA RISPOSTA GIUSTA IN SILENZIO.
#
# Era quattro, su una finestra che va da tre giorni prima a quarantacinque
# dopo. Un messaggio su un appuntamento arriva giorni prima di quello di cui
# parla, e nel frattempo in agenda ci sono le cose di dopodomani: i quattro
# posti se li prendevano quelle, e la visita della settimana prossima — la
# sola cosa che l'email potesse riguardare — non veniva nemmeno mostrata.
# Non c'era modo di accorgersene guardando la risposta: il modello diceva
# «situazione nuova», che sulle carte che aveva era anche corretto.
MAX_PER_KIND = 8

# What the judgement is allowed to answer. `uncertain` is first among equals:
# it is the honest answer whenever the evidence does not settle it, and
# removing it would force a guess.
LINK_OUTCOMES = (
    "same_situation", "related", "new_situation", "irrelevant", "uncertain",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _moment(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


async def candidates_for(
    db, owner_id: str, signal: ConnectedSignal,
) -> List[Dict[str, Any]]:
    """
    What else in this life is near this signal, as facts.

    Near in time and recent in filing — nothing else. A candidate finder that
    also asked "does the subject resemble the event title" would be doing the
    linking, and doing it by string, which is exactly what this design says
    a machine must not do.
    """
    found: List[Dict[str, Any]] = []
    found.extend(await _appointments_around(db, owner_id, signal))
    found.extend(await _documents_recently(db, owner_id))
    found.extend(await _situations_known(db, owner_id))
    return found


async def _appointments_around(
    db, owner_id: str, signal: ConnectedSignal,
) -> List[Dict[str, Any]]:
    """
    Appointments in the window, read from the calendar as it currently stands.

        UN CANDIDATO E' QUELLO CHE C'E', NON QUELLO CHE SI E' MOSSO.

    Questo leggeva dai segnali — il registro di cosa e' cambiato — e sono due
    insiemi diversi. Un impegno spostato tre volte li' sono tre righe e qui e'
    un impegno; uno annullato li' c'e' ancora, e veniva offerto come qualcosa
    di cui un messaggio potrebbe parlare; uno che nessuno ha piu' toccato da
    quando e' stato preso li' non c'e' affatto. Con un limite di quattro,
    l'effetto era che l'unica cosa di cui un'email poteva davvero parlare — la
    visita della settimana prossima — al giudizio non arrivava mai, e ci
    arrivavano quattro righe vecchie di eventi di prova.

    Quindi: il calendario, com'e' adesso, dentro la finestra. Gli annullati
    restano fuori — e' un fatto sulla riga, non un'opinione sul significato —
    e i piu' vicini nel tempo passano per primi, che e' l'unico ordine
    misurabile senza sapere di cosa si parli.
    """
    from ingestion.reading import plain, where

    anchor = _moment(signal.effective_at) or _moment(signal.observed_at) or _now()
    since = (anchor - timedelta(days=LOOK_BACK_DAYS)).isoformat()
    until = (anchor + timedelta(days=LOOK_FORWARD_DAYS)).isoformat()
    try:
        rows = await db.ingestion_events.find(
            {
                "user_id": owner_id,
                "source_record_type": "calendar_event",
                "ingestion_status": {"$ne": "superseded"},
                where("starts_at"): {"$gte": since, "$lte": until},
            },
            {"_id": 0, "external_id": 1, "normalized_payload": 1, "ingested_at": 1},
        ).sort(where("starts_at"), 1).to_list(60)
    except Exception as e:
        logger.info("appointment candidates soft-fail: %s", type(e).__name__)
        return []

    out: List[Dict[str, Any]] = []
    seen: set = set()
    for row in rows:
        ref = str(row.get("external_id") or "")
        if not ref or ref in seen or ref == signal.source_object_ref:
            continue
        payload = plain(row.get("normalized_payload"))
        if str(payload.get("status") or "") == "cancelled":
            continue
        title = str(payload.get("title") or "").strip()
        if not title:
            continue
        seen.add(ref)
        out.append({
            "kind": "appointment",
            "ref": ref,
            "what": title[:160],
            "when": payload.get("starts_at"),
            "whose_it_is": (
                "own" if not payload.get("attendees") else "with other people"
            ),
            "from_source": "calendar",
            "last_observed": row.get("ingested_at"),
            "how_directly_it_knows": "the calendar itself holds this appointment",
        })

    def _how_far(candidate: Dict[str, Any]) -> float:
        moment = _moment(candidate.get("when"))
        if moment is None:
            return float("inf")
        here, there = anchor, moment
        if (here.tzinfo is None) != (there.tzinfo is None):
            here = here.replace(tzinfo=here.tzinfo or timezone.utc)
            there = there.replace(tzinfo=there.tzinfo or timezone.utc)
        return abs((there - here).total_seconds())

    out.sort(key=_how_far)
    return out[:MAX_PER_KIND]


async def _documents_recently(db, owner_id: str) -> List[Dict[str, Any]]:
    """Documents on the shelf. Titles and labels; never their contents."""
    try:
        rows = await db.documents.find(
            {"user_id": owner_id, "deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "title": 1, "filename": 1, "tags": 1,
             "document_type": 1, "created_at": 1, "updated_at": 1},
        ).sort("updated_at", -1).to_list(MAX_PER_KIND)
    except Exception as e:
        logger.info("document candidates soft-fail: %s", type(e).__name__)
        return []
    return [{
        "kind": "document",
        "ref": str(r.get("id") or ""),
        "what": str(r.get("title") or r.get("filename") or "un documento")[:160],
        "labels": [str(t)[:40] for t in (r.get("tags") or [])][:4],
        "when": r.get("updated_at") or r.get("created_at"),
        "from_source": "documents",
        "last_observed": r.get("updated_at"),
        "how_directly_it_knows": "the file is in their own archive",
    } for r in rows if r.get("id")]


async def _situations_known(db, owner_id: str) -> List[Dict[str, Any]]:
    """
    Situations the Personal Life Model already holds.

    Read from the Life Object engine, which is where a situation spanning a
    document, an appointment and a goal already lives. This is deliberately a
    read: building a second place to record "these things go together" would
    be building the second graph this sprint is forbidden — and rightly, as
    the two would disagree within a week.
    """
    try:
        rows = await db.life_objects.find(
            {"user_id": owner_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "title": 1, "type": 1, "summary": 1,
             "updated_at": 1, "documents": 1, "calendar_events": 1},
        ).sort("updated_at", -1).to_list(MAX_PER_KIND)
    except Exception as e:
        logger.info("situation candidates soft-fail: %s", type(e).__name__)
        return []
    return [{
        "kind": "situation",
        "ref": str(r.get("id") or ""),
        "what": str(r.get("title") or "")[:160],
        "of_type": str(r.get("type") or "")[:40],
        "when": r.get("updated_at"),
        "from_source": "life_model",
        "already_holds": {
            "documents": len(r.get("documents") or []),
            "appointments": len(r.get("calendar_events") or []),
        },
        "how_directly_it_knows": "ORA already keeps this as one situation",
    } for r in rows if r.get("id")]


def _as_people_say_it(value: Any) -> str:
    """
    L'ora del calendario come la direbbe la persona, non come la conserva il database.

        DUE ORARI SONO CONFRONTABILI SOLO SE DETTI NELLO STESSO FUSO.

    Gli istanti sono conservati in UTC, ed e' giusto cosi'. Ma qui vanno
    messi accanto alle parole di un messaggio — «conferma appuntamento ore
    11:00» — e un'email non parla in UTC: parla nell'ora in cui vive chi
    l'ha scritta. Presentare «08:00Z» accanto a «ore 11:00» non mostra un
    disaccordo di un'ora: ne mostra uno di tre, e il giudizio che ne segue
    riguarda due appuntamenti che sembrano diversi.

    E' successo, ed e' costato una risposta sbagliata a un caso vero: la
    conferma delle 11:00 per la visita delle 10:00 e' stata letta come un
    appuntamento nuovo, perche' il calendario in quel confronto diceva
    «08:00».

    Il fuso e' quello della persona. Non e' una scelta di prodotto: e'
    l'unico in cui le due frasi parlano della stessa cosa.
    """
    raw = str(value or "").strip()
    moment = _moment(raw)
    if moment is None:
        return raw
    try:
        local = moment.astimezone(ZoneInfo(_HOME_TZ))
    except Exception:
        return raw
    if len(raw) == 10:
        # Una data senza ora e' un impegno che dura tutto il giorno.
        # Scriverci «alle 00:00» sarebbe inventare un orario.
        return local.strftime("%d/%m, tutto il giorno")
    return local.strftime("%d/%m alle %H:%M")


def disagreements_between(
    signal: ConnectedSignal, candidate: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    What each reading says about the same thing, with no view on which is right.

        CODE DOES NOT CHOOSE THE TRUE SOURCE.

    Two statements and the facts that bear on weighing them: what each says,
    when each was observed, and how directly each knows. A caller looking
    here for a winner will not find one, and that is the design — a table
    saying `calendar=0.9, email=0.8` would be a permanent, invisible,
    unexaminable answer to a question that depends entirely on the situation.

    What each source *says* is different in kind, and saying so honestly took
    a correction. A calendar states a time, so its statement is that time. A
    message does not: `effective_at` on an email is when it arrived, and
    presenting an arrival time as the message's claim about an appointment
    would be code inventing a disagreement out of two unrelated timestamps.
    So a message's statement is its own subject line — its words about the
    situation — and whether those words contradict the calendar is a
    judgement, made where judgements are made.
    """
    theirs = candidate.get("when")
    if not theirs:
        return []

    if signal.source_type == "email":
        # Its own words, and the arrival time labelled as an arrival.
        ours = str(signal.after or signal.payload_summary or "").strip()
        if not ours:
            return []
        how = "somebody wrote it in a message"
    else:
        ours = signal.effective_at or ""
        moment, other = _moment(ours), _moment(theirs)
        if moment is None or other is None:
            return []
        if abs((moment - other).total_seconds()) < 60:
            # The two readings agree. Nothing to weigh.
            return []
        how = "it is in the calendar itself"

    return [{
        "about": "what each of them says about this",
        "what_this_source_says": ours,
        "what_the_other_says": _as_people_say_it(theirs),
        "this_source_observed_at": signal.observed_at,
        "the_other_observed_at": candidate.get("last_observed"),
        "how_this_source_knows": how,
        "how_the_other_knows": candidate.get("how_directly_it_knows"),
    }]


async def record_link(
    db, owner_id: str, signal: ConnectedSignal, decision: Dict[str, Any],
    *, candidate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Write down that two readings are about one thing, and on what evidence.

    A row, not a merge. Nothing about this changes a Life Object, a memory or
    a goal: it records a relationship somebody can inspect, with the refs it
    relied on, so that "why does ORA think these are the same thing" always
    has an answer. Turning a link into a durable fact about a life is
    governance's decision and happens through the same door everything else
    does.
    """
    row = {
        "id": f"link_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "signal_id": signal.id,
        "source_type": signal.source_type,
        "source_object_ref": signal.source_object_ref,
        "relationship": str(decision.get("relationship") or "uncertain"),
        "target_kind": str((candidate or {}).get("kind") or ""),
        "target_ref": str((candidate or {}).get("ref") or ""),
        "confidence": float(decision.get("confidence") or 0.0),
        # Human-safe: a sentence somebody could be shown. Never the model's
        # working, and never anything read out of a message body.
        "reason_summary": str(decision.get("why") or "")[:300],
        "relied_on": [str(r)[:120] for r in (decision.get("relied_on") or [])][:8],
        "disagreements": disagreements_between(signal, candidate or {}),
        "decided_at": now_iso(),
        "expires_at": _now() + timedelta(days=180),
    }
    try:
        await db[LINKS].insert_one(dict(row))
    except Exception as e:
        logger.info("link write soft-fail: %s", type(e).__name__)
    row.pop("_id", None)
    return row


async def links_for(db, owner_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        return await db[LINKS].find(
            {"owner_id": owner_id}, {"_id": 0}
        ).sort("decided_at", -1).to_list(limit)
    except Exception as e:
        logger.info("links read soft-fail: %s", type(e).__name__)
        return []


async def ensure_indexes(db) -> None:
    try:
        await db[LINKS].create_index([("owner_id", 1), ("decided_at", -1)])
        await db[LINKS].create_index([("owner_id", 1), ("signal_id", 1)])
        await db[LINKS].create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        logger.exception("indici situation links non creati (non fatale)")


async def forget_all(db, owner_id: str) -> int:
    result = await db[LINKS].delete_many({"owner_id": owner_id})
    return result.deleted_count
