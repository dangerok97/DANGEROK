"""
V3.11 Sprint 5 — la banca come strumento, non come verità.

    BANK DATA IS A SENSOR.
    AI INTERPRETS WHAT IT MEANS.
    GOVERNANCE DECIDES WHAT BECOMES KNOWLEDGE.

Un estratto conto e' la cosa piu' facile da fraintendere che esista in un
prodotto come questo: sembra la verita' economica di una persona, ed e'
invece un elenco di righe scritte da una banca che non la conosce. `-118,42 €
· ENERGIA ITALIA S.P.A.` puo' essere una bolletta, un rimborso, o un
pagamento fatto per la madre.

Quasi tutto quello che c'e' qui sotto tiene ferma quella distinzione mentre
il sistema cresce — perche' la scorciatoia (l'elenco di esercenti, la soglia
sulle ripetizioni, la categoria del provider presa per buona) funziona quasi
sempre, e quando sbaglia lo fa con sicurezza.
"""
from __future__ import annotations

import ast
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)


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


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("financial_facts", "financial_observations", "bank_accounts",
                 "connector_instances", "memories", "agent_goals",
                 "life_objects", "opportunities", "financial_impacts"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class _Permissions:
    class _Audit:
        async def log(self, **kw):
            return None

    def __init__(self):
        self.audit = self._Audit()


class _Vault:
    async def get(self, ref, *, user_id):
        return {"access_token": "t"}


async def _connected(db, uid, provider=None):
    from connectors.bank import BankReadService, FakeBankProvider

    svc = BankReadService(
        db=db, permissions=_Permissions(), vault=_Vault(),
        provider=provider or FakeBankProvider(),
    )
    made = await svc.connect(user_id=uid)
    return svc, made["instance_id"]


# ---------------------------------------------------------------------------
# Quello che la banca dice, e quello che non dice
# ---------------------------------------------------------------------------

def test_a_bank_line_arrives_as_an_observation_and_not_as_a_category():
    """
    §2/§5: la riga della banca resta la riga della banca.

    Nessuna interpretazione entra nell'osservazione. Se ci fosse un campo per
    la categoria, prima o poi qualcuno lo riempirebbe con una regola, e la
    regola diventerebbe la verita' senza che nessuno l'abbia decisa.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            svc, instance_id = await _connected(db, uid)
            out = await svc.sync(user_id=uid, instance_id=instance_id)
            assert out["ok"] and out["written"] > 0

            row = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "tx_a002"}, {"_id": 0},
            )
            assert row["raw_description"] == "BONIFICO A ROSSI MARCO"
            assert row["amount"] == -760.0
            assert row["direction"] == "outgoing"
            # Nessuna conclusione, da nessuna parte nella riga.
            blob = str(row).lower()
            for forbidden in ("affitto", "rent", "category", "interpreted"):
                assert forbidden not in blob, (
                    f"l'osservazione porta un'interpretazione: «{forbidden}»"
                )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_providers_own_category_is_evidence_and_never_the_answer():
    """
    §2: provider category != ORA interpretation.

    L'aggregatore dice «utilities», e va conservato — e' un indizio vero. Ma
    resta dentro le prove, con un nome che dice cos'e': un suggerimento di
    qualcuno che non conosce questa vita.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            svc, instance_id = await _connected(db, uid)
            await svc.sync(user_id=uid, instance_id=instance_id)

            row = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "tx_b001"}, {"_id": 0},
            )
            assert row["provenance"]["provider_hint"] == "utilities"
            # Non e' un campo di primo livello dell'osservazione: sta fra le
            # prove, dove sta tutto quello che qualcun altro ha detto.
            assert "provider_category" not in row
            assert "category" not in row
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_balance_the_bank_did_not_give_is_unknown_and_not_zero():
    """
    §7: SCONOSCIUTO NON E' ZERO — anche sul saldo.

    Alcuni aggregatori danno il saldo solo su richiesta, altri mai. Uno zero
    di ripiego direbbe «hai il conto vuoto»: una cosa falsa detta con
    precisione, sulla cifra piu' delicata che ci sia.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank.provider import AccountSummary, FakeBankProvider

            class Silent(FakeBankProvider):
                async def accounts(self, *, access_token):
                    return [AccountSummary(
                        account_ref="acc_quiet", display_name="Conto",
                        institution="Banca silenziosa", currency="EUR",
                    )]

                async def balance(self, *, access_token, account_ref):
                    # Muta anche quando gliela si chiede a parte: con un
                    # aggregatore vero i saldi sono un endpoint per conto
                    # suo, e questa banca non risponde nemmeno li'.
                    return None

            svc, instance_id = await _connected(db, uid, Silent())
            await svc.sync(user_id=uid, instance_id=instance_id)

            row = await db.bank_accounts.find_one(
                {"owner_id": uid, "account_ref": "acc_quiet"}, {"_id": 0},
            )
            assert "current_balance" not in row, "un saldo non dato è stato inventato"

            from financial.overview import money_overview

            shown = await money_overview(db, uid)
            account = shown["conti"][0]
            assert account["saldo_noto"] is False
            assert "0" not in account["saldo"]
            assert "non comunicato" in account["saldo"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Leggere due volte
# ---------------------------------------------------------------------------

def test_reading_the_same_statement_twice_writes_nothing_new():
    """§4: dedupe sul riferimento della transazione."""
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            svc, instance_id = await _connected(db, uid)
            first = await svc.sync(user_id=uid, instance_id=instance_id)
            how_many = await db.financial_observations.count_documents(
                {"owner_id": uid},
            )
            second = await svc.sync(user_id=uid, instance_id=instance_id)
            assert second["written"] == 0, "una rilettura ha scritto righe nuove"
            assert await db.financial_observations.count_documents(
                {"owner_id": uid},
            ) == how_many
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_pending_line_that_settles_updates_instead_of_doubling():
    """
    §4: in sospeso → contabilizzato.

    E' la stessa riga con un altro stato, e affiancarla vorrebbe dire avere
    due volte lo stesso caffe' — con l'importo contato due volte da tutto
    quello che sta a valle.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank import FakeBankProvider

            provider = FakeBankProvider()
            svc, instance_id = await _connected(db, uid, provider)
            await svc.sync(user_id=uid, instance_id=instance_id)

            before = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "tx_b005"}, {"_id": 0},
            )
            assert before["provenance"]["status"] == "pending"

            account = (await provider.accounts(access_token="t"))[0]
            outcome = await svc._record(
                uid, instance_id, account, provider.settle_the_pending_one(),
            )
            assert outcome == "updated"

            assert await db.financial_observations.count_documents(
                {"owner_id": uid, "transaction_ref": "tx_b005"},
            ) == 1
            after = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "tx_b005"}, {"_id": 0},
            )
            assert after["provenance"]["status"] == "booked"
            assert after["raw_description"] == "PAGAMENTO POS BAR CENTRALE"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_reversed_movement_is_marked_and_not_left_as_if_it_happened():
    """§4: uno storno e' la banca che dice «quella riga non vale piu'»."""
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank import FakeBankProvider

            provider = FakeBankProvider()
            svc, instance_id = await _connected(db, uid, provider)
            await svc.sync(user_id=uid, instance_id=instance_id)

            account = (await provider.accounts(access_token="t"))[0]
            outcome = await svc._record(
                uid, instance_id, account, provider.reverse("tx_b003"),
            )
            assert outcome == "updated"

            row = await db.financial_observations.find_one(
                {"owner_id": uid, "transaction_ref": "tx_b003"}, {"_id": 0},
            )
            assert row["provenance"]["status"] == "reversed"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_failed_read_leaves_the_cursor_where_it_was():
    """
    §4: un consenso scaduto non e' un guasto, ed e' anche la legge.

    PSD2 obbliga a rinnovarlo ogni tre mesi: succedera' per sempre, e va
    detto in modo che una persona sappia cosa fare — non «token non valido».
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank import FakeBankProvider
            from connectors.bank.provider import BankAPIError

            class Expired(FakeBankProvider):
                async def accounts(self, *, access_token):
                    raise BankAPIError(401)

            svc, instance_id = await _connected(db, uid, Expired())
            out = await svc.sync(user_id=uid, instance_id=instance_id)

            assert out["ok"] is False
            assert out["reason"] == "consent_expired"
            assert "autorizzi di nuovo" in out["human"]
            for technical in ("401", "token", "oauth", "scope"):
                assert technical not in out["human"].lower(), (
                    f"il messaggio è tecnico: «{technical}»"
                )

            instance = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0, "status": 1, "cursor": 1},
            )
            assert instance["status"] == "reauthorization_required"
            assert not (instance.get("cursor") or {}).get("since"), (
                "il segnaposto si è mosso dopo una lettura fallita"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_bank_is_looked_at_gently():
    """
    §4: una banca non e' una casella.

    Le righe arrivano quando arrivano, e guardarla ogni minuto non le fa
    arrivare prima — ma consuma la quota del provider e, con alcuni
    aggregatori, si paga a chiamata.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            _, instance_id = await _connected(db, uid)
            instance = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0, "poll_interval_min": 1},
            )
            assert instance["poll_interval_min"] >= 60, (
                "la banca viene interrogata troppo spesso"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Il significato, che non e' del codice
# ---------------------------------------------------------------------------

def _answer(**over):
    base = {
        "interpreted_kind": "unclear", "likely_label": "",
        "recurring_likelihood": "high", "pattern_status": "recurring",
        "linked_situations": [], "linked_goals": [], "certainty": "low",
        "missing_information": ["cosa sia questo pagamento"],
        "evidence_refs": [], "should_persist": False, "should_ask_user": True,
        "reason": "succede ogni mese verso la stessa persona",
    }
    base.update(over)
    return base


def _install(monkeypatch, answer):
    async def read(*a, **kw):
        return answer

    monkeypatch.setattr("financial.reasoning.read_a_movement", read, raising=True)


def _observation(uid, n, *, amount=-760.0, who="BONIFICO A ROSSI MARCO"):
    from financial.observation import BankObservation

    base = datetime(2026, 3, 1, tzinfo=timezone.utc)
    return BankObservation(
        owner_id=uid, account_ref="acc_main", transaction_ref=f"tx_{uid}_{n}",
        booked_at=(base + timedelta(days=30 * n)).isoformat(),
        amount=amount, direction="outgoing", raw_description=who,
        provenance={"connector_id": "banking_psd2"},
    )


def test_a_monthly_transfer_to_a_person_is_not_rent_by_itself(monkeypatch):
    """
    §5/§16: «-760 € verso Rossi, ogni mese» senza altro resta non identificato.

    E' plausibile che sia un affitto. E' anche plausibile che sia un prestito
    restituito, un mantenimento, una quota divisa fra coinquilini. Il nome
    giusto e' quello che non si da'.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from financial import movements
            from financial.store import FinancialStore

            _install(monkeypatch, _answer())
            for n in range(5):
                await movements.look_at_a_movement(db, _observation(uid, n))
            out = await movements.look_at_a_movement(db, _observation(uid, 5))

            assert out["outcome"] == "seen_not_understood"
            assert "non ho ancora identificato" in out["how_to_say_it"]
            assert await FinancialStore(db).known(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_transfer_becomes_rent_when_the_evidence_says_so(monkeypatch):
    """
    §12: la stessa riga, con un'email e una situazione intorno, si capisce.

    E' il cuore del cross-source: non e' la stringa a decidere, e' l'insieme.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from financial import movements
            from financial.store import FinancialStore

            _install(monkeypatch, _answer(
                interpreted_kind="commitment", likely_label="affitto",
                certainty="high", should_persist=True, pattern_status="recurring",
            ))
            out = await movements.look_at_a_movement(db, _observation(uid, 9))

            assert out["outcome"] in ("kept", "already_known")
            assert out["what"] == "affitto"
            known = await FinancialStore(db).known(uid)
            assert [f.what for f in known] == ["affitto"]
            assert known[0].provenance[0].source == "bank"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_monthly_incoming_transfer_is_not_a_salary_by_itself(monkeypatch):
    """
    §10: un bonifico mensile in entrata non diventa stipendio da solo.

    Puo' essere un affitto incassato, un rimborso ricorrente, dei soldi da un
    familiare. Serve altro — la controparte, un cedolino, quello che ORA sa
    di questa vita — e senza, «entrata ricorrente non identificata».
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from financial import movements
            from financial.store import FinancialStore

            _install(monkeypatch, _answer(
                interpreted_kind="income", likely_label="", certainty="low",
                should_persist=False, pattern_status="recurring",
            ))
            out = await movements.look_at_a_movement(
                db, _observation(uid, 3, amount=2050.0, who="BONIFICO DA X"),
            )
            assert out["outcome"] == "seen_not_understood"
            assert await FinancialStore(db).known(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_everyday_spending_does_not_become_something_ora_remembers(monkeypatch):
    """
    §16: un caffe' e la spesa non sono fatti durevoli di una vita.

    Sono successi, e restano fra le osservazioni. Farne memoria vorrebbe dire
    riempire quello che ORA sa di una persona con la sua lista della spesa.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from financial import movements
            from financial.durable import governed_facts

            _install(monkeypatch, _answer(
                interpreted_kind="event", likely_label="spesa al supermercato",
                certainty="high", should_persist=False, pattern_status="one_off",
            ))
            out = await movements.look_at_a_movement(
                db, _observation(uid, 4, amount=-36.20, who="PAGAMENTO POS SUPERMERCATO"),
            )
            assert out["outcome"] == "seen_not_understood"
            assert out["why_not_kept"] == "non e' una cosa che valga la pena ricordare"
            assert await governed_facts(db, uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_transaction_never_creates_work_by_itself(monkeypatch):
    """§15/§17: nessun goal, nessuna opportunity da un movimento."""
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from financial import movements

            _install(monkeypatch, _answer(
                interpreted_kind="commitment", likely_label="affitto",
                certainty="high", should_persist=True,
            ))
            await movements.look_at_a_movement(db, _observation(uid, 7))

            for coll in ("agent_goals", "opportunities"):
                assert await db[coll].count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# «Conti e denaro»
# ---------------------------------------------------------------------------

def test_the_screen_keeps_what_was_seen_apart_from_what_was_understood():
    """
    §8: L'OSSERVAZIONE E L'INTERPRETAZIONE NON SI FONDONO MAI.

    Un elenco che scrive «Affitto» sopra una riga che diceva «BONIFICO A
    ROSSI MARCO» ha appena trasformato un'ipotesi in un fatto sotto gli occhi
    di chi legge, e nessuno se ne accorge.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from financial.overview import money_overview

            svc, instance_id = await _connected(db, uid)
            await svc.sync(user_id=uid, instance_id=instance_id)

            shown = await money_overview(db, uid)
            descriptions = [m["descrizione"] for m in shown["movimenti_recenti"]]
            assert any("BONIFICO A ROSSI MARCO" in d for d in descriptions), (
                "i movimenti non sono mostrati come li ha scritti la banca"
            )
            # Nessuna interpretazione dentro la lista dei movimenti.
            for movement in shown["movimenti_recenti"]:
                assert set(movement.keys()) == {
                    "quando", "descrizione", "quanto", "verso", "in_sospeso",
                }
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_screen_says_what_ora_can_and_cannot_do_in_words():
    """
    §13: la trasparenza serve a chi legge, non a chi la scrive.

    Nessuno scope tecnico: «accounts:read» non dice niente a nessuno, e
    nasconde esattamente la cosa che una persona vuole sapere.
    """
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from financial.overview import money_overview

            svc, instance_id = await _connected(db, uid)
            await svc.sync(user_id=uid, instance_id=instance_id)

            account = (await money_overview(db, uid))["conti"][0]
            assert "leggere" in account["cosa_posso_fare"]
            assert "Non posso spostare denaro" in account["cosa_non_posso_fare"]
            blob = str(account).lower()
            for technical in ("scope", "oauth", "psd2", "ais", "token", "read:"):
                assert technical not in blob, f"in schermata compare «{technical}»"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_screen_shows_nothing_when_there_is_nothing():
    """Una schermata che dice «non so niente» è peggio della sua assenza."""
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            from financial.overview import money_overview

            shown = await money_overview(db, uid)
            assert shown["vale_la_pena_mostrarlo"] is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# I confini
# ---------------------------------------------------------------------------

def test_the_bank_connector_has_no_verb_that_moves_money():
    """
    §3: SPRINT 5 E' SOLO LETTURA.

    Un attuatore che non esiste non puo' essere chiamato per sbaglio. Questa
    guardia verifica che continui a non esistere — nel protocollo, nel
    provider e nel servizio.
    """
    for name in ("provider.py", "service.py", "__init__.py"):
        source = _code_only(HERE / "connectors" / "bank" / name).lower()
        for forbidden in ("def transfer", "def pay", "def initiate",
                          "def cancel_direct_debit", "def block_card",
                          "payment_initiation", "def open_account",
                          "mail.send"):
            assert forbidden not in source, (
                f"connectors/bank/{name} contiene «{forbidden}»"
            )


def test_the_connector_asks_only_for_read_scopes():
    """§3: il consenso chiesto e' di sola lettura."""
    async def body():
        client, db = await _db()
        uid = f"bank_{uuid.uuid4().hex[:8]}"
        try:
            _, instance_id = await _connected(db, uid)
            instance = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0, "authorized_scopes": 1},
            )
            scopes = instance.get("authorized_scopes") or []
            assert scopes, "nessuno scope dichiarato"
            for scope in scopes:
                assert scope.endswith(":read"), f"scope non di lettura: «{scope}»"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_merchant_rule_decides_what_a_movement_is():
    """
    §5/§6: nessun elenco di esercenti, da nessuna parte.

    E' la scorciatoia piu' tentante di tutte — «se la descrizione contiene
    ENERGIA allora e' una bolletta» — e funziona finche' non arriva un
    rimborso da ENERGIA ITALIA.
    """
    # Un nome di esercente dentro l'istruzione che il modello legge — «una
    # riga che dice ENERGIA ITALIA puo' essere una bolletta o un rimborso» —
    # e' il contrario di una regola: e' il modo di dirgli di non concludere.
    # Quello che non deve esistere e' lo stesso nome dentro la logica: un
    # confronto, una chiave, una tabella. Le istruzioni sono lunghe, le
    # regole sono corte, e la lunghezza e' il modo piu' semplice di
    # distinguerle senza fingere di leggere le intenzioni.
    watched = ("energia", "enel", "esselunga", "netflix", "spotify",
               "affitto", "rent", "supermercato", "stipendio", "salary")
    offenders = []
    for path in list((HERE / "financial").glob("*.py")) + list(
        (HERE / "connectors" / "bank").glob("*.py")
    ):
        if path.name in ("reasoning.py", "provider.py"):
            # Il primo contiene le istruzioni per il giudizio; il secondo i
            # dati finti, che sono per definizione fatti di descrizioni vere.
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            if not isinstance(node.value, str) or len(node.value) > 60:
                continue
            # Parole intere: «rent» sta dentro «ricorrente» e «corrente», e
            # cercarlo come sottostringa fa fallire il file per l'italiano.
            words = set(re.findall(r"[a-zàèéìòù]+", node.value.lower()))
            for merchant in watched:
                if merchant in words:
                    offenders.append(f"{path.name}:{node.lineno} «{merchant}»")
    assert not offenders, f"una regola nomina un esercente o una categoria: {offenders}"


