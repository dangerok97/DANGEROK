"""
Il giro che porta da una frase a una telefonata che si può fare.

    NESSUNO DI QUESTI PASSI DECIDE DA SOLO DI TELEFONARE.

Si apre una preparazione, si cerca chi chiamare, si chiede conferma del
numero, si chiede quello che manca, e quando non manca più niente si costruisce
il riassunto. La telefonata nasce dopo, da un cancello che vuole due sì: uno su
un numero e uno su quanto si sa.

    E IL PROPOSITO È LO STESSO DALL'INIZIO ALLA FINE.

Il piano nasce con la preparazione, non con la chiamata. Quando la chiamata
arriva, il piano impara il suo nome — non ne nasce un secondo. È la ragione per
cui l'identità del piano, qui, è la richiesta: una frase detta da una persona,
che sopravvive a tutto quello che le succede dopo.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from preparation import brief as il_riassunto
from preparation.contacts import (
    COME_SI_DICE,
    ContactCandidate,
    QUANTO_CI_SI_FIDA,
    _clean_number,
    find_who_to_call,
)
from preparation.context import the_times_inside, what_ora_already_knows
from preparation.preparation import (
    AlreadyPrepared,
    MissionPreparation,
    by_key,
    for_plan,
    remember,
    request_key_for,
    save,
)
from preparation.readiness import evaluate

logger = logging.getLogger("ora.preparation.service")


async def start(
    db, *, owner_id: str, user_request: str, counterparty: str = "",
    operation: str = "", goal: str = "",
) -> Tuple[Optional[MissionPreparation], str]:
    """
    Apre la preparazione di una richiesta, o ritrova quella che c'era già.

        LA STESSA FRASE NON APRE DUE PRATICHE.

    Chi ripete la richiesta — perché la rete è caduta, perché ha premuto due
    volte — ritrova la preparazione di prima, con dentro le risposte che aveva
    già dato. Ricominciare da capo sarebbe la versione facile, ed è quella in
    cui si richiede a qualcuno una cosa che aveva appena detto.
    """
    frase = " ".join((user_request or "").split())[:600]
    if not frase:
        return None, "non mi hai detto cosa fare"

    chiave = request_key_for(owner_id, frase)
    esistente = await by_key(db, chiave)
    if esistente is not None:
        return esistente, ""

    prep = MissionPreparation(
        owner_id=owner_id,
        user_request=frase,
        goal=goal.strip()[:300],
        counterparty=" ".join((counterparty or "").split())[:160],
        idempotency_key=chiave,
    )
    try:
        prep = await remember(db, prep)
    except AlreadyPrepared:
        #     DUE RICHIESTE NELLO STESSO ISTANTE: VINCE LA PRIMA.
        gia = await by_key(db, chiave)
        return (gia, "") if gia is not None else (None, "richiesta già in corso")

    return await look_around(db, prep, operation=operation)


async def look_around(
    db, prep: MissionPreparation, *, operation: str = "",
) -> Tuple[Optional[MissionPreparation], str]:
    """
    Cerca chi chiamare e che cosa ORA sa già, poi valuta.

        PRIMA SI GUARDA, POI SI CHIEDE.

    L'ordine è tutto il punto di questo sprint: una domanda fatta prima di
    aver guardato è quasi sempre una domanda su una cosa che era già scritta
    da qualche parte.
    """
    prep = await _who_to_call(db, prep)

    frasi, refs, _ = await what_ora_already_knows(
        db, owner_id=prep.owner_id, user_request=prep.user_request,
        counterparty=prep.counterparty,
    )
    prep.known_context = frasi
    prep.context_refs = refs

    prep = await evaluate(db, prep, operation=operation)
    prep = _rebuild_the_brief(prep, operation)
    await save(db, prep)
    return prep, ""


# ---------------------------------------------------------------------------
# Le risposte di una persona
# ---------------------------------------------------------------------------


async def _who_to_call(db, prep: MissionPreparation) -> MissionPreparation:
    """
    Chi chiamare, tenendo conto di quello che la persona ha già confermato.

        UN NUMERO GIÀ CONFERMATO NON SI RICHIEDE A OGNI TELEFONATA.

    Chiedere «è ancora questo?» ogni volta sembra prudenza ed è rumore: chi
    ha già detto di sì una volta smette di leggere la domanda, e allora la
    domanda non protegge più niente. Si chiede quando c'è qualcosa di nuovo da
    guardare — un numero mai visto, o un numero diverso da quello di prima.
    """
    #     «CHIAMA +39…» È GIÀ UNA RISPOSTA.
    # Un numero scritto nella richiesta vale per quella richiesta: è la
    # persona che dice «questo». Non diventa affidabile per sempre — per quello
    # serve dire di chi è.
    dentro, di_chi = _number_in_the_request(prep.user_request)
    if dentro:
        return await _the_person_said_it(db, prep, dentro, di_chi)

    if not prep.counterparty:
        return prep

    trovato = await find_who_to_call(db, owner_id=prep.owner_id, who=prep.counterparty)
    prep.contact_candidates = trovato.candidates
    prep.number_conflict = False

    fidati = [c for c in trovato.candidates if c.trusted]
    altri = [c for c in trovato.candidates if not c.trusted]

    if len(fidati) == 1:
        vecchio = fidati[0]
        stessa = [c for c in altri if c.contact_identity == vecchio.contact_identity]
        if stessa:
            #     DUE NUMERI PER LA STESSA PERSONA: SI CHIEDE QUALE.
            prep.number_conflict = True
            prep.contact_candidates = [vecchio, *stessa]
            prep.selected_contact = None
            prep.number_confirmed = False
            prep.number_trust = ""
            return prep
        if not altri:
            #     GIÀ CONFERMATO, ANCORA ATTIVO: SI USA.
            _use_trusted(prep, vecchio)
            return prep
        #     UN «LORENZO» CONFERMATO E UN ALTRO «LORENZO» IN RUBRICA.
        # Non è un conflitto sul numero: è una domanda su chi. Si mostrano
        # tutti, e scegliere quello confermato non chiede una seconda conferma.
        prep.selected_contact = None
        return prep

    uno = trovato.only_one() or _the_official_one(trovato.candidates)
    if uno is not None and prep.selected_contact is None:
        prep.selected_contact = uno
        prep.number_source = uno.source
        prep.contact_identity = uno.contact_identity
    return prep


def _the_official_one(candidati: List[ContactCandidate]) -> Optional[ContactCandidate]:
    """
    Il sito ufficiale, quando ce n'è uno solo e vale più di tutto il resto.

        PREFERIRE NON È DECIDERE.

    Lo si mette in cima e lo si propone — e resta da confermare, con gli altri
    numeri trovati visibili sotto. Per le persone non vale: due «Lorenzo» in
    rubrica sono una domanda su chi, e nessuno dei due è «ufficiale».
    """
    ufficiali = [c for c in candidati if c.source == "official_site"]
    if len(ufficiali) != 1:
        return None
    primo = ufficiali[0]
    if all(primo.confidence > c.confidence for c in candidati if c is not primo):
        return primo
    return None


def _use_trusted(prep: MissionPreparation, c: ContactCandidate) -> None:
    prep.selected_contact = c
    prep.number_source = "confirmed"
    prep.contact_identity = c.contact_identity
    prep.number_confirmed = True
    prep.number_rejected = False
    prep.number_trust = "trusted"


async def _the_person_said_it(
    db, prep: MissionPreparation, numero: str, di_chi: str,
) -> MissionPreparation:
    """
    Il numero era nella frase.

        «CHIAMA +39…» E «IL NUMERO DI LORENZO È +39…» NON SONO LA STESSA FRASE.

    La prima è un'istruzione: vale per questa telefonata e basta. La seconda
    è un'affermazione su una persona: da lì in poi quel numero è di Lorenzo, e
    lo si può riusare. La differenza sta tutta in chi viene nominato accanto al
    numero — ed è l'unica che si può verificare senza interpretare.
    """
    from preparation import trust

    chi = di_chi or prep.counterparty or "questo numero"
    identita = _identity_of(chi)
    prep.selected_contact = ContactCandidate(
        name=chi, number=numero, kind="unknown", source="user",
        source_detail="scritto nella tua richiesta",
        confidence=QUANTO_CI_SI_FIDA["user"], why="Me l'hai scritto tu.",
        contact_identity=identita,
    )
    prep.contact_candidates = [prep.selected_contact]
    prep.number_source = "user"
    prep.contact_identity = identita
    prep.number_confirmed = True
    prep.number_rejected = False
    prep.number_trust = "confirmed_now"
    if not prep.counterparty:
        prep.counterparty = chi
    if di_chi:
        await trust.confirm(
            db, owner_id=prep.owner_id, identity=identita, display_name=chi,
            number=numero, source="user", source_detail="me l'hai detto tu",
        )
    else:
        await trust.remember_seen(
            db, owner_id=prep.owner_id, identity=identita, display_name=chi,
            number=numero, source="user", source_detail="scritto per una telefonata",
        )
    return prep


async def choose_contact(
    db, prep: MissionPreparation, *, number: str = "", index: int = -1,
    operation: str = "",
) -> Tuple[MissionPreparation, str]:
    """
    La persona ha detto quale dei candidati è quello giusto.

    Scegliere un numero nuovo non lo conferma: vederlo in cima a un elenco non
    lo rende approvato. Scegliere un numero **già confermato** invece sì —
    chiedere due volte la stessa cosa alla stessa persona non protegge niente.
    """
    scelto: Optional[ContactCandidate] = None
    pulito = _clean_number(number)
    if pulito:
        scelto = next((c for c in prep.contact_candidates if c.number == pulito), None)
    elif 0 <= index < len(prep.contact_candidates):
        scelto = prep.contact_candidates[index]
    if scelto is None:
        return prep, "non ho capito quale contatto intendi"

    prep.number_conflict = False
    if scelto.trusted:
        _use_trusted(prep, scelto)
    else:
        prep.selected_contact = scelto
        prep.number_source = scelto.source
        prep.contact_identity = scelto.contact_identity or _identity_of(scelto.name)
        prep.number_confirmed = False
        prep.number_rejected = False
        prep.number_trust = ""
    return await _settle(db, prep, operation)


async def confirm_number(
    db, prep: MissionPreparation, *, yes: bool, instead: str = "",
    operation: str = "",
) -> Tuple[MissionPreparation, str]:
    """
    Il sì — o il no — su un numero.

        SOLO UN SÌ ESPLICITO RENDE UN NUMERO AFFIDABILE.

    Il sì scrive la coppia identità + numero nel registro, e da quel momento
    la prossima telefonata alla stessa persona non richiede niente. Il no la
    scrive come rifiutata, e da quel momento nessuna fonte la ripropone.

    `instead` è un numero diverso scritto da chi risponde: è un cambio, e
    passa da `change_number` — che vuol dire che va confermato anche lui.
    """
    from preparation import trust

    if _clean_number(instead):
        return await change_number(db, prep, number=instead, operation=operation)

    c = prep.selected_contact
    if yes:
        if c is None:
            return prep, "non c'è nessun numero da confermare"
        identita = prep.contact_identity or c.contact_identity or _identity_of(
            prep.counterparty or c.name)
        await trust.confirm(
            db, owner_id=prep.owner_id, identity=identita, display_name=c.name,
            number=c.number, kind=c.kind, source=c.source,
            source_detail=c.source_detail, source_url=c.source_url,
        )
        prep.contact_identity = identita
        prep.number_confirmed = True
        prep.number_rejected = False
        prep.number_trust = "confirmed_now"
    else:
        if c is not None:
            identita = prep.contact_identity or c.contact_identity or _identity_of(
                prep.counterparty or c.name)
            await trust.reject(
                db, owner_id=prep.owner_id, identity=identita,
                display_name=c.name, number=c.number, source=c.source,
                source_detail=c.source_detail,
            )
        prep.number_confirmed = False
        prep.number_rejected = True
        prep.number_trust = ""
    return await _settle(db, prep, operation)


async def change_number(
    db, prep: MissionPreparation, *, number: str, operation: str = "",
) -> Tuple[MissionPreparation, str]:
    """
    «Usa questo numero invece.» «Non è più il numero di Lorenzo.»

        IL VECCHIO NON SI SOVRASCRIVE, E IL NUOVO NON SI USA ANCORA.

    Il numero di prima passa a `stale`, con scritto perché — non si cancella,
    e non si ripropone. Quello nuovo diventa il candidato, con la persona di
    prima: chi cambia il numero di Lorenzo non sta dicendo che Lorenzo è un
    altro. E aspetta un sì, come ogni numero mai confermato.

    Idempotente: lo stesso cambio chiesto due volte lascia lo stesso stato.
    """
    from preparation import trust

    nuovo = _clean_number(number)
    if not nuovo:
        return prep, "quel numero non lo riesco a leggere"

    prima = prep.selected_contact
    identita = (prep.contact_identity or (prima.contact_identity if prima else "")
                or _identity_of(prep.counterparty))
    nome = (prima.name if prima else "") or prep.counterparty or "questo numero"

    if prima is not None and prima.number != nuovo:
        await trust.retire(
            db, owner_id=prep.owner_id, identity=identita, number=prima.number,
            why=f"hai chiesto di usare un altro numero ({nuovo})",
        )
    await trust.remember_seen(
        db, owner_id=prep.owner_id, identity=identita, display_name=nome,
        number=nuovo, source="user", source_detail="me l'hai scritto tu",
    )
    #     SE ERA GIÀ CONFERMATO PER LEI, NON SERVE CHIEDERLO DI NUOVO.
    gia_suo = await trust.still_trusted(db, prep.owner_id, identita, nuovo)
    #     E SI DICE CHE FINE HA FATTO QUELLO DI PRIMA.
    # Chi legge deve vedere che il vecchio numero non è sparito per sbaglio:
    # è stato messo da parte, per sua richiesta.
    detto = (f"al posto del {prima.number}, che non userò più"
             if prima is not None and prima.number != nuovo else "")
    prep.selected_contact = ContactCandidate(
        name=nome, number=nuovo, kind=(prima.kind if prima else "unknown"),
        source="confirmed" if gia_suo else "user",
        source_detail=detto,
        confidence=QUANTO_CI_SI_FIDA["user"], why="Me l'hai scritto tu.",
        contact_identity=identita, trusted=gia_suo,
    )
    prep.contact_candidates = [prep.selected_contact]
    prep.number_source = prep.selected_contact.source
    prep.contact_identity = identita
    prep.number_conflict = False
    prep.number_rejected = False
    prep.number_confirmed = gia_suo
    prep.number_trust = "trusted" if gia_suo else ""
    return await _settle(db, prep, operation)


async def set_contact_number(
    db, prep: MissionPreparation, *, number: str, operation: str = "",
) -> Tuple[MissionPreparation, str]:
    """
    «Il numero di Lorenzo è +39…» — detto esplicitamente, per quella persona.

    È l'unico caso in cui un numero scritto da chi risponde diventa affidabile
    senza una seconda domanda: la frase stessa è la conferma, perché nomina la
    persona e il numero insieme. Il numero di prima, se c'era, diventa vecchio.
    """
    from preparation import trust

    prep, perche = await change_number(db, prep, number=number, operation=operation)
    if perche:
        return prep, perche
    c = prep.selected_contact
    await trust.confirm(
        db, owner_id=prep.owner_id, identity=prep.contact_identity,
        display_name=c.name, number=c.number, kind=c.kind, source="user",
        source_detail="me l'hai detto tu",
    )
    prep.number_confirmed = True
    prep.number_trust = "confirmed_now"
    return await _settle(db, prep, operation)


async def _settle(
    db, prep: MissionPreparation, operation: str,
) -> Tuple[MissionPreparation, str]:
    prep = await evaluate(db, prep, operation=operation)
    prep = _rebuild_the_brief(prep, operation)
    await save(db, prep)
    return prep, ""


def _identity_of(nome: str) -> str:
    from preparation.trust import identity_of

    return identity_of(nome)


def _number_in_the_request(frase: str) -> Tuple[str, str]:
    """
    Un numero scritto dentro la richiesta, e di chi dice che è.

    «Il numero di Lorenzo è 333…» → il numero, e «Lorenzo».
    «Chiama il 333…» → il numero, e nessuno.
    """
    import re as _re

    from preparation.contacts import _number_inside

    numero = _number_inside(frase or "")
    if not numero:
        return "", ""
    di_chi = _re.search(
        r"numero di ([A-Za-zÀ-ÿ ]{2,60}?)\s+(?:è|e'|é)\s", frase or "", _re.IGNORECASE,
    )
    return numero, (di_chi.group(1).strip() if di_chi else "")


async def answer_question(
    db, prep: MissionPreparation, *, field: str = "", text: str = "",
    operation: str = "",
) -> Tuple[MissionPreparation, str]:
    """
    La persona ha risposto a quello che mancava.

        UNA RISPOSTA PUÒ PORTARE DENTRO PIÙ DI UNA COSA.

    «Sabato alle 19, al massimo alle 20» è un orario voluto e un limite, detti
    insieme perché è così che parlano le persone. Si leggono tutti e due: il
    primo diventa dove si vuole arrivare, gli altri diventano quello che si può
    accettare.
    """
    testo = " ".join((text or "").split())[:300]
    if not testo:
        return prep, "non ho capito la risposta"

    quale = field or (
        prep.the_next_question().field if prep.the_next_question() else ""
    )
    if quale:
        prep.answer(quale, testo)

    _read_the_times_in(prep, testo)
    prep = await evaluate(db, prep, operation=operation)
    prep = _rebuild_the_brief(prep, operation)
    await save(db, prep)
    return prep, ""


def _read_the_times_in(prep: MissionPreparation, testo: str) -> None:
    """
    Gli orari dentro una risposta diventano obiettivo e autorità.

        IL PRIMO È DOVE SI VUOLE ARRIVARE. GLI ALTRI SONO FIN DOVE SI PUÒ.

    Non è una regola sulla lingua italiana: è la forma di quasi tutte le
    risposte a «a quando?». Chi dice un orario solo ha detto quello che vuole;
    chi ne dice due ha detto anche dove si ferma.
    """
    orari = the_times_inside(testo)
    if not orari:
        return
    prep.desired_state = {
        "start_datetime": orari[0],
        "says": testo[:200],
    }
    autorita = dict(prep.structured_authority or {})
    autorita["desired"] = orari[0]
    if len(orari) > 1:
        alternative = list(autorita.get("alternatives") or [])
        for altro in orari[1:]:
            if altro not in alternative:
                alternative.append(altro)
        autorita["alternatives"] = alternative[:6]
        #     «AL MASSIMO LE 20» È UN CONFINE, E SI SCRIVE COME CONFINE.
        autorita["latest"] = orari[-1]
    autorita.setdefault("same_day_only", True)
    prep.structured_authority = autorita


def _rebuild_the_brief(prep: MissionPreparation, operation: str) -> MissionPreparation:
    """
    Il riassunto si scrive solo quando c'è qualcosa da riassumere.

    Costruirlo prima vorrebbe dire avere in giro il ritratto di una missione
    che non esiste, e prima o poi qualcuno lo mostrerebbe.
    """
    if prep.conversation_ready:
        prep.mission_brief = il_riassunto.build(prep, operation=operation)
    else:
        prep.mission_brief = {}
    return prep


# ---------------------------------------------------------------------------
# Il cancello
# ---------------------------------------------------------------------------


async def turn_into_a_call(
    db, prep: MissionPreparation, *, operation: str = "reschedule",
    minutes: int = 5,
) -> Tuple[Optional[Any], str]:
    """
    Da preparazione a telefonata preparata, se e solo se si può.

        DUE SÌ, E NON SI ENTRA CON UNO SOLO.

    `number_confirmed` e `conversation_ready`. Il controllo sta qui, in un
    posto, scritto una volta: un cancello sparso in tre funzioni è un cancello
    che una quarta funzione non attraversa.

    Torna la telefonata **preparata** — non composta. Comporre resta un gesto
    a parte, e passa dalla porta di sempre.
    """
    if not prep.can_become_a_call():
        manca = []
        if not prep.number_confirmed or not prep.number_trust:
            manca.append("il numero non l'hai ancora confermato")
        if not prep.conversation_ready:
            manca.append(prep.readiness_says or "mi manca ancora qualcosa")
        return None, "; ".join(manca) or "questa missione non è ancora pronta"

    contatto = prep.selected_contact
    if contatto is None:  # pragma: no cover
        return None, "non c'è un numero"

    #     LA FIDUCIA SI RILEGGE ADESSO, NON SI RICORDA DA PRIMA.
    # Fra la preparazione e questo momento qualcuno può aver detto che quel
    # numero non è più di Lorenzo. Un numero riusato perché «affidabile» vale
    # solo se lo è ancora — e lo dice il registro, non la preparazione.
    if prep.number_trust == "trusted":
        from preparation.trust import still_trusted

        if not await still_trusted(db, prep.owner_id, prep.contact_identity,
                                   contatto.number):
            prep.number_confirmed = False
            prep.number_trust = ""
            await _settle(db, prep, operation)
            return None, "quel numero non è più confermato: dimmi tu quale usare"

    from telephone.models import Mandate
    from telephone.service import TelephoneService

    riassunto = prep.mission_brief or il_riassunto.build(prep, operation=operation)
    call = await TelephoneService(db).prepare(
        prep.owner_id,
        to_number=contatto.number,
        calling_whom=contatto.name,
        mandate=Mandate(
            why_calling=str(riassunto.get("perche_chiamo") or prep.goal)[:400],
            may_agree_to=[str(x)[:160] for x in
                          (riassunto.get("posso_accettare") or [])][:8],
            must_bring_back=[
                "che cosa hanno risposto",
                str(riassunto.get("cosa_voglio_ottenere") or "")[:160]
                or "se si può fare",
            ],
            minutes=max(2, min(int(minutes or 5), 15)),
        ),
        session_ref=prep.preparation_id,
    )
    if not call.to_number:
        return None, "quel numero non è componibile da questo pilota"

    #     E SI LEGA ADESSO, CHE C'È ANCORA QUALCUNO A CUI CHIEDERE.
    # È la regola di V3.15 e non cambia: l'oggetto si decide prima dello
    # squillo. La differenza è che adesso non lo passa una persona a mano —
    # lo porta la preparazione, che l'ha riconosciuto dal contesto.
    legame = await _tie_it(db, prep, call, operation)
    prep.call_id = call.id
    await save(db, prep)

    from autonomy.orchestrator import on_call_prepared

    await on_call_prepared(db, prep, call, legame)
    return call, ""


async def _tie_it(db, prep: MissionPreparation, call, operation: str):
    """
    Lega la telefonata all'oggetto che la preparazione ha riconosciuto.

    Non indovina: usa il riferimento canonico che il recupero del contesto ha
    trovato. Se non ce n'è uno, non lega niente — e la telefonata riporterà
    una risposta invece di cambiare qualcosa, che è un esito legittimo purché
    sia quello che la persona si aspetta.
    """
    ref = prep.context_refs.get("calendar", "")
    if not ref:
        return None

    autorita = prep.structured_authority or {}
    try:
        from telephone.binding import bind_a_calendar_event

        legame, perche, _ = await bind_a_calendar_event(
            db, call=call, calendar_ref=ref,
            desired_datetime=str(autorita.get("desired") or ""),
            desired_minutes=int(prep.desired_state.get("minutes") or 0),
            allowed_alternatives=[str(a) for a in (autorita.get("alternatives") or [])],
            latest=str(autorita.get("latest") or ""),
            same_day_only=bool(autorita.get("same_day_only")),
        )
        if legame is None:
            logger.info("legame non fatto: %s", perche or "-")
        return legame
    except Exception as e:
        logger.info("legame non riuscito: %s", type(e).__name__)
        return None


# ---------------------------------------------------------------------------
# Come si legge
# ---------------------------------------------------------------------------


def as_a_card(prep: MissionPreparation) -> Dict[str, Any]:
    """
    La preparazione come la legge una persona.

        NIENTE DI TECNICO QUI DENTRO.

    Non c'è la chiave, non c'è `preparation_id` come cosa da capire, non ci
    sono i riferimenti canonici, non c'è l'autorità in forma grezza. C'è quello
    che si sta per fare, che cosa manca, e che cosa si può rispondere.
    """
    from preparation.preparation import COME_SI_LEGGE

    contatto = prep.selected_contact
    domanda = prep.the_next_question()
    return {
        "preparation_id": prep.preparation_id,
        "you_asked": prep.user_request,
        "goal": prep.goal or "",
        "counterparty": prep.counterparty,
        "status_label": COME_SI_LEGGE.get(prep.readiness, "In preparazione"),
        "says": prep.readiness_says or "",
        "contact": _contact_card(contatto) if contatto else None,
        #     DA SCEGLIERE, O IN ALTERNATIVA: NON È LA STESSA LISTA.
        # Senza un numero proposto, i candidati sono la domanda. Con uno
        # proposto, gli altri sono una via d'uscita — e si mostrano così.
        "candidates": [_contact_card(c) for c in prep.contact_candidates]
        if prep.selected_contact is None and len(prep.contact_candidates) > 1 else [],
        "other_candidates": [
            _contact_card(c) for c in prep.contact_candidates
            if contatto is not None and c.number != contatto.number
        ] if not prep.number_confirmed else [],
        "number_confirmed": bool(prep.number_confirmed),
        "number_rejected": bool(prep.number_rejected),
        #     PERCHÉ QUEL NUMERO SI PUÒ USARE, DETTO A UNA PERSONA.
        "number_note": _why_this_number(prep),
        "number_conflict": bool(prep.number_conflict),
        "what_ora_knows": list(prep.known_context),
        "question": {
            "field": domanda.field,
            "asks": domanda.question,
            "already_known": domanda.already_known,
        } if domanda else None,
        "ready": bool(prep.conversation_ready),
        "can_call": prep.can_become_a_call(),
        "summary": il_riassunto.reads_like(prep) if prep.conversation_ready else "",
        "you_can_answer": _what_you_can_answer(prep),
        "created_at": prep.created_at,
        "updated_at": prep.updated_at,
    }


def _contact_card(c: ContactCandidate) -> Dict[str, Any]:
    """
    Un candidato come si mostra: nome, numero, e da dove viene.

    Per un numero trovato sul web si mostra anche il dominio e quante altre
    fonti dicono lo stesso: sono le due cose che servono a una persona per
    decidere se crederci, e nessuna delle due la decide ORA.
    """
    also = (f" · lo riportano anche altre {c.corroborated_by} fonti"
            if c.corroborated_by > 1 else
            " · lo riporta anche un'altra fonte" if c.corroborated_by == 1 else "")
    return {
        "name": c.name,
        "number": c.number,
        "source_label": COME_SI_DICE.get(c.source, "Trovato"),
        "source_detail": (c.source_detail or "") + also,
        "why": c.why,
        "trusted": bool(c.trusted),
    }


def _why_this_number(prep: MissionPreparation) -> str:
    """
    Una riga sola: perché ORA userà proprio questo numero.

    È quello che sostituisce la domanda quando la domanda non serve: non si
    chiede più «è questo?», ma si dice chiaramente quale numero si userà e
    perché — così chi legge può ancora fermarlo.
    """
    c = prep.selected_contact
    if c is None or not prep.number_confirmed:
        return ""
    if prep.number_trust == "trusted":
        quando = f" il {c.source_detail[3:]}" if c.source_detail.startswith("il ") else ""
        return f"Userò questo numero: l'avevi già confermato tu{quando}."
    return "Userò questo numero: l'hai appena confermato."


def _what_you_can_answer(prep: MissionPreparation) -> List[str]:
    """
    Che cosa una persona può rispondere adesso, e niente di più.

    Mostrare un pulsante che non serve è chiedere una decisione a chi non ne
    deve prendere nessuna.
    """
    if prep.number_rejected:
        return ["give_number"]
    if prep.selected_contact is None and len(prep.contact_candidates) > 1:
        return ["choose", "give_number"]
    if prep.selected_contact is not None and not prep.number_confirmed:
        return ["confirm_number", "reject_number", "give_number"]
    if not prep.contact_candidates and prep.selected_contact is None:
        return ["give_number"]
    #     UN NUMERO CHE SI USA SI PUÒ SEMPRE CAMBIARE.
    # Anche quando è già confermato, anche a missione pronta. È la
    # contropartita di non chiederlo ogni volta.
    fuori = ["change_number", "reject_number"]
    if prep.the_next_question() is not None:
        fuori.insert(0, "answer")
    elif prep.can_become_a_call():
        fuori.insert(0, "call")
    return fuori
