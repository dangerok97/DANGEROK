"""
Come una cosa osservata diventa, se lo e', un fatto economico.

    NESSUNA CATEGORIA GENERA LAVORO DA SOLA.

Questo e' il punto di innesto fra Connected Life e i soldi, ed e' scritto per
non essere una scorciatoia. Un segnale che nomina un importo non diventa un
impegno perche' nomina un importo: viene messo davanti a un giudizio, e la
risposta ordinaria e' che non e' niente.

Cosa fa il codice qui: raccoglie quello che si sa, chiama il giudizio, e
scrive quello che torna con la provenienza attaccata. Cosa non fa: decidere
che qualcosa conta, creare un goal, o toccare il Personal Life Model. Quella
strada passa dalla governance, come per ogni altra cosa durevole.

Nessun parser bancario, nessun secondo motore documenti, nessun OCR: le email
arrivano gia' come segnali di Connected Life e i documenti gia' come analisi.
Se il testo non c'e', non si finge di averlo letto.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from financial.models import (
    FinancialFact,
    FinancialImpact,
    Money,
    Provenance,
    now_iso,
)
from financial.store import FinancialStore

logger = logging.getLogger("ora.financial.bridge")


async def read_money_in(
    db,
    owner_id: str,
    *,
    observation: Dict[str, Any],
    provenance: Provenance,
    source_refs: Optional[List[str]] = None,
    language: str = "it",
) -> Dict[str, Any]:
    """
    Guarda una cosa osservata e, se dice qualcosa sui soldi, mettila via.

    Si chiama cosi' e non `consider` perche' quel verbo, in questo
    codice, significa gia' un'altra cosa: «valuta se creare un goal».
    Due funzioni con lo stesso nome e poteri diversi sono un incidente
    che aspetta, e una guardia in `connected/` lo dice a voce alta.

    Torna sempre un esito leggibile: `nothing` quando non c'era niente,
    `no_answer` quando il giudizio non e' arrivato — e sono due cose diverse,
    perche' la seconda non autorizza nessuno a concludere che non c'era
    niente.
    """
    from financial.reasoning import read_financial_meaning

    store = FinancialStore(db)
    known = [f.for_ai() for f in await store.known(owner_id, limit=40)]
    life = await _life(db, owner_id)

    answer = await read_financial_meaning(
        observation, life=life, already_known=known, language=language,
    )
    if answer is None:
        # Silenzio del giudizio. Non e' «niente»: e' «non lo so», e il mondo
        # resta com'era.
        return {"outcome": "no_answer"}

    if answer["what_it_is"] == "nothing":
        return {"outcome": "nothing", "why": answer.get("reasoning", "")}

    fact = _fact_from(
        owner_id, answer, provenance=provenance, source_refs=source_refs or [],
    )
    kept = await store.remember(fact, replaces=str(answer.get("changes_what") or ""))

    # E poi la parte che conta: farlo entrare — se merita — in quello che ORA
    # sa davvero. Il registro sopra e' l'osservato; la memoria governata e'
    # la vita. Qui non si scrive niente: si propone, e la governance decide.
    #
    # Quando c'e' un disaccordo, le versioni si nominano a vicenda: e' cosi'
    # che il modello della vita sa di non sapere ancora quale sia giusta,
    # invece di credere l'ultima arrivata.
    from financial.durable import propose

    coexists = []
    for other_id in kept.get("disputes") or []:
        other = await store.get(owner_id, other_id)
        if other is not None and getattr(other, "memory_id", None):
            coexists.append(other.memory_id)

    governed = await propose(db, fact, coexists_with=coexists)

    return {
        "outcome": kept["outcome"],
        "fact_id": fact.id,
        "what": fact.what,
        "disputes": kept.get("disputes") or [],
        "unknowns": list(fact.unknowns),
        "governance": governed["decision"],
        "in_life_model": governed["persisted"],
    }


def _fact_from(
    owner_id: str,
    answer: Dict[str, Any],
    *,
    provenance: Provenance,
    source_refs: List[str],
) -> FinancialFact:
    """
    Il fatto, costruito da quello che il giudizio ha detto — e solo da quello.

    Qui vive la regola che tiene in piedi tutto il resto: quello che il
    modello non ha detto resta assente. Nessun campo viene riempito con uno
    zero, con oggi, o con «una tantum» perche' era comodo avere un valore.
    """
    amount = answer.get("amount")
    money = Money(
        amount=float(amount) if isinstance(amount, (int, float)) else None,
        currency=str(answer.get("currency") or "").strip() or None,
    )

    unknowns = [str(u)[:120] for u in (answer.get("what_is_not_known") or [])][:8]
    if not money.is_known and not any("importo" in u.lower() for u in unknowns):
        unknowns.append("l'importo")

    direction = str(answer.get("direction") or "").strip()
    if direction not in ("incoming", "outgoing", "neutral"):
        direction = "outgoing" if answer["what_it_is"] == "commitment" else "neutral"

    cadence = str(answer.get("how_often") or "").strip()
    if cadence not in ("one_time", "recurring", "unknown"):
        cadence = "unknown"

    return FinancialFact(
        owner_id=owner_id,
        kind=answer["what_it_is"],
        what=str(answer.get("in_their_words") or "").strip()[:160] or "qualcosa di economico",
        money=money,
        direction=direction,
        cadence=cadence,
        recurrence=str(answer.get("recurrence") or "").strip() or None,
        due_at=str(answer.get("due_at") or "").strip() or None,
        occurred_at=str(answer.get("occurred_at") or "").strip() or None,
        counterparty=str(answer.get("counterparty") or "").strip() or None,
        valid_from=str(answer.get("valid_from") or "").strip() or None,
        confidence="observed" if provenance.source == "document" else "reported",
        provenance=[provenance],
        source_refs=source_refs[:8],
        unknowns=unknowns,
    )


async def weigh(
    db, owner_id: str, fact_id: str, *, language: str = "it",
) -> Optional[FinancialImpact]:
    """
    Chiedi quanto pesa un fatto su questa vita, e scrivi il giudizio.

    Il codice controlla solo che i riferimenti tornino: che i goal e le
    situazioni nominati siano di questa persona e che esistano. Il livello, la
    ragione e cosa manca sono del modello.
    """
    from financial.reasoning import weigh_against_their_life

    store = FinancialStore(db)
    fact = await store.get(owner_id, fact_id)
    if fact is None:
        return None

    goals = await _goals(db, owner_id)
    situations = await _situations(db, owner_id)
    answer = await weigh_against_their_life(
        fact.for_ai(),
        life=await _life(db, owner_id),
        goals=goals,
        situations=situations,
        language=language,
    )
    if answer is None:
        return None

    # I riferimenti nominati devono essere roba di questa persona. Un id
    # inventato o di qualcun altro non entra: e' l'unica cosa che il codice
    # verifica qui, ed e' una verifica di appartenenza, non di merito.
    mine_goals = {str(g.get("id")) for g in goals}
    mine_situations = {str(s.get("id")) for s in situations}

    impact = FinancialImpact(
        owner_id=owner_id,
        fact_id=fact.id,
        level=answer["level"],
        reason=str(answer.get("reason") or "")[:400],
        affected_goal_ids=[
            g for g in (answer.get("affected_goal_ids") or [])
            if str(g) in mine_goals
        ][:6],
        affected_situation_ids=[
            s for s in (answer.get("affected_situation_ids") or [])
            if str(s) in mine_situations
        ][:6],
        missing_information=[
            str(m)[:120] for m in (answer.get("missing_information") or [])
        ][:6],
        evidence_refs=list(fact.source_refs)[:8],
    )
    await store.record_impact(impact)

    # E il fatto sa a cosa appartiene. Non e' una copia: e' il riferimento
    # alla situazione che il giudizio ha nominato, ed e' quello che permette
    # a una schermata di dire «di questa cosa che stai facendo so anche
    # questo» senza andare a indovinare per somiglianza di parole.
    if impact.affected_situation_ids:
        await db.financial_facts.update_one(
            {"id": fact.id},
            {"$addToSet": {"about_refs": {"$each": impact.affected_situation_ids}}},
        )

    return impact


# --- quello che si sa di questa vita, letto e mai scritto ------------------

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
