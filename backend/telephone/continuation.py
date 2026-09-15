"""
Una commissione che si ferma, e riprende da dove si era fermata.

    «ALLE 18 NO, POSSO DOMANI ALLE 11» NON È UN FALLIMENTO.

È il caso più comune di tutti, ed era l'unico che ORA non sapeva gestire. Il
mandato diceva «sposta alle 18»; lo studio propone un'altra cosa. Accettarla
sarebbe prendere un impegno che nessuno ha autorizzato — il mandato è un
elenco chiuso, e lo è per questo. Dichiarare fallita la missione sarebbe
buttare via una proposta buona e il lavoro di una telefonata.

Quindi la missione non muore e non va avanti: **si mette in pausa**, con
addosso quello che ha imparato, e aspetta una persona.

    E QUANDO RIPRENDE, RIPRENDE. NON RICOMINCIA.

L'obiettivo è lo stesso, la controparte è la stessa, quello che è già stato
detto resta detto. Cambia una cosa sola: l'autorità, che adesso comprende
anche la proposta. Una seconda telefonata può servire — una proposta non è una
conferma, e il gate lo sa da tre sprint — ma è **la stessa missione** che la
fa, con lo stesso nome.

    FINCHÉ NESSUNO DECIDE, NEL MONDO NON SI TOCCA NIENTE.

Nessun calendario aggiornato, nessun successo dichiarato, nessuna applicazione.
Una proposta in attesa di risposta è esattamente questo: in attesa.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from telephone.authority import TimeSlot, a_slot_from
from telephone.models import now_iso

logger = logging.getLogger("ora.telephone.continuation")

CONTINUATIONS = "call_mission_continuations"

# Dove sta una commissione che si è fermata.
#
#     «FERMA» E «DAVANTI A QUALCUNO» NON SONO LO STESSO STATO.
#
# La prima nasce alla fine della telefonata, quando ancora nessuno sa niente;
# la seconda comincia quando la domanda è stata messa davanti alla persona. La
# distinzione serve a poter dire, dopo, se qualcuno non ha risposto o se non
# gliel'abbiamo mai chiesto — che sono due difetti diversi.
ContinuationState = Literal[
    "paused_for_user",        # la missione si è fermata, nessuno l'ha ancora vista
    "pending_user_decision",  # la domanda è davanti a chi deve rispondere
    "resumed",                # decisa, e la missione è ripartita
    "cancelled",              # lasciamo perdere
    "succeeded",              # ripresa e andata a buon fine
    "failed",                 # ripresa e non riuscita
]

# Che cosa può rispondere una persona. Tre, e non di più: accetta quello che
# hanno proposto, propone un'altra cosa, oppure lascia perdere.
Decision = Literal["accept", "alternative", "cancel"]

# Gli stati da cui si può ancora decidere qualcosa.
STILL_OPEN = ("paused_for_user", "pending_user_decision")


class CallMissionContinuation(BaseModel):
    """
    Il punto in cui una commissione si è fermata, e che cosa serve per andare
    avanti.

        NON È UN ERRORE DA REGISTRARE: È UNA DOMANDA DA FARE.

    Per questo dentro non c'è un codice di fallimento ma una frase, la proposta
    che è arrivata, e l'elenco di quello che si può rispondere.
    """

    id: str = Field(default_factory=lambda: f"cont_{uuid.uuid4().hex[:12]}")
    #     LA MISSIONE È QUELLA LOGICA, NON QUELLA DELLA TELEFONATA.
    # Una ripresa fa una seconda chiamata, e quella chiamata avrebbe un nome
    # di missione tutto suo. Qui si tiene il nome originale: è ciò che rende
    # impossibile applicare due volte lo stesso esito da due telefonate.
    mission_id: str = Field(min_length=1, max_length=64)
    call_id: str = Field(min_length=1, max_length=64)
    owner_id: str = Field(min_length=1, max_length=64)

    state: ContinuationState = "paused_for_user"

    # --- che cosa è successo ---------------------------------------------
    # Perché si è dovuto fermare, in italiano, come lo direbbe una persona.
    reason: str = Field(default="", max_length=300)
    # Quello che la controparte ha messo sul tavolo, se ha messo qualcosa.
    proposal: str = Field(default="", max_length=300)
    #     E LA STESSA COSA IN DATE VERE, QUANDO SI RIESCE.
    # «Giovedi' 8 alle 11» e' una frase; accettarla deve aggiungere un orario
    # all'autorita', non una riga di testo a un elenco che nessuno legge per
    # decidere. Vuoto quando chi ha telefonato non l'ha tradotta: allora resta
    # solo il testo, e si torna al comportamento di prima.
    proposed_slot: Optional["TimeSlot"] = None
    # I fatti nuovi emersi in linea, per nome e valore.
    facts: Dict[str, str] = Field(default_factory=dict)
    # Che cosa mancava all'autorità per poter dire di sì da solo.
    authority_missing: str = Field(default="", max_length=300)
    allowed_decisions: List[Decision] = Field(
        default_factory=lambda: ["accept", "alternative", "cancel"],
    )

    # --- che cosa ha risposto la persona ----------------------------------
    decision: str = Field(default="", max_length=20)
    decided_text: str = Field(default="", max_length=300)
    # La telefonata nata dalla ripresa, se ne è nata una.
    resumed_call_id: str = Field(default="", max_length=64)

    created_at: str = Field(default_factory=now_iso)
    shown_at: str = Field(default="", max_length=40)
    decided_at: str = Field(default="", max_length=40)
    resumed_at: str = Field(default="", max_length=40)

    def still_open(self) -> bool:
        return self.state in STILL_OPEN

    def in_a_line(self) -> str:
        """
        Che cosa è successo, per chi deve decidere.

            NON «needs_user». «LO STUDIO NON PUÒ ALLE 18.»

        Chi legge questa frase non ha seguito la telefonata: è la prima e
        spesso l'unica cosa che saprà, e deve bastargli per rispondere.
        """
        #     DUE FRASI SONO DUE FRASI, ANCHE SE ARRIVANO SEPARATE.
        # Il motivo e la proposta li scrive chi ha telefonato, in due campi
        # diversi e senza sapere che finiranno accanto. Attaccarli com'erano
        # dava «lo studio non può alle 18:00 del 30 settembre domani alle
        # 11:00»: due cose vere, lette come una sola sbagliata.
        pezzi = []
        for grezzo in (self.reason, self.proposal):
            testo = (grezzo or "").strip()
            if not testo:
                continue
            if testo[-1] not in ".!?":
                testo += "."
            pezzi.append(testo[0].upper() + testo[1:])
        return " ".join(pezzi) or "Serve una tua decisione per andare avanti."


# ---------------------------------------------------------------------------
# Fermarsi
# ---------------------------------------------------------------------------


async def pause_for_user(db, *, call, outcome, binding=None):
    """
    Mette in pausa questa commissione, con addosso quello che ha imparato.

        UNA SOLA PAUSA PER MISSIONE.

    Se la stessa telefonata viene riletta due volte — e succede: il recupero
    delle applicazioni rilegge gli esiti — non nascono due domande identiche
    davanti alla stessa persona.
    """
    mission_id = str(getattr(outcome, "mission_id", "") or "")
    if not mission_id:
        return None

    gia = await db[CONTINUATIONS].find_one({"mission_id": mission_id}, {"_id": 0})
    if gia:
        try:
            return CallMissionContinuation.model_validate(gia)
        except Exception:  # pragma: no cover
            return None

    continuazione = CallMissionContinuation(
        mission_id=mission_id,
        call_id=call.id,
        owner_id=call.owner_id,
        reason=(getattr(outcome, "user_confirmation_needed", "") or "").strip(),
        proposal=_what_they_put_on_the_table(outcome),
        proposed_slot=_the_same_thing_in_dates(outcome),
        facts={
            f.field: f.value for f in (getattr(outcome, "new_facts", None) or [])
        },
        authority_missing=_what_the_mandate_did_not_cover(call),
    )
    await db[CONTINUATIONS].insert_one(continuazione.model_dump())
    logger.info("missione in pausa: serve una decisione (%s)", continuazione.id)
    return continuazione


def _what_they_put_on_the_table(outcome) -> str:
    """
    La proposta della controparte, se ne ha fatta una.

    Si guarda prima quello che il gate ha classificato come `proposal`: è
    l'unica cosa che qualcuno ha dichiarato essere un'alternativa precisa,
    invece che una disponibilità generica o un dettaglio.
    """
    for detta in reversed(getattr(outcome, "counterparty_statements", None) or []):
        if detta.kind == "proposal" and detta.fact.strip():
            return detta.fact.strip()[:300]
    for detta in reversed(getattr(outcome, "counterparty_statements", None) or []):
        if detta.kind == "availability" and detta.fact.strip():
            return detta.fact.strip()[:300]
    return ""


def _the_same_thing_in_dates(outcome) -> Optional[TimeSlot]:
    """
    La proposta come orario, se chi ha telefonato l'ha tradotta.

        UNA FRASE NON SI PUO' CONFRONTARE. UN ORARIO SI'.

    Chi ha sentito parlare e' l'unico che puo' convertire «giovedi' 8 alle 11»
    in una data — e' gia' quello che fa per dire a che ora hanno spostato un
    appuntamento. Qui si prende quella conversione e basta: non si prova a
    ricavarla dal testo.
    """
    grezzo = getattr(outcome, "proposed_slot", None) or {}
    if not isinstance(grezzo, dict):
        grezzo = {}
    fessura = a_slot_from(
        grezzo.get("date", ""), grezzo.get("time", ""), grezzo.get("minutes", 0) or 0,
    )
    return fessura if fessura.is_real() else None


def _what_the_mandate_did_not_cover(call) -> str:
    """
    Che cosa il mandato non comprendeva, detto con le sue parole.

        IL MANDATO È UN ELENCO CHIUSO, ED È PER QUESTO CHE SI DEVE CHIEDERE.

    Non è una mancanza da correggere: è il motivo per cui ORA non ha accettato
    da sola. Riportarlo qui serve a chi legge per capire che non è stato un
    capriccio.
    """
    if call is None or call.mandate is None:
        return ""
    poteva = list(call.mandate.may_agree_to)
    if not poteva:
        return "non potevo accettare niente in linea senza chiedertelo"
    return "potevo accettare solo: " + "; ".join(poteva[:4])


# ---------------------------------------------------------------------------
# Leggere
# ---------------------------------------------------------------------------


async def continuation_for(db, call_id: str):
    """La pausa di questa telefonata, se si è fermata."""
    row = await db[CONTINUATIONS].find_one({"call_id": call_id}, {"_id": 0})
    if not row:
        # Una ripresa ha un `call_id` diverso: si cerca anche di là.
        row = await db[CONTINUATIONS].find_one(
            {"resumed_call_id": call_id}, {"_id": 0})
    if not row:
        return None
    try:
        return CallMissionContinuation.model_validate(row)
    except Exception as e:  # pragma: no cover
        logger.info("continuazione illeggibile: %s", type(e).__name__)
        return None


async def by_id(db, continuation_id: str, owner_id: str):
    row = await db[CONTINUATIONS].find_one(
        {"id": continuation_id, "owner_id": owner_id}, {"_id": 0},
    )
    if not row:
        return None
    try:
        return CallMissionContinuation.model_validate(row)
    except Exception:  # pragma: no cover
        return None


async def waiting_for(db, owner_id: str) -> List[CallMissionContinuation]:
    """Le commissioni ferme che aspettano questa persona."""
    fuori: List[CallMissionContinuation] = []
    righe = db[CONTINUATIONS].find(
        {"owner_id": owner_id, "state": {"$in": list(STILL_OPEN)}}, {"_id": 0},
    )
    async for row in righe:
        try:
            fuori.append(CallMissionContinuation.model_validate(row))
        except Exception:  # pragma: no cover
            continue
    return fuori


async def mark_shown(db, continuazione) -> CallMissionContinuation:
    """
    La domanda è stata messa davanti a qualcuno.

    Serve a distinguere «non ha risposto» da «non gliel'abbiamo mai chiesto»,
    che sono due difetti diversi e si correggono in due posti diversi.
    """
    if continuazione.state != "paused_for_user":
        return continuazione
    continuazione.state = "pending_user_decision"
    continuazione.shown_at = now_iso()
    await db[CONTINUATIONS].update_one(
        {"id": continuazione.id},
        {"$set": {"state": continuazione.state, "shown_at": continuazione.shown_at}},
    )
    return continuazione


# ---------------------------------------------------------------------------
# Decidere
# ---------------------------------------------------------------------------


class Decided:
    """Che cosa è successo alla decisione. Non un'eccezione: una risposta."""

    def __init__(self, continuation, *, ok: bool, why: str = "", call=None):
        self.continuation = continuation
        self.ok = ok
        self.why = why
        self.call = call


