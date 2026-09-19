"""
Quello che serve sapere prima di comporre un numero.

    UNA MISSIONE NON È UN MODULO COMPILATO: È UNA CONVERSAZIONE POSSIBILE.

Fino a ieri una telefonata partiva solo se una persona aveva già messo in fila
tutto a mano — il numero, l'appuntamento, l'orario nuovo, le alternative. ORA
capiva la frase e basta. Questo file è il posto in cui quella fila si compone
da sola, e in cui si scopre che cosa manca ancora.

    NON È UN SECONDO PIANO.

`AutonomousActionPlan` dice a che punto è il proposito; questo dice se la
telefonata si può fare. Sono due domande diverse, e tenerle nello stesso
oggetto vorrebbe dire che «pronta» e «autorizzata» finiscono per assomigliarsi
— e a quel punto basta un giro storto perché una missione mezza vuota trovi la
strada verso un telefono.

    DUE CANCELLI, E NON SI APRONO CON LA STESSA CHIAVE.

`number_confirmed` lo apre una persona guardando un numero. `conversation_ready`
lo apre una valutazione su quanto si sa. Servono tutti e due, perché rispondono
a due modi diversi di sbagliare: telefonare alla persona giusta senza sapere
cosa dirle, e sapere benissimo cosa dire a un numero sbagliato.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from preparation.contacts import ContactCandidate

logger = logging.getLogger("ora.preparation")

PREPARATIONS = "mission_preparations"

# Dove può stare una preparazione. Quattro parole, e tre di queste non sono
# guasti: sono modi legittimi di non essere ancora pronti.
Readiness = Literal["READY", "NEEDS_INFO", "AMBIGUOUS", "BLOCKED"]

COME_SI_LEGGE: Dict[str, str] = {
    "READY": "Pronta",
    "NEEDS_INFO": "Mi manca qualcosa",
    "AMBIGUOUS": "Non so a chi ti riferisci",
    "BLOCKED": "Così non posso telefonare",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_preparation_id() -> str:
    return f"prep_{uuid.uuid4().hex[:16]}"


def request_key_for(owner_id: str, user_request: str) -> str:
    """
    L'identità stabile di una richiesta.

        LA STESSA FRASE, DETTA DUE VOLTE, È LA STESSA RICHIESTA.

    Non si guarda l'orario e non si guarda un identificativo fresco: si guarda
    quello che una persona ha chiesto, ridotto alla sua forma essenziale.
    Ripeterla — perché la rete è caduta, perché si è premuto due volte — non
    deve aprire una seconda pratica accanto alla prima.

    Si taglia a un digest perché una richiesta può essere lunga e una chiave
    deve stare in un indice; il testo per intero resta nel documento, dove una
    persona può rileggerlo.
    """
    pulita = re.sub(r"\s+", " ", (user_request or "").strip().lower())
    pulita = re.sub(r"[^\w\s]", "", pulita)
    digest = hashlib.sha256(pulita.encode("utf-8")).hexdigest()[:24]
    return f"{owner_id}|request|{digest}"


class MissingInformation(BaseModel):
    """
    Una cosa che manca, e la domanda che la otterrebbe.

        SI CHIEDE UNA COSA PER VOLTA, E SOLO QUELLE CHE MANCANO.

    Un modulo chiede tutto e fa sentire interrogato chi aveva solo detto una
    frase. Qui ogni riga esiste perché qualcosa non si è potuto ricavare, e
    porta con sé la domanda già scritta in italiano — perché una mancanza senza
    domanda è un problema di chi programma, non una cosa da mostrare.
    """

    field: str = Field(default="", max_length=48)
    question: str = Field(default="", max_length=300)
    # Perché serve: si mostra solo se qualcuno chiede «e perché ti serve?».
    why: str = Field(default="", max_length=200)
    # Quello che ORA ha già e che la domanda dà per acquisito. Serve a non
    # richiedere nella domanda quello che si sta già dicendo di sapere.
    already_known: str = Field(default="", max_length=300)
    answered: bool = False
    answer: str = Field(default="", max_length=300)


class MissionPreparation(BaseModel):
    """Da «chiama Lorenzo» a una telefonata che si può davvero fare."""

    preparation_id: str = Field(default_factory=new_preparation_id, max_length=40)
    owner_id: str = Field(min_length=1, max_length=64)
    # Il piano a cui appartiene. Resta lo stesso per tutta la preparazione, e
    # anche dopo: una preparazione non genera un proposito nuovo, lo riempie.
    plan_id: str = Field(default="", max_length=40)

    # --- che cosa è stato chiesto ----------------------------------------
    user_request: str = Field(default="", max_length=600)
    goal: str = Field(default="", max_length=300)
    # Chi, come l'ha detto la persona: «Lorenzo», «il meccanico». Non risolto.
    counterparty: str = Field(default="", max_length=160)
    #     CHE TIPO DI TELEFONATA, DECISO UNA VOLTA.
    # Si stabilisce all'inizio, dalla richiesta, e da lì non cambia: chi
    # risponde alle domande non deve ridirlo a ogni passo, e un'interfaccia che
    # lo passasse sbagliato non deve poter trasformare un messaggio in uno
    # spostamento.
    operation: str = Field(default="", max_length=32)
    #     IL MESSAGGIO, CON LE PAROLE DI CHI LO MANDA.
    # È la versione che fa fede. Chi telefonerà potrà dirlo con calore e in
    # terza persona; questa riga resta com'è stata detta.
    message_to_deliver: str = Field(default="", max_length=400)

    # --- chi chiamare -----------------------------------------------------
    contact_candidates: List[ContactCandidate] = Field(default_factory=list)
    selected_contact: Optional[ContactCandidate] = None
    number_source: str = Field(default="", max_length=32)
    #     IL CANCELLO CHE APRE UNA PERSONA.
    # Non lo apre una confidenza alta, non lo apre una fonte affidabile, non lo
    # apre l'assenza di alternative. Lo apre qualcuno che guarda un numero e
    # dice di sì.
    number_confirmed: bool = False
    number_rejected: bool = False
    #     PERCHÉ QUEL NUMERO SI PUÒ USARE, IN UNA PAROLA.
    #
    # `trusted`: una persona l'aveva già confermato per questa identità, e la
    # coppia è ancora attiva — si riusa senza chiedere di nuovo.
    # `confirmed_now`: confermato in questa preparazione, adesso.
    # Vuoto: non si può usare. Il cancello guarda questo campo, e lo rilegge
    # dal registro al momento di preparare la chiamata.
    number_trust: str = Field(default="", max_length=16)
    # L'identità a cui appartiene il numero scelto. È la metà della coppia su
    # cui sta la fiducia, e senza questa un numero confermato per Lorenzo
    # varrebbe anche per lo studio che per caso ha lo stesso centralino.
    contact_identity: str = Field(default="", max_length=120)
    #     DUE NUMERI PER LA STESSA PERSONA, E UNO ERA GIÀ CONFERMATO.
    # Non si sceglie da soli e non si sovrascrive: si mostrano tutti e due.
    number_conflict: bool = False

    # --- che cosa ORA sa già ----------------------------------------------
    # Fatti già in mano, in italiano: «la partita è venerdì alle 20:30». Ogni
    # riga qui dentro è una domanda che non verrà fatta.
    known_context: List[str] = Field(default_factory=list, max_length=12)
    # I riferimenti canonici di quello che si è riconosciuto. Servono al
    # backend per legare la missione; non escono mai verso il modello.
    context_refs: Dict[str, str] = Field(default_factory=dict)
    missing_information: List[MissingInformation] = Field(
        default_factory=list, max_length=8,
    )

    # --- dove si vuole arrivare -------------------------------------------
    desired_state: Dict[str, str] = Field(default_factory=dict)
    # L'autorità in date e orari, costruita man mano che la persona risponde.
    # Sta qui come dizionario e diventa `CallMissionAuthority` al momento di
    # legare: questo file non è il posto in cui si giudica.
    structured_authority: Dict[str, Any] = Field(default_factory=dict)

    # --- il risultato ------------------------------------------------------
    readiness: Readiness = "NEEDS_INFO"
    # Perché non è pronta, in italiano, per chi legge.
    readiness_says: str = Field(default="", max_length=300)
    mission_brief: Dict[str, Any] = Field(default_factory=dict)
    conversation_ready: bool = False
    #     IL RIASSUNTO E' STATO LETTO — IN QUALE TURNO.
    # Il via libera vale solo per un riassunto che la persona ha già visto,
    # in un turno precedente. Misurato sul vero: lo stesso «sì» che confermava
    # il numero è stato preso anche come via libera, e il messaggio non è mai
    # stato riletto.
    summary_shown_in: str = Field(default="", max_length=120)

    # Quello che è nato da qui, quando è nato.
    call_id: str = Field(default="", max_length=64)
    idempotency_key: str = Field(default="", max_length=220)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    # ------------------------------------------------------------------
    def can_become_a_call(self) -> bool:
        """
        Il cancello, e sono due cose che devono valere insieme.

            NUMERO CONFERMATO **E** CONVERSAZIONE POSSIBILE.

        Una `and` invece di due controlli in due posti: un cancello scritto
        una volta sola non si può dimenticare a metà.
        """
        return (
            bool(self.number_confirmed)
            and not self.number_rejected
            and self.number_trust in ("trusted", "confirmed_now")
            and bool(self.contact_identity)
            and self.selected_contact is not None
            and bool(self.conversation_ready)
        )

    def what_is_still_missing(self) -> List[MissingInformation]:
        return [m for m in self.missing_information if not m.answered]

    def the_next_question(self) -> Optional[MissingInformation]:
        """
        La prossima cosa da chiedere, una sola.

            TRE DOMANDE IN FILA SONO UN MODULO.

        Se ne fa una, si ascolta la risposta, e si ricalcola: molto spesso la
        risposta alla prima rende inutile la seconda.
        """
        restano = self.what_is_still_missing()
        return restano[0] if restano else None

    def answer(self, field: str, testo: str) -> bool:
        """Registra una risposta. Torna se qualcosa è cambiato davvero."""
        for m in self.missing_information:
            if m.field == field and not m.answered:
                m.answered = True
                m.answer = (testo or "").strip()[:300]
                return True
        return False


# ---------------------------------------------------------------------------
# Persistenza
# ---------------------------------------------------------------------------


class AlreadyPrepared(Exception):
    """Questa richiesta era già in preparazione. Non è un guasto."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


