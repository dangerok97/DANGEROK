"""
Il filo che passa dentro tutti i motori, e non ne apre nessuno.

    QUESTO FILE NON SA NIENTE.

Non sa che cosa sia un appuntamento, non sa quando valga la pena spostarlo,
non sa se le diciotto rientrino in un mandato, non sa scrivere in un
calendario. Ogni volta che gli serve una di queste cose la chiede a chi la sa
fare da prima di lui. È il solo motivo per cui aggiungerlo non ha creato una
seconda testa.

    E IL PASSO È UNO SOLO.

`advance()` guarda il mondo e decide dove sta il piano. Non è una catena di
callback: è una funzione che, chiamata due volte di fila, dà due volte la
stessa risposta. Serve perché i processi muoiono — fra la telefonata e la
scrittura, fra la scrittura e il resoconto — e un giro che si potesse riprendere
solo dall'inizio non si potrebbe riprendere affatto.

    NESSUNA AZIONE ESTERNA SENZA UN SÌ.

C'è un punto solo in cui un piano passa da «ci ho pensato» a «sta succedendo»,
ed è una persona che dice di sì. Un piano senza autorità non arriva mai a
`executing`, e non perché ci sia un controllo che lo impedisce: perché non c'è
nessun percorso che ce lo porti.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from autonomy.plan import (
    AlreadyPlanned,
    AutonomousActionPlan,
    PLANS,
    by_key,
    for_call,
    for_mission,
    plan_key_for,
    remember,
    save,
    stuck_in_the_middle,
)

logger = logging.getLogger("ora.autonomy")


# ===========================================================================
# A · Nasce da una richiesta
# ===========================================================================


async def plan_a_user_request(
    db, *, call, binding, goal: str = "", reason: str = "",
) -> Tuple[Optional[AutonomousActionPlan], str]:
    """
    Apre un piano su una telefonata già preparata e già legata.

        IL LEGAME VIENE PRIMA DEL PIANO, NON DOPO.

    Non è un ordine estetico. Un piano senza un oggetto preciso sarebbe un
    proposito su «il dentista», e il momento in cui si può ancora chiedere
    «quale dei due?» è adesso, non dopo lo squillo. Se il legame non c'è, qui
    non nasce niente: la telefonata resta una telefonata che riporterà una
    risposta, che è un esito legittimo.

    Torna il piano e il motivo in italiano per cui non se n'è fatto uno. Non
    solleva su un secondo tentativo: torna quello di prima, che è la risposta
    giusta e non un guasto.
    """
    if binding is None:
        return None, "questa telefonata non è legata a niente da cambiare"

    from telephone.domains import adapter_for

    dominio = binding.target.domain
    operazione = binding.target.operation
    if adapter_for(dominio, operazione) is None:
        return None, f"non so ancora {operazione} su «{dominio}»"

    plan = AutonomousActionPlan(
        owner_id=call.owner_id,
        source="user_request",
        #     L'INNESCO È LA MISSIONE, NON LA TELEFONATA.
        # Una ripresa fa una seconda telefonata e resta la stessa missione:
        # se la chiave seguisse il `call_id`, una commissione fermata e
        # ripresa produrrebbe due piani per un proposito solo.
        source_ref=binding.mission_id,
        goal=goal.strip()[:300] or (call.mandate.why_calling or "")[:300],
        reason=reason.strip()[:400],
        domain=dominio,
        operation=operazione,
        target_ref=binding.target.entity_id,
        #     UNA RICHIESTA NON È ANCORA UN PERMESSO.
        # Chi l'ha chiesta ha detto che cosa vuole; il sì su *questa*
        # telefonata, verso *questo* numero, è un secondo gesto.
        authority_state="proposed" if binding.authority is not None else "absent",
        state="waiting_authority",
        mission_id=binding.mission_id,
        call_id=call.id,
    )
    plan.note("waiting_authority", "plan_opened", _opening_line(plan, call))
    try:
        return await remember(db, plan), ""
    except AlreadyPlanned as gia:
        #     LO STESSO INNESCO NON PRODUCE DUE PIANI.
        esistente = await by_key(db, gia.key)
        if esistente is not None:
            return esistente, ""
        return None, "questo proposito risultava già aperto"  # pragma: no cover


def _opening_line(plan: AutonomousActionPlan, call) -> str:
    chi = (call.calling_whom or "").strip()
    return (f"Ti propongo di chiamare {chi} per {plan.goal}." if chi
            else f"Ti propongo di {plan.goal}.")


# ===========================================================================
# B · Nasce da un segnale
# ===========================================================================


async def plan_from_a_signal(
    db, *, owner_id: str, dedupe_key: str, goal: str, reason: str,
    domain: str = "", operation: str = "", target_ref: str = "",
) -> Tuple[Optional[AutonomousActionPlan], str]:
    """
    Apre un piano che ORA ha pensato da sola, e lo lascia fermo.

        IN V1 UN PENSIERO DI ORA ARRIVA FINO ALLA PROPOSTA. NON OLTRE.

    Il piano nasce `proposed` e senza autorità, e non c'è nessun percorso che
    lo porti a toccare il mondo finché una persona non dice di sì. Non è un
    limite temporaneo travestito da controllo: è che un sistema che agisce
    fuori per un pensiero proprio deve prima meritarsi di essere creduto sui
    pensieri, e questa è la versione in cui se li fa leggere.

    `dedupe_key` è l'identità dell'innesco: il livello dei segnali la
    costruisce apposta perché un replay non produca due volte la stessa cosa,
    e qui la si riusa invece di inventarne una seconda.
    """
    from life_signals.models import is_valid_dedupe_key

    if not is_valid_dedupe_key(dedupe_key):
        #     UNA CHIAVE CHE NON È UNA CHIAVE SPEGNE L'IDEMPOTENZA IN SILENZIO.
        return None, "questo segnale non ha un'identità stabile"

    plan = AutonomousActionPlan(
        owner_id=owner_id,
        source="life_signal",
        source_ref=dedupe_key,
        goal=goal.strip()[:300],
        reason=reason.strip()[:400],
        domain=(domain or "").strip(),
        operation=(operation or "").strip(),
        target_ref=(target_ref or "").strip(),
        authority_state="absent",
        state="proposed",
    )
    plan.note("proposed", "signal_proposal",
              f"Ti propongo di {plan.goal}." if plan.goal else "Ho una proposta.")
    try:
        return await remember(db, plan), ""
    except AlreadyPlanned as gia:
        esistente = await by_key(db, gia.key)
        if esistente is not None:
            return esistente, ""
        return None, "questa proposta risultava già aperta"  # pragma: no cover


# ===========================================================================
# L'autorità
# ===========================================================================


async def grant(db, plan: AutonomousActionPlan, *, authority_ref: str = "") -> AutonomousActionPlan:
    """
    Una persona ha detto di sì. Da qui in poi il giro può succedere.

    Non decide niente per conto suo: registra un gesto che è avvenuto altrove
    — il sì esplicito su questa telefonata — e apre la strada. Quello che si
    può accettare resta scritto nella `CallMissionAuthority` del legame, ed è
    lì che `evaluate_authority` andrà a guardare.
    """
    if not plan.is_open():
        return plan
    plan.authority_state = "granted"
    plan.authority_ref = (authority_ref or "explicit_yes")[:64]
    plan.state = "authorised"
    plan.needs_user_decision = False
    plan.note("authorised", "authority_granted", "Hai detto di sì. Procedo.")
    return await save(db, plan)


async def refuse(db, plan: AutonomousActionPlan) -> AutonomousActionPlan:
    """Una persona ha detto di no. Non è un fallimento: è una risposta."""
    if not plan.is_open():
        return plan
    plan.authority_state = "refused"
    plan.state = "cancelled"
    plan.needs_user_decision = False
    plan.note("cancelled", "authority_refused", "Hai detto di no. Non faccio niente.")
    return await save(db, plan)


async def cancel(db, plan: AutonomousActionPlan, *, why: str = "") -> AutonomousActionPlan:
    """Fermato, da chiunque sia stato."""
    if not plan.is_open():
        return plan
    plan.state = "cancelled"
    plan.needs_user_decision = False
    plan.error = (why or "")[:300]
    plan.note("cancelled", "cancelled", why or "Ho lasciato perdere.")
    return await save(db, plan)


# ===========================================================================
# Il passo
# ===========================================================================


async def advance(db, plan: AutonomousActionPlan) -> AutonomousActionPlan:
    """
    Guarda il mondo e dice dove sta questo piano.

        NON RICORDA: RILEGGE.

    È la differenza che rende il giro riprendibile. Un passo che si fidasse di
    quello che il piano diceva di essere non potrebbe distinguere «la
    scrittura non è mai partita» da «la scrittura è andata e il processo è
    morto dopo» — che sono le due cose che capitano davvero, e che si
    riconoscono solo tornando a guardare.

    Chiamata due volte di fila dà due volte la stessa risposta, e non scrive
    niente nel mondo: le scritture le fa l'application layer, quando è il suo
    momento.
    """
    if not plan.is_open():
        return plan

    try:
        return await _one_step(db, plan)
    except Exception as e:  # pragma: no cover
        logger.info("passo non riuscito: %s", type(e).__name__)
        return plan


async def _one_step(db, plan: AutonomousActionPlan) -> AutonomousActionPlan:
    #     SENZA UN SÌ NON SI VA DA NESSUNA PARTE, E NON È UN CONTROLLO.
    # È che da `proposed` e da `waiting_authority` non parte nessuna strada:
    # l'unica cosa che le apre è `grant`, che è un gesto di una persona.
    if plan.authority_state != "granted":
        return plan

    call = await _the_call(db, plan.call_id)
    if call is None:
        return await _stop(db, plan, "call_gone",
                           "La telefonata di questo proposito non esiste più.")

    #     PRIMA LA DOMANDA APERTA, POI TUTTO IL RESTO.
    # Una commissione fermata produce anche un record di applicazione
    # `skipped` — non ha scritto niente, ed è giusto così — e leggerlo per
    # primo la farebbe sembrare finita male invece che in attesa.
    aspetta = await _open_question_for(db, plan)
    if aspetta is not None:
        return await _wait_for_the_user(db, plan, aspetta)

    if call.state != "ended":
        return await _still_going(db, plan, call)

    return await _read_the_outcome(db, plan, call)


async def _still_going(db, plan, call) -> AutonomousActionPlan:
    """La telefonata non è finita: il piano sta dove sta il filo."""
    dove = "executing" if call.state in ("dialling", "talking") else "authorised"
    if plan.state == dove:
        return plan
    plan.state = dove
    plan.note(dove, f"call_{call.state}",
              "Sto chiamando." if dove == "executing" else "Pronta a chiamare.")
    return await save(db, plan)


async def _open_question_for(db, plan):
    """La continuation ancora aperta di questa missione, se c'è."""
    from telephone.continuation import CONTINUATIONS, CallMissionContinuation, STILL_OPEN

    row = await db[CONTINUATIONS].find_one(
        {"mission_id": plan.mission_id, "state": {"$in": list(STILL_OPEN)}},
        {"_id": 0},
    )
    if not row:
        return None
    try:
        return CallMissionContinuation.model_validate(row)
    except Exception:  # pragma: no cover
        return None