async def decide(db, *, continuation, decision: str, alternative: str = ""):
    """
    La persona ha risposto. La missione riprende, o si chiude.

        UNA DECISIONE PRESA DUE VOLTE RESTA UNA DECISIONE.

    Chi preme due volte lo stesso pulsante — o lo preme da due schermi — non
    deve far partire due telefonate. La prima risposta vince e le successive
    tornano lo stesso risultato, che è il modo in cui si dice «sì, l'ho già
    fatto» senza rifarlo.
    """
    if decision not in ("accept", "alternative", "cancel"):
        return Decided(continuation, ok=False, why="non so cosa voglia dire")

    if not continuation.still_open():
        #     GIÀ DECISA: SI RACCONTA, NON SI RIFÀ.
        return Decided(
            continuation, ok=True,
            why="questa decisione era già stata presa",
        )

    if decision == "alternative" and not alternative.strip():
        return Decided(
            continuation, ok=False,
            why="dimmi quale alternativa vuoi che proponga",
        )
    if decision == "accept" and not continuation.proposal.strip():
        return Decided(
            continuation, ok=False,
            why="non c'è una proposta da accettare",
        )

    continuation.decision = decision
    continuation.decided_at = now_iso()
    continuation.decided_text = (
        alternative.strip()[:300] if decision == "alternative"
        else continuation.proposal
    )

    if decision == "cancel":
        #     LASCIAR PERDERE È UNA CONCLUSIONE, NON UN FALLIMENTO.
        continuation.state = "cancelled"
        await _save(db, continuation)
        logger.info("missione lasciata cadere da chi l'aveva chiesta")
        return Decided(continuation, ok=True)

    return await _resume(db, continuation)


