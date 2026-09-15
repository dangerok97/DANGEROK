"""
Le sessioni di studio pianificate, quando una telefonata le sposta.

    «HO CHIAMATO IL PROF: IL RICEVIMENTO È GIOVEDÌ, NON MARTEDÌ».

Il piano di studio non è un calendario e non è un elenco di impegni: è una
sequenza che si regge sul proprio avanzamento. Spostare una sessione non
significa spostare una riga — significa ricalcolare il progresso del piano, e
risincronizzare l'evento Google se quella sessione ne aveva uno.

Tutto questo lo fa già `StudyPlanService.session_action`, che è l'unico
scrittore di quello stato. Questo file non lo rifà: gli arriva davanti con un
esito confermato e i controlli fatti.

    E QUELLO CHE IL PIANO NON SA FARE, QUI NON SI INVENTA.

Una sessione si sposta in avanti — è quello che significa `snooze`, ed è
l'unico movimento che il piano conosce. Un accordo telefonico che la
anticipasse non trova una porta: si ferma, e lo dice. Aprirne una nuova
vorrebbe dire scrivere `starts_at` da qui, cioè diventare il secondo scrittore
di uno stato che ne ha già uno.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("ora.telephone.apply.study")

DOMAIN = "study"
OPERATIONS = ("reschedule", "complete", "cancel")

# Che cosa una telefonata può aver confermato su una sessione.
CONFIRMED_KEYS = frozenset({"appointment_date", "appointment_time", "new_date"})

# Gli stati da cui una sessione non torna indietro.
FINISHED = ("completed", "skipped")

# Quanto può slittare al massimo una sessione, in minuti. Sessanta giorni: non
# è una regola di prodotto, è un parafulmine contro un delta assurdo nato da
# una data letta storta. L'autorità vera decide prima di qui.
MOST_IT_CAN_SLIDE_MIN = 60 * 24 * 60


# ---------------------------------------------------------------------------
# 1 · Che cosa si fotografa prima di comporre il numero
# ---------------------------------------------------------------------------


def remembers(row: Dict[str, Any]) -> Dict[str, str]:
    """
    Com'era la sessione quando si è deciso di telefonare.

    L'inizio, perché è quello che si sposta e quello su cui si calcola di
    quanto; e lo stato, perché una sessione già fatta non si sposta più.
    """
    return {
        "starts_at": str((row or {}).get("starts_at") or ""),
        "status": str((row or {}).get("status") or "planned"),
        "title": str((row or {}).get("title") or "")[:120],
    }


# ---------------------------------------------------------------------------
# 4 · La traduzione, che non tocca niente
# ---------------------------------------------------------------------------


def translate(binding, outcome) -> Tuple[Dict[str, str], str]:
    """
    Dall'esito confermato ai campi veri. Puro: nessun database, nessuna rete.

        LO SPOSTAMENTO È UN ISTANTE, NON ANCORA UN DELTA.

    Di quanto slitta lo si può sapere solo davanti alla sessione com'è adesso,
    e «adesso» è una lettura. Qui si ferma l'istante concordato; il delta lo
    calcola chi scrive, un attimo prima di scrivere.
    """
    fare = binding.target.operation
    if fare not in OPERATIONS:
        return {}, f"operazione non applicabile: {fare}"

    cambiamenti = dict(getattr(outcome, "confirmed_changes", None) or {})
    fuori = set(cambiamenti) - CONFIRMED_KEYS
    if fuori:
        return {}, "confermate cose fuori dalla missione: " + ", ".join(sorted(fuori))

    if not binding.target.entity_id:
        return {}, "non c'è una sessione di studio su cui agire"

    if fare in ("complete", "cancel"):
        return {"action": fare}, ""

    giorno = _day(cambiamenti.get("new_date") or cambiamenti.get("appointment_date"))
    if giorno is None:
        return {}, "non c'è una data nuova utilizzabile"
    lancette = _hhmm(cambiamenti.get("appointment_time"))
    if lancette is None:
        return {}, "non c'è un'ora nuova utilizzabile"

    #     «LE 15» SONO LE 15 DI CHI HA TELEFONATO, NON DEL SERVER.
    # Le sessioni di studio sono scritte in UTC; l'accordo è un orario da
    # parete. Fonderli senza convertire sposterebbe ogni sessione dell'offset
    # del fuso — d'estate due ore, e sempre in silenzio.
    quando = _in_their_timezone(giorno, lancette)
    if quando is None:
        return {}, "non riesco a collocare quell'ora in un fuso"
    return {"action": "reschedule", "starts_at": quando.isoformat()}, ""


def _in_their_timezone(giorno, lancette: Tuple[int, int]) -> Optional[datetime]:
    """Quel giorno a quell'ora, dove sta la persona. Con il fuso attaccato."""
    from telephone.mission import _where_they_are

    try:
        from zoneinfo import ZoneInfo

        dove = ZoneInfo(_where_they_are())
    except Exception:
        dove = timezone.utc
    try:
        return datetime(
            giorno.year, giorno.month, giorno.day,
            lancette[0], lancette[1], tzinfo=dove,
        )
    except (ValueError, TypeError):  # pragma: no cover
        return None


