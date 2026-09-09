"""
I fatti economici di una vita, come fatti — non come un conto corrente.

    IL DENARO E' CONTESTO DI VITA, NON UN PRODOTTO A PARTE.

ORA non deve diventare un'app di spese. Deve poter rispondere a «cosa
significa questa informazione economica per questa persona», e per farlo le
serve una cosa sola che qui non c'era: un modo di dire un fatto economico
sapendo da dove viene, quanto ci si puo' contare, e cosa ancora non si sa.

Gli importi in ORA esistevano gia', ma come proprieta' sciolte su un Life
Object — `monthly_installment`, `utility_amount` — senza verso, senza
ricorrenza, senza provenienza e senza modo di essere in disaccordo con un
altro. Con quelle non si puo' rispondere «cosa mi aspetta nei prossimi trenta
giorni» senza inventare.

**Una forma sola.** Impegni, entrate, eventi, vincoli e contesto di un
obiettivo sono lo stesso oggetto con un `kind` diverso. Cinque collezioni
separate sarebbero cinque posti dove la stessa bolletta puo' esistere due
volte.

**Sconosciuto non e' zero.** E' la regola che questo modulo esiste per
tenere. Un importo che non si sa e' `None`, non `0`; una scadenza che non si
sa e' `None`, non oggi; una ricorrenza che non si sa e' `"unknown"`, non
«una tantum». Un sistema che riempie i buchi con zeri produce risposte
numeriche precise e false, ed e' la cosa peggiore che possa fare con i soldi
di qualcuno.

**La provenienza non e' un extra.** Un fatto economico senza `source_refs` e
`provenance` non si puo' scrivere: il costruttore lo rifiuta. «850 euro di
affitto» detto da un'email, da un contratto o dalla persona stessa non sono
la stessa cosa, e quale sia piu' forte dipende dalla situazione — quindi si
conservano tutte e non si sceglie qui.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Cosa puo' essere un fatto economico. Cinque parole, e la prima e' quella
# che copre quasi tutto: un impegno preso.
FinancialKind = Literal[
    "commitment",   # affitto, mutuo, rata, bolletta, assicurazione, abbonamento
    "income",       # stipendio, rimborso, entrata ricorrente
    "event",        # una fattura arrivata, un pagamento fatto, un rinnovo
    "constraint",   # un budget dichiarato, un limite, un impegno gia' preso
    "goal_context",  # il lato economico di qualcosa che la persona vuole fare
]

# Da che parte si muovono i soldi. `neutral` esiste per i fatti che non
# muovono niente — un vincolo, un contesto — e non e' un modo elegante di
# dire zero.
Direction = Literal["incoming", "outgoing", "neutral"]

# Ogni quanto. `unknown` e' un valore di prima classe: e' quello che si sa
# quando si e' letta una fattura e non si sa se ne arrivera' un'altra.
Cadence = Literal["one_time", "recurring", "unknown"]

# Quanto ci si puo' contare. Non un numero: un numero fra 0 e 1 su una cosa
# del genere e' precisione finta.
Confidence = Literal["observed", "reported", "inferred", "uncertain"]

Freshness = Literal["fresh", "aging", "stale", "unknown"]

Status = Literal["known", "superseded", "withdrawn", "disputed"]

# Quanto pesa una cosa nella vita di questa persona. Lo decide il modello,
# non una soglia sull'importo: cinquanta euro sono niente per qualcuno e una
# settimana per qualcun altro, e il codice non ha modo di saperlo.
ImpactLevel = Literal["negligible", "relevant", "material", "uncertain"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Money(BaseModel):
    """
    Un importo, o l'assenza di un importo detta come tale.

        SCONOSCIUTO NON E' ZERO.

    `amount` puo' essere `None`, e lo e' spesso: un'email che dice «il canone
    aumenta» senza cifra e' un fatto vero e importante di cui non si conosce
    l'importo. Zero sarebbe una bugia, e una bugia che si somma.
    """

    amount: Optional[float] = None
    currency: Optional[str] = Field(default=None, max_length=8)

    @property
    def is_known(self) -> bool:
        return self.amount is not None

    def for_human(self) -> str:
        if self.amount is None:
            return "importo non noto"
        symbol = {"EUR": "€", "USD": "$", "GBP": "£"}.get(
            str(self.currency or "EUR").upper(), ""
        )
        whole = f"{self.amount:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
        whole = whole.removesuffix(",00")
        return f"{symbol}{whole}" if symbol else f"{whole} {self.currency or ''}".strip()

    def for_ai(self) -> Dict[str, Any]:
        if self.amount is None:
            return {"known": False}
        return {"known": True, "amount": self.amount, "currency": self.currency}


class Provenance(BaseModel):
    """
    Da dove arriva questo, e quanto direttamente lo sa.

    `how_directly` non e' un punteggio: e' una frase che dice come si e'
    venuti a saperlo, perche' e' quello che serve a una persona — e a un
    modello — per pesare due versioni diverse della stessa cosa.
    """

    source: str = Field(min_length=1, max_length=40)      # email | document | person | calendar
    source_ref: str = Field(default="", max_length=200)   # l'id nel suo dominio
    how_directly: str = Field(default="", max_length=200)
    observed_at: str = Field(default_factory=now_iso)


class FinancialFact(BaseModel):
    """
    Una cosa che si sa dei soldi di questa persona, con tutto quello che serve
    per non fraintenderla.

    Non e' una transazione: e' un fatto. «L'affitto e' 700 al mese» e «il 18
    settembre scadono 118 euro di luce» sono due fatti di forma diversa e di
    natura uguale, e stanno bene tutti e due qui dentro.
    """

    id: str = Field(default_factory=lambda: f"fin_{uuid.uuid4().hex[:16]}")
    owner_id: str = Field(min_length=1)

    kind: FinancialKind
    # Come la chiamerebbe la persona: «affitto», «bolletta della luce»,
    # «stipendio». Non una categoria da menu a tendina: le parole con cui la
    # cosa e' arrivata.
    what: str = Field(min_length=1, max_length=160)

    money: Money = Field(default_factory=Money)
    direction: Direction = "neutral"
    cadence: Cadence = "unknown"

    # Quando. Uno dei due, o nessuno dei due: una fattura arrivata ha
    # `occurred_at`, una che scade ha `due_at`, e un impegno di cui si sa solo
    # che esiste non ha ne' l'uno ne' l'altro.
    due_at: Optional[str] = None
    occurred_at: Optional[str] = None
    # «ogni mese», «ogni anno a gennaio». Testo, non una regola: quello che si
    # e' letto, non quello che si e' dedotto.
    recurrence: Optional[str] = Field(default=None, max_length=80)

    # Con chi. Solo se davvero osservato — dedurre «Enel» da una bolletta
    # della luce e' inventare un fatto sulla vita di qualcuno.
    counterparty: Optional[str] = Field(default=None, max_length=120)

    confidence: Confidence = "reported"
    freshness: Freshness = "fresh"
    status: Status = "known"

    # Da dove viene, e con quali prove. Almeno una: senza, questo oggetto non
    # si costruisce.
    provenance: List[Provenance] = Field(min_length=1)
    source_refs: List[str] = Field(default_factory=list, max_length=8)

    # Cosa di questa vita riguarda. Riferimenti a Life Object, situazioni,
    # goal — mai copie.
    about_refs: List[str] = Field(default_factory=list, max_length=8)

    # Da quando vale e fino a quando. Un affitto aumentato dal mese prossimo
    # e' un fatto nuovo che vale da una certa data, non una correzione del
    # precedente.
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    supersedes: str = Field(default="", max_length=64)

    # Cosa non si sa e conta. Scritto qui perche' una risposta che non dice
    # cosa le manca e' una risposta che sembra completa.
    unknowns: List[str] = Field(default_factory=list, max_length=8)

    observed_at: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)

    @field_validator("provenance")
    @classmethod
    def _must_know_where_it_came_from(cls, value):
        if not value:
            raise ValueError("un fatto economico senza provenienza non si scrive")
        return value

    @field_validator("money")
    @classmethod
    def _no_zero_for_unknown(cls, value: Money):
        # Zero e' un importo legittimo — un rimborso azzerato, una bolletta a
        # saldo zero — ma solo se qualcuno lo ha detto. Qui non si puo'
        # distinguere, quindi si lascia passare e la regola vera vive dove i
        # fatti vengono costruiti: chi non sa scrive `None`.
        return value

    @property
    def is_future_obligation(self) -> bool:
        return bool(self.due_at) and self.direction == "outgoing"

    def for_human(self) -> Dict[str, Any]:
        """
        Come lo si direbbe a una persona. Niente id, niente stati tecnici.
        """
        when = ""
        if self.due_at:
            when = f"scade {human_day(self.due_at)}"
        elif self.occurred_at:
            when = f"del {human_day(self.occurred_at)}"
        if self.cadence == "recurring" and self.recurrence:
            when = (when + f", {self.recurrence}").strip(", ")
        return {
            "cosa": self.what,
            "quanto": self.money.for_human(),
            "quando": when,
            "verso": (
                "in uscita" if self.direction == "outgoing"
                else "in entrata" if self.direction == "incoming" else ""
            ),
            "da_dove_lo_so": self.provenance[0].how_directly or self.provenance[0].source,
            "cosa_non_so": list(self.unknowns),
        }

    def for_ai(self) -> Dict[str, Any]:
        """Quello che il modello vede. Fatti, mai un giudizio gia' preso."""
        return {
            "what_kind": self.kind,
            "in_their_words": self.what,
            "money": self.money.for_ai(),
            "direction": self.direction,
            "how_often": self.cadence,
            "recurrence": self.recurrence,
            "due_at": self.due_at,
            "occurred_at": self.occurred_at,
            "counterparty": self.counterparty,
            "how_sure": self.confidence,
            "how_old": self.freshness,
            "where_it_came_from": [
                {"source": p.source, "how_directly": p.how_directly,
                 "observed_at": p.observed_at}
                for p in self.provenance
            ],
            "what_is_not_known": list(self.unknowns),
            "about": list(self.about_refs),
        }