async def _resume(db, continuation) -> Decided:
    """
    Riprende la stessa missione, con l'autorità che adesso comprende la
    risposta.

        STESSO NOME, SECONDA TELEFONATA.

    Nasce una chiamata nuova — serve: una proposta non è una conferma, e il
    gate non ha mai accettato il contrario — ma porta il nome della missione
    originale. È così che l'applicazione resta una sola anche se le telefonate
    sono due, e che la storia non si sdoppia.
    """
    from telephone.binding import BINDINGS, binding_for
    from telephone.models import Mandate
    from telephone.service import TelephoneService

    servizio = TelephoneService(db)
    prima = await servizio.get(continuation.owner_id, continuation.call_id)
    if prima is None:
        return Decided(continuation, ok=False, why="la telefonata di prima non c'è più")

    accordato = continuation.decided_text.strip()
    #     ACCETTARE UN'ALTERNATIVA CAMBIA L'OBIETTIVO, NON SOLO I PERMESSI.
    #
    # Metterla in `may_agree_to` dice a chi telefona che cosa **puo'
    # accettare**; non gli dice che cosa **chiedere**. Sul vero e' successo
    # esattamente questo: la persona aveva accettato «domani alle 11», ORA ha
    # richiamato e ha chiesto di nuovo le 18:00 — perche' l'obiettivo era
    # rimasto quello di prima, e l'obiettivo e' cio' che legge.
    perche = _the_errand_now(prima.mandate.why_calling or "", accordato)
    mandato = Mandate(
        why_calling=perche[:300],
        #     L'AUTORITÀ NUOVA SI AGGIUNGE, NON SOSTITUISCE.
        # Quello che si poteva accettare prima si può ancora: la persona ha
        # aggiunto una possibilità, non ne ha tolte.
        may_agree_to=(list(prima.mandate.may_agree_to) + [accordato])[:8],
        must_bring_back=list(prima.mandate.must_bring_back)[:8],
        minutes=prima.mandate.minutes,
    )
    seconda = await servizio.prepare(
        continuation.owner_id,
        to_number=prima.to_number,
        calling_whom=prima.calling_whom,
        mandate=mandato,
        session_ref=prima.session_ref,
    )

    #     IL LEGAME SI EREDITA, CON IL NOME DI PRIMA.
    # L'oggetto da cambiare è lo stesso di allora: ritrovarlo adesso vorrebbe
    # dire cercarlo, e cercarlo è la cosa che questo progetto non fa.
    legame = await binding_for(db, continuation.call_id)
    if legame is not None:
        ereditato = legame.model_copy(deep=True)
        ereditato.call_id = seconda.id
        #     LA DECISIONE ENTRA NELLA POLICY, NON IN UN ELENCO DI FRASI.
        #
        # Concatenare il testo a `may_agree_to` diceva a chi telefona che cosa
        # puo' accettare, in una forma che nessuno puo' verificare. Aggiungere
        # l'orario alle alternative lo dice anche al giudice — che e' l'unico
        # che decidera' davvero se quella scrittura si puo' fare.
        #
        # Se la proposta non era stata tradotta in una data, qui non succede
        # niente e resta il comportamento di prima: il testo.
        ereditato.authority = _the_policy_now_allows(
            ereditato.authority, continuation)
        #     E DOVE SI VUOLE ARRIVARE ADESSO E' QUELLO CHE E' STATO DECISO.
        # `expected` non si tocca — l'appuntamento e' ancora dov'era — ma il
        # punto d'arrivo e' cambiato, e chi telefona lo legge da qui.
        ereditato.desired = {**(ereditato.desired or {}), "start_datetime": accordato}
        await db[BINDINGS].update_one(
            {"call_id": seconda.id},
            {"$set": ereditato.model_dump()},
            upsert=True,
        )

    continuation.state = "resumed"
    continuation.resumed_call_id = seconda.id
    continuation.resumed_at = now_iso()
    await _save(db, continuation)
    logger.info(
        "missione ripresa: %s -> %s", continuation.call_id, seconda.id,
    )
    return Decided(continuation, ok=True, call=seconda)


