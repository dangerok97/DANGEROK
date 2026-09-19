"""
Si può telefonare, o manca ancora qualcosa?

    UNA MISSIONE PRONTA È UNA CONVERSAZIONE POSSIBILE, NON UN MODULO PIENO.

Il modo sbagliato di rispondere sarebbe contare i campi: se ci sono tutti,
pronta. Funziona finché tutte le telefonate si somigliano, e smette di
funzionare al primo caso vero — una disdetta non ha bisogno di un orario
nuovo, una prenotazione non ha un appuntamento di partenza, e un modulo che
li chiede comunque fa sentire interrogato chi aveva solo detto una frase.

    QUINDI A CAPIRE COSA MANCA CI PENSA UN MODELLO. A DECIDERE NO.

È la stessa disciplina dell'autorità, per la stessa ragione. Il modello legge
la richiesta e quello che ORA sa, e dice che cosa manca e come lo chiederebbe:
è un lavoro di lingua, ed è il suo. Poi il risultato passa da un cancello
deterministico che controlla le cose che non si possono negoziare — c'è una
controparte? il numero l'ha confermato una persona? — e quel cancello non
chiede il permesso a nessuno.

    UN MODELLO CHE DICE «PRONTA» NON RENDE PRONTA UNA MISSIONE.

Può abbassare il verdetto, mai alzarlo sopra quello che i fatti permettono. Se
il numero non è confermato, «READY» non esiste, qualunque cosa risponda: non
c'è un ramo che ci arrivi.

    E QUATTRO RISPOSTE, CHE NON SI SOMIGLIANO.

`READY` si può fare. `NEEDS_INFO` manca un pezzo, e si sa quale. `AMBIGUOUS`
non si sa di chi o di che cosa si sta parlando — diverso da «manca», perché la
domanda da fare è «quale dei due?» e non «dimmi di più». `BLOCKED` così non si
telefona: non c'è un numero, o quello che c'era è stato rifiutato.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from preparation.preparation import MissingInformation, MissionPreparation

logger = logging.getLogger("ora.preparation.readiness")

# Le operazioni che hanno bisogno di sapere dove si vuole arrivare. Disdire no:
# l'appuntamento resta quello, tolto.
SERVE_UN_QUANDO = ("reschedule", "book", "postpone")

IL_SISTEMA = """Sei la parte di ORA che prepara una telefonata prima che parta.

ORA telefona per conto di una persona. Prima di comporre il numero deve sapere
abbastanza da reggere una conversazione vera con uno sconosciuto: chi sta
chiamando, perché, a che cosa si riferisce, e che cosa può accettare.

Il tuo compito è UNO SOLO: dire che cosa manca, e come lo chiederesti.

Regole:
- Non chiedere mai quello che è già scritto in «quello che ORA sa già».
- Non chiedere il numero di telefono: se ne occupa un'altra parte.
- Se contatto_trovato non è vuoto, chi chiamare è già deciso: non è ambiguo.
- Una domanda per informazione mancante, breve, in italiano, dando per
  acquisito quello che già si sa.
- Se la richiesta è chiara e il contesto basta per parlare, non inventare
  informazioni mancanti per prudenza: rispondi con un elenco vuoto.
- Se non si capisce a chi o a che cosa la persona si riferisce, dillo con
  ambiguous invece di inventare una domanda generica.
- Se tipo_di_telefonata è deliver_message e il messaggio c'è, non manca
  niente: non chiedere orari, date o dettagli. Chiedi solo se il messaggio,
  preso alla lettera, potrebbe voler dire cose molto diverse.

