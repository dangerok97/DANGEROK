"""
Quello che è successo al telefono, raccontato a chi ha chiesto la telefonata.

    QUESTA NON È UNA CONSOLE. È IL RESOCONTO DI UNA COMMISSIONE.

Dall'altra parte di questa schermata non c'è chi ha scritto il runtime: c'è
qualcuno che ha chiesto a ORA di spostare un appuntamento e adesso vuole
sapere com'è andata. La differenza fra le due cose è tutta nel linguaggio.

    «APPUNTAMENTO SPOSTATO ALLE 18» — NON «mission_status=success».

Gli stati che il backend usa per ragionare restano dove sono e non cambiano:
servono a decidere, e decidere non è raccontare. Qui accanto ne nasce un
secondo insieme, che serve solo a essere letto.

    E SONO TRE COSE DIVERSE, NON UNA.

Com'è finita la telefonata (`call_status`), com'è finita la missione
(`mission_status`), e come si dice a una persona (`presentation_status`). Una
telefonata può riuscire benissimo e riportare che non si è potuto fare niente:
«ha risposto, e ha detto di no» sono due fatti, non uno.

    SI RACCONTA SOLO QUELLO CHE QUALCUNO HA DAVVERO CONFERMATO.

Il riassunto non lo scrive chi ha parlato: nasce dall'esito già validato dal
backend. Un modello che decide da solo cosa scrivere in un resoconto è un
modello che prima o poi scrive «fatto» di una cosa che non è stata fatta.

    E «HANNO CONFERMATO» NON È ANCORA «È SPOSTATO».

La telefonata e la sua applicazione sono due fatti, e questa schermata è
l'unico posto in cui qualcuno li vede insieme. Se lo studio ha confermato le
18:00 e il calendario non si è lasciato aggiornare, la riga non può dire
«Appuntamento spostato alle 18:00»: quella frase manderebbe una persona a
fidarsi di un calendario che è rimasto alle sedici. Si dice tutte e due le
cose, in quest'ordine — cos'ha detto la controparte, e cos'è riuscito a fare
ORA — perché la seconda senza la prima sembrerebbe una telefonata andata male,
e non lo è stata.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

# Come si dice a una persona. Non sostituisce gli stati interni: li traduce.
PresentationStatus = Literal[
    "in_corso",
    "completata",
    "serve_una_decisione",
    "nessuna_risposta",
    "occupato",
    "segreteria",
    "non_riuscita",
    "interrotta",
    "non_avviata",
]

#     COM'E' FINITA, IN UNA PAROLA SOLA E STRUTTURATA.
#
# Non è un secondo insieme di stati da mantenere: è la lettura combinata di
# quello che c'è già — lo stato della linea (`state`, `how_it_ended`) e
# l'esito validato della missione (`status`, `delivery`, `ended_because`).
# Serve a chi ragiona (il piano, i test); a chi legge va `presentation_status`.
CallResult = Literal[
    "in_progress",
    "not_started",           # preparata e mai composta
    "success",
    "no_answer",
    "busy",
    "voicemail",
    "recipient_unavailable",
    "wrong_person",
    "not_connected",         # l'operatore non l'ha fatta partire
    "transport_failure",     # la linea è caduta a conversazione iniziata
    "live_runtime_failure",  # la voce è caduta e non si è ripresa
    "partial",
    "needs_user",
    "failed",
]

# Da com'è finita a come si dice. Più risultati possono leggersi allo stesso
# modo: «interrotta» è la stessa frase per chi legge, qualunque filo sia caduto.
_COME_SI_RACCONTA: Dict[str, str] = {
    "in_progress": "in_corso",
    "not_started": "non_avviata",
    "success": "completata",
    "no_answer": "nessuna_risposta",
    "busy": "occupato",
    "voicemail": "segreteria",
    "recipient_unavailable": "non_riuscita",
    "wrong_person": "non_riuscita",
    "not_connected": "non_riuscita",
    "transport_failure": "interrotta",
    "live_runtime_failure": "interrotta",
    "partial": "interrotta",
    "needs_user": "serve_una_decisione",
    "failed": "non_riuscita",
}

# L'etichetta che si legge sulla card, per ogni stato.
COME_SI_LEGGE: Dict[str, str] = {
    "in_corso": "In corso",
    "completata": "Completata",
    "serve_una_decisione": "Serve una tua decisione",
    "nessuna_risposta": "Nessuna risposta",
    "occupato": "Occupato",
    "segreteria": "Segreteria",
    "non_riuscita": "Non riuscita",
    "interrotta": "Interrotta",
    "non_avviata": "Non avviata",
}

# Che cosa si andava a fare, detto come lo direbbe una persona. Serve a
# scrivere il riassunto quando la missione è riuscita ma non ha prodotto un
# orario da mostrare.
_ANDATA_BENE = {
    "reschedule": "Appuntamento spostato",
    "book": "Prenotazione effettuata",
    "cancel": "Appuntamento disdetto",
    "confirm": "Confermato",
    "ask": "Informazione ottenuta",
}

_NON_ANDATA = {
    "reschedule": "Non è stato possibile spostare l'appuntamento.",
    "book": "Non è stato possibile prenotare.",
    "cancel": "Non è stato possibile disdire.",
    "confirm": "Non è stato possibile confermare.",
    "ask": "Non è stato possibile avere l'informazione.",
}


def _the_mission_outcome(call) -> Optional[Dict[str, Any]]:
    """
    L'esito della missione, da dove si trova.

    Il runtime a missione lo lascia fra i numeri della telefonata; il runtime
    classico ha un suo esito, di forma diversa. Qui interessa il primo: è
    l'unico che porta uno stato già validato dal backend.
    """
    esito = (call.metrics or {}).get("outcome")
    return esito if isinstance(esito, dict) else None


def _what_the_mission_says(call) -> Optional[str]:
    """Lo stato della missione: success · needs_user · failed · partial."""
    esito = _the_mission_outcome(call)
    if esito and esito.get("status"):
        return str(esito["status"])
    # Il runtime classico non ha stati di missione: ha capito, o non ha capito.
    if call.outcome is not None:
        return "success" if call.outcome.understood else "partial"
    return None


def result_of(call) -> str:
    """
    Com'è finita, in una parola strutturata (`CallResult`).

        PRIMA COM'È ANDATA LA LINEA, POI COM'È ANDATA LA MISSIONE.

    L'ordine non è arbitrario. Se nessuno ha risposto non c'è nessuna missione
    da raccontare, e dire «non riuscita» a una telefonata che non è mai
    cominciata sposterebbe la colpa sul posto sbagliato.

        «LA LINEA E' CADUTA» NON E' MAI «RIUSCITA».

    Un successo esce solo da un esito di missione validato. Una caduta prima
    di quell'esito è una caduta, qualunque cosa si fosse detto.
    """
    if call.state == "expired":
        return "not_started"
    if call.state == "authorised":
        # Preparation is not a connected line. A dial failure can leave the
        # call authorised for a safe retry; the UI must not poll it forever.
        return "not_started"
    if call.state in ("dialling", "talking"):
        return "in_progress"

    come_e_finita = call.how_it_ended or "unknown"
    if come_e_finita == "no_answer":
        return "no_answer"
    if come_e_finita == "busy":
        return "busy"

    esito = _the_mission_outcome(call) or {}
    perche = str(esito.get("ended_because") or "")
    consegna = str(esito.get("delivery") or "")
    if perche == "voicemail" or consegna == "voicemail":
        return "voicemail"

    if (come_e_finita == "failed" or call.state == "failed") and not esito:
        #     NON E' MAI PARTITA, O E' CADUTA SENZA LASCIARE NIENTE.
        return "transport_failure" if call.started_at else "not_connected"

    if consegna in ("recipient_unavailable", "wrong_person"):
        return consegna

    missione = _what_the_mission_says(call)
    if missione == "success":
        return "success"
    if missione == "needs_user":
        return "needs_user"
    if perche == "live_runtime_failure":
        return "live_runtime_failure"
    if perche == "line_dropped":
        return "transport_failure"
    if missione == "partial":
        return "partial"
    if missione == "failed":
        return "failed"

    #     HA RISPOSTO QUALCUNO, E NON SAPPIAMO DIRE COS'È SUCCESSO.
    # Non è un successo e non è un fallimento: è una telefonata che si è
    # chiusa senza lasciare un esito. Dirlo è più onesto che sceglierne uno.
    return "transport_failure"


def how_it_reads(call) -> PresentationStatus:
    """Come si racconta questa telefonata: la parola per chi legge."""
    return _COME_SI_RACCONTA.get(result_of(call), "interrotta")  # type: ignore[return-value]


def _when_it_moved_to(cambiamenti: Dict[str, Any]) -> str:
    """
    «alle 18:00», da quello che la controparte ha confermato.

        TRE MISSIONI SCRIVONO L'ORARIO IN TRE CAMPI DIVERSI.

    Uno spostamento dice dove è arrivato (`new_time`); una disdetta e una
    prenotazione dicono di quale appuntamento si parla (`appointment_time`).
    Sono la stessa frase per chi legge — «alle 18:00» — e tre chiavi diverse
    per chi la costruisce.
    """
    ora = (
        cambiamenti.get("new_time")
        or cambiamenti.get("appointment_time")
        or cambiamenti.get("when")
        or ""
    )
    return f" alle {ora}" if ora else ""


def in_one_line(call, application: Any = None) -> str:
    """
    Com'è andata, in una riga, per chi ha chiesto la telefonata.

        NON LO SCRIVE CHI HA PARLATO.

    Nasce dall'esito che il backend ha già validato: se là dentro non c'era
    niente di confermato, qui non compare niente di confermato — e se quello
    che è stato confermato non è arrivato fino al calendario, lo dice.
    """
    stato = how_it_reads(call)
    risultato = result_of(call)

    if stato == "in_corso":
        return "Chiamata in corso."
    if stato == "non_avviata":
        return "Non avviata: la telefonata non è mai partita."
    if stato == "nessuna_risposta":
        return "Non ha risposto."
    if stato == "occupato":
        return "Il numero era occupato."
    if stato == "segreteria":
        return "Ha risposto la segreteria."
    if risultato == "not_connected":
        return "La telefonata non è partita."
    if risultato in ("transport_failure", "live_runtime_failure", "partial"):
        return "La chiamata si è interrotta prima che riuscissi a concludere."

    esito = _the_mission_outcome(call)
    tipo = _mission_type_of(call)

    if tipo == "deliver_message":
        return _the_delivery_in_one_line(call, stato)

    if stato == "serve_una_decisione":
        perche = (esito or {}).get("user_confirmation_needed") or ""
        return perche.strip() or "Serve una tua decisione per andare avanti."

    if stato == "completata":
        cambiamenti = (esito or {}).get("confirmed_changes") or {}
        mancato = _what_did_not_get_written(application)
        if mancato:
            return _confirmed_but_not_written(tipo, cambiamenti, mancato)
        if cambiamenti:
            return f"{_ANDATA_BENE.get(tipo, 'Fatto')}{_when_it_moved_to(cambiamenti)}."
        if call.outcome is not None and call.outcome.in_a_line:
            return call.outcome.in_a_line
        return f"{_ANDATA_BENE.get(tipo, 'Fatto')}."

    if stato == "non_riuscita":
        perche = (esito or {}).get("user_confirmation_needed") or ""
        if perche.strip():
            return perche.strip()
        return _NON_ANDATA.get(tipo, "Non è stato possibile portarla a termine.")

    return "La chiamata si è interrotta prima che riuscissi a concludere."


#     COSA STA IN MEZZO FRA UNA CONFERMA E UN CALENDARIO AGGIORNATO.
#
# Quattro esiti dell'applicazione che non sono «fatto», e ognuno vuole una
# frase diversa perché chiede alla persona una cosa diversa. Il conflitto
# vuole che vada a guardare; il fallimento vuole che riprovi o lo faccia a
# mano; lo scarto senza legame non vuole niente, perché nessuno le aveva
# promesso che il calendario sarebbe cambiato.
_NON_SCRITTO = {
    "conflict": (
        "ma l'appuntamento in calendario era già cambiato: non l'ho toccato."
    ),
    "failed": "ma non sono riuscita ad aggiornare il calendario.",
    "skipped": "ma il calendario non l'ho aggiornato.",
    "pending": "sto verificando l'aggiornamento del calendario.",
}


def _what_did_not_get_written(application: Any) -> str:
    """
    Che cosa non è arrivato fino al calendario, se qualcosa.

        UN'APPLICAZIONE CHE NON C'È NON È UN'APPLICAZIONE FALLITA.

    Torna vuoto in tre casi che sembrano uno solo e non lo sono: nessuno ci ha
    provato, è andata a buon fine, oppure non c'era niente da scrivere perché
    la telefonata non era legata a un appuntamento. In tutti e tre la riga
    resta quella di prima — raccontare un fallimento che non è successo è
    sbagliato quanto tacerne uno che è successo.
    """
    if application is None:
        return ""
    stato = str(getattr(application, "application_status", "") or "")
    if stato == "applied":
        return ""
    if (
        not str(getattr(application, "target_entity_id", "") or "")
        and str(getattr(application, "operation", "") or "") != "book"
    ):
        # Stessa ragione di `_did_it_change_anything`: una prenotazione non ha
        # un oggetto prima di crearlo, e quel vuoto non vuol dire «non c'era
        # niente da fare».
        return ""
    return _NON_SCRITTO.get(stato, "ma il calendario non risulta aggiornato.")


def _confirmed_but_not_written(tipo: str, cambiamenti: Dict[str, Any], coda: str) -> str:
    """
    Le due metà, nell'ordine in cui servono.

    Prima quello che la controparte ha fatto — è successo, ed è merito suo —
    poi quello che ORA non è riuscita a fare. All'incontrario sembrerebbe una
    telefonata andata storta, e la telefonata è andata benissimo.
    """
    quando = _when_it_moved_to(cambiamenti)
    chi = {
        "reschedule": "Hanno confermato lo spostamento",
        "book": "Hanno confermato la prenotazione",
        "cancel": "Hanno confermato la disdetta",
        "confirm": "Hanno confermato",
    }.get(tipo, "Hanno confermato")
    if tipo == "cancel":
        # «Hanno confermato la disdetta alle 18:00» si legge come se avessero
        # disdetto alle diciotto. Per una disdetta l'ora non è un risultato:
        # è il nome dell'appuntamento tolto, e va detta così.
        quando = f" dell'appuntamento{quando}" if quando else ""
    return f"{chi}{quando}, {coda}"


def _mission_type_of(call) -> str:
    """Che cosa si andava a fare. Dal mandato, che è dove è sempre stato."""
    from telephone.mission import _what_kind_of_mission

    if call.mandate is not None and (call.mandate.message or "").strip():
        return "deliver_message"
    return _what_kind_of_mission((call.mandate.why_calling or "") if call.mandate else "")


def a_chi(nome: str) -> str:
    """«a Giulia», «ad Asia»: davanti a una vocale uguale si dice «ad»."""
    return f"ad {nome}" if nome[:1].lower() == "a" else f"a {nome}"


def _the_delivery_in_one_line(call, stato: str) -> str:
    """
    Una consegna, raccontata a chi l'aveva chiesta.

        «MESSAGGIO CONSEGNATO» SOLO SE L'HA SENTITO LA PERSONA GIUSTA.

    E se ha risposto qualcosa, la sua risposta viene prima di tutto il resto:
    è la cosa che chi ha mandato il messaggio vuole leggere.
    """
    esito = _the_mission_outcome(call) or {}
    chi = ((call.mandate.recipient if call.mandate else "") or call.calling_whom
           or "questa persona").split()[0]
    consegna = str(esito.get("delivery") or "")
    risposta = str(esito.get("recipient_reply") or "").strip()

    if consegna == "delivered":
        if risposta:
            return f"{chi} ti ha risposto: «{risposta}»"
        return f"Messaggio consegnato {a_chi(chi)}."
    if consegna == "recipient_unavailable":
        quando = str(esito.get("user_confirmation_needed") or "").strip()
        riga = f"Non sono riuscita a parlare con {chi}: ha risposto un'altra persona."
        return f"{riga} {quando}".strip() if quando else riga
    if consegna in ("wrong_person", "no_answer"):
        return f"Non sono riuscita a parlare con {chi}."
    if stato == "serve_una_decisione":
        return (str(esito.get("user_confirmation_needed") or "").strip()
                or "Serve una tua decisione.")
    return f"Non sono riuscita a consegnare il messaggio a {chi}."


def how_long(call) -> Optional[int]:
    """
    Quanto è durata la conversazione, in secondi.

        DA QUANDO HANNO RISPOSTO, NON DA QUANDO ABBIAMO COMPOSTO.

    Gli squilli non sono una telefonata: contarli farebbe sembrare lunga una
    chiamata a cui non ha risposto nessuno.
    """
    from datetime import datetime

    if not call.started_at or not call.ended_at:
        return None
    try:
        a = datetime.fromisoformat(call.started_at)
        b = datetime.fromisoformat(call.ended_at)
        return max(0, int((b - a).total_seconds()))
    except Exception:
        return None


def as_a_card(call, application: Any = None) -> Dict[str, Any]:
    """
    Una telefonata come si legge in elenco.

        NIENTE DI TECNICO QUI DENTRO.

    Non c'è il nome del modello, non c'è l'identificativo dell'operatore, non
    ci sono gli strumenti chiamati né i token spesi. Chi legge voleva sapere
    se l'appuntamento è stato spostato.
    """
    stato = how_it_reads(call)
    return {
        "id": call.id,
        "counterparty_name": call.calling_whom or "",
        "counterparty_number": call.to_number or "",
        "reason_summary": (call.mandate.why_calling if call.mandate else "") or "",
        "created_at": call.authorised_at,
        "started_at": call.started_at,
        "ended_at": call.ended_at,
        "duration_seconds": how_long(call),
        "presentation_status": stato,
        "status_label": COME_SI_LEGGE[stato],
        "outcome_summary": in_one_line(call, application),
        "needs_decision": stato == "serve_una_decisione",
        "transcript_available": bool(call.turns),
        #     DUE ESITI, DUE CAMPI.
        # Com'è andata la telefonata è `presentation_status`. Se il mondo è
        # cambiato è questo. Sono diversi apposta: una telefonata riuscita che
        # non ha potuto aggiornare il calendario è esattamente il caso in cui
        # un campo solo mentirebbe, e mentirebbe dalla parte rassicurante.
        # `None` vuol dire che non c'era niente da cambiare — la maggior parte
        # delle telefonate — e non è un fallimento.
        "changed_something": _did_it_change_anything(application),
    }


def _did_it_change_anything(application: Any) -> Any:
    """
    Sì, no, o «non c'era niente da cambiare».

        UNA PRENOTAZIONE NON HA UN OGGETTO FINCHÉ NON L'HA CREATO.

    Questa funzione chiedeva «c'è un `target_entity_id`?» e per spostare e
    disdire andava bene: l'evento esiste da prima. Per una prenotazione no —
    l'oggetto nasce dall'applicazione — e sulla prima prenotazione vera la
    scheda ha detto «non c'era niente da cambiare» di un appuntamento appena
    creato su Google. Adesso si guarda anche l'operazione: se c'era qualcosa
    da fare, la risposta è sì o no, mai «niente».
    """
    if application is None:
        return None
    fatto = str(getattr(application, "application_status", ""))
    if str(getattr(application, "operation", "") or "") == "book":
        return fatto == "applied"
    if not str(getattr(application, "target_entity_id", "") or ""):
        return None
    return fatto == "applied"


def in_full(
    call, *, kept_the_mandate: Any = None, application: Any = None,
) -> Dict[str, Any]:
    """
    La stessa telefonata, aperta.

    Qui compare il numero davvero composto — che nel pacchetto della missione
    non era voluto entrare, e che invece a chi ha chiesto la chiamata serve
    per sapere chi è stato chiamato.
    """
    esito = _the_mission_outcome(call) or {}
    scheda = as_a_card(call, application)
    scheda.update({
        "mission_type": _mission_type_of(call),
        "call_status": call.state,
        "how_it_ended": call.how_it_ended,
        "mission_status": _what_the_mission_says(call),
        "confirmed_changes": esito.get("confirmed_changes") or {},
        "needs_user_reason": (
            esito.get("user_confirmation_needed") or ""
            if scheda["presentation_status"] == "serve_una_decisione" else ""
        ),
        "failure_reason": (
            esito.get("user_confirmation_needed") or ""
            if scheda["presentation_status"] == "non_riuscita" else ""
        ),
        "may_agree_to": list(call.mandate.may_agree_to) if call.mandate else [],
        "kept_the_mandate": kept_the_mandate,
        "transcript_entries": len(call.turns or []),
        #     CHE COSA HA TOCCATO ORA, DETTO PER NOME.
        # Nel dettaglio ci sta: chi apre una telefonata dopo che qualcosa non
        # ha funzionato vuole sapere che cosa è stato provato e che cosa si è
        # fermato, non solo che si è fermato.
        **_the_application(application),
    })
    return scheda


def _the_application(application: Any) -> Dict[str, Any]:
    """Il secondo fatto, per la scheda aperta."""
    if application is None:
        return {
            "application_status": "",
            "application_error": "",
            "application_target": "",
        }
    return {
        "application_status": str(getattr(application, "application_status", "")),
        "application_error": str(getattr(application, "error", "")),
        "application_target": str(getattr(application, "target_domain", "")),
    }


def the_transcript(call) -> List[Dict[str, Any]]:
    """
    Quello che si sono detti, e nient'altro.

        IL TESTO C'ERA GIÀ. L'AUDIO NON C'È MAI STATO.

    Queste battute non si ricavano da una registrazione: sono state raccolte
    mentre si parlava, perché chi ascolta e chi parla producono testo comunque.
    Per questo il pulsante dice «mostra» e non «genera»: non stiamo
    trascrivendo niente adesso, stiamo aprendo una cosa che era già lì.

    E per la stessa ragione non si può fare meglio: se una frase è arrivata
    storta, resta storta. Correggerla vorrebbe dire inventare che cosa è stato
    detto a nome di qualcuno che non può smentirci.
    """
    fuori = []
    for n, battuta in enumerate(call.turns or []):
        fuori.append({
            "sequence_number": n,
            "speaker": "ora" if battuta.who == "ora" else "counterparty",
            "text": battuta.said or "",
            "at": battuta.at,
        })
    return fuori
