"""
V3.11 — Sprint 6: una banca vera, letta attraverso Enable Banking.

    IL PROVIDER E' NUOVO. LE PROMESSE SONO LE STESSE.

Queste prove non parlano con l'aggregatore: parlano con un trasporto che
risponde nella forma documentata — gli stessi percorsi, gli stessi nomi di
campo, gli stessi codici. Sono prove di contratto, e valgono quanto la
documentazione su cui sono scritte; il collegamento vero e' un'altra cosa e
sta nel gate, non qui.

Quello che invece dimostrano davvero e' tutto cio' che sta *fra* la risposta
e la vita di una persona: la firma, il consenso, lo scambio del codice, la
traduzione degli importi senza segno, la continuazione, la chiave privata che
non deve finire da nessuna parte, e il fatto che nessuna di queste strade
porti a un verbo che muove denaro.
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
APP_ID = "11111111-2222-3333-4444-555555555555"
CALLBACK = "http://127.0.0.1:8000/api/connectors/bank/enablebanking/callback"

# La chiave di prova, generata una volta per tutta la sessione e mai scritta
# accanto al codice: e' un file temporaneo, e serve solo a poter verificare
# che una firma sia una firma.
_KEY_FILE: list = []


def _key_path(tmp_path_factory) -> str:
    if _KEY_FILE:
        return _KEY_FILE[0]
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path_factory.mktemp("eb") / "prova.pem"
    path.write_bytes(pem)
    _KEY_FILE.append(str(path))
    return str(path)


@pytest.fixture(scope="session")
def key_path(tmp_path_factory):
    return _key_path(tmp_path_factory)


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("financial_facts", "financial_observations", "bank_accounts",
                 "connector_instances", "memories", "life_objects",
                 "connected_source_attempts", "bank_link_states"):
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


def _movements(page: int):
    """Due pagine, per poter dimostrare che la continuazione viene seguita."""
    if page == 1:
        return {
            "transactions": [
                {
                    "entry_reference": "eb-tx-1",
                    "booking_date": "2026-09-01", "value_date": "2026-09-02",
                    "transaction_amount": {"amount": "760.00", "currency": "EUR"},
                    "credit_debit_indicator": "DBIT",
                    "status": "BOOK",
                    "creditor": {"name": "M. B."},
                    "remittance_information": ["BONIFICO SEPA", "settembre"],
                    "bank_transaction_code": {"code": "PMNT", "sub_code": "ICDT"},
                },
                {
                    "entry_reference": "eb-tx-2",
                    "booking_date": "2026-09-02",
                    "transaction_amount": {"amount": "2050.00", "currency": "EUR"},
                    "credit_debit_indicator": "CRDT",
                    "status": "BOOK",
                    "debtor": {"name": "ACME SRL"},
                    "remittance_information": ["ACCREDITO MENSILE"],
                },
            ],
            "continuation_key": "pagina2",
        }
    return {
        "transactions": [
            {
                "booking_date": "2026-09-07",
                "transaction_amount": {"amount": "22.50", "currency": "EUR"},
                "credit_debit_indicator": "DBIT",
                "status": "PDNG",
                "remittance_information": ["PAGAMENTO IN CORSO"],
            },
        ],
    }


class _Http:
    """Le risposte nella forma della documentazione, e nient'altro."""

    def __init__(self, *, fail_with=None, balances=None, settle_pending=False):
        self.calls = []
        self.bodies = []
        self.fail_with = fail_with or {}
        self.settle_pending = settle_pending
        self.balances = balances if balances is not None else [
            {"name": "Booked", "balance_amount": {"amount": "3250.00", "currency": "EUR"},
             "balance_type": "CLBD", "reference_date": "2026-09-06"},
            {"name": "Available", "balance_amount": {"amount": "3180.50", "currency": "EUR"},
             "balance_type": "ITAV", "last_change_date_time": "2026-09-07T08:00:00Z"},
        ]

    async def request(self, method, url, headers=None, json=None, params=None):
        path = url.split("enablebanking.com", 1)[-1]
        self.calls.append(f"{method} {path}")
        if json:
            self.bodies.append(json)
        # La firma c'e', ed e' un JWT: non si controlla il contenuto qui, ma
        # che qualcuno stia davvero autenticando la chiamata.
        assert (headers or {}).get("Authorization", "").startswith("Bearer ey")

        for needle, response in self.fail_with.items():
            if needle in path:
                return response

        if path == "/application":
            return _Response(200, {
                "name": "ORA LOCAL", "environment": "SANDBOX", "active": True,
                "countries": ["IT"], "redirect_urls": [CALLBACK],
            })
        if path.startswith("/aspsps"):
            return _Response(200, {"aspsps": [
                {"name": "Mock ASPSP", "country": "IT",
                 "logo": "https://x/l.png", "psu_types": ["personal"],
                 "maximum_consent_validity": 15552000},
                {"name": "UniCredit", "country": "IT", "psu_types": ["personal"]},
            ]})
        if path == "/auth":
            return _Response(200, {
                "url": "https://tilisy-sandbox.enablebanking.com/ais/start?sessionid=s1",
                "authorization_id": "auth-1",
            })
        if path == "/sessions":
            return _Response(200, {
                "session_id": "sess-1",
                "accounts": [{
                    "uid": "acc-uid-1", "currency": "EUR",
                    "account_id": {"iban": IBAN},
                    "name": "M. Rossi", "product": "Conto corrente",
                    "cash_account_type": "CACC", "usage": "PRIV",
                    "identification_hash": "hash-1",
                }],
                "aspsp": {"name": "Mock ASPSP", "country": "IT"},
                "access": {"valid_until": "2026-12-07T00:00:00+00:00"},
                "psu_type": "personal",
            })
        if path.startswith("/sessions/") and method == "DELETE":
            return _Response(200, {"status": "REVOKED"})
        if path.startswith("/sessions/"):
            return _Response(200, {
                "session_id": "sess-1", "status": "AUTHORIZED",
                "aspsp": {"name": "Mock ASPSP", "country": "IT"},
                "accounts": [{
                    "uid": "acc-uid-1", "currency": "EUR",
                    "account_id": {"iban": IBAN},
                    "product": "Conto corrente", "cash_account_type": "CACC",
                    "identification_hash": "hash-1",
                }],
            })
        if path.endswith("/balances"):
            return _Response(200, {"balances": list(self.balances)})
        if "/transactions" in path:
            page = 2 if (params or {}).get("continuation_key") else 1
            got = _movements(page)
            if page == 2 and self.settle_pending:
                got = jsonlib.loads(jsonlib.dumps(got))
                got["transactions"][0]["status"] = "BOOK"
                got["transactions"][0]["booking_date"] = "2026-09-08"
            return _Response(200, got)
        return _Response(404, {})


