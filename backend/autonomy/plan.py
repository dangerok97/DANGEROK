"""
Il proposito, e a che punto è arrivato.

    UN PIANO NON È UNA COSA DA FARE: È UNA COSA GIÀ COMINCIATA.

Prima di questo file un proposito di ORA viveva in pezzi sparsi — una
telefonata qui, un legame lì, un record di applicazione da un'altra parte, una
continuation in un quarto posto — e nessuno di quei pezzi sapeva di essere
parte di qualcosa. Bastava una riga in più per chiedersi «e com'è finita?» e
non c'era un posto a cui chiederlo.

    TRE COSE, E SONO SEPARATE APPOSTA.

`authority_state` dice se qualcuno ha detto di sì. `state` dice a che punto è
il giro. `verified` dice se il mondo è davvero cambiato. Tenerle in un campo
solo era la versione corta, ed è la versione in cui «autorizzato» finisce per
significare «fatto» — che è il modo in cui un sistema comincia a mentire senza
che nessuno abbia scritto una bugia.

    E L'IDENTITÀ NON CAMBIA MAI.

La chiave del piano è la chiave del suo `_id`: a dire che questo proposito
c'era già non è un `if`, è il database. Ci è costato una volta scoprire che
mutare l'identità a cose fatte produce un secondo record; qui l'identità è
quella del *momento in cui il proposito è nato*, e quello che nasce dopo si
annota accanto.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("ora.autonomy.plan")

PLANS = "autonomous_action_plans"

# Da dove nasce un proposito.
#
#     CHI L'HA VOLUTO CAMBIA QUELLO CHE SI PUÒ FARE DA SOLI.
#
# Una richiesta di una persona porta già dentro di sé il motivo per cui la si
# sta facendo. Un segnale no: è ORA che ha pensato una cosa, e in V1 può
# arrivare fino a proporla e non oltre.
Source = Literal["user_request", "life_signal", "situation"]

# Dove può stare un piano. Nove stati, e non uno di più: ognuno risponde a una
# domanda diversa che qualcuno, prima o poi, farà a voce.
PlanState = Literal[
    "proposed",           # ORA lo propone, nessuno ha ancora detto niente
    "waiting_authority",  # serve un sì, e non è arrivato
    "authorised",         # il sì c'è; non è ancora successo niente
    "executing",          # l'azione esterna è in corso
    "waiting_user",       # si è fermata: serve una decisione
    "applying",           # l'esito c'è e si sta scrivendo nel mondo
    "completed",          # verificato sullo stato canonico
    "failed",
    "cancelled",
]

# Gli stati da cui un piano non si muove più.
FINISHED: tuple = ("completed", "failed", "cancelled")

# Se c'è già stato un sì, e di che tipo.
AuthorityState = Literal["absent", "proposed", "granted", "refused"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_plan_id() -> str:
    return f"plan_{uuid.uuid4().hex[:16]}"


def plan_key_for(
    owner_id: str, source: str, source_ref: str,
    domain: str, operation: str, target_ref: str,
) -> str:
    """
    La chiave che rende questo proposito irripetibile.

        LO STESSO INNESCO NON PRODUCE DUE PIANI.

    Chi l'ha voluto, da che cosa è nato, su che cosa, per farci che. Cinque
    cose che non cambiano fra un tentativo e l'altro — ed è proprio questo che
    le rende utili a riconoscere il secondo.

    `source_ref` è l'identità stabile dell'innesco, e non è un dettaglio: per
    una richiesta è il nome logico della missione, che sopravvive a una
    ripresa; per un segnale è la sua `dedupe_key`, che il livello dei segnali
    costruisce apposta perché un replay non conti due volte. Mettere qui un
    orario o un identificativo fresco vorrebbe dire spegnere l'idempotenza
    lasciando in piedi il campo che dice di averla.
    """
    pezzi = [owner_id, source, source_ref or "-", domain or "-",
             operation or "-", target_ref or "-"]
    return "|".join(p.strip() or "-" for p in pezzi)[:220]


class PlanEvent(BaseModel):
    """
    Una riga della storia del piano, scritta perché una persona la legga.

        NON UN LOG: UN RESOCONTO.

    Il codice serve a chi programma, la frase a chi ha chiesto la cosa. Stanno
    insieme perché separarli avrebbe voluto dire, prima o poi, mostrare il
    codice a una persona quando la frase non c'era.
    """

    at: str = Field(default_factory=now_iso)
    state: str = Field(default="", max_length=32)
    code: str = Field(default="", max_length=48)
    says: str = Field(default="", max_length=300)


class AutonomousActionPlan(BaseModel):
    """Un proposito di ORA, dall'idea al mondo cambiato."""

    plan_id: str = Field(default_factory=new_plan_id, max_length=40)
    owner_id: str = Field(min_length=1, max_length=64)

    # --- da dove nasce ----------------------------------------------------
    source: Source = "user_request"
    # L'identità stabile dell'innesco. Entra nella chiave.
    source_ref: str = Field(default="", max_length=180)
    # Che cosa si vuole ottenere, in italiano. È la frase che una persona
    # rilegge, e non è quella su cui si decide: quella è `authority`.
    goal: str = Field(default="", max_length=300)
    # Perché adesso. Vuoto per una richiesta — l'ha chiesto qualcuno — e pieno
    # per un segnale, dove il motivo è l'unica cosa che giustifica il disturbo.
    reason: str = Field(default="", max_length=400)

    # --- su che cosa ------------------------------------------------------
    domain: str = Field(default="", max_length=32)
    operation: str = Field(default="", max_length=32)
    #     L'IDENTIFICATIVO CANONICO, E NON VIAGGIA CON LA VOCE.
    # Sta qui come sta nel legame: chi telefona non lo sa e non deve saperlo.
    target_ref: str = Field(default="", max_length=64)

    # --- l'autorità -------------------------------------------------------
    authority_state: AuthorityState = "absent"
    # Il riferimento al sì, quando c'è. Non un booleano: si deve poter
    # risalire a *quale* autorizzazione ha aperto questo giro.
    authority_ref: str = Field(default="", max_length=64)

    # --- dove è arrivato --------------------------------------------------
    state: PlanState = "proposed"
    #     SERVE UNA DECISIONE È UNA COSA CHE SI GUARDA IN ELENCO.
    # Duplica in parte `state`, e la duplicazione è voluta: un elenco che deve
    # dire «questi aspettano te» non può filtrare su nove stati sperando di
    # ricordarseli tutti.
    needs_user_decision: bool = False

    # --- i pezzi del giro, quando esistono --------------------------------
    mission_id: str = Field(default="", max_length=64)
    call_id: str = Field(default="", max_length=64)
    continuation_id: str = Field(default="", max_length=64)
    application_id: str = Field(default="", max_length=220)

    #     E LA DOMANDA CHE COSTA DI PIÙ.
    # Non «il record dice applied», ma «lo stato canonico è dove doveva
    # essere». Un piano non diventa `completed` senza questo, mai.
    verified: bool = False
    error: str = Field(default="", max_length=300)

    idempotency_key: str = Field(default="", max_length=220)
    history: List[PlanEvent] = Field(default_factory=list, max_length=40)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    # ------------------------------------------------------------------
    def is_open(self) -> bool:
        return self.state not in FINISHED

    def needs_an_external_mission(self) -> bool:
        """
        Se per arrivare in fondo bisogna parlare con qualcuno fuori.

            IL MONDO NON SI CAMBIA SEMPRE DA SOLI.

        Oggi tutte e tre le operazioni che questo ciclo sa portare a termine
        passano da una telefonata: è la sola azione esterna che ORA ha. Il
        giorno in cui ne avesse una seconda — una mail, un modulo — questa
        funzione è il posto in cui si dirà, e non ci sarà un `if` sparso
        altrove che se ne accorge.
        """
        return True

    def note(self, state: str, code: str, says: str) -> None:
        """Aggiunge una riga alla storia, senza farla crescere all'infinito."""
        self.history.append(PlanEvent(state=state, code=code, says=says[:300]))
        if len(self.history) > 40:
            #     LA PRIMA RIGA NON SI PERDE MAI.
            # È quella che dice perché questo piano esiste, e senza di quella
            # una storia lunga diventa una storia senza inizio.
            self.history = [self.history[0]] + self.history[-39:]


