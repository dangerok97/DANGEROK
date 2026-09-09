"""
A quale pezzo di vita appartiene un messaggio. Deciso una volta, per tutte.

    «ACQUISTO» DENTRO UN OGGETTO NON VUOL DIRE CHE PARLA DEL TUO ACQUISTO.

Il difetto era visibile nello screenshot dello sprint precedente: sotto
«Acquisto di una nuova casa» compariva «Francesco, lascia un feedback sul tuo
acquisto recente» — una mail di marketing su un ordine online, arrivata li'
per una parola. Nessun elenco di parole avrebbe potuto salvarla: la parola
c'era davvero, ed era la parola giusta nel posto sbagliato.

Quindi la stessa disciplina delle carte, applicata ai messaggi: il giudizio
guarda una volta cosa un messaggio riguarda davvero, e la risposta si scrive.
Da quel momento «mail sulla casa» e' una lettura di relazioni, e una
newsletter che nomina un mutuo resta una newsletter.

**Cosa vede il giudizio.** Oggetto, mittente com'e' classificato, quando e'
arrivato, e la frase che il Connected Life ha gia' scritto interpretandolo.
Non il corpo — quello si chiede solo se il giudizio dichiara di non poter
decidere senza, per quel messaggio, una volta, e non viene conservato da
nessuna parte.

**Cosa si scrive.** Una relazione quando c'e' evidenza, un «non appartiene a
niente» quando non c'e'. Il secondo caso e' la maggioranza della posta di
chiunque, ed e' una risposta: senza, ogni passaggio ripagherebbe il giudizio
per farsi dire di nuovo che una promozione non c'entra con l'acquisto di una
casa.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from research.reasoning import _ask_model

logger = logging.getLogger("ora.lifesearch.messages")

# Quanti messaggi si guardano in un passaggio, e quanti corpi si possono
# chiedere. Il secondo numero e' piccolo di proposito: leggere il corpo di
# una mail e' la cosa piu' invasiva che ORA sappia fare, e un tetto basso
# vale piu' di qualunque intenzione.
PER_PASS = 30
AT_MOST_BODIES = 3

_DISCIPLINE = (
    "You are ORA, looking at the messages that reached a person and deciding "
    "which part of their life each one actually belongs to.\n\n"
    "You are given the situations they have open, and for each message: its "
    "subject, how the sender is classified, when it arrived, and — when ORA "
    "already interpreted it — one line about what it seemed to be. You do not "
    "see the body.\n\n"
    "Most messages belong to nothing anybody is tracking. Marketing, "
    "newsletters, notifications from services, receipts for things already "
    "closed: saying they belong to nothing is the ordinary answer and the "
    "correct one.\n\n"
    "A word in a subject line is not a connection. «Leave feedback on your "
    "recent purchase» is a shop writing about an order; it does not become "
    "part of somebody buying a house because both say «purchase». Ask what "
    "the message is *for*, and who sent it.\n\n"
    "An offer from a bank about a mortgage is marketing unless this person is "
    "actually dealing with that bank about their own mortgage. A message from "
    "a dental practice about an appointment belongs to that appointment.\n\n"
    "When you would need the text to decide — and only then — say so with "
    "needs_content, and say why in a sentence the person could read. Do not "
    "ask for content to be thorough: ask when the subject genuinely does not "
    "say enough and the message plausibly matters.\n\n"
    "Answer with JSON only. No markdown fences."
)


async def file_the_messages(
    db, owner_id: str, *, language: str = "it", limit: int = PER_PASS,
) -> Dict[str, Any]:
    """
    Guarda i messaggi non ancora collocati e scrivi dove appartengono.

    Torna cosa e' stato fatto e quante chiamate e' costato: una per il
    passaggio, piu' una sola se qualche messaggio ha davvero richiesto il
    testo.
    """
    from lifesearch.relations import (
        RELATION_TYPES, already_decided, note_nothing_to_link, remember_relation,
    )

    situations = await _situations(db, owner_id)
    if not situations:
        return _nothing_to_do("questa persona non ha ancora situazioni aperte")

    seen = set(await already_decided(db, owner_id, source_type="email"))
    messages = [m for m in await _messages(db, owner_id) if m["ref"] not in seen]
    if not messages:
        return _nothing_to_do("ogni messaggio ha gia' una risposta")

    messages = messages[:limit]
    answer = await _ask(situations, messages, language=language)
    calls = 1
    if not isinstance(answer, dict):
        return {"guardate": len(messages), "collegate": 0, "senza_posto": 0,
                "corpi_letti": 0, "chiamate": calls,
                "perche": "il giudizio non ha risposto"}

    known = {s["id"] for s in situations}
    mine = {m["ref"]: m for m in messages}
    decided = answer.get("messages") or []

    # Chi ha chiesto il testo. Si accontenta al massimo tre per passaggio, e
    # solo se il messaggio poteva davvero appartenere a qualcosa.
    wants_text = [
        row for row in decided
        if isinstance(row, dict) and row.get("needs_content")
        and str(row.get("ref") or "") in mine
    ][:AT_MOST_BODIES]

    read_bodies = 0
    if wants_text:
        with_text = await _with_the_text(db, owner_id, wants_text, mine)
        read_bodies = len(with_text)
        if with_text:
            second = await _ask(
                situations, with_text, language=language, having_read_them=True,
            )
            calls += 1
            if isinstance(second, dict):
                answered = {str(r.get("ref")): r for r in (second.get("messages") or [])
                            if isinstance(r, dict)}
                decided = [answered.get(str(r.get("ref")), r) for r in decided]

    linked = 0
    homeless = 0
    for row in decided:
        if not isinstance(row, dict):
            continue
        ref = str(row.get("ref") or "")
        if ref not in mine:
            continue
        target = str(row.get("belongs_to") or "")
        certainty = str(row.get("certainty") or "low").lower()
        why = str(row.get("why") or "").strip()
        relation = str(row.get("relation") or "about")

        # Quanta prova serve per scrivere una relazione.
        #
        #     UN ARGOMENTO IN COMUNE NON E' UN LEGAME CON LA TUA VITA.
        #
        # Sulla posta vera il giudizio ha collegato all'acquisto di una casa
        # due offerte commerciali di mutui: non parlavano di quella casa,
        # parlavano di mutui. Erano `related_to` con certezza media — cioe'
        # la forma piu' debole di legame detta con la fiducia piu' bassa.
        # Quella combinazione non basta: o il legame e' forte (appartiene,
        # fa parte, la sostiene), o la certezza lo e'.
        strong_enough = (
            certainty == "high"
            or (certainty == "medium"
                and relation in ("about", "part_of", "supports"))
        )
        if (not target or target not in known or not strong_enough
                or relation not in RELATION_TYPES):
            await note_nothing_to_link(
                db, owner_id, source_type="email", source_ref=ref,
                why=why or "Non ho abbastanza per collegarlo a qualcosa.",
            )
            homeless += 1
            continue

        made = await remember_relation(
            db, owner_id,
            source_type="email", source_ref=ref,
            target_kind="life_object", target_ref=target,
            relation_type=relation, why=why or "Riguarda questa parte della tua vita.",
            decided_by="judgement",
            confidence=1.0 if certainty == "high" else 0.6,
        )
        linked += 1 if made else 0

    return {
        "guardate": len(messages), "collegate": linked, "senza_posto": homeless,
        "corpi_letti": read_bodies, "chiamate": calls,
    }


def _nothing_to_do(why: str) -> Dict[str, Any]:
    return {"guardate": 0, "collegate": 0, "senza_posto": 0, "corpi_letti": 0,
            "chiamate": 0, "perche": why}


async def _ask(
    situations: List[Dict[str, Any]], messages: List[Dict[str, Any]],
    *, language: str, having_read_them: bool = False,
) -> Any:
    from lifesearch.relations import RELATION_TYPES

    instruction = (
        "For each message, say which situation it belongs to.\n\n"
        f"Return JSON: {{\"messages\": [{{\"ref\": \"…\", "
        "\"belongs_to\": \"the situation id, or empty if none\", "
        f"\"relation\": one of {list(RELATION_TYPES)}, "
        "\"why\": \"one sentence, in their language, that a person could "
        "read\", \"certainty\": \"high\" | \"medium\" | \"low\", "
        "\"needs_content\": false}]}"
    )
    if having_read_them:
        instruction += (
            "\n\nYou now have the text of these messages, fetched once for "
            "this decision and kept nowhere. Decide. `needs_content` must be "
            "false in this answer."
        )
    return await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        json.dumps({
            "their_situations": situations,
            "their_messages": messages,
            "answer_in": language,
        }, ensure_ascii=False, default=str)[:14000],
    )


async def _with_the_text(
    db, owner_id: str, asked: List[Dict[str, Any]], mine: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Il testo dei messaggi per cui il giudizio ha detto di non poter decidere.

        IL CORPO SI CHIEDE UNA VOLTA, E NON SI CONSERVA.

    Torna la stessa descrizione di prima piu' il testo, per una sola domanda.
    Niente di questo viene scritto: la riga che resta e' l'audit di aver
    guardato, con il motivo, che e' quello che serve a chi ci chiede conto.
    """
    import deps

    out: List[Dict[str, Any]] = []
    for row in asked:
        ref = str(row.get("ref") or "")
        item = mine.get(ref)
        if not item or not item.get("instance_id"):
            continue
        try:
            text = await deps.get_gmail_service().body_for(
                user_id=owner_id, instance_id=item["instance_id"], message_id=ref,
            )
        except Exception as e:
            logger.info("body read soft-fail: %s", type(e).__name__)
            continue
        out.append({
            **{k: v for k, v in item.items() if k != "instance_id"},
            # Limitato: serve a decidere di cosa parla, non a rileggerlo.
            "text": str(text or "")[:2000],
            "why_it_was_read": str(row.get("why") or "")[:200],
        })
    return out