def _provider(http, key_path, **over):
    from connectors.bank.enablebanking_provider import EnableBankingProvider

    return EnableBankingProvider(
        application_id=over.get("application_id", APP_ID),
        private_key_path=key_path,
        redirect_uri=CALLBACK,
        environment="sandbox",
        http=http,
    )


class _Permissions:
    class _Audit:
        async def log(self, **kw):
            return None

    def __init__(self):
        self.audit = self._Audit()


class _Vault:
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


async def _service(db, key_path, http=None):
    from connectors.bank.service import BankReadService

    http = http or _Http()
    vault = _Vault()
    svc = BankReadService(
        db=db, permissions=_Permissions(), vault=vault,
        provider=_provider(http, key_path),
    )
    return svc, vault, http


async def _linked(db, uid, key_path, http=None):
    """Una persona collegata, passando dal percorso vero: auth, codice, sessione."""
    from connectors.bank.link import complete_with_code

    svc, vault, http = await _service(db, key_path, http)
    started = await svc.begin_link(
        user_id=uid, institution_id="IT:Mock ASPSP",
        redirect_to="http://localhost:8081/conti-e-denaro",
    )
    state = (await db.bank_link_states.find_one(
        {"user_id": uid}, {"_id": 0, "state": 1},
    ))["state"]
    done = await complete_with_code(svc, state=state, code="il-codice")
    return svc, vault, http, started, done


# ---------------------------------------------------------------------------
# La firma
# ---------------------------------------------------------------------------

def test_the_call_is_signed_with_the_private_key_and_the_application_id(key_path):
    """
    §2: non c'e' un segreto condiviso — c'e' una firma.

    RS256, `kid` uguale all'id dell'applicazione, e le tre affermazioni che
    l'aggregatore si aspetta. Una firma sbagliata non e' un dettaglio: e'
    l'unica cosa che dice chi sta chiedendo.
    """
    import jwt as pyjwt

    provider = _provider(_Http(), key_path)
    token = provider._sign()

    head = pyjwt.get_unverified_header(token)
    assert head["alg"] == "RS256"
    assert head["kid"] == APP_ID, "il kid non e' l'id dell'applicazione"

    body = pyjwt.decode(token, options={"verify_signature": False},
                        audience="api.enablebanking.com")
    assert body["iss"] == "enablebanking.com"
    assert body["aud"] == "api.enablebanking.com"
    assert body["exp"] - body["iat"] == 3600


