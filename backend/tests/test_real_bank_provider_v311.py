"""
V3.11 — Sprint 6: una banca vera, letta attraverso GoCardless.

    IL PROVIDER E' NUOVO. LE PROMESSE SONO LE STESSE.

Queste prove non parlano con GoCardless: parlano con un trasporto che
risponde *nella forma documentata* — gli stessi percorsi, gli stessi nomi di
campo, gli stessi stati, gli stessi codici di errore. E' un test di contratto,
e vale esattamente quanto la documentazione su cui e' stato scritto: se
l'aggregatore cambiasse forma, questi test continuerebbero a passare e la
lettura vera fallirebbe. Per questo il gate reale resta una cosa a parte, e
per questo il report dice a chiare lettere che nessuna banca e' collegata.

Quello che invece dimostrano davvero e' tutto cio' che sta *fra* la risposta
e la vita di una persona: la traduzione, il consenso, i tetti di chiamata, il
saldo che puo' mancare, la riga in sospeso che si chiude, l'IBAN che non deve
finire da nessuna parte, e il fatto che nessuna di queste strade porti a un
verbo che muove denaro.
"""

from __future__ import annotations

import ast
import json as jsonlib
import re
import uuid
from pathlib import Path

import pytest

import _loop_harness

HERE = Path(__file__).resolve().parents[1]
MONGO = "mongodb://localhost:27017"
DBNAME = "ora_test"

