"""
Quello che ORA tiene aperto, e che una telefonata può chiudere o rimandare.

    «HO CHIAMATO IL COMMERCIALISTA: LA PRATICA SLITTA AL VENTI».

È un impegno che cambia stato, non un appuntamento che si sposta. Il
calendario non c'entra: qui c'è una cosa da fare, con una scadenza, che dopo
una telefonata è fatta oppure è più in là.

Il percorso di scrittura esiste da prima di questo file e non si tocca.
`ActionCenterService` è l'unico che scrive lo stato di una decisione: valida la
transizione contro la macchina a stati, scrive la riga di audit **prima** della
mutazione, e tiene allineato il campo legacy. Quello che mancava — e che questo
file aggiunge — è che ci si possa arrivare da una telefonata con gli stessi
otto doveri del calendario.

    E NON SI INVENTA NIENTE DI NUOVO PER ARRIVARCI.

Nessuna collezione, nessuno stato, nessuna transizione. Un dominio che per
essere raggiunto dal telefono avesse bisogno di un proprio storage sarebbe un
secondo prodotto, non un secondo adattatore — e la macchina a stati che
esisteva prima diventerebbe una delle due verità in circolazione.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("ora.telephone.apply.commitments")

DOMAIN = "commitments"
OPERATIONS = ("complete", "postpone", "cancel")

# Che cosa una telefonata può aver confermato su un impegno. Elenco chiuso di
# proposito: una chiave che non è qui dentro è una cosa che nessuno ha chiesto
# il permesso di cambiare.
CONFIRMED_KEYS = frozenset({"appointment_date", "appointment_time", "new_date"})

# Gli stati da cui non si esce più, secondo la macchina a stati vera. Non è un
# elenco nostro: è `TERMINAL_STATUSES`, riletto qui col nome del telefono.
FINISHED = ("completed", "dismissed")

# A che ora slitta un impegno rimandato a un giorno e basta. La mattina: un
# impegno senza un'ora è una cosa da fare quel giorno, non a mezzanotte.
DEFAULT_TIME = "09:00"


# ---------------------------------------------------------------------------
# 1 · Che cosa si fotografa prima di comporre il numero
# ---------------------------------------------------------------------------


def remembers(row: Dict[str, Any]) -> Dict[str, str]:
    """
    Com'era l'impegno quando si è deciso di telefonare.

        UN APPUNTAMENTO È IL SUO ORARIO. UN IMPEGNO È IL SUO STATO.

    Per il calendario la scadenza della missione è l'ora di inizio; qui è dove
    l'impegno stava nella macchina a stati. Se nel frattempo qualcuno l'ha già
    chiuso o rimandato dall'applicazione, l'accordo preso al telefono parlava
    di una cosa che non è più così.
    """
    return {
        "status": _where_it_stands(row),
        "title": str((row or {}).get("title") or "")[:120],
    }


# ---------------------------------------------------------------------------
# 4 · La traduzione, che non tocca niente
# ---------------------------------------------------------------------------


def translate(binding, outcome) -> Tuple[Dict[str, str], str]:
    """
    Dall'esito confermato ai campi veri. Puro: nessun database, nessuna rete.

    Chiudere non ha bisogno di una data. Rimandare sì, e senza quella non è un
    rinvio: è un'intenzione.
    """
    fare = binding.target.operation
    if fare not in OPERATIONS:
        return {}, f"operazione non applicabile: {fare}"

    cambiamenti = dict(getattr(outcome, "confirmed_changes", None) or {})
    fuori = set(cambiamenti) - CONFIRMED_KEYS
    if fuori:
        return {}, "confermate cose fuori dalla missione: " + ", ".join(sorted(fuori))

    if not binding.target.entity_id:
        return {}, "non c'è un impegno su cui agire"

    if fare in ("complete", "cancel"):
        return {"action": fare}, ""

    #     UN RINVIO SENZA UNA DATA NON È UN RINVIO.
    giorno = _day(cambiamenti.get("new_date") or cambiamenti.get("appointment_date"))
    if giorno is None:
        return {}, "non c'è una data nuova utilizzabile"
    ora = (cambiamenti.get("appointment_time") or "").strip()[:5] or DEFAULT_TIME
    return {"action": "postpone", "until": f"{giorno.isoformat()}T{ora}:00"}, ""


# ---------------------------------------------------------------------------
# 3 · Dov'è adesso
# ---------------------------------------------------------------------------


async def look(db, *, binding) -> Optional[Dict[str, Any]]:
    """L'impegno come lo vede lo stato canonico, o niente."""
    ref = binding.target.entity_id or binding.created_entity_id
    if not ref:
        return None
    return await db.decisions.find_one(
        {"id": ref, "user_id": binding.owner_id}, {"_id": 0},
    )


