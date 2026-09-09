"""
Leggere un conto: i movimenti nuovi, e nient'altro.

    UNA BANCA E' UNO STRUMENTO CHE SI LEGGE, NON UNO CHE SI USA.

Stessa disciplina del calendario e della casella: si riprende da dove si era
arrivati, si scrive una riga per ogni movimento nuovo, e si sposta il
segnaposto solo dopo una lettura finita. Un sync che si ferma a meta' e
sposta comunque il cursore perde in silenzio tutto quello che stava in mezzo.

Tre cose che una banca fa e le altre sorgenti no, e che quindi vivono qui.

**Il consenso scade.** PSD2 obbliga a rinnovarlo, quindi un 401 non e' un
guasto: e' una cosa da rifare, e la sorgente deve dirlo in modo che una
persona capisca — non «token non valido», ma «serve che tu autorizzi di
nuovo la banca».

**Le righe cambiano dopo essere state viste.** Un pagamento in sospeso
diventa contabilizzato, un addebito viene stornato. Lo stesso
`transaction_ref` torna con uno stato diverso, e la riga di prima va
aggiornata invece che affiancata.

**La categoria del provider e' un indizio.** Arriva, viene conservata fra le
prove, e non decide niente: quello che un movimento significa lo dice il
giudizio guardando questa vita, non un aggregatore che non la conosce.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from connectors.bank.provider import (
    BankAPIError,
    BankProviderProtocol,
    BankRateLimited,
    build_bank_provider,
)
from connectors.instances import ConnectorInstanceService
from financial.observation import BankObservation, ObservationStore

logger = logging.getLogger("ora.connectors.bank.service")

CONNECTOR_ID = "banking_psd2"
CAPABILITY_ID = "banking.read"

# Quanto indietro si guarda quando non si e' mai letto niente. Un conto ha
# anni di storia e non serve tutta: servono abbastanza ripetizioni per poter
# dire «questo succede ogni mese», che sono pochi mesi.
FIRST_LOOK_DAYS = 180

# Quanti movimenti una lettura tocca al massimo. Una banca non e' una casella:
# le righe arrivano a decine, non a migliaia, e chi torna da un anno di
# silenzio si smaltisce in piu' passaggi.
MAX_PER_SYNC = 300

# Entro quanti giorni una riga in sospeso puo' tornare contabilizzata ed
# essere ancora la stessa riga. Le banche ci mettono un giorno o due; una
# finestra larga rischierebbe di fondere due caffe' uguali di settimane
# diverse, una stretta lascerebbe passare un doppione.
SETTLES_WITHIN_DAYS = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


class BankReadService:
    """Collega un conto, leggi cosa e' successo, e fermati li'."""

    def __init__(self, *, db, permissions, vault,
                 provider: Optional[BankProviderProtocol] = None):
        self.db = db
        self.permissions = permissions
        self.vault = vault
        self.provider: BankProviderProtocol = provider or build_bank_provider()
        self.instances = ConnectorInstanceService(db)
        self.observations = ObservationStore(db)

    # --- collegare ---------------------------------------------------------

    async def connect(
        self, *, user_id: str, institution: str = "Banca di prova",
    ) -> Dict[str, Any]:
        """
        Registra il collegamento a una banca.

        Non c'e' un OAuth vero da fare: quando ci sara' un aggregatore, questo
        metodo ricevera' il suo riferimento di consenso e lo mettera' nel
        vault come fanno gia' Gmail e il calendario. La forma di quello che
        resta scritto e' pero' quella definitiva.
        """
        instance = await self.instances.upsert(
            user_id=user_id,
            connector_id=CONNECTOR_ID,
            provider_account_id=f"bank:{institution}",
            display_label=institution,
            authorized_scopes=["accounts:read", "transactions:read"],
            secret_reference="",
            status="connected",
            metadata={"institution": institution},
            # Una banca non e' una casella: le righe arrivano quando arrivano,
            # e guardarla ogni minuto non le fa arrivare prima. Sei ore sono
            # piu' che sufficienti, e sono gentili con la quota del provider.
            poll_interval_min=360,
        )
        return {"ok": True, "instance_id": instance["id"]}

    # --- leggere -----------------------------------------------------------

    async def sync(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        """
        Leggi cosa e' successo sui conti di questa persona dall'ultima volta.
        """
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")

        cursor = dict(instance.get("cursor") or {})
        since = cursor.get("since") or (
            datetime.now(timezone.utc) - timedelta(days=FIRST_LOOK_DAYS)
        ).isoformat()

        token = await self._access_token(user_id=user_id, instance=instance)

        try:
            accounts = await self.provider.accounts(access_token=token)
        except BankAPIError as e:
            return await self._could_not_read(user_id, instance_id, e)

        written = 0
        updated = 0
        skipped = 0
        seen_accounts: List[Dict[str, Any]] = []

        for account in accounts:
            account = await self._with_balance(token, account)
            await self._remember_account(user_id, instance_id, account)
            seen_accounts.append({"account_ref": account.account_ref})

            try:
                page = await self.provider.transactions(
                    access_token=token, account_ref=account.account_ref,
                    since=since,
                )
            except BankAPIError as e:
                return await self._could_not_read(user_id, instance_id, e)

            for raw in page.transactions[:MAX_PER_SYNC]:
                outcome = await self._record(user_id, instance_id, account, raw)
                if outcome == "written":
                    written += 1
                elif outcome == "updated":
                    updated += 1
                else:
                    skipped += 1

        # Il segnaposto si sposta solo adesso, a lettura finita. Un giorno
        # indietro di margine: le banche contabilizzano in ritardo, e una
        # finestra al millimetro perde le righe arrivate tardi.
        #
        #     UNA LETTURA SENZA CONTI NON E' UNA LETTURA.
        #
        # Trovato sul collegamento sandbox vero: la prima lettura non aveva
        # riconosciuto nessun conto — un difetto di traduzione — e ha
        # comunque portato il segnaposto a ieri. La lettura successiva, con
        # il difetto corretto, ha chiesto alla banca solo l'ultimo giorno: i
        # sei mesi di storia erano stati saltati per sempre, in silenzio, e
        # nessun errore lo diceva. Se non si e' letto niente, il segnaposto
        # resta dov'era.
        if seen_accounts:
            cursor["since"] = (
                datetime.now(timezone.utc) - timedelta(days=1)
            ).isoformat()
        await self.instances.update(user_id, instance_id, {
            "cursor": cursor, "last_sync_at": _now_iso(),
        })

        try:
            await self.permissions.audit.log(
                user_id=user_id, event_type="bank.sync", connector_id=CONNECTOR_ID,
                connector_instance_id=instance_id, capability_id=CAPABILITY_ID,
                success=True, records_returned=written,
                data_classification="highly_sensitive",
            )
        except Exception as e:
            logger.info("audit soft-fail: %s", type(e).__name__)

        return {
            "ok": True, "written": written, "updated": updated,
            "skipped": skipped, "accounts": len(seen_accounts),
        }

    async def _record(
        self, user_id: str, instance_id: str, account, raw: Dict[str, Any],
    ) -> str:
        """
        Una riga della banca come osservazione. Mai come categoria.

        Lo stato conta: una riga in sospeso e' vera ma provvisoria, e quando
        torna contabilizzata e' la stessa riga con un altro importo o un'altra
        data. Aggiornarla e' l'unico modo di non avere due volte lo stesso
        caffe'.
        """
        ref = str(raw.get("transaction_ref") or "").strip()
        if not ref:
            return "skipped"

        amount = float(raw.get("amount") or 0.0)
        status = str(raw.get("status") or "booked").lower()

        observation = BankObservation(
            owner_id=user_id,
            account_ref=account.account_ref,
            transaction_ref=ref,
            booked_at=str(raw.get("booked_at") or _now_iso()),
            amount=amount,
            currency=str(raw.get("currency") or account.currency or "EUR"),
            direction="incoming" if amount > 0 else "outgoing",
            raw_description=str(raw.get("description") or "")[:300],
            counterparty=(
                str(raw.get("counterparty"))[:200]
                if raw.get("counterparty") else None
            ),
            balance_after=raw.get("balance_after"),
            provenance={
                "connector_id": CONNECTOR_ID,
                "instance_id": instance_id,
                "institution": account.institution,
                # La classificazione del provider viaggia come indizio, in
                # mezzo alle prove. Non e' la nostra e non deve diventarlo:
                # un aggregatore che chiama «utilities» un rimborso non
                # conosce questa vita.
                "provider_hint": raw.get("provider_category"),
                "status": status,
            },
        )

        existing = await self.db["financial_observations"].find_one(
            {"owner_id": user_id, "transaction_ref": ref}, {"_id": 0, "id": 1, "provenance": 1},
        )
        if existing is None and status == "booked":
            # La stessa riga, contabilizzata, quando la banca non le da' un
            # identificativo finche' e' in sospeso.
            #
            #     UNA RIGA CHE SI CONSOLIDA CAMBIA DATA. E CAMBIAVA IDENTITA'.
            #
            # Senza identificativo il riferimento si calcola dai campi, e la
            # data e' uno di quelli: quando il pagamento passa da «in corso»
            # a contabilizzato, la data si sposta e la riga sembra un'altra.
            # Risultato: due volte lo stesso caffe', e nessuno se ne accorge
            # perche' entrambe le righe sono vere.
            #
            # Quindi si guarda se c'e' una riga in sospeso che *e'* questa:
            # stesso conto, stesso importo, stessa descrizione, a pochi
            # giorni di distanza. Nessuna di queste e' un'interpretazione —
            # sono le stesse quattro cose scritte due volte dalla banca.
            existing = await self._pending_twin(user_id, account, observation)

        if existing:
            was = str(((existing.get("provenance") or {}).get("status") or "booked"))
            if was == status:
                return "skipped"
            # La stessa riga con un altro stato: in sospeso che si chiude,
            # oppure stornata. Si aggiorna quella che c'e'.
            await self.db["financial_observations"].update_one(
                {"id": existing["id"]},
                {"$set": {
                    "transaction_ref": observation.transaction_ref,
                    "amount": observation.amount,
                    "booked_at": observation.booked_at,
                    "raw_description": observation.raw_description,
                    "provenance": observation.provenance,
                }},
            )
            return "updated"

        return "written" if await self.observations.record(observation) else "skipped"

    async def _with_balance(self, token: str, account):
        """
        Il saldo, chiesto a parte quando il conto non lo porta gia'.

            SALDO CONTABILE E SALDO DISPONIBILE NON SONO LA STESSA COSA.

        Il primo e' quello che la banca ha registrato, il secondo tiene conto
        di quello che e' gia' impegnato e non ancora contabilizzato — ed e'
        il numero che una persona vede quando apre l'app della banca. Restano
        distinti fin qui dentro: unirli sarebbe scegliere per conto di chi
        legge quale dei due e' «il saldo», e la risposta dipende da cosa sta
        per fare.

        Una lettura in piu' per conto, e non e' gratis: molte banche
        concedono poche chiamate al giorno per ciascun endpoint. Se questa
        fallisce, il conto resta senza saldo — che e' meglio di un saldo
        inventato.
        """
        if account.current_balance is not None or account.available_balance is not None:
            return account
        try:
            got = await self.provider.balance(
                access_token=token, account_ref=account.account_ref,
            )
        except BankAPIError as e:
            logger.info("balance unavailable (%s)", e.status_code)
            return account
        if not got:
            return account
        account.current_balance = got.get("current")
        account.available_balance = got.get("available")
        account.balance_at = str(got.get("at") or _now_iso())
        if got.get("currency"):
            account.currency = str(got["currency"])
        return account

    async def _pending_twin(self, user_id: str, account, observation):
        """
        La riga in sospeso che questa contabilizzazione sta chiudendo, se c'e'.

        Quattro cose devono coincidere — conto, importo, descrizione, e pochi
        giorni di distanza — e sono tutte scritte dalla banca. Non si
        interpreta niente: si riconosce la stessa riga vista due volte in due
        momenti della sua vita.
        """
        when = _moment(observation.booked_at)
        if when is None:
            return None
        window = {
            "$gte": (when - timedelta(days=SETTLES_WITHIN_DAYS)).isoformat(),
            "$lte": (when + timedelta(days=SETTLES_WITHIN_DAYS)).isoformat(),
        }
        return await self.db["financial_observations"].find_one(
            {
                "owner_id": user_id,
                "account_ref": account.account_ref,
                "provenance.status": "pending",
                "amount": observation.amount,
                "raw_description": observation.raw_description,
                "booked_at": window,
            },
            {"_id": 0, "id": 1, "provenance": 1},
        )

    async def _same_account_come_back(self, user_id: str, account) -> None:
        """
        Lo stesso conto, tornato con un altro identificativo. Uno solo resta.

            IL CONTO E' DELLA PERSONA. L'IDENTIFICATIVO E' DELLA SESSIONE.

        Trovato al primo ricollegamento vero: Enable Banking assegna un uid
        nuovo a ogni sessione autorizzata, quindi dopo aver ricollegato lo
        stesso conto della stessa banca arriva sotto un altro riferimento. La
        riga vecchia restava, marcata come scollegata — e la schermata
        mostrava lo stesso conto due volte: una volta fra i collegati e una
        volta fra le fonti che non lo sono piu'. Entrambe vere, insieme
        assurde.

        Quindi quando un conto torna, quello di prima viene riconosciuto e
        chiuso: i movimenti gia' osservati passano al riferimento nuovo — sono
        gli stessi movimenti dello stesso conto — e la riga vecchia sparisce.
        Non si perde niente: le osservazioni restano tutte, con la loro
        provenienza e le loro date.

        Il riconoscimento e' volutamente stretto: stessa banca, stessa valuta,
        stesso nome, e la riga vecchia dev'essere scollegata. Se entrambe
        portano le ultime quattro cifre e sono diverse, sono due conti veri e
        non si toccano.
        """
        previous = await self.db["bank_accounts"].find(
            {
                "owner_id": user_id,
                "institution": account.institution,
                "currency": account.currency,
                "display_name": account.display_name,
                "account_ref": {"$ne": account.account_ref},
                "source_disconnected_at": {"$ne": None},
            },
            {"_id": 0, "account_ref": 1, "masked_number": 1},
        ).to_list(5)

        mine = getattr(account, "masked_number", None)
        for row in previous:
            theirs = row.get("masked_number")
            if mine and theirs and mine != theirs:
                # Due conti diversi nella stessa banca. Restano due.
                continue
            old_ref = str(row.get("account_ref") or "")
            if not old_ref:
                continue
            await self.db["financial_observations"].update_many(
                {"owner_id": user_id, "account_ref": old_ref},
                {"$set": {"account_ref": account.account_ref}},
            )
            await self.db["bank_accounts"].delete_one(
                {"owner_id": user_id, "account_ref": old_ref},
            )
            logger.info("bank account reconciled after reconnect")

    async def _remember_account(self, user_id: str, instance_id: str, account) -> None:
        """
        Il conto come lo racconta la banca, aggiornato in un posto solo.

        Il saldo si scrive solo se c'e'. Se il provider non lo da', il campo
        resta assente — e chi legge sapra' che non lo sa, invece di leggere
        uno zero.
        """
        await self._same_account_come_back(user_id, account)
        patch: Dict[str, Any] = {
            "owner_id": user_id,
            "instance_id": instance_id,
            "account_ref": account.account_ref,
            "display_name": account.display_name,
            "institution": account.institution,
            "currency": account.currency,
            "account_type": account.account_type,
            "owner_relationship": account.owner_relationship,
            "updated_at": _now_iso(),
        }
        if account.current_balance is not None:
            patch["current_balance"] = account.current_balance
        if account.available_balance is not None:
            patch["available_balance"] = account.available_balance
        if account.balance_at:
            patch["balance_at"] = account.balance_at
        if getattr(account, "masked_number", None):
            # Le ultime quattro cifre, e solo quelle. L'IBAN intero non entra
            # nel database e non compare in nessuna schermata: non serve a
            # distinguere due conti, serve a pagare.
            patch["masked_number"] = account.masked_number
        # Un conto che torna a essere letto non e' piu' «scollegato».
        patch["source_disconnected_at"] = None

        await self.db["bank_accounts"].update_one(
            {"owner_id": user_id, "account_ref": account.account_ref},
            {"$set": patch},
            upsert=True,
        )

    async def _could_not_read(
        self, user_id: str, instance_id: str, error: BankAPIError,
    ) -> Dict[str, Any]:
        """
        Una lettura fallita lascia il conto che lo dice, e il cursore fermo.

        Se il consenso e' scaduto lo stato lo dice in modo che una persona
        capisca cosa deve fare: rifare l'autorizzazione, che e' una cosa che
        la legge le chiedera' ogni tre mesi per sempre.
        """
        if isinstance(error, BankRateLimited):
            # Il tetto della banca vale piu' della nostra cadenza: si sposta
            # l'appuntamento e non si tocca lo stato. Una sorgente marcata
            # «degradata» perche' ha finito le letture di oggi direbbe alla
            # persona che qualcosa e' rotto, e non e' rotto niente.
            when = await self._not_before(
                user_id, instance_id, error.retry_after_seconds,
            )
            return {
                "ok": False, "reason": "rate_limited", "next_allowed_at": when,
                "human": "La banca non concede altre letture per adesso. Riprovo dopo.",
            }

        expired = error.consent_expired
        await self.instances.mark_status(
            user_id, instance_id, "reauthorization_required" if expired else "degraded",
        )
        logger.info("bank read failed (%s)", error.status_code)
        return {
            "ok": False,
            "reason": "consent_expired" if expired else "provider_error",
            "human": (
                "Serve che tu autorizzi di nuovo la banca: il permesso scade "
                "ogni tre mesi." if expired
                else "Non sono riuscita a leggere il conto adesso."
            ),
        }

    async def _not_before(
        self, user_id: str, instance_id: str, seconds: int,
    ) -> str:
        """
        Scrivi l'ora prima della quale non si ripassa, dove la guarda la coda.

        In due posti perche' due cose diverse la leggono: il ciclo automatico
        interroga la coda dei tentativi, la schermata guarda l'istanza. Sono
        la stessa ora scritta due volte, e non due decisioni.
        """
        when = (
            datetime.now(timezone.utc) + timedelta(seconds=max(60, int(seconds)))
        ).isoformat()
        try:
            from connected.polling import hold_source

            await hold_source(self.db, user_id, instance_id, until=when)
        except Exception as e:
            logger.info("hold soft-fail: %s", type(e).__name__)
        await self.instances.update(
            user_id, instance_id, {"next_allowed_at": when},
        )
        return when

    # --- il consenso, delegato a chi lo sa raccontare -----------------------

    async def institutions(self, *, country: str = "IT") -> List[Dict[str, Any]]:
        """Le banche collegabili. Nessun giudizio, nessuna chiamata al modello."""
        from connectors.bank.link import institutions_for

        return await institutions_for(self, country=country)

    async def begin_link(
        self, *, user_id: str, institution_id: str, redirect_to: str,
    ) -> Dict[str, Any]:
        """Prepara il collegamento e dì alla persona dove autenticarsi."""
        from connectors.bank.link import begin_link

        return await begin_link(
            self, user_id=user_id, institution_id=institution_id,
            redirect_to=redirect_to,
        )

    async def finish_link(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        """Guarda se il collegamento e' andato in porto, e leggi la prima volta."""
        from connectors.bank.link import finish_link

        return await finish_link(self, user_id=user_id, instance_id=instance_id)

    async def state(self, *, user_id: str) -> Dict[str, Any]:
        """Com'e' messo il collegamento, in una frase."""
        from connectors.bank.link import connection_state

        return await connection_state(self, user_id=user_id)

    async def disconnect(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        """Scollega: chiudi il permesso, ferma le letture, tieni la memoria."""
        from connectors.bank.link import disconnect

        return await disconnect(self, user_id=user_id, instance_id=instance_id)

    async def _access_token(self, *, user_id: str, instance: Dict[str, Any]) -> str:
        """
        Il permesso di leggere, preso dal vault come per ogni altra sorgente.

        Con il provider finto non c'e' niente da prendere; la forma resta
        quella perche' e' dove un consenso vero andra' a incastrarsi.
        """
        secret_ref = instance.get("secret_reference")
        if not secret_ref:
            return "fake"
        payload = await self.vault.get(secret_ref, user_id=user_id)
        # Con un aggregatore vero il permesso di *questa persona* non e' un
        # token: e' il riferimento del suo consenso. Il token dell'API e'
        # dell'applicazione e se lo tiene il provider — mettere qui quello
        # sbagliato darebbe a chiunque i conti di chiunque.
        return str(
            (payload or {}).get("session_id")
            or (payload or {}).get("requisition_id")
            or (payload or {}).get("access_token")
            or ""
        )


async def accounts_of(db, owner_id: str) -> List[Dict[str, Any]]:
    """I conti collegati di questa persona, come la banca li descrive."""
    return await db["bank_accounts"].find(
        {"owner_id": owner_id}, {"_id": 0},
    ).sort("updated_at", -1).to_list(20)
