"""
Quello che ORA sa già, e che quindi non deve chiedere.

    «CHIAMA LORENZO E SPOSTA IL CALCETTO».

Dentro questa frase c'è tutto tranne le due cose che servono: il numero di
Lorenzo e l'orario nuovo. Il resto — quale partita, quando è adesso, che
appuntamento è in calendario — ORA ce l'ha già, e chiederlo sarebbe come
chiedere a qualcuno di ripetere una cosa che gli si è appena sentito dire.

    OGNI DOMANDA CHE NON SI FA È UNA COSA CHE SI SAPEVA.

È il motivo per cui questo file viene prima di quello che chiede. Non
raccoglie tutto: cerca quello che la richiesta nomina, e si ferma. Un contesto
che porta dentro tutta la vita di una persona per spostare una partita a
calcetto non è un contesto: è un archivio che qualcuno dovrà leggere.

    E QUELLO CHE TROVA LO DICE IN ITALIANO.

`known_context` sono frasi, non righe di database — «la partita è venerdì alle
20:30» — perché finiscono in due posti che leggono persone: la domanda che ORA
fa, e il riassunto che ORA legge prima di telefonare. I riferimenti canonici
viaggiano a parte, e non escono mai da qui verso un modello.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ora.preparation.context")

# Quanto indietro e quanto avanti si guarda nel calendario. Una richiesta al
# telefono parla quasi sempre di questa settimana o della prossima; allargare
# vuol dire trovare l'appuntamento dell'anno scorso con lo stesso titolo.
INDIETRO_GIORNI = 3
AVANTI_GIORNI = 45

# Le parole che in italiano dicono «questa cosa qui», e che da sole non
# identificano niente. Non entrano nella ricerca: cercare «la» non trova.
PAROLE_VUOTE = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "del", "della",
    "di", "da", "a", "al", "alla", "e", "che", "con", "per", "chiama",
    "chiamare", "digli", "dille", "dirgli", "sposta", "spostare", "spostala",
    "disdici", "prenota", "mio", "mia", "miei", "mie", "suo", "sua", "poi",
    "anche", "alle", "ore", "prova", "provare", "provi", "vorrei", "vuoi",
}


class WhatWeFound:
    """Un pezzo di contesto: come si dice, e a che cosa punta."""

    def __init__(self, says: str, *, ref: str = "", kind: str = "",
                 when: str = "", minutes: int = 0) -> None:
        self.says = says
        self.ref = ref
        self.kind = kind
        self.when = when
        self.minutes = minutes


async def what_ora_already_knows(
    db, *, owner_id: str, user_request: str, counterparty: str = "",
) -> Tuple[List[str], Dict[str, str], List[WhatWeFound]]:
    """
    Cerca fra le cose di questa persona quello che la richiesta nomina.

    Torna tre cose: le frasi da mostrare, i riferimenti canonici da tenere in
    tasca, e i pezzi interi per chi deve ragionarci sopra.

    Non solleva: un contesto che non si riesce a leggere è un contesto vuoto,
    e un contesto vuoto porta a una domanda in più — non a un guasto.
    """
    parole = _the_words_that_mean_something(user_request, counterparty)
    trovati: List[WhatWeFound] = []

    try:
        trovati.extend(await _from_the_calendar(db, owner_id, parole))
    except Exception as e:
        logger.info("calendario non letto: %s", type(e).__name__)
    try:
        trovati.extend(await _from_commitments(db, owner_id, parole))
    except Exception as e:
        logger.info("impegni non letti: %s", type(e).__name__)
    try:
        trovati.extend(await _from_study(db, owner_id, parole))
    except Exception as e:
        logger.info("studio non letto: %s", type(e).__name__)
    try:
        trovati.extend(await _from_past_missions(db, owner_id, parole))
    except Exception as e:
        logger.info("telefonate precedenti non lette: %s", type(e).__name__)

    #     UNA COSA SOLA PER TIPO, E LA PIÙ VICINA NEL TEMPO.
    # Due partite a calcetto nel raggio di un mese non sono due contesti: sono
    # un'ambiguità, e la si risolve chiedendo — non prendendo la prima.
    frasi: List[str] = []
    refs: Dict[str, str] = {}
    for pezzo in trovati[:8]:
        if pezzo.says not in frasi:
            frasi.append(pezzo.says)
        if pezzo.ref and pezzo.kind and pezzo.kind not in refs:
            refs[pezzo.kind] = pezzo.ref
    return frasi, refs, trovati


def _the_words_that_mean_something(richiesta: str, chi: str) -> List[str]:
    """
    Le parole della richiesta che possono identificare qualcosa.

    Tolte le parole vuote e il nome di chi si chiama — cercare «Lorenzo» fra
    gli appuntamenti troverebbe il contatto, non la partita.
    """
    del_nome = {p.lower() for p in re.split(r"\W+", chi or "") if p}
    fuori: List[str] = []
    for p in re.split(r"\W+", (richiesta or "").lower()):
        if len(p) < 3 or p in PAROLE_VUOTE or p in del_nome or p in fuori:
            continue
        fuori.append(p)
    return fuori[:10]


def _does_it_mention(testo: str, parole: List[str]) -> bool:
    """Se questo testo contiene almeno una delle parole che contano."""
    dentro = {p for p in re.split(r"\W+", (testo or "").lower()) if p}
    return any(p in dentro for p in parole)


async def _from_the_calendar(db, owner_id: str, parole: List[str]) -> List[WhatWeFound]:
    if not parole:
        return []
    adesso = datetime.now(timezone.utc)
    da = (adesso - timedelta(days=INDIETRO_GIORNI)).isoformat()
    a = (adesso + timedelta(days=AVANTI_GIORNI)).isoformat()
    righe = await db.calendar_event_drafts.find(
        {"user_id": owner_id, "status": {"$ne": "cancelled"},
         "start_datetime": {"$gt": da, "$lt": a}},
        {"_id": 0, "id": 1, "title": 1, "start_datetime": 1, "end_datetime": 1,
         "timezone": 1},
    ).to_list(200)
    fuori: List[WhatWeFound] = []
    for r in sorted(righe, key=lambda x: x.get("start_datetime") or ""):
        titolo = str(r.get("title") or "")
        if not _does_it_mention(titolo, parole):
            continue
        quando = _read(str(r.get("start_datetime") or ""))
        fuori.append(WhatWeFound(
            f"{titolo}: {_in_italiano(quando)}" if quando else titolo,
            ref=str(r.get("id") or ""), kind="calendar",
            when=str(r.get("start_datetime") or ""),
            minutes=_how_long(r),
        ))
    return fuori


async def _from_commitments(db, owner_id: str, parole: List[str]) -> List[WhatWeFound]:
    if not parole:
        return []
    righe = await db.decisions.find(
        {"user_id": owner_id}, {"_id": 0, "id": 1, "title": 1, "action_state": 1,
                                "status": 1},
    ).to_list(200)
    fuori: List[WhatWeFound] = []
    for r in righe:
        titolo = str(r.get("title") or "")
        if not _does_it_mention(titolo, parole):
            continue
        stato = ((r.get("action_state") or {}).get("status")
                 or r.get("status") or "aperto")
        if str(stato) in ("completed", "dismissed"):
            continue
        fuori.append(WhatWeFound(
            f"Hai un impegno aperto: {titolo}",
            ref=str(r.get("id") or ""), kind="commitments",
        ))
    return fuori


async def _from_study(db, owner_id: str, parole: List[str]) -> List[WhatWeFound]:
    if not parole:
        return []
    righe = await db.study_sessions.find(
        {"user_id": owner_id, "status": "planned"},
        {"_id": 0, "id": 1, "title": 1, "starts_at": 1, "duration_minutes": 1},
    ).to_list(200)
    fuori: List[WhatWeFound] = []
    for r in sorted(righe, key=lambda x: x.get("starts_at") or ""):
        titolo = str(r.get("title") or "")
        if not _does_it_mention(titolo, parole):
            continue
        quando = _read(str(r.get("starts_at") or ""))
        fuori.append(WhatWeFound(
            f"Sessione di studio «{titolo}»: {_in_italiano(quando)}"
            if quando else f"Sessione di studio «{titolo}»",
            ref=str(r.get("id") or ""), kind="study",
            when=str(r.get("starts_at") or ""),
            minutes=int(r.get("duration_minutes") or 0),
        ))
    return fuori


async def _from_past_missions(db, owner_id: str, parole: List[str]) -> List[WhatWeFound]:
    """
    Quello che ORA ha già fatto al telefono per questa cosa.

        SE CI ABBIAMO GIÀ PROVATO, VA DETTO.

    Non cambia l'esito della preparazione, ma cambia la frase che una persona
    legge — e sapere che si sta richiamando è diverso da sapere che si sta
    chiamando.
    """
    if not parole:
        return []
    righe = await db["phone_calls"].find(
        {"owner_id": owner_id, "state": "ended"},
        {"_id": 0, "calling_whom": 1, "mandate": 1, "ended_at": 1, "metrics": 1},
    ).to_list(120)
    fuori: List[WhatWeFound] = []
    for r in sorted(righe, key=lambda x: x.get("ended_at") or "", reverse=True):
        perche = str(((r.get("mandate") or {}).get("why_calling")) or "")
        if not _does_it_mention(perche, parole):
            continue
        esito = str(((r.get("metrics") or {}).get("outcome") or {}).get("status") or "")
        come = {"success": "ed era andata bene", "needs_user": "e serviva una tua decisione",
                "failed": "e non era andata"}.get(esito, "")
        fuori.append(WhatWeFound(
            f"ORA aveva già telefonato per questo{(' ' + come) if come else ''}.",
            kind="past_call",
        ))
        break
    return fuori


# ---------------------------------------------------------------------------
# Leggere quello che la persona risponde
# ---------------------------------------------------------------------------

_UN_ORARIO = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
_SOLO_ORA = re.compile(r"\b(?:alle|ore|le)\s+([01]?\d|2[0-3])\b")

I_GIORNI = {
    "lunedì": 0, "lunedi": 0, "martedì": 1, "martedi": 1, "mercoledì": 2,
    "mercoledi": 2, "giovedì": 3, "giovedi": 3, "venerdì": 4, "venerdi": 4,
    "sabato": 5, "domenica": 6,
}

I_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
}


def the_times_inside(testo: str, *, da: Optional[datetime] = None) -> List[str]:
    """
    Gli orari che una frase contiene, in ordine, come ISO.

        «SABATO ALLE 19, AL MASSIMO ALLE 20» SONO DUE ORARI.

    Il primo è quello che si vuole, il secondo è fin dove si può arrivare — e
    la differenza la fa chi chiama questa funzione, non questa funzione. Qui
    si legge e basta: interpretare che cosa significhi il secondo è una
    decisione, e le decisioni stanno altrove.

    Non indovina un giorno che non c'è: se la frase dice solo un'ora, l'ora
    resta attaccata al giorno che le si passa.
    """
    riferimento = da or datetime.now()
    giorno = _the_day_inside(testo, riferimento)
    ore = [(int(h), int(m)) for h, m in _UN_ORARIO.findall(testo or "")]
    if not ore:
        ore = [(int(h), 0) for h in _SOLO_ORA.findall(testo or "")]
    if not ore or giorno is None:
        return []
    return [
        f"{giorno.isoformat()}T{h:02d}:{m:02d}:00" for h, m in ore[:4]
    ]


def _the_day_inside(testo: str, riferimento: datetime):
    """Il giorno che la frase nomina, o quello di riferimento."""
    basso = (testo or "").lower()

    #     UNA DATA SCRITTA PER ESTESO VINCE SU UN NOME DI GIORNO.
    esteso = re.search(r"\b(\d{1,2})\s+(" + "|".join(I_MESI) + r")\b", basso)
    if esteso:
        giorno, mese = int(esteso.group(1)), I_MESI[esteso.group(2)]
        anno = riferimento.year + (1 if mese < riferimento.month else 0)
        try:
            return datetime(anno, mese, giorno).date()
        except ValueError:
            return None

    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", basso)
    if iso:
        try:
            return datetime(*(int(g) for g in iso.groups())).date()
        except ValueError:
            return None

    if "dopodomani" in basso:
        return (riferimento + timedelta(days=2)).date()
    if "domani" in basso:
        return (riferimento + timedelta(days=1)).date()
    if "oggi" in basso or "stasera" in basso:
        return riferimento.date()

    for nome, indice in I_GIORNI.items():
        if re.search(rf"\b{nome}\b", basso):
            #     «SABATO» È IL PROSSIMO SABATO, NON QUELLO PASSATO.
            avanti = (indice - riferimento.weekday()) % 7 or 7
            return (riferimento + timedelta(days=avanti)).date()
    return riferimento.date()


# ---------------------------------------------------------------------------
# Orologi e parole
# ---------------------------------------------------------------------------

DEI_GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì",
              "sabato", "domenica")


def _in_italiano(quando: Optional[datetime]) -> str:
    """
    «venerdì 19 alle 20:30». Come lo direbbe una persona.

        E ALLE 20:30 DI CHI LEGGE, NON DEL SERVER.

    Gli appuntamenti sono scritti con il fuso addosso, e alcuni in UTC. Una
    partita delle 20:30 mostrata come «18:30» è un contesto sbagliato, e su un
    contesto sbagliato ORA costruisce una domanda sbagliata — o peggio, non la
    fa perché crede di sapere.
    """
    if quando is None:
        return ""
    locale = _where_they_are(quando)
    return (f"{DEI_GIORNI[locale.weekday()]} {locale.day} "
            f"alle {locale.strftime('%H:%M')}")


def _where_they_are(quando: datetime) -> datetime:
    """Lo stesso istante, nel fuso di chi ha chiesto la telefonata."""
    if quando.tzinfo is None:
        return quando
    try:
        from zoneinfo import ZoneInfo

        from telephone.mission import _where_they_are as dove

        return quando.astimezone(ZoneInfo(dove()))
    except Exception:
        return quando


def _read(iso: str) -> Optional[datetime]:
    testo = (iso or "").strip()
    if not testo:
        return None
    try:
        return datetime.fromisoformat(testo.replace("Z", "+00:00"))
    except ValueError:
        return None


def _how_long(riga: Dict[str, Any]) -> int:
    inizio, fine = _read(str(riga.get("start_datetime") or "")), \
        _read(str(riga.get("end_datetime") or ""))
    if inizio is None or fine is None:
        return 0
    return max(0, int((fine - inizio).total_seconds() // 60))
