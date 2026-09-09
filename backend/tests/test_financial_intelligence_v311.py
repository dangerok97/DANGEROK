"""
V3.11 Sprint 1 — i soldi come contesto di vita.

    SCONOSCIUTO NON E' ZERO.
    L'IMPORTO NON DECIDE L'IMPORTANZA.
    IL CODICE NON SCEGLIE QUALE FONTE DICE IL VERO.

Tre frasi, e quasi tutto quello che c'e' qui sotto serve a tenerle vere sotto
pressione. La quarta, implicita in ognuna: ORA non deve mai produrre un numero
preciso che non sa.
"""
from __future__ import annotations

import ast
import os
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


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("financial_facts", "financial_impacts", "memories",
                 "agent_goals", "life_objects"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


def _from(source="email", how="lo dice un messaggio"):
    from financial.models import Provenance

    return Provenance(source=source, how_directly=how)


def _fact(uid, **over):
    from financial.models import FinancialFact, Money

    base = dict(
        owner_id=uid, kind="commitment", what="affitto",
        money=Money(amount=700, currency="EUR"),
        direction="outgoing", cadence="recurring", recurrence="ogni mese",
        provenance=[_from()],
    )
    base.update(over)
    return FinancialFact(**base)


def _soon(days=10):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


async def _known_by_ora(db, fact):
    """
    Un fatto come ORA lo sa davvero: osservato *e* passato dalla governance.

    Scriverlo solo nel registro non basta piu', ed e' il punto dello sprint:
    il registro dice cosa e' stato visto, il modello della vita dice cosa ORA
    sa. Chi risponde a una persona legge il secondo.
    """
    from financial.durable import propose
    from financial.store import FinancialStore

    await FinancialStore(db).remember(fact)
    return await propose(db, fact)


# ---------------------------------------------------------------------------
# Importi, valuta, e la cosa che non si sa
# ---------------------------------------------------------------------------

def test_an_amount_nobody_stated_is_unknown_and_never_zero():
    """
    §3: SCONOSCIUTO NON E' ZERO.

    Un'email che dice «il canone aumenta» senza cifra e' un fatto vero e
    importante di cui non si conosce l'importo. Zero sarebbe una bugia, e una
    bugia che poi qualcuno somma ad altre.
    """
    from financial.models import Money

    nothing = Money()
    assert nothing.amount is None
    assert nothing.is_known is False
    assert nothing.for_human() == "importo non noto"
    assert "0" not in nothing.for_human()

    real = Money(amount=0, currency="EUR")
    assert real.is_known is True, "uno zero dichiarato e' un importo, non un vuoto"


def test_money_is_written_the_way_a_person_reads_it():
    from financial.models import Money

    assert Money(amount=700, currency="EUR").for_human() == "€700"
    assert Money(amount=1234.5, currency="EUR").for_human() == "€1.234,50"


def test_a_fact_without_provenance_cannot_be_written():
    """
    §4: LA PROVENIENZA NON E' UN EXTRA.

    «850 euro di affitto» detto da un'email, da un contratto o dalla persona
    non sono la stessa cosa. Un fatto che non sa da dove viene non si puo'
    pesare contro un altro, e quindi non si scrive affatto.
    """
    from financial.models import FinancialFact

    with pytest.raises(Exception):
        FinancialFact(owner_id="u", kind="commitment", what="affitto",
                      provenance=[])


def test_the_unknowns_travel_with_the_fact():
    """Cosa non si sa e' parte del fatto, non una nota a margine."""
    fact = _fact("u", money=__import__(
        "financial.models", fromlist=["Money"],
    ).Money(), unknowns=["l'importo", "la scadenza"])
    human = fact.for_human()
    assert human["quanto"] == "importo non noto"
    assert "l'importo" in human["cosa_non_so"]


# ---------------------------------------------------------------------------
# Impegni ricorrenti, versioni, conflitti
# ---------------------------------------------------------------------------

def test_a_rent_that_goes_up_is_a_new_version_and_not_a_second_rent():
    """
    §16.B: l'affitto che aumenta non sono due affitti.

    Il fatto vecchio resta — dice cosa si pagava e fino a quando — e il nuovo
    lo nomina. Nessuno dei due e' sbagliato: si succedono.
    """
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial.models import Money
            from financial.store import FinancialStore

            store = FinancialStore(db)
            before = _fact(uid, valid_from="2026-01-01T00:00:00+00:00")
            await store.remember(before)

            after = _fact(
                uid, money=Money(amount=760, currency="EUR"),
                valid_from="2026-10-01T00:00:00+00:00",
            )
            out = await store.remember(after)

            assert out["outcome"] == "superseded"
            assert after.supersedes == before.id

            known = await store.known(uid, kinds=["commitment"])
            assert len(known) == 1, "ci sono due affitti invece di uno"
            assert known[0].money.amount == 760

            history = await store.history_of(uid, "affitto")
            assert len(history) == 2, "la versione precedente e' sparita"
            old = [h for h in history if h.id == before.id][0]
            assert old.status == "superseded"
            assert old.valid_until, "non si sa fino a quando valeva il vecchio"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_sources_that_disagree_both_stay_and_neither_is_chosen():
    """
    §16.E / §4: IL CODICE NON SCEGLIE QUALE FONTE DICE IL VERO.

    Il documento dice €900, l'email €850. Una tabella che dicesse «il
    documento vale di piu'» sarebbe una risposta permanente, invisibile e non
    discutibile a una domanda che dipende dal caso.
    """
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial.models import Money
            from financial.store import FinancialStore

            store = FinancialStore(db)
            from_document = _fact(
                uid, money=Money(amount=900, currency="EUR"),
                provenance=[_from("document", "c'e' scritto nel contratto")],
            )
            await store.remember(from_document)

            from_email = _fact(
                uid, money=Money(amount=850, currency="EUR"),
                provenance=[_from("email", "lo ha scritto il proprietario")],
            )
            out = await store.remember(from_email)

            assert out["outcome"] == "disputed"
            assert from_document.id in out["disputes"]

            known = await store.known(uid, kinds=["commitment"])
            amounts = sorted(f.money.amount for f in known)
            assert amounts == [850.0, 900.0], (
                "una delle due versioni e' stata scartata"
            )

            seen = await store.disagreements(uid)
            assert len(seen) == 1
            said_by = {v["said_by"] for v in seen[0]["versions"]}
            assert said_by == {"document", "email"}
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_fact_that_knows_less_is_not_in_disagreement_with_one_that_knows_more():
    """Non sapere l'importo non e' dire un importo diverso."""
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial.models import Money
            from financial.store import FinancialStore

            store = FinancialStore(db)
            await store.remember(_fact(uid))
            out = await store.remember(_fact(uid, money=Money()))
            assert out["outcome"] == "kept"
            assert not out["disputes"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# L'orizzonte, e quello che non contiene
# ---------------------------------------------------------------------------

def test_the_horizon_never_says_what_will_be_left():
    """
    §7/§13: UN ORIZZONTE SENZA I SUOI BUCHI E' UN PREVENTIVO.

    Sapendo +2.000 di stipendio, −700 di affitto e −305 di rata, ORA conosce
    tre movimenti. Non sa il saldo, non sa la spesa, non sa se sono tutti.
    «Ti rimarranno 995 euro» sarebbe un numero preciso e falso.
    """
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial.horizon import for_human, what_is_coming
            from financial.models import Money
            from financial.store import FinancialStore

            await _known_by_ora(db, _fact(
                uid, kind="income", what="stipendio", direction="incoming",
                money=Money(amount=2000, currency="EUR"), due_at=_soon(3),
            ))
            await _known_by_ora(db, _fact(uid, due_at=_soon(5)))
            await _known_by_ora(db, _fact(
                uid, what="rata", money=Money(amount=305, currency="EUR"),
                due_at=_soon(8),
            ))

            horizon = await what_is_coming(db, uid, days=30)
            assert len(horizon.outgoing) == 2
            assert len(horizon.incoming) == 1
            assert horizon.can_say_what_is_left is False

            said = for_human(horizon)
            assert said["posso_dire_quanto_ti_resta"] is False
            assert said["somma_di_cio_che_so_in_uscita"] == 1005.0
            assert said["cosa_non_so"], "l'orizzonte non dice cosa gli manca"
            assert any("saldo" in u for u in said["cosa_non_so"])
            blob = str(said)
            for forbidden in ("rimarranno", "rimangono", "ti resta", "995"):
                assert forbidden not in blob, (
                    f"l'orizzonte ha prodotto una previsione: «{forbidden}»"
                )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_sum_is_refused_when_one_of_the_amounts_is_unknown():
    """Una somma parziale presentata come somma e' una precisione finta."""
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial.horizon import what_is_coming
            from financial.models import Money
            from financial.store import FinancialStore

            await _known_by_ora(db, _fact(uid, due_at=_soon(4)))
            await _known_by_ora(db, _fact(
                uid, what="bolletta", money=Money(), due_at=_soon(6),
            ))

            horizon = await what_is_coming(db, uid, days=30)
            assert horizon.known_outgoing_total() is None, (
                "ha sommato lasciando fuori quello che non sa"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_recurring_commitment_without_a_day_is_still_in_the_horizon():
    """Un affitto mensile riguarda i prossimi trenta giorni anche senza il giorno."""
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial.horizon import what_is_coming
            from financial.store import FinancialStore

            await _known_by_ora(db, _fact(uid, due_at=None))
            horizon = await what_is_coming(db, uid, days=30)
            assert [f.what for f in horizon.outgoing] == ["affitto"]
            assert any("giorno esatto" in u for u in horizon.unknowns)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_something_with_no_date_and_no_recurrence_is_not_placed_in_the_period():
    """Non sapere quando cade non autorizza a metterlo qui."""
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial.horizon import what_is_coming
            from financial.store import FinancialStore

            await _known_by_ora(db, _fact(
                uid, what="tassa", cadence="unknown", due_at=None,
                recurrence=None,
            ))
            horizon = await what_is_coming(db, uid, days=30)
            assert horizon.outgoing == []
            assert any("tassa" in u for u in horizon.unknowns)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Il giudizio, e quello che il codice non decide
# ---------------------------------------------------------------------------

def test_nothing_in_the_financial_layer_decides_importance_from_an_amount():
    """
    §5/§17: L'IMPORTO NON DECIDE L'IMPORTANZA.

    Guardia strutturale su tutto il modulo: nessun confronto fra un importo e
    una costante. `if amount > 500: important = True` sarebbe una risposta
    permanente a una domanda che dipende da chi e' la persona, e sarebbe
    invisibile a chi legge la risposta.
    """
    offenders = []
    for path in sorted((HERE / "financial").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            named = ast.dump(node.left)
            if not any(
                word in named for word in ("amount", "importo", "total", "somma")
            ):
                continue
            for other in node.comparators:
                if isinstance(other, ast.Constant) and isinstance(
                    other.value, (int, float),
                ) and other.value not in (0, 1):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"l'importanza viene da una soglia in {offenders}"


def test_the_financial_layer_holds_no_thresholds_and_no_categories_table():
    """Nessun listino di categorie, nessuna scala di gravita' cablata."""
    for path in sorted((HERE / "financial").glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("important = true", "is_important", "severity =",
                          "priority_from_amount", "category_weights"):
            assert forbidden not in text, f"{path.name} contiene «{forbidden}»"


def test_an_impact_can_say_it_does_not_know():
    """
    §8: `uncertain` con cosa manca e' una risposta, non un fallimento.
    """
    from financial.models import FinancialImpact

    impact = FinancialImpact(
        owner_id="u", fact_id="fin_1", level="uncertain",
        reason="non so quanto entra ogni mese",
        missing_information=["il tuo reddito"],
    )
    assert impact.level == "uncertain"
    assert impact.missing_information == ["il tuo reddito"]


def test_an_impact_cannot_point_at_somebody_elses_goal(monkeypatch):
    """
    §8: il codice verifica l'appartenenza dei riferimenti, e solo quella.

    Il livello e la ragione sono del modello. Che un goal nominato sia di
    questa persona, no: quello e' un fatto, e un id inventato non deve
    entrare in un record che qualcuno leggera' come prova.
    """
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial import bridge
            from financial.store import FinancialStore

            store = FinancialStore(db)
            fact = _fact(uid)
            await store.remember(fact)
            await db.agent_goals.insert_one(
                {"id": "gol_mio", "owner_id": uid, "status": "active",
                 "objective": "comprare casa"},
            )

            async def answer(*a, **kw):
                return {
                    "level": "relevant", "reason": "tocca la casa",
                    "affected_goal_ids": ["gol_mio", "gol_di_un_altro"],
                    "affected_situation_ids": ["inventato"],
                    "missing_information": [],
                }

            monkeypatch.setattr(bridge, "weigh_against_their_life", answer, raising=False)
            import financial.reasoning as reasoning
            monkeypatch.setattr(reasoning, "weigh_against_their_life", answer)

            impact = await bridge.weigh(db, uid, fact.id)
            assert impact is not None
            assert impact.affected_goal_ids == ["gol_mio"]
            assert impact.affected_situation_ids == []
        finally:
            await db.agent_goals.delete_many({"owner_id": uid})
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Dalla cosa osservata al fatto
# ---------------------------------------------------------------------------

def _reply(**over):
    base = {
        "what_it_is": "commitment", "in_their_words": "bolletta della luce",
        "amount": 118.0, "currency": "EUR", "direction": "outgoing",
        "how_often": "one_time", "recurrence": None,
        "due_at": "2026-09-18T00:00:00+00:00", "occurred_at": None,
        "counterparty": None, "valid_from": None, "changes_what": "",
        "what_is_not_known": [], "reasoning": "una fattura con una scadenza",
    }
    base.update(over)
    return base


def _install_reader(monkeypatch, reply):
    import financial.reasoning as reasoning

    async def read(*a, **kw):
        return reply

    monkeypatch.setattr(reasoning, "read_financial_meaning", read)


def test_a_bill_becomes_a_future_obligation_with_its_provenance(monkeypatch):
    """§16.A: fattura luce €118, scadenza 18 settembre."""
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial import bridge
            from financial.store import FinancialStore

            _install_reader(monkeypatch, _reply())
            out = await bridge.read_money_in(
                db, uid,
                observation={"subject": "Fattura energia €118"},
                provenance=_from("email", "arrivata per email"),
                source_refs=["msg_1"],
            )
            assert out["outcome"] == "kept"

            fact = (await FinancialStore(db).known(uid))[0]
            assert fact.kind == "commitment"
            assert fact.direction == "outgoing"
            assert fact.is_future_obligation
            assert fact.money.amount == 118.0
            assert fact.provenance[0].source == "email"
            assert fact.source_refs == ["msg_1"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_newsletter_about_loans_leaves_nothing_behind(monkeypatch):
    """§16.D: nominare dei soldi non fa di una pubblicita' un impegno."""
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial import bridge
            from financial.store import FinancialStore

            _install_reader(monkeypatch, _reply(what_it_is="nothing"))
            out = await bridge.read_money_in(
                db, uid,
                observation={"subject": "Scopri i nostri prestiti"},
                provenance=_from(),
            )
            assert out["outcome"] == "nothing"
            assert await FinancialStore(db).known(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_receipt_is_a_past_event_and_makes_no_work(monkeypatch):
    """§16.C: una ricevuta e' una cosa successa, non una cosa da fare."""
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial import bridge
            from financial.horizon import what_is_coming
            from financial.store import FinancialStore

            _install_reader(monkeypatch, _reply(
                what_it_is="event", in_their_words="pagamento di 49,90",
                amount=49.9, due_at=None,
                occurred_at="2026-09-05T00:00:00+00:00",
            ))
            await bridge.read_money_in(
                db, uid, observation={"subject": "Ricevuta"},
                provenance=_from(),
            )
            fact = (await FinancialStore(db).known(uid))[0]
            assert fact.kind == "event"
            assert fact.is_future_obligation is False

            horizon = await what_is_coming(db, uid, days=30)
            assert horizon.outgoing == [], "una ricevuta e' finita fra gli impegni"

            for coll in ("agent_goals", "opportunities"):
                assert await db[coll].count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_judgement_that_did_not_arrive_is_not_a_judgement_of_nothing(monkeypatch):
    """
    Il silenzio del modello lascia il mondo com'era.

    `None` significa «non lo so»: un provider giu' o una risposta malformata
    non autorizzano nessuno a concludere che non c'era niente di economico.
    """
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial import bridge
            from financial.store import FinancialStore

            _install_reader(monkeypatch, None)
            out = await bridge.read_money_in(
                db, uid, observation={"subject": "boh"}, provenance=_from(),
            )
            assert out["outcome"] == "no_answer"
            assert out["outcome"] != "nothing"
            assert await FinancialStore(db).known(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_the_model_did_not_say_is_not_invented(monkeypatch):
    """
    §3: quello che non e' stato detto resta assente.

    Nessun campo viene riempito con uno zero, con oggi o con «una tantum»
    perche' faceva comodo avere un valore.
    """
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial import bridge
            from financial.store import FinancialStore

            _install_reader(monkeypatch, _reply(
                amount=None, currency=None, due_at=None, how_often=None,
                what_is_not_known=["quanto"],
            ))
            await bridge.read_money_in(
                db, uid, observation={"subject": "Il canone aumenta"},
                provenance=_from(),
            )
            fact = (await FinancialStore(db).known(uid))[0]
            assert fact.money.amount is None
            assert fact.money.is_known is False
            assert fact.due_at is None
            assert fact.cadence == "unknown"
            assert fact.unknowns, "non ha registrato cosa non sa"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# I confini
# ---------------------------------------------------------------------------

def test_the_financial_layer_cannot_move_money():
    """
    §12/§17: nessun pagamento, nessun bonifico, nessuna sottoscrizione.

    Guardia strutturale sull'intero modulo: non deve esistere niente che
    somigli a un attuatore finanziario, e non deve comparire `mail.send`.
    """
    for path in sorted((HERE / "financial").glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("mail.send", "def pay", "transfer(", "bonifico(",
                          "charge(", "subscribe(", "purchase(", "payment_capability"):
            assert forbidden not in text, f"{path.name} contiene «{forbidden}»"


def test_the_financial_layer_never_writes_the_life_model_directly():
    """
    §11: nessuna scrittura diretta nella memoria durevole.

    Tutto quello che deve restare passa dalla governance, come per ogni altra
    cosa. Qui si controlla che nessun file del modulo scriva su `memories` o
    `life_objects`.
    """
    for path in sorted((HERE / "financial").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("memories.insert", "memories.update",
                          "life_objects.insert", "life_objects.update",
                          "life_nodes.insert", "life_nodes.update"):
            assert forbidden not in text, f"{path.name} scrive direttamente: {forbidden}"


def test_there_is_no_finance_tab_and_no_dashboard():
    """
    §14/§17: la finanza emerge nelle superfici che ci sono.

    Nessuna sesta scheda, nessuna dashboard, nessun grafico a torta.
    """
    app = HERE.parent / "frontend" / "app"
    tabs = app / "(tabs)"
    names = {p.stem for p in tabs.glob("*.tsx")} if tabs.exists() else set()
    for forbidden in ("finanze", "finance", "wallet", "budget", "spese"):
        assert forbidden not in names, f"c'è una scheda «{forbidden}»"

    for path in list(app.glob("**/*.tsx")):
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for forbidden in ("piechart", "pie chart", "donutchart", "spesa per categoria"):
            assert forbidden not in text, f"{path.name} contiene «{forbidden}»"


def test_a_horizon_cannot_grow_a_remaining_balance():
    """
    §7/§13: la frase «ti rimarranno» non deve poter nascere per distrazione.

    `can_say_what_is_left` e' `False` per costruzione, e questa prova esiste
    per far fallire chiunque provi a renderla condizionale senza accorgersi
    di cosa sta promettendo.
    """
    from financial.models import Horizon

    source = (HERE / "financial" / "models.py").read_text(encoding="utf-8")
    body = source.split("def can_say_what_is_left", 1)[1].split("def ", 1)[0]
    assert "return False" in body, (
        "qualcuno ha reso condizionale il fatto di poter dire quanto resta"
    )

    horizon = Horizon(owner_id="u", days=30, from_day="a", to_day="b")
    assert horizon.can_say_what_is_left is False
    assert not hasattr(horizon, "remaining")
    assert not hasattr(horizon, "predicted_balance")


def test_a_rent_increase_arriving_by_email_does_not_become_a_second_rent(monkeypatch):
    """
    §16.B, dal percorso vero: «dal prossimo mese il canone passa da 700 a 760».

    Il bug che questa prova esiste per non far tornare: `changes_what` era
    nel prompt, il modello lo compilava, e il codice non lo leggeva. Il fatto
    nuovo finiva quindi nel ramo «dicono cifre diverse», e la persona si
    ritrovava due affitti vivi da 700 e da 760 — visti tutti e due
    nell'orizzonte, sommati tutti e due. Successo sull'account vero.

    «Dal prossimo mese» non e' una data, quindi `valid_from` resta vuoto: la
    successione non puo' dipendere da quello.
    """
    async def body():
        client, db = await _db()
        uid = f"fin_{uuid.uuid4().hex[:8]}"
        try:
            from financial import bridge
            from financial.horizon import what_is_coming
            from financial.store import FinancialStore

            store = FinancialStore(db)
            await store.remember(_fact(uid, valid_from="2026-01-01T00:00:00+00:00"))

            _install_reader(monkeypatch, _reply(
                what_it_is="commitment", in_their_words="affitto",
                amount=760.0, how_often="recurring", recurrence="ogni mese",
                due_at=None, valid_from=None,
                changes_what="affitto",
                what_is_not_known=["da quando esattamente"],
            ))
            out = await bridge.read_money_in(
                db, uid,
                observation={"subject": "Il canone passa da €700 a €760"},
                provenance=_from("email", "lo ha scritto il proprietario"),
            )

            assert out["outcome"] == "superseded", (
                f"un aumento è diventato «{out['outcome']}»"
            )
            assert not out["disputes"]

            live = await store.known(uid, kinds=["commitment"])
            rents = [f for f in live if f.what.strip().lower() == "affitto"]
            assert len(rents) == 1, f"ci sono {len(rents)} affitti vivi invece di uno"
            assert rents[0].money.amount == 760

            history = await store.history_of(uid, "affitto")
            assert len(history) == 2, "la versione da 700 è sparita"

            horizon = await what_is_coming(db, uid, days=30)
            assert horizon.known_outgoing_total() == 760.0, (
                "l'orizzonte somma due volte lo stesso affitto"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_the_judgement_says_it_replaces_is_actually_read():
    """
    Guardia strutturale: `changes_what` non deve tornare a essere ignorato.

    Era nel prompt e non nel codice — il tipo di disallineamento che non
    rompe niente, non fallisce nessun test, e produce due affitti.
    """
    prompt = (HERE / "financial" / "reasoning.py").read_text(encoding="utf-8")
    bridge = (HERE / "financial" / "bridge.py").read_text(encoding="utf-8")
    store = (HERE / "financial" / "store.py").read_text(encoding="utf-8")
    assert "changes_what" in prompt
    assert "changes_what" in bridge, "il ponte non legge cosa il giudizio sostituisce"
    assert "replaces" in store, "l'archivio non sa cosa sta sostituendo"
