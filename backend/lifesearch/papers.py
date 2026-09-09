"""
A quale pezzo di vita appartiene una carta. Deciso una volta, per tutte.

    IL TITOLO DI UN DOCUMENTO NON DICE A COSA SERVE.

«Rogito_2026_definitivo.pdf» e' il documento piu' importante dell'acquisto di
una casa e non contiene la parola «casa». «Bolletta_luce.pdf» contiene la
parola «casa» in nessun punto e riguarda quella dove si abita adesso, che e'
un'altra. Cercare per parola risolve i casi facili e sbaglia gli unici che
contano.

Quindi la domanda si fa una volta sola, quando il documento e' li' fermo, e
la risposta si scrive: *a quale parte della vita di questa persona appartiene
questa carta, e perche'?* Da quel momento «documenti della casa» e' una
lettura di relazioni, non una ricerca di stringhe — e costa zero.

**Come si chiede.** Tutti i documenti ancora senza risposta in una chiamata
sola, insieme all'elenco delle situazioni. Una chiamata per documento sarebbe
un costo che cresce con l'archivio di chi lo usa, e un archivio cresce.

**Cosa arriva al giudizio.** Nome, data, tipo, e la riga di sintesi che
l'estrazione documentale ha gia' prodotto. Non il testo: duplicarlo dentro il
modello della vita vorrebbe dire tenerne due copie destinate a divergere, e
mandarlo a ogni passaggio vorrebbe dire pagare l'intero archivio ogni volta.

**Cosa si scrive.** Solo quello di cui il giudizio e' ragionevolmente sicuro,
con il suo motivo. E anche i «no»: che una ricevuta non appartenga a niente e'
una risposta, e ricordarla evita di ricomprarla ogni volta.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from research.reasoning import _ask_model

logger = logging.getLogger("ora.lifesearch.papers")

# Quante carte si guardano in un passaggio. Un limite di costo, non di
# verita': quelle che avanzano toccano al giro dopo.
PER_PASS = 25

_DISCIPLINE = (
    "You are ORA, looking at the papers a person has filed and deciding which "
    "part of their life each one belongs to.\n\n"
    "You are given the situations that person has open, and a list of "
    "documents with their name, date and — when the system already extracted "
    "one — a line of summary. You never see the contents, and you must not "
    "pretend to.\n\n"
    "Most documents belong to something. Some belong to nothing anybody is "
    "tracking, and saying so is a correct answer: a supermarket receipt is "
    "not part of buying a house.\n\n"
    "Judge by what the paper is for, not by whether its name contains the "
    "words of the situation. A deed belongs to buying a house even when it "
    "says only «rogito». An energy bill for the flat somebody already lives "
    "in does not belong to buying a different one.\n\n"
    "When two situations would both be plausible and nothing distinguishes "
    "them, say so with certainty «low» and let it be: a relation nobody was "
    "sure of is worse than no relation, because everything downstream will "
    "reason about a connection that was never established.\n\n"
    "Belonging is not resemblance. Before you say a thing belongs to a "
    "situation, name what ties it to *that* one and not to another: the "
    "same property, the same address, the same counterparty, an explicit "
    "reference to it, a conversation this person is actually in. Put it "
    "in what_ties_it.\n\n"
    "A lease is about a home; it is not about the home somebody is "
    "buying unless something says so. A digest of property listings is "
    "about housing; it is not part of a purchase already under way. When "
    "you cannot name the tie, leave what_ties_it empty and use "
    "related_to — near, not inside.\n\n"
    "Answer with JSON only. No markdown fences."
)


async def file_the_papers(
    db, owner_id: str, *, language: str = "it", limit: int = PER_PASS,
) -> Dict[str, Any]:
    """
    Guarda le carte non ancora collocate e scrivi dove appartengono.

    Torna cosa e' stato fatto, incluso quante chiamate sono servite — una, o
    zero se non c'era niente da guardare.
    """
    from lifesearch.relations import (
        RELATION_TYPES, already_decided, note_nothing_to_link, remember_relation,
    )

    situations = await _situations(db, owner_id)
    if not situations:
        return {"guardate": 0, "collegate": 0, "senza_posto": 0, "chiamate": 0,
                "perche": "questa persona non ha ancora situazioni aperte"}

    seen = set(await already_decided(db, owner_id, source_type="document"))
    papers = [p for p in await _papers(db, owner_id) if p["ref"] not in seen]
    if not papers:
        return {"guardate": 0, "collegate": 0, "senza_posto": 0, "chiamate": 0,
                "perche": "ogni carta ha gia' una risposta"}

    papers = papers[:limit]
    instruction = (
        "For each document, say which situation it belongs to.\n\n"
        f"Return JSON: {{\"documents\": [{{\"ref\": \"…\", "
        "\"belongs_to\": \"the situation id, or empty if none\", "
        f"\"relation\": one of {list(RELATION_TYPES)}, "
        "\"why\": \"one sentence, in their language, that a person could "
        "read\", \"what_ties_it\": \"what makes it *this* situation and not another, or empty\", \"certainty\": \"high\" | \"medium\" | \"low\"}}]}"
    )

    answer = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        json.dumps({
            "their_situations": situations,
            "their_documents": papers,
            "answer_in": language,
        }, ensure_ascii=False, default=str)[:12000],
    )
    if not isinstance(answer, dict):
        return {"guardate": len(papers), "collegate": 0, "senza_posto": 0,
                "chiamate": 1, "perche": "il giudizio non ha risposto"}

    known = {s["id"] for s in situations}
    mine = {p["ref"] for p in papers}
    linked = 0
    homeless = 0

    for row in answer.get("documents") or []:
        ref = str(row.get("ref") or "")
        if ref not in mine:
            # Un riferimento che non era nella domanda non e' una risposta.
            continue
        target = str(row.get("belongs_to") or "")
        certainty = str(row.get("certainty") or "low").lower()
        why = str(row.get("why") or "").strip()

        if not target or target not in known or certainty == "low":
            #     UN FORSE NON SI SCRIVE COME UN SI'.
            await note_nothing_to_link(
                db, owner_id, source_type="document", source_ref=ref,
                why=why or "Non ho abbastanza per collegarlo a qualcosa.",
            )
            homeless += 1
            continue

        made = await remember_relation(
            db, owner_id,
            source_type="document", source_ref=ref,
            target_kind="life_object", target_ref=target,
            relation_type=str(row.get("relation") or "about"),
            why=why or "Riguarda questa parte della tua vita.",
            # Senza questo, «appartiene» diventa «assomiglia»: il codice
            # declassa da solo a vicinanza.
            ties=str(row.get("what_ties_it") or ""),
            decided_by="judgement",
            confidence=1.0 if certainty == "high" else 0.6,
        )
        linked += 1 if made else 0

    return {
        "guardate": len(papers), "collegate": linked, "senza_posto": homeless,
        "chiamate": 1,
    }


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


async def _papers(db, owner_id: str) -> List[Dict[str, Any]]:
    """
    Le carte, descritte da fuori.

    Nome, data, tipo, e la riga che l'estrazione ha gia' scritto. Il testo
    resta dov'e': non serve per sapere a cosa serve un documento, e mandarlo
    costerebbe l'intero archivio a ogni passaggio.
    """
    try:
        rows = await db.documents.find(
            {"user_id": owner_id, "deleted": {"$ne": True},
             "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "display_title": 1, "original_filename": 1,
             "created_at": 1, "document_type": 1, "summary": 1,
             "knowledge_summary": 1, "ai_summary": 1},
        ).sort("created_at", -1).to_list(200)
    except Exception as e:
        logger.info("document read soft-fail: %s", type(e).__name__)
        return []

    out = []
    for row in rows:
        out.append({
            "ref": row["id"],
            "name": str(row.get("display_title") or row.get("original_filename") or "")[:140],
            "filed_on": str(row.get("created_at") or "")[:10],
            "kind": str(row.get("document_type") or "")[:40],
            "in_a_line": str(
                row.get("knowledge_summary") or row.get("summary")
                or row.get("ai_summary") or ""
            )[:200],
        })
    return out
