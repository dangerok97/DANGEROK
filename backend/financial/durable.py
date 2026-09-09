"""
Come un fatto economico diventa — o non diventa — qualcosa che ORA sa davvero.

    UNA SOLA VERITA' DUREVOLE: IL PERSONAL LIFE MODEL.

`financial_facts` non e' una seconda memoria. E' il registro di cosa e' stato
osservato e come e' stato interpretato: serve a poter rispondere «perche' lo
credi» e a rileggere una catena, ma non e' la fonte di cio' che ORA sa. Quella
e' una sola, ed e' la stessa di tutto il resto — le memorie governate.

Quindi ogni fatto economico che vuole durare passa di qui, e di qui passa per
la governance esistente, che puo' dire tre cose diverse e tutte legittime:

  PROMOTE / SUPERSEDE   e' entrato nel modello della vita.
  CLARIFY               serve una conferma prima di crederlo.
  REJECT                non e' roba da ricordare.

Nessuna scrittura diretta. Se un giorno qualcuno volesse far entrare un
importo nel modello senza passare da qui, dovrebbe scriverne il codice a
mano, e un test glielo direbbe.

**Il conflitto sopravvive alla governance.** Due fonti che dicono cifre
diverse non diventano una memoria con la cifra piu' recente: diventano due
memorie che si nominano a vicenda in `coexists_with_refs`, e chi legge sa che
ORA non sa ancora quale sia quella giusta. E' l'unica forma onesta di
«dovrei chiedertelo».
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from financial.models import FinancialFact, Money, Provenance

logger = logging.getLogger("ora.financial.durable")

# Come si chiama, nel modello della vita, un fatto economico. Il prefisso
# serve a ritrovarli; il resto della chiave e' la cosa di cui si parla, cosi'
# che una versione nuova dello stesso impegno vada a superare la precedente
# invece di affiancarla.
KIND = "financial"


def identity_of(fact: FinancialFact) -> str:
    """La chiave con cui questo impegno si riconosce da una volta all'altra."""
    what = " ".join(str(fact.what or "").strip().lower().split())
    return f"financial:{fact.kind}:{what}"


def _authority_of(fact: FinancialFact) -> str:
    """
    Quanto vale la parola di chi lo ha detto.

    Non e' un punteggio di verita': e' *come* si e' venuti a saperlo, che e'
    quello che la governance usa per decidere se puo' crederci da sola o se
    deve chiedere. Un contratto e' un documento; un'email e' una fonte
    strutturata ma di terzi; quello che ha detto la persona vale come detto
    dalla persona.
    """
    source = (fact.provenance[0].source if fact.provenance else "").lower()
    return {
        "document": "document",
        "person": "user_stated",
        "email": "structured",
        "calendar": "structured",
    }.get(source, "inferred")


def as_sentence(fact: FinancialFact) -> str:
    """
    Il fatto come una frase, che e' quello che una memoria contiene.

    Non un record: una cosa che si potrebbe leggere ad alta voce. Quando
    l'importo non si sa, la frase lo dice — «non so ancora quanto» — perche'
    una memoria che tace su cosa le manca verra' riletta come completa.
    """
    money = fact.money.for_human()
    if fact.kind == "income":
        head = f"{fact.what}: {money}" if fact.money.is_known else f"{fact.what}, importo ancora non noto"
        return f"Entrata — {head}."
    if fact.kind == "event":
        when = f" del {fact.occurred_at[:10]}" if fact.occurred_at else ""
        return f"{fact.what}{when}: {money}."
    if fact.kind == "constraint":
        return f"Limite dichiarato — {fact.what}: {money}."

    bits = [fact.what]
    bits.append(money if fact.money.is_known else "importo ancora non noto")
    if fact.cadence == "recurring" and fact.recurrence:
        bits.append(fact.recurrence)
    elif fact.due_at:
        bits.append(f"scade il {fact.due_at[:10]}")
    return " · ".join(bits) + "."