def test_no_threshold_turns_a_count_into_a_category():
    """
    §6: il codice conta, non conclude.

    `if occurrences >= 3: category = "subscription"` sarebbe una risposta
    permanente a una domanda che dipende da chi e' la persona.
    """
    offenders = []
    for path in list((HERE / "financial").glob("*.py")) + list(
        (HERE / "connectors" / "bank").glob("*.py")
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if isinstance(node.left, ast.Call):
                continue
            left = ast.dump(node.left).lower()
            if not any(
                w in left for w in ("times_seen", "occurrences", "recurring_count")
            ):
                continue
            for other in node.comparators:
                if isinstance(other, ast.Constant) and isinstance(
                    other.value, (int, float),
                ):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"un conteggio decide una categoria in {offenders}"


def test_there_is_still_no_sixth_tab():
    """§7: «Conti e denaro» vive dentro Vita."""
    tabs = HERE.parent / "frontend" / "app" / "(tabs)"
    names = {p.stem.lower() for p in tabs.glob("*.tsx")} if tabs.exists() else set()
    for forbidden in ("conti", "denaro", "banca", "finanze", "wallet", "banking"):
        assert forbidden not in names, f"c'è una scheda «{forbidden}»"


def test_the_bank_reaches_the_life_model_only_through_governance():
    """
    §1: BANK → OBSERVATION → AI → FACT → GOVERNANCE → LIFE MODEL.

    Nessun pezzo del connettore bancario scrive memorie: la banca e' uno
    strumento, e uno strumento non decide cosa una persona sa di se'.
    """
    for name in ("provider.py", "service.py"):
        source = (HERE / "connectors" / "bank" / name).read_text(encoding="utf-8")
        for forbidden in ("memories.insert", "memories.update",
                          "MemoryGovernanceService", "financial_facts.insert"):
            assert forbidden not in source, (
                f"connectors/bank/{name} scrive conoscenza: «{forbidden}»"
            )
