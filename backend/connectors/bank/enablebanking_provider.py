"""
Una banca vera, letta attraverso Enable Banking.

    QUESTO FILE NON SA COSA SIGNIFICA UN MOVIMENTO. SA SOLO COME LEGGERLO.

Un traduttore, e nient'altro: prende quello che l'aggregatore risponde e lo
mette nella forma che il dominio si aspetta gia'. Nessuna categoria nasce
qui, nessuna soglia, nessun elenco di esercenti — quello che una riga vuol
dire lo decide il giudizio piu' avanti, guardando questa vita.

**Il contratto, verificato sulla documentazione e sull'API viva** (sandbox,
settembre 2026):

    JWT RS256, header {alg, typ, kid: application id}
              payload {iss: enablebanking.com, aud: api.enablebanking.com,
                       iat, exp = iat + 3600}
    GET  /application                    chi siamo, e in quale ambiente
    GET  /aspsps?country=IT              le banche collegabili
    POST /auth                           -> `url` dove la persona autorizza
    POST /sessions {code}                -> session_id + conti
    GET  /sessions/{id}                  la sessione e i suoi conti
    GET  /accounts/{uid}/balances        saldi tipizzati
    GET  /accounts/{uid}/transactions    con `continuation_key`

**Dove il loro modello e il nostro non combaciano**, e come si incastrano:

  *Non c'e' un segreto condiviso.* L'autenticazione e' una firma: una chiave
  RSA privata che sta sul server, mai altrove, e un `kid` che e' l'id
  dell'applicazione. Non c'e' niente da mandare in giro e niente da rubare
  da un log — il token si rifa' a ogni ora e non vale per nessun altro.

  *Il permesso della persona e' la sessione.* Il JWT e' dell'applicazione;
  quello che appartiene a chi collega il conto e' il `session_id`. Il
  protocollo del dominio passa un `access_token` per sorgente, e qui dentro
  quel parametro porta la sessione. E' l'unica scelta onesta: e' quello il
  permesso di questa persona, ed e' quello che va nel vault.

  *Gli importi non hanno segno.* Arriva un numero positivo e un indicatore —
  `CRDT` o `DBIT`. Il segno lo mettiamo noi, ed e' l'unica aritmetica di
  questo file: sbagliarla vorrebbe dire raccontare uno stipendio come una
  spesa.

  *Le date sono tre.* Contabile, valuta, e quella dell'operazione. Si tiene
  la contabile perche' e' quella che la banca considera avvenuta, e la valuta
  viaggia accanto per chi la vuole.

  *La classificazione non e' una categoria.* `bank_transaction_code` e
  `merchant_category_code` sono codici di schema bancario, non giudizi su una
  vita: viaggiano come indizio dentro le prove.

E una cosa che qui non c'e' e non ci sara': nessun verbo che muove denaro.
Enable Banking offre anche l'avvio dei pagamenti — e' un altro consenso e un
altro prodotto. Questo file parla solo di informazioni di conto.
"""

from __future__ import annotations

import logging
import os
import time
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

logger = logging.getLogger("ora.connectors.bank.enablebanking")

API_ORIGIN = "https://api.enablebanking.com"

# Quanto dura il permesso che si chiede. Ogni banca dichiara il proprio
# massimo (`maximum_consent_validity`) e chiedere piu' di quello fa fallire
# l'autorizzazione: si chiede questo e ci si adatta a quello che concede.
WANTED_ACCESS_DAYS = 90

# Quanta storia alla prima lettura. Servono abbastanza ripetizioni per poter
# dire «questo succede ogni mese», che sono pochi mesi.
FIRST_LOOK_DAYS = 180

# Quale saldo e' «quanto c'e'» e quale «quanto posso usare». I codici sono
# dello standard, non nostri. La distinzione conta: il disponibile tiene
# conto di quello che e' gia' impegnato, ed e' il numero che una persona vede
# quando apre l'app della banca.
BOOKED_KINDS = ("CLBD", "ITBD", "OPBD", "PRCD")
AVAILABLE_KINDS = ("CLAV", "ITAV", "FWAV", "XPCD")

# Quante pagine al massimo in una lettura. La continuazione puo' teoricamente
# non finire mai; un tetto e' l'unica difesa contro un ciclo che gira per
# sempre su una risposta malformata.
MAX_PAGES = 20


class EnableBankingNotConfigured(RuntimeError):
    """Manca l'applicazione o la chiave. Non e' un errore di rete."""