# Un IBAN inventato, usato solo per verificare che non compaia da nessuna
# parte. Se un giorno comparisse in un log o in una schermata, questo e' il
# valore che si vedrebbe.
IBAN = "IT60X0542811101000000123456"
SECRET_ID = "sid_soltanto_per_il_test"
SECRET_KEY = "skey_soltanto_per_il_test"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("financial_facts", "financial_observations", "bank_accounts",
                 "connector_instances", "memories", "life_objects",
                 "secret_vault", "connected_source_attempts", "agent_goals"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


# ---------------------------------------------------------------------------
# Un trasporto che risponde come risponde l'API documentata
# ---------------------------------------------------------------------------

class _Response:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class _Http:
    """
    Le risposte nella forma della documentazione, e nient'altro.

    Ogni chiamata viene annotata: meta' delle promesse di questo sprint sono
    su *quante* volte si parla con la banca, non su cosa si legge.
    """

    def __init__(self, *, fail_with=None, balances=None, status="LN"):
        self.calls = []
        self.fail_with = fail_with or {}
        self.status = status
        self.balances = balances if balances is not None else [
            {"balanceAmount": {"amount": "3250.00", "currency": "EUR"},
             "balanceType": "closingBooked", "referenceDate": "2026-09-06"},
            {"balanceAmount": {"amount": "3180.50", "currency": "EUR"},
             "balanceType": "interimAvailable",
             "lastChangeDateTime": "2026-09-07T08:00:00Z"},
        ]

    async def request(self, method, url, headers=None, json=None, params=None):
        path = url.split("/api/v2", 1)[-1]
        self.calls.append(f"{method} {path}")

        for needle, response in self.fail_with.items():
            if needle in path:
                return response

        if path == "/token/new/":
            return _Response(200, {"refresh": "refresh-token", "refresh_expires": 2592000})
        if path == "/token/refresh/":
            return _Response(200, {"access": "access-token", "access_expires": 86400})
        if path.startswith("/institutions/"):
            return _Response(200, [
                {"id": "INTESA_BCITITMM", "name": "Intesa Sanpaolo",
                 "bic": "BCITITMM", "countries": ["IT"], "logo": "https://x/l.png",
                 "transaction_total_days": "730", "max_access_valid_for_days": "90"},
                {"id": "ABANCA_CAGLESMM", "name": "Abanca",
                 "countries": ["IT"], "transaction_total_days": "90"},
            ])
        if path == "/agreements/enduser/":
            return _Response(201, {"id": "agr_1", "institution_id": "INTESA_BCITITMM",
                                   "access_scope": ["balances", "details", "transactions"]})
        if path == "/requisitions/":
            return _Response(201, {
                "id": "req_1", "status": "CR", "accounts": [],
                "link": "https://ob.gocardless.com/psd2/start/req_1/INTESA_BCITITMM",
            })
        if path.startswith("/requisitions/req_1/") and method == "DELETE":
            return _Response(200, {"summary": "Requisition deleted"})
        if path.startswith("/requisitions/req_1/"):
            return _Response(200, {
                "id": "req_1", "status": self.status,
                "accounts": ["acc_1"] if self.status == "LN" else [],
                "institution_id": "INTESA_BCITITMM",
            })
        if path == "/accounts/acc_1/":
            return _Response(200, {
                "id": "acc_1", "institution_id": "INTESA_BCITITMM",
                "status": "READY", "iban": IBAN, "owner_name": "M. Rossi",
                "created": "2026-09-01T09:00:00Z",
            })
        if path == "/accounts/acc_1/details/":
            return _Response(200, {"account": {
                "resourceId": "acc_1", "iban": IBAN, "currency": "EUR",
                "ownerName": "M. Rossi", "name": "Conto corrente",
                "product": "Conto", "cashAccountType": "CACC", "status": "enabled",
            }})
        if path == "/accounts/acc_1/balances/":
            return _Response(200, {"balances": list(self.balances)})
        if path.startswith("/accounts/acc_1/transactions/"):
            return _Response(200, {"transactions": {
                "booked": [
                    {
                        "transactionId": "tx-real-1",
                        "bookingDate": "2026-09-01", "valueDate": "2026-09-01",
                        "transactionAmount": {"amount": "-760.00", "currency": "EUR"},
                        "creditorName": "M. B.",
                        "remittanceInformationUnstructured": "BONIFICO SEPA",
                        "bankTransactionCode": "PMNT-ICDT-STDO",
                    },
                    {
                        "transactionId": "tx-real-2",
                        "bookingDate": "2026-09-02",
                        "transactionAmount": {"amount": "2050.00", "currency": "EUR"},
                        "debtorName": "ACME SRL",
                        "remittanceInformationUnstructuredArray": ["ACCREDITO", "MENSILE"],
                    },
                ],
                "pending": [
                    {
                        "bookingDate": "2026-09-07",
                        "transactionAmount": {"amount": "-22.50", "currency": "EUR"},
                        "remittanceInformationUnstructured": "PAGAMENTO IN CORSO",
                    },
                ],
            }})
        return _Response(404, {})


def _provider(http):
    from connectors.bank.gocardless_provider import GoCardlessProvider

    return GoCardlessProvider(
        secret_id=SECRET_ID, secret_key=SECRET_KEY, http=http,
    )


class _Permissions:
    class _Audit:
        async def log(self, **kw):
            return None

    def __init__(self):
        self.audit = self._Audit()


class _Vault:
    """Un vault che tiene davvero quello che gli si da', e sa revocarlo."""

    def __init__(self):
        self.kept = {}
        self.revoked = []

    async def put(self, *, user_id, purpose, payload, metadata=None):
        ref = f"sv_{uuid.uuid4().hex[:12]}"
        self.kept[ref] = dict(payload)
        return ref

    async def get(self, ref, *, user_id=None):
        if ref in self.revoked:
            raise LookupError(ref)
        return dict(self.kept.get(ref) or {})

    async def revoke(self, ref):
        self.revoked.append(ref)
        return True


async def _linked(db, uid, http=None):
    """Una persona con un conto collegato, passando dal percorso vero."""
    from connectors.bank.service import BankReadService

    http = http or _Http()
    vault = _Vault()
    svc = BankReadService(
        db=db, permissions=_Permissions(), vault=vault, provider=_provider(http),
    )
    started = await svc.begin_link(
        user_id=uid, institution_id="INTESA_BCITITMM",
        redirect_to="https://app.ora/conti-e-denaro",
    )
    done = await svc.finish_link(user_id=uid, instance_id=started["instance_id"])
    return svc, vault, http, started, done


# ---------------------------------------------------------------------------
# Il contratto
# ---------------------------------------------------------------------------

def test_the_real_provider_honours_the_read_only_contract():
    """
    §2: il provider vero rispetta il protocollo esistente, senza allargarlo.

    Tre verbi di lettura, gli stessi nomi, gli stessi parametri. Se il
    dominio avesse dovuto piegarsi per far entrare l'aggregatore, sarebbe il
    dominio a essere sbagliato.
    """
    import inspect

    from connectors.bank.gocardless_provider import GoCardlessProvider
    from connectors.bank.provider import BankProviderProtocol

    for verb in ("accounts", "transactions", "balance"):
        assert hasattr(GoCardlessProvider, verb), f"manca il verbo «{verb}»"
        ours = inspect.signature(getattr(GoCardlessProvider, verb))
        theirs = inspect.signature(getattr(BankProviderProtocol, verb))
        assert set(ours.parameters) >= set(theirs.parameters), (
            f"«{verb}» non accetta quello che il protocollo promette"
        )


def test_the_application_token_is_taken_once_and_reused():
    """
    §1: due gradini, e non uno per chiamata.

    I segreti diventano un refresh, il refresh diventa un access che dura un
    giorno. Chiederne uno nuovo a ogni lettura funzionerebbe, e sarebbe uno
    spreco che si paga in quota — la stessa quota che serve per leggere i
    conti di qualcuno.
    """
    async def body():
        http = _Http()
        provider = _provider(http)
        await provider.institutions(country="IT")
        await provider.institutions(country="IT")

        assert http.calls.count("POST /token/new/") == 1
        assert http.calls.count("POST /token/refresh/") == 1
        assert http.calls.count("GET /institutions/") == 2

    _run(body())


def test_the_requisition_states_become_words_a_person_can_read():
    """
    §5: «UA» non e' una cosa che si mostra a qualcuno.

    Gli stati dell'aggregatore sono otto sigle. Quelli di una persona sono
    cinque frasi, e la traduzione avviene in un posto solo.
    """
    from connectors.bank.link import (
        CONNECTED, CONNECTING, IN_WORDS, NEEDS_CONSENT, NOT_CONNECTED,
        WHILE_LINKING,
    )

    assert WHILE_LINKING["UA"] == CONNECTING
    assert WHILE_LINKING["LN"] == CONNECTED
    assert WHILE_LINKING["EX"] == NEEDS_CONSENT
    assert WHILE_LINKING["RJ"] == NOT_CONNECTED
    for state, sentence in IN_WORDS.items():
        assert sentence and sentence[0].isupper(), state
        for jargon in ("requisition", "psd2", "token", "http", "401", "429"):
            assert jargon not in sentence.lower(), (
                f"«{sentence}» parla la lingua dell'API"
            )


def test_a_person_never_types_their_bank_credentials_into_ora():
    """
    §4: il collegamento porta al percorso ufficiale, e non chiede niente.

    Quello che ORA restituisce e' un indirizzo. Se chiedesse utente e
    password sarebbe phishing con una buona intenzione — che resta phishing,
    e che nessun consenso dell'utente rende accettabile.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            _, _, http, started, done = await _linked(db, uid)
            assert started["vai_qui"].startswith("https://")
            assert "gocardless.com" in started["vai_qui"]
            assert done["stato"] == "collegato"
            # Nessuna chiamata dell'API accetta credenziali della persona.
            assert not any("password" in c.lower() for c in http.calls)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# La traduzione
# ---------------------------------------------------------------------------

def test_an_account_arrives_with_its_currency_and_without_its_iban():
    """§6: il conto si riconosce dalle ultime quattro cifre, non dall'IBAN."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid)
            row = await db.bank_accounts.find_one({"owner_id": uid}, {"_id": 0})
            assert row["currency"] == "EUR"
            assert row["display_name"]
            assert row.get("masked_number") == "•••• 3456"
            assert IBAN not in jsonlib.dumps(row, default=str), (
                "l'IBAN intero e' finito nel database"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_balance_keeps_booked_and_available_apart():
    """
    §12: il disponibile e il contabile non sono lo stesso numero.

    Il primo tiene conto di quello che e' gia' impegnato, ed e' quello che
    una persona vede in banca. Mostrarne uno per l'altro e' un errore da
    qualche decina di euro, ogni volta, senza che nessuno se ne accorga.
    """
    async def body():
        http = _Http()
        got = await _provider(http).balance(access_token="req_1", account_ref="acc_1")
        assert got["current"] == 3250.00
        assert got["available"] == 3180.50
        assert got["currency"] == "EUR"
        assert got["at"].startswith("2026-09-07")

    _run(body())


def test_a_bank_that_gives_no_balance_leaves_it_unknown():
    """§12 + §7: SCONOSCIUTO NON E' ZERO, anche con un provider vero."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            http = _Http(balances=[])
            await _linked(db, uid, http)
            row = await db.bank_accounts.find_one({"owner_id": uid}, {"_id": 0})
            assert "current_balance" not in row
            assert "available_balance" not in row

            from financial.overview import money_overview

            shown = (await money_overview(db, uid))["conti"][0]
            assert shown["saldo_noto"] is False
            assert "non comunicato" in shown["saldo"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_real_balance_is_shown_with_when_it_was_read():
    """
    §12: un saldo senza un'ora sopra e' una cifra che si spaccia per adesso.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid)
            from financial.overview import money_overview

            shown = (await money_overview(db, uid))["conti"][0]
            assert shown["saldo_noto"] is True
            assert shown["saldo_tipo"] == "disponibile"
            assert shown["aggiornato"], "non dice quando l'ha letto"
            assert "non so quando" not in shown["aggiornato"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_booked_movement_keeps_what_the_bank_wrote_and_adds_nothing():
    """
    §7: IL CODICE NORMALIZZA. Non conclude.

    Importo, segno, data, descrizione, controparte. Il codice di schema
    bancario viaggia fra le prove, e non diventa il nome di niente.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid)
            row = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "tx-real-1"}, {"_id": 0},
            )
            assert row["amount"] == -760.00
            assert row["direction"] == "outgoing"
            assert row["raw_description"] == "BONIFICO SEPA"
            assert row["counterparty"] == "M. B."
            assert row["booked_at"].startswith("2026-09-01")
            assert row["provenance"]["provider_hint"] == "PMNT-ICDT-STDO"
            # E niente che assomigli a una categoria nostra.
            for forbidden in ("category", "interpreted_kind", "label"):
                assert forbidden not in row, f"l'osservazione porta «{forbidden}»"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_incoming_movement_reads_the_other_side_of_the_transfer():
    """§7: la controparte e' quella che la banca nomina, dal lato giusto."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid)
            row = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "tx-real-2"}, {"_id": 0},
            )
            assert row["direction"] == "incoming"
            assert row["counterparty"] == "ACME SRL"
            assert "ACCREDITO" in row["raw_description"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_pending_movement_without_an_id_still_gets_a_stable_one():
    """
    §7: le righe in sospeso spesso non hanno identificativo.

    Senza un riferimento stabile, la stessa riga letta due volte sarebbe due
    caffe'. Il riferimento si calcola dai campi che non cambiano quando la
    riga si consolida.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            svc, _, _, _, _ = await _linked(db, uid)
            rows = await db.financial_observations.find(
                {"owner_id": uid, "provenance.status": "pending"}, {"_id": 0},
            ).to_list(10)
            assert len(rows) == 1
            first = rows[0]["transaction_ref"]
            assert first and first not in ("", "None")

            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1},
            )
            await svc.sync(user_id=uid, instance_id=instance["id"])
            again = await db.financial_observations.find(
                {"owner_id": uid, "provenance.status": "pending"}, {"_id": 0},
            ).to_list(10)
            assert len(again) == 1, "la riga in sospeso e' stata contata due volte"
            assert again[0]["transaction_ref"] == first
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_reading_the_same_real_statement_twice_writes_nothing_new():
    """§16-E: la seconda lettura non raddoppia niente."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            svc, _, _, _, _ = await _linked(db, uid)
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1},
            )
            before = await db.financial_observations.count_documents({"owner_id": uid})
            again = await svc.sync(user_id=uid, instance_id=instance["id"])
            after = await db.financial_observations.count_documents({"owner_id": uid})
            assert before == after == 3
            assert again["written"] == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Il consenso, i tetti, lo scollegamento
