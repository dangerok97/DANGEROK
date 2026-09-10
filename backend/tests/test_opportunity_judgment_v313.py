"""
Judgment recovery — perche' ORA taceva davanti a una vita che aveva qualcosa
da dire, e cosa deve smettere di fare.

    NOT URGENT != NOT USEFUL.
    «È GIÀ NEL CALENDARIO» != «LO SA».
    RETRIEVAL CONFIDENCE != ACTION AUTHORITY.

Il gate precedente aveva rimesso in piedi la catena: i segnali venivano letti,
capiti, i cambiamenti registrati, la revisione girava. E finiva sempre allo
stesso modo — zero. Il motivo non era una soglia: era che chi decide riceveva
un'agenda fatta di appuntamenti annullati, non riceveva i disaccordi, e aveva
davanti un'istruzione che diceva sei volte che il silenzio e' la risposta
normale e una sola volta cosa lo renderebbe sbagliato.

Qui si fissano tre cose, e nessuna delle tre e' una regola di dominio:

* i fatti che arrivano al giudizio devono essere quelli veri;
* il codice non deve filtrare per fretta cio' che chi giudica ha ritenuto
  utile;
* il silenzio resta una risposta valida, e resta gratis.

Il modello e' finto ovunque venga interrogato: quello che si verifica e' che
il codice non abbia giudicato al posto suo, in nessuna delle due direzioni.
"""

from __future__ import annotations

import ast
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _service(db):
    from opportunities.service import OpportunityService

    return OpportunityService(db)


