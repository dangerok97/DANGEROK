"""
Telefonare, come capacità della conversazione.

    PREPARARE NON È CHIAMARE.

Quello che ORA può fare da dentro una conversazione è *preparare* una
telefonata: scrivere a chi, perché, e cosa potrebbe accettare. Comporre il
numero è un'altra cosa e passa da un'altra porta, dove c'è una persona che
legge quello che ORA sta per dire e dice di sì.

La separazione non è burocrazia. Una capacità che compone il numero da sola
significa che una frase detta male in chat — o una riga di contesto letta
storta — fa squillare il telefono di un estraneo. Il sì non è un attrito da
ridurre: è il punto.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from conversation_engine.ai_core.models import Observation

logger = logging.getLogger("ora.telephone.caps")


def _fail(code: str, detail: str = "") -> Observation:
    return Observation(
        kind="tool", name="prepare_a_phone_call", status="failed",
        payload={
            "capability": "prepare_a_phone_call",
            "status": "error",
            "error": code,
            "detail": detail[:200],
        },
    )


async def prepare_a_phone_call(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    """
    Scrive la telefonata che ORA farebbe, e non la fa.

    Torna a chi ragiona una cosa da raccontare alla persona: chiamerei questo
    numero, direi questa frase per prima, potrei accettare queste cose, e
    tutto il resto te lo riporterei indietro. Poi si aspetta.
    """
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("NOT_CONFIGURED")

    from telephone.models import Mandate
    from telephone.service import TelephoneService

    service = TelephoneService(db)
    permission = await service.may_i_call(uid)

    #     DIRE CHE NON SI PUÒ È UNA RISPOSTA; TACERLO NO.
    #
    # Se non c'è un operatore, chi ragiona deve saperlo adesso — e dirlo — non
    # scoprirlo dopo aver chiesto alla persona il permesso per una cosa che
    # non sarebbe comunque successa.
    if not permission["provider_ready"]:
        return Observation(
            kind="tool", name="prepare_a_phone_call", status="partial",
            payload={
                "capability": "prepare_a_phone_call",
                "status": "unavailable",
                "reason": permission["why_not"] or "non c'è modo di telefonare",
                "say_it_like_this": (
                    "Di' che al telefono non ci puoi ancora andare, e perché, "
                    "in una riga. Non proporre di riprovare più tardi: non è "
                    "una cosa che passa da sola."
                ),
            },
        )

    if permission["denied"]:
        return Observation(
            kind="tool", name="prepare_a_phone_call", status="partial",
            payload={
                "capability": "prepare_a_phone_call",
                "status": "refused_before",
                "reason": "questa persona aveva già detto di no alle telefonate",
            },
        )

    #     A CHIUNQUE, ANCHE SENZA NUMERO: PASSA DALLA PREPARAZIONE.
    #
    # «Chiama la mia ragazza e dille che la amo» non ha un numero, e non deve
    # averlo: trovarlo è il lavoro di V3.20.1, con la rubrica, i numeri già
    # confermati e la domanda quando non si sa. Un messaggio passa sempre di
    # lì, anche con il numero scritto nella frase: è lì che vivono la conferma
    # del numero e il riassunto da leggere prima del sì. Resta diretto solo il
    # percorso di sempre — un numero e una ragione, senza messaggio.
    if (arguments.get("preparation_id") or arguments.get("message")
            or arguments.get("counterparty") or not arguments.get("to_number")):
        return await _through_the_preparation(arguments, runtime, db, uid)

    try:
        mandate = Mandate(
            why_calling=str(arguments.get("why_calling") or "").strip(),
            may_agree_to=[
                str(x)[:160] for x in (arguments.get("may_agree_to") or [])
            ][:8],
            must_bring_back=[
                str(x)[:160] for x in (arguments.get("must_bring_back") or [])
            ][:8],
            minutes=int(arguments.get("minutes") or 5),
        )
    except Exception as e:
        return _fail("INVALID_INPUT", f"mandato non valido: {type(e).__name__}")

    call = await service.prepare(
        uid,
        to_number=str(arguments.get("to_number") or ""),
        calling_whom=str(arguments.get("calling_whom") or ""),
        mandate=mandate,
        session_ref=str(runtime.get("session_id") or ""),
    )
    if not call.to_number:
        return _fail(
            "INVALID_INPUT",
            "numero non italiano: questo pilota chiama solo numeri nazionali",
        )

    from telephone.briefing import disclosure

    legame, perche_no, serve_chiarimento = await _tie_it_to_something(
        db, call, str(arguments.get("calendar_ref") or ""),
        anche_se_passato=bool(arguments.get("proceed_even_if_past")),
        quando=str(arguments.get("desired_datetime") or ""),
        minuti=int(arguments.get("desired_minutes") or 0),
        alternative=[str(x) for x in (arguments.get("allowed_alternatives") or [])][:12],
        primo=str(arguments.get("earliest") or ""),
        ultimo=str(arguments.get("latest") or ""),
        stesso_giorno=bool(arguments.get("same_day_only")),
    )

    #     E UN PROPOSITO CHE SI PUÒ SEGUIRE FINO IN FONDO.
    # Il piano nasce qui perché è qui che si sa che cosa si vuole ottenere e
    # su che cosa: dopo lo squillo resterebbe un orario, e un orario non è un
    # proposito. Nasce senza autorità e non fa succedere niente — il sì è un
    # secondo gesto, e senza quello non c'è nessuna strada che porti fuori.
    await _open_a_plan(db, call, legame)

    return Observation(
        kind="tool", name="prepare_a_phone_call", status="ok",
        payload={
            "capability": "prepare_a_phone_call",
            "status": "prepared",
            "call_id": call.id,
            "to_number": call.to_number,
            "calling_whom": call.calling_whom,
            **_what_it_will_change(legame, perche_no, serve_chiarimento),
            "first_words": disclosure(str(runtime.get("user_name") or "")),
            "why_calling": mandate.why_calling,
            "may_agree_to": mandate.may_agree_to,
            "must_bring_back": mandate.must_bring_back,
            # Perché non è ancora successo niente, e cosa manca.
            "nothing_has_happened_yet": True,
            "how_to_say_it": (
                "Racconta che cosa faresti: chi chiami, cosa dici per prima "
                "cosa, che cosa puoi accettare e che cosa gli riporteresti "
                "indietro. Poi chiedi se vuole che chiami — e aspetta. Non "
                "dire che hai chiamato, non dire che stai chiamando, e non "
                "promettere un esito: non è ancora squillato niente."
            ),
        },
    )


# Le parole con cui comincia un sì. Si guardano le parole che la persona ha
# scritto davvero, non il riassunto che ne fa il modello.
_SI_NUMERO = frozenset({
    "sì", "si", "esatto", "esattamente", "confermo", "ok", "okay", "certo",
    "corretto", "perfetto", "giusto",
})
# Per il via libera valgono anche i verbi rivolti a ORA — «chiamala», «vai».
# «Chiama» da solo no: è come comincia una richiesta, non una risposta.
_SI_VIA = _SI_NUMERO | {"vai", "procedi", "chiamala", "chiamalo", "fallo"}
_ANCHE = ("va bene", "è quello", "e quello", "è giusto", "e giusto")


def _the_person_said_yes(detto: str, *, via_libera: bool = False,
                         richiesta: str = "") -> bool:
    """
    Se quello che la persona ha scritto è un sì. Deterministico.

        CHI DECIDE SE UNO HA DETTO SÌ NON PUO' FIDARSI DI CHI RIASSUME.

    Misurato sul vero: con «chiama» fra le parole del sì, la richiesta
    stessa — «Chiama la mia ragazza e dille che la amo» — è passata per la
    conferma del numero, nello stesso turno. Adesso un sì deve cominciare con
    una parola di assenso, e la frase che ha aperto la preparazione non vale
    mai come risposta: la conferma arriva dopo, o non arriva.
    """
    import re

    testo = " ".join((detto or "").lower().split())
    if not testo:
        return False
    if richiesta and testo == " ".join((richiesta or "").lower().split()):
        return False
    parole = [p for p in re.split(r"[^\wàèéìòù']+", testo) if p]
    if not parole or "no" in parole or "non" in parole[:2]:
        return False
    ammesse = _SI_VIA if via_libera else _SI_NUMERO
    return parole[0] in ammesse or any(testo.startswith(f) for f in _ANCHE)


def _this_turn(runtime: Dict[str, Any]) -> str:
    """Il turno di conversazione in corso: sessione più epoca di ragionamento."""
    epoca = str(runtime.get("reasoning_epoch") or "")
    if not epoca:
        import hashlib
        epoca = "m:" + hashlib.sha1(
            str(runtime.get("user_message") or "").encode("utf-8")).hexdigest()[:16]
    return f"{runtime.get('session_id') or ''}:{epoca}"[:120]


async def _dial_from_the_chat(db, uid: str, call, runtime: Dict[str, Any]):
    """Compone dalla chat, ricordando in quale chat far tornare l'esito."""
    from telephone.placing import dial
    from telephone.service import TelephoneService

    chat = str(runtime.get("session_id") or "")
    if chat and call.chat_session_id != chat:
        call = await TelephoneService(db).mark(call, call.state, chat_session_id=chat)
    return await dial(db, uid, call, authority_ref="chat_final_yes")