def _where_it_stands(row: Dict[str, Any]) -> str:
    """
    Lo stato corrente, comunque sia scritto.

    `action_state.status` è quello vero; `status` è il campo legacy che il
    servizio tiene allineato per i client vecchi. Si legge il primo, e si
    ripiega sul secondo soltanto per le righe nate prima dell'Action Center.
    """
    stato = ((row or {}).get("action_state") or {}).get("status")
    if stato:
        return str(stato)
    legacy = str((row or {}).get("status") or "open")
    return {
        "open": "pending", "in_progress": "in_progress",
        "completed": "completed", "dismissed": "dismissed",
    }.get(legacy, "pending")


# ---------------------------------------------------------------------------
# 5 · La scrittura
# ---------------------------------------------------------------------------


async def apply(db, *, call, binding, outcome):
    """Chiude o rimanda l'impegno, se è ancora quello di cui si parlava."""
    from telephone.domains.calendar import Verdict

    row = await look(db, binding=binding)
    if row is None:
        return Verdict("failed", error="questo impegno non è più fra i tuoi")

    dove = _where_it_stands(row)
    if dove in FINISHED:
        #     ERA GIÀ CHIUSO, E NON È DETTO CHE L'ABBIAMO CHIUSO NOI.
        # La macchina a stati non lascia uscire da qui, e tentare comunque
        # vorrebbe dire sollevare un'eccezione per una cosa che si sapeva.
        return Verdict("skipped", error=f"questo impegno risultava già «{dove}»")

    campi, perche = translate(binding, outcome)
    if perche:
        return Verdict("skipped", error=perche)

    negato = _what_the_authority_says(binding, outcome)
    if negato is not None:
        return negato

    conflitto = detect_conflict(binding, row)
    if conflitto is not None:
        return conflitto

    try:
        await _write_it(db, binding, campi, outcome)
    except Exception as e:
        logger.info("impegno non aggiornato: %s", type(e).__name__)
        return Verdict(
            "failed",
            error=f"non sono riuscita ad aggiornare l'impegno ({type(e).__name__})",
            fields=campi,
        )
    return Verdict(
        "applied", writes=[f"commitments:{binding.target.entity_id}"], fields=campi,
    )


async def _write_it(db, binding, campi: Dict[str, str], outcome) -> None:
    """
    Dalla porta di sempre.

        LA MACCHINA A STATI ESISTEVA PRIMA DI QUESTA TELEFONATA.

    `ActionCenterService` valida la transizione, scrive la riga di audit prima
    della mutazione e tiene allineato il campo legacy. Scrivere in Mongo da qui
    sarebbe stato più corto e avrebbe saltato tutte e tre le cose.
    """
    from action_center.service import ActionCenterService

    centro = ActionCenterService(db)
    ref = binding.target.entity_id
    perche = (getattr(outcome, "notes", "") or "")[:200] or "concordato al telefono"

    if campi["action"] == "complete":
        await centro.complete(binding.owner_id, ref, note=perche)
    elif campi["action"] == "cancel":
        await centro.dismiss(binding.owner_id, ref, reason=perche)
    else:
        await centro.postpone(
            binding.owner_id, ref, until_datetime=campi["until"], reason=perche,
        )


# ---------------------------------------------------------------------------
# 7 · Il conflitto
# ---------------------------------------------------------------------------