async def _wait_for_the_user(db, plan, continuazione) -> AutonomousActionPlan:
    """
    Si è fermata, e aspetta una persona.

        CEDERE IL CONTROLLO NON È FALLIRE.

    Lo stesso piano, non un secondo: la domanda che si sta facendo nasce da
    questo proposito e ci tornerà dentro. Un piano nuovo avrebbe voluto dire
    due propositi per una cosa sola, e due posti in cui dire «fatto».
    """
    if plan.state == "waiting_user" and plan.continuation_id == continuazione.id:
        return plan
    plan.state = "waiting_user"
    plan.needs_user_decision = True
    plan.continuation_id = continuazione.id
    plan.note("waiting_user", "needs_user", continuazione.in_a_line())
    return await save(db, plan)


async def _read_the_outcome(db, plan, call) -> AutonomousActionPlan:
    """
    La telefonata è finita. Adesso conta che cosa è successo nel mondo.

        UNA TELEFONATA RIUSCITA NON È UN APPUNTAMENTO SPOSTATO.

    È l'errore che questo ciclo esiste per non fare. Qui non si guarda com'è
    andata la linea: si guarda il record dell'applicazione, e poi — perché
    nemmeno quello basta — lo stato canonico.
    """
    from telephone.application import application_for

    record = await application_for(db, call.id)
    if record is None:
        #     LA LINEA È CHIUSA E NON C'È NIENTE DA APPLICARE.
        return await _stop(db, plan, "nothing_to_apply", _why_nothing(call))

    plan.application_id = record.idempotency_key or plan.application_id
    fatto = str(record.application_status or "")

    if fatto == "pending":
        if plan.state != "applying":
            plan.state = "applying"
            plan.note("applying", "applying", "Sto aggiornando le tue cose.")
            return await save(db, plan)
        return plan

    if fatto in ("conflict", "failed"):
        return await _stop(db, plan, fatto,
                           record.error or "Non sono riuscita a completarlo.")

    #     E QUI LA PAROLA CHE COSTA.
    # `applied` è un record. `skipped` vuol dire che non si è scritto niente —
    # e a volte è la risposta giusta, perché il mondo c'era già. In tutti e
    # due i casi a decidere non è il record: è lo stato canonico.
    arrivato, come = await _did_the_world_change(db, plan, record)
    if arrivato:
        plan.verified = True
        plan.state = "completed"
        plan.needs_user_decision = False
        plan.note("completed", "verified", come)
        return await save(db, plan)

    return await _stop(db, plan, "not_verified", come)