def _the_policy_now_allows(regole, continuation):
    """
    L'autorita' con dentro quello che e' stato deciso.

        UNA DECISIONE AGGIUNGE, NON RISCRIVE.

    Chi ha risposto «va bene cosi'» non ha tolto niente: ha detto che anche
    quello va bene. E chiamarla due volte non aggiunge due volte — e' quello
    che rende una decisione presa due volte una decisione sola, anche qui
    dentro e non solo nel record.
    """
    if regole is None or continuation.proposed_slot is None:
        return regole
    if continuation.decision != "accept":
        #     UN'ALTRA DATA NON E' QUELLA CHE HANNO PROPOSTO.
        # Chi propone un'alternativa sua sta chiedendo di trattare ancora, non
        # autorizzando un orario preciso: quello resta da concordare in linea,
        # e il giudice lo fermera' come fermerebbe qualunque altra cosa.
        return regole
    return regole.now_also_allows(continuation.proposed_slot)


def _the_errand_now(originale: str, accordato: str) -> str:
    """
    La commissione, riscritta con quello che è stato deciso.

        CHI TELEFONA LEGGE L'OBIETTIVO, NON L'ELENCO DEI PERMESSI.

    Non si prova a correggere la frase di prima: si dice che cosa vale adesso,
    dopo di essa. Riscrivere «dalle 16:00 alle 18:00» in «dalle 16:00 alle
    11:00 di domani» vorrebbe dire capire una frase scritta da una persona, e
    capirla male una volta su dieci basta a far chiedere l'orario sbagliato.
    """
    base = (originale or "").strip().rstrip(".")
    scelto = (accordato or "").strip().rstrip(".")
    if not scelto:
        return base
    if not base:
        return f"concordare {scelto}"
    return f"{base}. Aggiornamento: è stato concordato {scelto}, chiedi questo."


