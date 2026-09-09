"""
Chi merita di essere guardato, e chi no — deciso contando, non giudicando.

    UNA CHIAMATA PER OGNI RIGA DI UN ESTRATTO CONTO E' UN PRODOTTO CHE NON
    SI PUO' PERMETTERE DI ESISTERE.

Sei mesi di conto sono qualche centinaio di movimenti. Interpretarli uno per
uno vorrebbe dire qualche centinaio di chiamate al giudizio per una persona
sola, e la seconda volta altrettante — un costo che cresce con la vita di chi
lo usa, e un rumore che cresce insieme.

La forma giusta e' un'altra e sta tutta in una frase: **si raggruppa con
l'aritmetica, si interpreta una volta per gruppo.** Sei bonifici uguali a
distanza di trenta giorni sono *una* domanda — «che cos'e' questa cosa che si
ripete?» — non sei.

E prima ancora, una domanda piu' economica: c'e' qualcosa da capire?

    UN MOVIMENTO SOLO, SENZA NIENTE INTORNO, NON E' INTERPRETABILE DA NESSUNO.

Un caffe' isolato non ha una spiegazione da trovare: non si ripete, non c'e'
un'email che ne parli, non appartiene a niente che stia succedendo. Chiedere
al giudizio cosa sia significa pagare per sentirsi dire «e' un caffe'». Resta
osservato — e' successo, e il registro lo tiene — e se un giorno si ripete, o
se arriva qualcosa che lo riguarda, torna in coda da solo.

Attenzione a cosa questo filtro *non* fa. Non guarda l'importo: quattromila
euro dal notaio e dodici euro al bar passano dallo stesso cancello, e il
notaio entra perche' c'e' un preventivo e una casa che si sta comprando, non
perche' e' grosso. Non guarda la descrizione: non c'e' nessun elenco di
esercenti qui, come non ce n'e' altrove. Guarda solo se esiste materiale con
cui ragionare — che e' una domanda sull'informazione disponibile, non sul
significato.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from financial.observation import (
    BankObservation,
    ObservationStore,
    _grouping_key,
)

logger = logging.getLogger("ora.financial.batching")

OBSERVATIONS = "financial_observations"

# Quanti gruppi al massimo si guardano in un passaggio. Non e' una soglia sul
# significato: e' quanto lavoro sta dentro un giro senza farlo durare piu' del
# giro stesso. Quelli che avanzano restano in coda e toccano al prossimo.
MAX_GROUPS_PER_PASS = 6

# Quanto intorno si guarda per sapere se c'e' materiale. Stessa finestra che
# usa il giudizio quando raccoglie le prove: due finestre diverse renderebbero
# possibile far entrare un movimento e poi non trovargli niente accanto.
NEARBY_DAYS = 21


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


async def read_what_is_new(
    db, owner_id: str, *, language: str = "it",
    max_groups: int = MAX_GROUPS_PER_PASS,
) -> Dict[str, Any]:
    """
    Guarda i movimenti mai interpretati, a gruppi, e chiama il giudizio il
    minimo numero di volte che serve.

    Torna cosa e' stato fatto e cosa e' stato lasciato stare, perche' «non ho
    chiamato» e' un esito quanto «ho chiamato»: senza distinguerli, un
    silenzio per prudenza e un silenzio per guasto si assomigliano troppo.
    """
    from financial.movements import look_at_a_movement

    fresh = await _never_looked_at(db, owner_id)
    if not fresh:
        return {"gruppi": 0, "interpretati": 0, "rimandati": 0, "chiamate": 0}

    everything = await ObservationStore(db).history(owner_id)
    groups = _group(fresh)

    # Prima i gruppi che si ripetono di piu': se il budget di un passaggio
    # finisce, deve finire sulle cose piu' piccole, non sulle piu' grosse.
    order = sorted(groups.items(), key=lambda kv: -len(kv[1]))

    calls = 0
    understood: List[Dict[str, Any]] = []
    postponed = 0

    for key, members in order:
        if calls >= max_groups:
            break
        members.sort(key=lambda o: str(o.booked_at))
        repeats = len([o for o in everything if _grouping_key(o) == key])

        if not await _worth_asking(db, owner_id, members, repeats=repeats):
            await _mark(db, owner_id, members, outcome="rimandato")
            postponed += len(members)
            continue

        # Il piu' recente rappresenta il gruppo: il giudizio riceve lui, con
        # i conti su tutti gli altri gia' fatti. E' una domanda sola su una
        # cosa che si ripete, che e' esattamente la domanda giusta.
        newest = members[-1]
        calls += 1
        outcome = await look_at_a_movement(db, newest, language=language)
        understood.append({"quanti": len(members), **outcome})
        await _mark(db, owner_id, members, outcome=str(outcome.get("outcome") or ""))

    return {
        "gruppi": len(groups),
        "interpretati": len(understood),
        "rimandati": postponed,
        # Il numero che conta davvero: quante volte si e' parlato con il
        # giudizio. Deve restare molto piu' piccolo del numero di movimenti.
        "chiamate": calls,
        "esiti": understood,
    }


async def _never_looked_at(db, owner_id: str) -> List[BankObservation]:
    """Le righe che nessuno ha ancora provato a capire."""
    rows = await db[OBSERVATIONS].find(
        {"owner_id": owner_id, "looked_at": {"$exists": False}}, {"_id": 0},
    ).sort("booked_at", -1).to_list(400)
    out: List[BankObservation] = []
    for row in rows:
        try:
            out.append(BankObservation.model_validate(row))
        except Exception:
            continue
    return out


def _group(observations: List[BankObservation]) -> Dict[str, List[BankObservation]]:
    """
    Le righe messe insieme per chi c'e' dall'altra parte. Solo aritmetica.

    La chiave e' la stessa che usa il calcolo delle ricorrenze — la
    controparte se la banca la da', altrimenti la descrizione grezza. Non e'
    un raggruppamento semantico e non pretende di esserlo: serve a non fare
    sei domande dove ce n'e' una.
    """
    out: Dict[str, List[BankObservation]] = {}
    for observation in observations:
        out.setdefault(_grouping_key(observation), []).append(observation)
    return out


async def _worth_asking(
    db, owner_id: str, members: List[BankObservation], *, repeats: int,
) -> bool:
    """
    C'e' abbastanza materiale perche' qualcuno possa capirci qualcosa?

    Tre modi di rispondere di sì, e nessuno guarda l'importo o la
    descrizione:

      *Si ripete.* Una cosa vista piu' volte ha una forma, e la forma e' la
      domanda: «cos'e' questa cosa che torna ogni mese?».

      *C'e' qualcosa intorno.* Un'email o un documento nella stessa finestra
      possono spiegarla. Il giudizio decidera' se c'entrano davvero — questo
      livello sa solo che esistono.

      *Sta succedendo qualcosa.* Se la persona ha una situazione aperta, un
      movimento puo' appartenerle; senza situazioni aperte non c'e' niente a
      cui appartenere.

    Un «no» non e' un giudizio sul movimento: e' l'ammissione che adesso non
    ci sono elementi. La riga resta, e se cambia qualcosa torna in coda.
    """
    if repeats > 1:
        return True
    if await _has_situations(db, owner_id):
        return True
    return await _has_nearby(db, owner_id, members[-1])


async def _has_situations(db, owner_id: str) -> bool:
    try:
        found = await db.life_objects.find_one(
            {"user_id": owner_id, "status": {"$ne": "archived"}}, {"_id": 0, "id": 1},
        )
    except Exception as e:
        logger.info("situation probe soft-fail: %s", type(e).__name__)
        return False
    return bool(found)


async def _has_nearby(db, owner_id: str, observation: BankObservation) -> bool:
    """C'e' un'email o un documento nella finestra intorno a questo movimento."""
    when = _moment(observation.booked_at)
    if when is None:
        return False
    try:
        found = await db.ingestion_events.find_one(
            {
                "user_id": owner_id,
                "source_record_type": {"$in": ["email_message", "document"]},
                "ingested_at": {
                    "$gte": (when - timedelta(days=NEARBY_DAYS)).isoformat(),
                    "$lte": (when + timedelta(days=NEARBY_DAYS)).isoformat(),
                },
            },
            {"_id": 0, "id": 1},
        )
    except Exception as e:
        logger.info("nearby probe soft-fail: %s", type(e).__name__)
        return False
    return bool(found)


async def _mark(
    db, owner_id: str, members: List[BankObservation], *, outcome: str,
) -> None:
    """
    Segna che queste righe sono state guardate, e com'e' andata.

    Senza questo, ogni passaggio riguarderebbe tutto da capo: la stessa
    domanda, lo stesso costo, per sempre. Il segno sta sull'osservazione e
    non altrove perche' e' dell'osservazione che si parla.
    """
    when = datetime.now(timezone.utc).isoformat()
    try:
        await db[OBSERVATIONS].update_many(
            {"owner_id": owner_id,
             "transaction_ref": {"$in": [o.transaction_ref for o in members]}},
            {"$set": {"looked_at": when, "look_outcome": outcome}},
        )
    except Exception as e:
        logger.info("mark soft-fail: %s", type(e).__name__)