# ---------------------------------------------------------------------------
# 3 · Dov'è adesso
# ---------------------------------------------------------------------------


async def look(db, *, binding) -> Optional[Dict[str, Any]]:
    """La sessione come la vede lo stato canonico, o niente."""
    ref = binding.target.entity_id or binding.created_entity_id
    if not ref:
        return None
    return await db.study_sessions.find_one(
        {"id": ref, "user_id": binding.owner_id}, {"_id": 0},
    )


# ---------------------------------------------------------------------------
# 5 · La scrittura
# ---------------------------------------------------------------------------


async def apply(db, *, call, binding, outcome):
    """Sposta, chiude o salta la sessione, se è ancora quella di allora."""
    from telephone.domains.calendar import Verdict

    row = await look(db, binding=binding)
    if row is None:
        return Verdict("failed", error="questa sessione di studio non esiste più")

    dove = str(row.get("status") or "planned")
    if dove in FINISHED:
        return Verdict("skipped", error=f"questa sessione risultava già «{dove}»")

    campi, perche = translate(binding, outcome)
    if perche:
        return Verdict("skipped", error=perche)

    negato = _what_the_authority_says(binding, outcome)
    if negato is not None:
        return negato

    conflitto = detect_conflict(binding, row)
    if conflitto is not None:
        return conflitto

    if campi["action"] == "reschedule":
        minuti, impossibile = _how_far_it_slides(row, campi["starts_at"])
        if impossibile:
            return Verdict("skipped", error=impossibile, fields=campi)
        campi["snooze_minutes"] = str(minuti)

    try:
        await _write_it(db, binding, campi)
    except Exception as e:
        logger.info("sessione non aggiornata: %s", type(e).__name__)
        return Verdict(
            "failed",
            error=f"non sono riuscita ad aggiornare la sessione ({type(e).__name__})",
            fields=campi,
        )
    return Verdict(
        "applied", writes=[f"study:{binding.target.entity_id}"], fields=campi,
    )


