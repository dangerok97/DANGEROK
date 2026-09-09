"""
Collegare e scollegare un conto, detto come lo direbbe una persona.

    NESSUNA CREDENZIALE BANCARIA PASSA DA ORA.

Il percorso e' quello ufficiale e non ce n'e' un altro: ORA mostra le banche,
la persona ne sceglie una, va sul sito della propria banca, autentica li' e
torna indietro con un consenso. Se ORA chiedesse utente e password sarebbe
phishing con una buona intenzione — che resta phishing, e che nessun sistema
serio ha motivo di costruire.

Quello che questo file custodisce e' la parte scomoda: gli stati intermedi.
Un collegamento bancario non e' acceso o spento — c'e' l'attesa mentre la
banca decide, c'e' il consenso che scade ogni tre mesi per obbligo di legge,
c'e' la banca che oggi non risponde. Sono cinque stati e vanno detti in
italiano:

    Non collegato
    Collegamento in corso
    Collegato
    Serve autorizzare di nuovo
    Temporaneamente non disponibile

Nessuno di questi e' «requisition EX» o «HTTP 429». Quei codici esistono, li
legge questo file, e non escono di qui.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.connectors.bank.link")

# Dove vivono gli «state» del collegamento: la sola cosa che lega un ritorno
# dal sito della banca alla persona che lo ha cominciato.
LINK_STATES = "bank_link_states"

# Quanto vale uno state. Il tempo di autenticarsi in banca e tornare, non di
# piu': una chiave che resta valida per ore e' una chiave in giro per ore.
LINK_STATE_MINUTES = 30

# Come si chiama, per una persona, ogni stato in cui un collegamento puo'
# trovarsi. La tabella e' una sola perche' due sarebbero due verita'.
NOT_CONNECTED = "non_collegato"
CONNECTING = "collegamento_in_corso"
CONNECTED = "collegato"
NEEDS_CONSENT = "serve_autorizzare_di_nuovo"
UNAVAILABLE = "temporaneamente_non_disponibile"

IN_WORDS = {
    NOT_CONNECTED: "Nessun conto collegato.",
    CONNECTING: "Sto collegando il conto. Ci vuole qualche istante.",
    CONNECTED: "Conto collegato.",
    NEEDS_CONSENT: "Serve che tu autorizzi di nuovo il conto: il permesso "
                   "scade ogni tre mesi.",
    UNAVAILABLE: "La banca non risponde in questo momento. Riprovo da sola.",
}

WHAT_TO_DO = {
    NOT_CONNECTED: "Collega un conto",
    CONNECTING: "",
    CONNECTED: "",
    NEEDS_CONSENT: "Ricollega",
    UNAVAILABLE: "",
}

# Gli stati della requisition, come li documenta l'aggregatore, tradotti una
# volta sola. CR creata, GC consenso, UA autenticazione, SA scelta dei conti,
# GA autorizzazione, LN collegata, RJ rifiutata, EX scaduta.
WHILE_LINKING = {
    "CR": CONNECTING, "GC": CONNECTING, "UA": CONNECTING,
    "SA": CONNECTING, "GA": CONNECTING,
    "LN": CONNECTED,
    "EX": NEEDS_CONSENT,
    "RJ": NOT_CONNECTED,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _human_state(instance: Optional[Dict[str, Any]]) -> str:
    """Da uno stato di connettore a uno stato che si puo' leggere."""
    if not instance:
        return NOT_CONNECTED
    if instance.get("reauthorization_required"):
        return NEEDS_CONSENT
    status = str(instance.get("status") or "")
    if status == "pending":
        return CONNECTING
    if status in ("connected", "syncing"):
        return CONNECTED
    if status == "degraded":
        return UNAVAILABLE
    return NOT_CONNECTED