async def _did_the_world_change(db, plan, record) -> Tuple[bool, str]:
    """
    Lo stato canonico è dove l'obiettivo voleva portarlo?

        A RISPONDERE È IL DOMINIO, E GUARDANDO.

    L'orchestratore non sa che cosa voglia dire «arrivato» per un
    appuntamento, per un impegno o per una sessione di studio — ed è giusto
    che non lo sappia. Chiede, e la risposta viene dallo stato canonico, non
    dal verdetto di chi ha scritto.
    """
    from telephone.application import _the_outcome_of
    from telephone.binding import binding_for
    from telephone.domains import adapter_for

    adattatore = adapter_for(plan.domain, plan.operation)
    if adattatore is None:  # pragma: no cover
        return False, "Non so più come si verifica questa cosa."

    legame = await binding_for(db, plan.call_id)
    if legame is None:
        return False, "Ho perso il collegamento con quello che dovevo cambiare."

    #     DOVE DOVEVA ARRIVARE LO DICE `translate`, NON IL RECORD.
    # È la funzione il cui mestiere è esattamente questo — dall'esito
    # confermato ai campi veri — ed è pura: nessuna rete, nessuna scrittura.
    # Ricalcolarla qui costa niente e vuol dire non aver bisogno di fidarsi di
    # un campo salvato da un processo che potrebbe essere morto a metà.
    call = await _the_call(db, plan.call_id)
    outcome = _the_outcome_of(call) if call is not None else None
    campi: Dict[str, str] = {}
    if outcome is not None:
        campi, _ = adattatore.translate(legame, outcome)

    row = await adattatore.look(db, binding=legame)
    if adattatore.landed(row, plan.operation, campi):
        return True, adattatore.says(plan.operation, campi)

    #     SCRITTO MA NON ARRIVATO È IL CASO PEGGIORE, ED È QUELLO DA DIRE.
    # Un record che dice `applied` su un mondo che non è cambiato è
    # esattamente la bugia rassicurante: se la si tace, una persona smette di
    # pensarci a una cosa che nessuno ha fatto.
    fatto = str(record.application_status or "")
    if fatto == "skipped":
        return False, record.error or "Non c'era niente da cambiare, e non è cambiato."
    return False, "Risulta fatto, ma non lo vedo cambiato. Meglio che controlli."