async def propose(
    db,
    fact: FinancialFact,
    *,
    session_id: str = "financial",
    reasoning_epoch: str = "",
    coexists_with: Optional[List[str]] = None,
    confirmed_by_user: bool = False,
) -> Dict[str, Any]:
    """
    Porta questo fatto davanti alla governance, e riporta cosa ha deciso.

    Non scrive niente di durevole per conto proprio: costruisce il candidato e
    lascia decidere. Quello che torna dice cosa e' successo, incluso quando
    non e' successo niente — `CLARIFY` e `REJECT` sono esiti, non errori.
    """
    from conversation_engine.ai_core.models import MemoryCandidate
    from life_memory.governance import MemoryGovernanceService

    epoch = reasoning_epoch or f"fin:{fact.id}"
    identity = identity_of(fact)

    # Se questo impegno esisteva gia' nel modello della vita, la nuova
    # versione lo supera invece di affiancarlo. E' la differenza fra «da
    # ottobre l'affitto e' 760» e «hai due affitti».
    prior = await db.memories.find_one(
        {"user_id": fact.owner_id, "identity_key": identity, "status": "active"},
        {"_id": 0, "id": 1},
    )

    candidate = MemoryCandidate(
        operation="supersede" if prior else "propose",
        summary=as_sentence(fact),
        kind=KIND,
        identity_key=identity,
        value={
            "kind": fact.kind,
            "what": fact.what,
            "amount": fact.money.amount,
            "currency": fact.money.currency,
            "direction": fact.direction,
            "cadence": fact.cadence,
            "recurrence": fact.recurrence,
            "due_at": fact.due_at,
            "occurred_at": fact.occurred_at,
            "unknowns": list(fact.unknowns),
        },
        # Non un punteggio inventato: quanto direttamente lo si sa, tradotto
        # nella scala che la governance gia' usa.
        confidence=0.9 if (confirmed_by_user or _authority_of(fact) == "document") else 0.6,
        authority=_authority_of(fact),
        # Confermato dalla persona e' uno stato diverso da «lo dice una
        # fonte»: e' l'unico che permette alla governance di scrivere senza
        # richiedere un'altra conferma della stessa cosa.
        epistemic_status=(
            "confirmed" if confirmed_by_user
            else "tentative" if fact.status == "disputed"
            else "asserted"
        ),
        provenance=[p.how_directly or p.source for p in fact.provenance][:8],
        evidence_refs=list(fact.source_refs)[:8],
        permanence="durable" if fact.cadence == "recurring" else "temporary",
        starts_at=fact.valid_from,
        ends_at=fact.valid_until,
        recurrence=fact.recurrence,
        existing_memory_ref=(prior or {}).get("id"),
        # Le versioni che convivono con questa senza superarla: e' cosi' che
        # il modello della vita sa di non sapere quale sia quella giusta.
        coexists_with_refs=list(coexists_with or [])[:6],
        user_authorized=confirmed_by_user,
        reason_for_future_utility=(
            "serve per sapere cosa sta arrivando e cosa ancora non si sa"
        ),
    )

    outcome = await MemoryGovernanceService(db).apply(
        user_id=fact.owner_id,
        session_id=session_id,
        reasoning_epoch=epoch,
        candidate=candidate,
        candidate_index=0,
    )

    # Il registro tiene il filo verso quello che e' durato: serve a
    # rispondere «perche' lo credi», non a essere riletto come verita'.
    try:
        await db.financial_facts.update_one(
            {"id": fact.id},
            {"$set": {
                "memory_id": outcome.memory_id or "",
                "governance_decision": outcome.decision,
            }},
        )
    except Exception as e:
        logger.info("journal link soft-fail: %s", type(e).__name__)

    return {
        "decision": outcome.decision,
        "persisted": bool(outcome.persisted),
        "memory_id": outcome.memory_id,
        "reason": getattr(outcome, "reason", ""),
    }