def detect_conflict(binding, row: Dict[str, Any]):
    """
    L'impegno è ancora quello su cui la missione era stata scritta?

        SE QUALCUNO L'HA GIÀ MOSSO, LA PREMESSA È SCADUTA.

    Stessa domanda del calendario, su un campo diverso. Se non torna, l'accordo
    preso al telefono riguardava una cosa che non è più così, e sopra non si
    scrive.
    """
    from telephone.domains.calendar import Verdict

    atteso = (binding.expected or {}).get("status", "")
    if not atteso:
        return None
    adesso = _where_it_stands(row)
    if adesso != atteso:
        return Verdict(
            "conflict",
            error=f"questo impegno è cambiato dopo la telefonata "
                  f"(era «{atteso}», adesso è «{adesso}»)",
        )
    return None


# ---------------------------------------------------------------------------
# 6 · La riconciliazione
# ---------------------------------------------------------------------------


async def reconcile(db, *, call, binding, outcome):
    """
    Un'applicazione rimasta a metà: l'impegno è stato toccato o no?

    Tre posizioni, come per il calendario. È già dove doveva arrivare: la
    scrittura era andata, e si chiude senza rifarla. È ancora dov'era: non è
    mai partita, si riprova una volta sola. È altrove: qualcuno ci ha messo
    mano, e sopra non si scrive.
    """
    from telephone.domains.calendar import Verdict

    row = await look(db, binding=binding)
    if row is None:
        return Verdict("failed", error="questo impegno non è più fra i tuoi")

    campi, perche = translate(binding, outcome)
    if perche:
        return Verdict("skipped", error=perche)

    if _already_there(campi, row):
        #     LA SCRITTURA ERA PASSATA: IL PROCESSO È MORTO DOPO.
        return Verdict(
            "applied",
            writes=[f"commitments:{binding.target.entity_id}"],
            fields=campi,
        )

    conflitto = detect_conflict(binding, row)
    if conflitto is not None:
        return conflitto

    return await apply(db, call=call, binding=binding, outcome=outcome)


def _already_there(campi: Dict[str, str], row: Dict[str, Any]) -> bool:
    """Se l'impegno è già arrivato esattamente dove la missione voleva."""
    adesso = _where_it_stands(row)
    voluto = campi.get("action", "")
    if voluto == "complete":
        return adesso == "completed"
    if voluto == "cancel":
        return adesso == "dismissed"
    if voluto == "postpone":
        if adesso != "postponed":
            return False
        #     RIMANDATO SÌ, MA A QUANDO?
        # Un impegno rimandato da qualcun altro a un giorno diverso non è la
        # nostra scrittura arrivata: è un'altra scrittura.
        fino = str(((row.get("action_state") or {}).get("postponed_until")) or "")
        return _same_moment(fino, campi.get("until", ""))
    return False


# ---------------------------------------------------------------------------
# 2 · L'autorità
# ---------------------------------------------------------------------------


def _what_the_authority_says(binding, outcome):
    """
    Lo stesso giudice del calendario, sullo stesso contratto.

        UN DOMINIO NUOVO NON SI SCRIVE UN'AUTORITÀ SUA.

    `evaluate_authority` non sa che cosa sia un impegno, e non deve saperlo:
    riceve un'operazione, un oggetto e un orario, e risponde. Un secondo
    giudice vorrebbe dire due modi di dire di no, e prima o poi uno dei due
    direbbe di sì.
    """
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
    """Come si racconta a chi non c'era. Gli impegni parlano di stati."""
    if operation == "complete":
        return "Impegno chiuso."
    if operation == "cancel":
        return "Impegno lasciato cadere."
    quando = _read(fields.get("until", ""))
    return f"Rimandato al {quando.strftime('%d/%m')}." if quando else "Rimandato."


# ---------------------------------------------------------------------------
# Orologi
# ---------------------------------------------------------------------------


def _day(valore: Any):
    testo = str(valore or "").strip()[:10]
    try:
        return datetime.strptime(testo, "%Y-%m-%d").date()
    except ValueError:
        return None


def _read(iso: str) -> Optional[datetime]:
    testo = (iso or "").strip()
    if not testo:
        return None
    try:
        return datetime.fromisoformat(testo.replace("Z", "+00:00"))
    except ValueError:
        return None


def _same_moment(a: str, b: str) -> bool:
    x, y = _read(a), _read(b)
    if x is None or y is None:
        return (a or "").strip() == (b or "").strip()
    if (x.tzinfo is None) != (y.tzinfo is None):
        return x.replace(tzinfo=None) == y.replace(tzinfo=None)
    return x == y