async def _through_the_preparation(
    arguments: Dict[str, Any], runtime: Dict[str, Any], db, uid: str,
) -> Observation:
    """
    La telefonata passa dalla preparazione: chi, quale numero, che cosa dire.

        OGNI PASSO TORNA A CHI RAGIONA CON LA FRASE GIUSTA DA DIRE.

    Non compone mai. Arriva al massimo a «la telefonata è pronta» — e ci
    arriva solo dopo un sì vero sul numero, se il numero è nuovo.
    """
    from preparation.preparation import by_id, save
    from preparation.service import (
        answer_question,
        as_a_card,
        change_number,
        choose_contact,
        confirm_number,
        turn_into_a_call,
    )

    detto = str(runtime.get("user_message") or "")
    rif = str(arguments.get("preparation_id") or "").strip()

    if rif:
        prep = await by_id(db, uid, rif)
        if prep is None:
            return _fail("NOT_FOUND", "questa preparazione non esiste più")
    else:
        from autonomy.orchestrator import plan_a_request
        from telephone.requests import the_message_in

        #     LA RICHIESTA E' QUELLA SCRITTA, NON QUELLA RIASSUNTA.
        richiesta = detto.strip() or " ".join(filter(None, (
            f"chiama {arguments.get('counterparty') or ''}".strip(),
            str(arguments.get("why_calling") or ""),
        )))
        numero = str(arguments.get("to_number") or "").strip()
        if numero and numero not in richiesta:
            richiesta = f"{richiesta} (numero {numero})"
        messaggio = the_message_in(detto) or str(arguments.get("message") or "")
        _plan, prep, perche = await plan_a_request(
            db, owner_id=uid, user_request=richiesta,
            counterparty=str(arguments.get("counterparty") or ""),
            operation=str(arguments.get("operation") or ""),
            goal=str(arguments.get("why_calling") or ""),
            message=messaggio,
        )
        if prep is None:
            return _fail("INVALID_INPUT", perche or "non ho capito chi chiamare")

    #     LE RISPOSTE DELLA PERSONA, UNA PER VOLTA.
    rifiutato = ""
    if arguments.get("choose_number"):
        prep, rifiutato = await choose_contact(
            db, prep, number=str(arguments.get("choose_number")))
    elif arguments.get("give_number"):
        prep, rifiutato = await change_number(
            db, prep, number=str(arguments.get("give_number")))
    elif arguments.get("number_is_right") is not None:
        voluto = bool(arguments.get("number_is_right"))
        if voluto and not _the_person_said_yes(detto, richiesta=prep.user_request):
            #     IL MODELLO HA DETTO «SÌ». LA PERSONA NO.
            rifiutato = "la persona non ha ancora confermato il numero"
        else:
            prep, rifiutato = await confirm_number(db, prep, yes=voluto)
    elif arguments.get("answer"):
        prep, rifiutato = await answer_question(
            db, prep, text=str(arguments.get("answer")))

    carta = as_a_card(prep)
    chiamata = ""
    gia_partita = False
    turno = _this_turn(runtime)
    if arguments.get("go_ahead"):
        if not prep.summary_shown_in or prep.summary_shown_in == turno:
            #     PRIMA SI LEGGE IL RIASSUNTO, POI SI DICE SÌ.
            # Un sì dato prima di aver visto il riassunto — o nello stesso
            # turno in cui è apparso — non è un sì al riassunto.
            # Non è un errore da ritentare: è il turno in cui il riassunto
            # viene letto. Il modello lo dice, e aspetta.
            pass
        elif not _the_person_said_yes(detto, via_libera=True,
                                      richiesta=prep.user_request):
            rifiutato = "la persona non ha ancora dato il via libera"
        elif prep.call_id:
            #     UN SECONDO SÌ NON FA UNA SECONDA TELEFONATA.
            # La telefonata di questa preparazione esiste già: se non è ancora
            # partita la si compone, altrimenti si dice che è già in corso.
            from telephone.service import TelephoneService

            gia = await TelephoneService(db).get(uid, prep.call_id)
            if gia is not None and gia.state == "authorised":
                fatta, rifiutato = await _dial_from_the_chat(db, uid, gia, runtime)
                chiamata = fatta.id if fatta is not None and not rifiutato else ""
            else:
                chiamata, gia_partita = prep.call_id, True
        elif not prep.can_become_a_call():
            rifiutato = prep.readiness_says or "la telefonata non è ancora pronta"
        else:
            fatta, perche = await turn_into_a_call(db, prep, operation=prep.operation)
            if fatta is not None and not perche:
                #     IL SECONDO SÌ E' IL VIA LIBERA: SI COMPONE ADESSO.
                # Il primo sì era sul numero; questo è sul riassunto, detto in
                # un turno successivo. Si passa dalla stessa porta della route.
                fatta, perche = await _dial_from_the_chat(db, uid, fatta, runtime)
            chiamata = fatta.id if fatta is not None and not perche else ""
            rifiutato = perche
            carta = as_a_card(prep)

    if carta["ready"] and not chiamata and not prep.summary_shown_in:
        #     DA QUI IN POI IL RIASSUNTO E' STATO DETTO.
        prep.summary_shown_in = turno
        await save(db, prep)

    return Observation(
        kind="tool", name="prepare_a_phone_call", status="ok",
        payload={
            "capability": "prepare_a_phone_call",
            "status": ("calling" if chiamata
                       else "ready" if carta["ready"] else "preparing"),
            "preparation_id": carta["preparation_id"],
            "what_kind_of_call": prep.operation,
            "message_to_deliver": prep.message_to_deliver or None,
            "ora_says": carta["says"],
            #     LA FRASE COMPLETA, GIA' PRONTA.
            # Misurato sul vero: con i pezzi separati il modello ha detto solo
            # «È questo il numero corretto?», senza dire quale numero né da
            # dove veniva. Una conferma su un numero che non si vede non è
            # una conferma.
            "say_this": (
                f"Non sono riuscita a far partire la telefonata: {rifiutato}."
                if arguments.get("go_ahead") and rifiutato and prep.call_id
                else _the_sentence(carta, bool(chiamata), gia_partita)),
            "contact": carta["contact"],
            "candidates": carta["candidates"],
            "number_confirmed": carta["number_confirmed"],
            "number_note": carta["number_note"],
            "question": carta["question"],
            "summary": carta["summary"] or None,
            "not_accepted": rifiutato or None,
            "call_id": chiamata or None,
            "nothing_has_happened_yet": not chiamata,
            "how_to_say_it": _what_to_say_now(carta, bool(chiamata)),
        },
    )