# ---------------------------------------------------------------------------
# Persistenza
# ---------------------------------------------------------------------------


class AlreadyPlanned(Exception):
    """Questo proposito c'era già. Non è un guasto: è l'idempotenza."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


async def remember(db, plan: AutonomousActionPlan) -> AutonomousActionPlan:
    """
    Scrive il piano per la prima volta, e non due volte.

        A DIRE CHE C'ERA GIÀ È IL DATABASE, NON UN `if`.

    La chiave è l'`_id`: un secondo tentativo non arriva nemmeno a guardare se
    esiste, perché l'inserimento gli viene rifiutato. Cercare-poi-scrivere
    avrebbe lasciato aperta la finestra fra le due cose, che è esattamente
    quella in cui due richieste ravvicinate producono due piani.
    """
    chiave = plan.idempotency_key or plan_key_for(
        plan.owner_id, plan.source, plan.source_ref,
        plan.domain, plan.operation, plan.target_ref,
    )
    plan.idempotency_key = chiave
    try:
        await db[PLANS].insert_one({**plan.model_dump(), "_id": chiave})
    except Exception as e:
        if _is_duplicate(e):
            raise AlreadyPlanned(chiave) from e
        raise
    return plan


async def save(db, plan: AutonomousActionPlan) -> AutonomousActionPlan:
    """Aggiorna un piano che esiste già. L'identità non si tocca."""
    plan.updated_at = now_iso()
    await db[PLANS].update_one(
        {"_id": plan.idempotency_key},
        {"$set": _without_identity(plan.model_dump())},
    )
    return plan