def test_the_signature_is_reused_until_it_is_about_to_expire(key_path):
    """§2: firmare a ogni chiamata funzionerebbe, e sarebbe uno spreco."""
    provider = _provider(_Http(), key_path)
    first = provider._bearer()
    assert provider._bearer() == first


def test_without_a_key_the_provider_does_not_pretend(key_path):
    """
    §2/§17: una configurazione mancante si dice, non si aggira.

    Un provider costruito a meta' fallirebbe piu' tardi, dentro una lettura,
    e la persona vedrebbe «la banca non risponde» — che sarebbe falso.
    """
    from connectors.bank.enablebanking_provider import (
        EnableBankingNotConfigured, EnableBankingProvider,
    )

    with pytest.raises(EnableBankingNotConfigured):
        EnableBankingProvider(application_id="", private_key_path=key_path)
    with pytest.raises(EnableBankingNotConfigured):
        EnableBankingProvider(
            application_id=APP_ID,
            private_key_path=str(Path(key_path).parent / "non-esiste.pem"),
        )


def test_the_private_key_is_never_kept_anywhere(key_path):
    """
    §14: LA CHIAVE NON ESCE DALLA FUNZIONE CHE FIRMA.

    Non in un attributo, non in un `repr`, non in un messaggio d'errore.
    Quello che l'oggetto conserva e' un percorso; il contenuto si legge, si
    usa e si lascia andare.
    """
    provider = _provider(_Http(), key_path)
    provider._bearer()

    pem = Path(key_path).read_text(encoding="utf-8")
    secret_line = pem.splitlines()[1]

    for value in vars(provider).values():
        assert secret_line not in str(value), "la chiave e' rimasta nell'oggetto"
    assert secret_line not in repr(provider)
    assert "BEGIN PRIVATE KEY" not in repr(provider)


# ---------------------------------------------------------------------------
# Il consenso
# ---------------------------------------------------------------------------

def test_the_institutions_come_from_the_aggregator(key_path):
    """§4: l'elenco e' quello vero, e porta con se' il paese."""
    async def body():
        provider = _provider(_Http(), key_path)
        banks = await provider.institutions(country="IT")
        assert [b.id for b in banks] == ["IT:Mock ASPSP", "IT:UniCredit"]
        assert banks[0].country == "IT"
        assert banks[0].sandbox is True

    _run(body())


def test_the_authorization_asks_for_the_registered_return_address(key_path):
    """
    §4: l'indirizzo di ritorno non e' una scelta.

    Trovato sull'API vera, non da un test: mandare il ritorno alla schermata
    dell'app fa rispondere «REDIRECT_URI_NOT_ALLOWED». L'unico indirizzo
    ammesso e' quello registrato nell'applicazione — dove va la persona
    *dopo* e' un'altra cosa, e la decide la porta di ritorno.
    """
    async def body():
        http = _Http()
        provider = _provider(http, key_path)
        started = await provider.begin_link(
            institution_id="IT:Mock ASPSP",
            redirect="http://localhost:8081/conti-e-denaro",
            reference="ora_stato_1",
        )
        assert started["link"].startswith("https://")
        sent = http.bodies[-1]
        assert sent["redirect_url"] == CALLBACK
        assert sent["aspsp"] == {"name": "Mock ASPSP", "country": "IT"}
        assert sent["state"] == "ora_stato_1"
        assert sent["psu_type"] == "personal"
        assert sent["access"]["valid_until"] > "2026"

    _run(body())