async def _situations(db, owner_id: str) -> List[Dict[str, Any]]:
    try:
        rows = await db.life_objects.find(
            {"user_id": owner_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "title": 1, "type": 1, "ai_summary": 1},
        ).to_list(30)
    except Exception as e:
        logger.info("situation read soft-fail: %s", type(e).__name__)
        return []
    return [
        {"id": r["id"], "what_it_is": str(r.get("title") or "")[:80],
         "kind": r.get("type") or "",
         "in_a_line": str(r.get("ai_summary") or "")[:140]}
        for r in rows if r.get("title")
    ]


async def _messages(db, owner_id: str) -> List[Dict[str, Any]]:
    """
    I messaggi, descritti da fuori — e con quello che ORA ne aveva gia' detto.
    """
    from ingestion.reading import plain

    try:
        rows = await db.ingestion_events.find(
            {"user_id": owner_id, "source_record_type": "email_message"},
            {"_id": 0, "external_id": 1, "normalized_payload": 1,
             "ingested_at": 1, "connector_instance_id": 1},
        ).sort("ingested_at", -1).to_list(300)
    except Exception as e:
        logger.info("message read soft-fail: %s", type(e).__name__)
        return []

    interpreted = await _what_ora_said(db, owner_id)
    out = []
    for row in rows:
        payload = plain(row.get("normalized_payload"))
        ref = str(row.get("external_id") or "")
        if not ref:
            continue
        out.append({
            "ref": ref,
            "subject": str(payload.get("subject") or "")[:200],
            "who_sent_it": str(payload.get("sender_relationship") or "unknown"),
            "arrived": str(payload.get("received_at") or row.get("ingested_at"))[:19],
            "in_inbox": str(payload.get("in_inbox") or ""),
            "ora_already_said": interpreted.get(ref, ""),
            "instance_id": str(row.get("connector_instance_id") or ""),
        })
    return out


async def _what_ora_said(db, owner_id: str) -> Dict[str, str]:
    """Quello che il Connected Life ha gia' capito di questi messaggi."""
    try:
        rows = await db.connected_signals.find(
            {"owner_id": owner_id, "source_type": "email"},
            {"_id": 0, "source_object_ref": 1, "payload_summary": 1},
        ).sort("observed_at", -1).to_list(300)
    except Exception:
        return {}
    return {
        str(r.get("source_object_ref")): str(r.get("payload_summary") or "")[:200]
        for r in rows if r.get("source_object_ref")
    }