class FinancialImpact(BaseModel):
    """
    Quanto una cosa economica pesa su questa vita — come giudizio, non come verita'.

        L'IMPORTO NON DECIDE L'IMPORTANZA.

    Un aumento di due euro al mese e' niente per quasi tutti e qualcosa per
    chi sta contando ogni euro per un anticipo. Non c'e' soglia che lo sappia,
    quindi non c'e' soglia: lo dice il modello, e dice anche cosa non sa.
    """

    id: str = Field(default_factory=lambda: f"imp_{uuid.uuid4().hex[:12]}")
    owner_id: str = Field(min_length=1)
    fact_id: str = Field(min_length=1)

    level: ImpactLevel = "uncertain"
    reason: str = Field(default="", max_length=400)

    affected_goal_ids: List[str] = Field(default_factory=list, max_length=6)
    affected_situation_ids: List[str] = Field(default_factory=list, max_length=6)

    missing_information: List[str] = Field(default_factory=list, max_length=6)
    evidence_refs: List[str] = Field(default_factory=list, max_length=8)

    decided_at: str = Field(default_factory=now_iso)


class Horizon(BaseModel):
    """
    Quello che ORA sa dei prossimi giorni, e quello che non sa.

        UN ORIZZONTE SENZA I SUOI BUCHI E' UN PREVENTIVO.

    Non c'e' un «ti rimarranno» qui dentro, e non c'e' per costruzione: senza
    saldo iniziale e senza la certezza di conoscere tutti i movimenti, quella
    frase e' un numero preciso e sbagliato. Ci sono le uscite che si
    conoscono, le entrate che si conoscono, e l'elenco esplicito di cosa
    manca per poter dire di piu'.
    """

    owner_id: str
    days: int
    from_day: str
    to_day: str

    outgoing: List[FinancialFact] = Field(default_factory=list)
    incoming: List[FinancialFact] = Field(default_factory=list)

    # Cosa impedisce di dire di piu'. Se questa lista non e' vuota, nessuna
    # somma va presentata come «quanto ti resta».
    unknowns: List[str] = Field(default_factory=list)

    @property
    def can_say_what_is_left(self) -> bool:
        """
        Se si puo' dire quanto resta. Quasi sempre: no.

        Servirebbero il saldo di partenza e la certezza che non ci sia altro.
        ORA il saldo non lo ha — nessuna sorgente bancaria — quindi questa
        proprieta' esiste soprattutto per essere falsa, e per rendere
        impossibile scrivere quella frase per distrazione.
        """
        return False

    def known_outgoing_total(self) -> Optional[float]:
        """La somma di quello che si sa, o niente se non si sa tutto."""
        known = [f.money.amount for f in self.outgoing if f.money.is_known]
        if not known or len(known) != len(self.outgoing):
            return None
        return round(sum(known), 2)

    def known_incoming_total(self) -> Optional[float]:
        known = [f.money.amount for f in self.incoming if f.money.is_known]
        if not known or len(known) != len(self.incoming):
            return None
        return round(sum(known), 2)


_MONTHS = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
    "agosto", "settembre", "ottobre", "novembre", "dicembre",
)


def human_day(value: Optional[str]) -> str:
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(value or "")
    return f"il {when.day} {_MONTHS[when.month - 1]}"
