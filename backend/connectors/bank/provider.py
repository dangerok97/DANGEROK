"""
Il contratto che un provider bancario deve rispettare, e uno finto che lo rispetta.

    LA BANCA E' UNO STRUMENTO. IL SIGNIFICATO VIENE DOPO.

Nessuna banca reale e' collegata in questo sprint, e la ragione non e' il
tempo: collegare un aggregatore PSD2 vuol dire una licenza AISP o un accordo
con chi ce l'ha, e un consenso che scade ogni novanta giorni per obbligo di
legge. Sono decisioni di prodotto e di conformita', non di codice.

Quello che si puo' fare adesso — ed e' quello che serve — e' fissare la forma
che i dati devono avere quando arriveranno, e dimostrare che il percorso a
valle regge: normalizzazione, giudizio, governance, modello della vita. Il
provider finto qui sotto produce esattamente quella forma.

**Cosa deve dare un provider.** Conti e movimenti, e nient'altro. Nessun
metodo per spostare denaro esiste in questo protocollo: non c'e' `transfer`,
non c'e' `pay`, non c'e' `cancel`. Non e' una dimenticanza — un attuatore che
non esiste non puo' essere chiamato per sbaglio, e una guardia strutturale
verifica che continui a non esistere.

**La categoria del provider non e' la nostra.** Gli aggregatori restituiscono
una loro classificazione — «utilities», «groceries» — ed e' un indizio utile
che viaggia come tale, dentro le prove, non come verita'. La classificazione
di ORA la fa il giudizio, guardando la vita di questa persona.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger("ora.connectors.bank")


class BankAPIError(Exception):
    """Un errore del provider, con il suo codice e senza il suo corpo."""

    def __init__(self, status_code: int, message: str = ""):
        super().__init__(message or f"bank_http_{status_code}")
        self.status_code = status_code

    @property
    def consent_expired(self) -> bool:
        """
        Il consenso e' scaduto. Non e' un guasto: e' la legge.

        PSD2 obbliga a rinnovare il consenso periodicamente, quindi questo
        stato e' normale e ricorrente, e va detto alla persona come una cosa
        da rifare — non come un errore.
        """
        return self.status_code in (401, 403)


class BankRateLimited(BankAPIError):
    """
    La banca ha detto basta per adesso.

        UN TETTO NON E' UN GUASTO: E' UN APPUNTAMENTO SPOSTATO.

    Per legge un conto puo' essere letto un numero limitato di volte al
    giorno, e alcune banche concedono quattro letture per endpoint. Non c'e'
    niente da riparare e non c'e' niente da dire alla persona: c'e' un'ora
    prima della quale non si ripassa, e la dice la banca — vale piu' di
    qualunque cadenza decisa da noi.
    """

    def __init__(self, retry_after_seconds: int = 3600, message: str = ""):
        super().__init__(429, message or "rate_limited")
        self.retry_after_seconds = max(60, int(retry_after_seconds))


@dataclass
class AccountSummary:
    """Un conto come lo descrive la banca."""

    account_ref: str
    display_name: str = ""
    institution: str = ""
    currency: str = "EUR"
    account_type: Optional[str] = None
    owner_relationship: Optional[str] = None
    # Il saldo c'e' solo se il provider lo fornisce.
    #
    #     SCONOSCIUTO NON E' ZERO.
    #
    # Alcuni aggregatori danno il saldo solo su richiesta, altri mai. Un
    # `0.0` di ripiego diventerebbe «hai il conto vuoto», che e' una cosa
    # falsa detta con precisione.
    current_balance: Optional[float] = None
    available_balance: Optional[float] = None
    balance_at: Optional[str] = None
    # Le ultime quattro cifre, quando servono a dire due conti l'uno
    # dall'altro. Mai il numero intero: quello non serve a distinguere, serve
    # a pagare, e non abbiamo motivo di conservarlo.
    masked_number: Optional[str] = None


@dataclass
class TransactionsPage:
    """Una pagina di movimenti, e dove riprendere."""

    transactions: List[Dict[str, Any]] = field(default_factory=list)
    next_cursor: Optional[str] = None


class BankProviderProtocol(Protocol):
    """
    Cosa un provider bancario deve saper fare. Tre verbi, tutti di lettura.

    Se un giorno qualcuno aggiungesse qui un quarto verbo che muove denaro,
    dovrebbe cambiare questo protocollo, il connettore e una guardia — che e'
    esattamente il numero di passi deliberati che una cosa del genere merita.
    """

    async def accounts(self, *, access_token: str) -> List[AccountSummary]: ...

    async def transactions(
        self, *, access_token: str, account_ref: str,
        since: Optional[str] = None, cursor: Optional[str] = None,
    ) -> TransactionsPage: ...

    async def balance(
        self, *, access_token: str, account_ref: str,
    ) -> Optional[Dict[str, Any]]: ...


class FakeBankProvider:
    """
    Un conto verosimile, deterministico, per far camminare il percorso.

    I movimenti sono quelli di una vita ordinaria — uno stipendio, un
    affitto, una bolletta, un addebito piccolo e ricorrente, una spesa
    grossa una tantum, e due spese di tutti i giorni — perche' e' su questi
    che si vede se il sistema capisce o tira a indovinare. Nessuna categoria
    e' dichiarata: la descrizione e' quella che scriverebbe una banca.
    """

    def __init__(self, *, today: Optional[datetime] = None):
        self.today = today or datetime.now(timezone.utc)
        self.calls: List[str] = []
        # Un movimento in sospeso, che diventera' contabilizzato: e' il caso
        # in cui una banca cambia idea su una riga gia' vista.
        self.pending_becomes_booked = True

    async def accounts(self, *, access_token: str) -> List[AccountSummary]:
        self.calls.append("accounts")
        return [AccountSummary(
            account_ref="acc_main",
            display_name="Conto principale",
            institution="Banca di prova",
            currency="EUR",
            account_type="checking",
            owner_relationship="own",
            current_balance=3250.00,
            available_balance=3250.00,
            balance_at=self.today.isoformat(),
        )]

    async def balance(
        self, *, access_token: str, account_ref: str,
    ) -> Optional[Dict[str, Any]]:
        self.calls.append("balance")
        return {
            "current": 3250.00, "available": 3250.00,
            "currency": "EUR", "at": self.today.isoformat(),
        }

    async def transactions(
        self, *, access_token: str, account_ref: str,
        since: Optional[str] = None, cursor: Optional[str] = None,
    ) -> TransactionsPage:
        self.calls.append("transactions")
        rows: List[Dict[str, Any]] = []

        def day(back: int) -> str:
            return (self.today - timedelta(days=back)).isoformat()

        def add(ref, back, amount, description, **extra):
            rows.append({
                "transaction_ref": ref,
                "booked_at": day(back),
                "amount": amount,
                "currency": "EUR",
                "description": description,
                **extra,
            })

        # Sei mesi di ricorrenze, cosi' che i conti abbiano qualcosa da contare.
        for month in range(6):
            back = 30 * month
            add(f"tx_a{month:02d}1", back + 3, 2050.00,
                "BONIFICO DA ACME SRL STIPENDIO",
                counterparty="ACME SRL", provider_category="income")
            add(f"tx_a{month:02d}2", back + 1, -760.00,
                "BONIFICO A ROSSI MARCO",
                counterparty="ROSSI MARCO")
            add(f"tx_a{month:02d}3", back + 12, -14.99,
                "ADDEBITO SEPA 4411",
                provider_category="subscriptions")

        # Una bolletta, una spesa grossa, due spese di tutti i giorni.
        add("tx_b001", 8, -118.42, "ENERGIA ITALIA S.P.A. FATT 8891",
            counterparty="ENERGIA ITALIA S.P.A.", provider_category="utilities")
        add("tx_b002", 5, -4000.00, "BONIFICO STUDIO NOTARILE BIANCHI",
            counterparty="STUDIO NOTARILE BIANCHI")
        add("tx_b003", 2, -36.20, "PAGAMENTO POS SUPERMERCATO",
            provider_category="groceries")
        add("tx_b004", 1, -12.00, "PAGAMENTO POS BAR CENTRALE",
            provider_category="restaurants")

        # Una riga ancora in sospeso: la banca la ricontabilizzera'.
        rows.append({
            "transaction_ref": "tx_b005",
            "booked_at": day(0),
            "amount": -22.50,
            "currency": "EUR",
            "description": "PAGAMENTO POS IN CORSO",
            "status": "pending",
        })

        if since:
            rows = [r for r in rows if str(r["booked_at"]) >= str(since)]
        return TransactionsPage(transactions=rows, next_cursor=None)

    def settle_the_pending_one(self) -> Dict[str, Any]:
        """La stessa riga, contabilizzata. Stesso riferimento, stato diverso."""
        return {
            "transaction_ref": "tx_b005",
            "booked_at": self.today.isoformat(),
            "amount": -22.50,
            "currency": "EUR",
            "description": "PAGAMENTO POS BAR CENTRALE",
            "status": "booked",
        }

    def reverse(self, transaction_ref: str) -> Dict[str, Any]:
        """Un movimento stornato: la banca dice che non e' piu' valido."""
        return {
            "transaction_ref": transaction_ref,
            "booked_at": self.today.isoformat(),
            "amount": 0.0,
            "currency": "EUR",
            "description": "STORNO",
            "status": "reversed",
        }


def build_bank_provider(mode: str = "") -> BankProviderProtocol:
    """
    Il provider da usare: quello vero se e' configurato, altrimenti il finto.

    La scelta non e' un ramo nascosto nella logica — e' una configurazione,
    dichiarata, e chi la legge sa subito con che cosa sta parlando. Senza
    credenziali il provider vero non si costruisce nemmeno: meglio dire
    «non e' collegato» che provarci e fallire su ogni chiamata.
    """
    wanted = (mode or os.environ.get("BANK_PROVIDER_MODE") or "").strip().lower()
    if not wanted:
        # Nessuna scelta esplicita: si usa quello che e' configurato. Un
        # aggregatore configurato e non usato sarebbe una sorpresa peggiore
        # di un aggregatore assente.
        wanted = (
            "enablebanking"
            if os.environ.get("ENABLE_BANKING_APPLICATION_ID", "").strip()
            else "fake"
        )
    if wanted in ("enablebanking", "enable_banking", "real"):
        from connectors.bank.enablebanking_provider import EnableBankingProvider

        return EnableBankingProvider.from_env()
    if wanted == "gocardless":
        from connectors.bank.gocardless_provider import GoCardlessProvider

        return GoCardlessProvider.from_env()
    if wanted != "fake":
        raise NotImplementedError(f"provider bancario sconosciuto: {wanted}")
    return FakeBankProvider()


def stable_ref(*parts: str) -> str:
    """Un riferimento stabile, per quando il provider non ne da' uno."""
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:24]
