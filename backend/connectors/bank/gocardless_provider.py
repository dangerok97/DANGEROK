"""
Una banca vera, letta attraverso GoCardless Bank Account Data.

    QUESTO FILE NON SA COSA SIGNIFICA UN MOVIMENTO. SA SOLO COME LEGGERLO.

E' un traduttore, e nient'altro: prende quello che l'aggregatore risponde e
lo mette nella forma che il dominio si aspetta gia' — `AccountSummary`,
righe grezze, saldo o niente. Nessuna categoria nasce qui, nessuna soglia,
nessun elenco di esercenti: quello che una riga vuol dire lo decide il
giudizio piu' avanti, guardando questa vita.

**Il contratto, verificato sulla documentazione corrente** (settembre 2026):

    POST /api/v2/token/new/         secret_id + secret_key -> refresh
    POST /api/v2/token/refresh/     refresh -> access (dura 24 ore)
    GET  /api/v2/institutions/      ?country=IT
    POST /api/v2/agreements/enduser/  quanta storia, per quanti giorni, cosa
    POST /api/v2/requisitions/      -> `link`, dove la persona autentica
    GET  /api/v2/requisitions/{id}/ -> stato + elenco conti
    GET  /api/v2/accounts/{id}/            metadati
    GET  /api/v2/accounts/{id}/details/    intestatario, IBAN, prodotto
    GET  /api/v2/accounts/{id}/balances/   saldi tipizzati
    GET  /api/v2/accounts/{id}/transactions/  booked + pending

**Dove il loro modello e il nostro non combaciano**, e come si incastrano:

  *Il token non e' della persona.* Il bearer di GoCardless e'
  dell'applicazione, non di chi collega il conto; quello che appartiene alla
  persona e' la *requisition*, il riferimento del consenso. Il protocollo del
  dominio passa un `access_token` per sorgente, e qui dentro quel parametro
  porta la requisition. E' l'unica scelta onesta: e' quello il permesso di
  questa persona, ed e' quello che va nel vault e che si revoca.

  *Il consenso scade per legge.* `max_access_valid_for_days` lo dice per
  ciascuna banca — novanta giorni tipici, con riconferma. Non e' un guasto:
  il servizio lo traduce gia' in «serve che tu autorizzi di nuovo».

  *Il tetto di chiamate e' della banca, non nostro.* Alcune concedono quattro
  letture al giorno per conto, e ogni endpoint conta per conto suo. Un 429
  arriva con l'ora in cui si potra' riprovare, e quell'ora vale piu' di
  qualunque cadenza decisa da noi.

  *Le righe non hanno sempre un identificativo.* `transactionId` c'e' quasi
  sempre sulle contabilizzate e spesso manca su quelle in sospeso; dove manca
  se ne calcola uno stabile dai campi che non cambiano.

  *La loro classificazione non e' una categoria.* `bankTransactionCode` e
  simili sono codici di schema bancario, non giudizi su una vita: viaggiano
  come indizio dentro le prove, dove il resto del sistema li tratta gia' come
  tali.

E una cosa che qui non c'e' e non ci sara': nessun verbo che muove denaro.
GoCardless ha anche un'API di pagamenti — e' un altro prodotto, un altro
dominio, un altro consenso. Questo file parla solo con Bank Account Data.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from connectors.bank.provider import (
    AccountSummary,
    BankAPIError,
    BankRateLimited,
    TransactionsPage,
    stable_ref,
)

logger = logging.getLogger("ora.connectors.bank.gocardless")

BASE_URL = "https://bankaccountdata.gocardless.com/api/v2"

# Quanta storia chiedere alla prima lettura, e per quanto tenere il permesso.
# Non sono numeri liberi: ogni banca dichiara i propri massimi, e chiedere
# piu' di quanto concede fa fallire l'accordo. Si chiede questo e si accetta
# quello che la banca concede.
WANTED_HISTORY_DAYS = 180
WANTED_ACCESS_DAYS = 90

# Cosa si chiede di poter leggere. Tre voci, tutte di lettura, e sono le
# uniche che questa API conosce.
ACCESS_SCOPE = ["balances", "details", "transactions"]

# Quale tipo di saldo e' «quanto c'e'» e quale e' «quanto posso usare».
# I nomi sono dello standard, non nostri, e la distinzione conta: il
# disponibile tiene conto di quello che e' gia' impegnato e non ancora
# contabilizzato, ed e' quello che una persona vede in banca.
BOOKED_KINDS = ("closingBooked", "interimBooked", "openingBooked")
AVAILABLE_KINDS = ("interimAvailable", "forwardAvailable", "expected")


class GoCardlessNotConfigured(RuntimeError):
    """Mancano le credenziali dell'applicazione. Non e' un errore di rete."""


@dataclass
class Institution:
    """Una banca fra quelle collegabili, come la si mostra a una persona."""

    id: str
    name: str
    logo: str = ""
    history_days: Optional[int] = None
    access_days: Optional[int] = None


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _number(value: Any) -> Optional[float]:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


class GoCardlessProvider:
    """
    Il traduttore. Rispetta `BankProviderProtocol` e aggiunge il consenso.

    I tre verbi di lettura sono quelli del protocollo e non cambiano; quello
    che c'e' in piu' — elenco delle banche, avvio del collegamento, stato,
    revoca — e' il ciclo di vita del consenso, che nel finto non esisteva
    perche' non c'era niente da consentire.
    """

    def __init__(
        self,
        *,
        secret_id: str,
        secret_key: str,
        base_url: str = BASE_URL,
        http: Any = None,
    ):
        if not secret_id or not secret_key:
            raise GoCardlessNotConfigured(
                "servono le credenziali dell'applicazione GoCardless"
            )
        self._secret_id = secret_id
        self._secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        # Un client iniettabile: i test parlano con un trasporto finto, e in
        # produzione si apre httpx. Nessun ramo «se test» dentro la logica.
        self._http = http
        self._access: str = ""
        self._access_until: Optional[datetime] = None
        self._refresh: str = ""
        self._refresh_until: Optional[datetime] = None
        # Quanto resta del tetto, come l'ha detto l'ultima risposta.
        self.last_limits: Dict[str, Any] = {}

    # --- la porta ----------------------------------------------------------

    @classmethod
    def from_env(cls, *, http: Any = None) -> "GoCardlessProvider":
        """
        Le credenziali stanno nell'ambiente, e da nessun'altra parte.

        Non nel repository, non in una fixture, non nel database, non in un
        log. Se non ci sono, questa funzione lo dice — e chi la chiama
        traduce la mancanza in una frase per una persona, invece di far
        finta di aver provato.
        """
        return cls(
            secret_id=os.environ.get("GOCARDLESS_SECRET_ID", "").strip(),
            secret_key=os.environ.get("GOCARDLESS_SECRET_KEY", "").strip(),
            http=http,
        )

    async def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    # --- il permesso di parlare con l'API ----------------------------------

    async def _bearer(self) -> str:
        """
        Il token dell'applicazione, preso quando serve e riusato finche' dura.

        Due gradini, come li ha disegnati loro: i segreti diventano un
        refresh a lunga vita, il refresh diventa un access che dura un
        giorno. Chiedere un token nuovo a ogni chiamata funzionerebbe e
        sarebbe uno spreco che si paga in quota.
        """
        now = datetime.now(timezone.utc)
        if self._access and self._access_until and self._access_until > now:
            return self._access

        if not self._refresh or not self._refresh_until or self._refresh_until <= now:
            got = await self._call(
                "POST", "/token/new/", authenticated=False,
                json={"secret_id": self._secret_id, "secret_key": self._secret_key},
            )
            self._refresh = _text(got.get("refresh"))
            self._refresh_until = now + timedelta(
                seconds=int(got.get("refresh_expires") or 2592000)
            )
            # Alcune risposte danno subito anche l'access: se c'e', si usa.
            if got.get("access"):
                self._access = _text(got.get("access"))
                self._access_until = now + timedelta(
                    seconds=int(got.get("access_expires") or 86400)
                )
                return self._access

        got = await self._call(
            "POST", "/token/refresh/", authenticated=False,
            json={"refresh": self._refresh},
        )
        self._access = _text(got.get("access"))
        self._access_until = now + timedelta(
            seconds=int(got.get("access_expires") or 86400)
        )
        return self._access

    async def _call(
        self, method: str, path: str, *, authenticated: bool = True,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Una chiamata, e la traduzione dei suoi modi di andare male.

        Il corpo di un errore non entra mai nei log: puo' contenere il nome
        dell'intestatario, un IBAN, o l'eco dei segreti che gli abbiamo
        mandato. Resta il codice, che e' tutto quello che serve per decidere
        cosa fare.
        """
        client = await self._client()
        headers = {"accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {await self._bearer()}"

        response = await client.request(
            method, f"{self.base_url}{path}",
            headers=headers, json=json, params=params,
        )
        self._note_limits(getattr(response, "headers", {}) or {})

        status = int(getattr(response, "status_code", 0))
        if status == 429:
            raise BankRateLimited(self._retry_after(getattr(response, "headers", {})))
        if status >= 400:
            logger.info("gocardless %s %s -> %s", method, path.split("/")[1], status)
            raise BankAPIError(status)
        try:
            return response.json() or {}
        except Exception:
            return {}

    def _note_limits(self, headers: Any) -> None:
        """Quanto resta del tetto, per chi decide quando ripassare."""
        def read(name: str) -> Optional[int]:
            try:
                return int(headers.get(name))
            except (TypeError, ValueError, AttributeError):
                return None

        found = {
            "limit": read("HTTP_X_RATELIMIT_LIMIT"),
            "remaining": read("HTTP_X_RATELIMIT_REMAINING"),
            "reset_seconds": read("HTTP_X_RATELIMIT_RESET"),
            "account_remaining": read("HTTP_X_RATELIMIT_ACCOUNT_SUCCESS_REMAINING"),
            "account_reset_seconds": read("HTTP_X_RATELIMIT_ACCOUNT_SUCCESS_RESET"),
        }
        if any(v is not None for v in found.values()):
            self.last_limits = {k: v for k, v in found.items() if v is not None}

    @staticmethod
    def _retry_after(headers: Any) -> int:
        for name in ("HTTP_X_RATELIMIT_ACCOUNT_SUCCESS_RESET",
                     "HTTP_X_RATELIMIT_RESET", "Retry-After"):
            try:
                value = int(headers.get(name))
            except (TypeError, ValueError, AttributeError):
                continue
            if value > 0:
                return value
        # Nessuna indicazione: si aspetta il giro di un giorno, che e' la
        # finestra su cui questi tetti sono quasi sempre definiti.
        return 86400

    # --- il ciclo di vita del consenso -------------------------------------

    async def institutions(self, *, country: str = "IT") -> List[Institution]:
        """Le banche collegabili in un paese, come le elenca l'aggregatore."""
        got = await self._call("GET", "/institutions/", params={"country": country})
        rows = got if isinstance(got, list) else got.get("results") or []
        out: List[Institution] = []
        for row in rows:
            if not row.get("id"):
                continue
            out.append(Institution(
                id=_text(row.get("id")),
                name=_text(row.get("name")) or _text(row.get("id")),
                logo=_text(row.get("logo")),
                history_days=row.get("transaction_total_days"),
                access_days=row.get("max_access_valid_for_days"),
            ))
        out.sort(key=lambda i: i.name.lower())
        return out

    async def begin_link(
        self, *, institution_id: str, redirect: str, reference: str,
        language: str = "IT",
        history_days: int = WANTED_HISTORY_DAYS,
        access_days: int = WANTED_ACCESS_DAYS,
    ) -> Dict[str, Any]:
        """
        Prepara il collegamento e restituisci dove la persona deve andare.

            LE CREDENZIALI DELLA BANCA NON PASSANO MAI DA NOI.

        Il `link` che torna e' il percorso ufficiale: la persona autentica
        sul sito della propria banca, e quello che torna indietro e' un
        consenso, non una password. Se ORA chiedesse le credenziali sarebbe
        phishing con una buona intenzione, che resta phishing.
        """
        agreement = ""
        try:
            made = await self._call(
                "POST", "/agreements/enduser/",
                json={
                    "institution_id": institution_id,
                    "max_historical_days": history_days,
                    "access_valid_for_days": access_days,
                    "access_scope": list(ACCESS_SCOPE),
                },
            )
            agreement = _text(made.get("id"))
        except BankAPIError as e:
            # Una banca che concede meno di quanto si e' chiesto rifiuta
            # l'accordo su misura. Non e' un motivo per fermare tutto: si
            # procede con i termini standard di quella banca.
            logger.info("agreement declined (%s), using defaults", e.status_code)

        body: Dict[str, Any] = {
            "institution_id": institution_id,
            "redirect": redirect,
            "reference": reference,
            "user_language": language,
        }
        if agreement:
            body["agreement"] = agreement

        made = await self._call("POST", "/requisitions/", json=body)
        return {
            "requisition_id": _text(made.get("id")),
            "link": _text(made.get("link")),
            "status": _text(made.get("status")) or "CR",
        }

    async def link_status(self, requisition_id: str) -> Dict[str, Any]:
        """
        A che punto e' il collegamento, e quali conti sono arrivati.

        Gli stati sono i loro — CR, GC, UA, SA, GA, LN, RJ, EX — e restano
        codici fino al servizio, che li traduce in cose che una persona
        capisce. Tradurli qui vorrebbe dire due traduzioni in due posti.
        """
        got = await self._call("GET", f"/requisitions/{requisition_id}/")
        return {
            "status": _text(got.get("status")),
            "accounts": [_text(a) for a in (got.get("accounts") or [])],
            "institution_id": _text(got.get("institution_id")),
        }

    async def end_link(self, requisition_id: str) -> bool:
        """
        Chiudi il collegamento dal lato dell'aggregatore.

        Non e' un dettaglio di pulizia: finche' la requisition vive, il
        permesso di leggere quel conto esiste. Scollegare in ORA senza
        chiuderla lascerebbe in piedi esattamente la cosa che la persona ha
        appena chiesto di togliere.
        """
        try:
            await self._call("DELETE", f"/requisitions/{requisition_id}/")
            return True
        except BankAPIError as e:
            # Gia' sparita, o mai esistita: il risultato per la persona e' lo
            # stesso, e insistere non lo migliora.
            logger.info("end_link non-fatal (%s)", e.status_code)
            return e.status_code in (404, 410)

    # --- i tre verbi di lettura --------------------------------------------

    async def accounts(self, *, access_token: str) -> List[AccountSummary]:
        """
        I conti collegati da questa persona. `access_token` e' la requisition.

        Per ciascuno si chiedono i metadati e i dettagli: sono due chiamate
        per conto, e si fanno una volta al collegamento e poi di rado —
        perche' ognuna consuma il tetto giornaliero della banca.
        """
        linked = await self.link_status(access_token)
        out: List[AccountSummary] = []
        for account_id in linked["accounts"]:
            out.append(await self._account(account_id))
        return out

    async def _account(self, account_id: str) -> AccountSummary:
        meta = await self._call("GET", f"/accounts/{account_id}/")
        status = _text(meta.get("status")).upper()
        if status in ("SUSPENDED", "EXPIRED"):
            # Il conto c'e' ma non e' leggibile: e' un consenso da rifare,
            # ed e' esattamente quello che 403 significa piu' avanti.
            raise BankAPIError(403, f"account_{status.lower()}")

        details: Dict[str, Any] = {}
        try:
            got = await self._call("GET", f"/accounts/{account_id}/details/")
            details = got.get("account") or got or {}
        except BankAPIError as e:
            # I dettagli sono un lusso: senza, il conto ha un nome piu'
            # povero e tutto il resto funziona.
            logger.info("details unavailable (%s)", e.status_code)

        name = (
            _text(details.get("name"))
            or _text(details.get("product"))
            or _text(meta.get("name"))
            or "Conto"
        )
        return AccountSummary(
            account_ref=account_id,
            display_name=name[:120],
            institution=_text(meta.get("institution_id")),
            currency=_text(details.get("currency")) or "EUR",
            account_type=_text(details.get("cashAccountType")) or None,
            owner_relationship=None,
            # L'IBAN non entra qui e non entra nel database: quello che serve
            # per distinguere due conti sono le ultime quattro cifre.
            masked_number=_mask(
                details.get("iban") or details.get("resourceId") or meta.get("iban")
            ),
        )

    async def balance(
        self, *, access_token: str, account_ref: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Quanto c'e' e quanto e' disponibile, tenuti distinti.

            UN SALDO E' UN'OSSERVAZIONE CON UN'ORA SOPRA.

        Se la banca non manda nessuno dei due, torna `None` — e chi legge
        scrivera' «non comunicato», non uno zero.
        """
        got = await self._call("GET", f"/accounts/{account_ref}/balances/")
        rows = got.get("balances") or []

        booked: Optional[float] = None
        available: Optional[float] = None
        currency = "EUR"
        when = ""
        for row in rows:
            kind = _text(row.get("balanceType"))
            amount = _number((row.get("balanceAmount") or {}).get("amount"))
            if amount is None:
                continue
            currency = _text((row.get("balanceAmount") or {}).get("currency")) or currency
            when = (
                _text(row.get("lastChangeDateTime"))
                or _text(row.get("referenceDate"))
                or when
            )
            if kind in BOOKED_KINDS and booked is None:
                booked = amount
            elif kind in AVAILABLE_KINDS and available is None:
                available = amount

        if booked is None and available is None:
            return None
        return {
            "current": booked,
            "available": available,
            "currency": currency,
            "at": when or datetime.now(timezone.utc).isoformat(),
        }

    async def transactions(
        self, *, access_token: str, account_ref: str,
        since: Optional[str] = None, cursor: Optional[str] = None,
    ) -> TransactionsPage:
        """
        I movimenti, contabilizzati e in sospeso, nella forma del dominio.

        Le due liste arrivano separate e restano distinguibili: una riga in
        sospeso e' vera ma provvisoria, e quando torna contabilizzata e' la
        stessa riga — il servizio la aggiorna invece di affiancarla, ed e'
        per questo che il riferimento deve essere stabile.
        """
        params: Dict[str, Any] = {}
        if since:
            params["date_from"] = str(since)[:10]
        got = await self._call(
            "GET", f"/accounts/{account_ref}/transactions/", params=params,
        )
        block = got.get("transactions") or {}

        rows: List[Dict[str, Any]] = []
        for raw in block.get("booked") or []:
            rows.append(self._movement(raw, account_ref, "booked"))
        for raw in block.get("pending") or []:
            rows.append(self._movement(raw, account_ref, "pending"))
        return TransactionsPage(transactions=rows, next_cursor=None)

    @staticmethod
    def _movement(
        raw: Dict[str, Any], account_ref: str, status: str,
    ) -> Dict[str, Any]:
        """
        Una riga della banca, tradotta e non interpretata.

        Il segno lo mette la banca e si rispetta. La controparte e' quella
        che la banca nomina, dal lato giusto. La descrizione e' quella che
        una persona leggerebbe sull'estratto conto. Niente altro: qui non si
        deduce nulla, e in particolare non si guarda la descrizione per
        decidere cosa la riga sia.
        """
        amount = _number((raw.get("transactionAmount") or {}).get("amount")) or 0.0
        currency = _text((raw.get("transactionAmount") or {}).get("currency")) or "EUR"
        when = (
            _text(raw.get("bookingDate"))
            or _text(raw.get("valueDate"))
            or _text(raw.get("bookingDateTime"))
            or _text(raw.get("valueDateTime"))
        )

        described = _text(raw.get("remittanceInformationUnstructured"))
        if not described:
            described = " ".join(
                _text(x) for x in (raw.get("remittanceInformationUnstructuredArray") or [])
            ).strip()
        if not described:
            described = _text(raw.get("additionalInformation"))

        # Chi c'e' dall'altra parte, dal lato che la banca ha compilato.
        other = _text(raw.get("creditorName")) if amount < 0 else _text(raw.get("debtorName"))
        if not other:
            other = _text(raw.get("creditorName")) or _text(raw.get("debtorName"))

        ref = (
            _text(raw.get("transactionId"))
            or _text(raw.get("internalTransactionId"))
            # Senza identificativo se ne calcola uno dai campi che non
            # cambiano quando la riga si consolida. Non e' perfetto e non
            # pretende di esserlo: e' meglio di due volte lo stesso caffe'.
            or stable_ref(account_ref, when[:10], f"{amount:.2f}", described[:60])
        )

        return {
            "transaction_ref": ref,
            "booked_at": when or datetime.now(timezone.utc).isoformat(),
            "amount": amount,
            "currency": currency,
            "description": described[:300],
            "counterparty": other[:200] or None,
            # Il codice di schema della banca. Non e' una categoria e non
            # diventa un nome: resta fra le prove, dove il giudizio puo'
            # guardarlo e decidere che non gli serve.
            "provider_category": (
                _text(raw.get("bankTransactionCode"))
                or _text(raw.get("proprietaryBankTransactionCode"))
                or None
            ),
            "status": status,
        }


def _mask(value: Any) -> Optional[str]:
    """
    Le ultime quattro cifre, e nient'altro.

        UN IBAN INTERO NON SERVE A DISTINGUERE DUE CONTI: SERVE A PAGARE.

    Non viene mai salvato per intero e non compare mai in una schermata. Chi
    ha due conti nella stessa banca ha bisogno di dirli l'uno dall'altro, e
    quattro cifre bastano.
    """
    text = _text(value).strip()
    if len(text) < 4:
        return None
    return "•••• " + text[-4:]
