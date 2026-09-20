"""
L'esito torna nella chat da cui è partita la telefonata.

    «SÌ, CHIAMALA» E «COM'È ANDATA» STANNO NELLA STESSA CONVERSAZIONE.

La persona ha dato il via libera in chat: è lì che guarda per sapere com'è
finita. Una riga sola, scritta una volta sola, con le stesse parole dello
storico delle chiamate — mai un id, mai uno stato tecnico.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("ora.telephone.chat_report")

#     «CHIAMATA FINITA» NON VUOL DIRE «MESSAGGIO CONSEGNATO».
# Quando la linea non si è mai aperta non c'è una missione da raccontare:
# si dice che non ci si è riuscite a parlare.
_LINEA = {
    "nessuna_risposta": "Non sono riuscita a parlare con {chi}: non ha risposto.",
    "occupato": "Non sono riuscita a parlare con {chi}: il numero era occupato.",
    "segreteria": "Non sono riuscita a parlare con {chi}: ha risposto la segreteria.",
    "non_avviata": "La telefonata a {chi} non è mai partita.",
    "interrotta": "La telefonata non è andata a buon fine.",
}


def what_to_tell_the_chat(call) -> Optional[str]:
    """La riga per la chat, o None se la telefonata non è ancora finita."""
    from telephone.history import _the_mission_outcome, how_it_reads, in_one_line

    stato = how_it_reads(call)
    if stato == "in_corso":
        return None
    if stato in _LINEA:
        chi = ((getattr(call.mandate, "recipient", "") or call.calling_whom
                or "").split() or ["questa persona"])[0]
        return _LINEA[stato].format(chi=chi)
    if not (call.mandate and call.mandate.message):
        return in_one_line(call)

    esito = _the_mission_outcome(call) or {}
    chi = ((call.mandate.recipient or call.calling_whom or "").split() or ["lei"])[0]
    if str(esito.get("delivery") or "") == "delivered":
        from telephone.history import a_chi

        riga = f"Messaggio consegnato {a_chi(chi)}."
        risposta = str(esito.get("recipient_reply") or "").strip()
        if risposta:
            riga += f" Ti ha risposto: «{risposta}»"
        return riga
    return in_one_line(call)


async def tell_the_chat(db, call) -> bool:
    """
    Scrive l'esito nella chat di origine. Una volta sola, anche se chiamata due volte.

    Torna True se ha scritto.
    """
    chat = str(getattr(call, "chat_session_id", "") or "")
    if not chat or getattr(call, "told_the_chat", False):
        return False
    try:
        from telephone.service import TelephoneService

        fresca = await TelephoneService(db).get(call.owner_id, call.id) or call
        riga = what_to_tell_the_chat(fresca)
        if not riga:
            return False
        #     UNA VOLTA SOLA: CHI ARRIVA SECONDO TROVA IL POSTO GIÀ PRESO.
        # Il posto preso non basta a dire «è scritto»: per quello c'è
        # `chat_told_at`, messo solo dopo la riga. Misurato sul vero: la chat
        # ha visto il posto preso, ha riletto la conversazione un istante
        # prima che la riga arrivasse, e ha smesso di aspettare.
        preso = await db.phone_calls.find_one_and_update(
            {"id": call.id, "told_the_chat": {"$in": [False, None]}},
            {"$set": {"told_the_chat": True}},
        )
        if preso is None:
            return False

        from conversation_engine.models import HistoryEntry
        from conversation_engine.ai_core.orchestrator import _new_message_id

        mid = _new_message_id()
        voce = HistoryEntry(role="ora", kind="answer", text=riga, step_id=mid,
                            meta={"message_id": mid}).model_dump()
        await db.conversation_sessions.update_one(
            {"id": chat, "user_id": call.owner_id},
            {"$push": {"history": voce}},
        )
        from telephone.models import now_iso

        await db.phone_calls.update_one(
            {"id": call.id}, {"$set": {"chat_told_at": now_iso()}})
        #     IL LAVORO E' FINITO: NON SI CHIEDE PIU' NIENTE PER LUI.
        # «Vuoi che la chiami?» non ha senso su una telefonata già fatta.
        try:
            from waiting.service import get_waiting_service

            await get_waiting_service(db).close_for_work(
                call.owner_id, session_id=chat, reason="call_finished",
            )
        except Exception as e:  # pragma: no cover
            logger.info("domande della chat non chiuse: %s", type(e).__name__)

        call.told_the_chat = True
        return True
    except Exception as e:  # pragma: no cover
        logger.info("esito non riportato in chat: %s", type(e).__name__)
        return False


async def calling_from(db, owner_id: str, chat_session_id: str) -> bool:
    """Se da questa chat c'è una telefonata partita e non ancora raccontata."""
    riga = await db.phone_calls.find_one({
        "owner_id": owner_id,
        "chat_session_id": chat_session_id,
        "chat_told_at": {"$in": ["", None]},
        "state": {"$in": ["dialling", "talking", "ended", "failed"]},
        #     SOLO SE E' PARTITA DAVVERO.
        # Una telefonata che l'operatore ha rifiutato subito l'ha già detta la
        # chat, in quel turno: non c'è niente da aspettare.
        "provider_ref": {"$nin": ["", None]},
    }, {"_id": 0, "id": 1})
    return riga is not None
