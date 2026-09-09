"""
V3.11 Sprint 2 — i soldi entrano nella vita, o non entrano affatto.

    UNA SOLA VERITA' DUREVOLE: IL PERSONAL LIFE MODEL.

Sprint 1 aveva costruito un modello di fatti economici con la sua collezione.
Il rischio, da li' in poi, era di lasciarla diventare una seconda memoria: un
posto dove ORA «sa» cose che nessuno ha mai governato, che nessuno puo'
correggere, e che nel giro di un mese dice cose diverse dal resto.

Quindi: la collezione resta il registro di cosa e' stato osservato e come e'
stato interpretato — serve a rispondere «perche' lo credi» — e la fonte di
cio' che ORA sa e' una sola, la stessa di tutto il resto.
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
                 "agent_goals", "life_objects", "connected_signals",
                 "meaningful_changes", "ambient_wakes", "opportunities"):
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


# ---------------------------------------------------------------------------
# La governance, che e' il cuore dello sprint
# ---------------------------------------------------------------------------

def test_a_lasting_commitment_from_a_document_enters_the_life_model():
    """
    §2: observation → candidate → governance → persisted.

    Un contratto e' una fonte diretta e un affitto mensile e' una cosa che
    dura: la governance lo promuove, e da quel momento ORA lo sa.
    """
    async def body():
        client, db = await _db()
        uid = f"gov_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts, propose

            out = await propose(db, _fact(uid))
            assert out["decision"] in ("PROMOTE", "SUPERSEDE"), out
            assert out["persisted"] is True
            assert out["memory_id"]

            known = await governed_facts(db, uid)
            assert [f.what for f in known] == ["affitto"]
            assert known[0].money.amount == 700

            memory = await db.memories.find_one(
                {"user_id": uid, "id": out["memory_id"]}, {"_id": 0},
            )
            # La memoria conserva quello che serve per non fraintenderla dopo.
            assert memory["kind"] == "financial"
            assert memory["identity_key"] == "financial:commitment:affitto"
            assert memory["provenance"], "una memoria economica senza provenienza"
            assert memory["temporal_scope"]["recurrence"] == "ogni mese"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_something_read_in_an_email_is_not_believed_without_asking():
    """
    §2: CLARIFY e' un esito, non un fallimento.

    ORA non deve credere durevolmente che l'affitto sia cambiato perche' lo
    ha letto in un messaggio. La governance chiede conferma, e quel «devo
    chiedertelo» e' esattamente il comportamento giusto.
    """
    async def body():
        client, db = await _db()
        uid = f"gov_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts, propose

            out = await propose(db, _fact(
                uid, provenance=[_from("email", "lo ha scritto il proprietario")],
            ))
            assert out["decision"] == "CLARIFY"
            assert out["persisted"] is False
            assert await governed_facts(db, uid) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_dated_bill_is_not_a_durable_memory():
    """
    §2: una scadenza non e' una cosa che ORA sa di te.

    La governance lo dice da sola — «contesto temporaneo, appartiene a una
    situazione» — e ha ragione: riempire la memoria di una persona di
    bollette scadute e' il modo di renderla inutile.
    """
    async def body():
        client, db = await _db()
        uid = f"gov_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import propose

            soon = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()
            out = await propose(db, _fact(
                uid, what="bolletta della luce", cadence="one_time",
                recurrence=None, due_at=soon,
            ))
            assert out["decision"] == "REJECT"
            assert out["persisted"] is False
            assert await db.memories.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_bill_that_is_not_a_memory_still_reaches_the_horizon():
    """
    §8: e nonostante questo la persona la vede arrivare.

    E' la coppia di regole che rende il sistema onesto invece che rigido: la
    bolletta non entra in cio' che ORA sa di te, ma alla domanda «cosa mi
    aspetta» c'e', perche' e' quella la domanda a cui serve.
    """
    async def body():
        client, db = await _db()
        uid = f"gov_{uuid.uuid4().hex[:8]}"
        try:
            from financial.horizon import what_is_coming
            from financial.store import FinancialStore

            soon = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()
            await FinancialStore(db).remember(_fact(
                uid, what="bolletta della luce", cadence="one_time",
                recurrence=None, due_at=soon,
            ))
            horizon = await what_is_coming(db, uid, days=30)
            assert [f.what for f in horizon.outgoing] == ["bolletta della luce"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_life_model_is_the_only_thing_the_horizon_trusts_for_what_lasts():
    """
    §2/§3: il registro non e' una seconda fonte canonica.

    Un impegno ricorrente che sta solo nel registro compare come osservato,
    con la sua riserva scritta accanto; quando la governance lo promuove,
    diventa quello che ORA sa e la riserva sparisce.
    """
    async def body():
        client, db = await _db()
        uid = f"gov_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import propose
            from financial.horizon import what_is_coming
            from financial.store import FinancialStore

            fact = _fact(uid)
            await FinancialStore(db).remember(fact)

            before = await what_is_coming(db, uid, days=30)
            assert [f.what for f in before.outgoing] == ["affitto"]
            assert any("non me l'hai confermato" in u for u in before.unknowns), (
                "un impegno non governato viene presentato come noto"
            )

            await propose(db, fact)
            after = await what_is_coming(db, uid, days=30)
            assert [f.what for f in after.outgoing] == ["affitto"]
            assert not any("non me l'hai confermato" in u for u in after.unknowns)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_new_version_supersedes_the_memory_instead_of_adding_one():
    """
    §3: da ottobre l'affitto e' 760, e resta un affitto solo.
    """
    async def body():
        client, db = await _db()
        uid = f"gov_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts, propose
            from financial.models import Money

            first = await propose(db, _fact(uid))
            assert first["persisted"] is True

            out = await propose(db, _fact(
                uid, money=Money(amount=760, currency="EUR"),
                valid_from="2026-10-01T00:00:00+00:00",
            ))
            assert out["decision"] == "SUPERSEDE"
            assert out["persisted"] is True

            known = await governed_facts(db, uid)
            assert len(known) == 1, f"ci sono {len(known)} affitti nel modello"
            assert known[0].money.amount == 760

            old = await db.memories.find_one(
                {"user_id": uid, "id": first["memory_id"]}, {"_id": 0},
            )
            assert old["status"] == "superseded"
            assert old["superseded_by"] == out["memory_id"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_disagreement_survives_governance_without_a_winner():
    """
    §4: il documento dice 900, l'email 850, e ORA sa di non sapere.

    Non una memoria con la cifra piu' recente: due memorie che si nominano a
    vicenda. E' l'unica forma onesta di «dovrei chiedertelo», e la schermata
    la puo' leggere senza inventare.
    """
    async def body():
        client, db = await _db()
        uid = f"gov_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import governed_facts, open_questions, propose
            from financial.models import Money

            first = await propose(db, _fact(
                uid, money=Money(amount=900, currency="EUR"),
            ))
            assert first["persisted"] is True

            # La seconda versione dichiara di convivere con la prima: non la
            # sostituisce, e non viene sostituita.
            second = await propose(
                db,
                _fact(uid, money=Money(amount=850, currency="EUR"),
                      status="disputed",
                      provenance=[_from("document", "c'è scritto in un altro atto")]),
                reasoning_epoch=f"fin:conflitto:{uuid.uuid4().hex[:6]}",
                coexists_with=[first["memory_id"]],
            )
            assert second["decision"] in ("PROMOTE", "CLARIFY"), second

            if second["persisted"]:
                known = await governed_facts(db, uid)
                amounts = sorted(f.money.amount for f in known)
                assert amounts == [850.0, 900.0], (
                    "una delle due versioni è stata scelta al posto dell'altra"
                )
                asked = await open_questions(db, uid)
                assert asked, "il modello della vita non sa di non sapere"
            else:
                # Se la governance chiede conferma, il conflitto resta
                # comunque rappresentato: non ne è entrata una sola.
                assert second["decision"] == "CLARIFY"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Il ponte automatico
# ---------------------------------------------------------------------------

def test_connected_life_asks_the_money_question_in_the_judgement_it_already_makes():
    """
    §1: nessun secondo giro, nessuna parola chiave.

    Chi decide se una cosa parla di soldi e' lo stesso giudizio che decide se
    conta — nella stessa chiamata — e non un elenco di parole. «Fattura»
    manderebbe al ragionamento finanziario ogni pubblicita' che la nomina, e
    lascerebbe fuori «da settembre pago sessanta euro in piu'».
    """
    reasoning = (HERE / "connected" / "reasoning.py").read_text(encoding="utf-8")
    assert "touches_money" in reasoning, "il giudizio non chiede se parla di soldi"

    service = (HERE / "connected" / "service.py").read_text(encoding="utf-8")
    assert 'answer.get("touches_money")' in service, (
        "il passaggio non usa la risposta del giudizio per instradare"
    )

    # E nessun elenco di parole che decida al posto suo.
    for word in ("fattura", "bolletta", "canone", "iban", "pagamento"):
        assert word not in service.lower().split("#")[0], (
            f"c'è un instradamento a parole chiave: «{word}»"
        )


def test_noise_never_reaches_the_financial_reasoning():
    """
    §1: il rumore muore prima.

    Una pubblicita' di prestiti nomina delle somme. Non deve arrivare al
    ragionamento finanziario, e non ci arriva perche' e' `noise` e il rumore
    non viene passato a niente.
    """
    service = (HERE / "connected" / "service.py").read_text(encoding="utf-8")
    body = service.split("if outcome == \"noise\":", 1)[1].split("link = None", 1)[0]
    assert "read_money_in" not in body, (
        "il rumore può arrivare al ragionamento finanziario"
    )

    # E il gancio sta dentro `_pass_on`, cioè dopo che il rumore è stato
    # tolto di mezzo.
    passed = service.split("async def _pass_on", 1)[1]
    assert "read_money_in" in passed


def test_the_bridge_runs_inside_the_existing_pass(monkeypatch):
    """
    §1: comportamentale — un segnale finanziario arriva ai soldi da solo.
    """
    async def body():
        client, db = await _db()
        uid = f"br_{uuid.uuid4().hex[:8]}"
        try:
            from connected.models import ConnectedSignal
            from connected.service import ConnectedLifeService
            import financial.bridge as bridge

            seen = []

            async def spy(db_, owner, *, observation, provenance, source_refs=None,
                          language="it"):
                seen.append((owner, provenance.source))
                return {"outcome": "nothing"}

            monkeypatch.setattr(bridge, "read_money_in", spy)

            signal = ConnectedSignal(
                owner_id=uid, source_id="src", source_type="email",
                signal_type="email.message.added", source_object_ref="m1",
                payload_summary="È arrivata una fattura.", after="Fattura",
            )
            await ConnectedLifeService(db)._pass_on(
                uid, signal,
                {"outcome": "worth_knowing", "touches_money": True,
                 "what_it_means": "una fattura"},
            )
            assert seen == [(uid, "email")], "il ponte non è stato attraversato"

            seen.clear()
            await ConnectedLifeService(db)._pass_on(
                uid, signal,
                {"outcome": "worth_knowing", "touches_money": False,
                 "what_it_means": "niente di economico"},
            )
            assert seen == [], "ci è passato anche quello che non parla di soldi"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# I confini, di nuovo
# ---------------------------------------------------------------------------

def test_nothing_financial_writes_a_memory_by_itself():
    """
    §2: NO DIRECT WRITE AL LIFE MODEL.

    L'unico modulo che puo' scrivere in `memories` e' la governance. Il
    modulo finanziario propone e basta — e questa guardia fallisce il giorno
    in cui qualcuno prende una scorciatoia.
    """
    for path in sorted((HERE / "financial").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("memories.insert", "memories.update_one",
                          "memories.update_many", "memories.replace"):
            assert forbidden not in text, f"{path.name} scrive memorie: {forbidden}"
    durable = (HERE / "financial" / "durable.py").read_text(encoding="utf-8")
    assert "MemoryGovernanceService" in durable, (
        "il percorso durevole non passa dalla governance"
    )


def test_the_financial_collection_is_not_a_second_source_of_truth():
    """
    §3: chi risponde a una persona legge il modello della vita.

    L'orizzonte legge i fatti governati; il registro lo tocca solo per le
    scadenze, che memorie non sono.
    """
    horizon = (HERE / "financial" / "horizon.py").read_text(encoding="utf-8")
    assert "governed_facts" in horizon
    used = horizon.index("governed_facts")
    journal = horizon.index("FinancialStore(db).known")
    assert used < journal, (
        "l'orizzonte guarda il registro prima del modello della vita"
    )


def test_the_financial_layer_still_cannot_move_money():
    """§9: nessun pagamento, nessun bonifico, nessun mail.send."""
    for path in sorted((HERE / "financial").glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("mail.send", "def pay", "transfer(", "bonifico(",
                          "charge(", "subscribe(", "purchase("):
            assert forbidden not in text, f"{path.name} contiene «{forbidden}»"


def test_no_financial_fact_creates_a_goal_by_itself():
    """
    §9: NESSUNA CATEGORIA GENERA LAVORO DA SOLA.

    Guardia strutturale: nel modulo finanziario non deve esserci modo di
    creare un goal, un piano o un'opportunita'.
    """
    for path in sorted((HERE / "financial").glob("*.py")):
        source = ast.dump(ast.parse(path.read_text(encoding="utf-8")))
        for forbidden in ("create_goal", "AutonomousGoal", "OpportunityService",
                          "save_plan", "agent_goals.insert"):
            assert forbidden not in source, f"{path.name} crea lavoro: {forbidden}"


def test_there_is_still_no_finance_tab():
    """§6: la finanza resta dentro le superfici che ci sono."""
    tabs = HERE.parent / "frontend" / "app" / "(tabs)"
    names = {p.stem.lower() for p in tabs.glob("*.tsx")} if tabs.exists() else set()
    for forbidden in ("finanze", "finance", "wallet", "budget", "spese"):
        assert forbidden not in names, f"c'è una scheda «{forbidden}»"