def test_the_code_becomes_a_session_and_the_session_is_the_permission(key_path):
    """
    §4: UN CODICE NON E' UN PERMESSO. LO DIVENTA UNA VOLTA SOLA.

    Saltare lo scambio e andare dritti ai conti non e' una scorciatoia: e'
    una cosa che non funziona, perche' il codice non apre niente.
    """
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            svc, vault, http, _, done = await _linked(db, uid, key_path)
            assert done["ok"] is True
            assert "POST /sessions" in http.calls

            # Il permesso sta nel vault, e nel documento c'e' solo il puntatore.
            assert any("session_id" in kept for kept in vault.kept.values())
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0},
            )
            assert instance["status"] == "connected"
            assert instance["secret_reference"]
            assert "sess-1" not in jsonlib.dumps(instance, default=str)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_unknown_state_opens_nothing(key_path):
    """
    §4: LO «STATE» E' L'UNICA COSA CHE LEGA UN RITORNO A UNA PERSONA.

    Chi arriva sulla porta di ritorno non e' autenticato — e' un browser che
    torna da un altro sito. Se uno state qualunque bastasse, chiunque
    potrebbe far finire un conto dentro l'account sbagliato.
    """
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank.link import complete_with_code

            svc, _, http = await _service(db, key_path)
            out = await complete_with_code(svc, state="inventato", code="x")
            assert out["ok"] is False
            assert "POST /sessions" not in http.calls, (
                "ha provato ad aprire una sessione per uno state sconosciuto"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_state_works_once_and_then_never_again(key_path):
    """§4: un biglietto usato non e' piu' un biglietto."""
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank.link import complete_with_code

            svc, _, _, _, _ = await _linked(db, uid, key_path)
            state = (await db.bank_link_states.find_one(
                {"user_id": uid}, {"_id": 0, "state": 1},
            ))["state"]
            again = await complete_with_code(svc, state=state, code="il-codice")
            assert again["ok"] is False
            assert "già stato usato" in again["perche"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_expired_state_is_refused(key_path):
    """§4: e scade, perche' una chiave che resta valida per ore gira per ore."""
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank.link import complete_with_code

            svc, _, http = await _service(db, key_path)
            await svc.begin_link(
                user_id=uid, institution_id="IT:Mock ASPSP",
                redirect_to="http://localhost:8081/conti-e-denaro",
            )
            row = await db.bank_link_states.find_one({"user_id": uid}, {"_id": 0})
            await db.bank_link_states.update_one(
                {"state": row["state"]},
                {"$set": {"expires_at": "2020-01-01T00:00:00+00:00"}},
            )
            out = await complete_with_code(svc, state=row["state"], code="x")
            assert out["ok"] is False and "scaduto" in out["perche"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_callback_never_answers_with_json(key_path):
    """
    §4: sulla porta di ritorno ci arriva una persona dentro un browser.

    Quello che deve succederle e' ritrovarsi nell'app, non leggere un
    oggetto. E il codice della banca non compare mai nell'indirizzo di
    ritorno: e' stato speso, e il suo lavoro e' finito.
    """
    source = (HERE / "connectors" / "bank" / "router.py").read_text(encoding="utf-8")
    assert "RedirectResponse" in source
    assert "sanitize_redirect_after" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            rendered = ast.unparse(node)
            assert "code" not in rendered.split("collegamento")[0] or "quote" in rendered


# ---------------------------------------------------------------------------
# La traduzione
# ---------------------------------------------------------------------------

def test_an_account_arrives_with_its_currency_and_without_its_iban(key_path):
    """§11/§14: il conto si riconosce dalle ultime quattro cifre."""
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid, key_path)
            row = await db.bank_accounts.find_one({"owner_id": uid}, {"_id": 0})
            assert row["account_ref"] == "acc-uid-1"
            assert row["currency"] == "EUR"
            assert row["institution"] == "Mock ASPSP"
            assert row.get("masked_number") == "•••• 3456"
            assert IBAN not in jsonlib.dumps(row, default=str)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_balance_keeps_booked_and_available_apart(key_path):
    """§9: contabile e disponibile non sono lo stesso numero."""
    async def body():
        provider = _provider(_Http(), key_path)
        got = await provider.balance(access_token="sess-1", account_ref="acc-uid-1")
        assert got["current"] == 3250.00
        assert got["available"] == 3180.50
        assert got["at"].startswith("2026-09-07")

    _run(body())


def test_a_bank_that_gives_no_balance_leaves_it_unknown(key_path):
    """§9 + SCONOSCIUTO NON E' ZERO."""
    async def body():
        provider = _provider(_Http(balances=[]), key_path)
        assert await provider.balance(
            access_token="sess-1", account_ref="acc-uid-1") is None

    _run(body())


def test_the_sign_comes_from_the_indicator_and_not_from_the_amount(key_path):
    """
    §8: gli importi arrivano senza segno.

    Un numero positivo e un indicatore: `DBIT` o `CRDT`. Sbagliare questa
    traduzione vorrebbe dire raccontare uno stipendio come una spesa — e
    nessun controllo a valle se ne accorgerebbe, perche' il numero e' giusto.
    """
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid, key_path)
            out = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "eb-tx-1"}, {"_id": 0})
            assert out["amount"] == -760.00
            assert out["direction"] == "outgoing"
            assert out["counterparty"] == "M. B."
            assert "BONIFICO SEPA" in out["raw_description"]
            assert out["booked_at"].startswith("2026-09-01")

            income = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "eb-tx-2"}, {"_id": 0})
            assert income["amount"] == 2050.00
            assert income["direction"] == "incoming"
            assert income["counterparty"] == "ACME SRL"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_continuation_is_followed_to_the_end(key_path):
    """
    §4/§10: fermarsi alla prima pagina perde tutto il resto in silenzio.

    E nessuno se ne accorge, perche' una pagina di movimenti sembra un
    estratto conto.
    """
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            _, _, http, _, _ = await _linked(db, uid, key_path)
            assert len([c for c in http.calls if "/transactions" in c]) == 2
            assert await db.financial_observations.count_documents(
                {"owner_id": uid}) == 3
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_pending_line_that_settles_updates_instead_of_doubling(key_path):
    """§12: la stessa riga che si consolida resta una riga sola."""
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            svc, _, _, _, _ = await _linked(db, uid, key_path)
            pending = await db.financial_observations.find(
                {"owner_id": uid, "provenance.status": "pending"}, {"_id": 0},
            ).to_list(5)
            assert len(pending) == 1

            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1})
            svc.provider = _provider(_Http(settle_pending=True), key_path)
            again = await svc.sync(user_id=uid, instance_id=instance["id"])

            assert again["written"] == 0
            assert await db.financial_observations.count_documents(
                {"owner_id": uid}) == 3
            # La riga e' la stessa: cambia stato e riferimento, non identita'.
            settled = await db.financial_observations.find_one(
                {"owner_id": uid, "amount": -22.50}, {"_id": 0})
            assert settled is not None
            assert settled["provenance"]["status"] == "booked"
            assert await db.financial_observations.count_documents(
                {"owner_id": uid, "provenance.status": "pending"}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_reading_the_same_statement_twice_writes_nothing_new(key_path):
    """§12: la seconda lettura non raddoppia niente."""
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            svc, _, _, _, _ = await _linked(db, uid, key_path)
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1})
            before = await db.financial_observations.count_documents({"owner_id": uid})
            again = await svc.sync(user_id=uid, instance_id=instance["id"])
            after = await db.financial_observations.count_documents({"owner_id": uid})
            assert before == after == 3
            assert again["written"] == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_connection_survives_a_restart(key_path):
    """
    §5-L: dopo un riavvio il permesso e' ancora dove lo si e' messo.

    Nessuno stato in memoria: la sessione sta nel vault e l'istanza nel
    database, e un servizio costruito da zero legge esattamente come prima.
    """
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            _, vault, _, _, _ = await _linked(db, uid, key_path)

            # Un processo nuovo: servizio nuovo, provider nuovo, stesso vault.
            from connectors.bank.service import BankReadService

            fresh = BankReadService(
                db=db, permissions=_Permissions(), vault=vault,
                provider=_provider(_Http(), key_path),
            )
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1})
            out = await fresh.sync(user_id=uid, instance_id=instance["id"])
            assert out["ok"] is True
            assert out["accounts"] == 1

            state = await fresh.state(user_id=uid)
            assert state["stato"] == "collegato"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_providers_code_stays_evidence_and_never_becomes_a_name(key_path):
    """§8: «PMNT» e' un codice di schema bancario, non un significato."""
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid, key_path)
            row = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "eb-tx-1"}, {"_id": 0})
            assert row["provenance"]["provider_hint"] == "PMNT"
            for forbidden in ("category", "interpreted_kind", "label"):
                assert forbidden not in row

            from financial.overview import money_overview

            blob = jsonlib.dumps(await money_overview(db, uid), default=str)
            assert "PMNT" not in blob
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_real_observation_is_not_knowledge_until_governance_says_so(key_path):
    """§12: leggere non e' sapere, nemmeno con una banca vera."""
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            await _linked(db, uid, key_path)
            assert await db.financial_observations.count_documents(
                {"owner_id": uid}) == 3
            assert await db.financial_facts.count_documents({"owner_id": uid}) == 0
            assert await db.memories.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_disconnecting_closes_the_session(key_path):
    """§7/§14: finche' la sessione vive, il permesso di leggere esiste."""
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            svc, vault, http, _, _ = await _linked(db, uid, key_path)
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1, "secret_reference": 1})
            out = await svc.disconnect(user_id=uid, instance_id=instance["id"])
            assert out["ok"] is True
            assert any(c.startswith("DELETE /sessions/") for c in http.calls)
            assert instance["secret_reference"] in vault.revoked
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# La coda
# ---------------------------------------------------------------------------