async def _clean(db, uid):
    for coll in (
        "opportunities", "opportunity_decisions", "calendar_events",
        "ingestion_events", "connected_situation_links", "life_objects",
        "open_questions", "home_snapshots",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class FakeModel:
    """The model, saying what a test needs it to say."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.seen = []

    async def __call__(self, system, user):
        self.seen.append({"system": system, "user": user})
        return self.answers.pop(0) if self.answers else None


def _install(monkeypatch, model):
    import opportunities.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


def _proposal(identity, refs, **over):
    out = {
        "identity_key": identity,
        "what": "Ci sono due orari diversi per l'appuntamento di oggi.",
        "why_it_matters": "Rischi di presentarti all'ora sbagliata.",
        "why_now": "È oggi.",
        "initiative": "recommend",
        "what_i_can_do": "Posso verificare quale delle due ore è quella confermata.",
        "relevance": "medium",
        "urgency": "none",
        "time_sensitivity": "stable",
        "confidence": "reasonable",
        "evidence_refs": list(refs),
    }
    out.update(over)
    return out


async def _an_appointment(db, uid, *, title, when, status="confirmed",
                          ingestion_status="processed", ref=None):
    """Un impegno come arriva davvero: dentro ingestion_events."""
    ref = ref or f"evt_{uuid.uuid4().hex[:10]}"
    await db.ingestion_events.insert_one({
        "id": f"ing_{uuid.uuid4().hex[:12]}",
        "user_id": uid,
        "external_id": ref,
        "source_record_type": "calendar_event",
        "ingestion_status": ingestion_status,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "normalized_payload": {
            "title": title,
            "starts_at": when.isoformat(),
            "ends_at": (when + timedelta(hours=1)).isoformat(),
            "status": status,
        },
    })
    return ref


async def _a_disagreement(db, uid, *, target_ref, says, other_says,
                          decided_days_ago=0):
    ref = f"link_{uuid.uuid4().hex[:12]}"
    when = datetime.now(timezone.utc) - timedelta(days=decided_days_ago)
    await db.connected_situation_links.insert_one({
        "id": ref,
        "owner_id": uid,
        "target_ref": target_ref,
        "target_kind": "appointment",
        "reason_summary": "Il messaggio parla dello stesso appuntamento con un'ora diversa.",
        "disagreements": [{
            "about": "what each of them says about this",
            "what_this_source_says": says,
            "what_the_other_says": other_says,
            "how_this_source_knows": "somebody wrote it in a message",
            "how_the_other_knows": "the calendar itself holds this appointment",
        }],
        "decided_at": when.isoformat(),
    })
    return ref


async def _some_noise_links(db, uid, how_many=8):
    """Le righe che il giudizio produce di continuo: nessun disaccordo."""
    now = datetime.now(timezone.utc)
    await db.connected_situation_links.insert_many([
        {
            "id": f"link_{uuid.uuid4().hex[:12]}",
            "owner_id": uid,
            "target_ref": "",
            "reason_summary": "È una newsletter promozionale.",
            "disagreements": None,
            "decided_at": (now - timedelta(minutes=i)).isoformat(),
        }
        for i in range(how_many)
    ])


# ---------------------------------------------------------------------------
# I fatti su cui si decide
# ---------------------------------------------------------------------------

def test_the_calendar_the_judgement_sees_holds_only_commitments_that_exist():
    """
    §3 + §6: un impegno annullato non e' un impegno, e lo stesso impegno
    scritto quattro volte e' uno.

    Trovato sull'account vero: le sei righe di agenda che arrivavano al
    giudizio erano quattro copie annullate della stessa visita piu' un evento
    di prova. L'unica visita che esisteva davvero ci stava dentro per caso.
    Chi guarda quell'agenda non puo' che concludere che non c'e' niente.
    """
    async def body():
        client, db = await _db()
        uid = f"u_jd_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities import snapshot as life

            soon = datetime.now(timezone.utc) + timedelta(hours=6)
            real = await _an_appointment(
                db, uid, title="Visita dentistica — Studio Bianchi", when=soon,
            )
            # Le copie annullate della stessa cosa, e una lettura superata.
            await _an_appointment(
                db, uid, title="Visita dentistica — Studio Bianchi",
                when=soon, status="cancelled",
            )
            await _an_appointment(
                db, uid, title="QA — Visita dentistica", when=soon,
                status="cancelled",
            )
            await _an_appointment(
                db, uid, title="Visita dentistica — Studio Bianchi",
                when=soon, ingestion_status="superseded",
            )
            # E la stessa identica riga arrivata due volte dalla sorgente.
            twin = await _an_appointment(
                db, uid, title="Visita dentistica — Studio Bianchi", when=soon,
            )

            snapshot = await life.build(db, uid)
            agenda = snapshot["calendar"]

            assert len(agenda) == 1, (
                f"al giudizio arriva un'agenda di fantasmi: {agenda}"
            )
            # Quale delle due letture identiche resti non e' una domanda con
            # una risposta giusta: sono la stessa cosa. Che ne resti una sola,
            # e che sia una viva, lo e'.
            assert agenda[0]["ref"] in (real, twin)
            assert agenda[0]["title"] == "Visita dentistica — Studio Bianchi"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_live_entries_at_different_hours_both_reach_the_judgement():
    """
    §6: STESSO IMPEGNO, ORE DIVERSE — e il codice non sceglie quale vale.

    L'altra meta' della regola sopra. Togliere gli annullati e' un fatto sulla
    riga; accorpare due impegni vivi che dicono ore diverse sarebbe il codice
    a decidere quale delle due e' quella giusta, che e' esattamente la domanda
    da lasciare a chi ragiona.
    """
    async def body():
        client, db = await _db()
        uid = f"u_jd_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities import snapshot as life

            now = datetime.now(timezone.utc)
            first = await _an_appointment(
                db, uid, title="Visita — Studio Bianchi", when=now + timedelta(hours=5),
            )
            second = await _an_appointment(
                db, uid, title="Visita — Studio Bianchi", when=now + timedelta(hours=6),
            )

            refs = [r["ref"] for r in (await life.build(db, uid))["calendar"]]
            assert first in refs and second in refs, (
                "il codice ha scelto da solo quale delle due ore vale"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_live_disagreement_reaches_the_judgement_and_can_be_cited():
    """
    §11 + §20: due fonti che dicono ore diverse sono tutte e due nel
    calendario, e averle tutte e due e' il problema, non la risposta.

    Il disaccordo era registrato dal Connected Life dal giorno prima. Non
    arrivava al giudizio per due motivi, tutti e due nel codice: la query
    prendeva anche le righe con il campo nullo — che sono quasi tutte — e i
    riferimenti di un disaccordo non erano fra le prove citabili, quindi
    qualunque frase che ne parlasse veniva scartata per mancanza di fatti.
    """
    async def body():
        client, db = await _db()
        uid = f"u_jd_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities import snapshot as life

            soon = datetime.now(timezone.utc) + timedelta(hours=6)
            appointment = await _an_appointment(
                db, uid, title="Visita dentistica — Studio Bianchi", when=soon,
            )
            # Il disaccordo vero e' vecchio di qualche giorno; il rumore e' di
            # stamattina. Ordinare per data e basta lo lasciava sempre fuori.
            conflict = await _a_disagreement(
                db, uid, target_ref=appointment,
                says="Studio Bianchi — conferma appuntamento ore 11:00",
                other_says="10/09 alle 10:00",
                decided_days_ago=4,
            )
            await _some_noise_links(db, uid, how_many=8)

            snapshot = await life.build(db, uid)
            said = snapshot["disagreements"]
            assert [r["ref"] for r in said] == [conflict], (
                f"il disaccordo vivo non arriva al giudizio: {said}"
            )
            assert "11:00" in said[0]["one_source_says"]
            assert said[0]["nobody_has_chosen"] is True

            allowed = life.evidence_refs(snapshot)
            assert allowed.get(conflict) == "disagreement", (
                "un'opportunità che parla del conflitto verrebbe scartata "
                "per «nessun fatto reale a sostegno»"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Il giudizio
# ---------------------------------------------------------------------------

def test_not_urgent_can_still_be_useful(monkeypatch):
    """
    §1: NOT URGENT != NOT USEFUL.

    Il codice non ha nessun diritto di guardare `urgency` per decidere se una
    cosa merita di esistere. Una cosa ferma da settimane, senza nessuna
    scadenza addosso, vale una frase — e se chi giudica lo dice, il codice la
    scrive.
    """
    async def body():
        client, db = await _db()
        uid = f"u_jd_{uuid.uuid4().hex[:8]}"
        try:
            far = datetime.now(timezone.utc) + timedelta(days=9)
            ref = await _an_appointment(db, uid, title="Rogito", when=far)

            _install(monkeypatch, FakeModel([{
                "opportunities": [_proposal(
                    "casa:indirizzo-mancante", [ref],
                    what="Alla casa che stai comprando manca ancora l'indirizzo.",
                    why_it_matters="Senza quello ORA non può tenere insieme mutuo, utenze e documenti.",
                    initiative="recommend",
                    urgency="none",
                    relevance="medium",
                    time_sensitivity="stable",
                )],
            }]))

            result = await (await _service(db)).scan(uid)

            assert result.silence is False
            assert len(result.created) == 1
            born = result.created[0]
            assert born.urgency == "none"
            assert born.status == "active"
            assert born.initiative == "recommend"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_offer_survives_all_the_way_to_what_a_person_reads(monkeypatch):
    """
    §12: quello che ORA ha notato, perche' conta, e cosa puo' farci lei.

    L'ultima riga e' la meta' per cui vale la pena leggere le prime due, e
    fino a ieri non esisteva: si poteva dire a qualcuno che c'era un problema
    e non cosa ORA fosse disposta a farci.
    """
    async def body():
        client, db = await _db()
        uid = f"u_jd_{uuid.uuid4().hex[:8]}"
        try:
            soon = datetime.now(timezone.utc) + timedelta(hours=6)
            appointment = await _an_appointment(
                db, uid, title="Visita dentistica", when=soon,
            )
            conflict = await _a_disagreement(
                db, uid, target_ref=appointment,
                says="conferma appuntamento ore 11:00",
                other_says="10/09 alle 10:00",
            )

            _install(monkeypatch, FakeModel([{
                "opportunities": [_proposal(
                    "dentista:ora-in-dubbio", [conflict, appointment],
                )],
            }]))

            result = await (await _service(db)).scan(uid)
            assert len(result.created) == 1

            read = result.created[0].for_home()
            assert read["what_ora_can_do"], (
                "la persona legge il problema e non cosa ORA può farci"
            )
            assert "verificare" in read["what_ora_can_do"]
            # E niente parole di sistema in quello che si legge.
            for word in ("initiative", "relevance", "confidence", "recommend"):
                assert word not in str(read), read
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_significant_but_not_actionable_is_still_silence(monkeypatch):
    """
    §4 + §19B: il silenzio resta una risposta valida e non costa niente.

    Il rischio del fix opposto e' esattamente questo: un sistema che, dopo che
    gli hai detto che tacere troppo e' un difetto, comincia a parlare sempre.
    Se chi giudica guarda e dice che non c'e' niente da fare, non si scrive
    niente — nemmeno una riga di «ho guardato».
    """
    async def body():
        client, db = await _db()
        uid = f"u_jd_{uuid.uuid4().hex[:8]}"
        try:
            await _an_appointment(
                db, uid, title="Cena con Marco",
                when=datetime.now(timezone.utc) + timedelta(days=3),
            )
            _install(monkeypatch, FakeModel([{
                "opportunities": [],
                "reason_for_silence": (
                    "Ho guardato la cena di giovedì e la casa: sulla prima non "
                    "c'è niente da preparare, sulla seconda ti ho già chiesto "
                    "l'indirizzo e la domanda è ancora aperta."
                ),
            }]))

            result = await (await _service(db)).scan(uid)

            assert result.silence is True
            assert result.unavailable is False
            assert result.created == [] and result.updated == []
            assert await db.opportunities.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_initiative_does_not_arrive_twice(monkeypatch):
    """
    §10: la stessa preoccupazione, notata di nuovo, aggiorna — non si affianca.
    """
    async def body():
        client, db = await _db()
        uid = f"u_jd_{uuid.uuid4().hex[:8]}"
        try:
            soon = datetime.now(timezone.utc) + timedelta(hours=6)
            ref = await _an_appointment(db, uid, title="Visita", when=soon)

            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("dentista:ora-in-dubbio", [ref])]},
                {"opportunities": [_proposal(
                    "dentista:ora-in-dubbio", [ref],
                    what="Restano due orari diversi per la visita di oggi.",
                )]},
            ]))

            service = await _service(db)
            first = await service.scan(uid)
            second = await service.scan(uid)

            assert len(first.created) == 1
            assert second.created == []
            assert len(second.updated) == 1
            assert await db.opportunities.count_documents({"owner_id": uid}) == 1
            assert second.updated[0].semantic_summary.startswith("Restano")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_something_refused_comes_back_only_with_a_fact_that_was_not_there(monkeypatch):
    """
    §10: nuova evidenza puo' riaprire — e nient'altro puo'.

    Chi ha detto «non questo» ha risposto a quello che sapeva allora. Se oggi
    la stessa preoccupazione poggia su un fatto che quel giorno non c'era,
    tacere le nasconde la parte che avrebbe potuto cambiarle idea. Ma il
    fatto deve essere un fatto: una frase riscritta meglio non riapre niente,
    altrimenti qualunque rifiuto tornerebbe il giorno dopo con un sinonimo.
    """
    async def body():
        client, db = await _db()
        uid = f"u_jd_{uuid.uuid4().hex[:8]}"
        try:
            now = datetime.now(timezone.utc)
            known = await _an_appointment(db, uid, title="Visita", when=now + timedelta(hours=6))

            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("dentista:ora-in-dubbio", [known])]},
            ]))
            service = await _service(db)
            born = (await service.scan(uid)).created[0]
            await service.dismiss(uid, born.id)

            # Di nuovo, sugli stessi fatti: resta chiusa.
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal(
                    "dentista:ora-in-dubbio", [known],
                    what="Ripensandoci, l'ora della visita è ancora incerta.",
                )]},
            ]))
            again = await service.scan(uid)
            assert again.created == [] and again.updated == []
            assert any("chiusa" in s["reason"] for s in again.skipped)
            still = await db.opportunities.find_one({"id": born.id})
            assert still["status"] == "dismissed"

            # Con un fatto che prima non c'era: torna.
            fresh = await _a_disagreement(
                db, uid, target_ref=known,
                says="conferma appuntamento ore 11:00",
                other_says="10/09 alle 10:00",
            )
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal(
                    "dentista:ora-in-dubbio", [known, fresh],
                    what="È arrivata una conferma che dice un'ora diversa.",
                )]},
            ]))
            reopened = await service.scan(uid)
            assert len(reopened.updated) == 1
            assert reopened.updated[0].id == born.id
            back = await db.opportunities.find_one({"id": born.id})
            assert back["status"] == "active"

            decisions = await db.opportunity_decisions.find(
                {"opportunity_id": born.id}
            ).to_list(10)
            assert any(d["outcome"] == "reopen" for d in decisions), (
                "un'opportunità è tornata viva e non c'è scritto perché"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_was_suppressed_stays_suppressed(monkeypatch):
    """
    §10: «mai piu'» e «non ora» sono due risposte diverse.

    Un fatto nuovo riapre cio' che era stato rifiutato una volta. Non riapre
    cio' che qualcuno ha chiesto di non sentire piu'.
    """
    async def body():
        client, db = await _db()
        uid = f"u_jd_{uuid.uuid4().hex[:8]}"
        try:
            now = datetime.now(timezone.utc)
            known = await _an_appointment(db, uid, title="Visita", when=now + timedelta(hours=6))
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("dentista:ora-in-dubbio", [known])]},
            ]))
            service = await _service(db)
            born = (await service.scan(uid)).created[0]
            await service.dismiss(uid, born.id, suppress=True)

            fresh = await _a_disagreement(
                db, uid, target_ref=known, says="ore 11:00", other_says="ore 10:00",
            )
            _install(monkeypatch, FakeModel([
                {"opportunities": [_proposal("dentista:ora-in-dubbio", [known, fresh])]},
            ]))
            again = await service.scan(uid)

            assert again.created == [] and again.updated == []
            still = await db.opportunities.find_one({"id": born.id})
            assert still["status"] == "suppressed"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Fin dove ORA si spinge
# ---------------------------------------------------------------------------

def test_a_sentence_is_a_complete_outcome_and_the_goal_side_is_told_so(monkeypatch):
    """
    §15: piccolo aiuto utile non diventa un lavoro.

    Il gradino scelto viaggia fino a chi decide se ne nasce un obiettivo. Non
    lo vincola — quella resta una seconda decisione, presa da chi ragiona — ma
    senza quell'informazione ogni frase utile rischiava di diventare una
    commissione che nessuno aveva chiesto.
    """
    async def body():
        from life_orchestration import scheduler
        from opportunities.models import Opportunity

        asked = {}

        class FakeAgent:
            def __init__(self, db):
                pass

            async def consider(self, owner_id, *, situation, **rest):
                asked.update(situation)
                return {"outcome": "no_goal"}

        import agent.service as agent_service

        monkeypatch.setattr(agent_service, "AgentService", FakeAgent)

        class FakeScan:
            created = [Opportunity(
                owner_id="u_jd",
                identity_key="dentista:ora-in-dubbio",
                semantic_summary="Due orari diversi per oggi.",
                why_it_matters="Rischi di arrivare all'ora sbagliata.",
                initiative="recommend",
                what_ora_can_do="Posso verificare quale è confermata.",
            )]

        await scheduler._consider_goals("u_jd", FakeScan())

        assert asked.get("how_far_ora_meant_to_go") == "recommend"
        assert asked.get("what_ora_offered_to_do")

    _run(body())


def test_the_goal_judgement_is_told_that_a_remark_need_not_become_work():
    """
    §15 di nuovo, dall'altra parte: l'istruzione lo dice, e lo dice come
    criterio — non come regola che il codice applica al posto suo.
    """
    source = (HERE / "agent" / "reasoning.py").read_text(encoding="utf-8")
    assert "how_far_ora_meant_to_go" in source
    assert "usually `no_goal`" in source


def test_reasoning_never_needs_consent_and_effects_still_do():
    """
    §16: capire, confrontare, preparare non chiedono permesso. Toccare il
    mondo si'. La seconda meta' non e' negoziabile da nessun prompt.
    """
    from agent.authority import _NEVER_AUTONOMOUS

    assert {"payment.execute", "external.booking", "mail.send"} <= set(
        _NEVER_AUTONOMOUS
    )
    source = (HERE / "agent" / "reasoning.py").read_text(encoding="utf-8")
    assert "Do not ask permission to think" in source


# ---------------------------------------------------------------------------
# Cosa il codice non ha il diritto di fare
# ---------------------------------------------------------------------------

def _code_only(path: Path) -> ast.Module:
    """L'albero senza le docstring: i principi si scrivono, non si eseguono."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:]
    return tree


def _only_a_vocabulary(fn: ast.AST) -> bool:
    """
    Una funzione che dai numeri tira fuori soltanto parole.

    `_bucket` prende dei minuti e restituisce «entro un'ora», «oggi»,
    «piu' tardi». I suoi confronti sono la definizione di quelle parole, non
    una decisione su cosa meriti attenzione — e si riconosce senza sapere come
    si chiama: non restituisce altro che stringhe.
    """
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    if not returns:
        return False
    for node in returns:
        value = node.value
        if value is None:
            continue
        if isinstance(value, ast.Constant) and isinstance(
            value.value, (str, type(None))
        ):
            continue
        return False
    return True


def test_no_domain_threshold_decides_whether_something_matters():
    """
    §2 + §8: niente `if amount > 3000`, niente `if days_until < 3`.

    E' la tentazione piu' facile del mondo dopo un gate come questo: la
    prossima volta che ORA tace davanti a quattromila euro, aggiungere una
    soglia. Una soglia e' una risposta permanente e invisibile a una domanda
    che dipende dalla situazione, e questo test esiste per impedirla.

    Sorvegliati i due file che decidono: quello che tiene o scarta una
    proposta, e quello che formula la domanda. `snapshot.py` non e' qui
    dentro perche' non decide niente — dichiara il tempo come fatto, con un
    orizzonte e delle bande scritte in chiaro, e passa tutto a chi ragiona.
    """
    for name in ("service.py", "reasoning.py"):
        tree = _code_only(HERE / "opportunities" / name)
        vocabulary = {
            id(node)
            for scope in ast.walk(tree) if _only_a_vocabulary(scope)
            for node in ast.walk(scope)
        }
        for node in ast.walk(tree):
                if not isinstance(node, ast.Compare) or id(node) in vocabulary:
                    continue
                for side in [node.left, *node.comparators]:
                    if not isinstance(side, ast.Constant):
                        continue
                    if isinstance(side.value, bool) or not isinstance(
                        side.value, (int, float)
                    ):
                        continue
                    if side.value in (0, 1):
                        # Zero e uno non sono soglie: sono il vuoto e
                        # l'unita'. `if hours <= 0` controlla che un numero
                        # letto sia un numero, e non ha nessuna opinione su
                        # cosa conti.
                        continue
                    text = ast.dump(node)
                    assert "len" in text or "Attribute" in text, (
                        f"{name}: un numero decide se qualcosa conta "
                        f"({ast.unparse(node)})"
                    )


def test_no_word_of_anybody_life_is_written_into_the_judgement():
    """
    §2: nessuna regola di dominio. «dentista», «casa», «mutuo», «notaio» non
    compaiono nel codice che decide: sono la vita di una persona, e domani
    sono la vita di un'altra.
    """
    domains = ("dentist", "dentista", "mutuo", "notaio", "affitto",
               "stipendio", "esame", "medico")
    for name in ("service.py", "snapshot.py"):
        source = (HERE / "opportunities" / name).read_text(encoding="utf-8")
        tree = _code_only(HERE / "opportunities" / name)
        # Le docstring possono nominarle: raccontano dove il difetto e' stato
        # trovato. Il codice no.
        running = ast.unparse(tree).lower()
        for word in domains:
            assert word not in running, f"{name}: il codice conosce «{word}»"
        assert source  # letto davvero


def test_urgency_never_decides_anything_in_code():
    """
    §1: il codice puo' ordinare per urgenza, mai filtrare per urgenza.

    La differenza e' tutta qui: mettere in fila due cose che chi giudica ha
    ritenuto utili e' aritmetica; togliere quella meno urgente e' un giudizio,
    e non e' del codice.
    """
    tree = _code_only(HERE / "opportunities" / "service.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            text = ast.unparse(node)
            for word in ("urgency", "urgent", "relevance", "in_days"):
                assert word not in text, (
                    f"il codice decide guardando «{word}»: {text}"
                )


def test_the_instruction_forbids_the_two_answers_that_produced_silence():
    """
    §1 + §11: le due frasi con cui ORA si e' zittita davanti a una vita vera.

    «Gli impegni futuri sono già noti nel calendario e non richiedono azioni
    immediate.» Ogni parola vera, la conclusione sbagliata. Adesso l'istruzione
    dice esattamente perche' nessuna delle due regge.
    """
    source = (HERE / "opportunities" / "reasoning.py").read_text(encoding="utf-8")
    assert "NOT URGENT IS NOT THE SAME AS NOT USEFUL" in source
    assert "KNOWING WHERE A FACT IS WRITTEN IS NOT THE SAME AS KNOWING THERE IS A" in source
    assert "never that nothing was " in source
    # E il silenzio resta una risposta, non un difetto.
    assert "Saying nothing costs " in source