def _how_far_it_slides(row: Dict[str, Any], voluto: str) -> Tuple[int, str]:
    """
    Di quanti minuti slitta questa sessione, o perché non può slittare.

        UNA SESSIONE DI STUDIO VA AVANTI.

    `session_action` sposta per differenza, non per destinazione: è così che
    tiene insieme inizio, fine e l'evento Google, e non c'è una seconda porta
    che accetti un istante. Un accordo che anticipasse la sessione passerebbe
    da qui con un numero negativo — e la lascerebbe segnata «rimandata» a
    un'ora precedente, che è una riga che non vuol dire niente.

    Quindi non si forza: si torna il motivo, e la telefonata resta raccontata.
    """
    parte = _utc(str(row.get("starts_at") or ""))
    arriva = _utc(voluto)
    if parte is None or arriva is None:
        return 0, "non riesco a leggere l'orario di questa sessione"

    minuti = int((arriva - parte).total_seconds() // 60)
    if minuti <= 0:
        return 0, "una sessione di studio si può rimandare, non anticipare"
    if minuti > MOST_IT_CAN_SLIDE_MIN:
        return 0, "quella data è troppo lontana perché sia lo stesso piano"
    return minuti, ""


async def _write_it(db, binding, campi: Dict[str, str]) -> None:
    """
    Dalla porta di sempre.

        IL PIANO SI RICALCOLA DA SOLO, SE LO SI LASCIA FARE.

    `session_action` aggiorna la sessione, rilegge il progresso del piano e
    risincronizza l'evento Google. Un `update_one` da qui avrebbe cambiato la
    riga e lasciato le altre due cose a metà.
    """
    from action_engine.study.plan_service import StudyPlanService

    piano = StudyPlanService(db)
    ref = binding.target.entity_id
    fare = campi["action"]

    if fare == "complete":
        esito = await piano.session_action(binding.owner_id, ref, "complete")
    elif fare == "cancel":
        esito = await piano.session_action(binding.owner_id, ref, "skip")
    else:
        esito = await piano.session_action(
            binding.owner_id, ref, "snooze",
            snooze_minutes=int(campi["snooze_minutes"]),
        )

    #     UN «ok: False» È UN FALLIMENTO, ANCHE SE NON SOLLEVA.
    # Il servizio torna un dizionario, e un ritorno che nessuno guarda è un
    # errore che diventa un successo.
    if not (esito or {}).get("ok"):
        raise RuntimeError(str((esito or {}).get("error") or "session_action_failed"))


# ---------------------------------------------------------------------------
# 7 · Il conflitto
# ---------------------------------------------------------------------------


def detect_conflict(binding, row: Dict[str, Any]):
    """
    La sessione è ancora quella su cui la missione era stata scritta?

    Se è stata spostata da qualcun altro dopo che abbiamo composto il numero,
    il delta calcolato sull'inizio di adesso la porterebbe in un posto che
    nessuno ha concordato. È il motivo per cui questo controllo, qui, non è
    una cortesia.
    """
    from telephone.domains.calendar import Verdict

    atteso = (binding.expected or {}).get("starts_at", "")
    adesso = str((row or {}).get("starts_at") or "")
    if atteso and adesso and not _same_moment(atteso, adesso):
        return Verdict(
            "conflict", error="questa sessione è stata spostata dopo la telefonata",
        )

    stato_atteso = (binding.expected or {}).get("status", "")
    stato_adesso = str((row or {}).get("status") or "planned")
    if stato_atteso and stato_adesso != stato_atteso:
        return Verdict(
            "conflict",
            error=f"questa sessione è cambiata dopo la telefonata "
                  f"(era «{stato_atteso}», adesso è «{stato_adesso}»)",
        )
    return None


# ---------------------------------------------------------------------------
# 6 · La riconciliazione
# ---------------------------------------------------------------------------


async def reconcile(db, *, call, binding, outcome):
    """
    Un'applicazione rimasta a metà: la sessione è stata toccata o no?

        QUI «DOVE DOVEVA ARRIVARE» SI SA CON PRECISIONE.

    E per una volta è più facile che altrove: l'istante concordato è scritto
    nell'esito, e la sessione o ci è sopra o non ci è. Se ci è, la scrittura
    era passata e il processo è morto dopo. Se è ferma dov'era, non è mai
    partita. Se è in un terzo posto, ci ha messo mano qualcun altro.
    """
    from telephone.domains.calendar import Verdict

    row = await look(db, binding=binding)
    if row is None:
        return Verdict("failed", error="questa sessione di studio non esiste più")

    campi, perche = translate(binding, outcome)
    if perche:
        return Verdict("skipped", error=perche)

    if _already_there(campi, row):
        return Verdict(
            "applied", writes=[f"study:{binding.target.entity_id}"], fields=campi,
        )

    conflitto = detect_conflict(binding, row)
    if conflitto is not None:
        return conflitto

    return await apply(db, call=call, binding=binding, outcome=outcome)


def _already_there(campi: Dict[str, str], row: Dict[str, Any]) -> bool:
    """Se la sessione è già esattamente dove la missione voleva portarla."""
    adesso = str((row or {}).get("status") or "planned")
    voluto = campi.get("action", "")
    if voluto == "complete":
        return adesso == "completed"
    if voluto == "cancel":
        return adesso == "skipped"
    if voluto == "reschedule":
        if adesso != "snoozed":
            return False
        return _same_moment(
            str(row.get("starts_at") or ""), campi.get("starts_at", ""),
        )
    return False


# ---------------------------------------------------------------------------
# 2 · L'autorità
# ---------------------------------------------------------------------------


def _what_the_authority_says(binding, outcome):
    """Lo stesso giudice del calendario, sullo stesso contratto."""
    from telephone.authority import Proposal, a_slot_from, evaluate_authority
    from telephone.domains.calendar import Verdict

    regole = getattr(binding, "authority", None)
    if regole is None:
        return None

    cambiamenti = dict(getattr(outcome, "confirmed_changes", None) or {})
    quando = a_slot_from(
        cambiamenti.get("new_date") or cambiamenti.get("appointment_date", ""),
        cambiamenti.get("appointment_time", ""),
    )
    responso = evaluate_authority(
        Proposal(
            operation=binding.target.operation,
            slot=quando if quando.is_real() else None,
            entity_id=binding.target.entity_id,
        ),
        regole,
    )
    if responso.verdict in ("allowed", "invalid"):
        return None
    logger.info("l'autorità non consente questa scrittura: %s", responso.code)
    return Verdict("skipped", error=responso.says or responso.code)


# ---------------------------------------------------------------------------
# 8 · Come si racconta
# ---------------------------------------------------------------------------


def says(operation: str, fields: Dict[str, str]) -> str:
    """Come si racconta a chi non c'era. Lo studio parla di sessioni."""
    if operation == "complete":
        return "Sessione di studio segnata come fatta."
    if operation == "cancel":
        return "Sessione di studio saltata."
    quando = _read(fields.get("starts_at", ""))
    if quando is None:
        return "Sessione di studio spostata."
    return f"Sessione di studio spostata a {quando.strftime('%d/%m alle %H:%M')}."


# ---------------------------------------------------------------------------
# Orologi
# ---------------------------------------------------------------------------


def _day(valore: Any):
    testo = str(valore or "").strip()[:10]
    try:
        return datetime.strptime(testo, "%Y-%m-%d").date()
    except ValueError:
        return None


def _hhmm(valore: Any) -> Optional[Tuple[int, int]]:
    testo = str(valore or "").strip()[:5]
    try:
        h, m = testo.split(":")
        ore, minuti = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    if 0 <= ore <= 23 and 0 <= minuti <= 59:
        return ore, minuti
    return None


def _read(iso: str) -> Optional[datetime]:
    testo = (iso or "").strip()
    if not testo:
        return None
    try:
        return datetime.fromisoformat(testo.replace("Z", "+00:00"))
    except ValueError:
        return None


def _utc(iso: str) -> Optional[datetime]:
    """
    Lo stesso istante, sempre con un fuso addosso.

        QUI UN ORARIO SENZA FUSO È UTC, E NON È UNA SUPPOSIZIONE.

    Il modello lo dichiara: `starts_at` è UTC ISO. Trattare un orario nudo
    come ora locale, in questo dominio, sposterebbe le sessioni dell'offset
    ogni volta che qualcuno scrive una data a mano.
    """
    quando = _read(iso)
    if quando is None:
        return None
    return quando if quando.tzinfo is not None else quando.replace(tzinfo=timezone.utc)


def _same_moment(a: str, b: str) -> bool:
    """Stesso istante, comunque sia scritto il fuso."""
    x, y = _utc(a), _utc(b)
    if x is None or y is None:
        return (a or "").strip() == (b or "").strip()
    return x == y