def test_the_bank_is_in_the_queue_and_the_shelf_does_not_starve_it(key_path):
    """
    §13: una banca dietro un arretrato di documenti viene letta lo stesso.

    Il rischio e' concreto: lo scaffale dei documenti e' la sorgente piu'
    numerosa, e una coda ordinata per attesa puo' mettere una banca appena
    scaduta sempre dietro. Quando una persona viene presa, pero', vengono
    prese *tutte* le sue sorgenti scadute — ed e' questo che va verificato,
    perche' e' l'unica ragione per cui la banca non resta indietro.
    """
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import due

            await _linked(db, uid, key_path)
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1})

            # Lo scaffale dei documenti, scaduto da un pezzo.
            await db.connected_source_attempts.update_one(
                {"owner_id": uid, "source_id": f"documents:{uid}"},
                {"$set": {"owner_id": uid, "source_id": f"documents:{uid}",
                          "next_attempt_at": "2020-01-01T00:00:00+00:00",
                          "failures": 0}},
                upsert=True,
            )
            # E la banca, scaduta adesso.
            await db.connected_source_attempts.update_one(
                {"owner_id": uid, "source_id": instance["id"]},
                {"$set": {"owner_id": uid, "source_id": instance["id"],
                          "next_attempt_at": "2020-06-01T00:00:00+00:00",
                          "failures": 0}},
                upsert=True,
            )

            waiting = [s.source_type for s in await due(db, uid)]
            assert "bank" in waiting, "la banca non e' nemmeno in coda"
            assert "documents" in waiting, "lo scaffale non e' in coda"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_bank_source_is_a_kind_of_its_own(key_path):
    """
    §13: «bank» esiste nel modello delle sorgenti.

    Trovato con una prova, non a tavolino: senza, costruire la sorgente
    bancaria sollevava un errore di validazione *fuori* dal try, e la lettura
    dell'intero elenco delle sorgenti di quella persona falliva. La banca non
    entrava in coda affatto — e nemmeno il calendario e la posta, dopo di
    lei.
    """
    from connected.models import ConnectedSource

    source = ConnectedSource(
        id="x", owner_id="y", source_type="bank", provider="Mock ASPSP",
    )
    assert source.source_type == "bank"

    from connected.polling import POLL_SECONDS

    assert POLL_SECONDS["bank"] >= 3600, "una banca non si guarda ogni minuto"


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


