"""
V3.11 Sprint 4 — un movimento e' un'osservazione, il significato viene dopo.

    IL CODICE NORMALIZZA. L'AI INTERPRETA.
    LA GOVERNANCE DECIDE COSA DIVENTA CONOSCENZA.

`-118,42 € · ENERGIA ITALIA S.P.A.` non e' una bolletta. E' una riga che dice
che sono usciti centodiciotto euro e quarantadue verso qualcuno che si chiama
cosi'. Che sia una bolletta e' un'interpretazione, e puo' essere sbagliata: un
rimborso, un conguaglio, un pagamento fatto per un'altra persona.

Quasi tutto quello che c'e' qui sotto serve a tenere ferma quella distinzione
mentre il sistema cresce — perche' la scorciatoia (una parola nella
descrizione, una soglia sul numero di ripetizioni) e' sempre a una riga di
distanza, funziona quasi sempre, e quando sbaglia lo fa con sicurezza.
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


def _code_only(path: Path) -> str:
    """Il codice senza le sue spiegazioni — vedi la suite dello Sprint 3."""
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
    for coll in ("financial_facts", "financial_impacts", "financial_observations",
                 "memories", "agent_goals", "life_objects", "opportunities",
                 "ingestion_events"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


BASE = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _obs(uid, n, *, amount=-760.0, who="BONIFICO A ROSSI MARCO", every=30):
    from financial.observation import BankObservation

    return BankObservation(
        owner_id=uid, account_ref="acc_1", transaction_ref=f"tx_{uid}_{n}",
        booked_at=(BASE + timedelta(days=every * n)).isoformat(),
        amount=amount, direction="outgoing", raw_description=who,
        provenance={"source": "bank"},
    )


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
    """Il giudizio, sostituito: quello che si prova qui e' il percorso."""
    import financial.movements as movements

    async def read(*a, **kw):
        return answer

    monkeypatch.setattr(
        "financial.reasoning.read_a_movement", read, raising=True,
    )
    return movements


# ---------------------------------------------------------------------------
# Il codice conta. Non conclude.
# ---------------------------------------------------------------------------

def test_the_arithmetic_counts_and_says_nothing_about_meaning():
    """
    §3: sei volte a trenta giorni e' un fatto. «E' un abbonamento» e' un giudizio.

    Quello che il codice produce sono intervalli, mediane e scarti. Nessun
    campo di questa struttura dice cosa la cosa sia, e non deve poterlo dire:
    un affitto mensile e una spesa quindicinale hanno gli stessi numeri.
    """
    from financial.observation import Pattern, features_of

    uid = "u"
    history = [_obs(uid, n) for n in range(6)]
    pattern = features_of(_obs(uid, 6), history)

    assert pattern.times_seen == 6
    assert pattern.typical_gap_days == 30.0
    assert pattern.gap_regularity_days == 0.0
    assert pattern.same_counterparty_every_time is True
    assert pattern.amount_change_from_usual == 0.0

    # Nessun campo che sia una categoria, un tipo o un verdetto.
    for forbidden in ("category", "kind", "label", "is_recurring", "type"):
        assert forbidden not in Pattern.model_fields, (
            f"l'aritmetica ha un campo che conclude: «{forbidden}»"
        )


def test_a_changed_amount_is_measured_not_judged():
    """Sessanta euro in piu' e' una misura. Se conti, lo dice il giudizio."""
    from financial.observation import features_of

    uid = "u"
    history = [_obs(uid, n) for n in range(6)]
    pattern = features_of(_obs(uid, 7, amount=-820.0), history)
    assert pattern.amount_change_from_usual == 60.0


def test_a_bank_observation_has_nowhere_to_put_a_category():
    """
    §10: UNA TRANSAZIONE E' UN'OSSERVAZIONE.

    Se il modello avesse un campo per la categoria, prima o poi qualcuno lo
    riempirebbe con una regola, e la regola diventerebbe la verita' senza che
    nessuno l'abbia decisa.
    """
    from financial.observation import BankObservation

    fields = set(BankObservation.model_fields)
    for forbidden in ("category", "kind", "label", "merchant_category",
                      "is_recurring", "interpreted_kind"):
        assert forbidden not in fields, (
            f"l'osservazione bancaria ha un campo interpretativo: «{forbidden}»"
        )
    # E ha invece tutto quello che serve per essere una prova.
    for required in ("account_ref", "transaction_ref", "booked_at", "amount",
                     "currency", "direction", "raw_description", "provenance"):
        assert required in fields, f"manca «{required}» al contratto"


