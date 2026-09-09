"""
Cosa ORA sa dei prossimi giorni — e cosa non sa.

    QUELLO CHE SO NON E' QUELLO CHE C'E'.

La domanda «quali impegni economici conosco nei prossimi trenta giorni» ha
una risposta onesta e una comoda. Quella comoda somma quello che si ha in
mano e la presenta come il futuro. Quella onesta dice le stesse cose e poi
aggiunge cosa manca perche' quella somma non significhi niente.

Questo modulo produce solo la seconda. Non c'e' un campo «rimanente», non c'e'
un saldo previsto, e `Horizon.can_say_what_is_left` e' `False` per
costruzione: finche' ORA non ha una sorgente bancaria non conosce il punto di
partenza, e senza punto di partenza una differenza fra due numeri non e' un
saldo — e' due numeri.

Le ricorrenti entrano nell'orizzonte anche senza una data precisa: un affitto
mensile e' un impegno dei prossimi trenta giorni anche se nessuno ha scritto
il giorno. Entra come impegno noto con la scadenza sconosciuta, il che e'
diverso dal non esserci.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from financial.models import FinancialFact, Horizon, human_day
from financial.store import FinancialStore

logger = logging.getLogger("ora.financial.horizon")

# Cosa manca per poter dire «quanto ti resta». Non e' una lista tecnica: sono
# le tre cose che una persona capirebbe come mancanti, e finche' ci sono
# nessuna somma va presentata come una previsione.
ALWAYS_MISSING = (
    "il saldo dei tuoi conti",
    "le spese di tutti i giorni, che non passano da qui",
)


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


async def what_is_coming(
    db, owner_id: str, *, days: int = 30, now: Optional[datetime] = None,
) -> Horizon:
    """
    Gli impegni e le entrate note per i prossimi giorni, con i loro buchi.
    """
    moment = now or datetime.now(timezone.utc)
    until = moment + timedelta(days=days)

    # DUE COSE DIVERSE, E LA GOVERNANCE HA RAGIONE A DISTINGUERLE.
    #
    # Quello che dura — «l'affitto e' 760 al mese», «lo stipendio arriva il
    # 27» — e' cio' che ORA *sa* di questa persona, e sta nel modello della
    # vita, dove ci arriva solo passando dalla governance. E' la fonte
    # canonica, ed e' quella che si legge per prima.
    #
    # Una bolletta che scade il 18 non e' invece una cosa che dura: e'
    # contesto di un periodo, e la governance lo dice esplicitamente —
    # «TEMPORARY_CONTEXT_BELONGS_TO_SITUATION». Mettercela dentro
    # significherebbe riempire la memoria di una persona di scadenze morte.
    # Quindi le obbligazioni datate restano nel registro delle osservazioni e
    # si leggono di li', per quello che sono: cose che stanno arrivando, non
    # cose che ORA sa di te.
    #
    # L'orizzonte le mette insieme perche' la domanda — «cosa mi aspetta» —
    # riguarda entrambe. La distinzione non sparisce: quello che dura ha una
    # memoria dietro, l'altro no.
    from financial.durable import governed_facts

    unknowns: List[str] = []
    facts = await governed_facts(db, owner_id, kinds=["commitment", "income"])
    lasting = {f"{f.kind}:{' '.join(str(f.what).lower().split())}" for f in facts}
    for observed in await FinancialStore(db).known(
        owner_id, kinds=["commitment", "income"],
    ):
        key = f"{observed.kind}:{' '.join(str(observed.what).lower().split())}"
        if key in lasting:
            continue
        if not observed.due_at and observed.cadence != "recurring":
            # Ne' una scadenza ne' una ricorrenza: non si sa se riguardi
            # questo periodo, e metterlo qui sarebbe inventare. Ma tacerlo del
            # tutto sarebbe peggio: la persona sa che quella cosa esiste, e
            # se non la vede pensa che ORA se ne sia dimenticata.
            unknowns.append(
                f"quando cade «{observed.what}» — so che c'è, non quando"
            )
            continue
        # OSSERVATO NON E' CONFERMATO, MA NON E' NEMMENO NIENTE.
        #
        # Un impegno ricorrente letto in un messaggio e non ancora confermato
        # non entra nel modello della vita — la governance chiede conferma, e
        # fa bene: ORA non deve credere durevolmente che il tuo affitto sia
        # cambiato perche' l'ha letto in un'email. Ma alla domanda «cosa mi
        # aspetta questo mese» quella cosa serve, e tacerla sarebbe peggio che
        # dirla con la sua riserva. Quindi compare, e la riserva compare con
        # lei fra le cose che ORA non sa.
        if observed.cadence == "recurring":
            unknowns.append(
                f"se «{observed.what}» è quello che credo — l'ho letto, "
                "non me l'hai confermato"
            )
        facts.append(observed)

    outgoing: List[FinancialFact] = []
    incoming: List[FinancialFact] = []

    for fact in facts:
        when = _moment(fact.due_at)
        if when is not None and not (moment <= when <= until):
            continue
        if when is None:
            if fact.cadence != "recurring":
                # Nessuna data e nessuna ricorrenza: non si sa se cade in
                # questo periodo, e dire di si' sarebbe inventare.
                unknowns.append(
                    f"quando cade «{fact.what}» — so che c'è, non quando"
                )
                continue
            # Ricorrente senza giorno: succede in questo periodo, il giorno no.
            unknowns.append(f"il giorno esatto di «{fact.what}»")

        if not fact.money.is_known:
            unknowns.append(f"quanto è «{fact.what}»")

        if fact.direction == "incoming":
            incoming.append(fact)
        elif fact.direction == "outgoing":
            outgoing.append(fact)

    for missing in ALWAYS_MISSING:
        unknowns.append(missing)

    return Horizon(
        owner_id=owner_id,
        days=days,
        from_day=moment.date().isoformat(),
        to_day=until.date().isoformat(),
        outgoing=outgoing,
        incoming=incoming,
        unknowns=unknowns,
    )


def for_human(horizon: Horizon) -> Dict[str, Any]:
    """
    L'orizzonte come lo si direbbe a una persona.

    Nessun id, nessuno stato tecnico, nessuna confidenza numerica — e nessun
    «ti resteranno». Se qualcuno un giorno vorra' aggiungere quella frase,
    dovra' prima togliere `can_say_what_is_left`, che e' li' apposta.
    """
    def line(fact: FinancialFact) -> str:
        bits = [fact.what]
        if fact.money.is_known:
            bits.append(fact.money.for_human())
        if fact.due_at:
            bits.append(human_day(fact.due_at))
        elif fact.cadence == "recurring" and fact.recurrence:
            bits.append(fact.recurrence)
        return " · ".join(bits)

    known_out = horizon.known_outgoing_total()
    known_in = horizon.known_incoming_total()

    return {
        "periodo": f"prossimi {horizon.days} giorni",
        "in_uscita": [line(f) for f in horizon.outgoing],
        "in_entrata": [line(f) for f in horizon.incoming],
        # Le somme ci sono solo quando *tutti* gli importi del gruppo sono
        # noti, e sono etichettate per quello che sono: la somma di quello che
        # so, non quello che spenderai.
        "somma_di_cio_che_so_in_uscita": known_out,
        "somma_di_cio_che_so_in_entrata": known_in,
        "cosa_non_so": list(dict.fromkeys(horizon.unknowns)),
        "posso_dire_quanto_ti_resta": horizon.can_say_what_is_left,
    }