Rispondi SOLO con JSON:
{
  "understood_goal": "l'obiettivo in una riga, in italiano",
  "ambiguous": false,
  "ambiguous_about": "",
  "missing": [
    {"field": "nome_breve_senza_spazi",
     "question": "la domanda in italiano",
     "why": "perché serve, in poche parole",
     "already_known": "quello che la domanda dà per acquisito"}
  ]
}"""


async def evaluate(
    db, prep: MissionPreparation, *, operation: str = "",
) -> MissionPreparation:
    """
    Guarda la preparazione e dice a che punto è.

        PRIMA I FATTI, POI IL MODELLO, POI DI NUOVO I FATTI.

    I fatti che bloccano si guardano subito, perché se non c'è un numero
    confermato non c'è niente da chiedere a nessuno. Poi il modello dice che
    cosa manca per parlare. Poi il cancello deterministico ricontrolla, perché
    quello che il modello ha detto è un'opinione su una lingua, non un
    permesso.

    Non solleva mai: se il modello non risponde, si ripiega su una regola
    scritta a mano che sa meno ma non sbaglia dalla parte pericolosa.
    """
    fermata = _anything_that_blocks(prep)
    if fermata is not None:
        prep.readiness, prep.readiness_says = fermata
        prep.conversation_ready = False
        return prep

    letto = await _what_the_model_sees(prep)
    if letto is None:
        letto = _what_we_can_tell_without_it(prep, operation)

    if letto.get("ambiguous"):
        prep.readiness = "AMBIGUOUS"
        prep.readiness_says = (
            str(letto.get("ambiguous_about") or "").strip()[:300]
            or "Non ho capito bene a cosa ti riferisci."
        )
        prep.conversation_ready = False
        return prep

    if not prep.goal:
        prep.goal = str(letto.get("understood_goal") or "").strip()[:300]

    prep.missing_information = _merge_what_is_missing(
        prep.missing_information, letto.get("missing") or [],
    )

    #     E QUI IL CANCELLO, CHE NON CHIEDE IL PERMESSO A NESSUNO.
    restano = prep.what_is_still_missing()
    if restano:
        prep.readiness = "NEEDS_INFO"
        prep.readiness_says = restano[0].question
        prep.conversation_ready = False
        return prep

    manca_ancora = _what_the_rules_still_require(prep, operation)
    if manca_ancora:
        prep.readiness = "NEEDS_INFO"
        prep.readiness_says = manca_ancora
        prep.conversation_ready = False
        return prep

    prep.readiness = "READY"
    prep.readiness_says = "Ho tutto quello che mi serve."
    prep.conversation_ready = True
    return prep


def _anything_that_blocks(prep: MissionPreparation) -> Optional[Tuple[str, str]]:
    """
    Le cose che non si negoziano, e che si guardano per prime.

        SENZA UN NUMERO NON C'È NIENTE DA PREPARARE.
    """
    if prep.number_rejected:
        return ("BLOCKED",
                "Mi hai detto che il numero non è quello giusto: "
                "dimmi tu quale devo chiamare.")
    if not prep.counterparty.strip():
        return ("BLOCKED", "Non mi hai detto chi devo chiamare.")
    if prep.selected_contact is None and not prep.contact_candidates:
        return ("BLOCKED",
                f"Non ho trovato un numero per {prep.counterparty}. "
                "Me lo dici tu?")
    if prep.selected_contact is None and prep.number_conflict:
        #     UNO ERA GIÀ CONFERMATO, E NE È SPUNTATO UN ALTRO.
        # Non si sostituisce e non si ignora: si dicono tutti e due, e si
        # chiede. Il confermato è in cima, perché è quello che valeva ieri.
        vecchio = next((c for c in prep.contact_candidates if c.trusted), None)
        nuovi = [c for c in prep.contact_candidates if not c.trusted]
        if vecchio is not None and nuovi:
            return ("AMBIGUOUS",
                    f"Per {vecchio.name} avevi già confermato il {vecchio.number}. "
                    f"Adesso ho trovato anche il {nuovi[0].number}. "
                    "Quale devo usare?")
    if prep.selected_contact is None:
        #     PIÙ DI UNO E NESSUNO SCELTO NON È «MANCA QUALCOSA».
        # È «non so di chi stai parlando», ed è una domanda diversa: «quale dei
        # due?» invece di «dimmi di più». Confonderle vuol dire mostrare una
        # richiesta di conferma su un numero che nessuno ha ancora indicato.
        return ("AMBIGUOUS",
                f"Ho trovato {len(prep.contact_candidates)} possibilità per "
                f"{prep.counterparty}: dimmi tu qual è quella giusta.")
    if not prep.number_confirmed:
        #     IL NOME TROVATO, NON LE PAROLE DELLA DOMANDA.
        # «Ho trovato questo numero per la mia ragazza» suonava strano; il nome
        # che la rubrica ha trovato è quello da confermare.
        chi = (prep.selected_contact.name if prep.selected_contact is not None
               else "") or prep.counterparty
        return ("NEEDS_INFO", f"Ho trovato questo numero per {chi}. È quello giusto?")
    return None


def _what_the_rules_still_require(
    prep: MissionPreparation, operation: str,
) -> str:
    """
    L'ultimo controllo, e non lo fa un modello.

        SPOSTARE SENZA SAPERE A QUANDO NON È SPOSTARE.

    Un modello che dicesse «pronta» su una missione così manderebbe ORA a
    chiedere a uno studio di spostare un appuntamento «a un altro orario», che
    è una frase che al telefono non vuol dire niente.
    """
    if (operation or "") in SERVE_UN_QUANDO and not prep.desired_state.get(
        "start_datetime"
    ):
        return "A quando vuoi che provi a spostarlo?"
    #     UN MESSAGGIO SENZA MESSAGGIO NON E' UNA TELEFONATA.
    if (operation or "") == "deliver_message" and not prep.message_to_deliver.strip():
        return f"Che cosa vuoi che dica a {prep.counterparty or 'questa persona'}?"
    return ""


def _merge_what_is_missing(
    gia: List[MissingInformation], dal_modello: List[Dict[str, Any]],
) -> List[MissingInformation]:
    """
    Unisce quello che si sapeva mancare con quello che dice il modello.

        UNA RISPOSTA GIÀ DATA NON SI RICHIEDE.

    È il motivo per cui questo non è una sostituzione: una valutazione che
    ricominciasse da capo rifarebbe la stessa domanda a chi aveva appena
    risposto, e non c'è modo di far sembrare quello un sistema che ascolta.
    """
    per_campo = {m.field: m for m in gia}
    fuori: List[MissingInformation] = list(gia)
    for riga in dal_modello[:8]:
        campo = str(riga.get("field") or "").strip()[:48]
        if not campo or campo in per_campo:
            continue
        domanda = str(riga.get("question") or "").strip()[:300]
        if not domanda:
            continue
        nuova = MissingInformation(
            field=campo, question=domanda,
            why=str(riga.get("why") or "").strip()[:200],
            already_known=str(riga.get("already_known") or "").strip()[:300],
        )
        per_campo[campo] = nuova
        fuori.append(nuova)
    return fuori[:8]


async def _what_the_model_sees(prep: MissionPreparation) -> Optional[Dict[str, Any]]:
    """
    Una sola chiamata, dal gestore di sempre.

        AL MODELLO NON ARRIVA NIENTE DI INTERNO.

    Non il numero, non gli identificativi, non la chiave della preparazione.
    Riceve la frase che una persona ha detto, quello che ORA sa detto in
    italiano, e le risposte già date. È tutto quello che serve per rispondere
    a «che cosa manca», ed è tutto quello che ha senso fargli leggere.
    """
    payload = {
        "cosa_ha_chiesto": prep.user_request,
        "chi_si_chiama": prep.counterparty,
        #     CHI E' GIA' STATO TROVATO. SENZA, IL MODELLO LO CERCAVA ANCORA.
        # Misurato: con la rubrica che aveva già risolto «la mia ragazza» in
        # Giulia, il valutatore ha scritto «non è specificato il nome della
        # fidanzata». Il nome sì; il numero no, che non gli serve.
        "contatto_trovato": (prep.selected_contact.name
                             if prep.selected_contact is not None else ""),
        "quello_che_ORA_sa_gia": prep.known_context,
        "risposte_gia_date": [
            {"domanda": m.question, "risposta": m.answer}
            for m in prep.missing_information if m.answered
        ],
        "dove_si_vuole_arrivare": prep.desired_state or {},
        #     PER UN MESSAGGIO, IL MESSAGGIO E' TUTTO.
        # Senza questa riga il modello chiedeva «a che ora?» a chi voleva solo
        # far sapere a qualcuno che gli vuole bene.
        "tipo_di_telefonata": prep.operation or "",
        "messaggio_da_consegnare": prep.message_to_deliver or "",
    }
    try:
        from llm.manager import get_manager

        esito = await get_manager().chat(
            system=IL_SISTEMA,
            user=json.dumps(payload, ensure_ascii=False),
            json_mode=True,
        )
    except Exception as e:
        logger.info("valutazione non riuscita: %s", type(e).__name__)
        return None
    return _parse(getattr(esito, "text", "") or "")


def _what_we_can_tell_without_it(
    prep: MissionPreparation, operation: str,
) -> Dict[str, Any]:
    """
    Quando il modello non risponde, si guarda quello che si può guardare.

        UN PROVIDER GIÙ NON DEVE FAR PARTIRE UNA TELEFONATA A CASO.

    Sa meno, e sbaglia dalla parte giusta: chiede una cosa in più invece di
    dare per pronta una missione che non lo è.
    """
    manca: List[Dict[str, Any]] = []
    if (operation or "") in SERVE_UN_QUANDO and not prep.desired_state.get(
        "start_datetime"
    ):
        manca.append({
            "field": "quando",
            "question": "A quando vuoi che provi a spostarlo?",
            "why": "senza un orario non ho niente da proporre",
            "already_known": "; ".join(prep.known_context[:2]),
        })
    return {
        "understood_goal": prep.goal or prep.user_request[:200],
        "ambiguous": False,
        "ambiguous_about": "",
        "missing": manca,
    }


def _parse(testo: str) -> Optional[Dict[str, Any]]:
    """Il JSON dentro la risposta, anche se è avvolto in altro."""
    grezzo = (testo or "").strip()
    if not grezzo:
        return None
    if grezzo.startswith("```"):
        grezzo = grezzo.split("```")[1] if "```" in grezzo[3:] else grezzo[3:]
        grezzo = grezzo[4:] if grezzo.lower().startswith("json") else grezzo
    apre, chiude = grezzo.find("{"), grezzo.rfind("}")
    if apre < 0 or chiude <= apre:
        return None
    try:
        letto = json.loads(grezzo[apre:chiude + 1])
    except Exception:
        return None
    return letto if isinstance(letto, dict) else None