# ---------------------------------------------------------------------------

def test_an_expired_consent_is_said_as_a_thing_to_redo():
    """
    §13: il permesso scade ogni tre mesi, per legge.

    Non e' un guasto e non va detto come tale: e' una cosa da rifare, che
    accadra' per sempre. E quello che ORA aveva capito non si perde.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            svc, _, _, _, _ = await _linked(db, uid)
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1},
            )
            before = await db.financial_observations.count_documents({"owner_id": uid})

            svc.provider = _provider(_Http(
                fail_with={"/requisitions/": _Response(401, {"detail": "expired"})},
            ))
            out = await svc.sync(user_id=uid, instance_id=instance["id"])

            assert out["ok"] is False and out["reason"] == "consent_expired"
            assert "autorizzi di nuovo" in out["human"]
            row = await db.connector_instances.find_one({"id": instance["id"]}, {"_id": 0})
            assert row["reauthorization_required"] is True

            state = await svc.state(user_id=uid)
            assert state["stato"] == "serve_autorizzare_di_nuovo"
            assert state["cosa_posso_fare"] == "Ricollega"
            # Le osservazioni restano: la fonte e' ferma, non cancellata.
            assert await db.financial_observations.count_documents(
                {"owner_id": uid}) == before
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_rate_limit_moves_the_appointment_instead_of_breaking_the_source():
    """
    §15: il tetto della banca vale piu' della nostra cadenza.

    Alcune banche concedono quattro letture al giorno per conto. Insistere
    non fa arrivare i dati: fa arrivare altri 429. E marcare la sorgente come
    «degradata» direbbe alla persona che qualcosa e' rotto, e non e' rotto
    niente.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            svc, _, _, _, _ = await _linked(db, uid)
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1},
            )
            svc.provider = _provider(_Http(fail_with={
                "/transactions/": _Response(
                    429, {"detail": "rate limit"},
                    headers={"HTTP_X_RATELIMIT_ACCOUNT_SUCCESS_RESET": "7200"},
                ),
            }))
            out = await svc.sync(user_id=uid, instance_id=instance["id"])

            assert out["ok"] is False and out["reason"] == "rate_limited"
            assert out["next_allowed_at"]

            row = await db.connector_instances.find_one({"id": instance["id"]}, {"_id": 0})
            # Lo stato non peggiora: non c'e' niente da riparare.
            assert row["status"] == "connected"
            assert row["reauthorization_required"] is False
            assert row["next_allowed_at"] == out["next_allowed_at"]

            queued = await db.connected_source_attempts.find_one(
                {"owner_id": uid, "source_id": instance["id"]}, {"_id": 0},
            )
            assert queued["not_before"] == out["next_allowed_at"]

            from connected.polling import due

            waiting = await due(db, uid)
            assert instance["id"] not in [s.id for s in waiting], (
                "la coda ripasserebbe comunque, contro il tetto della banca"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_provider_hold_survives_the_next_scheduling():
    """§15: una cadenza nostra non puo' anticipare un limite del provider."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import hold_source, schedule_next

            far = "2099-01-01T00:00:00+00:00"
            await hold_source(db, uid, "src_1", until=far)
            when = await schedule_next(
                db, uid, "src_1", "bank", failed=False,
            )
            assert when == far, "il backoff ha scavalcato il tetto della banca"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_disconnecting_closes_the_consent_and_keeps_what_was_understood():
    """
    §14: scollegare toglie il permesso, non la memoria.

    Che l'affitto sia 760 al mese resta vero dopo aver scollegato la banca:
    e' una cosa che ORA ha capito, non un pezzo di dato in prestito. Perde
    pero' il diritto di essere data per fresca.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            svc, vault, http, _, _ = await _linked(db, uid)
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1, "secret_reference": 1},
            )

            from financial.models import FinancialFact, Money, Provenance
            from financial.store import FinancialStore

            await FinancialStore(db).remember(FinancialFact(
                owner_id=uid, kind="commitment", what="una cosa capita",
                money=Money(amount=760, currency="EUR"), direction="outgoing",
                cadence="recurring",
                provenance=[Provenance(source="bank",
                                       how_directly="l'ho visto sul tuo conto")],
                source_refs=["tx-real-1"],
            ))

            out = await svc.disconnect(user_id=uid, instance_id=instance["id"])
            assert out["ok"] is True
            assert "resta" in out["in_parole"]

            # Il consenso e' chiuso dal lato dell'aggregatore.
            assert any("DELETE /requisitions/" in c for c in http.calls)
            # E il riferimento nel vault non e' piu' usabile.
            assert instance["secret_reference"] in vault.revoked

            row = await db.connector_instances.find_one({"id": instance["id"]}, {"_id": 0})
            assert row["status"] == "revoked"
            assert not row.get("secret_reference")

            # La conoscenza c'e' ancora, e dice di non essere piu' aggiornata.
            fact = await db.financial_facts.find_one({"owner_id": uid}, {"_id": 0})
            assert fact is not None, "scollegare ha cancellato quello che ORA sapeva"
            assert fact.get("source_disconnected_at")
            account = await db.bank_accounts.find_one({"owner_id": uid}, {"_id": 0})
            assert account.get("source_disconnected_at")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_disconnected_source_is_not_read_again():
    """§14: dopo lo scollegamento non si legge piu' niente."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            svc, _, _, _, _ = await _linked(db, uid)
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1},
            )
            await svc.disconnect(user_id=uid, instance_id=instance["id"])

            from connected.polling import due

            assert instance["id"] not in [s.id for s in await due(db, uid)]
            state = await svc.state(user_id=uid)
            assert state["stato"] == "non_collegato"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_disconnect_route_asks_before_doing_it():
    """§14: si chiede conferma, perche' il consenso non si riapre da solo."""
    source = (HERE / "routers" / "financial.py").read_text(encoding="utf-8")
    assert "confirmation_required" in source
    assert "confirm: bool = False" in source