async def remember(db, prep: MissionPreparation) -> MissionPreparation:
    """
    Scrive la preparazione, e non due volte.

        A DIRE CHE C'ERA GIÀ È IL DATABASE, NON UN `if`.

    Stessa disciplina del piano e dell'applicazione: la chiave è l'`_id`, e un
    secondo tentativo viene rifiutato dall'inserimento invece che da un
    controllo che qualcuno potrebbe dimenticare di scrivere.
    """
    chiave = prep.idempotency_key or request_key_for(prep.owner_id, prep.user_request)
    prep.idempotency_key = chiave
    try:
        await db[PREPARATIONS].insert_one({**prep.model_dump(), "_id": chiave})
    except Exception as e:
        if _is_duplicate(e):
            raise AlreadyPrepared(chiave) from e
        raise
    return prep


async def save(db, prep: MissionPreparation) -> MissionPreparation:
    """Aggiorna. L'identità non si tocca mai."""
    prep.updated_at = now_iso()
    fuori = prep.model_dump()
    for immutabile in ("preparation_id", "idempotency_key", "created_at"):
        fuori.pop(immutabile, None)
    await db[PREPARATIONS].update_one(
        {"_id": prep.idempotency_key}, {"$set": fuori},
    )
    return prep


async def by_key(db, key: str) -> Optional[MissionPreparation]:
    return _read(await db[PREPARATIONS].find_one({"_id": key}, {"_id": 0}))


