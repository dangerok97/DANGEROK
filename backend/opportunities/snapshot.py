"""
What ORA can say about a life, compactly, without handing over the life.

The model needs enough to judge and no more. Not a document, a summary of one;
not a coordinate, the name the person gave the place; not a history, the shape
of the recent past. Every field here exists because a judgement about whether
something is worth saying would be wrong without it.

    LOCATION IS CONTEXT, NOT A TRIGGER.
    EVENT != OPPORTUNITY.

So this file gathers facts and refuses to grade them. There is nothing here
that marks a calendar event as important, a deadline as pressing or a place as
significant — those are the judgements being delegated, and pre-judging them in
the payload would be the rule engine this sprint exists to avoid, hidden one
layer down.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# How far ahead is worth describing. Beyond a fortnight almost nothing is
# actionable today, and a longer window mostly adds noise to the payload.
HORIZON_DAYS = 14

# Per-source caps. A model given forty of anything reads the first few and
# guesses about the rest.
MAX_PER_SOURCE = 6


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def build(
    db, user_id: str, *, changes: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    A relevant life state snapshot: facts, bounded, unranked.

    Every source is best-effort. A domain that fails to answer leaves its part
    of the picture empty rather than failing the scan — the model is told what
    is missing, and a judgement made on less is still a judgement, whereas no
    judgement at all is a silence for the wrong reason.
    """
    now = _now()
    snapshot: Dict[str, Any] = {
        "now": now.isoformat(),
        "local_weekday": now.strftime("%A").lower(),
        "horizon_days": HORIZON_DAYS,
        # What moved since last time, when the caller knows. It focuses
        # attention; it never implies that a change is an opportunity.
        "what_changed": (changes or [])[:MAX_PER_SOURCE],
        "unavailable_sources": [],
    }

    # Time is a fact, and it is the code's job to state it. Nothing here
    # interprets anything: how many minutes until the next thing, whether a
    # window has opened or closed. What any of that means is the model's.
    snapshot["temporal"] = {}

    for name, gather in (
        ("open_questions", _open_questions),
        ("recently_settled", _recently_settled),
        ("places", _places),
        ("presence", _presence),
        ("routines", _routines),
        ("open_comparisons", _comparisons),
        ("calendar", _calendar),
        ("situations", _situations),
        ("disagreements", _disagreements),
        ("money", _money),
        ("documents", _documents),
        ("market_offers", _market_offers),
        ("existing_work", _existing_work),
    ):
        try:
            snapshot[name] = await gather(db, user_id, now)
        except Exception as e:
            logger.info("snapshot source %s unavailable: %s", name, type(e).__name__)
            snapshot[name] = []
            snapshot["unavailable_sources"].append(name)

    snapshot["temporal"] = _temporal_facts(snapshot, now)
    return snapshot


