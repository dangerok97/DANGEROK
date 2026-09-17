"""
Quello che ORA porta con sé quando compone il numero.

    NON È UN DOSSIER: È QUELLO CHE SI TIENE A MENTE MENTRE SI TELEFONA.

Una persona che chiama uno studio per conto di un amico non porta con sé la
vita dell'amico. Porta il nome, il motivo, l'appuntamento di cui si parla, a
che ora vorrebbe spostarlo, fin dove può accettare, e che cosa invece deve
riportare indietro senza decidere. Sette cose, e stanno in testa.

    IL PACCHETTO PORTA IL NOME DEL CAMPO, MAI IL VALORE.

È la regola di V3.15 e vale identica qui. L'identificativo dell'appuntamento
non entra: chi parla non deve scegliere l'evento, quindi non deve sapere che
gli eventi hanno un nome. Non entra il numero. Non entra la chiave della
preparazione. C'è una prova che li cerca dentro e fallisce se li trova.

    E QUELLO CHE NON PUÒ DECIDERE VA DETTO PIÙ DI QUELLO CHE PUÒ.

Un mandato scritto solo in positivo lascia intendere che il resto sia
trattabile. Non lo è, e il momento in cui qualcuno se ne accorge è sempre
troppo tardi — è già stato detto a voce a uno sconosciuto.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from preparation.preparation import MissionPreparation

# Quello che nessuna telefonata può accettare per conto di una persona, mai.
# Non è un elenco che cresce con la missione: è il confine del mestiere.
NON_PUO_DECIDERE = (
    "accettare costi, penali o pagamenti",
    "prendere altri impegni a nome della persona",
    "dare dati personali che non siano stati autorizzati",
    "accettare un orario fuori da quelli consentiti",
)

DEI_GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì",
              "sabato", "domenica")


def build(prep: MissionPreparation, *, operation: str = "") -> Dict[str, Any]:
    """
    Il minimo che serve per reggere la conversazione, e niente di più.

    Si costruisce solo quando la preparazione è pronta: costruirlo prima
    vorrebbe dire avere un riassunto di una missione che non esiste, e
    qualcuno prima o poi lo leggerebbe come se esistesse.
    """
    contatto = prep.selected_contact
    voluto = _when_we_want_it(prep)
    adesso = _how_it_is_now(prep)

    brief: Dict[str, Any] = {
        # Chi: il nome, non il numero.
        "chi_chiamo": (contatto.name if contatto else prep.counterparty)[:160],
        "che_tipo_e": (contatto.kind if contatto else "unknown"),
        # Perché: la frase che una persona capisce, non l'operazione.
        "perche_chiamo": prep.goal or prep.user_request[:200],
        # A che cosa si riferisce: le frasi del contesto, non i riferimenti.
        "di_cosa_si_parla": list(prep.known_context[:4]),
        "come_sta_adesso": adesso,
        "cosa_voglio_ottenere": voluto,
        "posso_accettare": _what_else_is_allowed(prep),
        "non_posso_decidere": list(NON_PUO_DECIDERE),
        "cose_utili_da_sapere": _useful_facts(prep),
    }
    return {k: v for k, v in brief.items() if v not in ("", [], {}, None)}


def _how_it_is_now(prep: MissionPreparation) -> str:
    """Com'è la cosa adesso, detto come lo direbbe una persona."""
    for frase in prep.known_context:
        if ":" in frase:
            return frase[:200]
    return prep.known_context[0][:200] if prep.known_context else ""


def _when_we_want_it(prep: MissionPreparation) -> str:
    """Dove si vuole arrivare. Una frase, non un ISO."""
    quando = _read(prep.desired_state.get("start_datetime", ""))
    if quando is None:
        return str(prep.desired_state.get("says") or "")[:200]
    return f"{DEI_GIORNI[quando.weekday()]} {quando.day} alle {quando.strftime('%H:%M')}"


def _what_else_is_allowed(prep: MissionPreparation) -> List[str]:
    """
    Le alternative, dette a voce.

        SE NON C'È NESSUNA ALTERNATIVA, VA DETTO CHE NON CE NE SONO.

    Un elenco vuoto lascia intendere «vedi tu». Una riga esplicita chiude il
    discorso, ed è la differenza fra chi torna con un no e chi torna con un
    appuntamento che nessuno aveva autorizzato.
    """
    fuori: List[str] = []
    for grezzo in (prep.structured_authority.get("alternatives") or [])[:6]:
        quando = _read(str(grezzo))
        if quando is not None:
            fuori.append(
                f"{DEI_GIORNI[quando.weekday()]} {quando.day} "
                f"alle {quando.strftime('%H:%M')}"
            )
    if not fuori:
        return ["nient'altro: se non va, riporta indietro la risposta"]
    return fuori


def _useful_facts(prep: MissionPreparation) -> List[str]:
    """
    Quello che la persona ha risposto durante la preparazione.

    Sono fatti che ORA non aveva e che adesso ha perché qualcuno gliel'ha
    detto. Vanno in mano a chi telefona; il resto della memoria no.
    """
    return [
        f"{m.question} {m.answer}".strip()[:200]
        for m in prep.missing_information
        if m.answered and m.answer
    ][:4]


def _read(iso: str) -> Optional[datetime]:
    testo = (iso or "").strip()
    if not testo:
        return None
    try:
        return datetime.fromisoformat(testo.replace("Z", "+00:00"))
    except ValueError:
        return None


def reads_like(prep: MissionPreparation) -> str:
    """
    Il riassunto che legge chi ha chiesto la telefonata, prima che parta.

        «CHIAMERÒ LORENZO PER PROVARE A SPOSTARE…»

    Una frase sola, al futuro, in italiano, senza niente che assomigli a uno
    stato interno. È l'ultima cosa che qualcuno legge prima di dire di sì, e
    quindi è l'ultima occasione per accorgersi che ORA ha capito storto.
    """
    contatto = prep.selected_contact
    chi = (contatto.name if contatto else prep.counterparty) or "questa persona"
    adesso = _how_it_is_now(prep)
    voluto = _when_we_want_it(prep)

    righe = [f"Chiamerò {chi}"]
    if prep.goal:
        righe.append(f"per {_lowered(prep.goal)}")
    #     E NON SI DICE DUE VOLTE LA STESSA COSA.
    # L'obiettivo, scritto da chi legge la richiesta, spesso contiene già
    # l'appuntamento — «spostare la partita di venerdì alle 20:30». Ripeterlo
    # fra parentesi subito dopo non aggiunge niente e fa sembrare la frase
    # scritta da una macchina che non si rilegge.
    if adesso and not _already_said(adesso, prep.goal):
        righe.append(f"({adesso})")
    if voluto:
        righe.append(f"a {voluto}")
    frase = " ".join(righe).strip() + "."

    alternative = [
        a for a in _what_else_is_allowed(prep)
        if not a.startswith("nient'altro")
    ]
    if alternative:
        frase += " Se non può, posso accettare " + " o ".join(alternative) + "."
    return frase


def _already_said(pezzo: str, dentro: str) -> bool:
    """Se questa informazione è già nella frase, con altre parole."""
    orario = pezzo.split("alle")[-1].strip()[:5] if "alle" in pezzo else ""
    return bool(orario) and orario in (dentro or "")


def _lowered(testo: str) -> str:
    """Una frase che entra in mezzo a un'altra non comincia in maiuscolo."""
    pulito = (testo or "").strip()
    return pulito[:1].lower() + pulito[1:] if pulito else ""