def test_no_verb_moves_money_anywhere_in_the_bank_connector():
    """
    §7: Enable Banking sa anche avviare pagamenti. ORA no.

    Un attuatore che non esiste non puo' essere chiamato per sbaglio.
    """
    for path in (HERE / "connectors" / "bank").glob("*.py"):
        source = _code_only(path).lower()
        for forbidden in ("def transfer", "def pay", "def initiate",
                          "def create_payment", "def cancel_direct_debit",
                          "def block_card", "payment_initiation",
                          "def open_account", "mail.send"):
            assert forbidden not in source, (
                f"connectors/bank/{path.name} contiene «{forbidden}»"
            )


def test_no_payment_endpoint_is_ever_named():
    """
    §7: non basta non avere il verbo — non deve esserci nemmeno l'indirizzo.

    Un percorso scritto in una costante e' una riga di distanza dall'essere
    chiamato.
    """
    offenders = []
    for path in (HERE / "connectors" / "bank").glob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for forbidden in ("/payments", "/payment-requests", "/beneficiaries",
                          "/mandates", "/payouts", "/refunds",
                          "payment_request", "payment_initiation"):
            if forbidden in source:
                offenders.append(f"{path.name}: «{forbidden}»")
    assert not offenders, f"un percorso dei pagamenti compare qui: {offenders}"


