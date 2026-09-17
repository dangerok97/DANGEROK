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
    if prep.counterparty:
        trovato = await find_who_to_call(
            db, owner_id=prep.owner_id, who=prep.counterparty,
        )
        prep.contact_candidates = trovato.candidates
        #     UNO SOLO NON VUOL DIRE CONFERMATO.
        # Si preseleziona per poterlo mostrare, e si resta in attesa del sì.
        uno = trovato.only_one()
        if uno is not None and prep.selected_contact is None:
            prep.selected_contact = uno
            prep.number_source = uno.source

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


async def choose_contact(
    db, prep: MissionPreparation, *, number: str = "", index: int = -1,
    operation: str = "",
) -> Tuple[MissionPreparation, str]:
    """
    La persona ha detto quale dei candidati è quello giusto.

    Sceglie per numero o per posizione; non conferma. Scegliere e confermare
    sono due gesti, e tenerli separati vuol dire che vedere il numero giusto
    in cima a un elenco non lo rende approvato.
    """
    scelto: Optional[ContactCandidate] = None
    pulito = _clean_number(number)
    if pulito:
        scelto = next(
            (c for c in prep.contact_candidates if c.number == pulito), None,
        )
    elif 0 <= index < len(prep.contact_candidates):
        scelto = prep.contact_candidates[index]

    if scelto is None:
        return prep, "non ho capito quale contatto intendi"

    prep.selected_contact = scelto
    prep.number_source = scelto.source
    prep.number_confirmed = False
    prep.number_rejected = False
    prep = await evaluate(db, prep, operation=operation)
    prep = _rebuild_the_brief(prep, operation)
    await save(db, prep)
    return prep, ""


async def confirm_number(
    db, prep: MissionPreparation, *, yes: bool, instead: str = "",
    operation: str = "",
) -> Tuple[MissionPreparation, str]:
    """
    Il sì — o il no — su un numero.

        UN NO NON È UN GUASTO: È LA RAGIONE PER CUI SI CHIEDE.

    Se la persona dice di no e non dà un'alternativa, la preparazione resta
    ferma e lo dice. Nessun ripiego sul secondo candidato: il secondo era
    meno probabile del primo, e il primo era sbagliato.
    """
    alternativo = _clean_number(instead)
    if alternativo:
        #     UN NUMERO DETTO DA UNA PERSONA È GIÀ CONFERMATO.
        # Non c'è nessuno di più affidabile a cui chiederlo.
        prep.selected_contact = ContactCandidate(
            #     IL NOME TROVATO NON SI PERDE PER UN NUMERO NUOVO.
            # Chi corregge il numero non sta dicendo che la persona è
            # un'altra: sta dicendo che quella cifra era sbagliata. Buttare
            # via «Lorenzo Bianchi» per tornare a «Lorenzo» farebbe sembrare
            # che ORA abbia dimenticato con chi stava parlando.
            name=(prep.selected_contact.name if prep.selected_contact
                  else prep.counterparty) or "questo numero",
            number=alternativo,
            kind=(prep.selected_contact.kind if prep.selected_contact else "unknown"),
            source="user",
            source_detail="me l'hai dato tu",
            confidence=QUANTO_CI_SI_FIDA["user"],
            why="Me l'hai dato tu.",
        )
        prep.number_source = "user"
        prep.number_confirmed = True
        prep.number_rejected = False
    elif yes:
        if prep.selected_contact is None:
            return prep, "non c'è nessun numero da confermare"
        prep.number_confirmed = True
        prep.number_rejected = False
    else:
        prep.number_confirmed = False
        prep.number_rejected = True

    prep = await evaluate(db, prep, operation=operation)
    prep = _rebuild_the_brief(prep, operation)
    await save(db, prep)
    return prep, ""


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
        if not prep.number_confirmed:
            manca.append("il numero non l'hai ancora confermato")
        if not prep.conversation_ready:
            manca.append(prep.readiness_says or "mi manca ancora qualcosa")
        return None, "; ".join(manca)

    contatto = prep.selected_contact
    if contatto is None:  # pragma: no cover
        return None, "non c'è un numero"

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
        "candidates": [_contact_card(c) for c in prep.contact_candidates]
        if len(prep.contact_candidates) > 1 else [],
        "number_confirmed": bool(prep.number_confirmed),
        "number_rejected": bool(prep.number_rejected),
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
    """Un candidato come si mostra: nome, numero, e da dove viene."""
    return {
        "name": c.name,
        "number": c.number,
        "source_label": COME_SI_DICE.get(c.source, "Trovato"),
        "source_detail": c.source_detail,
        "why": c.why,
    }


def _what_you_can_answer(prep: MissionPreparation) -> List[str]:
    """
    Che cosa una persona può rispondere adesso, e niente di più.

    Mostrare un pulsante che non serve è chiedere una decisione a chi non ne
    deve prendere nessuna.
    """
    if prep.number_rejected:
        return ["give_number"]
    if len(prep.contact_candidates) > 1 and not prep.number_confirmed:
        return ["choose", "give_number"]
    if prep.selected_contact is not None and not prep.number_confirmed:
        return ["confirm_number", "reject_number", "give_number"]
    if not prep.contact_candidates and prep.selected_contact is None:
        return ["give_number"]
    if prep.the_next_question() is not None:
        return ["answer"]
    if prep.can_become_a_call():
        return ["call"]
    return []