# ---------------------------------------------------------------------------
# Lo stesso movimento, letto in due contesti
# ---------------------------------------------------------------------------

def test_a_recurring_charge_nobody_can_name_stays_unnamed(monkeypatch):
    """
    §13.G: «-14,99 € ogni mese» senza altro contesto resta non identificato.

    Ed e' la risposta utile. «Un addebito ricorrente che non ho ancora
    identificato» dice a una persona qualcosa di vero su cui puo' agire; una
    categoria inventata le dice una cosa falsa con sicurezza.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from financial.store import FinancialStore

            movements = _install(monkeypatch, _answer())
            for n in range(4):
                await movements.look_at_a_movement(
                    db, _obs(uid, n, amount=-14.99, who="ADDEBITO SEPA 4411"),
                )
            out = await movements.look_at_a_movement(
                db, _obs(uid, 4, amount=-14.99, who="ADDEBITO SEPA 4411"),
            )

            assert out["outcome"] == "seen_not_understood"
            assert "non ho ancora identificato" in out["how_to_say_it"]
            assert "14,99" in out["how_to_say_it"]
            # E niente e' entrato in quello che ORA sa.
            assert await FinancialStore(db).known(uid) == []
            assert await db.memories.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_movement_reads_differently_when_the_context_changes(monkeypatch):
    """
    §13.E/F: la stessa riga, due esiti, e la differenza e' quello che c'e' intorno.

    Senza contesto: un bonifico ricorrente non identificato. Con l'email che
    dice che il canone e' 760 e una situazione «Casa»: un impegno con un nome.
    Il codice e' lo stesso; a cambiare e' cosa gli e' stato messo davanti.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from financial.store import FinancialStore

            movements = _install(monkeypatch, _answer())
            blind = await movements.look_at_a_movement(db, _obs(uid, 1))
            assert blind["outcome"] == "seen_not_understood"
            assert await FinancialStore(db).known(uid) == []

            await db.life_objects.insert_one(
                {"id": "lo_casa", "user_id": uid, "title": "Casa a Tarquinia",
                 "type": "HOME", "status": "active"},
            )
            _install(monkeypatch, _answer(
                interpreted_kind="commitment", likely_label="affitto",
                certainty="high", should_persist=True, should_ask_user=False,
                linked_situations=["lo_casa", "lo_di_un_altro"],
                missing_information=[],
            ))
            seeing = await movements.look_at_a_movement(db, _obs(uid, 2))

            assert seeing["outcome"] in ("kept", "superseded")
            assert seeing["what"] == "affitto"
            # Solo i riferimenti che sono davvero di questa persona.
            assert seeing["linked_situations"] == ["lo_casa"]

            fact = (await FinancialStore(db).known(uid))[0]
            assert fact.provenance[0].source == "bank"
            assert fact.source_refs == [f"tx_{uid}_2"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_judgement_staying_silent_is_not_a_judgement_of_nothing(monkeypatch):
    """Provider giu' non vuol dire «non era niente». L'osservazione resta."""
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observation import ObservationStore

            movements = _install(monkeypatch, None)
            out = await movements.look_at_a_movement(db, _obs(uid, 1))
            assert out["outcome"] == "no_answer"
            # La riga e' stata vista: e' successa, ed e' un fatto.
            assert len(await ObservationStore(db).history(uid)) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_transaction_read_twice_is_one_observation(monkeypatch):
    """Un estratto conto riletto non deve raddoppiare la storia."""
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observation import ObservationStore

            movements = _install(monkeypatch, _answer())
            await movements.look_at_a_movement(db, _obs(uid, 1))
            await movements.look_at_a_movement(db, _obs(uid, 1))
            assert len(await ObservationStore(db).history(uid)) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_single_purchase_however_large_is_not_a_thing_ora_remembers(monkeypatch):
    """
    §11: `should_persist` non e' una soglia sull'importo.

    Una spesa una tantum da quattromila euro non e' una parte stabile della
    vita economica di qualcuno: e' una cosa successa. Il giudizio lo dice, e
    il codice lo rispetta senza guardare la cifra.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from financial.store import FinancialStore

            movements = _install(monkeypatch, _answer(
                interpreted_kind="event", likely_label="acquisto",
                pattern_status="one_off", certainty="high",
                should_persist=False,
            ))
            out = await movements.look_at_a_movement(
                db, _obs(uid, 1, amount=-4000.0, who="POS ARREDAMENTI"),
            )
            assert out["outcome"] == "seen_not_understood"
            assert await FinancialStore(db).known(uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Il collegamento alla situazione
# ---------------------------------------------------------------------------

def test_a_structured_link_wins_over_a_name_that_happens_to_match():
    """
    §5: UN NOME NON E' UNA RELAZIONE.

    Il preventivo del notaio appartiene all'acquisto della casa perche' il
    giudizio ce lo ha messo, non perche' contiene la parola «casa». E una
    bolletta «di casa» non appartiene all'acquisto solo per come si chiama.
    """
    async def body():
        client, db = await _db()
        uid = f"lk_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import propose
            from financial.models import FinancialFact, Money, Provenance
            from financial.store import FinancialStore
            from routers.financial import _narrow
            from financial.knowledge import what_ora_knows

            await db.life_objects.insert_one(
                {"id": "lo_acquisto", "user_id": uid,
                 "title": "Acquisto di una nuova casa", "type": "HOME",
                 "status": "active"},
            )

            def fact(what, refs):
                return FinancialFact(
                    owner_id=uid, kind="commitment", what=what,
                    money=Money(amount=4000, currency="EUR"),
                    direction="outgoing", cadence="recurring",
                    recurrence="ogni mese", about_refs=refs,
                    provenance=[Provenance(source="document",
                                           how_directly="c'è nel preventivo")],
                )

            store = FinancialStore(db)
            belongs = fact("preventivo del notaio", ["lo_acquisto"])
            await store.remember(belongs)
            await propose(db, belongs)

            # Si chiama «casa» e non c'entra con l'acquisto.
            stranger = fact("bolletta di casa", [])
            await store.remember(stranger)
            await propose(db, stranger)

            out = await _narrow(
                db, uid, await what_ora_knows(db, uid), "acquisto",
            )
            assert out["matched_by"] == "situation"
            names = [r["cosa"] for r in out["so"]]
            assert names == ["preventivo del notaio"], names
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_name_is_only_a_fallback_and_says_so():
    """Quando non c'e' nessun collegamento strutturato, il ripiego si dichiara."""
    async def body():
        client, db = await _db()
        uid = f"lk_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import propose
            from financial.knowledge import what_ora_knows
            from financial.models import FinancialFact, Money, Provenance
            from financial.store import FinancialStore
            from routers.financial import _narrow

            loose = FinancialFact(
                owner_id=uid, kind="commitment", what="affitto casa",
                money=Money(amount=700, currency="EUR"), direction="outgoing",
                cadence="recurring", recurrence="ogni mese",
                provenance=[Provenance(source="document",
                                       how_directly="c'è nel contratto")],
            )
            await FinancialStore(db).remember(loose)
            await propose(db, loose)

            out = await _narrow(db, uid, await what_ora_knows(db, uid), "casa")
            assert out["matched_by"] == "name"
            assert [r["cosa"] for r in out["so"]] == ["affitto casa"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Home: una cosa irrisolta, una presenza sola
# ---------------------------------------------------------------------------

async def _pending_rent(db, uid):
    """Un affitto saputo e una versione letta che aspetta una parola."""
    from financial.durable import propose
    from financial.models import FinancialFact, Money, Provenance
    from financial.store import FinancialStore

    store = FinancialStore(db)

    def rent(amount, source, how):
        return FinancialFact(
            owner_id=uid, kind="commitment", what="affitto",
            money=Money(amount=amount, currency="EUR"), direction="outgoing",
            cadence="recurring", recurrence="ogni mese",
            provenance=[Provenance(source=source, how_directly=how)],
        )

    known = rent(700, "document", "c'è scritto nel contratto")
    await store.remember(known)
    await propose(db, known)

    read = rent(760, "email", "lo ha scritto il proprietario")
    await store.remember(read)
    await propose(db, read)


def test_one_unresolved_money_question_is_one_thing_on_the_screen():
    """
    §6: UNA COSA IRRISOLTA, UNA PRESENZA SOLA.

    «L'affitto è €760?» e «ho due cifre diverse per l'affitto» sono la stessa
    cosa detta due volte: la persona ne vede due e pensa di avere due
    problemi. Si tiene la domanda, perche' e' quella risolvibile in un
    secondo.
    """
    async def body():
        client, db = await _db()
        uid = f"hm_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.financial import load_financial_context

            await _pending_rent(db, uid)
            items, _ = await load_financial_context(db, uid)
            # Le cose da risolvere, non tutto quello che nomina l'affitto:
            # l'orizzonte lo elenca fra le uscite del mese, ed e' giusto che
            # lo faccia — non e' una seconda domanda.
            unresolved = [i for i in items if i.type == "verify"]
            assert len(unresolved) == 1, (
                f"la stessa cosa irrisolta compare {len(unresolved)} volte: "
                f"{[i.title for i in unresolved]}"
            )
            assert "€760" in unresolved[0].title
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_question_can_be_answered_where_it_is_read():
    """§7: sì, no, oppure parlarne — sulla carta stessa."""
    async def body():
        client, db = await _db()
        uid = f"hm_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.financial import load_financial_context

            await _pending_rent(db, uid)
            items, _ = await load_financial_context(db, uid)
            card = [i for i in items if i.subtype == "financial_confirmation"][0]
            labels = [a.label for a in card.actions]
            assert labels == ["Sì", "No", "Approfondisci con ORA"]
            assert card.actions[0].params["confirmed"] is True
            assert card.actions[1].params["confirmed"] is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_answering_yes_from_home_goes_through_the_same_door():
    """
    §7: LA STESSA DOMANDA, RISOLTA UNA VOLTA SOLA.

    Un sì dato in Home e un sì detto a ORA devono chiudere la stessa cosa. Se
    fossero due percorsi, uno dei due prima o poi direbbe una cosa diversa.
    """
    async def body():
        client, db = await _db()
        uid = f"hm_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts
            from home.adapters.financial import load_financial_context
            from home.service import HomeService

            await _pending_rent(db, uid)
            out = await HomeService(db).apply_action(
                uid, item_id="ask:affitto", action="money_yes",
            )
            assert out["ok"] is True and out["confirmed"] is True

            known = await governed_facts(db, uid)
            rents = [f for f in known if f.what == "affitto"]
            assert len(rents) == 1 and rents[0].money.amount == 760

            items, _ = await load_financial_context(db, uid)
            assert not [i for i in items if i.subtype == "financial_confirmation"], (
                "la domanda è ancora sullo schermo dopo essere stata risolta"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_answering_no_from_home_closes_it_and_keeps_what_was_known():
    """§7: e un no chiude la stessa domanda, lasciando le cose come stavano."""
    async def body():
        client, db = await _db()
        uid = f"hm_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts
            from home.adapters.financial import load_financial_context
            from home.service import HomeService

            await _pending_rent(db, uid)
            out = await HomeService(db).apply_action(
                uid, item_id="ask:affitto", action="money_no",
            )
            assert out["ok"] is True and out["confirmed"] is False

            known = await governed_facts(db, uid)
            assert [f.money.amount for f in known if f.what == "affitto"] == [700.0]

            items, _ = await load_financial_context(db, uid)
            assert not [i for i in items if i.subtype == "financial_confirmation"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_answering_creates_no_work():
    """Rispondere a una domanda non e' cominciare qualcosa."""
    async def body():
        client, db = await _db()
        uid = f"hm_{uuid.uuid4().hex[:8]}"
        try:
            from home.service import HomeService

            await _pending_rent(db, uid)
            await HomeService(db).apply_action(
                uid, item_id="ask:affitto", action="money_yes",
            )
            for coll in ("agent_goals", "opportunities"):
                assert await db[coll].count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_money_is_written_the_way_a_person_would_say_it():
    """§9: «Affitto casa — €700 al mese», non «affitto casa · €700 · ogni mese»."""
    from home.adapters.financial import _as_a_person_would_say

    said = _as_a_person_would_say("affitto casa · €700 · ogni mese")
    assert said.startswith("Affitto casa")
    assert "·" not in said
    assert "€700" in said


# ---------------------------------------------------------------------------
# Le guardie
# ---------------------------------------------------------------------------

def test_no_line_of_code_decides_what_a_movement_is_from_its_description():
    """
    §12: nessuna parola chiave decide una categoria.

    La scorciatoia e' sempre a una riga di distanza — `if "ENERGIA" in
    description` — funziona quasi sempre, e quando sbaglia lo fa con
    sicurezza. Questa guardia cerca proprio quella riga.
    """
    words = ("affitto", "bolletta", "canone", "stipendio", "abbonamento",
             "assicurazione", "energia", "netflix", "mutuo", "rata")
    for path in sorted((HERE / "financial").glob("*.py")):
        code = _code_only(path)
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            blob = ast.dump(node).lower()
            for word in words:
                assert f"'{word}'" not in blob, (
                    f"{path.name}:{node.lineno} decide da una parola: «{word}»"
                )


def test_no_threshold_turns_a_count_into_a_category():
    """
    §12: `if times_seen >= 3: recurring` sarebbe il codice che conclude.

    Le feature numeriche si possono calcolare; la parola che le riassume no.
    """
    for path in sorted((HERE / "financial").glob("*.py")):
        tree = ast.parse(_code_only(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            # `len(gaps) > 1` e' aritmetica — servono due intervalli per
            # calcolare uno scarto — e non decide niente su cosa una cosa
            # sia. Quello che questa guardia cerca e' un conteggio messo a
            # confronto con una soglia per concluderne un significato.
            if isinstance(node.left, ast.Call):
                continue
            left = ast.dump(node.left).lower()
            if not any(
                w in left for w in ("times_seen", "recurring_count",
                                    "regularity", "amounts_seen")
            ):
                continue
            for other in node.comparators:
                assert not (
                    isinstance(other, ast.Constant)
                    and isinstance(other.value, (int, float))
                ), f"{path.name}:{node.lineno} conclude da un conteggio"


def test_the_interpretation_vocabulary_belongs_to_the_judgement():
    """
    §11: il codice valida le parole, non le sceglie.

    Le parole ammesse stanno in una tupla e vengono confrontate con quello
    che il giudizio ha risposto. Da nessuna parte il codice ne assegna una
    guardando i dati.
    """
    reasoning = _code_only(HERE / "financial" / "reasoning.py")
    assert "INTERPRETED_KINDS" in reasoning
    assert "not in INTERPRETED_KINDS" in reasoning
    movements = _code_only(HERE / "financial" / "movements.py")
    # `movements` legge la risposta; non la costruisce.
    # `ast.unparse` normalizza le virgolette: si cerca la forma che produce.
    assert "answer['interpreted_kind']" in movements, (
        "il ponte non legge la parola dal giudizio"
    )
    assert "interpreted_kind'] = '" not in movements, (
        "il codice assegna da se' il tipo di un movimento"
    )


def test_a_movement_never_becomes_knowledge_without_governance():
    """§10: osservazione → giudizio → candidato → governance. Mai una scorciatoia."""
    movements = _code_only(HERE / "financial" / "movements.py")
    assert "propose(" in movements
    for forbidden in ("memories.insert", "memories.update_one",
                      "memories.replace_one"):
        assert forbidden not in movements


def test_nothing_here_can_move_money():
    """Nessun attuatore, nessuna scrittura bancaria, nessun mail.send."""
    for path in sorted((HERE / "financial").glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("mail.send", "def pay", "transfer(", "charge(",
                          "purchase(", "bonifico(", "initiate_payment",
                          "bank_write", "post_transaction"):
            assert forbidden not in text, f"{path.name} contiene «{forbidden}»"


def test_there_is_still_no_sixth_tab():
    """§14 di sempre: le cinque schede restano cinque."""
    tabs = HERE.parent / "frontend" / "app" / "(tabs)"
    names = {p.stem.lower() for p in tabs.glob("*.tsx")} if tabs.exists() else set()
    for forbidden in ("finanze", "finance", "wallet", "budget", "spese",
                      "transazioni"):
        assert forbidden not in names, f"c'è una scheda «{forbidden}»"


def test_the_last_thing_on_a_screen_is_reachable():
    """
    §8: L'ULTIMA RIGA DI UNA SCHERMATA DEVE ESSERE RAGGIUNGIBILE.

    La barra in basso galleggia sopra il contenuto: un `paddingBottom` fisso
    la ignora, e su un iPhone con la barra di sistema l'ultimo elemento
    finisce sotto due volte.
    """
    for name in ("app/life-area/[areaId].tsx", "app/(tabs)/index.tsx"):
        screen = (HERE.parent / "frontend" / name).read_text(encoding="utf-8")
        assert "useAmbientInset" in screen, f"{name} non tiene conto della barra"
        assert "ambient.paddingBottom" in screen, (
            f"{name} non applica lo spazio in fondo"
        )


def test_a_guess_never_enters_the_record_however_plausible(monkeypatch):
    """
    Trovato dal gate reale: il giudizio ha battezzato «Abbonamento mensile»
    un addebito di 14,99 € di cui non sapeva niente.

        UN NOME DETTO A META' NON E' UN NOME.

    Poteva essere una polizza, una quota associativa, un addebito che
    qualcun altro ha attivato sulla sua carta. La regolarita' e l'importo non
    dicono cosa una cosa sia — e un nome plausibile, letto da una persona,
    diventa un nome certo.

    Questo controllo non decide *cosa* sia: decide che chi non e' sicuro
    riferisca quello che ha visto invece di battezzarlo.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from financial.store import FinancialStore

            movements = _install(monkeypatch, _answer(
                interpreted_kind="commitment",
                likely_label="Abbonamento mensile",
                certainty="medium", should_persist=True,
                pattern_status="recurring",
            ))
            out = await movements.look_at_a_movement(
                db, _obs(uid, 1, amount=-14.99, who="ADDEBITO SEPA 4411"),
            )

            assert out["outcome"] == "seen_not_understood"
            assert out["why_not_kept"] == "il giudizio non e' abbastanza sicuro"
            assert "non ho ancora identificato" in out["how_to_say_it"]
            assert await FinancialStore(db).known(uid) == []

            # E con la certezza, la stessa risposta entra.
            _install(monkeypatch, _answer(
                interpreted_kind="commitment", likely_label="affitto",
                certainty="high", should_persist=True,
                pattern_status="recurring",
            ))
            out = await movements.look_at_a_movement(db, _obs(uid, 2))
            assert out["outcome"] in ("kept", "already_known")
            assert out["what"] == "affitto"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_fact_read_every_month_stays_one_fact():
    """
    Trovato dal gate reale: tre letture dello stesso affitto, tre fatti.

        LO STESSO FATTO, RILETTO, RESTA UNO.

    Un movimento ricorrente produce ogni mese lo stesso fatto — stesso nome,
    stesso importo, stessa cadenza. Senza raccoglierli, l'orizzonte li sommava
    tutti e presentava un affitto pagato tre volte.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from financial.models import FinancialFact, Money, Provenance
            from financial.store import FinancialStore

            store = FinancialStore(db)

            def rent():
                return FinancialFact(
                    owner_id=uid, kind="commitment", what="affitto",
                    money=Money(amount=760, currency="EUR"),
                    direction="outgoing", cadence="recurring",
                    recurrence="ogni mese",
                    provenance=[Provenance(source="bank",
                                           how_directly="l'ho visto sul conto")],
                )

            first = await store.remember(rent())
            again = await store.remember(rent())
            third = await store.remember(rent())

            assert first["outcome"] == "kept"
            assert again["outcome"] == "already_known"
            assert third["outcome"] == "already_known"
            assert again["fact_id"] == first["fact_id"]

            known = await store.known(uid)
            assert len(known) == 1, f"ci sono {len(known)} affitti invece di uno"

            # E l'orizzonte non lo somma tre volte.
            from financial.horizon import what_is_coming

            horizon = await what_is_coming(db, uid, days=30)
            assert horizon.known_outgoing_total() == 760.0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_different_amount_is_still_a_change_and_not_a_repeat():
    """La raccolta non deve inghiottire un aumento."""
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from financial.models import FinancialFact, Money, Provenance
            from financial.store import FinancialStore

            store = FinancialStore(db)

            def rent(amount):
                return FinancialFact(
                    owner_id=uid, kind="commitment", what="affitto",
                    money=Money(amount=amount, currency="EUR"),
                    direction="outgoing", cadence="recurring",
                    recurrence="ogni mese",
                    provenance=[Provenance(source="bank",
                                           how_directly="l'ho visto sul conto")],
                )

            await store.remember(rent(760))
            out = await store.remember(rent(820))
            assert out["outcome"] != "already_known", (
                "un aumento è stato scambiato per una rilettura"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