async def institutions_for(svc, *, country: str = "IT") -> List[Dict[str, Any]]:
    """
    Le banche che questa persona puo' collegare, nel suo paese.

    Nessun giudizio e nessuna chiamata al modello: e' un elenco, e ordinarlo
    per nome e' tutta l'intelligenza che merita.
    """
    lister = getattr(svc.provider, "institutions", None)
    if lister is None:
        # Nessun aggregatore configurato: non c'e' niente da elencare, e va
        # detto.
        #
        #     OFFRIRE UNA BANCA FINTA IN UNA SCHERMATA VERA E' UNA BUGIA.
        #
        # La prima versione restituiva «Banca di prova» qui, e una persona
        # avrebbe potuto sceglierla dal percorso di collegamento vero. Il
        # provider di prova serve a far camminare il codice nei test: la sua
        # porta e' `/bank/connect`, e resta separata apposta.
        raise NotImplementedError("nessun aggregatore bancario configurato")
    return [
        {"id": bank.id, "nome": bank.name, "logo": bank.logo}
        for bank in await lister(country=country)
    ]


async def begin_link(
    svc, *, user_id: str, institution_id: str, redirect_to: str,
) -> Dict[str, Any]:
    """
    Prepara il collegamento e dì alla persona dove deve andare.

    Quello che resta scritto adesso e' un'istanza in attesa: c'e' un
    collegamento cominciato, non ancora uno riuscito. Scrivere «connected»
    qui vorrebbe dire mostrare un conto collegato a chi non ha ancora aperto
    la pagina della propria banca.
    """
    from connectors.bank.service import CONNECTOR_ID

    starter = getattr(svc.provider, "begin_link", None)
    if starter is None:
        raise NotImplementedError("questo provider non collega banche vere")

    reference = f"ora_{uuid.uuid4().hex[:16]}"
    started = await starter(
        institution_id=institution_id, redirect=redirect_to, reference=reference,
    )

    # Il riferimento del consenso e' il permesso di questa persona: sta nel
    # vault, cifrato, come il token di ogni altra sorgente. Nel documento
    # dell'istanza resta soltanto il puntatore.
    #
    # Con alcuni aggregatori qui non c'e' ancora niente da custodire: il
    # permesso nasce dopo, quando il codice del ritorno diventa una
    # sessione. Mettere adesso un riferimento vuoto sarebbe scrivere che c'e'
    # un consenso che non c'e'.
    secret_reference = ""
    if started.get("requisition_id"):
        secret_reference = await svc.vault.put(
            user_id=user_id,
            purpose="bank_consent",
            payload={"requisition_id": started["requisition_id"]},
            metadata={"connector_id": CONNECTOR_ID, "institution_id": institution_id},
        )

    # Un tentativo nuovo non deve rompere quello che gia' funziona.
    #
    #     RICOLLEGARE NON E' SCOLLEGARE.
    #
    # Trovato mentre si preparava lo screenshot del consenso: ricominciare il
    # percorso su una banca gia' collegata riscriveva l'istanza con
    # `pending` e un riferimento vuoto, e il permesso vivo spariva prima
    # ancora che il nuovo esistesse. Bastava aprire la schermata e cambiare
    # idea per restare senza conto.
    #
    # Quindi: finche' il nuovo consenso non arriva, il vecchio resta al suo
    # posto — e chi non ne aveva uno vede «collegamento in corso», che e'
    # vero solo per lui.
    alive = [
        row for row in await svc.instances.list(user_id, CONNECTOR_ID)
        if str(row.get("status")) in ("connected", "syncing")
    ]
    instance = await svc.instances.upsert(
        user_id=user_id,
        connector_id=CONNECTOR_ID,
        provider_account_id=f"bank:{institution_id}",
        display_label=institution_id,
        authorized_scopes=["accounts:read", "transactions:read"],
        # `None` lascia dov'e' il riferimento che c'e' gia'; una stringa
        # vuota lo cancellerebbe.
        secret_reference=secret_reference or None,
        status=str(alive[0]["status"]) if alive else "pending",
        metadata={
            "institution": institution_id,
            "link_reference": reference,
            "started_at": _now_iso(),
        },
        poll_interval_min=360,
    )

    # Chi torna dal sito della banca non porta con se' un'autenticazione: il
    # browser arriva sulla porta di ritorno con un codice e uno `state`, e
    # nient'altro.
    #
    #     LO «STATE» E' L'UNICA COSA CHE LEGA QUEL RITORNO A UNA PERSONA.
    #
    # Quindi e' imprevedibile, si usa una volta sola, e scade. Senza queste
    # tre proprieta' chiunque sappia indovinare una stringa potrebbe far
    # collegare il proprio conto all'account di qualcun altro — o, peggio,
    # il contrario.
    await svc.db[LINK_STATES].insert_one({
        "state": reference,
        "user_id": user_id,
        "instance_id": instance["id"],
        "institution_id": institution_id,
        # Dove torna la persona a cose fatte. Non e' l'indirizzo che riceve
        # il codice — quello e' registrato nell'applicazione e non si sceglie
        # — ma la schermata su cui deve ritrovarsi.
        "redirect_after": redirect_to,
        "created_at": _now_iso(),
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(minutes=LINK_STATE_MINUTES)
        ).isoformat(),
        "used_at": None,
    })

    return {
        "ok": True,
        "instance_id": instance["id"],
        # Dove la persona autentica. E' l'unico posto in cui digitera'
        # qualcosa, e non e' ORA.
        "vai_qui": started["link"],
        "stato": CONNECTING,
        "in_parole": IN_WORDS[CONNECTING],
    }