def test_the_key_and_the_application_id_come_only_from_the_environment():
    """§14: nel codice non c'e' nessuna credenziale, e non c'e' un ripiego."""
    source = (
        HERE / "connectors" / "bank" / "enablebanking_provider.py"
    ).read_text(encoding="utf-8")

    offenders = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = " ".join(ast.unparse(t) for t in targets).lower()
        if not any(w in names for w in ("key", "secret", "token", "password",
                                        "application_id")):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
            offenders.append(f"{names} = «{value.value[:8]}…»")
    assert not offenders, f"una credenziale e' scritta nel codice: {offenders}"

    flat = " ".join(source.split())
    assert 'os.environ.get( "ENABLE_BANKING_PRIVATE_KEY_PATH"' in flat or            'os.environ.get("ENABLE_BANKING_PRIVATE_KEY_PATH"' in flat
    assert 'os.environ.get("ENABLE_BANKING_APPLICATION_ID"' in flat
    assert "BEGIN PRIVATE KEY" not in source


def test_the_error_bodies_never_reach_the_logs():
    """
    §14: il corpo di un errore puo' contenere un IBAN o un nome.

    Nei log resta il codice, che e' tutto quello che serve per decidere cosa
    fare.
    """
    source = _code_only(
        HERE / "connectors" / "bank" / "enablebanking_provider.py"
    )
    for forbidden in ("logger.info(response.text", "logger.warning(response",
                      "print(response", "logger.error(response"):
        assert forbidden not in source


def test_there_is_still_no_sixth_tab():
    """§11: «Conti e denaro» vive dentro Vita."""
    tabs = HERE.parent / "frontend" / "app" / "(tabs)"
    names = {p.stem.lower() for p in tabs.glob("*.tsx")} if tabs.exists() else set()
    for forbidden in ("conti", "denaro", "banca", "finanze", "wallet", "banking"):
        assert forbidden not in names, f"c'e' una scheda «{forbidden}»"


def test_the_session_names_the_accounts_in_two_different_shapes(key_path):
    """
    §7/§8: LA SESSIONE DICE I CONTI IN DUE MODI, E NON SONO LO STESSO.

    Trovato sull'API vera durante il collegamento sandbox, non a tavolino:
    `POST /sessions` mette gli oggetti-conto dentro `accounts`, mentre
    `GET /sessions/{id}` mette li' soltanto gli identificativi, e i dettagli
    in `accounts_data`. Leggendo solo `accounts` da entrambe, la seconda
    tornava una lista di stringhe che venivano scartate in silenzio: il
    collegamento risultava riuscito, con zero conti dentro — che e' il modo
    peggiore di fallire, perche' sembra funzionare.
    """
    async def body():
        from connectors.bank.enablebanking_provider import EnableBankingProvider

        class _AsTheApiReallyAnswers(_Http):
            async def request(self, method, url, headers=None, json=None, params=None):
                path = url.split("enablebanking.com", 1)[-1]
                if path.startswith("/sessions/") and method == "GET":
                    self.calls.append(f"{method} {path}")
                    return _Response(200, {
                        "status": "AUTHORIZED",
                        "aspsp": {"name": "Mock ASPSP", "country": "IT"},
                        # Solo identificativi qui…
                        "accounts": ["acc-uid-1"],
                        # …e i dettagli qui.
                        "accounts_data": [{
                            "uid": "acc-uid-1", "currency": "EUR",
                            "account_id": {"iban": IBAN},
                            "product": "Conto corrente",
                            "cash_account_type": "CACC",
                        }],
                    })
                return await super().request(
                    method, url, headers=headers, json=json, params=params)

        provider = EnableBankingProvider(
            application_id=APP_ID, private_key_path=key_path,
            redirect_uri=CALLBACK, http=_AsTheApiReallyAnswers(),
        )
        found = await provider.accounts(access_token="sess-1")
        assert len(found) == 1, "il conto e' stato scartato perche' era una stringa"
        assert found[0].account_ref == "acc-uid-1"
        assert found[0].display_name == "Conto corrente"
        assert found[0].masked_number == "•••• 3456"

    _run(body())


