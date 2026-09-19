"""
La telefonata in cui a parlare è un esecutore, e a decidere è ORA.

    ORA SA TUTTO. CHI TELEFONA SA UNA COSA.

Il runtime classico porta ORA intera al telefono: diciottomila token a ogni
battuta, e sei-nove secondi di silenzio in faccia a chi ha appena finito di
parlare. Funziona, ed è lei — ma non è una conversazione.

Qui parla un modello che vive fuori e che sa soltanto questa missione: mille
token, un secondo e due. Non è ORA, e non finge di esserlo. È una bocca con un
mandato preciso, e ogni volta che deve **sapere** o **decidere** qualcosa
torna a chiedere qui dentro.

    L'AUTORITÀ NON STA NELLA BOCCA.

Sei strumenti, non trentanove. Un dato si dà solo se era previsto. Una
missione si chiude solo se la controparte ha confermato, e «alle 18 abbiamo
posto» non è una conferma. Quello che è successo torna come resoconto, non
come comando: ORA lo valida, e solo allora il mondo si muove.

    L'AUDIO È UN FIUME, NON UN ARCHIVIO.

Il PCM entra da Vonage, attraversa questo file e viene dimenticato nello
stesso gesto. Non c'è un buffer che cresce, non c'è un file, non c'è un campo
nel database. Restano il testo, i tempi e i conteggi.

    E IL CLASSICO NON SI ACCORGE DI NIENTE.

Questo file non è importato da nessun altro del runtime telefonico. Ci si
arriva solo dal flag, che parte spento.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from telephone.audio import LINE_RATE, Ears, Resampler
from telephone.introduction import IntroductionLedger
from telephone.mission import (
    REFUSALS,
    CallMissionOutcome,
    CallMissionPacket,
    MissionLedger,
    an_ambiguous_reply,
    packet_for,
)
from telephone.playback import PlaybackController
from telephone.voicemail import VoicemailWatch

logger = logging.getLogger("ora.telephone.live")

LIVE_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)

# Quello che Gemini Live manda indietro. La linea ne vuole sedici: in mezzo
# c'è il ricampionatore, che lavora mentre il fiume scorre.
MODEL_RATE = 24000

# Quanto si aspetta che il modello apra bocca prima di considerarlo perso.
SETUP_TIMEOUT_S = 12

#     QUANTE VOLTE SI PROVA A RIPRENDERE, E QUANTO SI ASPETTA FRA UNA E L'ALTRA.
#
# Tre tentativi e una pausa che cresce piano. Il limite non e' prudenza
# generica: un filo che cade tre volte di fila in pochi secondi non e' un
# inciampo, e continuare a riaprirlo mentre una persona aspetta al telefono
# vuol dire farle ascoltare il silenzio piu' a lungo invece di chiudere con
# onesta'.
MAX_RESUME_ATTEMPTS = 3


def _dev_drop_after_turns() -> int:
    """
    DEV-ONLY: dopo quanti turni chiudere di proposito il filo verso Gemini.

        SPENTO DI DEFAULT, E IMPOSSIBILE IN PRODUZIONE.

    Serve a provare davvero la ripresa di sessione su una telefonata vera,
    senza aspettare che Google chiuda la sessione da solo. Vale solo se
    `ORA_DEV_DROP_LIVE_AFTER_TURNS` è un numero positivo **e** `ENVIRONMENT`
    non è `production`. Chiude soltanto il filo verso Gemini: la telefonata
    con l'operatore resta aperta, ed è esattamente il caso da provare.
    """
    if (os.environ.get("ENVIRONMENT") or "development").strip().lower() in (
            "production", "prod"):
        return 0
    try:
        return max(0, int(os.environ.get("ORA_DEV_DROP_LIVE_AFTER_TURNS") or 0))
    except ValueError:
        return 0

RESUME_BACKOFF_S = (0.2, 0.5, 1.0)

#     QUANTO SI LASCIA ALL'ALTRO PER DIRE «PRONTO».
# Chi risponde al telefono spesso parla subito, e non gli si parla sopra.
#
#     MA UNA GUARDIA CHE NON PUO' VEDERE NON E' UNA GUARDIA.
#
# Alla sesta telefonata questa finestra durava un quarto di secondo, e le
# orecchie ne chiedono mezzo per imparare quanto e alto il silenzio della
# linea: la protezione non poteva funzionare, e infatti il primo «pronto?» e
# passato inosservato. Adesso non si conta piu un tempo — si aspetta che le
# orecchie siano sveglie, e questo succede quasi subito perche mentre la
# sessione si apriva i pacchetti si accumulavano nel buffer del socket e
# arrivano tutti insieme.
LISTEN_BEFORE_OPENING_S = 0.12

# Oltre questo non si aspetta piu: meglio una guardia imperfetta che una
# telefonata muta.
WAIT_FOR_EARS_S = 0.8

# Quanta voce si mette da parte prima di cominciare a parlare. Con Gemini
# Live l'audio nasce mentre lo si versa: senza margine, la linea va a tratti.
SPEECH_CUSHION_MS = 200

#     NON SI RIAGGANCIA SU UNA LINEA CHE PARLA.
# Dopo l'ultima parola di ORA serve un tratto **continuo** di linea libera, non
# una pausa a orologio. Ottocento millisecondi: `Ears` dichiara che qualcuno
# parla dopo tre pacchetti, cioe sessanta millisecondi, quindi questa finestra
# raccoglie chiunque apra bocca entro settecentoquaranta millisecondi
# dall'ultima parola — e un turno umano normale comincia fra i duecento e i
# cinquecento. Sta anche sotto i novecento che `Ears` usa per dire che un turno
# e finito: non aspettiamo piu di quanto aspetti il resto del runtime.
QUIET_LINE_BEFORE_CLOSING_S = 0.8

#     QUANTO SI ASPETTA DOPO UN SALUTO, PRIMA DI CHIUDERE COMUNQUE.
#
# Dodici secondi. Non e' una scorciatoia sul contratto del commiato: il saluto
# c'e' stato — `goodbye_state` e' `completed` — e nessuno sta parlando. E' il
# fondo sotto al quale non si puo' cadere, perche' una telefonata che resta
# aperta dopo «arrivederci» la deve chiudere la persona, e non e' il suo
# mestiere.
HANGUP_SAFETY_S = 12.0

# Oltre questo non si aspetta piu: se la linea non e mai libera per ottocento
# millisecondi di fila, si chiude alla prima pausa utile. Una telefonata che
# non finisce mai e un altro modo di essere scortesi — e costa.
DONT_WAIT_FOREVER_S = 8.0

# Quanto si lascia al trasporto per consegnare la coda dell'audio, prima
# ancora di cominciare a guardare se la linea e libera.
GOODBYE_GRACE_S = 0.3

#     COME SUONA UN CONGEDO, NELLE NOSTRE STESSE PAROLE.
# Qui non si interpreta la controparte: si rilegge quello che abbiamo detto
# noi, per sapere se l'abbiamo detto. E' la stessa verifica di consegna che
# fa il contratto dell'apertura, dall'altro capo della telefonata.
FAREWELLS = (
    "arrivederci", "buona giornata", "buona serata", "buonasera",
    "a presto", "la saluto", "ci sentiamo", "le auguro", "buon proseguimento",
    #     A UNA PERSONA CARA SI DICE «CIAO».
    # Misurato sul vero (V3.21.1a): ORA ha salutato Asia con «Ciao!», il
    # congedo non è stato riconosciuto, e le sono stati chiesti altri tre
    # saluti — «Arrivederci», «Buona giornata», «Arrivederci!».
    "ciao",
)

# Quante volte si chiede a chi parla di congedarsi prima di lasciar perdere.
# Oltre, non e' piu' educazione: e' un telefono che non si chiude.
MAX_GOODBYE_NUDGES = 2

# Quante volte al massimo si ricorda a chi parla che l'apertura è incompleta.
# Oltre, non è più un promemoria: è una persona che si ripete.
MAX_INTRODUCTION_NUDGES = 2


#     IL PROMPT DI SESSIONE È CORTO PERCHÉ NON È ORA.
# Duecentoquaranta token. Non descrive una personalità, non elenca strumenti,
# non racconta una vita: dice che cosa si può fare in questa telefonata e dove
# finisce il mandato. Tutto il resto arriva col pacchetto.
SESSION_PROMPT = """Sei la voce di ORA per questa singola telefonata, e per nessun'altra.

Non hai una missione generale: hai quella descritta qui sotto. Tutto quello che sai è nel pacchetto; se ti serve altro, chiedilo con gli strumenti — non inventarlo e non dedurlo.