def _temporal_facts(snapshot: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """
    What the passing of time has done, stated and not interpreted.

        TIME IS A FACT.

    Nothing in a life has to change for its meaning to change. An event two
    days away yesterday is tomorrow today, and a window that had not opened
    at midnight is open at eight. None of that moves a single stored value,
    so a snapshot built only from stored values looks identical on both days
    — and anything comparing snapshots would conclude, wrongly, that there is
    nothing new to think about.

    So the counting is done here, in buckets rather than in seconds: an event
    forty-one minutes away and one forty-three minutes away are the same
    situation, and a fingerprint that changed between them would defeat its
    own purpose.
    """
    soonest: Optional[int] = None
    for row in snapshot.get("calendar") or []:
        minutes = _minutes_until(row.get("starts_at"), now)
        if minutes is not None and (soonest is None or minutes < soonest):
            soonest = minutes

    return {
        # Coarse on purpose: the hour, not the minute.
        "hour_bucket": now.strftime("%Y-%m-%dT%H"),
        "weekday": now.strftime("%A").lower(),
        "minutes_to_next_commitment": _bucket(soonest),
        "something_within_the_hour": bool(soonest is not None and soonest <= 60),
        "something_today": any(
            (row.get("in_days") == 0) for row in (snapshot.get("calendar") or [])
        ),
        "something_tomorrow": any(
            (row.get("in_days") == 1) for row in (snapshot.get("calendar") or [])
        ),
    }


def _minutes_until(when: Optional[str], now: datetime) -> Optional[int]:
    if not when:
        return None
    try:
        moment = datetime.fromisoformat(str(when))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delta = int((moment - now).total_seconds() // 60)
    return delta if delta >= 0 else None


def _bucket(minutes: Optional[int]) -> Optional[str]:
    """
    Human-sized bands.

    A judgement about whether to interrupt somebody does not turn on the
    difference between 41 and 43 minutes, and a value that precise would make
    every snapshot different from every other one.
    """
    if minutes is None:
        return None
    if minutes <= 15:
        return "within_15_minutes"
    if minutes <= 60:
        return "within_the_hour"
    if minutes <= 240:
        return "within_four_hours"
    if minutes <= 1440:
        return "today"
    return "later"


async def _open_questions(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    Things ORA asked and nobody has answered.

    The stake travels with the question. Without it a model sees only that
    something was asked, which says nothing about whether the answer still
    matters — and an unanswered question is not, by itself, a problem.
    """
    from waiting.repository import OpenQuestionRepository

    rows = await OpenQuestionRepository(db).list_open(user_id, limit=MAX_PER_SOURCE)
    return [
        {
            "ref": r.get("id"),
            "question": (r.get("question") or "")[:200],
            "why_it_matters": (r.get("why_needed") or "")[:200] or None,
            "about": (r.get("context_label") or "")[:80] or None,
            "asked_at": r.get("created_at"),
        }
        for r in rows
    ]


async def _recently_settled(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    Questions that were open and are not any more.

    Without this a snapshot only ever grows: something raised because an
    answer was missing would stay raised for ever, because the moment the
    answer arrives the question leaves `open` and disappears from view. A
    review that cannot see what got settled has nothing to settle anything
    with, so the answer travels here in the words it was given.
    """
    since = (now - timedelta(days=HORIZON_DAYS)).isoformat()
    rows = await db.open_questions.find(
        {
            "user_id": user_id,
            "status": {"$ne": "open"},
            "updated_at": {"$gte": since},
        },
        {"_id": 0, "id": 1, "question": 1, "answer_raw": 1, "context_label": 1,
         "answered_at": 1, "status": 1},
    ).sort("updated_at", -1).to_list(MAX_PER_SOURCE)
    return [
        {
            "ref": r.get("id"),
            "question": (r.get("question") or "")[:200],
            "answer": (r.get("answer_raw") or "")[:200] or None,
            "about": (r.get("context_label") or "")[:80] or None,
            "settled_at": r.get("answered_at") or None,
        }
        for r in rows
    ]


async def _places(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    The places the person named — names and roles, never coordinates.

    A model deciding whether something is worth saying does not need to know
    where anybody lives to a metre. It needs to know that "Casa" exists.
    """
    from places.service import PlacesService

    places = await PlacesService(db).list_places(user_id)
    return [
        {
            "ref": p.id,
            "name": p.label,
            "role": p.role if p.role_confirmed_by_user else None,
            "locality": p.locality or None,
        }
        for p in places[:MAX_PER_SOURCE]
    ]


async def _presence(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """
    Where they are, if anywhere known, and for how long.

    Context, not a trigger. "Sei a casa" on its own means nothing, and the
    payload says as much by carrying no importance alongside it.
    """
    from places.service import PlacesService

    here = await PlacesService(db).where_now(user_id)
    if not here.get("at_a_known_place"):
        return {"at_a_known_place": False}
    seconds = here.get("seconds_here") or 0
    return {
        "at_a_known_place": True,
        "place": here.get("place"),
        "place_ref": here.get("place_id"),
        "roughly_minutes_there": int(seconds // 60) if seconds else None,
    }


async def _routines(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """Shapes the days keep taking, as the model itself once read them."""
    from places.service import PlacesService

    rows = await PlacesService(db).list_routines(user_id)
    return [
        {
            "ref": r.get("id"),
            "what": r.get("what_ora_thinks"),
            "weekdays": r.get("weekdays"),
            "state": r.get("state"),
        }
        for r in rows[:MAX_PER_SOURCE]
        if r.get("what_ora_thinks")
    ]


async def _comparisons(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    Choices ORA worked through, and whether one was made.

    A comparison with no chosen option is a fact about a decision, not a
    reason to push somebody towards making it.
    """
    rows = await db.comparison_runs.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(MAX_PER_SOURCE)
    out = []
    for r in rows:
        recommendation = r.get("recommendation") or {}
        out.append(
            {
                "ref": r.get("id"),
                "decision": ((r.get("need") or {}).get("decision") or "")[:160],
                "options": [
                    (a.get("name") or "")[:60] for a in (r.get("alternatives") or [])
                ][:4],
                "verdict": recommendation.get("verdict"),
                "chosen": bool(recommendation.get("chosen_alternative_id")),
                "at": r.get("created_at"),
            }
        )
    return out


async def _calendar(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    What is on the calendar within the horizon.

    Titles and times. No attendees, no locations, no descriptions: a judgement
    about whether an event needs preparing does not require reading who else
    is coming.
    """
    horizon = now + timedelta(days=HORIZON_DAYS)
    out: List[Dict[str, Any]] = []

    rows = await db.calendar_events.find(
        {
            "user_id": user_id,
            "start_at": {"$gte": now.isoformat(), "$lte": horizon.isoformat()},
        },
        {"_id": 0, "id": 1, "title": 1, "start_at": 1, "end_at": 1, "all_day": 1},
    ).sort("start_at", 1).to_list(MAX_PER_SOURCE)
    for r in rows:
        out.append({
            "ref": r.get("id"),
            "title": (r.get("title") or "")[:120],
            "starts_at": r.get("start_at"),
            "in_days": _days_from_now(r.get("start_at"), now),
            "all_day": bool(r.get("all_day")),
        })

    # E quelli che arrivano dal calendario collegato.
    #
    #     UNA VITA LETTA E POI NON GUARDATA E' UNA VITA CHE ORA NON HA.
    #
    # Gli appuntamenti di questa persona vivono in `ingestion_events` da
    # V3.10; qui si leggeva soltanto `calendar_events`, che su un account
    # vero e' vuota. Il risultato: ORA decideva se ci fosse qualcosa da dire
    # guardando un'agenda vuota, e taceva — con ragione, e senza sapere che
    # domani mattina c'e' il dentista.
    seen = {str(r.get("ref") or "") for r in out}
    for row in await _appointments_that_still_stand(db, user_id, now, horizon):
        if row["ref"] in seen:
            continue
        seen.add(row["ref"])
        out.append({
            "ref": row["ref"],
            "title": row["title"],
            "starts_at": row["starts_at"],
            "in_days": _days_from_now(row["starts_at"], now),
            "all_day": row["all_day"],
        })

    out.sort(key=lambda r: str(r.get("starts_at") or ""))
    return out[:MAX_PER_SOURCE]


async def _appointments_that_still_stand(
    db, user_id: str, now: datetime, horizon: datetime,
) -> List[Dict[str, Any]]:
    """
    Gli impegni che esistono davvero, dal calendario collegato.

        UN IMPEGNO ANNULLATO NON E' UN IMPEGNO.
        LO STESSO IMPEGNO SCRITTO QUATTRO VOLTE E' UNO.

    Questo leggeva tutto: annullati, sostituiti, copie. Su un account vero il
    risultato era che le sei righe di agenda che il giudizio riceveva erano
    quattro fantasmi della stessa visita e un evento di prova — e l'unica
    visita che esiste davvero ci stava dentro per caso, indistinguibile dalle
    altre. Chi guarda quell'agenda non puo' che concludere che non c'e'
    niente di serio.

    Cosa resta fuori e' un fatto sulla riga, mai un'opinione sul significato:
    annullato, superato da una lettura piu' recente, o gia' presente identico.
    Cosa NON viene tolto: due impegni vivi che dicono ore diverse per la
    stessa cosa. Quelli restano tutti e due, uno accanto all'altro, perche'
    accorparli sarebbe il codice a scegliere quale delle due ore e' quella
    giusta — che e' esattamente la domanda che va lasciata a chi ragiona.
    """
    try:
        from ingestion.reading import plain

        rows = await db.ingestion_events.find(
            {
                "user_id": user_id,
                "source_record_type": "calendar_event",
                "ingestion_status": {"$ne": "superseded"},
            },
            {"_id": 0, "external_id": 1, "normalized_payload": 1, "ingested_at": 1},
        ).sort("ingested_at", -1).to_list(400)
    except Exception as e:
        logger.info("calendar read soft-fail: %s", type(e).__name__)
        return []

    out: List[Dict[str, Any]] = []
    by_ref: set = set()
    same_thing: set = set()
    for row in rows:
        payload = plain(row.get("normalized_payload"))
        starts = str(payload.get("starts_at") or "")
        if not starts or not (now.isoformat()[:19] <= starts <= horizon.isoformat()):
            continue
        if str(payload.get("status") or "").lower() == "cancelled":
            continue
        ref = str(row.get("external_id") or "")
        title = str(payload.get("title") or "").strip()[:120]
        if not ref or not title or ref in by_ref:
            continue
        # La stessa cosa alla stessa ora, arrivata due volte, e' una cosa.
        twice = (title.lower(), starts)
        if twice in same_thing:
            continue
        by_ref.add(ref)
        same_thing.add(twice)
        out.append({
            "ref": ref,
            "title": title,
            "starts_at": starts,
            "all_day": len(starts) == 10
            or str(payload.get("all_day") or "").lower() == "true",
        })
    out.sort(key=lambda r: r["starts_at"])
    return out


async def _situations(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    Le parti di vita aperte di questa persona, e cosa non si sa ancora di esse.

        NON SI PUO' DECIDERE SE QUALCOSA CONTA SENZA SAPERE COSA STA
        SUCCEDENDO.

    Erano assenti: il giudizio riceveva ora, luogo e agenda, e nessuna delle
    situazioni su cui questa persona sta effettivamente vivendo. Un acquisto
    di casa senza indirizzo non poteva essere notato da nessuno, perche'
    nessuno lo stava guardando.
    """
    try:
        rows = await db.life_objects.find(
            {"user_id": user_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "title": 1, "type": 1, "ai_summary": 1,
             "next_reasoning": 1},
        ).to_list(MAX_PER_SOURCE)
    except Exception as e:
        logger.info("situation read soft-fail: %s", type(e).__name__)
        return []

    out: List[Dict[str, Any]] = []
    for row in rows:
        if not row.get("title"):
            continue
        out.append({
            "ref": row["id"],
            "what_it_is": str(row["title"])[:100],
            "kind": row.get("type") or "",
            "in_a_line": str(row.get("ai_summary") or "")[:200],
            # Quello che ORA stessa ha gia' scritto di non sapere. E' la cosa
            # piu' utile della riga: e' una domanda aperta, non una lacuna.
            "still_unclear": str(row.get("next_reasoning") or "")[:160],
        })
    return out


async def _disagreements(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    Dove due fonti dicono cose diverse della stessa cosa, e nessuno ha scelto.

        IL CODICE NON SCEGLIE QUALE FONTE DICE IL VERO — E QUALCUNO DEVE
        SAPERLO.

    Un appuntamento che il calendario mette alle 08:00 e una mail che parla
    delle 11:00 sono la cosa piu' utile che ORA possa dire a qualcuno la sera
    prima. Il Connected Life li registra gia' come disaccordo; qui dentro non
    arrivavano, e il giudizio decideva se ci fosse qualcosa da dire senza
    sapere che c'era un orario in dubbio per domattina.
    """
    try:
        rows = await db.connected_situation_links.find(
            # `$ne: []` prende anche le righe dove il campo e' nullo, ed erano
            # quasi tutte: sei righe lette, quattro vuote, e il disaccordo
            # vero — la mail che dice un'ora e il calendario che ne dice
            # un'altra per oggi — restava fuori perche' deciso qualche giorno
            # prima. Qui si chiedono le righe che un disaccordo ce l'hanno.
            {"owner_id": user_id, "disagreements.0": {"$exists": True}},
            {"_id": 0, "id": 1, "target_ref": 1, "reason_summary": 1,
             "disagreements": 1, "decided_at": 1},
        ).sort("decided_at", -1).to_list(60)
    except Exception as e:
        logger.info("disagreement read soft-fail: %s", type(e).__name__)
        return []

    # Un disaccordo su qualcosa che deve ancora succedere e' una cosa che si
    # puo' ancora chiarire; uno su qualcosa che e' passato e' un archivio.
    # Quale sia quale e' una data, non un giudizio: prima quelli sugli
    # impegni che stanno ancora in piedi.
    horizon = now + timedelta(days=HORIZON_DAYS)
    try:
        ahead = {
            r["ref"]
            for r in await _appointments_that_still_stand(db, user_id, now, horizon)
        }
    except Exception:
        ahead = set()
    rows.sort(key=lambda r: str(r.get("target_ref") or "") not in ahead)

    out: List[Dict[str, Any]] = []
    for row in rows:
        for said in (row.get("disagreements") or [])[:2]:
            out.append({
                "ref": str(row.get("id") or ""),
                "about": str(row.get("reason_summary") or "")[:200],
                "one_source_says": str(said.get("what_this_source_says") or "")[:120],
                "the_other_says": str(said.get("what_the_other_says") or "")[:120],
                "how_the_first_knows": str(said.get("how_this_source_knows") or "")[:80],
                "how_the_other_knows": str(said.get("how_the_other_knows") or "")[:80],
                "nobody_has_chosen": True,
            })
    return out[:MAX_PER_SOURCE]


async def _money(db, user_id: str, now: datetime) -> Dict[str, Any]:
    """
    Cosa ORA sa dei soldi di questa persona, con i gradi intatti.

    Non un saldo e non una previsione: quello che e' governato, quello che e'
    stato solo letto, quello su cui serve una parola. Un pagamento che pesa
    sul mese e' un fatto che puo' meritare attenzione, e finora il giudizio
    non lo vedeva affatto.
    """
    try:
        from financial.knowledge import what_ora_knows

        said = await what_ora_knows(db, user_id)
    except Exception as e:
        logger.info("money read soft-fail: %s", type(e).__name__)
        return {}

    def names(rows):
        # Limitata come ogni altra fonte: uno snapshot che cresce con la vita
        # di chi lo usa smette di essere uno snapshot.
        return [
            {"what": str(r.get("cosa") or "")[:80],
             "how_much": str(r.get("quanto") or "")[:40],
             "how_i_know": str(r.get("come_lo_so") or "")[:80]}
            for r in rows[:MAX_PER_SOURCE]
        ]

    bank = said.get("la_banca") or {}
    return {
        "what_ora_knows": names(said.get("so") or []),
        "what_ora_only_read": names(said.get("ho_letto") or []),
        "waiting_on_them": names(said.get("devo_chiederti") or []),
        "can_read_the_account_now": bool(bank.get("posso_leggere_adesso")),
        "this_month_so_far": said.get("questo_mese") or {},
    }


def _days_from_now(when: Optional[str], now: datetime) -> Optional[int]:
    """
    How many days away, counted here rather than by the model.

    A model asked to reason about whether something matters should not also be
    subtracting dates in its head: it says "in three days" about the day after
    tomorrow and the sentence is wrong in the only part a person would check.
    Counting is arithmetic, and arithmetic belongs to the code.

    Days are counted the way a person counts them, on the calendar. Elapsed
    hours would call tomorrow morning "in 0 days" and something four days out
    "in 3", which is how a correct number still produces a wrong sentence.
    """
    if not when:
        return None
    try:
        start = datetime.fromisoformat(str(when))
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return max(0, (start.date() - now.date()).days)


async def _documents(db, user_id: str, now: datetime, *, document_ids=None) -> List[Dict[str, Any]]:
    """Bounded, unverified previews for discovery; fuller reads use document.read."""
    import hashlib
    from agent.capabilities import CapabilityResolver

    access = await CapabilityResolver(db).resolve(user_id, "document.read")
    if not access.permitted or not access.executable:
        raise PermissionError("document.read unavailable")
    query = {"user_id": user_id, "deleted": {"$ne": True}, "archived": {"$ne": True}}
    if document_ids is not None:
        query["id"] = {"$in": list(document_ids)[:8]}
    rows = await db.documents.find(
        query,
        {"_id": 0, "id": 1, "original_filename": 1, "display_title": 1,
         "filename": 1, "extracted_text": 1, "updated_at": 1, "created_at": 1},
    ).sort([("updated_at", -1), ("created_at", -1), ("id", 1)]).limit(MAX_PER_SOURCE).to_list(MAX_PER_SOURCE)
    out = []
    for row in rows:
        if not row.get("id"):
            continue
        text = row.get("extracted_text")
        text = text if isinstance(text, str) else ""
        out.append({
            "ref": f"document:{row['id']}",
            "title": str(row.get("display_title") or row.get("original_filename") or row.get("filename") or "")[:160],
            "unverified_excerpt": text[:1200],
            "text_available": bool(text.strip()),
            "excerpt_truncated": len(text) > 1200,
            "text_version": hashlib.sha256(text.encode()).hexdigest()[:16],
            "updated_at": row.get("updated_at") or row.get("created_at"),
            "freshness": "unknown",
        })
    return out


async def _market_offers(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """Fresh, source-backed alternatives from recurring public web research."""
    rows = await db.energy_offer_monitors.find(
        {"user_id": user_id, "enabled": True,
         "source_fetched_at": {"$gte": (now - timedelta(days=10)).isoformat()},
         "$or": [{"evidence_valid_until": {"$exists": False}},
                 {"evidence_valid_until": None},
                 {"evidence_valid_until": {"$gte": now.isoformat()}}]},
        {"_id": 0, "commodity": 1, "document_id": 1, "annual_consumption": 1,
         "candidates": 1, "advice": 1, "source_url": 1, "source_fetched_at": 1},
    ).limit(MAX_PER_SOURCE).to_list(MAX_PER_SOURCE)
    out = []
    for row in rows:
        active_bill = await db.documents.find_one(
            {"user_id": user_id, "id": row["document_id"],
             "deleted": {"$ne": True}, "archived": {"$ne": True}},
            {"_id": 1},
        )
        if not active_bill:
            continue
        for offer in (row.get("candidates") or [])[:3]:
            if offer.get("valid_until") and offer["valid_until"] < now.date().isoformat():
                continue
            out.append({
                "ref": f"market_offer:{row['commodity']}:{offer['code']}",
                "market": row["commodity"],
                "name": offer["name"], "seller": offer["seller"],
                "offer_url": offer["url"],
                "observed_at": row["source_fetched_at"],
                "valid_until": offer.get("valid_until"),
                "bill_ref": f"document:{row['document_id']}",
                "annual_consumption": row.get("annual_consumption"),
                "estimated_seller_year": offer.get("estimated_seller_year"),
                "current_seller_year": offer.get("current_seller_year"),
                "potential_saving_year": offer.get("potential_saving_year"),
                "comparison_basis": offer["comparison_basis"],
                "advice": (row.get("advice") or {}).get("text")
                if (row.get("advice") or {}).get("offer_code") == offer["code"] else None,
                "caveat": (
                    "Stima della sola componente di vendita da prezzi espliciti; "
                    "bolletta totale, condizioni e requisiti non verificati."
                    if offer["comparison_basis"] == "seller_component_estimate" else
                    "Alternativa osservata online; convenienza rispetto al contratto attuale non verificata."
                ),
            })
    return out[:MAX_PER_SOURCE]


async def _existing_work(db, user_id: str, now: datetime) -> List[Dict[str, Any]]:
    """
    What is already on the person's plate.

    So the model can tell the difference between noticing something and
    repeating something they are already looking at.
    """
    rows = await db.home_snapshots.find(
        {"user_id": user_id}, {"_id": 0, "items": 1}
    ).sort("generated_at", -1).to_list(1)
    if not rows:
        return []
    out = []
    for item in (rows[0].get("items") or [])[:MAX_PER_SOURCE]:
        out.append(
            {
                "ref": item.get("id"),
                "title": (item.get("title") or "")[:120],
                "why": ((item.get("meta") or {}).get("work_reason")),
            }
        )
    return out


def evidence_refs(snapshot: Dict[str, Any]) -> Dict[str, str]:
    """
    Every reference the snapshot actually contains, by ref.

    The set an opportunity's evidence must be drawn from. A model that cites
    something absent from here has invented it, and the caller drops it —
    which is the whole reason this returns a lookup rather than a count.
    """
    found: Dict[str, str] = {}

    def take(kind: str, rows) -> None:
        for row in rows or []:
            ref = row.get("ref") if isinstance(row, dict) else None
            if ref:
                found[str(ref)] = kind

    take("open_question", snapshot.get("open_questions"))
    take("settled_question", snapshot.get("recently_settled"))
    take("place", snapshot.get("places"))
    take("routine", snapshot.get("routines"))
    take("comparison", snapshot.get("open_comparisons"))
    take("calendar_event", snapshot.get("calendar"))
    take("life_object", snapshot.get("situations"))
    take("disagreement", snapshot.get("disagreements"))
    take("existing_work", snapshot.get("existing_work"))
    take("document", snapshot.get("documents"))
    take("market_offer", snapshot.get("market_offers"))

    presence = snapshot.get("presence") or {}
    if presence.get("place_ref"):
        found[str(presence["place_ref"])] = "presence"

    for change in snapshot.get("what_changed") or []:
        if isinstance(change, dict) and change.get("ref"):
            found[str(change["ref"])] = str(change.get("kind") or "change")
    return found