def _why_nothing(call) -> str:
    """Perché non c'è niente da applicare, detto a una persona."""
    return {
        "no_answer": "Non ha risposto nessuno.",
        "busy": "Era occupato.",
        "failed": "La telefonata non è partita.",
    }.get(str(call.how_it_ended or ""), "La telefonata non ha prodotto niente da fare.")


async def _stop(db, plan, code: str, says: str) -> AutonomousActionPlan:
    plan.state = "failed"
    plan.needs_user_decision = False
    plan.error = (says or "")[:300]
    plan.note("failed", code, says)
    return await save(db, plan)


async def _the_call(db, call_id: str):
    if not call_id:
        return None
    from telephone.models import PhoneCall

    row = await db["phone_calls"].find_one({"id": call_id}, {"_id": 0})
    if not row:
        return None
    try:
        return PhoneCall.model_validate(row)
    except Exception:  # pragma: no cover
        return None


# ===========================================================================
# I momenti in cui qualcosa succede altrove
# ===========================================================================


async def on_call_finished(db, call) -> Optional[AutonomousActionPlan]:
    """
    La telefonata è finita e l'esito è già stato applicato: adesso il piano.

        IL GANCIO È SOTTILE APPOSTA.

    Chi chiude la telefonata non deve sapere che esiste un ciclo: passa di qui
    e basta. Se il piano non c'è — la maggior parte delle telefonate — non
    succede niente, e non è un caso da gestire.
    """
    plan = await for_call(db, call.id)
    if plan is None:
        return None
    return await advance(db, plan)