def _the_sentence(carta: Dict[str, Any], preparata: bool,
                  gia_partita: bool = False) -> str:
    """
    Quello che ORA deve dire adesso, in una frase intera e senza pezzi mancanti.

    Nome, numero e provenienza stanno sempre insieme: sono le tre cose che
    servono a chi deve dire «sì, è quello».
    """
    def chi(c):
        dove = c["source_label"] + (f" — {c['source_detail']}" if c.get("source_detail") else "")
        return f"{c['name']}, {c['number']} ({dove})"

    if preparata:
        nome = ((carta.get("contact") or {}).get("name") or "").split()
        a_chi = f" {nome[0]}" if nome else ""
        if gia_partita:
            return f"Sto già chiamando{a_chi}: ti dico com'è andata appena finisce."
        return f"Sto chiamando{a_chi}… Ti dico com'è andata appena finisce."
    if carta["ready"]:
        return f"{carta['summary']} Vuoi che la chiami?"
    if carta["candidates"]:
        elenco = "; ".join(chi(c) for c in carta["candidates"])
        return f"Ho trovato più numeri: {elenco}. Quale è quello giusto?"
    if carta["contact"] and not carta["number_confirmed"]:
        return f"Ho trovato {chi(carta['contact'])}. È questo il numero corretto?"
    if carta["question"]:
        return carta["question"]["asks"]
    return carta["says"]