# ---------------------------------------------------------------------------
# I segreti
# ---------------------------------------------------------------------------

def test_no_secret_is_ever_written_down():
    """
    §3: le credenziali stanno nell'ambiente, e da nessun'altra parte.

    Non nel documento dell'istanza, non nei metadati, non nelle osservazioni,
    non nei conti. Il riferimento del consenso sta nel vault, cifrato, e nel
    resto del database c'e' solo il puntatore.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid)
            for coll in ("connector_instances", "bank_accounts",
                         "financial_observations", "financial_facts"):
                rows = await db[coll].find(
                    {"$or": [{"user_id": uid}, {"owner_id": uid}]}, {"_id": 0},
                ).to_list(50)
                blob = jsonlib.dumps(rows, default=str)
                for secret in (SECRET_ID, SECRET_KEY, "refresh-token", "access-token"):
                    assert secret not in blob, f"«{secret}» e' finito in {coll}"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_iban_never_reaches_a_screen():
    """§6: dalla schermata escono quattro cifre, mai il numero intero."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid)
            from financial.overview import money_overview

            blob = jsonlib.dumps(await money_overview(db, uid), default=str)
            assert IBAN not in blob
            assert IBAN[-6:] not in blob, "sei cifre sono piu' di quattro"
            assert "3456" in blob, "senza le ultime cifre due conti si confondono"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_secret_is_read_from_anywhere_but_the_environment():
    """§3: nel codice non c'e' nessuna credenziale, e non c'e' un ripiego."""
    source = (HERE / "connectors" / "bank" / "gocardless_provider.py").read_text(
        encoding="utf-8")

    # Nessun valore scritto a mano finisce in qualcosa che si chiama segreto,
    # chiave o token: quei nomi possono essere riempiti solo dall'ambiente o
    # da chi costruisce l'oggetto.
    offenders = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = " ".join(
            ast.unparse(t) for t in targets
        ).lower()
        if not any(w in names for w in ("secret", "key", "token", "password")):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
            offenders.append(f"{names} = «{value.value[:8]}…»")
    assert not offenders, f"una credenziale e' scritta nel codice: {offenders}"

    assert 'os.environ.get("GOCARDLESS_SECRET_ID"' in source
    assert 'os.environ.get("GOCARDLESS_SECRET_KEY"' in source