Regole, in ordine di importanza:
- La prima frase è say_this_first, detta per intera. Sei l'assistente della persona per cui chiami: non sei quella persona, e non dire mai di esserlo. Se ti interrompono mentre ti presenti, non ricominciare da capo: completa solo quello che manca al primo momento naturale.
- Non allargare la missione. Se emerge una decisione che non è in allowed_negotiation, non accettarla: chiedi conferma a chi ti ha mandato e aspetta.
- Una porta chiusa con un'altra porta aperta accanto non è un fallimento. Se ti dicono di no ma ti propongono un'altra data o un altro orario, quella proposta è la cosa più utile della telefonata: riportala con request_user_confirmation, scritta per intero. Non accettarla tu e non buttarla via. fail_mission è solo per quando non c'è niente e non ci sarà.
- Prima di salutare, dì che cosa farai: che riporterai la proposta e che vi risentirete. Non chiudere su «devo chiedere conferma» senza spiegare.
- Non dire di aver concluso finché la controparte non l'ha confermato con parole sue. Che ci sia posto non vuol dire che sia stato spostato.
- Non rivelare niente che non sia in known_facts. Se ti chiedono un dato che non hai, chiedilo con lo strumento apposito: potrebbe esserti negato, e va bene così.
- Non nominare mai strumenti, sistemi, autorizzazioni o il fatto che stai consultando qualcosa.
- Parla come una persona al telefono: frasi brevi, tono professionale, niente elenchi.
- Fai una domanda alla volta. Con due domande nella stessa frase un «no» non si sa a quale risponde.
- Se risponde una segreteria o un messaggio registrato, non lasciare messaggi e non dire perché chiami: chiudi la missione come non raggiunta."""


#     SEI STRUMENTI, E L'ELENCO È CHIUSO.
# ORA ne ha trentanove. Nessuno di quelli arriva qui: quello che passa di qui
# è soltanto quello che serve a condurre una trattativa e a tornare indietro
# con un resoconto che qualcun altro validerà.
THE_SIX: List[Dict[str, Any]] = [{
    "function_declarations": [
        {
            "name": "get_call_context",
            "description": "Chiedi un dato della missione che non hai nel pacchetto.",
            "parameters": {
                "type": "object",
                "properties": {"field": {"type": "string"}},
                "required": ["field"],
            },
        },
        {
            "name": "get_allowed_alternatives",
            "description": "Chiedi quali alternative puoi accettare in linea.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "request_user_confirmation",
            "description": (
                "USA QUESTO quando la controparte ti mette sul tavolo "
                "un'alternativa che non sta nelle tue possibilita'. "
                "«Alle 18 no, ma posso domani alle 11» e' questo caso, non un "
                "fallimento: la commissione si ferma e aspetta una decisione, "
                "e quella proposta vale — qualcuno la accettera' o ne "
                "proporra' un'altra. Non accettarla tu, e non buttarla via."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": (
                            "Perche' ti sei dovuto fermare, in una riga, come "
                            "lo diresti a una persona. Es. «Lo studio non "
                            "puo' alle 18:00.»"
                        ),
                    },
                    "proposal": {
                        "type": "string",
                        "description": (
                            "Che cosa hanno proposto, con le loro parole "
                            "tradotte in date e orari. Es. «Propone domani "
                            "alle 11:00.» Vuoto solo se non hanno proposto "
                            "niente."
                        ),
                    },
                    "proposed_date": {
                        "type": "string",
                        "description": (
                            "La stessa proposta come data: AAAA-MM-GG. "
                            "Serve a chi dovra' decidere: una frase non si "
                            "puo' confrontare con un calendario."
                        ),
                    },
                    "proposed_time": {
                        "type": "string",
                        "description": "La stessa proposta come ora: HH:MM.",
                    },
                },
                "required": ["reason"],
            },
        },
        {
            "name": "record_call_fact",
            "description": (
                "Annota una frase della controparte che sposta la trattativa: "
                "quando ti dicono che c'è posto, quando propongono loro "
                "un'alternativa, quando rifiutano. La conferma finale non "
                "annotarla qui: portala dentro complete_mission."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["availability", "proposal", "confirmation",
                                 "refusal", "detail"],
                        "description": (
                            "availability: c'è posto, si potrebbe fare. "
                            "proposal: propongono loro un'alternativa precisa. "
                            "confirmation: hanno registrato la modifica, è "
                            "fatta. refusal: no. detail: altro. "
                            "Nel dubbio fra availability e confirmation "
                            "scegli availability."
                        ),
                    },
                    "field": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["kind", "value"],
            },
        },
        {
            "name": "complete_mission",
            "description": "La controparte ha confermato: la missione è compiuta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmed_changes": {
                        "type": "object",
                        "description": (
                            "Cosa ha confermato la controparte, con le sue "
                            "parole tradotte in date e orari."
                        ),
                        "properties": {
                            "appointment_date": {
                                "type": "string", "description": "AAAA-MM-GG",
                            },
                            "old_time": {"type": "string", "description": "HH:MM"},
                            "new_time": {"type": "string", "description": "HH:MM"},
                        },
                        "required": ["appointment_date", "new_time"],
                    },
                    "confirmation": {
                        "type": "string",
                        "description": (
                            "Le parole con cui la controparte ha detto che la "
                            "modifica è REGISTRATA, non che ci sarebbe posto. "
                            "Se non te l'hanno ancora detto, chiediglielo "
                            "prima di chiudere."
                        ),
                    },
                    "notes": {"type": "string"},
                },
                "required": ["confirmed_changes", "confirmation"],
            },
        },
        {
            "name": "fail_mission",
            "description": (
                "SOLO quando non c'e' niente sul tavolo e non ci sara'. "
                "Hanno detto di no e basta, non rispondono, non e' il posto "
                "giusto. Se invece ti hanno proposto un'altra data o un altro "
                "orario, quella non e' una missione fallita: e' una decisione "
                "che non spetta a te — usa request_user_confirmation."
            ),
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    ]
}]

def tools_for(mission_type: str) -> List[Dict[str, Any]]:
    """
    Gli stessi sei strumenti, con la domanda giusta dentro `complete_mission`.

        CHE COSA SIA UNA CONFERMA CAMBIA CON LA MISSIONE.

    Per uno spostamento e' «a che ora l'ha messo»; per una disdetta e' «quale
    ha tolto»; per una prenotazione e' «quando me l'ha fissato». Chiedere le
    tre cose con lo stesso schema vorrebbe dire chiedere un `new_time` a chi
    ha appena disdetto — e un campo obbligatorio che non ha senso si riempie
    comunque, con qualcosa.

    Gli strumenti restano sei e i loro nomi non cambiano: cambia solo la forma
    di cio' che si riporta indietro.
    """
    if mission_type == "deliver_message":
        #     LO STESSO FALLIMENTO, LA STESSA DOMANDA: IL RESTO E' DIVERSO.
        # Si tengono `get_call_context`, `request_user_confirmation` e
        # `fail_mission`; `complete_mission` no — non c'è niente da farsi
        # confermare — e al suo posto vengono i tre della consegna.
        tenuti = [
            f for f in THE_SIX[0]["function_declarations"]
            if f["name"] in ("get_call_context", "request_user_confirmation",
                             "fail_mission")
        ]
        return [{"function_declarations": [*DELIVERY_TOOLS, *tenuti]}]
    campi = _WHAT_A_CONFIRMATION_LOOKS_LIKE.get(mission_type)
    if not campi:
        return THE_SIX
    attrezzi = []
    for f in THE_SIX[0]["function_declarations"]:
        if f["name"] != "complete_mission":
            attrezzi.append(f)
            continue
        su_misura = json.loads(json.dumps(f))
        su_misura["parameters"]["properties"]["confirmed_changes"] = campi
        attrezzi.append(su_misura)
    return [{"function_declarations": attrezzi}]


#     TRE MISSIONI, TRE COSE DA FARSI CONFERMARE.
# Lo spostamento sta scritto in `THE_SIX` ed e' il caso di riposo; questi due
# lo sostituiscono quando la missione e' un'altra.
_WHAT_A_CONFIRMATION_LOOKS_LIKE: Dict[str, Dict[str, Any]] = {
    "cancel": {
        "type": "object",
        "description": (
            "Quale appuntamento la controparte ha detto di aver DISDETTO. "
            "Non un orario nuovo: non ce n'e' uno."
        ),
        "properties": {
            "appointment_date": {"type": "string", "description": "AAAA-MM-GG"},
            "appointment_time": {
                "type": "string",
                "description": "HH:MM, l'ora dell'appuntamento tolto",
            },
        },
        "required": ["appointment_date", "appointment_time"],
    },
    "book": {
        "type": "object",
        "description": (
            "Il giorno e l'ora che la controparte ha detto di aver FISSATO, "
            "con le sue parole tradotte in date e orari."
        ),
        "properties": {
            "appointment_date": {"type": "string", "description": "AAAA-MM-GG"},
            "appointment_time": {"type": "string", "description": "HH:MM"},
            "duration_minutes": {
                "type": "string",
                "description": "Quanto dura, in minuti, solo se l'hanno detto",
            },
        },
        "required": ["appointment_date", "appointment_time"],
    },
}

#     QUATTRO STRUMENTI PER PORTARE UN MESSAGGIO.
#
# Una consegna non ha niente da farsi confermare: ha una persona da trovare,
# una frase da dire, e una risposta da ascoltare. Gli strumenti di chi sposta
# appuntamenti qui chiederebbero date a chi sta dicendo «ti amo».
DELIVERY_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "recipient_confirmed",
        "description": (
            "Chiamalo SOLO quando dall'altra parte c'e' davvero la persona a "
            "cui devi il messaggio: l'ha detto lei («sì, sono io», «sono "
            "Giulia»). Ti restituisce il messaggio da consegnare — prima non "
            "lo conosci, ed e' voluto. Se risponde qualcun altro, NON "
            "chiamarlo: usa recipient_not_available."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "how_they_confirmed": {
                    "type": "string",
                    "description": "Le parole con cui ha detto di essere lei.",
                },
            },
            "required": ["how_they_confirmed"],
        },
    },
    {
        "name": "recipient_not_available",
        "description": (
            "Ha risposto qualcun altro, o non sei riuscita a parlare con la "
            "persona giusta. Non dire niente del messaggio: puoi chiedere se "
            "c'e' o quando richiamare."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "who_answered": {
                    "type": "string",
                    "enum": ["someone_else", "not_sure", "voicemail"],
                },
                "callback_hint": {
                    "type": "string",
                    "description": "Se hanno detto quando richiamare, con le loro parole.",
                },
            },
            "required": ["who_answered"],
        },
    },
    {
        "name": "message_delivered",
        "description": (
            "Hai detto il messaggio alla persona giusta. Riporta con le sue "
            "parole quello che ha risposto, anche se e' solo un «grazie». Se "
            "ti ha chiesto qualcosa che non puoi decidere tu, non rispondere "
            "per lui: di' che glielo riferirai, e mettilo qui."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recipient_reply": {
                    "type": "string",
                    "description": (
                        "Quello che ha voluto far sapere indietro, con le sue "
                        "parole. Es. «Digli che lo amo anch'io.»"
                    ),
                },
                "notes": {"type": "string"},
            },
            "required": ["recipient_reply"],
        },
    },
]

ALLOWED_TOOLS = frozenset(
    f["name"] for f in THE_SIX[0]["function_declarations"]
)


def tools_allowed_for(mission_type: str) -> frozenset:
    """
    Gli strumenti che questa telefonata può chiamare: quelli che le si offrono.

        L'ELENCO E' CHIUSO, E DIPENDE DA CHE COSA SI STA FACENDO.

    Una consegna non può chiudere con `complete_mission`, e uno spostamento
    non può chiedere il messaggio di un altro.
    """
    return frozenset(
        f["name"] for f in tools_for(mission_type)[0]["function_declarations"]
    )


def live_is_configured() -> str:
    """Perché non si può usare questo runtime, o stringa vuota."""
    if not _key():
        return "manca la chiave Gemini"
    if not _model():
        return "manca GEMINI_LIVE_MODEL"
    return ""


#     DUE CHIAVI, UNA PREFERENZA FISSA, E NESSUNA RELAZIONE COL RESTO.
#
# Questa scelta non guarda lo stato dei fornitori: `gemini2` viene prima
# sempre, anche quando il manager LLM ha appena messo `gemini` in castigo per
# quota. Sono due sottosistemi diversi che condividono solo un prefisso nel
# nome delle variabili, e confonderli porta a cercare la causa dove non e'.
_SLOTS = (("gemini2", "GEMINI2_API_KEY"), ("gemini", "GEMINI_API_KEY"))


def _key_slot() -> str:
    """Quale credenziale apre il filo. Il nome, mai il valore."""
    for nome, dove in _SLOTS:
        if (os.environ.get(dove) or "").strip():
            return nome
    return ""


def _key() -> str:
    for _nome, dove in _SLOTS:
        chiave = (os.environ.get(dove) or "").strip()
        if chiave:
            return chiave
    return ""


def _model() -> str:
    return (os.environ.get("GEMINI_LIVE_MODEL") or "").strip()


#     ORA HA UNA VOCE, E NON DIPENDE DA CHI PAGA IL FILO.
#
# Charon. Scelta ascoltandola, non leggendo una tabella. Sta qui come valore
# di riposo perche' una sessione aperta senza `speechConfig` prende la voce
# predefinita del modello — che e' un'altra — e su una telefonata vera si e'
# sentito: la voce e' cambiata a meta' e nessun campo poteva smentirlo.
#
# Dipende dalla configurazione di ORA e da nient'altro: stessa voce sul
# primario, sul secondario, e su ogni sessione riaperta per riprendere una
# telefonata caduta.
THE_VOICE = "Charon"


def _voice() -> str:
    """Quale voce. Senza configurazione, la sua."""
    return (os.environ.get("GEMINI_LIVE_VOICE") or "").strip() or THE_VOICE


# I messaggi del server che sappiamo leggere. Tutto il resto viene contato per
# nome, cosi' un messaggio nuovo non passa piu' inosservato.
_WHAT_WE_KNOW = frozenset({
    "setupComplete", "serverContent", "toolCall", "toolCallCancellation",
    "usageMetadata", "goAway", "sessionResumptionUpdate",
})


def _just_the_shape(qualcosa) -> Any:
    """
    La forma di un messaggio, mai il contenuto.

    Le chiavi e i tipi bastano a capire che cosa e' arrivato; il testo dentro
    puo' portare parole di una telefonata, e quelle non si registrano.
    """
    if isinstance(qualcosa, dict):
        return {k: type(v).__name__ for k, v in qualcosa.items()}
    return type(qualcosa).__name__


def _when_it_is_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _how_she_sounds() -> Dict[str, Any]:
    """
    Come suona, se qualcuno l'ha deciso.

        UNA VOCE NON SI SCEGLIE DA SOLI.

    Senza `GEMINI_LIVE_VOICE` non si manda nessuna preferenza e il modello usa
    la sua — che e' esattamente il comportamento di prima, quindi cambiare
    questo file non cambia come parla finche' qualcuno non lo chiede.
    """
    #     NESSUNA SESSIONE PARTE SENZA DIRE COME DEVE SUONARE.
    # `_voice()` non torna mai vuoto, quindi questo ramo non ha un altro lato:
    # e' deliberato. Una sessione senza `speechConfig` e' una sessione con una
    # voce che non abbiamo scelto noi.
    return {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": _voice()}},
        },
    }


#     QUANTO SILENZIO ASPETTA GEMINI PRIMA DI DIRE «HA FINITO».
#
# Misurato su Gemini vero, senza telefono, con la stessa battuta rimandata a
# una sessione Live: col default del server la risposta arriva in 1781 ms
# (mediana), con 700 ms di silenzio in 1495, con 500 in 1182. Sotto non
# migliora e diventa instabile — e rischia di parlare sopra a chi fa una
# pausa. Cinquecento, e regolabile senza toccare il codice.
DEFAULT_SILENCE_MS = 500
SILENCE_MS_BOUNDS = (300, 2000)


def _silence_ms() -> int:
    """La soglia di fine turno, entro limiti sensati."""
    import os

    try:
        valore = int(os.environ.get("GEMINI_LIVE_SILENCE_MS") or DEFAULT_SILENCE_MS)
    except ValueError:
        valore = DEFAULT_SILENCE_MS
    basso, alto = SILENCE_MS_BOUNDS
    return max(basso, min(alto, valore))


def _when_a_turn_ends() -> Dict[str, Any]:
    """
    Il rilevatore di fine turno di Gemini, detto esplicitamente.

    Campi verificati sul server vero: un campo inventato viene rifiutato con
    «Cannot find field», questi no. `END_SENSITIVITY_HIGH` è già il default
    per Gemini Live — lo si scrive per non dipendere da un default che cambia.
    """
    return {
        "endOfSpeechSensitivity": "END_SENSITIVITY_HIGH",
        "silenceDurationMs": _silence_ms(),
    }


# Sotto quanto rumore dieci millisecondi di voce generata sono silenzio. In
# unità del campione a 16 bit: la voce di Charon sta sopra il migliaio.
SILENT_BELOW = 120
# Quanto silenzio dentro una generazione merita di essere segnato. Una pausa
# fra due frasi dura poco; mezzo secondo di niente in mezzo a una frase no.
SILENCE_WORTH_NOTING_MS = 400
# Quanto deve fermarsi il processo per chiamarlo fermo. Sotto, è normale.
LOOP_STALL_MS = 50
# Da quanto deve essere fermo perché valga la pena guardare chi lo tiene.
STALL_WORTH_A_NAME_S = 0.15
# Quanto silenzio dopo una frase basta a dire che la frase è finita, quando
# Gemini risponde prima delle nostre orecchie. Sotto, è una pausa.
QUIET_MEANS_DONE_MS = 150


#     QUANTE TELEFONATE STANNO PARLANDO ADESSO.
# Serve a chi fa lavoro di sfondo nello stesso processo per sapere quando
# aspettare: una lettura di rete che ferma l'event loop per mezzo secondo è
# innocua a telefono spento e uno strappo nella voce a telefono acceso.
_IN_CORSO: set = set()


def calls_in_progress() -> int:
    """Quante sessioni vocali sono aperte in questo momento."""
    return len(_IN_CORSO)


class MissionVoiceSession:
    """
    Una telefonata, una sessione, un mandato.

        UNA CHIAMATA È UNA SESSIONE, NON UNA SEQUENZA DI SESSIONI.

    Aprire un socket per ogni battuta costerebbe ottocento millisecondi a
    turno e butterebbe via il contesto ogni volta: la controparte si
    ritroverebbe a parlare con qualcuno che ha dimenticato la frase di prima.
    Si apre una volta, si tiene aperta, e si chiude quando la linea cade.

    Espone lo stesso contratto del runtime classico — `open`, `hear`, `close`,
    `how_it_went` — perché chi sta sopra non deve sapere quale dei due sta
    parlando.
    """

    def __init__(
        self,
        db,
        *,
        owner_id: str,
        session_ref: str,
        send: Callable[[bytes], Awaitable[None]],
        clear_transport: Optional[Callable[[], Awaitable[None]]] = None,
        on_said: Optional[Callable[[str, str], Awaitable[None]]] = None,
        dossier=None,
        call=None,
        packet: Optional[CallMissionPacket] = None,
        binding=None,
        connect=None,
    ) -> None:
        self.db = db
        self.owner_id = owner_id
        self.session_ref = session_ref
        self.on_said = on_said
        self.dossier = dossier
        self.call = call

        #     IL LEGAME NON PARLA, MA FA PARLARE MEGLIO.
        # Serve dopo, per applicare l'esito — ma porta anche una cosa che
        # serve adesso: a che ora e' l'appuntamento. Senza, la missione diceva
        # «sposta la visita» senza sapere da quando, e chi telefonava doveva
        # farselo dire dallo studio. L'identificativo dell'evento resta qui e
        # non entra nel packet: quello non si pronuncia.
        self.binding = binding
        self.packet = packet or (
            packet_for(call, dossier, binding=binding)
            if (call is not None and dossier is not None) else None
        )
        self.mission = MissionLedger(
            self.packet.mission_type if self.packet is not None else "reschedule"
        )
        self.intro = (
            IntroductionLedger(self.packet.introduction)
            if self.packet is not None and self.packet.introduction is not None
            else None
        )

        #     QUI LA VOCE NASCE MENTRE SI VERSA.
        # Duecento millisecondi di margine prima di aprire bocca. Costano
        # duecento millisecondi; senza, la coda resta a secco all'inizio di
        # ogni risposta e dall'altra parte si sente una voce che va a tratti,
        # «come se non ci fosse linea». E' un cambio che vale solo qui: al
        # runtime classico la frase arriva gia fatta.
        self.playback = PlaybackController(
            send=send, clear_transport=clear_transport,
            jitter_ms=SPEECH_CUSHION_MS,
            #     IL METRONOMO NON E' NOSTRO: E' DELLA LINEA.
            # `asyncio.sleep(20 ms)` su questo host ne dorme trentuno. La
            # cadenza dei pacchetti in arrivo da Vonage invece e' quella della
            # rete telefonica — misurata su tre chiamate vere: 49,1 · 49,4 ·
            # 49,1 al secondo contro 50 teorici, silenzi compresi.
            external_clock=True,
        )
        self._down = Resampler(src=MODEL_RATE, dst=LINE_RATE)
        #     CHI DECIDE I TURNI E GEMINI. CHI TIENE IL TEMPO SIAMO NOI.
        # Queste orecchie non comandano niente: non aprono bocca, non chiudono
        # turni, non interrompono. Servono a sapere **quando** la controparte
        # ha smesso di parlare, che e l'unico punto da cui ha senso far partire
        # il cronometro. Attaccato alla fine del turno di ORA misurava anche i
        # tre secondi in cui parlava lo studio, e dava 4.780 ms per una
        # risposta che ne aveva messi mille.
        self._ears = Ears()

        # Chi apre il filo. Iniettabile: una prova non deve chiamare Google.
        self._connect = connect
        self.ws = None
        self._pump: Optional[asyncio.Task] = None
        self._closed = False

        # --- quello che raccontiamo dopo ----------------------------------
        self._opened_at = 0.0
        self._ready_ms: Optional[int] = None
        self._turn = 0
        self._speech_ended_at: Optional[float] = None
        self._first_audio: List[int] = []
        self._intro_ms: Optional[int] = None
        self._tool_ms: List[int] = []
        self._resample_ms: List[float] = []
        self._barge_ins: List[int] = []
        self._tool_calls = 0
        self._refused_tools = 0
        self._tokens: Dict[str, int] = {}
        # Quello che il server ha annunciato durante la telefonata, e i nomi
        # dei messaggi che non sappiamo ancora leggere. Nessun contenuto:
        # solo la forma, per poter dire dopo che cosa e' passato di qui.
        self._server_said: List[Dict[str, Any]] = []
        self._server_unknown: set = set()
        self._trace: Dict[str, Any] = {}

        # --- riprendere una telefonata a cui e' caduto il filo -------------
        #
        #     L'APPIGLIO VALE PER QUESTA TELEFONATA E BASTA.
        #
        # Non e' una cache e non si condivide: nasce con la sessione, muore
        # con lei, e serve a dire al server «sono sempre quella di prima».
        self._resume_handle = ""
        self._connection_index = 0
        self._connections: List[Dict[str, Any]] = []
        self._resumption_updates = 0
        self._go_away_count = 0
        self._go_away_time_left = ""
        self._must_resume = ""
        self._resuming = False
        self._resume_attempts = 0
        self._resumes_done = 0
        # Perché si apre la prossima connessione: vuoto la prima volta.
        self._next_connection_reason = ""
        self._dev_drop_after = _dev_drop_after_turns()
        self._dev_dropped = False
        self._reconnect_ms: List[int] = []
        self._reconnect_reasons: List[str] = []
        self._closed_reasons: List[str] = []
        # Perche' la telefonata si e' fermata per colpa del trasporto, se e'
        # successo. Vuoto e' il caso normale, ed e' quello che permette a un
        # esito di esistere.
        self._transport_failure = ""
        self._speaking = None
        self._said_this_turn: List[str] = []
        self._heard_this_turn: List[str] = []
        #     SE IL BUCO ARRIVA DA MONTE, NESSUN CUSCINETTO LO CHIUDE.
        # Quanto passa fra un pezzo d'audio e il successivo **in arrivo** da
        # chi parla. Se qui ci sono gli stessi buchi che si sentono sulla
        # linea, il problema non e la nostra coda: e' che l'audio non arriva.
        self._gemini_gaps_ms: List[float] = []
        self._gemini_gap_at_ms: List[int] = []
        # Ogni buco in arrivo sopra i cento millisecondi, con quanta voce
        # c'era ancora in coda quando è finito: se ce n'era più del buco, la
        # linea non l'ha sentito.
        self._gemini_gap_events: List[Dict[str, Any]] = []
        # Silenzi lunghi *dentro* la voce generata: lì il buco è nell'audio,
        # non nel trasporto.
        self._generated_silences: List[Dict[str, Any]] = []
        self._silent_run_ms = 0
        self._voiced_in_generation = False
        # Quando il processo si è fermato, e per quanto.
        self._loop_stalls: List[Dict[str, Any]] = []
        self._clock_watch: Optional[asyncio.Task] = None
        # Chi teneva fermo il processo, fotografato mentre lo teneva fermo.
        self._stall_culprits: List[Dict[str, Any]] = []
        self._loop_heartbeat = time.perf_counter()
        self._loop_thread_id: Optional[int] = None
        self._answered_before_our_ears = False
        # Se la persona giusta ha detto di essere lei. Fino ad allora il
        # messaggio non esce dal server.
        self._recipient_ok = False
        # Se chi risponde ha gia' detto chi e' — lei, qualcun altro, una
        # segreteria. Da li' in poi la domanda d'identita' non si rifa'.
        self._identity_settled = False
        # Quello che la controparte ha detto nell'ultimo turno chiuso, e quante
        # chiusure sono state respinte perché rispondevano a due domande
        # insieme. Si respinge al massimo due volte: poi decide chi parla.
        self._their_last_words = ""
        self._ambiguity_refusals = 0
        #     PERSONA O SEGRETERIA: SI DICE SOLO CON DUE SEGNALI.
        self._voicemail = VoicemailWatch()
        self._voicemail_handled = False
        # La lingua che è scivolata, turno per turno.
        self._drift: List[Dict[str, Any]] = []
        self._last_chunk_at = 0.0
        self._chunks_in = 0
        self._responses: List[Dict[str, Any]] = []
        self._this_response: Optional[Dict[str, Any]] = None
        # L'interruzione, pezzo per pezzo: quando l'abbiamo sentita noi,
        # quando l'ha detto Gemini, quando la bocca si e chiusa davvero.
        self._heard_them_start_at = 0.0
        #     IL PRIMO NON E' L'ULTIMO, E LA TELEMETRIA NON DEVE DIRLO.
        # `first_human_onset_at_ms` riportava l'ultimo inizio di parlato, non
        # il primo: un numero che significa una cosa diversa da come si chiama
        # e peggio di un numero assente, perche qualcuno ci crede.
        self._first_human_onset: Optional[float] = None
        self._barge: List[Dict[str, Any]] = []
        #     IL BATTITO NASCE QUI, E QUI PUO' ARRIVARE TARDI.
        # `hear` fa base64, JSON e una send verso Gemini per ogni pacchetto
        # che arriva dalla linea. Se quella send rallenta, il router smette di
        # leggere e i battiti non arrivano — e nessun credito puo inventarli.
        # Questi tre numeri dicono se sta succedendo, e dove.
        self._hear_total_ms: List[float] = []
        self._to_credit_ms: List[float] = []
        self._gemini_send_ms: List[float] = []
        self._inbound_gap_ms: List[float] = []
        self._last_inbound = 0.0
        #     SE SULLA LINEA NON C'E' MAI STATA UNA VOCE, IL COLPEVOLE E' IL FILO.
        # La quinta chiamata e arrivata muta: 1289 trame entrate, zero risposte
        # da Gemini. Con l'audio che non si conserva non si puo tornare
        # indietro a sentire se dentro quelle trame ci fosse qualcuno. Questi
        # due numeri lo dicono senza conservare niente: quante volte le
        # orecchie hanno sentito partire una voce, e quanto era alto il fondo.
        self._speech_onsets = 0
        self._loudest = 0.0
        #     NOT_STARTED · SPEAKING · INTERRUPTED · IDENTITY_PENDING · COMPLETED.
        # «Compiuta» non vuol dire «chiesta»: lo diventa solo quando il
        # registro dell'apertura ha sentito uscire tutt'e due le cose che
        # devono uscire — di chi siamo l'assistente, e perche chiamiamo.
        # Per una consegna c'e' un passo in piu': «Parlo con Asia?» e' detto,
        # ma finche' non ha risposto chi e', l'apertura aspetta l'identita'.
        self._opening = "not_started"
        self._opening_task: Optional[asyncio.Task] = None
        self._opening_deferred = 0
        self._answered_at: Optional[float] = None
        self._live_ready_at: Optional[float] = None
        self._opening_requested_at: Optional[float] = None
        self._opening_first_gemini_at: Optional[float] = None
        self._opening_first_line_at: Optional[float] = None
        self._opening_completed_at: Optional[float] = None
        self._ears_ready_at: Optional[float] = None
        #     NOT_STARTED · PENDING · SPEAKING · COMPLETED · INTERRUPTED
        # La missione e' un fatto, la chiusura e' un'intenzione, e il congedo
        # e' un atto: deve succedere, e finche non e' successo non si chiude.
        self._goodbye = "not_started"
        self._goodbye_story: List[str] = ["not_started"]
        self._goodbye_interrupted = 0
        self._hangup_attempts = 0
        self._blocked_by_goodbye = 0
        self._blocked_by_human = 0
        self._goodbye_nudges = 0
        self._goodbye_at: Optional[float] = None
        self._last_words = ""
        self.outcome: Optional[CallMissionOutcome] = None
        #     LA MISSIONE E' UN FATTO. LA CHIUSURA E' UN'INTENZIONE.
        # Il primo non si revoca: quello che la controparte ha confermato
        # resta confermato. La seconda sì, e la revoca chiunque apra bocca
        # mentre stiamo per chiudere.
        self._mission_terminal_at: Optional[float] = None
        self._call_closing = "open"        # open · pending · closed
        self._hung_up = False
        self._closing_watch: Optional[asyncio.Task] = None
        # Quello che si raccontera dopo su come e finita.
        self._playback_finished_at: Optional[float] = None
        self._close_candidate_at: Optional[float] = None
        self._hangup_at: Optional[float] = None
        self._human_after_terminal = 0
        self._close_window_resets = 0
        self._final_quiet_ms: Optional[int] = None
        self._hangup_while_human_speaking = 0
        # Quante volte la sorveglianza della chiusura e' stata rimessa in piedi
        # dopo che qualcosa l'aveva annullata, e quante volte si e' chiuso per
        # scadenza invece che su una linea libera. Due spie, non due modi.
        self._closing_rearms = 0
        # Quante volte chi parla ha provato a dire qualcosa dopo il saluto.
        # Zero e' il caso normale; un numero alto vuol dire che il commiato
        # non sta chiudendo niente.
        self._words_after_goodbye = 0
        self._closed_by_safety_net = 0
        self._hangup_task: Optional[asyncio.Task] = None

    # --- aprire -----------------------------------------------------------

    async def open(self) -> bool:
        """Apre il filo verso chi parlerà, e lo prepara con la missione."""
        if self.packet is None:
            logger.info("nessuna missione: il runtime a missione non si apre")
            return False
        perche_no = live_is_configured()
        if perche_no:
            logger.info("runtime a missione non configurato: %s", perche_no)
            return False

        self._opened_at = time.perf_counter()
        if not await self._connect_once(resume_handle=""):
            await self.close()
            return False

        self._ready_ms = int((time.perf_counter() - self._opened_at) * 1000)
        self._answered_at = self._opened_at
        self._live_ready_at = time.perf_counter()
        self._pump = asyncio.create_task(self._listen_to_the_model())
        self._clock_watch = asyncio.create_task(self._watch_the_clock())
        _IN_CORSO.add(id(self))
        #     ADESSO CI SONO TUTTE E QUATTRO: SI PUO' PARLARE.
        # La linea ha risposto, il filo media e' aperto, la sessione e' pronta
        # e la coda verso il trasporto anche. Prima di questo punto parlare
        # vorrebbe dire parlare sopra uno squillo.
        self._opening_task = asyncio.create_task(self._say_the_first_line())
        logger.info("runtime a missione pronto in %d ms", self._ready_ms)
        return True

    async def _watch_the_clock(self) -> None:
        """
        Se il processo si ferma, lo si scrive.

            UN BUCO NELLA VOCE CON LA CODA PIENA HA UN SOLO SOSPETTO.

        Sul gate V3.20 la voce si è fermata due volte per più di un secondo
        con otto secondi di audio pronti. Se in quel momento l'event loop era
        fermo, lo si vede qui. Un sonno di venti millisecondi che ne dura
        trecento è un processo che per duecentottanta non ha fatto altro.
        """
        passo = 0.02
        import threading

        self._loop_thread_id = threading.get_ident()
        testimone = threading.Thread(
            target=self._witness_the_stalls, name="ora-stall-witness", daemon=True,
        )
        testimone.start()
        try:
            while not self._closed:
                prima = time.perf_counter()
                self._loop_heartbeat = prima
                await asyncio.sleep(passo)
                fermo = (time.perf_counter() - prima - passo) * 1000
                if fermo > LOOP_STALL_MS and len(self._loop_stalls) < 60:
                    self._loop_stalls.append({
                        "at_ms": int((prima - self._opened_at) * 1000),
                        "stall_ms": round(fermo, 1),
                    })
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover
            pass

    def _witness_the_stalls(self) -> None:
        """
        Un thread che guarda l'event loop da fuori, e quando è fermo lo fotografa.

            SAPERE CHE SI È FERMATO NON BASTA: SERVE SAPERE CHI LO TENEVA.

        Il cane da guardia dentro il loop vede lo stallo solo quando è finito,
        e a quel punto il colpevole se n'è andato. Da fuori invece lo si vede
        mentre succede: si legge lo stack del thread del loop e si scrive dove
        era — una volta per stallo, e solo sopra i centocinquanta millisecondi.
        """
        import sys as _sys
        import traceback

        gia_visto = 0.0
        while not self._closed and len(self._stall_culprits) < 10:
            time.sleep(0.05)
            battito = self._loop_heartbeat
            fermo = time.perf_counter() - battito
            if fermo < STALL_WORTH_A_NAME_S or battito == gia_visto:
                continue
            gia_visto = battito
            quadro = _sys._current_frames().get(self._loop_thread_id or 0)
            if quadro is None:
                continue
            pila = traceback.extract_stack(quadro)
            nostri = [f for f in pila if "DANGEROK" in f.filename
                      and "site-packages" not in f.filename]
            self._stall_culprits.append({
                "at_ms": int((battito - self._opened_at) * 1000),
                "idle_ms_when_seen": int(fermo * 1000),
                "our_code": [f"{f.filename.rsplit(chr(92), 1)[-1].rsplit('/', 1)[-1]}:"
                             f"{f.lineno} {f.name}" for f in nostri[-3:]],
                "deepest": f"{pila[-1].filename.rsplit(chr(92), 1)[-1].rsplit('/', 1)[-1]}:"
                           f"{pila[-1].lineno} {pila[-1].name}" if pila else "",
            })

    # --- il fiume che entra -----------------------------------------------

    async def hear(self, pcm: bytes) -> None:
        """
        Venti millisecondi di linea, passati e dimenticati.

        Vonage parla già a sedicimila, che è il passo che si aspetta chi
        ascolta: in questa direzione non c'è niente da ricampionare, e non
        aggiungere un passaggio è il modo più sicuro di non aggiungere ritardo.
        """
        if self._closed or self.ws is None or not pcm:
            return
        entrato = time.perf_counter()
        #     MENTRE SI RIAPRE IL FILO, QUESTI VENTI MILLISECONDI SI PERDONO.
        #
        # E vanno persi. Accodarli vorrebbe dire, un secondo dopo, mandare a
        # chi parla un pezzo di conversazione vecchio di un secondo — e far
        # rispondere a una frase che l'altra persona ha gia' finito di dire.
        # Il credito invece si prende comunque, qualche riga piu' sotto: il
        # metronomo della linea non si ferma perche' si e' fermato il nostro.
        _ripresa_in_corso = self._resuming
        if self._last_inbound:
            # Ogni quanto la linea riesce davvero a parlarci. Se qui compaiono
            # trenta millisecondi invece di venti, il collo di bottiglia sta
            # prima di noi: nel giro di lettura del trasporto.
            self._inbound_gap_ms.append(
                round((entrato - self._last_inbound) * 1000, 1)
            )
        self._last_inbound = entrato

        #     PRIMA IL CREDITO, POI TUTTO IL RESTO.
        # Il battito e' la prima cosa che succede qui dentro, apposta: non
        # deve aspettare ne le orecchie ne la send verso Gemini.
        self.playback.tick()
        self._to_credit_ms.append(
            round((time.perf_counter() - entrato) * 1000, 3)
        )
        try:
            from telephone.audio import loudness

            quanto = loudness(pcm)
            if quanto > self._loudest:
                self._loudest = quanto
            ha_cominciato, ha_finito = self._ears.hear(pcm)
            if ha_cominciato:
                self._answered_before_our_ears = False
                self._speech_onsets += 1
                self._heard_them_start_at = time.perf_counter()
                if self._first_human_onset is None:
                    # Si scrive una volta sola, per tutta la telefonata.
                    self._first_human_onset = self._heard_them_start_at
                if self._call_closing == "pending":
                    self._human_after_terminal += 1
                    self._somebody_is_talking_again()
            #     LA RETE SI GUARDA QUI, CHE E' L'UNICO POSTO CHE BATTE SEMPRE.
            # Venti millisecondi, un confronto: non c'e' un altro momento in
            # cui si possa essere sicuri di passare anche quando ORA non ha
            # piu' niente da dire e la controparte nemmeno.
            if self._mission_terminal_at is not None:
                self._make_sure_we_actually_hang_up()
            if ha_finito and self._answered_before_our_ears:
                #     QUESTA FRASE HA GIA' AVUTO LA SUA RISPOSTA.
                # Gemini ha risposto prima che queste orecchie dichiarassero
                # la fine: la dichiarazione arriva adesso, in ritardo, e non
                # deve finire attribuita alla risposta successiva.
                self._answered_before_our_ears = False
            elif ha_finito:
                # La fine del parlato e' dove il silenzio e' cominciato, non
                # dove ce ne siamo accorti: la finestra e' nota e si toglie.
                self._speech_ended_at = (
                    time.perf_counter() - Ears.SILENCE_MS / 1000.0
                )
        except Exception:
            pass
        if _ripresa_in_corso:
            # Il credito e' gia' stato preso: la linea continua a battere anche
            # mentre il filo si riapre. Questi campioni invece finiscono qui.
            return
        try:
            verso_gemini = time.perf_counter()
            await self._send({"realtimeInput": {"audio": {
                "data": base64.b64encode(pcm).decode(),
                "mimeType": f"audio/pcm;rate={LINE_RATE}",
            }}})
            adesso = time.perf_counter()
            self._gemini_send_ms.append(round((adesso - verso_gemini) * 1000, 2))
            self._hear_total_ms.append(round((adesso - entrato) * 1000, 2))
        except Exception:
            #     UNA LINEA CHE SI CHIUDE NON RISALE FINO AL TRASPORTO.
            # E adesso non chiude nemmeno la telefonata: se il filo verso chi
            # parla e' caduto, se ne accorge chi legge — ed e' lui che sa
            # riaprirlo. Qui si smette soltanto di mandare.
            self._closed_reasons.append("send:" + "ConnectionClosed")

    # --- il fiume che esce ------------------------------------------------

    # --- riprendere, invece di morire --------------------------------------

    def _setup_message(self, resume_handle: str = "") -> Dict[str, Any]:
        """
        Il messaggio che apre una sessione. Uno solo, per tutte le aperture.

            LA PRIMA E LA QUINTA SESSIONE DEVONO ESSERE LA STESSA COSA.

        Se la connessione di ripresa si costruisse altrove, prima o poi una
        delle due si dimenticherebbe la voce — ed e' esattamente il difetto che
        si e' sentito: una telefonata che cambia timbro a meta' senza che nulla
        nel rapporto lo spieghi. Una funzione sola, e la domanda «con quale
        voce?» ha una risposta sola.

        `sessionResumption` si chiede sempre: e' come si ottengono gli appigli
        che servono se il filo cade. Con un appiglio dentro, il server capisce
        che non e' una telefonata nuova — e' la stessa che riprende.
        """
        ripresa: Dict[str, Any] = {}
        if resume_handle:
            ripresa["handle"] = resume_handle

        #     LA LINGUA DELLA MISSIONE, IN TUTTI E TRE I POSTI.
        # La voce la pronuncia, e le due trascrizioni la ascoltano. Misurato
        # sul vero: senza, la controparte è stata trascritta in portoghese a
        # metà telefonata. Viene dal pacchetto, non da una costante.
        lingua = self._language_tag()
        voce = _how_she_sounds()
        voce["speechConfig"] = {**voce["speechConfig"], "languageCode": lingua}
        return {
            "setup": {
                "model": f"models/{_model()}",
                "generationConfig": voce,
                "systemInstruction": {"parts": [{
                    "text": SESSION_PROMPT
                    + self._rules_for_this_kind_of_call()
                    + "\n\nPACCHETTO MISSIONE:\n"
                    + self.packet.for_the_model(),
                }]},
                "tools": tools_for(
                    self.packet.mission_type if self.packet is not None
                    else "reschedule"
                ),
                "inputAudioTranscription": {"languageCodes": [lingua]},
                "outputAudioTranscription": {"languageCodes": [lingua]},
                "realtimeInputConfig": {
                    "automaticActivityDetection": _when_a_turn_ends(),
                },
                "sessionResumption": ripresa,
            }
        }

    def _rules_for_this_kind_of_call(self) -> str:
        """
        Le regole che valgono solo per un tipo di telefonata.

        Oggi una: la consegna di un messaggio, che non è una trattativa e ha
        un ordine che non si salta — prima chi, poi che cosa, poi ascoltare.
        """
        p = self.packet
        if p is None or p.mission_type != "deliver_message":
            return ""
        nome = (p.recipient_name or "").split()[0] if p.recipient_name else "la persona"
        chi = p.on_behalf_of
        return (
            "\n\nPER QUESTA TELEFONATA — un messaggio da consegnare:\n"
            f"- Dopo la prima frase aspetta che ti dicano chi sono. Solo quando "
            f"la persona dice di essere {nome}, usa recipient_confirmed: ti darà "
            "il messaggio. Prima non lo conosci.\n"
            f"- Quando dice di essere {nome}, non restare in silenzio mentre "
            f"aspetti il messaggio: di' subito una parola breve («Ciao {nome}!») "
            "e intanto usa recipient_confirmed.\n"
            f"- Se risponde qualcun altro, non dire niente del messaggio né del "
            f"perché chiami: chiedi se {nome} c'è o quando richiamare, e usa "
            "recipient_not_available.\n"
            "- Consegna il messaggio fedelmente, con calore, in terza persona. "
            "Non cambiarne il significato e non aggiungere niente.\n"
            f"- Il messaggio si attribuisce sempre a {chi} («{chi} mi ha "
            "chiesto di dirti che…»): non dirlo mai in prima persona.\n"
            f"- Poi ascolta. Se ti dà una risposta per {chi}, di' «Certo, "
            f"glielo riferisco». Se ti chiede qualcosa che solo {chi} può "
            "decidere, non rispondere tu: «Questo non posso deciderlo per "
            "lui, ma glielo riferisco».\n"
            "- Usa message_delivered solo dopo che ha risposto o ha chiaramente "
            "finito di parlare, riportando la sua risposta con le sue parole "
            "(e le sue domande per lui). Poi saluta con calore.\n"
            f"- «Parlo con {nome}?» si chiede una volta. Se ha già detto chi è, "
            "non chiederlo più; se la risposta non era chiara («Pronto?», "
            "«Ciao»), puoi chiederlo ancora una volta sola.\n"
            f"- Se risponde una segreteria, non lasciare il messaggio: usa "
            "recipient_not_available con who_answered=voicemail.\n"
            "- Qui il tono è caldo e personale, non da ufficio."
        )

    def _language_tag(self) -> str:
        """La lingua della missione, con l'italiano quando non c'è pacchetto."""
        if self.packet is not None:
            try:
                return self.packet.language_tag()
            except Exception:  # pragma: no cover
                pass
        return "it-IT"

    async def _connect_once(self, *, resume_handle: str = "") -> bool:
        """
        Apre un filo e lo prepara. Torna se ha funzionato.

        Non chiude niente e non decide niente: apre, chiede, aspetta la
        conferma. Chi la chiama sa se e' la prima volta o la terza, e sa che
        cosa fare se torna `False`.
        """
        suona = _how_she_sounds()
        chiesta = (
            suona["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
        )
        self._connection_index += 1
        scheda: Dict[str, Any] = {
            "connection_index": self._connection_index,
            "credential_slot": _key_slot(),
            "model": _model(),
            "requested_voice": _voice(),
            "live_voice_in_setup": chiesta,
            "speech_config_sent": True,
            "language_in_setup": self._language_tag(),
            "silence_ms_in_setup": _silence_ms(),
            "session_started_at": _when_it_is_now(),
            "resumed_from_handle": bool(resume_handle),
            "resume_handle_present": bool(resume_handle),
            "reason": self._next_connection_reason or "first",
            #     LA STESSA MISSIONE, SU OGNI FILO.
            "mission_id": self.packet.mission_id if self.packet is not None else "",
            "closed_because": "",
            "setup_echo": {},
            "failed_because": "",
        }
        vecchio = self.ws
        try:
            nuovo = await (self._connect or _dial)()
            self.ws = nuovo
            await self._send(self._setup_message(resume_handle))
            primo = await asyncio.wait_for(self._recv(), timeout=SETUP_TIMEOUT_S)
            if not primo or "setupComplete" not in primo:
                scheda["failed_because"] = "setup non accettato"
                self._connections.append(scheda)
                self.ws = vecchio
                await _shut(nuovo)
                return False
            scheda["setup_echo"] = _just_the_shape(primo.get("setupComplete"))
        except Exception as e:
            scheda["failed_because"] = type(e).__name__
            self._connections.append(scheda)
            self.ws = vecchio
            logger.info("il filo verso chi parla non si è aperto: %s", type(e).__name__)
            return False

        #     IL VECCHIO SI CHIUDE SOLO QUANDO IL NUOVO È PRONTO.
        # Mai due sessioni vive insieme, e mai un istante senza nessuna: e' la
        # differenza fra una ripresa che non si sente e un buco nella
        # telefonata.
        if vecchio is not None and vecchio is not self.ws:
            await _shut(vecchio)

        self._connections.append(scheda)
        self._trace = {
            "live_credential_slot": scheda["credential_slot"],
            "live_model_opened": scheda["model"],
            "live_requested_voice": scheda["requested_voice"],
            "live_speech_config_sent": True,
            "live_voice_in_setup": scheda["live_voice_in_setup"],
            "live_session_opened_at": scheda["session_started_at"],
            "live_fallback_reason": "",
            "live_setup_echo": scheda["setup_echo"],
        }
        logger.info(
            "sessione Live %s: slot=%s modello=%s voce=%s%s",
            self._connection_index, scheda["credential_slot"], scheda["model"],
            chiesta, " (ripresa)" if resume_handle else "",
        )
        return True

    def _remember_the_handle(self, aggiornamento: Dict[str, Any]) -> None:
        """
        L'appiglio per riprendere, se e' buono.

            UN APPIGLIO NON RIPRENDIBILE NON SOSTITUISCE QUELLO BUONO.

        Il server ne manda uno circa al secondo. Alcuni arrivano con
        `resumable` falso o senza manico: quelli si contano e si buttano, non
        si scrivono sopra all'ultimo valido — sovrascriverlo vorrebbe dire
        perdere l'unica cosa che serve proprio quando il filo cade.
        """
        self._resumption_updates += 1
        manico = str(aggiornamento.get("newHandle") or "").strip()
        if not manico or aggiornamento.get("resumable") is False:
            return
        self._resume_handle = manico

    async def _drop_the_live_wire_on_purpose(self) -> None:
        """DEV-ONLY: chiude il filo Gemini, come se Google l'avesse chiuso."""
        try:
            if self._connections:
                self._connections[-1]["closed_because"] = "dev_fault_injection"
            if self.ws is not None:
                await self.ws.close()
        except Exception as e:  # pragma: no cover
            logger.info("DEV: chiusura del filo non riuscita: %s", type(e).__name__)

    def _handle_go_away(self, avviso: Dict[str, Any]) -> None:
        """
        Il server annuncia che questa sessione sta per finire.

            NON È UN ERRORE DELLA MISSIONE.

        E' un preavviso, ed e' un regalo: dice quanto tempo resta. Si riapre
        prima che cada, cosi' chi sta parlando non sente niente.
        """
        self._go_away_count += 1
        if self._connections:
            self._connections[-1]["go_away"] = True
        resta = avviso.get("timeLeft")
        self._go_away_time_left = str(resta) if resta is not None else ""
        self._must_resume = "goAway"
        logger.info("il server ha annunciato goAway (resta %s)", self._go_away_time_left)

    async def _resume(self, perche: str) -> bool:
        """
        Riprende la stessa telefonata su un filo nuovo.

            NON È UNA SECONDA CHIAMATA, E NON DEVE SEMBRARLO.

        Niente presentazione, niente saluto, niente conversazione che
        ricomincia: la continuita' la porta l'appiglio di ripresa, non noi. Il
        ledger della missione, l'autorita', lo stato del commiato e l'identita'
        della chiamata restano quelli di prima — non si toccano nemmeno.

            E SE NON C'È UN APPIGLIO, NON SI FINGE.

        Aprire una sessione vuota e proseguire vorrebbe dire una ORA nuova che
        non sa niente di quello che si e' detto, con la stessa voce. Meglio
        dichiarare che il trasporto e' caduto: nessun esito, nessuna scrittura,
        e una telefonata che si racconta per quello che e' stata.
        """
        if self._closed:
            return False
        self._resuming = True
        try:
            if not self._resume_handle:
                self._transport_failure = f"{perche}: nessun appiglio di ripresa"
                logger.info("filo caduto senza appiglio: la missione si ferma")
                return False

            #     MENTRE SI RIAPRE, ORA NON PARLA.
            # Quello che era in coda apparteneva a una generazione che non
            # esiste piu': versarlo adesso vorrebbe dire far dire a ORA la fine
            # di una frase cominciata su un altro filo.
            #
            #     MA UNA FRASE GIA' FINITA DI GENERARE SI LASCIA FINIRE DI DIRE.
            # Misurato sul vero (V3.21.2, gate A): il filo è caduto subito dopo
            # la fine di un turno e la ripresa ha buttato l'audio in coda —
            # completo — tagliando il messaggio a metà: «…che questo è un
            # test», «Pronto?», e ORA ha dovuto ripeterlo. Si butta solo quello
            # che apparteneva a una generazione rimasta a metà.
            if self._speaking is not None:
                try:
                    await self.playback.cancel()
                except Exception:
                    pass
                self._speaking = None

            for tentativo in range(MAX_RESUME_ATTEMPTS):
                self._resume_attempts += 1
                self._next_connection_reason = perche
                if tentativo:
                    await asyncio.sleep(
                        RESUME_BACKOFF_S[min(tentativo, len(RESUME_BACKOFF_S) - 1)]
                    )
                comincio = time.perf_counter()
                if await self._connect_once(resume_handle=self._resume_handle):
                    self._resumes_done += 1
                    self._reconnect_ms.append(
                        int((time.perf_counter() - comincio) * 1000))
                    self._reconnect_reasons.append(perche)
                    logger.info(
                        "sessione ripresa dopo %s (tentativo %d)",
                        perche, tentativo + 1,
                    )
                    return True
                if self._closed:
                    return False

            self._transport_failure = (
                f"{perche}: ripresa non riuscita in "
                f"{MAX_RESUME_ATTEMPTS} tentativi"
            )
            logger.info("ripresa non riuscita: la missione si ferma")
            return False
        finally:
            self._resuming = False

    async def _listen_to_the_model(self) -> None:
        """
        Tutto quello che arriva da chi parla — e se smette di arrivare, si
        riapre invece di lasciar morire la telefonata.

            UN FILO CHE CADE NON È UNA MISSIONE FINITA.

        Su una prenotazione vera il filo e' caduto quattordici secondi dopo
        l'apertura, mentre lo studio stava fissando l'appuntamento. ORA non ha
        riagganciato: le hanno tolto la sessione da sotto, e non sapeva
        riprenderla. Adesso sa.
        """
        while not self._closed:
            try:
                while not self._closed:
                    messaggio = await self._recv()
                    if messaggio is None:
                        raise ConnectionError("il filo si è chiuso")
                    await self._one_message(messaggio)
                    if self._must_resume and not self._closed:
                        #     IL PREAVVISO SI ONORA PRIMA DELLA CADUTA.
                        perche, self._must_resume = self._must_resume, ""
                        if not await self._resume(perche):
                            return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if self._closed:
                    return
                motivo = type(e).__name__
                logger.info("il filo di chi parla si è chiuso: %s", motivo)
                self._closed_reasons.append(motivo)
                if self._connections and not self._connections[-1].get("closed_because"):
                    self._connections[-1]["closed_because"] = motivo
                if not await self._resume(motivo):
                    return

    async def _one_message(self, m: Dict[str, Any]) -> None:
        if m.get("usageMetadata"):
            u = m["usageMetadata"]
            self._tokens = {
                "total": int(u.get("totalTokenCount") or 0),
                "input": int(u.get("promptTokenCount") or 0),
                "output": int(u.get("responseTokenCount") or 0),
            }

        #     QUELLO CHE IL SERVER DICE E CHE NON STAVAMO ASCOLTANDO.
        #
        # `goAway` annuncia che questa sessione sta per finire;
        # `sessionResumptionUpdate` che ne e' cominciata un'altra al suo
        # posto. Su una telefonata in cui la voce e' cambiata a meta' erano
        # esattamente i due messaggi che avrebbero spiegato perche', e li
        # stavamo lasciando cadere senza contarli. Non si reagisce: si annota.
        for avviso in ("goAway", "sessionResumptionUpdate"):
            if m.get(avviso):
                self._server_said.append({
                    "what": avviso,
                    "at_ms": self._since_open(time.perf_counter()),
                    "shape": _just_the_shape(m.get(avviso)),
                })
                logger.info("il server ha detto %s a %s ms", avviso,
                            self._server_said[-1]["at_ms"])
        if m.get("sessionResumptionUpdate"):
            self._remember_the_handle(m["sessionResumptionUpdate"])
        if m.get("goAway"):
            self._handle_go_away(m["goAway"])
        ignoti = set(m) - _WHAT_WE_KNOW
        if ignoti:
            self._server_unknown.update(ignoti)

        if m.get("toolCall"):
            await self._tools_were_asked(m["toolCall"])
            return

        content = m.get("serverContent") or {}

        if content.get("interrupted"):
            await self._someone_cut_in()
            return

        for part in ((content.get("modelTurn") or {}).get("parts") or []):
            dati = (part.get("inlineData") or {}).get("data")
            if dati:
                await self._pour(dati)

        if content.get("outputTranscription"):
            parole = content["outputTranscription"].get("text") or ""
            self._said_this_turn.append(parole)
            if self.intro is not None:
                self.intro.we_said(parole)
                if (self.intro.is_settled()
                        and self._opening not in ("completed", "identity_pending")):
                    if self._asks_who_they_are() and not self._identity_settled:
                        self._opening = "identity_pending"
                    else:
                        self._opening = "completed"
                        self._opening_completed_at = time.perf_counter()

        if content.get("inputTranscription"):
            self._heard_this_turn.append(
                content["inputTranscription"].get("text") or ""
            )

        if content.get("turnComplete"):
            await self._the_turn_is_over()

    async def _pour(self, base64_pcm: str) -> None:
        """
        L'audio di chi parla, portato al passo della linea e versato.

        Fra i due passi c'è il ricampionatore in streaming: porta avanti la
        coda del filtro fra un pacchetto e l'altro, perché filtrare ogni
        pacchetto come se fosse solo al mondo lascia una giunta udibile
        cinquanta volte al secondo.
        """
        adesso = time.perf_counter()
        if self._call_closing == "pending" and self._goodbye != "completed":
            #     STA RICOMINCIANDO A PARLARE: LA TELEFONATA NON ERA FINITA.
            #
            # Ma solo se il saluto non e' gia' stato detto. Dopo il saluto,
            # quella che continua a parlare e' ORA — e un commiato che esce a
            # pezzi («La ringrazio,» · «Buona giornata.» · «Arrivederci.») la
            # portava ad annullare la propria chiusura a ogni frammento.
            # Misurato: `goodbye_state=completed` e la telefonata aperta per
            # altri nove secondi, finche' non ha riagganciato la persona.
            #
            # Chi parla ha sempre ragione sulla chiusura — ma «chi parla» qui
            # vuol dire la controparte, e di quella si occupano le orecchie.
            self._somebody_is_talking_again()
        if self._speaking is None and self._goodbye == "completed":
            #     DOPO «ARRIVEDERCI» NON SI DICE PIU' NIENTE.
            #
            # Il commiato e' fatto e la controparte ha risposto. Gemini pero'
            # sente quel «arrivederci» e genera un altro turno — e ORA lo dice,
            # e ne nasce un terzo. Sul vero si sono contati tre saluti di fila
            # dove ne bastava uno, e la persona ha dovuto riagganciare lei.
            #
            # Impedire al modello di generare non si puo'. Versare quello che
            # genera si': la coda verso la linea e' nostra. Una generazione
            # gia' cominciata finisce — tagliarla a meta' sarebbe il difetto
            # opposto — ma una nuova, dopo il saluto, non parte.
            self._words_after_goodbye += 1
            return

        if self._speaking is None:
            #     GEMINI E' PIU' SVELTO DELLE NOSTRE ORECCHIE.
            # Decide dopo mezzo secondo di silenzio, noi dopo novecento
            # millisecondi. Se risponde nel mezzo, la fine del parlato è
            # «adesso meno il silenzio già passato» — e senza questo il turno
            # più veloce della telefonata sparirebbe dalle misure.
            zitto = self._ears.quiet_for_ms() if self._ears is not None else 0
            if self._speech_ended_at is None and zitto >= QUIET_MEANS_DONE_MS:
                self._speech_ended_at = adesso - zitto / 1000.0
                self._answered_before_our_ears = True
            self._speaking = self.playback.begin(
                generation_id=uuid.uuid4().hex[:12], turn_id=self._turn,
            )
            self._this_response = {
                "turn": self._turn,
                "gemini_first_audio_ms": None,
                "first_line_frame_ms": None,
                "audio_ms": 0,
                "chunks": 0,
                #     I DUE PEZZI DELLA LATENZA, SEPARATI.
                # Da quando la controparte ha smesso a quando Gemini ha dato il
                # primo audio: a monte. Da lì al primo pacchetto sulla linea: noi.
                "speech_end_at_ms": (
                    int((self._speech_ended_at - self._opened_at) * 1000)
                    if self._speech_ended_at is not None else None
                ),
                "gemini_first_audio_at_ms": int((adesso - self._opened_at) * 1000),
                "local_first_audio_ms": None,
            }
            self._last_chunk_at = 0.0
            self._silent_run_ms = 0
            self._voiced_in_generation = False
            if self._opening == "starting" and self._opening_first_gemini_at is None:
                self._opening_first_gemini_at = adesso
            if self._speech_ended_at is not None:
                quanto = int((adesso - self._speech_ended_at) * 1000)
                self._first_audio.append(quanto)
                self._this_response["gemini_first_audio_ms"] = quanto
                if self._intro_ms is None:
                    self._intro_ms = quanto
                self._speech_ended_at = None

        # Il buco in arrivo: quanto e passato dall'ultimo pezzo di voce.
        if self._last_chunk_at:
            vuoto = (adesso - self._last_chunk_at) * 1000
            if vuoto > 30:
                self._gemini_gaps_ms.append(round(vuoto, 1))
                self._gemini_gap_at_ms.append(
                    int((adesso - self._opened_at) * 1000)
                )
            if vuoto > 100 and len(self._gemini_gap_events) < 40:
                in_coda = (
                    int(self._speaking.queued_audio_ms - self._speaking.sent_audio_ms)
                    if self._speaking is not None else 0
                )
                self._gemini_gap_events.append({
                    "at_ms": int((adesso - self._opened_at) * 1000),
                    "gap_ms": round(vuoto, 1),
                    # Quanta voce restava da dire quando il pezzo è arrivato:
                    # sopra zero, il buco a monte non è arrivato alla linea.
                    "queued_ms_on_arrival": in_coda,
                    "absorbed": in_coda > 0,
                })
        self._last_chunk_at = adesso
        self._chunks_in += 1
        if self._this_response is not None:
            self._this_response["chunks"] += 1

        inizio = time.perf_counter()
        try:
            grezzo = base64.b64decode(base64_pcm)
        except Exception:
            return
        self._listen_for_silence(grezzo, adesso)
        alla_linea = self._down.feed(grezzo)
        self._resample_ms.append((time.perf_counter() - inizio) * 1000)
        if alla_linea:
            await self.playback.feed(alla_linea, self._speaking)
            if (self._this_response is not None
                    and self._this_response["first_line_frame_ms"] is None
                    and self.playback.first_send_at is not None):
                self._this_response["first_line_frame_ms"] = int(
                    (self.playback.first_send_at - self._opened_at) * 1000
                )
                self._this_response["local_first_audio_ms"] = (
                    self._this_response["first_line_frame_ms"]
                    - self._this_response["gemini_first_audio_at_ms"]
                )
                if (self._opening == "speaking"
                        and self._opening_first_line_at is None):
                    self._opening_first_line_at = self.playback.first_send_at

    def _check_the_language(self, chi: str, testo: str) -> None:
        """
        Se una frase è uscita in un'altra lingua, lo si scrive. E basta.

            UNA PAROLA STRANIERA NON CHIUDE UNA TELEFONATA.

        Non si interrompe e non si corregge: si segna nel resoconto, così la
        prossima volta si sa se la deriva è di chi parla (ORA) o di chi
        trascrive la controparte — che sono due problemi diversi.
        """
        from telephone.language import drifted

        altra = drifted(testo, self._language_tag())
        if altra is None or len(self._drift) >= 12:
            return
        self._drift.append({
            "turn": self._turn, "who": chi, "language": altra,
            "text": testo[:80],
        })

    def _listen_for_silence(self, pcm: bytes, adesso: float) -> None:
        """
        Silenzio lungo dentro la voce generata — cioè il buco è nell'audio.

        Si guarda a finestre di dieci millisecondi. Un silenzio iniziale non
        conta (è il confine fra una risposta e l'altra); uno in mezzo, dopo
        che si è già sentita voce e prima che ne torni, sì.
        """
        import array

        passo = MODEL_RATE // 100  # dieci millisecondi di campioni
        campioni = array.array("h")
        try:
            campioni.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
        except Exception:  # pragma: no cover
            return
        for i in range(0, len(campioni) - passo + 1, passo):
            finestra = campioni[i:i + passo]
            forte = max(abs(min(finestra)), abs(max(finestra)))
            if forte < SILENT_BELOW:
                self._silent_run_ms += 10
                continue
            if (self._voiced_in_generation
                    and self._silent_run_ms >= SILENCE_WORTH_NOTING_MS
                    and len(self._generated_silences) < 30):
                self._generated_silences.append({
                    "at_ms": int((adesso - self._opened_at) * 1000),
                    "silence_ms": self._silent_run_ms,
                    "turn": self._turn,
                })
            self._voiced_in_generation = True
            self._silent_run_ms = 0

    async def _someone_cut_in(self) -> None:
        """
        Qualcuno ha parlato sopra: si smette, e si smette subito.

            CHI VIENE INTERROTTO TACE. NON FINISCE LA FRASE.
        """
        inizio = time.perf_counter()
        prima = self.playback.frames_sent
        buttati = await self.playback.cancel()
        coda = self._down.drain()   # la coda del filtro non deve finire dopo
        del coda
        self._speaking = None
        if self._opening == "speaking":
            # §5: l'hanno interrotta a meta. Non si ricomincia: si completa.
            self._opening = "interrupted"
            #     E LO SI DICE SUBITO, NON ALLA FINE DEL TURNO.
            # Misurato sul vero (V3.21.1a): «Ciao, sono—» / «Pronto?» — e la
            # risposta a quel «pronto» e' partita prima della nota di fine
            # turno, rifacendo tutta la presentazione. La nota adesso arriva
            # con l'interruzione, cosi' la prossima frase sa gia' che cosa e'
            # stato detto e che cosa manca.
            await self._finish_the_introduction_if_it_is_short()
        if self._goodbye == "speaking":
            self._goodbye_interrupted += 1
            # L'hanno interrotta mentre salutava: il saluto non e avvenuto.
            self._goodbye = "interrupted"
            self._goodbye_story.append("interrupted")
        fermata_in = int((time.perf_counter() - inizio) * 1000)
        self._barge_ins.append(fermata_in)
        self._barge.append({
            "turn": self._turn,
            # Quando le nostre orecchie hanno sentito che qualcuno parlava,
            # rispetto a quando Gemini ce l'ha detto. La differenza dice chi
            # se ne accorge prima.
            "we_heard_them_ms_before": (
                int((inizio - self._heard_them_start_at) * 1000)
                if self._heard_them_start_at else None
            ),
            "playback_stop_ms": fermata_in,
            "frames_after_detection": self.playback.frames_sent - prima,
            "stale_frames_dropped": buttati,
        })

    async def _the_turn_is_over(self) -> None:
        if self._speaking is not None:
            residuo = self._down.drain()
            if residuo:
                await self.playback.feed(residuo, self._speaking)
            await self.playback.finish(self._speaking)
            if self._this_response is not None:
                self._this_response["audio_ms"] = self._speaking.generated_audio_ms
                self._responses.append(self._this_response)
                self._this_response = None
            self._speaking = None

        #     PRIMA CHI HA PARLATO, POI CHI HA RISPOSTO.
        # Al contrario il registro mette la risposta sopra la domanda, e
        # rileggendolo sembra che ORA abbia chiuso prima della conferma.
        self._last_words = "".join(self._said_this_turn).strip()
        self._their_last_words = "".join(self._heard_this_turn).strip()
        self._voicemail.heard(self._their_last_words)
        self._check_the_language("ora", self._last_words)
        self._check_the_language("them", "".join(self._heard_this_turn).strip())
        await self._write_down("them", "".join(self._heard_this_turn))
        await self._write_down("ora", "".join(self._said_this_turn))
        self._said_this_turn.clear()
        self._heard_this_turn.clear()

        self._turn += 1
        self.mission.a_new_turn_begins()
        self._playback_finished_at = time.perf_counter()
        if (self._dev_drop_after and not self._dev_dropped
                and self._turn >= self._dev_drop_after
                and self._mission_terminal_at is None and not self._closed):
            #     DEV-ONLY: IL FILO CADE ADESSO, DI PROPOSITO.
            self._dev_dropped = True
            logger.info("DEV: filo Live chiuso di proposito dopo %d turni", self._turn)
            asyncio.create_task(self._drop_the_live_wire_on_purpose())
        if await self._is_it_a_voicemail():
            return
        if self._mission_terminal_at is not None and not self._hung_up:
            await self._make_sure_she_said_goodbye()
            return
        await self._finish_the_introduction_if_it_is_short()

    async def _say_the_first_line(self) -> None:
        """
        Apre lei, perche' e' lei che ha chiamato.

            CHI COMPONE UN NUMERO NON ASPETTA DI ESSERE INTERROGATO.

        Si lascia un quarto di secondo a chi risponde: se dice «pronto» in
        quell'istante, non gli si parla sopra — si rimanda, lo si ascolta, e
        ci si presenta dopo. Il registro dell'apertura chiedera' comunque il
        pezzo che manca, quindi rimandare non vuol dire rinunciare.
        """
        try:
            #     PRIMA CHE LE ORECCHIE SIANO SVEGLIE, NON SI DECIDE NIENTE.
            scade = time.perf_counter() + WAIT_FOR_EARS_S
            while not self._ears.ready and time.perf_counter() < scade:
                if self._closed:
                    return
                await asyncio.sleep(0.01)
            self._ears_ready_at = time.perf_counter()
            # E adesso che sanno riconoscere una voce, si sta a sentire.
            await asyncio.sleep(LISTEN_BEFORE_OPENING_S)
            if self._closed or self.packet is None:
                return
            if self._ears.speaking or self._speech_onsets:
                #     HANNO PARLATO PER PRIMI. TOCCA A LORO.
                self._opening_deferred += 1
                logger.info("hanno risposto parlando: l'apertura aspetta")
                return
            self._opening = "speaking"
            self._opening_requested_at = time.perf_counter()
            await self._send({"clientContent": {
                "turns": [{"role": "user", "parts": [{
                    "text": (
                        "[la linea si e' aperta, tocca a te] Parla tu adesso, "
                        "per primo, e di' esattamente questo: "
                        f"«{self.packet.say_this_first}»"
                    ),
                }]}],
                "turnComplete": True,
            }})
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.info("l'apertura non e' partita: %s", type(e).__name__)

    @staticmethod
    def _is_a_question(parole: str) -> bool:
        """
        Se l'ultima cosa detta era una domanda.

            CHI FA UNA DOMANDA ASPETTA LA RISPOSTA.

        Non serve capire cosa sia una domanda: basta guardare come finisce.
        E' punteggiatura, non semantica, e non sbaglia.
        """
        return parole.rstrip().endswith("?")

    @staticmethod
    def _sounds_like_a_goodbye(parole: str) -> bool:
        """Se in quello che abbiamo detto c'e' un congedo."""
        basso = parole.lower()
        return any(f in basso for f in FAREWELLS)

    async def _make_sure_she_said_goodbye(self) -> None:
        """
        La missione e' chiusa. La telefonata no, finche' non ci si saluta.

            NON SI RIAGGANCIA SENZA SALUTARE.
        """
        if self._is_a_question(self._last_words):
            #     HA APPENA CHIESTO QUALCOSA: TOCCA A LORO.
            # E' esattamente il caso della sesta telefonata: «ci sono
            # problemi?», e un istante dopo il telefono muto.
            self._goodbye = "pending"
            self._goodbye_story.append("pending")
            return

        if self._sounds_like_a_goodbye(self._last_words):
            self._goodbye = "completed"
            self._goodbye_story.append("completed")
            if self._goodbye_at is None:
                self._goodbye_at = time.perf_counter()
            self._start_watching_for_a_quiet_line()
            return

        if self._goodbye_nudges >= MAX_GOODBYE_NUDGES:
            # Non si insiste all'infinito: a un certo punto si chiude lo stesso,
            # ma solo sulla linea libera, come sempre.
            self._goodbye = "completed"
            self._goodbye_story.append("completed")
            self._start_watching_for_a_quiet_line()
            return

        self._goodbye = "speaking"
        self._goodbye_story.append("speaking")
        self._goodbye_nudges += 1
        await self._send({"clientContent": {
            "turns": [{"role": "user", "parts": [{
                "text": (
                    "[la missione e' conclusa] Chiudi la telefonata con un "
                    "saluto breve e cortese, senza fare altre domande."
                ),
            }]}],
            "turnComplete": True,
        }})

    def _the_mission_is_over(self) -> None:
        """
        L'esito e arrivato. Non vuol dire che la telefonata sia finita.

            UN FATTO NON SI REVOCA. UN'INTENZIONE SI'.
        """
        if self._mission_terminal_at is None:
            self._mission_terminal_at = time.perf_counter()

    def _make_sure_we_actually_hang_up(self) -> None:
        """
        Se il saluto e' stato detto, prima o poi si chiude. Sempre.

            UN COMMIATO COMPLETATO CHE NON RIAGGANCIA E' UN COMMIATO INUTILE.

        La sorveglianza della linea libera si annulla ogni volta che qualcuno
        riprende la parola, ed e' giusto: chi parla ha ragione sulla chiusura.
        Ma una volta annullata la rimetteva in piedi soltanto un turno nuovo di
        ORA — e se ORA non ha piu' niente da dire, quel turno non arriva mai.

        Questa funzione e' il pezzo che mancava: costa un confronto ogni venti
        millisecondi e garantisce che, a saluto dato e linea libera, la
        sorveglianza esista.

            E OLTRE UN CERTO PUNTO NON SI GUARDA PIU': SI CHIUDE.

        Se il saluto e' completato da abbastanza tempo e nessuno sta parlando,
        non c'e' nient'altro da aspettare. Non e' una scorciatoia sul contratto
        — il saluto c'e' stato, e la persona non sta dicendo niente — e' il
        fondo sotto al quale non si puo' cadere.
        """
        if self._hung_up or self._goodbye != "completed":
            return
        if self._ears.speaking:
            #     MAI SU QUALCUNO CHE PARLA. NEMMENO QUI.
            return
        if self.playback.still_pouring():
            #     E MAI CON LA PROPRIA FRASE ANCORA IN CODA.
            # Quello che sta nella coda verso il trasporto non e' ancora
            # arrivato a nessuno: riagganciare adesso taglierebbe la fine del
            # saluto, che e' il modo piu' brutto di rispettare un contratto
            # che esiste per salutare.
            return
        if self._goodbye_at is not None and (
            time.perf_counter() - self._goodbye_at >= HANGUP_SAFETY_S
        ):
            self._closed_by_safety_net += 1
            self._hangup_task = asyncio.create_task(self._hang_up_now())
            return
        if self._closing_watch is not None and not self._closing_watch.done():
            return
        self._closing_rearms += 1
        self._start_watching_for_a_quiet_line()

    def _start_watching_for_a_quiet_line(self) -> None:
        """Comincia a guardare se si puo chiudere. Senza fretta."""
        if self._hung_up or (
            self._closing_watch is not None and not self._closing_watch.done()
        ):
            return
        self._call_closing = "pending"
        self._close_candidate_at = time.perf_counter()
        self._closing_watch = asyncio.create_task(self._close_when_nobody_talks())

    def _somebody_is_talking_again(self) -> None:
        """
        Qualcuno ha ripreso la parola mentre stavamo per chiudere.

            CHI PARLA HA SEMPRE RAGIONE SULLA CHIUSURA.

        Alla terza telefonata vera la persona ha detto «aspetti un secondo» e
        si e ritrovata il telefono muto. Da qui in poi la chiusura torna
        indietro: l'esito resta quello che era, la conversazione riprende.
        """
        if self._call_closing != "pending":
            return
        self._call_closing = "open"
        self._close_window_resets += 1
        if self._closing_watch is not None:
            self._closing_watch.cancel()
            self._closing_watch = None

    async def _close_when_nobody_talks(self) -> None:
        """
        Si chiude solo dopo un tratto continuo di linea libera.

            NON UNA PAUSA A OROLOGIO: UN SILENZIO CHE DURA.

        Ogni volta che `Ears` sente una voce, la finestra riparte da zero. Chi
        vuole aggiungere una parola dopo il saluto la puo aggiungere, e
        qualcuno gliela ascolta.
        """
        try:
            # Prima che il trasporto consegni la coda dell'ultima frase.
            await asyncio.sleep(GOODBYE_GRACE_S)

            zitti_da = time.perf_counter()
            scade = zitti_da + DONT_WAIT_FOREVER_S
            while True:
                adesso = time.perf_counter()
                if self._ears.speaking:
                    if self._call_closing == "pending":
                        self._human_after_terminal += 1
                    self._somebody_is_talking_again()
                    return
                if adesso - zitti_da >= QUIET_LINE_BEFORE_CLOSING_S:
                    break
                if adesso > scade:
                    # La linea non e mai stata libera abbastanza a lungo, ma
                    # adesso nessuno sta parlando: e la pausa buona.
                    break
                await asyncio.sleep(0.02)

            self._final_quiet_ms = int((time.perf_counter() - zitti_da) * 1000)
            await self._hang_up_now()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.info("la chiusura non e riuscita: %s", type(e).__name__)

    async def _hang_up_now(self) -> None:
        """Riaggancia, e lascia detto se lo ha fatto su qualcuno che parlava."""
        self._hangup_attempts += 1
        if self._hung_up:
            return
        if self._ears.speaking:
            #     NON DOVREBBE MAI SUCCEDERE, E SE SUCCEDE SI VEDE.
            # Questa spia va guardata per prima: e' l'unica che registra un
            # tentativo di riagganciare su una persona che sta parlando, e se
            # un altro controllo scattasse prima non lo saprebbe nessuno.
            self._hangup_while_human_speaking += 1
            self._blocked_by_human += 1
            self._somebody_is_talking_again()
            return
        if self._goodbye != "completed":
            #     NON SI CHIUDE SENZA SALUTARE. MAI.
            self._blocked_by_goodbye += 1
            self._somebody_is_talking_again()
            return
        self._hung_up = True
        self._call_closing = "closed"
        self._hangup_at = time.perf_counter()
        riferimento = getattr(self.call, "provider_ref", "") if self.call else ""
        if not riferimento:
            return
        try:
            from telephone import carrier

            await carrier.hang_up(riferimento)
            logger.info("linea libera: la telefonata si chiude")
        except Exception as e:
            logger.info("non si e' potuto riagganciare: %s", type(e).__name__)

    async def _finish_the_introduction_if_it_is_short(self) -> None:
        """
        Se manca un pezzo dell'apertura, lo si ricorda. Una volta, non sempre.

            SI COMPLETA QUELLO CHE MANCA. NON SI RIFÀ LA PRESENTAZIONE.

        La nota entra nel contesto senza chiedere una risposta
        (`turnComplete: false`): chi parla la troverà quando toccherà a lui,
        e non aprirà bocca adesso per dire «va bene».
        """
        if self.intro is None or self.intro.is_settled():
            return
        if self.intro.nudges >= MAX_INTRODUCTION_NUDGES:
            return
        manca = self.intro.what_still_has_to_be_said()
        if not manca:
            return
        await self._send({"clientContent": {
            "turns": [{"role": "user", "parts": [{"text": f"[nota] {manca}"}]}],
            "turnComplete": False,
        }})

    # --- gli strumenti ----------------------------------------------------

    async def _tools_were_asked(self, tool_call: Dict[str, Any]) -> None:
        """
        Quello che chi parla ha chiesto, e quello che gli si concede.

            L'ELENCO È CHIUSO, E CHI NON C'È NON ENTRA.
        """
        risposte = []
        for f in tool_call.get("functionCalls") or []:
            nome = f.get("name") or ""
            argomenti = f.get("args") or {}
            inizio = time.perf_counter()
            self._tool_calls += 1
            tipo = self.packet.mission_type if self.packet is not None else ""
            if nome not in tools_allowed_for(tipo):
                self._refused_tools += 1
                logger.info("strumento fuori elenco richiesto e negato")
                esito: Dict[str, Any] = {"error": "strumento sconosciuto"}
            else:
                esito = await self._answer_one(nome, argomenti)
            self._tool_ms.append(int((time.perf_counter() - inizio) * 1000))
            risposte.append({"id": f.get("id"), "name": nome, "response": esito})
        if risposte:
            await self._send({"toolResponse": {"functionResponses": risposte}})

    async def _answer_one(self, nome: str, argomenti: Dict[str, Any]) -> Dict[str, Any]:
        packet = self.packet
        assert packet is not None

        if nome == "get_call_context":
            campo = str(argomenti.get("field") or "")
            gia = packet.already_knows(campo)
            if gia:
                return {"value": gia}
            if packet.may_release(campo):
                valore = await self._go_and_get(campo)
                if valore:
                    return {"value": valore}
            #     UN DATO NON PREVISTO NON SI DÀ, E NON SI SPIEGA PERCHÉ.
            return {
                "refused": True,
                "say": "Non ho questo dato con me, posso farglielo sapere dopo.",
            }

        if nome == "get_allowed_alternatives":
            return {"alternatives": list(packet.allowed_negotiation)}

        if nome in ("recipient_confirmed", "recipient_not_available",
                    "message_delivered"):
            return self._the_delivery(nome, argomenti)

        if (nome in ("complete_mission", "fail_mission")
                and self._ambiguity_refusals < 2
                and an_ambiguous_reply(
                    self._last_words,
                    "".join(self._heard_this_turn).strip() or self._their_last_words)):
            #     A QUALE DELLE DUE DOMANDE HA DETTO NO?
            self._ambiguity_refusals += 1
            self._refused_tools += 1
            return {
                "accepted": False,
                "reason": "risposta ambigua a due domande",
                "do_this": ("Hai fatto due domande insieme e la risposta è "
                            "troppo breve per sapere a quale vale. Chiedi di "
                            "nuovo, una cosa alla volta."),
            }

        if nome == "complete_mission" and packet.mission_type == "deliver_message":
            #     UNA CONSEGNA NON SI CHIUDE CON UNA CONFERMA DI MODIFICHE.
            self._refused_tools += 1
            return {"accepted": False,
                    "reason": "questa telefonata consegna un messaggio",
                    "do_this": "usa recipient_confirmed, poi message_delivered"}

        if nome == "request_user_confirmation":
            # Anche qui la missione e finita: quello che restava da
            # decidere non lo decide chi sta parlando. Ma la telefonata puo
            # ancora avere un saluto dentro.
            self._the_mission_is_over()
            #     LA PROPOSTA E' LA META' UTILE DI QUESTA FERMATA.
            # Senza, a chi deve decidere resta solo «non si e' potuto»: la
            # cosa che gli serve per rispondere e' quello che hanno offerto.
            # Si annota come `proposal` nel ledger, che e' il posto da cui la
            # continuazione la legge.
            proposta = str(argomenti.get("proposal") or "").strip()[:300]
            if proposta:
                self.mission.heard("proposal", proposta)
            self.outcome = CallMissionOutcome(
                mission_id=packet.mission_id,
                status="needs_user",
                user_confirmation_needed=str(argomenti.get("reason") or "")[:300],
                counterparty_statements=self.mission.statements[:8],
                proposed_slot={
                    "date": str(argomenti.get("proposed_date") or "")[:10],
                    "time": str(argomenti.get("proposed_time") or "")[:5],
                },
                followup_required=True,
            )
            return {
                "answer": "pending",
                "say": ("Devo chiedere conferma e la richiamo, non posso "
                        "confermare adesso."),
            }

        if nome == "record_call_fact":
            try:
                self.mission.heard(
                    str(argomenti.get("kind") or "detail"),
                    str(argomenti.get("value") or ""),
                )
            except Exception:
                return {"ok": False, "why": "tipo di frase sconosciuto"}
            return {"ok": True}

        if nome == "complete_mission":
            cambiamenti = argomenti.get("confirmed_changes") or {}
            motivo = self.mission.why_not_complete(
                cambiamenti, str(argomenti.get("confirmation") or ""),
            )
            if motivo:
                self._refused_tools += 1
                return {"accepted": False, "reason": motivo, **REFUSALS[motivo]}
            self.mission.completed()
            self._the_mission_is_over()
            self.outcome = CallMissionOutcome(
                mission_id=packet.mission_id,
                status="success",
                confirmed_changes={
                    str(k): str(v) for k, v in dict(cambiamenti).items()
                },
                counterparty_statements=self.mission.statements[:8],
                notes=str(argomenti.get("notes") or "")[:400],
            )
            return {"accepted": True, "say": "La ringrazio, buona giornata."}

        if nome == "fail_mission":
            self._the_mission_is_over()
            #     CHI HA LASCIATO UNA PORTA APERTA NON HA FALLITO: HA CHIESTO.
            # Se durante la telefonata e emersa un'alternativa che nessuno
            # aveva autorizzato, l'esito non e un fallimento — e una domanda
            # rimasta in sospeso, e va a chi puo rispondere.
            sul_tavolo = self.mission.something_is_on_the_table()
            self.outcome = CallMissionOutcome(
                mission_id=packet.mission_id,
                status="needs_user" if sul_tavolo else "failed",
                user_confirmation_needed=str(argomenti.get("reason") or "")[:300],
                counterparty_statements=self.mission.statements[:8],
                followup_required=True,
            )
            return {"ok": True, "say": "La ringrazio comunque, buona giornata."}

        return {"error": "strumento sconosciuto"}

    def _the_delivery(self, nome: str, argomenti: Dict[str, Any]) -> Dict[str, Any]:
        """
        Le tre mosse di una consegna, e l'ordine in cui sono ammesse.

            IL MESSAGGIO ESCE SOLO DOPO CHE SI SA CON CHI SI PARLA.

        `recipient_confirmed` è l'unica porta da cui il testo arriva a chi
        parla. `message_delivered` senza quella porta è rifiutato: non si può
        dire di aver consegnato una cosa che non si conosceva.
        """
        packet = self.packet
        assert packet is not None
        mandato = self._the_mandate()
        messaggio = (mandato.message if mandato is not None else "").strip()
        nome_persona = (packet.recipient_name or "").split()[0] if packet.recipient_name else ""

        if nome == "recipient_confirmed":
            if not messaggio:
                return {"error": "questa telefonata non ha un messaggio da consegnare"}
            #     A UNA SEGRETERIA IL MESSAGGIO NON ESCE, NEMMENO SE DICE «SONO ASIA».
            self._voicemail.heard("".join(self._heard_this_turn))
            if self._voicemail.verdict == "voicemail" or self._voicemail.carrier == "machine":
                self._refused_tools += 1
                return {
                    "accepted": False,
                    "reason": "sembra una segreteria",
                    "do_this": ("Non dire il messaggio. Usa recipient_not_available "
                                "con who_answered=voicemail."),
                }
            self._recipient_ok = True
            self._identity_is_settled()
            self.mission.heard("detail", str(argomenti.get("how_they_confirmed") or "")[:200])
            return {
                "message_to_deliver": messaggio,
                "from": packet.on_behalf_of,
                "say_it_like_this": (
                    f"Il messaggio è di {packet.on_behalf_of}, scritto con le "
                    "sue parole: quando parla di «lei» o «lui», parla di "
                    f"{nome_persona or 'questa persona'}. Rivolgilo a lei e "
                    f"attribuiscilo sempre a lui: «{packet.on_behalf_of} mi ha "
                    "chiesto di dirti che …» — per esempio «la amo» diventa "
                    f"«{packet.on_behalf_of} mi ha chiesto di dirti che ti "
                    "ama». Mai in prima persona, come se il sentimento fosse "
                    "tuo. Dillo con calore, senza cambiarne il significato, "
                    "senza aggiungere promesse o dettagli, senza togliere "
                    "niente. Poi taci e ascolta la sua risposta."
                ),
            }

        if nome == "recipient_not_available":
            self._identity_is_settled()
            self._the_mission_is_over()
            chi = str(argomenti.get("who_answered") or "not_sure")
            if chi == "voicemail":
                #     LA PAROLA DI CHI PARLA E' UN SEGNALE, NON UN FATTO.
                # Se nessun altro segnale la conferma, non si scrive
                # «segreteria»: si scrive che non l'abbiamo raggiunta.
                self._voicemail.heard("".join(self._heard_this_turn))
                consegna = ("voicemail" if self._voicemail.verdict == "voicemail"
                            or self._voicemail.carrier == "machine" else "not_reached")
            else:
                consegna = ("recipient_unavailable" if chi == "someone_else"
                            else "wrong_person")
            self.outcome = CallMissionOutcome(
                mission_id=packet.mission_id,
                status="failed",
                delivery=consegna,
                ended_because="voicemail" if consegna == "voicemail" else "",
                user_confirmation_needed=(
                    str(argomenti.get("callback_hint") or "")[:300]
                ),
                counterparty_statements=self.mission.statements[:8],
            )
            return {"ok": True, "say": "Va bene, grazie. Riproverò più tardi, buona giornata."}

        # message_delivered
        if not self._recipient_ok:
            self._refused_tools += 1
            return {
                "accepted": False,
                "reason": "non hai ancora confermato di parlare con la persona giusta",
                "do_this": "chiedi se stai parlando con lei; poi recipient_confirmed",
            }
        risposta = str(argomenti.get("recipient_reply") or "").strip()[:400]
        self.mission.completed()
        self._the_mission_is_over()
        self.outcome = CallMissionOutcome(
            mission_id=packet.mission_id,
            status="success",
            delivery="delivered",
            recipient_reply=risposta,
            counterparty_statements=self.mission.statements[:8],
            notes=str(argomenti.get("notes") or "")[:400],
        )
        return {"accepted": True,
                "say": "Certo, glielo riferisco. Ciao!"}

    async def the_carrier_says(self, answered_by: str) -> None:
        """L'operatore ha riconosciuto chi ha risposto: «machine» o «human»."""
        self._voicemail.carrier_says(answered_by)
        await self._is_it_a_voicemail()

    async def _is_it_a_voicemail(self) -> bool:
        """
        Se i segnali dicono segreteria, la missione finisce qui. Torna se e' finita.

            A UNA SEGRETERIA NON SI LASCIA NIENTE.

        Nessun mandato di V1 autorizza a lasciare messaggi: per una consegna
        vorrebbe dire dire il messaggio a una macchina che chiunque in casa
        puo' ascoltare. Si chiude senza dire niente di piu'.
        """
        if (self._voicemail_handled or self.packet is None
                or self._voicemail.verdict != "voicemail"):
            return False
        if self._mission_terminal_at is not None and self.outcome is not None:
            # Un esito vero c'era gia': una segreteria dopo non lo cancella.
            return False
        self._voicemail_handled = True
        self._identity_is_settled()
        self._the_mission_is_over()
        self.outcome = CallMissionOutcome(
            mission_id=self.packet.mission_id,
            status="failed",
            delivery=("voicemail" if self.packet.mission_type == "deliver_message"
                      else ""),
            ended_because="voicemail",
            counterparty_statements=self.mission.statements[:8],
            notes="ha risposto la segreteria: nessun messaggio lasciato",
        )
        logger.info("segreteria riconosciuta (%s): si chiude senza lasciare niente",
                    ", ".join(self._voicemail.signals))
        await self._hang_up_on_a_machine()
        return True

    async def _hang_up_on_a_machine(self) -> None:
        """
        Riaggancia su una segreteria.

        E' l'unica eccezione alla regola del saluto: a una registrazione non
        si dice arrivederci, e aspettare che taccia vorrebbe dire aspettare il
        bip — cioe' registrare.
        """
        try:
            await self.playback.cancel()
        except Exception:
            pass
        self._goodbye = "completed"
        self._goodbye_story.append("skipped_voicemail")
        if self._hung_up:
            return
        self._hangup_attempts += 1
        self._hung_up = True
        self._call_closing = "closed"
        self._hangup_at = time.perf_counter()
        riferimento = getattr(self.call, "provider_ref", "") if self.call else ""
        if not riferimento:
            return
        try:
            from telephone import carrier

            await carrier.hang_up(riferimento)
        except Exception as e:
            logger.info("non si e' potuto riagganciare: %s", type(e).__name__)

    def _asks_who_they_are(self) -> bool:
        """Se l'apertura finisce con una domanda d'identita' («Parlo con Asia?»)."""
        return bool(
            self.intro is not None and getattr(self.intro.intro, "asks_for", "")
        )

    def _identity_is_settled(self) -> None:
        """Chi ha risposto l'ha detto: l'apertura e' finita, e non si richiede."""
        self._identity_settled = True
        if self._opening in ("identity_pending", "speaking", "interrupted",
                             "not_started"):
            self._opening = "completed"
            if self._opening_completed_at is None:
                self._opening_completed_at = time.perf_counter()

    def _the_mandate(self):
        """Il mandato della telefonata: è lì, e solo lì, che sta il messaggio."""
        return getattr(self.call, "mandate", None)

    async def _go_and_get(self, campo: str) -> str:
        """
        Il valore di un campo consentito, preso dalla fonte canonica.

            IL PACCHETTO PORTA IL NOME DEL CAMPO, MAI IL VALORE.

        Per questo primo runtime la fonte è il profilo della persona, e solo
        per i campi che la missione aveva già dichiarato richiedibili: un
        elenco chiuso deciso prima che il telefono squillasse.
        """
        try:
            profilo = await self.db.users.find_one({"id": self.owner_id}) or {}
        except Exception:
            return ""
        dove = {"data_di_nascita": ("birth_date", "date_of_birth", "birthdate")}
        for chiave in dove.get(campo.strip().lower(), ()):
            valore = profilo.get(chiave)
            if valore:
                return str(valore)[:120]
        return ""

    # --- chiudere ----------------------------------------------------------

    async def close(self) -> None:
        """
        Si chiude tutto: il filo, la pompa, la coda dell'audio.

            UN SOCKET LASCIATO APERTO È UNA PORTA CHE QUALCUNO PUÒ TENERE.
        """
        if self._closed and self.ws is None and self._pump is None:
            return
        self._closed = True

        if self._hangup_task is not None:
            self._hangup_task.cancel()
            try:
                await self._hangup_task
            except (asyncio.CancelledError, Exception):
                pass
            self._hangup_task = None

        if self._opening_task is not None:
            self._opening_task.cancel()
            try:
                await self._opening_task
            except (asyncio.CancelledError, Exception):
                pass
            self._opening_task = None

        _IN_CORSO.discard(id(self))
        if self._clock_watch is not None:
            self._clock_watch.cancel()
            try:
                await self._clock_watch
            except (asyncio.CancelledError, Exception):
                pass
            self._clock_watch = None

        if self._opening_task is not None:
            self._opening_task.cancel()
            try:
                await self._opening_task
            except (asyncio.CancelledError, Exception):
                pass
            self._opening_task = None

        if self._closing_watch is not None:
            self._closing_watch.cancel()
            try:
                await self._closing_watch
            except (asyncio.CancelledError, Exception):
                pass
            self._closing_watch = None

        if self._pump is not None:
            self._pump.cancel()
            try:
                await self._pump
            except (asyncio.CancelledError, Exception):
                pass
            self._pump = None

        try:
            await self.playback.close()
        except Exception:
            pass

        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

        if self.outcome is None and self.packet is not None:
            #     UNA TELEFONATA SENZA ESITO NON È UNA TELEFONATA RIUSCITA.
            #
            # E si dice fin dove si era arrivati, senza supporre niente:
            # prima che la conversazione cominciasse, a trattativa aperta con
            # una proposta sul tavolo (decide una persona), o a meta'.
            cominciata = bool(
                self._turn > 0 and (self._their_last_words or self.mission.statements
                                    or self._opening in ("completed", "identity_pending"))
            )
            if not cominciata:
                stato = "failed"
            elif self.mission.something_is_on_the_table():
                stato = "needs_user"
            else:
                stato = "partial"
            self.outcome = CallMissionOutcome(
                mission_id=self.packet.mission_id,
                status=stato,
                counterparty_statements=self.mission.statements[:8],
                ended_because=("live_runtime_failure" if self._transport_failure
                               else "line_dropped"),
                notes=(
                    f"il filo verso chi parla è caduto: {self._transport_failure}"
                    if self._transport_failure
                    else ("la linea è caduta prima di un esito" if cominciata
                          else "la linea è caduta prima che la conversazione cominciasse")
                ),
                followup_required=True,
            )
            #     `partial` NON È AZIONABILE, ED È IL PUNTO.
            # Una telefonata a cui e' caduto il trasporto non scrive niente nel
            # mondo: il livello di applicazione salta, il calendario non si
            # tocca, e la scheda racconta che non si e' arrivati a un esito.
            # Non serve un ramo nuovo — serve non inventare un successo.

    def _since_open(self, quando: Optional[float]) -> Optional[int]:
        """Quanti millisecondi dall'apertura della linea. Niente orologi veri."""
        if quando is None or not self._opened_at:
            return None
        return int((quando - self._opened_at) * 1000)

    def _quality_report(self) -> Dict[str, Any]:
        """
        La qualità della conversazione, con la latenza divisa fra noi e loro.

            «LENTA» NON È UNA DIAGNOSI.

        Per ogni turno: quanto ha messo Gemini dalla fine del parlato al primo
        audio (a monte), e quanto abbiamo messo noi da lì al primo pacchetto
        sulla linea (in casa). E per ogni buco nella voce, da dove viene.
        """
        risposte = [r for r in self._responses if r.get("gemini_first_audio_ms") is not None]
        monte = sorted(r["gemini_first_audio_ms"] for r in risposte)
        casa = sorted(
            r["local_first_audio_ms"] for r in self._responses
            if r.get("local_first_audio_ms") is not None
        )
        mediana = lambda v: v[len(v) // 2] if v else None  # noqa: E731

        ora_deriva = [d for d in self._drift if d["who"] == "ora"]
        loro_deriva = [d for d in self._drift if d["who"] == "them"]
        return {
            "mission_language": self._language_tag(),
            "silence_ms_in_setup": _silence_ms(),
            "upstream_first_audio_ms": monte,
            "upstream_first_audio_p50_ms": mediana(monte),
            "local_first_audio_ms": casa,
            "local_first_audio_p50_ms": mediana(casa),
            "local_first_audio_max_ms": max(casa) if casa else None,
            "language_drift_count": len(ora_deriva),
            "their_language_drift_count": len(loro_deriva),
            "language_drift": list(self._drift),
            "gemini_gap_events": list(self._gemini_gap_events),
            "gemini_gaps_absorbed": sum(1 for g in self._gemini_gap_events if g["absorbed"]),
            "generated_silences": list(self._generated_silences),
            "loop_stalls": list(self._loop_stalls),
            "stall_culprits": list(self._stall_culprits),
            "loop_stall_max_ms": max((x["stall_ms"] for x in self._loop_stalls), default=0),
            "audio_gap_causes": self._why_the_voice_stopped(),
        }

    def _why_the_voice_stopped(self) -> Dict[str, Any]:
        """
        Per ogni buco sentito sulla linea, la causa più probabile. Con i dati.

            A · il pezzo di voce è arrivato tardi e la coda era vuota
            B · il silenzio era dentro la voce generata
            C · confine fra due generazioni
            D · locale: il processo era fermo, o la linea non batteva

        Non è un giudizio a occhio: per ogni buco si guarda che cosa c'era nello
        stesso momento. Se non c'è niente che lo spieghi, lo si dice.
        """
        #     DUE OROLOGI, UNO SCARTO.
        # La coda verso la linea nasce prima della sessione: i suoi istanti si
        # riportano sul nostro prima di confrontarli.
        partenza_coda = getattr(self.playback, "_opened_at", None) or self._opened_at
        scarto = int((self._opened_at - partenza_coda) * 1000)
        cause = {"A_late_chunk": 0, "B_silence_in_audio": 0,
                 "C_generation_boundary": 0, "D_local_stall": 0,
                 "D_line_clock": 0, "unexplained": 0}
        dettagli: List[Dict[str, Any]] = []

        def vicino(eventi, chiave, quando, durata, margine=150):
            for e in eventi:
                inizio = e["at_ms"]
                fine = inizio + e.get(chiave, 0)
                if inizio - margine <= quando and quando - durata <= fine + margine:
                    return e
            return None

        for g in getattr(self.playback, "gap_events", []):
            quando = g["at_ms"] - scarto   # sul nostro orologio
            durata = g["gap_ms"]
            if vicino(self._loop_stalls, "stall_ms", quando, durata):
                causa = "D_local_stall"
            elif g.get("in_fallback") or (g.get("beat_silent_for_ms") or 0) >= durata * 0.8:
                causa = "D_line_clock"
            elif g.get("queued_ms", 0) <= 0 and vicino(
                    self._gemini_gap_events, "gap_ms", quando, durata):
                causa = "A_late_chunk"
            elif vicino(self._generated_silences, "silence_ms", quando, durata):
                causa = "B_silence_in_audio"
            elif g.get("queued_ms", 0) <= 0:
                causa = "C_generation_boundary"
            else:
                causa = "unexplained"
            cause[causa] += 1
            dettagli.append({"at_ms": quando, "gap_ms": durata, "cause": causa})
        return {**cause, "gaps": dettagli[:20]}

    def how_it_went(self) -> Dict[str, Any]:
        tempi = sorted(self._first_audio)
        meta: Dict[str, Any] = {
            "runtime": "gemini_live",
            "live_ready_ms": self._ready_ms,
            "turns": self._turn,
            "first_audio_ms": tempi,
            "first_audio_p50_ms": tempi[len(tempi) // 2] if tempi else None,
            "first_audio_p90_ms": (
                tempi[min(len(tempi) - 1, int(round(0.9 * len(tempi))) - 1)]
                if tempi else None
            ),
            "introduction_first_audio_ms": self._intro_ms,
            "tool_calls": self._tool_calls,
            "tool_refused": self._refused_tools,
            "tool_ms": self._tool_ms,
            "resample_ms_avg": (
                round(sum(self._resample_ms) / len(self._resample_ms), 3)
                if self._resample_ms else None
            ),
            "barge_in_ms": self._barge_ins,
            "speech_cushion_ms": SPEECH_CUSHION_MS,
            # --- il percorso critico di hear() ------------------------------
            "hear_total_p50_ms": _q(self._hear_total_ms, 50),
            "hear_total_p95_ms": _q(self._hear_total_ms, 95),
            "hear_total_max_ms": (
                max(self._hear_total_ms) if self._hear_total_ms else None
            ),
            "time_to_credit_p50_ms": _q(self._to_credit_ms, 50),
            "time_to_credit_p95_ms": _q(self._to_credit_ms, 95),
            "time_to_credit_max_ms": (
                max(self._to_credit_ms) if self._to_credit_ms else None
            ),
            "gemini_send_p50_ms": _q(self._gemini_send_ms, 50),
            "gemini_send_p95_ms": _q(self._gemini_send_ms, 95),
            "gemini_send_max_ms": (
                max(self._gemini_send_ms) if self._gemini_send_ms else None
            ),
            "inbound_gap_p50_ms": _q(self._inbound_gap_ms, 50),
            "inbound_gap_p90_ms": _q(self._inbound_gap_ms, 90),
            "inbound_gap_p95_ms": _q(self._inbound_gap_ms, 95),
            "inbound_gap_max_ms": (
                max(self._inbound_gap_ms) if self._inbound_gap_ms else None
            ),
            # --- l'apertura: un caso a se, e si misura a parte ---------------
            "opening_state": self._opening,
            "opening_voice": _voice() or "(quella del modello)",
            **self._trace,
            "server_announcements": self._server_said,
            "server_messages_not_understood": sorted(self._server_unknown),
            # --- il filo, e quante volte e' stato riaperto ------------------
            "live_connections": self._connections,
            "live_connection_count": self._connection_index,
            "session_resumption_updates": self._resumption_updates,
            "has_valid_resume_handle": bool(self._resume_handle),
            "go_away_count": self._go_away_count,
            "go_away_time_left": self._go_away_time_left,
            "resume_attempts": self._resume_attempts,
            "resumes_succeeded": self._resumes_done,
            "reconnect_ms": self._reconnect_ms,
            "reconnect_reasons": self._reconnect_reasons,
            "connection_closed_reasons": self._closed_reasons,
            "transport_failure": self._transport_failure,
            "mission_id": self.packet.mission_id if self.packet is not None else "",
            "dev_fault_injected": self._dev_dropped,
            "voicemail": self._voicemail.report(),
            "ambiguity_refusals": self._ambiguity_refusals,
            "identity_settled": self._identity_settled,
            "opening_deferred_for_human": self._opening_deferred,
            "answered_at_ms": 0 if self._answered_at else None,
            "live_ready_at_ms": self._since_open(self._live_ready_at),
            "ears_ready_at_ms": self._since_open(self._ears_ready_at),
            "live_ready_to_ears_ready_ms": (
                int((self._ears_ready_at - self._live_ready_at) * 1000)
                if self._ears_ready_at and self._live_ready_at else None
            ),
            "opening_requested_at_ms": self._since_open(self._opening_requested_at),
            "opening_first_gemini_audio_at_ms": self._since_open(
                self._opening_first_gemini_at),
            "opening_first_vonage_audio_at_ms": self._since_open(
                self._opening_first_line_at),
            "opening_completed_at_ms": self._since_open(self._opening_completed_at),
            "answered_to_live_ready_ms": self._ready_ms,
            "answered_to_first_ora_audio_ms": self._since_open(
                self._opening_first_line_at),
            "live_ready_to_first_ora_audio_ms": (
                int((self._opening_first_line_at - self._live_ready_at) * 1000)
                if self._opening_first_line_at and self._live_ready_at else None
            ),
            "speech_onsets_heard": self._speech_onsets,
            "line_floor": round(self._ears.floor, 5),
            "line_loudest": round(self._loudest, 5),
            "inbound_gaps_over_30ms": sum(
                1 for g in self._inbound_gap_ms if g > 30
            ),
            "inbound_gaps_over_60ms": sum(
                1 for g in self._inbound_gap_ms if g > 60
            ),
            # --- come e finita ---------------------------------------------
            "call_closing": self._call_closing,
            "goodbye_state": self._goodbye,
            "closing_rearms": self._closing_rearms,
            "words_after_goodbye_dropped": self._words_after_goodbye,
            "closed_by_safety_net": self._closed_by_safety_net,
            "goodbye_story": self._goodbye_story[:20],
            "goodbye_interrupted_count": self._goodbye_interrupted,
            "last_ora_utterance": self._last_words[:200],
            "hangup_attempt_count": self._hangup_attempts,
            "hangup_blocked_by_goodbye": self._blocked_by_goodbye,
            "hangup_blocked_by_human_speech": self._blocked_by_human,
            "first_human_onset_at_ms": self._since_open(self._first_human_onset),
            "last_human_onset_at_ms": self._since_open(
                self._heard_them_start_at or None),
            "goodbye_nudges": self._goodbye_nudges,
            "goodbye_at_ms": self._since_open(self._goodbye_at),
            "last_words_were_a_question": self._is_a_question(self._last_words),
            "mission_terminal_at_ms": self._since_open(self._mission_terminal_at),
            "playback_finished_at_ms": self._since_open(self._playback_finished_at),
            "close_candidate_at_ms": self._since_open(self._close_candidate_at),
            "hangup_at_ms": self._since_open(self._hangup_at),
            "human_speech_after_terminal_count": self._human_after_terminal,
            "close_window_resets": self._close_window_resets,
            "final_quiet_window_ms": self._final_quiet_ms,
            "hangup_while_human_speaking": self._hangup_while_human_speaking,
            "gemini_chunks_in": self._chunks_in,
            "gemini_gaps_over_30ms": len(self._gemini_gaps_ms),
            "gemini_gaps_over_50ms": sum(1 for g in self._gemini_gaps_ms if g > 50),
            "gemini_gaps_over_100ms": sum(1 for g in self._gemini_gaps_ms if g > 100),
            "worst_gemini_gaps_ms": sorted(self._gemini_gaps_ms, reverse=True)[:10],
            "gemini_gap_at_ms": self._gemini_gap_at_ms[:40],
            **self._quality_report(),
            "resample_ms_worst": (
                round(max(self._resample_ms), 3) if self._resample_ms else None
            ),
            "responses": self._responses[:12],
            "barge_ins": self._barge[:8],
            "hung_up_by_ora": self._hung_up,
            "mission_progress": self.mission.progress,
            "tokens": dict(self._tokens),
            "outcome_status": self.outcome.status if self.outcome else None,
            "outcome_actionable": (
                self.outcome.is_actionable() if self.outcome else False
            ),
            #     IL RESOCONTO SI RIPORTA. NON SI ESEGUE.
            # Qui finisce quello che la controparte ha confermato, in una
            # forma che ORA puo' rileggere e validare. Nessuno tocca il
            # calendario da questo file: chi ha parlato non scrive nel mondo.
            "outcome": (
                self.outcome.model_dump(exclude_none=True) if self.outcome else None
            ),
        }
        if self.intro is not None:
            meta.update(self.intro.how_it_went())
        meta.update(self.playback.how_it_went())
        return meta

    # --- il filo ------------------------------------------------------------

    async def _send(self, payload: Dict[str, Any]) -> None:
        if self.ws is None:
            return
        await self.ws.send(json.dumps(payload))

    async def _recv(self) -> Optional[Dict[str, Any]]:
        if self.ws is None:
            return None
        grezzo = await self.ws.recv()
        if isinstance(grezzo, (bytes, bytearray)):
            grezzo = grezzo.decode("utf-8", "ignore")
        try:
            return json.loads(grezzo)
        except Exception:
            return {}

    async def _write_down(self, chi: str, parole: str) -> None:
        """Il testo sì, l'audio mai."""
        detto = (parole or "").strip()
        if detto and self.on_said is not None:
            try:
                await self.on_said(chi, detto[:2000])
            except Exception:
                pass


def _q(valori, quanto: int):
    """Il valore sotto cui sta il `quanto` per cento delle misure."""
    if not valori:
        return None
    ordinati = sorted(valori)
    return round(ordinati[min(len(ordinati) - 1, int(quanto / 100 * len(ordinati)))], 2)


async def _shut(ws) -> None:
    """Chiude un filo e non si lamenta. Chiuderne uno gia' chiuso non e' un evento."""
    if ws is None:
        return
    try:
        await ws.close()
    except Exception:
        pass


async def _dial():
    """Il filo vero verso chi parla. La chiave non viene mai scritta da nessuna parte."""
    import websockets

    from telephone.carrier import _tls

    #     IL CONTESTO TLS E' QUELLO CONDIVISO, NON UNO NUOVO.
    # Senza `ssl=`, ogni apertura ne crea uno e ricarica i certificati: ~450 ms
    # di processo fermo (V3.21.1). Alla prima apertura si nota poco; a una
    # ripresa di sessione a meta' telefonata e' un buco che si sente.
    return await websockets.connect(
        f"{LIVE_URL}?key={_key()}", max_size=None, open_timeout=SETUP_TIMEOUT_S,
        ssl=_tls(),
    )