def _what_to_say_now(carta: Dict[str, Any], preparata: bool) -> str:
    """La frase che chi ragiona deve dire adesso, e che cosa aspettare."""
    intera = "Di' `say_this` così com'è, per intero — non accorciarla. "
    if preparata:
        return intera + ("La telefonata è partita adesso: non dire com'è "
                         "andata, lo saprai quando finisce.")
    if carta["ready"]:
        return (intera + "Poi fermati e aspetta la sua risposta: in questo turno "
                "non richiamare lo strumento. Solo quando, nel messaggio "
                "successivo, risponde sì, richiama con lo stesso preparation_id "
                "e go_ahead=true. Non dire che hai già chiamato.")
    if carta["candidates"]:
        return intera + "Poi richiama con choose_number."
    if carta["contact"] and not carta["number_confirmed"]:
        return (intera + "Poi richiama con preparation_id e number_is_right=true o "
                "false, oppure give_number se te ne dà un altro.")
    if carta["question"]:
        return (intera + "Poi richiama con preparation_id e answer con la "
                "sua risposta.")
    return intera + "Se ti dà un numero, richiama con give_number."


async def _tie_it_to_something(
    db, call, calendar_ref: str, *, anche_se_passato: bool = False,
    quando: str = "", minuti: int = 0,
    alternative: Optional[List[str]] = None, primo: str = "",
    ultimo: str = "", stesso_giorno: bool = False,
):
    """
    Lega la telefonata all'appuntamento che dovrà spostare, se ce n'è uno.

        L'EVENTO SI DECIDE ADESSO, CHE C'È ANCORA QUALCUNO A CUI CHIEDERE.

    Questo è l'unico momento in cui la domanda «quale appuntamento?» ha una
    risposta possibile: c'è una conversazione aperta, la persona è lì, e non è
    ancora squillato niente. Dopo la telefonata resterebbe solo un orario, e
    un orario da solo non dice quale evento — cercarlo per somiglianza vuol
    dire, prima o poi, spostare quello sbagliato.
    """
    from telephone.binding import bind_a_calendar_event

    try:
        return await bind_a_calendar_event(
            db, call=call, calendar_ref=calendar_ref,
            even_if_it_is_past=anche_se_passato,
            desired_datetime=quando, desired_minutes=minuti,
            allowed_alternatives=alternative, earliest=primo,
            latest=ultimo, same_day_only=stesso_giorno,
        )
    except Exception as e:
        logger.info("legame non riuscito: %s", type(e).__name__)
        return None, "non sono riuscita a ritrovare quell'appuntamento", False


