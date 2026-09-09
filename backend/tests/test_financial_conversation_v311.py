"""
V3.11 Sprint 3 — dire quello che si sa, come lo si sa.

    SO · HO LETTO · DEVO CHIEDERTELO

E' la distinzione che rende onesto tutto quello che c'e' sotto. «Il tuo
affitto e' 760» detto quando 760 e' soltanto una riga letta in un'email e'
una bugia con l'aria di un servizio — e la differenza fra le due frasi non
puo' dipendere da come il modello si sente quel giorno.
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
    """
    Il codice senza le sue spiegazioni.

    Le guardie strutturali cercano frasi che non devono esistere — «ti
    rimarranno», un saldo previsto — e quelle stesse frasi sono scritte nei
    commenti e nelle docstring che spiegano perché sono vietate. Cercarle nel
    sorgente grezzo farebbe fallire il file proprio perché è ben spiegato.
    """
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
    for coll in ("financial_facts", "financial_impacts", "memories",
                 "agent_goals", "life_objects", "opportunities"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


def _from(source="document", how="c'è scritto nel contratto"):
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


async def _ora_knows(db, fact):
    """Quello che ORA sa: osservato e promosso."""
    from financial.durable import propose
    from financial.store import FinancialStore

    await FinancialStore(db).remember(fact)
    return await propose(db, fact)


async def _ora_only_read(db, fact):
    """Quello che ORA ha letto e non puo' credere da sola."""
    from financial.durable import propose
    from financial.store import FinancialStore

    await FinancialStore(db).remember(fact)
    out = await propose(db, fact)
    assert out["decision"] == "CLARIFY", (
        f"questa fonte non doveva bastare da sola: {out}"
    )
    return out


# ---------------------------------------------------------------------------
# I tre stati
# ---------------------------------------------------------------------------

