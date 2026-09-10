"""
Provare prima di chiedere.

    NEVER ASK SOMEBODY TO DO INFORMATION WORK ORA CAN DO ITSELF.
    READING IS NOT AN EFFECT. IT DOES NOT NEED CONSENT.

Una revisione vera aveva prodotto questa riga: «posso verificare l'orario di
partenza per la vacanza» — e subito sotto la domanda «parti la mattina del 20
o l'impegno dura tutto il giorno?». Le due frasi insieme sono una promessa e
il suo contrario nello stesso respiro: ORA dice di poter guardare e intanto fa
guardare la persona. La domanda non era sbagliata, era prematura.

Quindi, prima che una domanda arrivi a qualcuno, il codice raccoglie quello
che ORA puo' gia' leggere da sola su quel punto — le versioni successive di un
impegno, i collegamenti che qualcuno ha gia' deciso, i disaccordi registrati,
cosa e' stato annullato e quando — e chiede a chi ragiona una cosa sola: con
questo davanti, sai gia' rispondere alla tua domanda?

Se sa, la domanda sparisce e al suo posto c'e' quello che ha trovato. Se non
sa, la domanda resta e resta legittima, perche' e' l'ultima cosa rimasta e non
la prima. Niente qui tocca il mondo: si leggono righe che esistono gia', e
chiedere il permesso di leggerle sarebbe trasformare l'aiuto in un quiz.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from opportunities.models import EvidenceRef, Opportunity, OpportunityDecision

logger = logging.getLogger(__name__)

# Quanto puo' costare un tentativo. Limiti di quantita', non di merito.
MAX_VERSIONS = 12
MAX_LINKS = 10
MAX_PAPERS = 6


async def what_ora_can_read_alone(
    db, user_id: str, refs: List[str],
) -> Dict[str, Any]:
    """
    Tutto quello che ORA puo' guardare da sola intorno a questi riferimenti.

    Nessuna sorgente esterna e nessuna scrittura: la storia delle letture di
    un impegno, i collegamenti gia' decisi e i documenti che qualcuno ha
    legato a questa cosa. Fatti, non conclusioni — quale versione valga e' la
    domanda, e non la si risponde qui dentro.
    """
    wanted = [str(r) for r in refs if str(r).strip()][:8]
    out: Dict[str, Any] = {
        "how_the_appointment_was_read_over_time": [],
        "other_rows_that_look_like_the_same_thing": [],
        "links_somebody_already_decided": [],
        "papers_and_messages_tied_to_it": [],
    }
    if not wanted:
        return out

    # --- come quell'impegno e' stato letto nel tempo ----------------------
    #
    # Comprese le letture superate e gli annullamenti: e' esattamente la
    # storia che dice se due righe sono due versioni della stessa cosa o due
    # cose diverse, e nessuno l'aveva mai messa davanti a chi decide.
    from ingestion.reading import plain

    try:
        rows = await db.ingestion_events.find(
            {"user_id": user_id, "external_id": {"$in": wanted}},
            {"_id": 0, "external_id": 1, "normalized_payload": 1,
             "ingested_at": 1, "ingestion_status": 1},
        ).sort("ingested_at", -1).to_list(60)
    except Exception as e:
        logger.info("versions read soft-fail: %s", type(e).__name__)
        rows = []

    for row in rows[:MAX_VERSIONS]:
        payload = plain(row.get("normalized_payload"))
        out["how_the_appointment_was_read_over_time"].append({
            "ref": row.get("external_id"),
            "title": str(payload.get("title") or "")[:120],
            "starts_at": payload.get("starts_at"),
            "ends_at": payload.get("ends_at"),
            "status": payload.get("status"),
            "where": str(payload.get("location") or "")[:80] or None,
            "read_at": row.get("ingested_at"),
            "still_current": row.get("ingestion_status") != "superseded",
        })

    # --- e chi altro, in agenda, porta lo stesso nome ---------------------
    #
    #     «È STATO ANNULLATO» E' UNA FRASE SU UNA RIGA, NON SU UN VIAGGIO.
    #
    # Trovato provando questa verifica su una vita vera: dello stesso viaggio
    # il calendario teneva quattro copie, tre annullate e una viva. Le note di
    # annullamento erano state scritte guardando le copie morte e appese alla
    # riga viva, e chi ha provato a rispondere con quelle davanti ha concluso
    # che il viaggio era annullato — che era falso, ed e' esattamente il tipo
    # di risposta che sarebbe stato meglio non dare affatto.
    #
    # Quindi accanto alla riga di cui si parla vanno le sue omonime, con il
    # loro stato. Chi guarda vede quattro righe uguali di cui tre barrate, e
    # quella e' un'informazione, non un'opinione.
    titles = {
        str(r.get("title") or "").strip().lower()
        for r in out["how_the_appointment_was_read_over_time"]
        if r.get("title")
    }
    if titles:
        try:
            twins = await db.ingestion_events.find(
                {"user_id": user_id, "source_record_type": "calendar_event",
                 "ingestion_status": {"$ne": "superseded"}},
                {"_id": 0, "external_id": 1, "normalized_payload": 1},
            ).sort("ingested_at", -1).to_list(400)
        except Exception as e:
            logger.info("twins read soft-fail: %s", type(e).__name__)
            twins = []
        already = set(wanted)
        for row in twins:
            ref = str(row.get("external_id") or "")
            if not ref or ref in already:
                continue
            payload = plain(row.get("normalized_payload"))
            title = str(payload.get("title") or "").strip()
            if title.lower() not in titles:
                continue
            already.add(ref)
            out["other_rows_that_look_like_the_same_thing"].append({
                "ref": ref,
                "title": title[:120],
                "starts_at": payload.get("starts_at"),
                "status": payload.get("status"),
            })
            if len(out["other_rows_that_look_like_the_same_thing"]) >= MAX_VERSIONS:
                break

    # --- cosa qualcuno ha gia' deciso che sta insieme ---------------------
    try:
        links = await db.connected_situation_links.find(
            {"owner_id": user_id,
             "$or": [{"target_ref": {"$in": wanted}},
                     {"id": {"$in": wanted}},
                     {"source_object_ref": {"$in": wanted}}]},
            {"_id": 0, "id": 1, "relationship": 1, "reason_summary": 1,
             "target_ref": 1, "source_object_ref": 1, "source_type": 1,
             "disagreements": 1, "decided_at": 1},
        ).sort("decided_at", -1).to_list(30)
    except Exception as e:
        logger.info("links read soft-fail: %s", type(e).__name__)
        links = []

    papers: List[str] = []
    for link in links[:MAX_LINKS]:
        out["links_somebody_already_decided"].append({
            "ref": link.get("id"),
            "what_it_says": str(link.get("reason_summary") or "")[:200],
            "how_they_are_related": link.get("relationship"),
            "about": link.get("target_ref"),
            # Di quale riga parlava chi ha scritto la nota. Senza questo,
            # «e' stato annullato» sembra riferito alla riga viva anche quando
            # chi lo ha scritto stava guardando una copia morta.
            "the_row_it_was_written_about": link.get("source_object_ref") or None,
            "from_a": link.get("source_type"),
            "decided_at": link.get("decided_at"),
            "what_each_source_says": (link.get("disagreements") or [])[:2] or None,
        })
        source = str(link.get("source_object_ref") or "")
        if source and source not in wanted:
            papers.append(source)

    # --- e i documenti che portano quel nome ------------------------------
    if papers:
        try:
            docs = await db.documents.find(
                {"user_id": user_id, "id": {"$in": papers[:MAX_PAPERS]},
                 "deleted": {"$ne": True}},
                {"_id": 0, "id": 1, "display_title": 1, "title": 1,
                 "document_type": 1, "created_at": 1},
            ).to_list(MAX_PAPERS)
        except Exception as e:
            logger.info("papers read soft-fail: %s", type(e).__name__)
            docs = []
        for doc in docs:
            out["papers_and_messages_tied_to_it"].append({
                "ref": doc.get("id"),
                "what_it_is": str(
                    doc.get("display_title") or doc.get("title") or ""
                )[:120],
                "kind": doc.get("document_type"),
                "filed_at": doc.get("created_at"),
            })
    return out


async def try_to_settle_it(
    db, user_id: str, opportunity: Opportunity, *, language: str = "it",
) -> Dict[str, Any]:
    """
    Guardare da sola prima di far guardare qualcun altro.

    Torna quello che e' successo: `settled` quando la domanda ha trovato
    risposta senza disturbare nessuno, `asked` quando la domanda resta perche'
    davvero manca qualcosa che solo una persona sa, `unavailable` quando non
    si e' potuto nemmeno provare — e quest'ultimo non e' un fallimento della
    verifica, e' l'assenza della verifica: la domanda resta esattamente com'e'
    e nessuno finge che sia stata controllata.
    """
    from opportunities.reasoning import settle_it

    if not opportunity.requires_clarification:
        return {"outcome": "nothing_to_settle"}

    refs = [e.ref for e in opportunity.evidence]
    at_hand = await what_ora_can_read_alone(db, user_id, refs)
    if not any(at_hand.values()):
        # Niente da leggere: la domanda e' gia' l'ultima risorsa.
        return {"outcome": "asked", "why": "non c'era niente da guardare"}

    answer = await settle_it(
        {
            "what_i_noticed": opportunity.semantic_summary,
            "why_it_matters": opportunity.why_it_matters,
            "what_i_was_going_to_ask": opportunity.clarifying_question,
            "what_i_said_i_could_do": opportunity.what_ora_can_do,
            "what_i_can_read_by_myself": at_hand,
        },
        language=language,
    )
    if answer is None:
        return {"outcome": "unavailable"}

    if not answer.get("settled"):
        #     CHIEDERE DOPO AVER GUARDATO E' UN'ALTRA COSA DA CHIEDERE E BASTA.
        #
        # La domanda resta, ma non resta com'era: diventa quella che manca
        # davvero dopo il tentativo, e accanto le va cosa ORA ha gia'
        # guardato. Chi riceve una domanda ha diritto di sapere che e'
        # l'ultima cosa rimasta e non la prima tentata.
        looked = str(answer.get("what_i_checked") or "").strip()
        asking = str(answer.get("question") or "").strip()
        if looked:
            opportunity.what_ora_can_do = looked[:300]
        if asking:
            opportunity.clarifying_question = asking[:300]
        if looked or asking:
            opportunity.touch()
        return {
            "outcome": "asked",
            "looked_at": looked,
            "why": asking or "resta una domanda per una persona",
        }

    found = str(answer.get("answer") or "").strip()
    if not found:
        return {"outcome": "asked", "why": "la risposta era vuota"}

    rested_on = [
        str(r) for r in (answer.get("what_it_rests_on") or []) if str(r).strip()
    ][:4]
    known = {e.ref for e in opportunity.evidence}
    for ref in rested_on:
        if ref not in known and len(opportunity.evidence) < 8:
            opportunity.evidence.append(EvidenceRef(kind="checked", ref=ref))

    opportunity.what_ora_can_do = found[:300]
    opportunity.requires_clarification = False
    opportunity.clarifying_question = ""
    opportunity.touch()
    return {"outcome": "settled", "answer": found, "rested_on": rested_on}


def decision_for(opportunity: Opportunity, settled: Dict[str, Any]) -> Optional[
    OpportunityDecision
]:
    """
    La riga che dice che ORA ha guardato prima di chiedere.

    Senza questa, fra un mese «perche' non me l'ha chiesto» e «perche' non
    l'ha verificato» sono indistinguibili, e sono due cose molto diverse.
    """
    if settled.get("outcome") != "settled":
        return None
    return OpportunityDecision(
        opportunity_id=opportunity.id,
        owner_id=opportunity.owner_id,
        outcome="update",
        source="model",
        rationale=f"ha guardato da sola prima di chiedere: {settled['answer']}"[:400],
    )