async def by_key(db, key: str) -> Optional[AutonomousActionPlan]:
    return _read(await db[PLANS].find_one({"_id": key}, {"_id": 0}))


async def by_id(db, owner_id: str, plan_id: str) -> Optional[AutonomousActionPlan]:
    return _read(await db[PLANS].find_one(
        {"plan_id": plan_id, "owner_id": owner_id}, {"_id": 0}))


async def for_call(db, call_id: str) -> Optional[AutonomousActionPlan]:
    """
    Il piano di questa telefonata, se ne ha uno.

        SI CERCA PER TELEFONATA, E LA TELEFONATA PUÒ ESSERE LA SECONDA.

    Una commissione che si è fermata e ha ripreso ha due `call_id` e un piano
    solo: il piano segue l'ultima telefonata, perché è quella che porterà
    l'esito. La missione invece resta quella di sempre, ed è lei a tenere
    insieme le due.
    """
    return _read(await db[PLANS].find_one({"call_id": call_id}, {"_id": 0}))


async def for_mission(db, mission_id: str) -> Optional[AutonomousActionPlan]:
    return _read(await db[PLANS].find_one({"mission_id": mission_id}, {"_id": 0}))


async def open_plans(db, owner_id: str, limit: int = 50) -> List[AutonomousActionPlan]:
    """I piani ancora in giro, il più recente per primo."""
    righe = await db[PLANS].find(
        {"owner_id": owner_id, "state": {"$nin": list(FINISHED)}}, {"_id": 0},
    ).to_list(max(1, min(limit, 200)))
    piani = [p for p in (_read(r) for r in righe) if p is not None]
    return sorted(piani, key=lambda p: p.created_at, reverse=True)


async def recent(db, owner_id: str, limit: int = 20) -> List[AutonomousActionPlan]:
    righe = await db[PLANS].find({"owner_id": owner_id}, {"_id": 0}).to_list(200)
    piani = [p for p in (_read(r) for r in righe) if p is not None]
    return sorted(piani, key=lambda p: p.created_at, reverse=True)[:max(1, limit)]


async def stuck_in_the_middle(db, limit: int = 50) -> List[AutonomousActionPlan]:
    """
    I piani rimasti a metà strada.

        UN PIANO IN `applying` CHE NON SI MUOVE È UNA DOMANDA APERTA.

    Il processo che lo stava portando avanti è morto: non sappiamo se il mondo
    è cambiato. Nessuno qui indovina — si torna a guardare, ed è il ciclo a
    dirlo. Gli stati che aspettano qualcun altro (`waiting_user`,
    `waiting_authority`, `proposed`) non sono rimasti a metà: stanno aspettando
    una persona, ed è diverso.
    """
    righe = await db[PLANS].find(
        {"state": {"$in": ["authorised", "executing", "applying"]}}, {"_id": 0},
    ).to_list(max(1, min(limit, 200)))
    return [p for p in (_read(r) for r in righe) if p is not None]


def _read(row: Optional[Dict[str, Any]]) -> Optional[AutonomousActionPlan]:
    if not row:
        return None
    try:
        return AutonomousActionPlan.model_validate(row)
    except Exception as e:  # pragma: no cover
        logger.info("piano illeggibile: %s", type(e).__name__)
        return None


def _without_identity(campi: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tutto tranne quello che non deve cambiare mai.

    `plan_id` e `idempotency_key` sono l'identità. Riscriverli a ogni
    salvataggio non farebbe niente di visibile — finché un giorno qualcosa li
    ricalcola, e quel giorno la stessa cosa diventa due.
    """
    fuori = dict(campi)
    fuori.pop("plan_id", None)
    fuori.pop("idempotency_key", None)
    fuori.pop("created_at", None)
    return fuori


def _is_duplicate(e: Exception) -> bool:
    nome = type(e).__name__
    if nome in ("DuplicateKeyError", "GiaPreso"):
        return True
    testo = str(e).lower()
    return "duplicate key" in testo or "e11000" in testo