def test_a_reading_that_found_no_accounts_leaves_the_watermark_alone(key_path):
    """
    §5/§10: UNA LETTURA SENZA CONTI NON E' UNA LETTURA.

    Trovato sul collegamento sandbox vero. La prima lettura non riconosceva
    nessun conto — un difetto di traduzione — e spostava comunque il
    segnaposto a ieri. La lettura successiva, con il difetto corretto, ha
    chiesto alla banca solo l'ultimo giorno: sei mesi di storia saltati per
    sempre, in silenzio, senza un errore che lo dicesse. Delle dodici righe
    del conto ne erano arrivate tre.
    """
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank.service import BankReadService

            class _NoAccounts(_Http):
                async def request(self, method, url, headers=None, json=None, params=None):
                    path = url.split("enablebanking.com", 1)[-1]
                    if path.startswith("/sessions/") and method == "GET":
                        self.calls.append(f"{method} {path}")
                        return _Response(200, {
                            "status": "AUTHORIZED",
                            "aspsp": {"name": "Mock ASPSP", "country": "IT"},
                            "accounts": [], "accounts_data": [],
                        })
                    return await super().request(
                        method, url, headers=headers, json=json, params=params)

            svc, vault, _, _, _ = await _linked(db, uid, key_path)
            instance = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1})
            before = await db.connector_instances.find_one(
                {"id": instance["id"]}, {"_id": 0, "cursor": 1})

            blind = BankReadService(
                db=db, permissions=_Permissions(), vault=vault,
                provider=_provider(_NoAccounts(), key_path),
            )
            out = await blind.sync(user_id=uid, instance_id=instance["id"])
            assert out["accounts"] == 0

            after = await db.connector_instances.find_one(
                {"id": instance["id"]}, {"_id": 0, "cursor": 1})
            assert after["cursor"] == before["cursor"], (
                "una lettura a vuoto ha spostato il segnaposto"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_account_without_an_iban_shows_no_number_at_all(key_path):
    """
    §11: le ultime quattro lettere di un hash non sono un numero di conto.

    Il conto sandbox non ha IBAN, e ha un `identification_hash` in base64:
    mascherarlo produceva «•••• L40=» in schermata — che sembra un numero
    di conto e non lo e'. Meglio niente.
    """
    async def body():
        from connectors.bank.enablebanking_provider import EnableBankingProvider

        class _NoIban(_Http):
            async def request(self, method, url, headers=None, json=None, params=None):
                path = url.split("enablebanking.com", 1)[-1]
                if path.startswith("/sessions/") and method == "GET":
                    self.calls.append(f"{method} {path}")
                    return _Response(200, {
                        "status": "AUTHORIZED",
                        "aspsp": {"name": "Mock ASPSP", "country": "IT"},
                        "accounts": ["acc-uid-1"],
                        "accounts_data": [{
                            "uid": "acc-uid-1", "currency": "EUR",
                            "product": "Conto corrente",
                            "identification_hash": "WwpbCiJhc3BzcF9uYW1lIgpd.KV6g3woQL40=",
                        }],
                    })
                return await super().request(
                    method, url, headers=headers, json=json, params=params)

        provider = EnableBankingProvider(
            application_id=APP_ID, private_key_path=key_path,
            redirect_uri=CALLBACK, http=_NoIban(),
        )
        found = await provider.accounts(access_token="sess-1")
        assert found[0].masked_number is None, (
            f"in schermata comparirebbe «{found[0].masked_number}»"
        )

    _run(body())


def test_starting_a_new_link_does_not_break_the_one_that_works(key_path):
    """
    §6: RICOLLEGARE NON E' SCOLLEGARE.

    Trovato mentre si preparava lo screenshot del consenso: ricominciare il
    percorso su una banca gia' collegata riscriveva l'istanza con `pending` e
    un riferimento vuoto, e il permesso vivo spariva prima ancora che il
    nuovo esistesse. Bastava aprire la schermata e cambiare idea per restare
    senza conto.
    """
    async def body():
        client, db = await _db()
        uid = f"eb_{uuid.uuid4().hex[:8]}"
        try:
            svc, _, _, _, _ = await _linked(db, uid, key_path)
            before = await db.connector_instances.find_one(
                {"user_id": uid}, {"_id": 0, "id": 1, "status": 1, "secret_reference": 1})
            assert before["status"] == "connected" and before["secret_reference"]

            await svc.begin_link(
                user_id=uid, institution_id="IT:Mock ASPSP",
                redirect_to="http://localhost:8081/conti-e-denaro",
            )

            after = await db.connector_instances.find_one(
                {"id": before["id"]}, {"_id": 0, "status": 1, "secret_reference": 1})
            assert after["secret_reference"] == before["secret_reference"], (
                "il permesso vivo e' stato cancellato da un tentativo nuovo"
            )
            assert after["status"] == "connected"

            # E la lettura continua a funzionare.
            out = await svc.sync(user_id=uid, instance_id=before["id"])
            assert out["ok"] is True and out["accounts"] == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