@dataclass
class Institution:
    """Una banca fra quelle collegabili, come la si mostra a una persona."""

    id: str
    name: str
    country: str = ""
    logo: str = ""
    psu_types: Optional[List[str]] = None
    max_consent_seconds: Optional[int] = None
    sandbox: bool = False


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _number(value: Any) -> Optional[float]:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _name_of(party: Any) -> str:
    """Il nome di chi c'e' dall'altra parte, comunque lo abbiano impacchettato."""
    if isinstance(party, dict):
        return _text(party.get("name"))
    return _text(party)


class EnableBankingProvider:
    """
    Il traduttore. Rispetta `BankProviderProtocol` e aggiunge il consenso.

    I tre verbi di lettura sono quelli del protocollo e non cambiano; quello
    che c'e' in piu' — elenco delle banche, avvio dell'autorizzazione,
    apertura e chiusura della sessione — e' il ciclo di vita del consenso.
    """

    def __init__(
        self,
        *,
        application_id: str,
        private_key_path: str,
        redirect_uri: str = "",
        environment: str = "sandbox",
        api_origin: str = API_ORIGIN,
        http: Any = None,
    ):
        if not application_id or not private_key_path:
            raise EnableBankingNotConfigured(
                "servono l'id dell'applicazione e il percorso della chiave"
            )
        if not os.path.isfile(private_key_path):
            raise EnableBankingNotConfigured(
                "la chiave privata non si trova dove dice la configurazione"
            )
        self.application_id = application_id
        # Il *percorso*, non la chiave. Il contenuto si legge quando serve e
        # non resta in memoria piu' del necessario: un oggetto che porta in
        # giro una chiave privata finisce prima o poi dentro un repr.
        self._key_path = private_key_path
        self.redirect_uri = redirect_uri
        self.environment = (environment or "sandbox").lower()
        self.api_origin = api_origin.rstrip("/")
        self._http = http
        self._token: str = ""
        self._token_until: float = 0.0
        self.last_limits: Dict[str, Any] = {}

    # --- la porta ----------------------------------------------------------

    @classmethod
    def from_env(cls, *, http: Any = None) -> "EnableBankingProvider":
        """
        La configurazione sta nell'ambiente, e da nessun'altra parte.

        Non nel repository, non in una fixture, non nel database, non in un
        log. Se manca, questa funzione lo dice — e chi la chiama traduce la
        mancanza in una frase per una persona, invece di far finta di aver
        provato.
        """
        return cls(
            application_id=os.environ.get("ENABLE_BANKING_APPLICATION_ID", "").strip(),
            private_key_path=os.environ.get(
                "ENABLE_BANKING_PRIVATE_KEY_PATH", "").strip().strip('"'),
            redirect_uri=os.environ.get("ENABLE_BANKING_REDIRECT_URI", "").strip(),
            environment=os.environ.get("ENABLE_BANKING_ENV", "sandbox").strip(),
            http=http,
        )

    @property
    def is_sandbox(self) -> bool:
        return self.environment != "production"

    async def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.AsyncClient(timeout=60.0)
        return self._http

    # --- il permesso di parlare con l'API ----------------------------------

    def _sign(self) -> str:
        """
        Un JWT firmato con la chiave privata dell'applicazione.

            LA CHIAVE NON ESCE DA QUESTA FUNZIONE.

        Si legge dal disco, si firma, e si lascia andare. Non viene messa in
        un attributo, non viene passata a nessuno, non compare in nessun
        messaggio di errore: quello che gira e' la firma, che vale un'ora e
        non serve a nient'altro.
        """
        import jwt as pyjwt

        now = int(time.time())
        try:
            with open(self._key_path, "rb") as handle:
                key = handle.read()
        except OSError as e:
            # Il messaggio dice cosa manca, non dove: un percorso in un log
            # e' meta' del lavoro di chi cerca la chiave.
            raise EnableBankingNotConfigured(
                f"non riesco a leggere la chiave privata ({type(e).__name__})"
            ) from None
        return pyjwt.encode(
            {
                "iss": "enablebanking.com",
                "aud": "api.enablebanking.com",
                "iat": now,
                "exp": now + 3600,
            },
            key,
            algorithm="RS256",
            headers={"kid": self.application_id},
        )

    def _bearer(self) -> str:
        """La firma corrente, rifatta quando sta per scadere."""
        now = time.time()
        if self._token and self._token_until > now + 60:
            return self._token
        self._token = self._sign()
        self._token_until = now + 3600
        return self._token

    async def _call(
        self, method: str, path: str, *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Una chiamata, e la traduzione dei suoi modi di andare male.

        Il corpo di un errore non entra mai nei log: puo' contenere il nome
        dell'intestatario, un IBAN, o l'eco di quello che gli abbiamo
        mandato. Resta il codice, che e' tutto quello che serve per decidere
        cosa fare.
        """
        client = await self._client()
        response = await client.request(
            method, f"{self.api_origin}{path}",
            headers={
                "Authorization": f"Bearer {self._bearer()}",
                "Accept": "application/json",
            },
            json=json, params=params,
        )
        status = int(getattr(response, "status_code", 0))
        if status == 429:
            raise BankRateLimited(self._retry_after(getattr(response, "headers", {})))
        if status >= 400:
            logger.info(
                "enablebanking %s %s -> %s", method, path.split("/")[1] or "/", status,
            )
            raise BankAPIError(status)
        try:
            return response.json() or {}
        except Exception:
            return {}

    @staticmethod
    def _retry_after(headers: Any) -> int:
        for name in ("Retry-After", "X-RateLimit-Reset"):
            try:
                value = int(headers.get(name))
            except (TypeError, ValueError, AttributeError):
                continue
            if value > 0:
                return value
        return 3600

    # --- il ciclo di vita del consenso -------------------------------------

    async def whoami(self) -> Dict[str, Any]:
        """
        Chi siamo per l'aggregatore, e in quale ambiente.

        Serve per dire a una persona «ambiente di prova» invece di lasciarle
        credere che stia guardando la propria banca vera.
        """
        got = await self._call("GET", "/application")
        return {
            "nome": _text(got.get("name")),
            "ambiente": _text(got.get("environment")).lower(),
            "paesi": list(got.get("countries") or []),
            "attiva": bool(got.get("active")),
        }

    async def institutions(self, *, country: str = "IT") -> List[Institution]:
        """Le banche collegabili in un paese, come le elenca l'aggregatore."""
        got = await self._call("GET", "/aspsps", params={"country": country})
        out: List[Institution] = []
        for row in got.get("aspsps") or []:
            name = _text(row.get("name"))
            place = _text(row.get("country")) or country
            if not name:
                continue
            out.append(Institution(
                # Enable Banking identifica una banca con nome + paese, non
                # con un id: la coppia e' la chiave, e va tenuta insieme.
                id=f"{place}:{name}",
                name=name,
                country=place,
                logo=_text(row.get("logo")),
                psu_types=list(row.get("psu_types") or []),
                max_consent_seconds=row.get("maximum_consent_validity"),
                sandbox=self.is_sandbox,
            ))
        out.sort(key=lambda i: i.name.lower())
        return out

    async def begin_link(
        self, *, institution_id: str, redirect: str, reference: str,
        language: str = "IT", psu_type: str = "personal",
        access_days: int = WANTED_ACCESS_DAYS,
    ) -> Dict[str, Any]:
        """
        Prepara l'autorizzazione e restituisci dove la persona deve andare.

            LE CREDENZIALI DELLA BANCA NON PASSANO MAI DA NOI.

        L'indirizzo che torna e' il percorso ufficiale: la persona autentica
        sul sito della propria banca, e quello che torna indietro e' un
        codice, non una password. Se ORA chiedesse le credenziali sarebbe
        phishing con una buona intenzione, che resta phishing.
        """
        country, _, name = institution_id.partition(":")
        if not name:
            country, name = "IT", institution_id

        valid_until = (
            datetime.now(timezone.utc) + timedelta(days=access_days)
        ).replace(microsecond=0).isoformat()

        made = await self._call("POST", "/auth", json={
            "access": {"valid_until": valid_until},
            "aspsp": {"name": name, "country": country},
            "state": reference,
            # L'indirizzo di ritorno non e' una scelta: e' quello registrato
            # nell'applicazione, e l'aggregatore rifiuta tutto il resto con
            # «REDIRECT_URI_NOT_ALLOWED». Dove va la persona *dopo* — la
            # schermata dell'app — e' un'altra cosa, e la decide la porta di
            # ritorno una volta che il codice e' stato speso.
            "redirect_url": self.redirect_uri or redirect,
            "psu_type": psu_type,
        })
        return {
            "link": _text(made.get("url")),
            # Enable Banking non consegna niente da tenere a questo punto: il
            # permesso nasce dopo, quando il codice diventa una sessione.
            "requisition_id": "",
            "status": "CR",
        }

    async def open_session(self, *, code: str) -> Dict[str, Any]:
        """
        Il codice del ritorno diventa una sessione, e la sessione i conti.

        E' il passaggio che non si puo' saltare: senza, quello che si ha in
        mano e' un biglietto usato una volta, non un permesso.
        """
        got = await self._call("POST", "/sessions", json={"code": code})
        return {
            "session_id": _text(got.get("session_id")),
            "accounts": [
                _text(a.get("uid")) if isinstance(a, dict) else _text(a)
                for a in (got.get("accounts") or [])
            ],
            "raw_accounts": list(got.get("accounts") or []),
            "aspsp": got.get("aspsp") or {},
            "valid_until": _text((got.get("access") or {}).get("valid_until")),
        }

    async def link_status(self, session_id: str) -> Dict[str, Any]:
        """
        A che punto e' il collegamento, e quali conti ci sono dentro.

        Gli stati restano quelli del dominio — CR, LN, EX — perche' e' il
        servizio a tradurli in frasi, e due traduzioni in due posti
        divergerebbero al primo cambiamento.
        """
        if not session_id:
            return {"status": "CR", "accounts": [], "institution_id": ""}
        try:
            got = await self._call("GET", f"/sessions/{session_id}")
        except BankAPIError as e:
            if e.consent_expired or e.status_code == 404:
                return {"status": "EX", "accounts": [], "institution_id": ""}
            raise
        status = _text(got.get("status")).upper()
        aspsp = got.get("aspsp") or {}
        return {
            "status": "EX" if status in ("EXPIRED", "REVOKED", "CANCELLED") else "LN",
            "accounts": [
                _text(a.get("uid")) if isinstance(a, dict) else _text(a)
                for a in (got.get("accounts") or got.get("accounts_data") or [])
            ],
            "institution_id": f"{_text(aspsp.get('country'))}:{_text(aspsp.get('name'))}",
        }

    async def end_link(self, session_id: str) -> bool:
        """
        Chiudi la sessione dal lato dell'aggregatore.

        Non e' pulizia: finche' la sessione vive, il permesso di leggere quel
        conto esiste. Scollegare in ORA senza chiuderla lascerebbe in piedi
        esattamente la cosa che la persona ha chiesto di togliere.
        """
        if not session_id:
            return True
        try:
            await self._call("DELETE", f"/sessions/{session_id}")
            return True
        except BankAPIError as e:
            # Gia' sparita, o mai esistita: per la persona il risultato e' lo
            # stesso, e insistere non lo migliora.
            logger.info("end_link non-fatal (%s)", e.status_code)
            return e.status_code in (404, 410)

    # --- i tre verbi di lettura --------------------------------------------

    async def accounts(self, *, access_token: str) -> List[AccountSummary]:
        """
        I conti di questa persona. `access_token` e' la sessione.

        Il dettaglio si prende dalla sessione stessa: una chiamata invece di
        una per conto, ed e' la quota di qualcuno.

            LA SESSIONE DICE I CONTI IN DUE MODI, E NON SONO LO STESSO.

        Trovato sull'API vera, non sulla documentazione: la risposta a
        `POST /sessions` mette gli oggetti-conto dentro `accounts`, mentre
        `GET /sessions/{id}` mette li' soltanto gli identificativi e i
        dettagli in `accounts_data`. Leggendo solo `accounts` da entrambe, la
        seconda tornava una lista di stringhe che venivano scartate — e il
        collegamento risultava riuscito con zero conti dentro.
        """
        if not access_token:
            return []
        got = await self._call("GET", f"/sessions/{access_token}")
        aspsp = got.get("aspsp") or {}
        institution = _text(aspsp.get("name")) or "Banca"

        described = [r for r in (got.get("accounts_data") or []) if isinstance(r, dict)]
        if not described:
            described = [r for r in (got.get("accounts") or []) if isinstance(r, dict)]

        out: List[AccountSummary] = [
            self._account(row, institution) for row in described
        ]
        if out:
            return out

        # Solo identificativi, nessun dettaglio: e' comunque un conto, e
        # saperlo con un nome povero e' meglio che non vederlo affatto.
        return [
            AccountSummary(
                account_ref=_text(uid), display_name="Conto",
                institution=institution, currency="EUR",
            )
            for uid in (got.get("accounts") or []) if _text(uid)
        ]

    def _account(self, row: Dict[str, Any], institution: str) -> AccountSummary:
        identification = row.get("account_id") or {}
        iban = _text(identification.get("iban")) if isinstance(identification, dict) else ""
        name = (
            _text(row.get("product"))
            or _text(row.get("name"))
            or _text(row.get("usage"))
            or "Conto"
        )
        return AccountSummary(
            account_ref=_text(row.get("uid")),
            display_name=name[:120],
            institution=institution,
            currency=_text(row.get("currency")) or "EUR",
            account_type=_text(row.get("cash_account_type")) or None,
            owner_relationship=None,
            # L'IBAN non entra qui e non entra nel database: quello che serve
            # per distinguere due conti sono le ultime quattro cifre. Se la
            # banca non da' un IBAN non si mostra niente — le ultime quattro
            # lettere di un hash non dicono niente a nessuno, e sembrano un
            # numero di conto senza esserlo.
            masked_number=_mask(iban),
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
        got = await self._call("GET", f"/accounts/{account_ref}/balances")

        booked: Optional[float] = None
        available: Optional[float] = None
        currency = ""
        when = ""
        for row in got.get("balances") or []:
            kind = _text(row.get("balance_type")).upper()
            money = row.get("balance_amount") or {}
            amount = _number(money.get("amount"))
            if amount is None:
                continue
            currency = _text(money.get("currency")) or currency
            when = (
                _text(row.get("last_change_date_time"))
                or _text(row.get("reference_date"))
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
            "currency": currency or "EUR",
            "at": when or datetime.now(timezone.utc).isoformat(),
        }

    async def transactions(
        self, *, access_token: str, account_ref: str,
        since: Optional[str] = None, cursor: Optional[str] = None,
    ) -> TransactionsPage:
        """
        I movimenti, seguendo la continuazione finche' ce n'e'.

        Fermarsi alla prima pagina vorrebbe dire perdere in silenzio tutto
        quello che sta dietro — e nessuno se ne accorgerebbe, perche' una
        pagina di movimenti sembra un estratto conto.
        """
        params: Dict[str, Any] = {}
        if since:
            params["date_from"] = str(since)[:10]
        if cursor:
            params["continuation_key"] = cursor

        rows: List[Dict[str, Any]] = []
        pages = 0
        key: Optional[str] = cursor
        while pages < MAX_PAGES:
            page = await self._call(
                "GET", f"/accounts/{account_ref}/transactions", params=params,
            )
            for raw in page.get("transactions") or []:
                rows.append(self._movement(raw, account_ref))
            pages += 1
            key = _text(page.get("continuation_key")) or ""
            if not key:
                key = None
                break
            params["continuation_key"] = key

        return TransactionsPage(transactions=rows, next_cursor=key)

    @staticmethod
    def _movement(raw: Dict[str, Any], account_ref: str) -> Dict[str, Any]:
        """
        Una riga della banca, tradotta e non interpretata.

        L'unica aritmetica e' il segno, che qui non arriva: l'importo e'
        positivo e la direzione sta in un indicatore. Sbagliare quella
        traduzione vorrebbe dire raccontare uno stipendio come una spesa.
        """
        money = raw.get("transaction_amount") or {}
        size = _number(money.get("amount")) or 0.0
        currency = _text(money.get("currency")) or "EUR"

        indicator = _text(raw.get("credit_debit_indicator")).upper()
        incoming = indicator.startswith("CRDT") or indicator == "CRED"
        amount = abs(size) if incoming else -abs(size)

        when = (
            _text(raw.get("booking_date"))
            or _text(raw.get("transaction_date"))
            or _text(raw.get("value_date"))
        )

        described = " ".join(
            _text(x) for x in (raw.get("remittance_information") or []) if x
        ).strip()
        if not described:
            described = _text(raw.get("note")) or _text(raw.get("reference_number"))

        other = _name_of(raw.get("debtor") if incoming else raw.get("creditor"))
        if not other:
            other = _name_of(raw.get("creditor")) or _name_of(raw.get("debtor"))

        status = "pending" if _text(raw.get("status")).upper() == "PDNG" else "booked"

        ref = (
            _text(raw.get("entry_reference"))
            or _text(raw.get("transaction_id"))
            # Senza identificativo se ne calcola uno dai campi che non
            # cambiano quando la riga si consolida. Non e' perfetto e non
            # pretende di esserlo: e' meglio di due volte lo stesso caffe'.
            or stable_ref(account_ref, when[:10], f"{amount:.2f}", described[:60])
        )

        code = raw.get("bank_transaction_code") or {}
        hint = (
            _text(code.get("code")) if isinstance(code, dict) else _text(code)
        ) or _text(raw.get("merchant_category_code"))

        return {
            "transaction_ref": ref,
            "booked_at": when or datetime.now(timezone.utc).isoformat(),
            "value_at": _text(raw.get("value_date")) or None,
            "amount": amount,
            "currency": currency,
            "description": described[:300],
            "counterparty": other[:200] or None,
            # Il codice di schema della banca. Non e' una categoria e non
            # diventa un nome: resta fra le prove, dove il giudizio puo'
            # guardarlo e decidere che non gli serve.
            "provider_category": hint or None,
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
