"""
Un movimento visto su un conto, prima che qualcuno decida cosa significhi.

    UNA TRANSAZIONE E' UN'OSSERVAZIONE. IL SIGNIFICATO VIENE DOPO.

E' la distinzione che questo file esiste per tenere, e vale la pena dirla per
esteso perche' e' quella che quasi tutti i prodotti finanziari saltano:
`-118,42 € · ENERGIA ITALIA S.P.A.` non e' una bolletta. E' una riga che dice
che sono usciti centodiciotto euro e quarantadue verso qualcuno che si chiama
cosi'. Che sia una bolletta e' un'interpretazione, e puo' essere sbagliata —
un rimborso, un conguaglio, un pagamento fatto per un'altra persona.

Quindi qui non c'e' nessuna categoria, nessun elenco di esercenti, nessuna
regola che guardi una descrizione e concluda qualcosa. C'e' quello che il
conto ha detto, e i **conti** che si possono fare su quello che si e' visto
prima: ogni quanto e' successo, con chi, con quale regolarita', quanto e'
cambiato l'importo. Numeri, intervalli, ripetizioni.

Poi quei numeri vanno davanti a un giudizio, e il giudizio dice cosa sembra.
Il codice non ha mai una parola in merito.

**Nessuna banca e' collegata.** Questo file definisce la forma che un futuro
sensore bancario dovra' produrre, e la prova che quella forma basta: la si
puo' costruire a mano — da una riga di estratto conto, da un'email di
addebito — e attraversa gia' tutto il percorso fino alla governance.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("ora.financial.observation")

OBSERVATIONS = "financial_observations"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


class BankObservation(BaseModel):
    """
    Quello che un conto ha detto. Niente di piu'.

    Deliberatamente povero: nessun campo per la categoria, nessuno per il
    tipo, nessuno per «e' ricorrente». Se ci fossero, qualcuno prima o poi li
    riempirebbe con una regola, e la regola diventerebbe la verita' senza che
    nessuno l'abbia decisa.

    `raw_description` e' la riga come l'ha scritta la banca — «BONIFICO A
    ROSSI MARCO» — e non viene interpretata qui. `counterparty` c'e' solo se
    e' il provider a fornirla separatamente: ricavarla dalla descrizione
    sarebbe gia' un'interpretazione.
    """

    id: str = Field(default_factory=lambda: f"obs_{uuid.uuid4().hex[:16]}")
    owner_id: str = Field(min_length=1)

    account_ref: str = Field(min_length=1, max_length=120)
    transaction_ref: str = Field(min_length=1, max_length=120)

    booked_at: str = Field(min_length=4, max_length=40)
    amount: float
    currency: str = Field(default="EUR", max_length=8)
    direction: str = Field(default="outgoing", max_length=16)

    raw_description: str = Field(default="", max_length=300)
    counterparty: Optional[str] = Field(default=None, max_length=200)
    balance_after: Optional[float] = None

    # Da dove arriva questa riga e quanto direttamente lo si sa. Stessa
    # disciplina di ogni altra cosa in questo modulo: senza, non si scrive.
    provenance: Dict[str, Any] = Field(default_factory=dict)
    observed_at: str = Field(default_factory=_now_iso)

    def for_ai(self) -> Dict[str, Any]:
        """La riga come la vede il giudizio: i fatti, mai una conclusione."""
        return {
            "when": self.booked_at,
            "amount": self.amount,
            "currency": self.currency,
            "direction": self.direction,
            "what_the_bank_wrote": self.raw_description,
            "counterparty_if_given": self.counterparty,
        }


class Pattern(BaseModel):
    """
    Cosa si e' visto succedere prima, in numeri.

        IL CODICE CONTA. NON CONCLUDE.

    Ogni campo qui e' aritmetica su date e importi: quante volte, ogni quanti
    giorni, quanto regolare, quanto e' cambiato. Nessuno di questi numeri dice
    «e' ricorrente» — dicono «e' successo sei volte a distanza di trenta
    giorni con uno scarto di due». Se sei volte bastino a chiamarla una
    ricorrenza e' un giudizio, e i giudizi stanno altrove.
    """

    times_seen: int = 0
    typical_gap_days: Optional[float] = None
    gap_regularity_days: Optional[float] = None
    amounts_seen: List[float] = Field(default_factory=list)
    amount_change_from_usual: Optional[float] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    same_counterparty_every_time: bool = False

    def for_ai(self) -> Dict[str, Any]:
        return {
            "how_many_times_something_like_this_happened": self.times_seen,
            "typical_days_between_them": self.typical_gap_days,
            "how_regular_those_gaps_are_in_days": self.gap_regularity_days,
            "amounts_seen": self.amounts_seen[-8:],
            "how_much_this_one_differs_from_the_usual": self.amount_change_from_usual,
            "first_time": self.first_seen,
            "most_recent_before_this": self.last_seen,
            "always_the_same_counterparty": self.same_counterparty_every_time,
        }


def features_of(
    observation: BankObservation, history: List[BankObservation],
) -> Pattern:
    """
    I conti su quello che si e' visto prima. Aritmetica, e basta.

    «Quello che si e' visto prima» qui e' deliberatamente ampio: le righe con
    la stessa controparte quando c'e', altrimenti quelle con la stessa
    descrizione grezza. Non e' un raggruppamento semantico e non pretende di
    esserlo — serve a poter dire «di righe come questa ne ho viste sei», e se
    il raggruppamento e' grossolano il giudizio lo vedra' dai numeri.
    """
    key = _grouping_key(observation)
    similar = [o for o in history if _grouping_key(o) == key]
    similar.sort(key=lambda o: str(o.booked_at))

    moments = [m for m in (_moment(o.booked_at) for o in similar) if m]
    gaps = [
        (later - earlier).total_seconds() / 86400.0
        for earlier, later in zip(moments, moments[1:])
    ]
    amounts = [abs(o.amount) for o in similar]

    typical = statistics.median(gaps) if gaps else None
    regularity = statistics.pstdev(gaps) if len(gaps) > 1 else None

    usual = statistics.median(amounts) if amounts else None
    change = (
        round(abs(observation.amount) - usual, 2)
        if usual is not None else None
    )

    parties = {(o.counterparty or o.raw_description or "").strip().lower()
               for o in similar}

    return Pattern(
        times_seen=len(similar),
        typical_gap_days=round(typical, 1) if typical is not None else None,
        gap_regularity_days=round(regularity, 1) if regularity is not None else None,
        amounts_seen=amounts,
        amount_change_from_usual=change,
        first_seen=similar[0].booked_at if similar else None,
        last_seen=similar[-1].booked_at if similar else None,
        same_counterparty_every_time=len(parties) == 1 and bool(parties),
    )


def _grouping_key(observation: BankObservation) -> str:
    """
    Con chi. Una chiave per contare, non una categoria.

    Se la banca fornisce una controparte si usa quella; altrimenti la
    descrizione grezza normalizzata negli spazi e nel caso. Nient'altro:
    togliere numeri, sigle o parole «rumorose» sarebbe gia' decidere cosa in
    quella riga conta, e non e' una cosa che il codice sappia.
    """
    raw = (observation.counterparty or observation.raw_description or "").strip()
    return " ".join(raw.lower().split())


class ObservationStore:
    """Le righe viste su un conto. Un registro, non una conoscenza."""

    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[OBSERVATIONS].create_index("id", unique=True)
            await self.db[OBSERVATIONS].create_index(
                [("owner_id", 1), ("transaction_ref", 1)], unique=True,
            )
            await self.db[OBSERVATIONS].create_index([("owner_id", 1), ("booked_at", -1)])
        except Exception as e:
            logger.info("index soft-fail: %s", type(e).__name__)

    async def record(self, observation: BankObservation) -> bool:
        """
        Metti via una riga. La stessa transazione due volte resta una.

        Torna `False` quando c'era gia': un estratto conto riletto non deve
        raddoppiare la storia su cui si contano le ricorrenze.
        """
        # Si guarda prima, invece di affidarsi all'indice.
        #
        #     UN ESTRATTO CONTO RILETTO NON DEVE RADDOPPIARE LA STORIA.
        #
        # L'indice unico c'e' ed e' la difesa vera contro due scritture
        # simultanee, ma viene creato da `ensure_indexes`, che in un processo
        # appena avviato puo' non essere ancora passato — e nel frattempo
        # ogni rilettura aggiungeva una riga, gonfiando proprio i conteggi su
        # cui si decide se una cosa e' ricorrente.
        already = await self.db[OBSERVATIONS].find_one(
            {
                "owner_id": observation.owner_id,
                "transaction_ref": observation.transaction_ref,
            },
            {"_id": 0, "id": 1},
        )
        if already:
            return False
        try:
            await self.db[OBSERVATIONS].insert_one(observation.model_dump())
            return True
        except Exception:
            return False

    async def history(
        self, owner_id: str, *, limit: int = 400,
    ) -> List[BankObservation]:
        rows = await self.db[OBSERVATIONS].find(
            {"owner_id": owner_id}, {"_id": 0},
        ).sort("booked_at", -1).to_list(limit)
        out = []
        for row in rows:
            try:
                out.append(BankObservation.model_validate(row))
            except Exception:
                continue
        return out