async def finish_link(svc, *, user_id: str, instance_id: str) -> Dict[str, Any]:
    """
    Guarda se la persona ha finito, e in caso registra i conti.

    Chiamata al ritorno dal percorso della banca, e di nuovo se la persona
    riapre la schermata: e' idempotente per costruzione, perche' l'unico
    modo di sapere com'e' andata e' chiedere all'aggregatore.
    """
    instance = await svc.instances.get(user_id, instance_id)
    if not instance:
        return {"stato": NOT_CONNECTED, "in_parole": IN_WORDS[NOT_CONNECTED]}

    asker = getattr(svc.provider, "link_status", None)
    if asker is None:
        await svc.instances.mark_status(user_id, instance_id, "connected")
        return {"stato": CONNECTED, "in_parole": IN_WORDS[CONNECTED]}

    requisition = await _consent_reference(svc, user_id, instance)
    if not requisition:
        return {"stato": NOT_CONNECTED, "in_parole": IN_WORDS[NOT_CONNECTED]}

    from connectors.bank.provider import BankAPIError

    try:
        seen = await asker(requisition)
    except BankAPIError as e:
        state = NEEDS_CONSENT if e.consent_expired else UNAVAILABLE
        await svc.instances.mark_status(
            user_id, instance_id,
            "reauthorization_required" if state == NEEDS_CONSENT else "degraded",
        )
        return {"stato": state, "in_parole": IN_WORDS[state],
                "cosa_posso_fare": WHAT_TO_DO[state]}

    state = WHILE_LINKING.get(str(seen.get("status") or "").upper(), CONNECTING)
    if state != CONNECTED:
        if state == NEEDS_CONSENT:
            await svc.instances.mark_status(
                user_id, instance_id, "reauthorization_required")
        return {"stato": state, "in_parole": IN_WORDS[state],
                "cosa_posso_fare": WHAT_TO_DO[state]}

    await svc.instances.mark_status(user_id, instance_id, "connected")
    # I conti arrivano adesso: e' la prima lettura, e la persona si aspetta
    # di vedere qualcosa appena torna indietro.
    read = await svc.sync(user_id=user_id, instance_id=instance_id)
    return {
        "stato": CONNECTED,
        "in_parole": IN_WORDS[CONNECTED],
        "conti": len(seen.get("accounts") or []),
        "prima_lettura": read,
    }