async def governed_facts(
    db, owner_id: str, *, kinds: Optional[List[str]] = None,
) -> List[FinancialFact]:
    """
    Quello che ORA sa dei soldi di questa persona — letto dal modello della vita.

        LA FONTE E' UNA SOLA.

    Non dalla collezione dei fatti: quella e' il registro dell'osservato. Chi
    deve rispondere a una persona legge di qui, e quello che legge e' cio' che
    e' passato dalla governance ed e' rimasto attivo.
    """
    try:
        rows = await db.memories.find(
            {"user_id": owner_id, "kind": KIND, "status": "active"},
            {"_id": 0},
        ).to_list(200)
    except Exception as e:
        logger.info("life model read soft-fail: %s", type(e).__name__)
        return []

    out: List[FinancialFact] = []
    for row in rows:
        value = row.get("value") or {}
        if kinds and value.get("kind") not in kinds:
            continue
        scope = row.get("temporal_scope") or {}
        try:
            out.append(FinancialFact(
                id=str(row.get("id") or ""),
                owner_id=owner_id,
                kind=value.get("kind") or "commitment",
                what=str(value.get("what") or row.get("content") or "qualcosa")[:160],
                money=Money(
                    amount=value.get("amount"),
                    currency=value.get("currency"),
                ),
                direction=value.get("direction") or "neutral",
                cadence=value.get("cadence") or "unknown",
                recurrence=value.get("recurrence") or scope.get("recurrence"),
                due_at=value.get("due_at"),
                occurred_at=value.get("occurred_at"),
                valid_from=scope.get("starts_at"),
                valid_until=scope.get("ends_at"),
                status=(
                    "disputed"
                    if row.get("epistemic_status") == "tentative"
                    else "known"
                ),
                unknowns=list(value.get("unknowns") or []),
                provenance=[Provenance(
                    source=str(row.get("authority") or "inferred"),
                    how_directly=(row.get("provenance") or [""])[0],
                )],
                source_refs=list(row.get("evidence_refs") or [])[:8],
                about_refs=list(row.get("coexists_with_refs") or [])[:8],
            ))
        except Exception as e:
            logger.info("memory shape soft-fail: %s", type(e).__name__)
    return out


async def open_questions(db, owner_id: str) -> List[Dict[str, Any]]:
    """
    Le cose economiche su cui ORA sa di non sapere.

    Due memorie che convivono sulla stessa cosa sono un «non lo so ancora»
    che qualcuno puo' sciogliere. Escono di qui perche' una schermata deve
    poterlo dire con parole, senza tirare a indovinare quale valga.
    """
    facts = await governed_facts(db, owner_id)
    by_thing: Dict[str, List[FinancialFact]] = {}
    for fact in facts:
        if fact.status != "disputed":
            continue
        by_thing.setdefault(identity_of(fact), []).append(fact)

    out: List[Dict[str, Any]] = []
    for versions in by_thing.values():
        if len(versions) < 2:
            continue
        out.append({
            "what": versions[0].what,
            "versions": [
                {
                    "how_much": v.money.for_human(),
                    "how_directly": v.provenance[0].how_directly
                    or v.provenance[0].source,
                }
                for v in versions
            ],
        })
    return out


async def needs_your_word(db, owner_id: str) -> List[Dict[str, Any]]:
    """
    Le cose economiche che ORA ha visto e non puo' credere da sola.

        UN «DEVO CHIEDERTELO» CHE NESSUNO SENTE E' UN'INFORMAZIONE PERSA.

    La governance risponde `CLARIFY` a un aumento letto in un'email, e fa
    bene: ORA non deve credere durevolmente che il tuo affitto sia cambiato
    perche' lo ha letto in un messaggio. Ma se quel «devo chiedertelo» resta
    nel registro e non arriva mai a nessuno, l'effetto pratico e' che
    l'aumento e' stato osservato e poi buttato — che e' peggio di non averlo
    letto, perche' ORA sa e tace.

    Quindi escono di qui, come domande: cosa si e' visto, quanto, da dove, e
    cosa cambierebbe rispetto a quello che ORA gia' sa.
    """
    try:
        rows = await db.financial_facts.find(
            {"owner_id": owner_id, "governance_decision": "CLARIFY"},
            {"_id": 0},
        ).sort("observed_at", -1).to_list(20)
    except Exception as e:
        logger.info("clarify read soft-fail: %s", type(e).__name__)
        return []

    known = {identity_of(f): f for f in await governed_facts(db, owner_id)}

    out: List[Dict[str, Any]] = []
    seen: set = set()
    for row in rows:
        try:
            fact = FinancialFact.model_validate(row)
        except Exception:
            continue
        identity = identity_of(fact)
        if identity in seen:
            continue
        seen.add(identity)
        current = known.get(identity)
        out.append({
            "what": fact.what,
            "how_much": fact.money.for_human(),
            "how_directly": (
                fact.provenance[0].how_directly or fact.provenance[0].source
                if fact.provenance else ""
            ),
            # Cosa cambierebbe. Senza questo la domanda e' «e' giusto?», che
            # non aiuta nessuno; con questo e' «prima sapevo 700, adesso
            # leggo 760, quale vale?».
            "instead_of": current.money.for_human() if current else "",
        })
    return out