def test_what_ora_knows_and_what_it_only_read_are_never_the_same_list():
    """
    §3: la distinzione e' il cuore.

    Un contratto fa sapere; un'email fa leggere. Le due cose escono da porte
    diverse, e quella letta porta con se' da dove viene — senza, «ho letto» e
    «so» ridiventano la stessa frase alla prima rilettura.
    """
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from financial.knowledge import what_ora_knows
            from financial.models import Money

            await _ora_knows(db, _fact(uid))
            await _ora_only_read(db, _fact(
                uid, what="bolletta della luce",
                money=Money(amount=118, currency="EUR"),
                cadence="recurring", recurrence="ogni due mesi",
                provenance=[_from("email", "lo ha scritto il fornitore")],
            ))

            said = await what_ora_knows(db, uid)

            assert [r["cosa"] for r in said["so"]] == ["affitto"]
            assert [r["cosa"] for r in said["ho_letto"]] == ["bolletta della luce"]
            assert said["ho_letto"][0]["come_lo_so"], (
                "quello che è stato solo letto non dice da dove viene"
            )
            assert [r["cosa"] for r in said["devo_chiederti"]] == [
                "bolletta della luce",
            ]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_observed_version_does_not_replace_the_known_one_in_what_ora_says():
    """
    §3: finche' la governance non lo consente, l'affitto resta quello.

    Il caso vero: contratto 700, email che dice 760. ORA deve poter dire
    tutte e due le cose — «finora so 700, ho letto 760, non l'ho dato per
    certo» — e non deve poter dire «il tuo affitto e' 760».
    """
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from financial.knowledge import what_ora_knows
            from financial.models import Money

            await _ora_knows(db, _fact(uid))
            await _ora_only_read(db, _fact(
                uid, money=Money(amount=760, currency="EUR"),
                provenance=[_from("email", "lo ha scritto il proprietario")],
            ))

            said = await what_ora_knows(db, uid)
            known = {r["cosa"]: r["quanto"] for r in said["so"]}
            assert known["affitto"] == "€700", (
                "quello che ORA afferma è cambiato senza una conferma"
            )
            asked = {r["cosa"]: r for r in said["devo_chiederti"]}
            assert asked["affitto"]["quanto"] == "€760"
            assert asked["affitto"]["invece_di"] == "€700", (
                "la domanda non dice cosa cambierebbe"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Chiudere la domanda
# ---------------------------------------------------------------------------

def test_a_yes_makes_what_was_read_become_what_ora_knows():
    """
    §4: un si' chiude la domanda e cambia quello che ORA sa.

    Senza consumare un modello: il contesto e' univoco, e chiedere a un
    giudizio di interpretare un «sì» sarebbe pagare per sapere una cosa che
    si sa gia'.
    """
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts
            from financial.knowledge import resolve_open_question, what_ora_knows
            from financial.models import Money

            await _ora_knows(db, _fact(uid))
            await _ora_only_read(db, _fact(
                uid, money=Money(amount=760, currency="EUR"),
                provenance=[_from("email", "lo ha scritto il proprietario")],
            ))

            out = await resolve_open_question(db, uid, about="affitto", confirmed=True)
            assert out["resolved"] is True and out["confirmed"] is True
            assert out["in_life_model"] is True, out

            known = await governed_facts(db, uid)
            rents = [f for f in known if f.what == "affitto"]
            assert len(rents) == 1, f"ci sono {len(rents)} affitti dopo la conferma"
            assert rents[0].money.amount == 760

            said = await what_ora_knows(db, uid)
            assert not [r for r in said["devo_chiederti"] if r["cosa"] == "affitto"], (
                "la domanda è ancora aperta dopo essere stata risolta"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_no_closes_the_same_question_and_keeps_what_was_known():
    """
    §4: un no non cancella l'osservazione — e' vero che quel messaggio lo diceva.

    Quello che era stato letto resta nel registro con la sua provenienza; la
    conoscenza precedente resta quella corrente; la domanda si chiude lo
    stesso, perche' e' la stessa domanda e non deve tornare a chiedere.
    """
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts
            from financial.knowledge import resolve_open_question, what_ora_knows
            from financial.models import Money

            await _ora_knows(db, _fact(uid))
            await _ora_only_read(db, _fact(
                uid, money=Money(amount=760, currency="EUR"),
                provenance=[_from("email", "lo ha scritto il proprietario")],
            ))

            out = await resolve_open_question(db, uid, about="affitto", confirmed=False)
            assert out["resolved"] is True and out["confirmed"] is False

            known = await governed_facts(db, uid)
            rents = [f for f in known if f.what == "affitto"]
            assert len(rents) == 1
            assert rents[0].money.amount == 700, "il no ha cambiato quello che ORA sa"

            said = await what_ora_knows(db, uid)
            assert not [r for r in said["devo_chiederti"] if r["cosa"] == "affitto"]

            # L'osservazione resta: e' un fatto che quel messaggio lo diceva.
            row = await db.financial_facts.find_one(
                {"owner_id": uid, "governance_decision": "DECLINED_BY_USER"},
                {"_id": 0},
            )
            assert row is not None
            assert row["provenance"], "il rifiuto ha cancellato la provenienza"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_answering_a_question_creates_no_work():
    """§4: NON CREARE UN NUOVO GOAL. Rispondere non e' cominciare qualcosa."""
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from financial.knowledge import resolve_open_question
            from financial.models import Money

            await _ora_knows(db, _fact(uid))
            await _ora_only_read(db, _fact(
                uid, money=Money(amount=760, currency="EUR"),
                provenance=[_from("email", "lo ha scritto il proprietario")],
            ))
            await resolve_open_question(db, uid, about="affitto", confirmed=True)

            for coll in ("agent_goals", "opportunities"):
                assert await db[coll].count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_question_nobody_asked_cannot_be_answered():
    """Confermare una cosa che non era in sospeso non deve fare niente."""
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from financial.knowledge import resolve_open_question

            out = await resolve_open_question(
                db, uid, about="mutuo", confirmed=True,
            )
            assert out["resolved"] is False
            assert await db.memories.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Il tool della conversazione
# ---------------------------------------------------------------------------

def test_the_conversation_tool_hands_over_the_three_states_separately():
    """
    §2: un tool solo, e la divisione la porta lui.

    Se le tre categorie arrivassero appiattite, la differenza fra affermare e
    riferire dovrebbe rifarla il modello a ogni turno — e a un certo punto,
    in fondo a una conversazione lunga, non la rifa'.
    """
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import financial_caps
            from financial.models import Money

            await _ora_knows(db, _fact(uid))
            await _ora_only_read(db, _fact(
                uid, money=Money(amount=760, currency="EUR"),
                provenance=[_from("email", "lo ha scritto il proprietario")],
            ))

            obs = await financial_caps.what_do_i_know_about_money(
                {}, {"user_id": uid, "db": db},
            )
            assert obs.status == "ok"
            payload = obs.payload
            assert [r["cosa"] for r in payload["what_ora_knows"]] == ["affitto"]
            assert payload["what_needs_their_word"]
            assert payload["what_is_coming"]["posso_dire_quanto_ti_resta"] is False
            # La regola viaggia col dato, non solo nel prompt di sistema.
            assert "come lo sai" in payload["how_to_say_it"].lower()
            assert "saldo" in payload["how_to_say_it"].lower()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_tool_can_narrow_to_one_thing():
    """§2/§6: «cosa sai delle spese per la casa» non deve tornare tutto."""
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import financial_caps
            from financial.models import Money

            await _ora_knows(db, _fact(uid, what="mutuo casa"))
            await _ora_knows(db, _fact(
                uid, what="palestra", money=Money(amount=40, currency="EUR"),
            ))

            obs = await financial_caps.what_do_i_know_about_money(
                {"about": "casa"}, {"user_id": uid, "db": db},
            )
            assert [r["cosa"] for r in obs.payload["what_ora_knows"]] == ["mutuo casa"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_tool_never_confirms_on_the_persons_behalf():
    """
    §4: una conferma che non e' stata data e' il modo in cui una cosa letta
    diventa una cosa creduta.
    """
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import financial_caps

            obs = await financial_caps.confirm_money_question(
                {"about": "affitto"}, {"user_id": uid, "db": db},
            )
            assert obs.status == "failed"
            assert obs.payload["reason"] == "INVALID_INPUT"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_tool_says_plainly_when_it_knows_nothing():
    """Non sapere niente e' una risposta, e va detta come tale."""
    async def body():
        client, db = await _db()
        uid = f"kn_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import financial_caps

            obs = await financial_caps.what_do_i_know_about_money(
                {}, {"user_id": uid, "db": db},
            )
            assert obs.payload["nothing_known"] is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Le guardie
# ---------------------------------------------------------------------------

def test_the_conversation_reads_the_governed_model_and_not_the_journal():
    """
    §2: NON INTERROGARE `financial_facts` COME SE FOSSE VERITA' FINALE.
    """
    tool = (
        HERE / "conversation_engine/ai_core/tools/financial_caps.py"
    ).read_text(encoding="utf-8")
    assert "what_ora_knows" in tool
    for forbidden in ("financial_facts", "FinancialStore("):
        assert forbidden not in tool, (
            f"il tool legge il registro direttamente: «{forbidden}»"
        )


def test_nothing_in_the_financial_layer_can_state_a_remaining_balance():
    """§5: NO FALSO SALDO — nemmeno per distrazione."""
    for path in sorted((HERE / "financial").glob("*.py")):
        # Solo il codice: la frase compare nei commenti e nelle docstring che
        # spiegano perché non deve esistere, ed è giusto che sia scritta lì.
        code = _code_only(path).lower()
        for forbidden in ("rimarranno", "ti resta", "remaining_balance",
                          "predicted_balance", "saldo_previsto"):
            assert forbidden not in code, f"{path.name} contiene «{forbidden}»"
    tool = _code_only(
        HERE / "conversation_engine/ai_core/tools/financial_caps.py"
    ).lower()
    # Nel codice del tool la parola compare una volta sola, dentro
    # l'istruzione che dice al modello di non usarla: e' il posto giusto.
    assert tool.count("rimarranno") <= 1


def test_the_financial_conversation_cannot_move_money():
    """§9 di sempre: nessun attuatore, nessun mail.send."""
    tool = (
        HERE / "conversation_engine/ai_core/tools/financial_caps.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in ("mail.send", "def pay", "transfer(", "charge(",
                      "purchase(", "bonifico("):
        assert forbidden not in tool, f"il tool contiene «{forbidden}»"


def test_answering_a_question_never_writes_a_memory_by_itself():
    """
    §4: anche un «sì» passa dalla governance.

    La parola della persona alza l'autorita' della proposta; non salta il
    passaggio. Se un giorno qualcuno scrivesse la memoria a mano da qui,
    questa guardia lo direbbe.
    """
    knowledge = (HERE / "financial" / "knowledge.py").read_text(encoding="utf-8")
    for forbidden in ("memories.insert", "memories.update_one",
                      "memories.replace_one"):
        assert forbidden not in knowledge, (
            f"la risoluzione scrive memorie da sé: «{forbidden}»"
        )
    assert "propose(" in knowledge, "il sì non passa dalla governance"


def test_there_is_one_financial_tool_and_not_three():
    """
    §2: UN SOLO TOOL.

    Uno per l'orizzonte, uno per le domande aperte e uno per il resto
    avrebbero fatto scegliere al modello quale verita' guardare.
    """
    registry = (
        HERE / "conversation_engine/ai_core/tools/registry.py"
    ).read_text(encoding="utf-8")
    block = registry.split("def _register_financial", 1)[1].split(
        "def _register_calendar", 1,
    )[0]
    registered = block.count("capability=\"")
    assert registered == 2, (
        f"ci sono {registered} capacità finanziarie: una per leggere e una "
        "per registrare la risposta, non di più"
    )


def test_the_life_screen_shows_the_three_states_apart():
    """
    §1: anche in Vita, «so» e «ho letto» non sono la stessa riga.

    Appiattirli in un elenco solo sarebbe presentare come certo qualcosa che
    non lo e' — sullo schermo, dove nessuno rilegge il codice.
    """
    screen = (
        HERE.parent / "frontend" / "app" / "life-area" / "[areaId].tsx"
    ).read_text(encoding="utf-8")
    assert "LATO ECONOMICO" in screen
    assert "money.so.map" in screen
    assert "money.ho_letto.map" in screen
    assert "money.devo_chiederti.map" in screen
    assert "l'ho letto" in screen, "quello che è stato letto non è attribuito"
    # Nel blocco economico non deve entrare niente di tecnico. Il resto della
    # schermata ha gia' una sua nozione di provenienza, scritta per una
    # persona — «me lo hai detto tu» — e non c'entra con questa guardia.
    block = screen.split("LATO ECONOMICO", 1)[1].split("COSA ORA TIENE A MENTE", 1)[0]
    for forbidden in ("confidence", "source_ref", "fin_", "JSON.stringify",
                      "memory_id", "identity_key"):
        assert forbidden not in block, f"nel lato economico compare «{forbidden}»"


# ---------------------------------------------------------------------------
# La risposta data da Home
# ---------------------------------------------------------------------------

def test_the_question_reaches_home_with_its_two_answers():
    """
    §1: UNA DOMANDA VA DOVE STANNO LE DOMANDE.

    Stava fra gli aggiornamenti, che e' il posto dove ORA racconta cosa ha
    fatto: li' una domanda si legge come una notizia, e una notizia non si
    risponde. Adesso e' una domanda, con le due risposte addosso.
    """
    async def body():
        client, db = await _db()
        uid = f"tap_{uuid.uuid4().hex[:8]}"
        try:
            from financial.models import Money
            from home.service import HomeService

            await _ora_knows(db, _fact(uid))
            await _ora_only_read(db, _fact(
                uid, money=Money(amount=760, currency="EUR"),
                provenance=[_from("email", "lo ha scritto il proprietario")],
            ))

            home = await HomeService(db).build_home(uid)
            asked = [q for q in home.open_questions if q["id"].startswith("ask:")]
            assert len(asked) == 1, "la domanda non è arrivata fra le domande"
            assert "€760" in asked[0]["question"]
            assert [a["action"] for a in asked[0]["answers"]] == [
                "money_yes", "money_no",
            ]
            # E non anche fra gli aggiornamenti: sarebbe chiedere due volte.
            for insight in home.insights:
                assert "è €760?" not in insight.text, (
                    "la stessa domanda compare anche fra gli aggiornamenti"
                )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_yes_from_home_goes_through_the_same_door_as_the_one_from_chat():
    """
    §1: tap → stessa open_question → governance → SUPERSEDE.

    Quello che l'azione di Home esegue e' `resolve_open_question`, la stessa
    funzione che chiama il tool della conversazione. Due porte, una stanza.
    """
    async def body():
        client, db = await _db()
        uid = f"tap_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts
            from financial.horizon import what_is_coming
            from financial.knowledge import what_ora_knows
            from financial.models import Money
            from home.service import HomeService

            await _ora_knows(db, _fact(uid))
            await _ora_only_read(db, _fact(
                uid, money=Money(amount=760, currency="EUR"),
                provenance=[_from("email", "lo ha scritto il proprietario")],
            ))

            svc = HomeService(db)
            out = await svc.apply_action(uid, item_id="ask:affitto", action="money_yes")
            assert out["ok"] is True and out["confirmed"] is True
            assert out["in_life_model"] is True

            known = await governed_facts(db, uid)
            assert [(f.what, f.money.amount) for f in known] == [("affitto", 760.0)]

            said = await what_ora_knows(db, uid)
            assert said["devo_chiederti"] == [], "la domanda è rimasta aperta"
            assert [r["quanto"] for r in said["so"]] == ["€760"]

            horizon = await what_is_coming(db, uid, days=30)
            assert len(horizon.outgoing) == 1, "l'orizzonte ha due affitti"
            assert horizon.known_outgoing_total() == 760.0

            home = await svc.build_home(uid)
            assert not [q for q in home.open_questions if q["id"].startswith("ask:")]

            for coll in ("agent_goals", "opportunities"):
                assert await db[coll].count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_no_from_home_closes_the_question_and_keeps_what_was_known():
    """
    §2: un no non cancella l'osservazione.

    E' vero che quel messaggio lo diceva, anche se non era vero il contenuto:
    la provenienza resta, la conoscenza precedente resta corrente, e la
    domanda si chiude comunque.
    """
    async def body():
        client, db = await _db()
        uid = f"tap_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts
            from financial.knowledge import what_ora_knows
            from financial.models import Money
            from home.service import HomeService

            await _ora_knows(db, _fact(uid))
            await _ora_only_read(db, _fact(
                uid, money=Money(amount=760, currency="EUR"),
                provenance=[_from("email", "lo ha scritto il proprietario")],
            ))

            svc = HomeService(db)
            out = await svc.apply_action(uid, item_id="ask:affitto", action="money_no")
            assert out["ok"] is True and out["confirmed"] is False

            known = await governed_facts(db, uid)
            assert [(f.what, f.money.amount) for f in known] == [("affitto", 700.0)]

            said = await what_ora_knows(db, uid)
            assert said["devo_chiederti"] == []

            home = await svc.build_home(uid)
            assert not [q for q in home.open_questions if q["id"].startswith("ask:")]

            declined = await db.financial_facts.find_one(
                {"owner_id": uid, "governance_decision": "DECLINED_BY_USER"},
                {"_id": 0},
            )
            assert declined is not None
            assert declined["status"] == "withdrawn"
            assert declined["provenance"], "il rifiuto ha cancellato la provenienza"

            for coll in ("agent_goals", "opportunities"):
                assert await db[coll].count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_home_and_chat_resolve_through_one_function():
    """
    Guardia strutturale: due porte, una stanza.

    Se un domani l'azione di Home risolvesse per conto suo, un sì dato in
    Home e uno detto a ORA chiuderebbero due cose diverse, e la domanda
    tornerebbe a chiedere.
    """
    service = (HERE / "home" / "service.py").read_text(encoding="utf-8")
    block = service.split('if action in ("money_yes", "money_no"):', 1)[1][:900]
    assert "resolve_open_question" in block
    for own in ("propose(", "memories.update", "financial_facts.update"):
        assert own not in block, f"Home risolve per conto suo: «{own}»"
