"""
Tre modi diversi di sapere una cosa sui soldi di qualcuno, tenuti distinti.

    SO · HO LETTO · DEVO CHIEDERTELO

E' la distinzione che rende onesto tutto il resto, e l'unico posto dove viene
fatta e' questo. Sotto ci sono gia' tre meccanismi diversi — le memorie
governate, il registro delle osservazioni, le proposte che la governance ha
messo in attesa — e senza un punto in cui vengono messi in fila diventano
tre voci che dicono cose diverse alla stessa domanda.

**So.** E' passato dalla governance ed e' rimasto attivo. E' quello che ORA
puo' affermare: «l'affitto e' 700 al mese».

**Ho letto.** E' stato osservato — un'email, un documento — e non e' entrato
nel modello della vita: o perche' non e' roba che dura (una bolletta con una
scadenza), o perche' la governance ha chiesto conferma. ORA lo puo' dire, ma
deve dire *come* lo sa: «ho letto in un messaggio che dal mese prossimo…».

**Devo chiedertelo.** Una proposta in attesa o due versioni che convivono.
Non e' un errore ed e' l'informazione piu' utile delle tre, perche' e' l'unica
su cui la persona puo' fare qualcosa in un secondo.

Chi risponde a una persona — la chat, la Home, il dettaglio di una situazione
— legge di qui e non dalle collezioni: e' cosi' che le tre superfici dicono la
stessa cosa.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from financial.durable import governed_facts, identity_of, needs_your_word
from financial.models import FinancialFact
from financial.store import FinancialStore

logger = logging.getLogger("ora.financial.knowledge")


async def what_ora_knows(
    db, owner_id: str, *, days: int = 30,
) -> Dict[str, Any]:
    """
    Tutto quello che ORA ha sui soldi di questa persona, diviso per come lo sa.

    Non una risposta: il materiale con cui una risposta si costruisce. Chi
    parla — il modello, in chat — riceve questo e ha davanti la differenza
    fra affermare e riferire, che e' la sola cosa che non deve sbagliare.
    """
    from financial.horizon import for_human, what_is_coming

    known = await governed_facts(db, owner_id)
    known_keys = {identity_of(f) for f in known}

    observed: List[FinancialFact] = []
    for fact in await FinancialStore(db).known(owner_id):
        if identity_of(fact) in known_keys:
            # Ne esiste gia' una versione governata: e' «so», non «ho letto».
            continue
        observed.append(fact)

    asking = await needs_your_word(db, owner_id)
    horizon = for_human(await what_is_coming(db, owner_id, days=days))

    # E le tre cose che mancavano, e senza le quali ogni risposta sui soldi
    # era imprecisa in un modo che nessun test coglieva:
    #
    #     LO STATO DELLA FONTE · LA FORMA DEI MOVIMENTI · LA SOMMA DEL MESE
    #
    # Senza la prima, ORA parlava di un saldo come se fosse di adesso anche a
    # conto scollegato. Senza la seconda, chiamava «ricorrente» un pagamento
    # al notaio fatto una volta. Senza la terza, non sapeva rispondere a
    # «come sono messo questo mese» se non tacendo — che e' onesto e inutile.
    from financial.observed import the_bank_right_now, this_month, what_was_seen

    bank = await the_bank_right_now(db, owner_id)
    live = bool(bank.get("posso_leggere_adesso"))
    seen = await what_was_seen(db, owner_id)
    month = await this_month(db, owner_id)

    return {
        # Quello che ORA puo' affermare.
        "so": [_said(f, bank_is_live=live) for f in known],
        # Quello che ha letto e non ha ancora fatto proprio. Ogni riga porta
        # con se' da dove viene: senza, «ho letto» e «so» diventano la stessa
        # frase appena qualcuno le rilegge.
        "ho_letto": [_said(f, with_source=True, bank_is_live=live) for f in observed],
        # Quello su cui serve una parola della persona.
        "devo_chiederti": [
            {
                "cosa": a["what"],
                "quanto": a["how_much"],
                "invece_di": a["instead_of"],
                "come_lo_so": a["how_directly"],
            }
            for a in asking
        ],
        # E cosa sta arrivando, con i suoi buchi.
        "in_arrivo": horizon,
        # Com'e' messa la fonte adesso: collegata o no, e che diritto c'e' di
        # parlare del saldo.
        "la_banca": bank,
        # I movimenti come forme, non come significati.
        "movimenti_osservati": seen,
        # E la somma del mese, con il suo nome addosso.
        "questo_mese": month,
    }


def _said(
    fact: FinancialFact, *, with_source: bool = False, bank_is_live: bool = True,
) -> Dict[str, Any]:
    """Un fatto come una riga leggibile. Nessun id, nessuno stato tecnico."""
    line = {
        "cosa": fact.what,
        "quanto": fact.money.for_human(),
        "quando": (
            f"scade il {fact.due_at[:10]}" if fact.due_at
            else (fact.recurrence or "")
        ),
        "verso": (
            "in uscita" if fact.direction == "outgoing"
            else "in entrata" if fact.direction == "incoming" else ""
        ),
    }
    if fact.unknowns:
        line["cosa_non_so"] = list(fact.unknowns)[:3]
    # Il «come lo so» viaggia sempre, anche su quello che ORA puo' affermare.
    #
    #     «PENSO — L'HO VISTO SUL TUO CONTO» DETTO DI TUTTO NON DICE NIENTE.
    #
    # Sapere una cosa perche' l'ha detta la persona e saperla perche' torna
    # ogni mese sul conto sono due cose diverse, e la schermata le mostra
    # diverse solo se qui arrivano diverse.
    line["come_lo_so"] = _how_it_is_known(fact, bank_is_live=bank_is_live)
    return line


def _how_it_is_known(fact: FinancialFact, *, bank_is_live: bool = True) -> str:
    """
    Da dove viene questa cosa, detto come lo direbbe una persona.

        «L'HO VISTO SUL TUO CONTO» DETTO DI TUTTO NON DICE NIENTE.

    Una cosa vista tornare ogni mese e una vista una volta sola non si sanno
    allo stesso modo, e una vista su un conto che non e' piu' collegato non
    la si sta vedendo adesso. Tre frasi diverse per tre cose diverse: e' la
    stessa disciplina dei gradi, un gradino piu' in basso.
    """
    if not fact.provenance:
        return ""
    first = fact.provenance[0]
    if first.source == "person":
        return "confermato da te"
    if first.source == "bank":
        seen = (
            "compare regolarmente sul conto" if fact.cadence == "recurring"
            else "l'ho visto una volta sul conto"
        )
        return seen if bank_is_live else seen + ", quando era collegato"
    return first.how_directly or first.source


async def resolve_open_question(
    db, owner_id: str, *, about: str, confirmed: bool,
    session_id: str = "financial",
) -> Dict[str, Any]:
    """
    La persona ha risposto alla domanda, e la risposta chiude il giro.

        UN «SI'» E UN «NO» CHIUDONO LA STESSA DOMANDA, IN DUE MODI DIVERSI.

    Con un si': quello che era stato letto diventa quello che ORA sa. La
    proposta torna davanti alla governance, questa volta con l'autorita' che
    le mancava — la parola della persona — e la versione precedente viene
    superata. Una sola conoscenza corrente, e la storia resta leggibile.

    Con un no: non si promuove niente, e non si cancella niente. Quello che
    era stato osservato resta nel registro con la sua provenienza — e' un
    fatto che quel messaggio l'ha detto, anche se non era vero — e la
    conoscenza precedente resta quella corrente. La domanda si chiude in
    entrambi i casi: e' la stessa domanda, e non deve tornare a chiedere.

    Nessun goal, nessun engine nuovo: e' una risposta a una domanda, non
    l'inizio di un lavoro.
    """
    from financial.durable import propose

    wanted = " ".join(str(about or "").strip().lower().split())
    pending = await db.financial_facts.find(
        {"owner_id": owner_id, "governance_decision": "CLARIFY"},
        {"_id": 0},
    ).sort("observed_at", -1).to_list(20)

    target: Optional[FinancialFact] = None
    for row in pending:
        try:
            fact = FinancialFact.model_validate(row)
        except Exception:
            continue
        name = " ".join(str(fact.what).lower().split())
        if wanted and (name == wanted or wanted in name or name in wanted):
            target = fact
            break

    if target is None:
        return {"resolved": False, "reason": "nessuna domanda aperta su questo"}

    if not confirmed:
        # Rifiutata. Il fatto resta come osservazione — con la sua
        # provenienza, perche' e' vero che quel messaggio lo diceva — e
        # smette di essere una domanda.
        await db.financial_facts.update_one(
            {"id": target.id},
            {"$set": {
                "governance_decision": "DECLINED_BY_USER",
                "status": "withdrawn",
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return {
            "resolved": True, "confirmed": False, "what": target.what,
            "still_known": "quello che sapevo prima resta quello corrente",
        }

    # Confermata. Adesso l'autorita' c'e': l'ha detta la persona.
    target.confidence = "observed"
    # La parola della persona va davanti, non in coda.
    #
    #     CHI LO SA PER PRIMO DECIDE QUANTO VALE.
    #
    # L'autorita' di una proposta si legge dalla prima provenienza, e con
    # l'email davanti la conferma valeva ancora «l'ha scritto qualcun altro»:
    # la governance continuava a chiedere conferma di una cosa appena
    # confermata, e la domanda non si chiudeva mai.
    target.provenance = [
        type(target.provenance[0])(
            source="person",
            how_directly="me lo hai confermato tu",
        )
    ] + list(target.provenance)
    out = await propose(
        db, target,
        session_id=session_id,
        reasoning_epoch=f"fin:confermato:{target.id}",
        confirmed_by_user=True,
    )
    await db.financial_facts.update_one(
        {"id": target.id},
        {"$set": {
            "governance_decision": out["decision"],
            "confidence": "observed",
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {
        "resolved": True, "confirmed": True, "what": target.what,
        "decision": out["decision"], "in_life_model": out["persisted"],
    }
