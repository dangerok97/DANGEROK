"""
Da una riga di conto a qualcosa che ORA sa — passando da tutti i controlli.

    IL CODICE NORMALIZZA. L'AI INTERPRETA. LA GOVERNANCE DECIDE COSA DIVENTA
    CONOSCENZA.

Il percorso, per intero e senza scorciatoie:

    osservazione bancaria
    -> conti su quello che si e' visto prima  (aritmetica, qui)
    -> quello che c'e' intorno                (email, documenti, vita)
    -> giudizio                               (cosa sembra, quanto sicuro)
    -> candidato a fatto economico            (solo se il giudizio lo dice)
    -> governance                             (cosa merita di durare)
    -> modello della vita + situazioni

Quello che questo file non fa, mai: guardare `raw_description` e concludere
qualcosa. Non c'e' un elenco di esercenti, non c'e' una soglia sul numero di
ripetizioni che fa scattare «ricorrente», non c'e' una parola che mappa a una
categoria. Ci sono numeri calcolati e una chiamata a un giudizio.

E una cosa che il giudizio deve poter dire ed e' la piu' importante di tutte:
«un addebito ricorrente che non ho ancora identificato». Un nome sbagliato
detto con sicurezza e' peggio di nessun nome.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from financial.models import FinancialFact, Money, Provenance
from financial.observation import (
    BankObservation,
    ObservationStore,
    features_of,
)
from financial.store import FinancialStore

logger = logging.getLogger("ora.financial.movements")

# Quanto indietro e in avanti si guarda per trovare qualcosa che parli dello
# stesso movimento — un'email di addebito, una fattura. Una finestra, non un
# criterio: cosa sia pertinente lo decide il giudizio, questo decide solo
# quanta roba vale la pena mettergli davanti.
NEARBY_DAYS = 21


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


async def look_at_a_movement(
    db,
    observation: BankObservation,
    *,
    language: str = "it",
) -> Dict[str, Any]:
    """
    Guarda un movimento e, se il giudizio dice che vale, portalo avanti.

    Torna sempre cosa e' successo, incluso quando non e' successo niente:
    `unclear` e `noise` sono esiti, e `no_answer` — il giudizio non e'
    arrivato — e' un terzo esito diverso da entrambi.
    """
    from financial.reasoning import read_a_movement

    observations = ObservationStore(db)
    await observations.record(observation)

    history = [
        o for o in await observations.history(observation.owner_id)
        if o.id != observation.id
    ]
    pattern = features_of(observation, history)

    store = FinancialStore(db)
    known = [f.for_ai() for f in await store.known(observation.owner_id, limit=40)]

    answer = await read_a_movement(
        observation.for_ai(),
        pattern=pattern.for_ai(),
        life=await _life(db, observation.owner_id),
        already_known=known,
        nearby_evidence=await _nearby(db, observation),
        situations=await _situations(db, observation.owner_id),
        goals=await _goals(db, observation.owner_id),
        language=language,
    )
    if answer is None:
        # Silenzio del giudizio. L'osservazione resta — e' successa — ma
        # nessuno ha concluso niente su di essa.
        return {"outcome": "no_answer", "observation_id": observation.id}

    kind = answer["interpreted_kind"]
    if kind == "noise":
        return {
            "outcome": "noise", "observation_id": observation.id,
            "why": answer.get("reason", ""),
        }

    # UN NOME DETTO A META' NON E' UN NOME.
    #
    # Il giudizio, messo davanti a «-14,99 € ogni mese» e nient'altro, ha
    # risposto «Abbonamento mensile» — che e' plausibile e non lo sa nessuno.
    # Poteva essere una polizza, una quota associativa, un addebito che
    # qualcun altro ha attivato sulla sua carta. La regolarita' e l'importo
    # non dicono cosa una cosa sia.
    #
    # Questo controllo non decide *cosa* sia quel movimento — non saprebbe —
    # ma decide che una supposizione non entri nel registro con l'aria di un
    # fatto. E' la stessa disciplina della governance, un gradino prima: chi
    # non e' sicuro puo' dire quello che ha visto, non battezzarlo.
    #
    # Quello che la persona riceve non peggiora: «un addebito ricorrente di
    # €14,99 che non ho ancora identificato» e' vero, ed e' azionabile.
    unsure = answer["certainty"] != "high"
    if kind == "unclear" or unsure or not answer.get("should_persist"):
        # Il caso piu' comune, e quello che va detto bene: si e' visto
        # qualcosa, non si e' capito cosa, e va scritto proprio cosi'.
        return {
            "outcome": "seen_not_understood",
            "observation_id": observation.id,
            # Perche' non e' stato preso per buono: e' la differenza fra «non
            # ho capito» e «ho capito che non conta».
            "why_not_kept": (
                "il giudizio non e' abbastanza sicuro" if unsure
                else "non e' una cosa che valga la pena ricordare"
            ),
            "pattern_status": answer["pattern_status"],
            "recurring_likelihood": answer.get("recurring_likelihood", "low"),
            "certainty": answer["certainty"],
            "missing_information": list(answer.get("missing_information") or [])[:6],
            "how_to_say_it": _how_to_say_it(answer, observation),
            "should_ask_user": bool(answer.get("should_ask_user")),
        }

    fact = _fact_from(observation, answer, pattern_status=answer["pattern_status"])
    fact.about_refs = _mine(
        answer.get("linked_situations"),
        {s["id"] for s in await _situations(db, observation.owner_id)},
    )

    kept = await store.remember(fact)

    from financial.durable import propose

    governed = await propose(db, fact)
    return {
        "outcome": kept["outcome"],
        "observation_id": observation.id,
        "fact_id": fact.id,
        "what": fact.what,
        "certainty": answer["certainty"],
        "pattern_status": answer["pattern_status"],
        "governance": governed["decision"],
        "in_life_model": governed["persisted"],
        "linked_situations": list(fact.about_refs),
    }


def _how_to_say_it(answer: Dict[str, Any], observation: BankObservation) -> str:
    """
    Come si dice a una persona una cosa che non si e' capita.

    Non «spesa non categorizzata», che e' il modo in cui lo direbbe un
    software. Quello che serve sapere e' che c'e', quanto e', ogni quanto —
    e che ORA non ha ancora capito cosa sia.
    """
    amount = Money(
        amount=abs(observation.amount), currency=observation.currency,
    ).for_human()
    if answer["pattern_status"] in ("recurring", "new_recurrence"):
        return f"Un addebito ricorrente di {amount} che non ho ancora identificato."
    if answer["pattern_status"] == "amount_changed":
        return f"Un addebito ricorrente che questa volta è di {amount}."
    return f"Un movimento di {amount} che non ho ancora identificato."


def _fact_from(
    observation: BankObservation, answer: Dict[str, Any], *, pattern_status: str,
) -> FinancialFact:
    """
    Il fatto, costruito da quello che il giudizio ha detto — e solo da quello.

    Il nome viene da `likely_label`, che il giudizio compila quando ha capito
    e lascia vuoto quando no. Se e' vuoto qui non ci si arriva: un fatto
    senza nome non e' un fatto, e il ramo `unclear` esce prima.
    """
    label = str(answer.get("likely_label") or "").strip()
    return FinancialFact(
        owner_id=observation.owner_id,
        kind=answer["interpreted_kind"],
        what=label[:160] or "movimento non identificato",
        money=Money(amount=abs(observation.amount), currency=observation.currency),
        direction=observation.direction,
        cadence=(
            "recurring" if pattern_status in ("recurring", "new_recurrence",
                                              "amount_changed")
            else "one_time" if pattern_status in ("one_off", "past_receipt")
            else "unknown"
        ),
        occurred_at=observation.booked_at,
        counterparty=observation.counterparty,
        # `observed` e' il grado giusto: e' un movimento che e' davvero
        # avvenuto. Quanto sia *capito* e' un'altra cosa, e viaggia negli
        # unknowns e nel giudizio.
        confidence="observed" if answer["certainty"] == "high" else "inferred",
        provenance=[Provenance(
            source="bank",
            source_ref=observation.transaction_ref,
            how_directly="l'ho visto sul tuo conto",
        )],
        source_refs=[observation.transaction_ref],
        unknowns=[str(m)[:120] for m in (answer.get("missing_information") or [])][:6],
    )


def _mine(named: Any, owned: set) -> List[str]:
    """Solo i riferimenti che appartengono davvero a questa persona."""
    return [str(x) for x in (named or []) if str(x) in owned][:6]


async def _nearby(db, observation: BankObservation) -> List[Dict[str, Any]]:
    """
    Cosa altro e' stato osservato intorno a questo movimento.

    Email e documenti gia' normalizzati: non si rilegge niente e non si
    interpreta niente qui: si mette a disposizione. Che una fattura di
    centodiciotto euro arrivata tre giorni prima c'entri con un addebito di
    centodiciotto euro e' un giudizio, e lo fa chi di dovere.
    """
    when = _moment(observation.booked_at)
    if when is None:
        return []
    since = (when - timedelta(days=NEARBY_DAYS)).isoformat()
    until = (when + timedelta(days=NEARBY_DAYS)).isoformat()
    try:
        rows = await db.ingestion_events.find(
            {
                "user_id": observation.owner_id,
                "source_record_type": {"$in": ["email_message", "document"]},
                "ingested_at": {"$gte": since, "$lte": until},
            },
            {"_id": 0, "normalized_payload": 1, "source_record_type": 1},
        ).sort("ingested_at", -1).to_list(12)
    except Exception as e:
        logger.info("nearby read soft-fail: %s", type(e).__name__)
        return []

    from ingestion.reading import plain

    out = []
    for row in rows:
        payload = plain(row.get("normalized_payload"))
        out.append({
            "kind": row.get("source_record_type"),
            "about": str(payload.get("subject") or payload.get("title") or "")[:200],
            "when": str(payload.get("received_at") or payload.get("created_at") or "")[:19],
        })
    return out


async def _life(db, owner_id: str) -> Dict[str, Any]:
    try:
        memories = await db.memories.find(
            {"user_id": owner_id, "status": "active"},
            {"_id": 0, "content": 1},
        ).sort("updated_at", -1).to_list(12)
    except Exception as e:
        logger.info("life read soft-fail: %s", type(e).__name__)
        return {}
    return {
        "things_ora_knows": [
            str(m.get("content"))[:200] for m in memories if m.get("content")
        ],
    }


async def _situations(db, owner_id: str) -> List[Dict[str, Any]]:
    try:
        rows = await db.life_objects.find(
            {"user_id": owner_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "title": 1, "type": 1},
        ).to_list(12)
    except Exception as e:
        logger.info("situation read soft-fail: %s", type(e).__name__)
        return []
    return [
        {"id": r.get("id"), "what_it_is": str(r.get("title") or "")[:160],
         "kind": r.get("type")}
        for r in rows
    ]


async def _goals(db, owner_id: str) -> List[Dict[str, Any]]:
    try:
        rows = await db.agent_goals.find(
            {"owner_id": owner_id, "status": "active"},
            {"_id": 0, "id": 1, "objective": 1},
        ).to_list(10)
    except Exception as e:
        logger.info("goal read soft-fail: %s", type(e).__name__)
        return []
    return [
        {"id": r.get("id"), "what_they_want": str(r.get("objective") or "")[:200]}
        for r in rows
    ]