async def on_user_decision(db, continuation) -> Optional[AutonomousActionPlan]:
    """
    La persona ha risposto alla domanda. Lo stesso piano riparte.

        NESSUN PIANO NUOVO. MAI.

    La ripresa fa una seconda telefonata, e il piano la segue — ma resta
    quello di prima, con la sua chiave, la sua storia e il suo nome di
    missione. È così che «fatto» si può dire una volta sola.
    """
    plan = await for_mission(db, continuation.mission_id)
    if plan is None:
        return None

    if str(continuation.decision or "") == "cancel":
        return await cancel(db, plan, why="Hai preferito lasciar perdere.")

    #     LA SECONDA TELEFONATA È LA TELEFONATA DI ADESSO.
    # Il piano la segue perché è quella che porterà l'esito; la missione
    # invece non si muove, ed è lei a tenere insieme le due.
    nuova = str(continuation.resumed_call_id or "")
    if nuova and nuova != plan.call_id:
        plan.call_id = nuova
        plan.state = "authorised"
        plan.needs_user_decision = False
        plan.continuation_id = continuation.id
        plan.note("authorised", "resumed", "Hai deciso. Richiamo.")
        plan = await save(db, plan)
        return await advance(db, plan)

    plan.needs_user_decision = False
    plan.note(plan.state, "decided", "Hai deciso.")
    plan = await save(db, plan)
    return await advance(db, plan)


async def recover_plans(db, limit: int = 50) -> List[AutonomousActionPlan]:
    """
    I piani rimasti a metà, riportati a guardare il mondo.

    Non riprova niente da solo: `advance` rilegge, e se c'è ancora da
    applicare qualcosa è il recupero dell'application layer a farlo — quello
    che ha la rivendicazione atomica. Due recuperi che scrivono sarebbero due
    motori.
    """
    fatti: List[AutonomousActionPlan] = []
    for plan in await stuck_in_the_middle(db, limit=limit):
        prima = plan.state
        dopo = await advance(db, plan)
        if dopo.state != prima:
            fatti.append(dopo)
    return fatti