async def complete_with_code(svc, *, state: str, code: str) -> Dict[str, Any]:
    """
    Il ritorno dal sito della banca: uno state, un codice, e una sessione.

        UN CODICE NON E' UN PERMESSO. LO DIVENTA UNA VOLTA SOLA.

    Il codice che arriva nel browser vale un solo scambio: si presenta
    all'aggregatore e torna indietro una sessione, che e' il permesso vero e
    l'unica cosa che vale la pena custodire. Saltare questo passaggio e
    andare dritti ai conti non e' una scorciatoia — e' una cosa che non
    funziona, perche' il codice non apre niente.

    Lo `state` fa il resto del lavoro: dice di chi e' questo ritorno. Viene
    consumato qui e non serve piu' a nessuno.
    """
    opener = getattr(svc.provider, "open_session", None)
    if opener is None:
        return {"ok": False, "perche": "questo provider non apre sessioni"}

    row = await svc.db[LINK_STATES].find_one({"state": state}, {"_id": 0})
    if not row:
        # Nessuno ha cominciato questo collegamento. Non si dice altro: chi
        # tira a indovinare non deve imparare niente dalla risposta.
        return {"ok": False, "perche": "collegamento non riconosciuto"}
    if row.get("used_at"):
        return {"ok": False, "perche": "questo collegamento è già stato usato"}
    if str(row.get("expires_at") or "") < _now_iso():
        return {"ok": False, "perche": "il collegamento è scaduto, riprova"}

    user_id = str(row["user_id"])
    instance_id = str(row["instance_id"])

    from connectors.bank.provider import BankAPIError
    from connectors.bank.service import CONNECTOR_ID

    try:
        session = await opener(code=code)
    except BankAPIError as e:
        await svc.instances.mark_status(user_id, instance_id, "degraded")
        logger.info("session exchange failed (%s)", e.status_code)
        return {"ok": False, "perche": "la banca non ha completato il collegamento"}

    if not session.get("session_id"):
        return {"ok": False, "perche": "la banca non ha completato il collegamento"}

    # Adesso c'e' un permesso, e va dove vanno tutti i permessi: nel vault,
    # cifrato. Nel documento dell'istanza resta il puntatore e nient'altro.
    secret_reference = await svc.vault.put(
        user_id=user_id,
        purpose="bank_consent",
        payload={"session_id": session["session_id"]},
        metadata={"connector_id": CONNECTOR_ID,
                  "institution_id": str(row.get("institution_id") or "")},
    )

    aspsp = session.get("aspsp") or {}
    await svc.instances.update(user_id, instance_id, {
        "secret_reference": secret_reference,
        "status": "connected",
        "reauthorization_required": False,
        "metadata": {
            "institution": str(aspsp.get("name") or row.get("institution_id") or ""),
            "country": str(aspsp.get("country") or ""),
            "consent_until": session.get("valid_until") or "",
            "accounts": len(session.get("accounts") or []),
        },
    })
    await svc.db[LINK_STATES].update_one(
        {"state": state}, {"$set": {"used_at": _now_iso()}},
    )

    # E si legge subito: chi torna indietro si aspetta di vedere qualcosa.
    read = await svc.sync(user_id=user_id, instance_id=instance_id)
    return {
        "ok": True,
        "user_id": user_id,
        "instance_id": instance_id,
        "redirect_after": str(row.get("redirect_after") or ""),
        "conti": len(session.get("accounts") or []),
        "prima_lettura": read,
    }


async def connection_state(svc, *, user_id: str) -> Dict[str, Any]:
    """Com'e' messo il collegamento di questa persona, in una frase."""
    from connectors.bank.service import CONNECTOR_ID

    rows = await svc.instances.list(user_id, CONNECTOR_ID)
    alive = [r for r in rows if str(r.get("status")) not in ("revoked", "disabled")]
    instance = alive[0] if alive else None
    state = _human_state(instance)
    out: Dict[str, Any] = {
        "stato": state,
        "in_parole": IN_WORDS[state],
        "cosa_posso_fare": WHAT_TO_DO[state],
    }
    if instance:
        out["instance_id"] = instance["id"]
        out["banca"] = str(
            (instance.get("metadata") or {}).get("institution")
            or instance.get("display_label") or ""
        )
        out["letto_l_ultima_volta"] = instance.get("last_sync_at") or ""
    return out