# ---------------------------------------------------------------------------
# Quante volte si parla con il giudizio
# ---------------------------------------------------------------------------

def _answer(**over):
    base = {
        "interpreted_kind": "unclear", "certainty": "low",
        "pattern_status": "recurring", "should_persist": False,
        "likely_label": "", "missing_information": [], "reason": "",
        "recurring_likelihood": "medium", "should_ask_user": True,
        "linked_situations": [],
    }
    base.update(over)
    return base


def test_six_identical_transfers_are_one_question_and_not_six(monkeypatch):
    """
    §9: SEI BONIFICI UGUALI SONO UNA DOMANDA.

    Una chiamata per riga sarebbe un costo che cresce con la vita di chi usa
    il prodotto — qualche centinaio di chiamate per una persona sola, e
    altrettante la volta dopo.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            from financial import reasoning
            from financial.batching import read_what_is_new
            from financial.observation import BankObservation, ObservationStore

            calls = {"n": 0}

            async def counted(*a, **kw):
                calls["n"] += 1
                return _answer()

            monkeypatch.setattr(reasoning, "read_a_movement", counted)

            store = ObservationStore(db)
            for month in range(6):
                await store.record(BankObservation(
                    owner_id=uid, account_ref="acc_1",
                    transaction_ref=f"tx_group_{month}",
                    booked_at=f"2026-0{month + 1}-05T10:00:00+00:00",
                    amount=-14.99, currency="EUR", direction="outgoing",
                    raw_description="ADDEBITO SEPA 4411",
                ))

            out = await read_what_is_new(db, uid)
            assert out["chiamate"] == 1, f"{out['chiamate']} chiamate per un gruppo solo"
            assert calls["n"] == 1
            assert out["gruppi"] == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_single_everyday_movement_asks_nobody_anything(monkeypatch):
    """
    §9 + §17: un caffe' isolato non ha una spiegazione da trovare.

    Non si ripete, non c'e' niente intorno che ne parli, non appartiene a
    niente che stia succedendo. Chiedere al giudizio cosa sia significa
    pagare per sentirsi dire che e' un caffe'.

    E il filtro non guarda l'importo: se ci fosse una situazione aperta o
    un'email vicina, la stessa riga passerebbe.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            from financial import reasoning
            from financial.batching import read_what_is_new
            from financial.observation import BankObservation, ObservationStore

            calls = {"n": 0}

            async def counted(*a, **kw):
                calls["n"] += 1
                return _answer()

            monkeypatch.setattr(reasoning, "read_a_movement", counted)

            await ObservationStore(db).record(BankObservation(
                owner_id=uid, account_ref="acc_1", transaction_ref="tx_solo",
                booked_at="2026-09-06T10:00:00+00:00",
                amount=-12.00, currency="EUR", direction="outgoing",
                raw_description="PAGAMENTO POS",
            ))

            out = await read_what_is_new(db, uid)
            assert calls["n"] == 0, "ha chiesto al giudizio cos'e' un caffe'"
            assert out["chiamate"] == 0
            assert out["rimandati"] == 1

            # La riga resta: e' successa, e il registro la tiene.
            assert await db.financial_observations.count_documents(
                {"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_lone_movement_is_looked_at_when_something_is_going_on(monkeypatch):
    """
    §9: il cancello guarda se c'e' materiale, non quanto e' grosso l'importo.

    Dodici euro e quattromila passano dalla stessa porta. Quello che cambia
    e' se c'e' una situazione aperta a cui una spesa possa appartenere.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            from financial import reasoning
            from financial.batching import read_what_is_new
            from financial.observation import BankObservation, ObservationStore

            calls = {"n": 0}

            async def counted(*a, **kw):
                calls["n"] += 1
                return _answer(interpreted_kind="noise", reason="quotidiano")

            monkeypatch.setattr(reasoning, "read_a_movement", counted)

            await db.life_objects.insert_one({
                "id": "lo_test", "user_id": uid, "title": "Una cosa in corso",
                "type": "project", "status": "active",
            })
            await ObservationStore(db).record(BankObservation(
                owner_id=uid, account_ref="acc_1", transaction_ref="tx_solo_2",
                booked_at="2026-09-06T10:00:00+00:00",
                amount=-12.00, currency="EUR", direction="outgoing",
                raw_description="PAGAMENTO POS",
            ))

            out = await read_what_is_new(db, uid)
            assert calls["n"] == 1
            assert out["rimandati"] == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_group_already_looked_at_is_not_paid_for_twice(monkeypatch):
    """§9: il secondo passaggio non ricompra le stesse risposte."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            from financial import reasoning
            from financial.batching import read_what_is_new
            from financial.observation import BankObservation, ObservationStore

            calls = {"n": 0}

            async def counted(*a, **kw):
                calls["n"] += 1
                return _answer()

            monkeypatch.setattr(reasoning, "read_a_movement", counted)

            store = ObservationStore(db)
            for month in range(3):
                await store.record(BankObservation(
                    owner_id=uid, account_ref="acc_1",
                    transaction_ref=f"tx_again_{month}",
                    booked_at=f"2026-0{month + 1}-05T10:00:00+00:00",
                    amount=-9.99, currency="EUR", direction="outgoing",
                    raw_description="ADDEBITO SEPA 9",
                ))

            await read_what_is_new(db, uid)
            first = calls["n"]
            await read_what_is_new(db, uid)
            assert calls["n"] == first, "ha richiesto quello che sapeva gia'"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Cosa resta separato da cosa
# ---------------------------------------------------------------------------

def test_a_real_observation_is_not_knowledge_until_governance_says_so():
    """
    §8: leggere non e' sapere.

    Tre movimenti letti da una banca vera non producono nessuna memoria da
    soli. Fra l'estratto conto e il modello della vita ci sono un giudizio e
    una governance, e nessuno dei due si salta.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid)
            assert await db.financial_observations.count_documents(
                {"owner_id": uid}) == 3
            assert await db.financial_facts.count_documents({"owner_id": uid}) == 0
            assert await db.memories.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_providers_code_never_becomes_the_name_of_anything():
    """§7: «PMNT-ICDT-STDO» e' un indizio, non un significato."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid)
            from financial.overview import money_overview

            blob = jsonlib.dumps(await money_overview(db, uid), default=str)
            assert "PMNT" not in blob, "il codice della banca e' finito in schermata"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_screen_says_what_it_knows_and_what_it_only_saw():
    """
    §10: SO · PENSO · HO VISTO, e non tutto «penso».

    Un addebito che torna ogni mese e che nessuno ha capito non e'
    un'interpretazione debole: e' un'altra cosa, e va detta come tale.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observation import BankObservation, ObservationStore
            from financial.overview import money_overview

            store = ObservationStore(db)
            for month in range(4):
                await store.record(BankObservation(
                    owner_id=uid, account_ref="acc_1",
                    transaction_ref=f"tx_seen_{month}",
                    booked_at=f"2026-0{month + 1}-12T10:00:00+00:00",
                    amount=-14.99, currency="EUR", direction="outgoing",
                    raw_description="ADDEBITO SEPA 4411",
                ))

            rows = (await money_overview(db, uid))["cosa_ho_capito"]
            seen = [r for r in rows if r.get("stato") == "HO VISTO"]
            assert seen, "un addebito che torna quattro volte non compare"
            assert "14,99" in seen[0]["cosa"]
            # Senza una banca collegata la frase e' al passato: la sostanza
            # e' la stessa — non si sa che cosa sia — e il tempo verbale lo
            # tiene fermo la suite dello scollegamento.
            assert "non so" in seen[0]["non_so"].lower()
            assert "cosa sia" in seen[0]["non_so"].lower()
            assert "4 volte" in seen[0]["perche"]
            # E soprattutto: nessun nome inventato.
            for invented in ("abbonamento", "bolletta", "assicurazione"):
                assert invented not in jsonlib.dumps(seen, ensure_ascii=False).lower()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_ora_knows_says_how_it_knows_it():
    """§10: «confermato da te» e «compare sul conto» non sono la stessa cosa."""
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            from financial.knowledge import what_ora_knows
            from financial.models import FinancialFact, Money, Provenance
            from financial.store import FinancialStore

            await FinancialStore(db).remember(FinancialFact(
                owner_id=uid, kind="commitment", what="una spesa che torna",
                money=Money(amount=760, currency="EUR"), direction="outgoing",
                cadence="recurring",
                provenance=[Provenance(source="bank",
                                       how_directly="l'ho visto sul tuo conto")],
                source_refs=["tx-real-1"],
            ))
            said = await what_ora_knows(db, uid)
            assert said["ho_letto"][0]["come_lo_so"].startswith(
                "compare regolarmente sul conto"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Le guardie strutturali
# ---------------------------------------------------------------------------

def _code_only(path: Path) -> str:
    """Il codice senza le sue spiegazioni — come nelle suite precedenti."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        body = getattr(node, "body", [])
        if (
            body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)
    return ast.unparse(tree)


def test_the_real_provider_has_no_verb_that_moves_money():
    """
    §2: nemmeno con un aggregatore vero.

    GoCardless ha anche un'API di pagamenti: e' un altro prodotto, un altro
    consenso, un altro dominio. Un attuatore che non esiste non puo' essere
    chiamato per sbaglio.
    """
    for name in ("gocardless_provider.py", "link.py", "provider.py",
                 "service.py", "__init__.py"):
        source = _code_only(HERE / "connectors" / "bank" / name).lower()
        for forbidden in ("def transfer", "def pay", "def initiate",
                          "def cancel_direct_debit", "def block_card",
                          "payment_initiation", "def open_account",
                          "def create_payment", "mail.send"):
            assert forbidden not in source, (
                f"connectors/bank/{name} contiene «{forbidden}»"
            )


def test_no_payment_endpoint_is_ever_named():
    """
    §2: e nessun percorso dell'API dei pagamenti compare da nessuna parte.

    Non basta non avere il verbo: non deve esserci nemmeno l'indirizzo. Un
    percorso scritto in una costante e' una riga di distanza dall'essere
    chiamato.
    """
    offenders = []
    for path in (HERE / "connectors" / "bank").glob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for forbidden in ("/billing-requests", "/payments", "/mandates",
                          "/payouts", "/refunds", "/subscriptions",
                          "api.gocardless.com"):
            if forbidden in source:
                offenders.append(f"{path.name}: «{forbidden}»")
    assert not offenders, f"un percorso dei pagamenti compare qui: {offenders}"


def test_the_bank_still_asks_only_to_read():
    """§2: gli scope chiesti all'aggregatore sono tre, e sono di lettura."""
    from connectors.bank.gocardless_provider import ACCESS_SCOPE

    assert set(ACCESS_SCOPE) == {"balances", "details", "transactions"}


def test_there_is_still_no_sixth_tab():
    """§10: «Conti e denaro» sta dentro Vita, e non diventa una sezione."""
    tabs = HERE.parent / "frontend" / "app" / "(tabs)"
    names = {p.stem.lower() for p in tabs.glob("*.tsx")} if tabs.exists() else set()
    for forbidden in ("conti", "denaro", "banca", "finanze", "wallet", "banking"):
        assert forbidden not in names, f"c'e' una scheda «{forbidden}»"


def test_the_same_thing_is_never_shown_twice_with_two_certainties():
    """
    §10: LA STESSA COSA NON PUO' COMPARIRE DUE VOLTE CON DUE GRADI.

    Trovato sul dataset vero, non da un test: un fatto nasce dal movimento
    piu' recente e porta il riferimento di quello solo. Gli altri cinque
    bonifici identici restavano orfani, e la schermata mostrava «HO VISTO —
    un pagamento di €760, sei volte» subito sotto «SO — Affitto €760». Due
    gradi di certezza sulla stessa cosa, uno accanto all'altro: la
    confusione esatta che questa schermata esiste per togliere.
    """
    async def body():
        client, db = await _db()
        uid = f"gc_{uuid.uuid4().hex[:8]}"
        try:
            from financial.models import FinancialFact, Money, Provenance
            from financial.observation import BankObservation, ObservationStore
            from financial.overview import money_overview
            from financial.store import FinancialStore

            store = ObservationStore(db)
            for month in range(6):
                await store.record(BankObservation(
                    owner_id=uid, account_ref="acc_1",
                    transaction_ref=f"tx_pair_{month}",
                    booked_at=f"2026-0{month + 1}-05T10:00:00+00:00",
                    amount=-760.00, currency="EUR", direction="outgoing",
                    raw_description="BONIFICO SEPA", counterparty="M. B.",
                ))

            # Il fatto nasce dall'ultimo movimento, e porta solo il suo.
            await FinancialStore(db).remember(FinancialFact(
                owner_id=uid, kind="commitment", what="una cosa che torna",
                money=Money(amount=760, currency="EUR"), direction="outgoing",
                cadence="recurring",
                provenance=[Provenance(source="bank",
                                       how_directly="l'ho visto sul tuo conto")],
                source_refs=["tx_pair_5"],
            ))

            rows = (await money_overview(db, uid))["cosa_ho_capito"]
            seen = [r for r in rows if r.get("stato") == "HO VISTO"]
            assert not seen, f"la stessa cosa compare anche come «ho visto»: {seen}"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