async def settle(db, *, mission_id: str, succeeded: bool) -> None:
    """
    La ripresa è finita. La commissione anche.

    Si scrive solo su una continuazione che era stata ripresa: un esito che
    arriva da una telefonata senza pause non ha niente da chiudere qui.
    """
    await db[CONTINUATIONS].update_one(
        {"mission_id": mission_id, "state": "resumed"},
        {"$set": {"state": "succeeded" if succeeded else "failed"}},
    )


async def _save(db, continuation) -> None:
    await db[CONTINUATIONS].update_one(
        {"id": continuation.id}, {"$set": continuation.model_dump()},
    )


def as_a_question(continuation) -> Dict[str, Any]:
    """
    La pausa come la legge chi deve rispondere.

        NIENTE STATI INTERNI, E UNA DOMANDA VERA.

    Chi apre questa scheda non ha seguito la telefonata. Quello che gli serve è
    cos'è successo, cosa si può fare, e nient'altro.
    """
    return {
        "id": continuation.id,
        "call_id": continuation.call_id,
        "state": continuation.state,
        "open": continuation.still_open(),
        "says": continuation.in_a_line(),
        "proposal": continuation.proposal,
        "why_i_could_not_decide": continuation.authority_missing,
        "can": list(continuation.allowed_decisions),
        "decision": continuation.decision,
        "resumed_call_id": continuation.resumed_call_id,
        "created_at": continuation.created_at,
    }