def _what_it_will_change(
    legame, perche_no: str, serve_chiarimento: bool = False,
) -> Dict[str, Any]:
    """
    Che cosa cambierà davvero, detto a chi deve raccontarlo alla persona.

        «TI CHIAMO E POI TE LO DICO» E «TI CHIAMO E LO SPOSTO» SONO DUE COSE.

    La differenza sta tutta in questo campo, e va detta prima del sì — perché
    è esattamente quello su cui la persona sta dicendo di sì. Una telefonata
    senza legame non è un guasto: è una telefonata che riporterà una risposta
    invece di cambiare un calendario, ed è un esito legittimo purché sia
    quello che la persona si aspetta.
    """
    if legame is not None:
        return {
            "will_update_calendar": True,
            "how_to_say_that_too": (
                "Di' anche che, se lo studio conferma, l'appuntamento in "
                "calendario lo sposti tu — così non deve farlo lui."
            ),
        }
    if not perche_no:
        return {"will_update_calendar": False}
    if serve_chiarimento:
        #     UNA DOMANDA NON È UN RIFIUTO, E NON SI RACCONTA COME TALE.
        # Qui non c'è niente di rotto: c'è una cosa che solo la persona può
        # decidere, e che dopo lo squillo non potrà più decidere.
        return {
            "will_update_calendar": False,
            "needs_clarification": True,
            "ask_this_first": perche_no,
            "how_to_say_that_too": (
                "Non chiedere ancora se vuole che chiami. Fai prima questa "
                "domanda e aspetta: se ti dice di sì, richiama questo stesso "
                "strumento con `proceed_even_if_past` a vero e lo stesso "
                "`calendar_ref`. Se ti dice di no, chiedi quale appuntamento "
                "intendeva."
            ),
        }
    return {
        "will_update_calendar": False,
        "why_nothing_will_change": perche_no,
        "how_to_say_that_too": (
            "Prima di chiedere il sì, chiedi quale appuntamento è: senza "
            "quello puoi telefonare e riportargli la risposta, ma il "
            "calendario resterà com'è. Dillo, non lasciarlo intendere."
        ),
    }


async def _open_a_plan(db, call, legame) -> None:
    """
    Apre il piano di questa commissione, se c'è qualcosa da portare a termine.

        UNA TELEFONATA CHE RIPORTA UNA RISPOSTA NON HA BISOGNO DI UN PIANO.

    Il piano serve a rispondere a «e com'è finita?» quando la risposta non è
    una frase ma un calendario cambiato. Senza legame non c'è niente da
    cambiare, e un piano vuoto sarebbe un proposito che non può che finire
    male.

    Non solleva mai: preparare una telefonata è una cosa che deve riuscire
    anche quando il ciclo che la seguirà non riesce a nascere.
    """
    if legame is None:
        return
    try:
        from autonomy.orchestrator import plan_a_user_request

        await plan_a_user_request(db, call=call, binding=legame)
    except Exception as e:  # pragma: no cover
        logger.info("piano non aperto: %s", type(e).__name__)