async def disconnect(svc, *, user_id: str, instance_id: str) -> Dict[str, Any]:
    """
    Scollega il conto: chiudi il permesso, ferma le letture, tieni la memoria.

        SCOLLEGARE UNA FONTE NON CANCELLA QUELLO CHE SI E' CAPITO.

    Quattro cose, in quest'ordine. Si chiude il consenso dal lato
    dell'aggregatore — finche' vive, il permesso di leggere esiste, e
    scollegare in ORA senza chiuderlo lascerebbe in piedi esattamente cio'
    che la persona ha chiesto di togliere. Si distrugge il riferimento nel
    vault. Si mette l'istanza fra le revocate, cosi' il ciclo automatico non
    la guarda piu'. E si marca come non piu' aggiornato tutto quello che
    veniva da li'.

    Quello che *non* si fa e' cancellare la conoscenza governata. Che
    l'affitto sia di 760 euro al mese resta vero dopo aver scollegato la
    banca: e' una cosa che ORA ha capito, non un pezzo di dato bancario in
    prestito. Perde pero' il diritto di essere data per fresca, e la
    provenienza dice da dove veniva e fino a quando.
    """
    instance = await svc.instances.get(user_id, instance_id)
    if not instance:
        return {"ok": False, "in_parole": "Non c'è nessun conto da scollegare."}

    closed = False
    ender = getattr(svc.provider, "end_link", None)
    requisition = await _consent_reference(svc, user_id, instance)
    if ender is not None and requisition:
        try:
            closed = await ender(requisition)
        except Exception as e:
            logger.info("end_link soft-fail: %s", type(e).__name__)

    reference = instance.get("secret_reference")
    if reference:
        try:
            await svc.vault.revoke(reference)
        except Exception as e:
            logger.info("vault revoke soft-fail: %s", type(e).__name__)

    await svc.instances.mark_status(user_id, instance_id, "revoked")
    await svc.instances.update(user_id, instance_id, {"secret_reference": ""})

    when = _now_iso()
    stale = await _mark_stale(svc.db, user_id, instance_id, when)

    try:
        await svc.permissions.audit.log(
            user_id=user_id, event_type="bank.disconnect",
            connector_id="banking_psd2", connector_instance_id=instance_id,
            capability_id="banking.read", success=True,
            data_classification="highly_sensitive",
        )
    except Exception as e:
        logger.info("audit soft-fail: %s", type(e).__name__)

    return {
        "ok": True,
        "consenso_chiuso": closed,
        "non_piu_aggiornato": stale,
        "stato": NOT_CONNECTED,
        "in_parole": (
            "Ho scollegato il conto. Non leggerò più i movimenti. "
            "Quello che ho capito finora resta, con la data in cui l'ho letto."
        ),
    }


async def _mark_stale(db, user_id: str, instance_id: str, when: str) -> int:
    """
    Quello che veniva dalla banca non e' piu' aggiornato — e lo dice.

    Non cancellato: un saldo di ieri e' un fatto di ieri, e mostrarlo con la
    sua data e' onesto. Mostrarlo come se fosse di adesso non lo sarebbe.
    """
    touched = 0
    try:
        got = await db["bank_accounts"].update_many(
            {"owner_id": user_id},
            {"$set": {"source_disconnected_at": when}},
        )
        touched += int(getattr(got, "modified_count", 0) or 0)
        got = await db["financial_facts"].update_many(
            {"owner_id": user_id, "provenance.source": "bank"},
            {"$set": {"source_disconnected_at": when}},
        )
        touched += int(getattr(got, "modified_count", 0) or 0)
    except Exception as e:
        logger.info("stale mark soft-fail: %s", type(e).__name__)
    return touched


async def _consent_reference(svc, user_id: str, instance: Dict[str, Any]) -> str:
    """Il riferimento del consenso, dal vault. Mai dal documento."""
    reference = instance.get("secret_reference")
    if not reference:
        return ""
    try:
        payload = await svc.vault.get(reference, user_id=user_id)
    except Exception as e:
        logger.info("vault read soft-fail: %s", type(e).__name__)
        return ""
    # Ogni aggregatore chiama il proprio permesso in un modo — una
    # requisition, una sessione. Quello che conta e' che sia *il permesso di
    # questa persona*, e che stia in un posto solo.
    return str(
        (payload or {}).get("session_id")
        or (payload or {}).get("requisition_id")
        or ""
    )