async def by_id(db, owner_id: str, preparation_id: str) -> Optional[MissionPreparation]:
    return _read(await db[PREPARATIONS].find_one(
        {"preparation_id": preparation_id, "owner_id": owner_id}, {"_id": 0}))


async def for_plan(db, plan_id: str) -> Optional[MissionPreparation]:
    return _read(await db[PREPARATIONS].find_one({"plan_id": plan_id}, {"_id": 0}))


async def waiting_for_you(db, owner_id: str, limit: int = 20) -> List[MissionPreparation]:
    """Le preparazioni che aspettano una risposta o una conferma."""
    righe = await db[PREPARATIONS].find(
        {"owner_id": owner_id, "conversation_ready": False,
         "number_rejected": {"$ne": True}}, {"_id": 0},
    ).to_list(max(1, min(limit, 100)))
    preps = [p for p in (_read(r) for r in righe) if p is not None]
    return sorted(preps, key=lambda p: p.created_at, reverse=True)


def _read(row: Optional[Dict[str, Any]]) -> Optional[MissionPreparation]:
    if not row:
        return None
    try:
        return MissionPreparation.model_validate(row)
    except Exception as e:  # pragma: no cover
        logger.info("preparazione illeggibile: %s", type(e).__name__)
        return None


def _is_duplicate(e: Exception) -> bool:
    nome = type(e).__name__
    if nome in ("DuplicateKeyError", "GiaPreso"):
        return True
    testo = str(e).lower()
    return "duplicate key" in testo or "e11000" in testo
