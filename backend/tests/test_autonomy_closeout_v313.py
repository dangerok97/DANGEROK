"""
Le due incoerenze finali, quelle che si vedono solo su uno schermo vero.

    LA RIGA E LA CARD DEVONO VENIRE DALLA STESSA DECISIONE.
    NON CHIEDERE A UNA PERSONA QUELLO CHE PUOI LEGGERE DA SOLO.

Il gate precedente era passato: senza nessun comando, ORA aveva trovato un
conflitto vero e l'aveva messo in Home. Poi, guardando la schermata, due cose
si contraddicevano da sole.

La prima: sopra c'era scritto «due variazioni controllate oggi, tutto
tranquillo» e subito sotto una card che diceva che c'era un conflitto in
calendario da chiarire. La riga era stata scritta qualche minuto prima della
card ed era vera quando fu scritta — il che e' il modo peggiore di essere
falsa, perche' nessuno l'aveva mai detta a voce alta.

La seconda: la card diceva «posso verificare l'orario di partenza» e nella
riga dopo chiedeva alla persona a che ora partisse. Una promessa e il suo
contrario nello stesso respiro. La domanda non era sbagliata: era prematura.

Qui si fissano tutte e due, e si fissa quello che il codice possiede in
entrambe — quale stato viene letto, cosa viene messo davanti a chi ragiona, e
che una verifica mancata non diventi mai una verifica riuscita.
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


async def _clean(db, uid):
    for coll in (
        "opportunities", "opportunity_decisions", "ingestion_events",
        "connected_situation_links", "ambient_activity", "agent_goals",
        "action_intents", "documents",
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


def _install_opportunity_model(monkeypatch, model):
    import opportunities.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


def _install_delivery_model(monkeypatch, model):
    import delivery.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


async def _an_appointment(db, uid, *, title, when, status="confirmed",
                          ingestion_status="processed"):
    ref = f"evt_{uuid.uuid4().hex[:10]}"
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


async def _a_note(db, uid, *, about, written_about, says):
    ref = f"link_{uuid.uuid4().hex[:12]}"
    await db.connected_situation_links.insert_one({
        "id": ref,
        "owner_id": uid,
        "target_ref": about,
        "source_object_ref": written_about,
        "source_type": "calendar",
        "relationship": "same_situation",
        "reason_summary": says,
        "disagreements": [],
        "decided_at": datetime.now(timezone.utc).isoformat(),
    })
    return ref


async def _an_initiative(db, uid, *, refs, question, offer, surfaced=True):
    from opportunities.models import EvidenceRef, Opportunity
    from opportunities.repository import OpportunityRepository

    opportunity = Opportunity(
        owner_id=uid,
        identity_key=f"k{uuid.uuid4().hex[:8]}",
        status="active",
        semantic_summary="Ci sono due voci diverse per lo stesso giorno.",
        why_it_matters="Rischi di regolarti sulla versione sbagliata.",
        why_now="Mancano dieci giorni.",
        initiative="recommend",
        what_ora_can_do=offer,
        requires_clarification=bool(question),
        clarifying_question=question,
        evidence=[EvidenceRef(kind="calendar_event", ref=r) for r in refs],
        surface_state="surfaced" if surfaced else "hidden",
    )
    await OpportunityRepository(db).save(opportunity)
    return opportunity


# ---------------------------------------------------------------------------
# Una riga e una card che si smentiscono
# ---------------------------------------------------------------------------

def test_the_line_is_told_what_is_standing_on_the_same_screen(monkeypatch):
    """
    §1: la riga e la card devono venire dalla stessa decisione.

    Non un secondo giudizio: la riga riceve esattamente la lista che Home
    rende. Senza quella, chi la scrive non ha modo di sapere che due
    centimetri piu' in basso c'e' qualcosa che la smentisce.
    """
    async def body():
        client, db = await _db()
        uid = f"u_cl_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            service = DeliveryService(db)
            await service.note_activity(
                uid, kind="review_completed", summary="",
                provenance={"changes_reviewed": 2, "raised": 1},
            )
            await _an_initiative(
                db, uid, refs=["evt_x"],
                question="", offer="Posso verificare.",
            )

            model = FakeModel([{"worth_saying": True, "line": "Ho guardato."}])
            _install_delivery_model(monkeypatch, model)
            await service.summarise_recent(uid)

            asked = model.seen[0]["user"]
            assert "what_is_standing_right_now" in asked
            assert "due voci diverse" in asked, (
                "chi scrive la riga non sa cosa c'è sulla stessa schermata"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_calm_line_is_not_kept_once_something_is_standing(monkeypatch):
    """
    §1 + §7: la riga di prima era vera prima. Adesso non lo e' piu'.

    Il difetto vero non era la frase: era che la frase, una volta scritta,
    restava per ore qualunque cosa succedesse sotto. Il tempo non basta a dire
    se una riga e' ancora giusta — lo stato si'.
    """
    async def body():
        client, db = await _db()
        uid = f"u_cl_{uuid.uuid4().hex[:8]}"
        try:
            from delivery.service import DeliveryService

            service = DeliveryService(db)
            await service.note_activity(
                uid, kind="review_completed", summary="",
                provenance={"changes_reviewed": 2, "raised": 0},
            )

            # Schermata pulita: la riga tranquilla e' onesta.
            calm = FakeModel([{"worth_saying": True, "line": "Tutto tranquillo."}])
            _install_delivery_model(monkeypatch, calm)
            first = await service.summarise_recent(uid)
            assert first is not None and "tranquillo" in first.summary

            # Con la schermata ancora pulita, la stessa riga vale: nessuna
            # domanda al modello, nessun costo.
            again = FakeModel([])
            _install_delivery_model(monkeypatch, again)
            kept = await service.summarise_recent(uid)
            assert kept is not None and kept.id == first.id
            assert again.seen == [], "ha riscritto una riga che andava bene"

            # Poi nasce un'iniziativa e finisce sullo schermo.
            await _an_initiative(
                db, uid, refs=["evt_x"], question="", offer="Posso verificare.",
            )
            fresh = FakeModel([
                {"worth_saying": True,
                 "line": "Ho guardato il calendario: una cosa vuole la tua attenzione."},
            ])
            _install_delivery_model(monkeypatch, fresh)
            rewritten = await service.summarise_recent(uid)

            assert fresh.seen, "la riga tranquilla è sopravvissuta all'iniziativa"
            assert rewritten is not None
            assert "tranquillo" not in rewritten.summary.lower()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_instruction_forbids_calm_over_something_standing():
    """
    §1: la regola sta scritta dove viene presa la decisione, non in un `if`.
    """
    source = (HERE / "delivery" / "reasoning.py").read_text(encoding="utf-8")
    assert "what_is_standing_right_now" in source
    assert "«tutto tranquillo», " in source or "«tutto tranquillo»," in source
    assert "are false, whatever the " in source


# ---------------------------------------------------------------------------
# Provare prima di chiedere
# ---------------------------------------------------------------------------

def test_ora_looks_before_it_asks(monkeypatch):
    """
    §2 + §3 STEP 3A: se ORA dice che puo' verificare, prima verifica.

    La domanda sparisce e al suo posto c'e' quello che ha trovato. Nessun
    consenso viene chiesto per leggere righe che esistono gia': §16, leggere
    non e' un effetto.
    """
    async def body():
        client, db = await _db()
        uid = f"u_cl_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.settle import try_to_settle_it

            when = datetime.now(timezone.utc) + timedelta(days=10)
            live = await _an_appointment(db, uid, title="Andata", when=when)
            await _a_note(
                db, uid, about=live, written_about=live,
                says="La partenza è stata spostata alle 06:00.",
            )
            opportunity = await _an_initiative(
                db, uid, refs=[live],
                question="A che ora parti?",
                offer="posso verificare l'orario di partenza",
            )

            _install_opportunity_model(monkeypatch, FakeModel([{
                "settled": True,
                "answer": "Ho guardato in calendario: la partenza è alle 06:00.",
                "what_it_rests_on": [live],
            }]))
            outcome = await try_to_settle_it(db, uid, opportunity)

            assert outcome["outcome"] == "settled"
            assert opportunity.requires_clarification is False
            assert opportunity.clarifying_question == ""
            assert "06:00" in opportunity.what_ora_can_do
            assert live in [e.ref for e in opportunity.evidence]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_when_it_cannot_settle_it_says_what_it_looked_at_and_asks_the_least(monkeypatch):
    """
    §3 STEP 3B: la domanda resta, ma non resta com'era.

    Diventa la cosa minima che manca davvero, e accanto le va cosa ORA ha gia'
    guardato. Chi riceve una domanda ha diritto di sapere che e' l'ultima cosa
    rimasta e non la prima tentata.
    """
    async def body():
        client, db = await _db()
        uid = f"u_cl_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.settle import try_to_settle_it

            when = datetime.now(timezone.utc) + timedelta(days=10)
            live = await _an_appointment(db, uid, title="Andata", when=when)
            opportunity = await _an_initiative(
                db, uid, refs=[live],
                question="A che ora parti?",
                offer="posso verificare l'orario di partenza",
            )

            _install_opportunity_model(monkeypatch, FakeModel([{
                "settled": False,
                "what_i_checked": (
                    "Ho guardato il calendario e quello che era stato annotato, "
                    "ma non dice quale delle due valga."
                ),
                "question": "Parti alle 06:00 o l'impegno dura tutto il giorno?",
            }]))
            outcome = await try_to_settle_it(db, uid, opportunity)

            assert outcome["outcome"] == "asked"
            assert opportunity.requires_clarification is True
            assert opportunity.clarifying_question.startswith("Parti alle 06:00")
            assert opportunity.what_ora_can_do.startswith("Ho guardato")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_check_that_could_not_run_leaves_the_question_exactly_as_it_was(monkeypatch):
    """
    Non aver verificato non e' «non sono riuscito a verificare».

    Se il modello non risponde, la domanda resta parola per parola quella di
    prima e nessuno racconta che qualcosa e' stato controllato. Una verifica
    assente travestita da verifica fallita e' una bugia che sopravvive.
    """
    async def body():
        client, db = await _db()
        uid = f"u_cl_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.settle import try_to_settle_it

            when = datetime.now(timezone.utc) + timedelta(days=10)
            live = await _an_appointment(db, uid, title="Andata", when=when)
            opportunity = await _an_initiative(
                db, uid, refs=[live],
                question="A che ora parti?", offer="posso verificare",
            )

            _install_opportunity_model(monkeypatch, FakeModel([None]))
            outcome = await try_to_settle_it(db, uid, opportunity)

            assert outcome["outcome"] == "unavailable"
            assert opportunity.requires_clarification is True
            assert opportunity.clarifying_question == "A che ora parti?"
            assert opportunity.what_ora_can_do == "posso verificare"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_check_sees_the_rows_that_share_a_title_and_their_state():
    """
    §6, e il difetto vero trovato provandolo su una vita reale.

    «È stato annullato» e' una frase su una riga, non su un viaggio. Di quel
    viaggio il calendario teneva quattro copie, tre annullate e una viva; le
    note di annullamento erano appese alla riga viva, e chi ha provato a
    rispondere con quelle davanti ha concluso che il viaggio era annullato.
    Era falso, ed era peggio della domanda che voleva evitare.

    Quindi accanto alla riga di cui si parla ci vanno le omonime con il loro
    stato, e ogni nota dice di quale riga stava parlando.
    """
    async def body():
        client, db = await _db()
        uid = f"u_cl_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.settle import what_ora_can_read_alone

            when = datetime.now(timezone.utc) + timedelta(days=10)
            live = await _an_appointment(db, uid, title="Andata → Vibo", when=when)
            dead = await _an_appointment(
                db, uid, title="Andata → Vibo", when=when, status="cancelled",
            )
            await _a_note(
                db, uid, about=live, written_about=dead,
                says="Il viaggio di andata è stato annullato.",
            )

            at_hand = await what_ora_can_read_alone(db, uid, [live])

            twins = at_hand["other_rows_that_look_like_the_same_thing"]
            assert [r["ref"] for r in twins] == [dead]
            assert twins[0]["status"] == "cancelled", (
                "la copia morta arriva senza dire che è morta"
            )
            note = at_hand["links_somebody_already_decided"][0]
            assert note["the_row_it_was_written_about"] == dead, (
                "«è stato annullato» sembra detto della riga viva"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_reading_what_is_already_filed_asks_nobody_for_permission():
    """
    §4 + §16: capire, confrontare, preparare non chiedono consenso.

    Strutturale, perche' e' il tipo di cosa che si aggiunge «per prudenza» sei
    mesi dopo: in tutto il tentativo non si tocca l'autorita', non nasce un
    intento d'azione, e non si scrive niente fuori dall'opportunita' stessa.
    """
    source = (HERE / "opportunities" / "settle.py").read_text(encoding="utf-8")
    for forbidden in ("authority", "ActionIntent", "consent", "grant",
                      "insert_one", "update_one", "delete_"):
        assert forbidden not in source, (
            f"il tentativo di verifica fa qualcosa che non gli compete: {forbidden}"
        )


def test_pure_information_work_creates_no_goal_and_no_action_intent(monkeypatch):
    """
    §15 di nuovo, sul caso che qui e' facile sbagliare: ORA ha appena fatto
    del lavoro — ha letto, confrontato, concluso — e non e' nato niente da
    portare avanti. Una frase al momento giusto e' un esito completo.
    """
    async def body():
        client, db = await _db()
        uid = f"u_cl_{uuid.uuid4().hex[:8]}"
        try:
            from opportunities.settle import try_to_settle_it

            when = datetime.now(timezone.utc) + timedelta(days=10)
            live = await _an_appointment(db, uid, title="Andata", when=when)
            await _a_note(db, uid, about=live, written_about=live,
                          says="Spostata alle 06:00.")
            opportunity = await _an_initiative(
                db, uid, refs=[live], question="A che ora parti?",
                offer="posso verificare",
            )

            _install_opportunity_model(monkeypatch, FakeModel([{
                "settled": True,
                "answer": "Ho guardato: la partenza è alle 06:00.",
                "what_it_rests_on": [live],
            }]))
            await try_to_settle_it(db, uid, opportunity)

            assert await db.agent_goals.count_documents({"owner_id": uid}) == 0
            assert await db.action_intents.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_instruction_puts_the_question_last():
    """
    §5: NEVER ASK THE USER TO DO INFORMATION WORK ORA CAN DO ITSELF.

    Scritto dove si decide cosa dire, non applicato da un `if` a valle.
    """
    source = (HERE / "opportunities" / "reasoning.py").read_text(encoding="utf-8")
    assert "Never ask them for something you could find out yourself" in source
    assert "A question is what is left when that look " in source


def test_the_card_stays_human():
    """
    §8: nessuna etichetta tecnica in quello che una persona legge.

    `for_home` porta cosa ORA ha notato, perche' conta, cosa ha fatto o puo'
    fare, e la domanda solo se e' rimasta. Il gradino, la rilevanza e la
    fiducia restano dietro: sono il modo in cui il sistema pensa, e nessuno
    dice «rilevanza alta» della propria settimana.
    """
    from opportunities.models import Opportunity

    card = Opportunity(
        owner_id="u",
        identity_key="abc",
        semantic_summary="Ci sono due voci per lo stesso giorno.",
        why_it_matters="Rischi di regolarti sulla versione sbagliata.",
        why_now="Mancano dieci giorni.",
        initiative="recommend",
        what_ora_can_do="Ho guardato il calendario: ci sono tutte e due.",
        requires_clarification=True,
        clarifying_question="Parti alle 06:00?",
        relevance="high",
        confidence="strong",
    ).for_home()

    assert set(card) == {
        "id", "title", "why_now", "what_ora_can_do", "question", "seen",
    }
    for wiring in ("recommend", "high", "strong", "initiative", "relevance"):
        assert wiring not in str(card), card


def test_the_line_and_the_card_read_the_same_state():
    """
    §1: una sola decisione, letta due volte — mai due decisioni.

    Chi scrive la riga chiede a `SurfacingService.visible`, che e' la stessa
    funzione che riempie Home. Se un giorno qualcuno gli desse una lista
    diversa — «tutto cio' che e' attivo», «tutto cio' che e' recente» — le due
    meta' della schermata tornerebbero a raccontare cose diverse.
    """
    source = (HERE / "delivery" / "service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    body = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_what_is_standing"
    ]
    assert body, "la riga non legge nessuno stato"
    running = ast.unparse(body[0])
    assert "SurfacingService" in running and "visible" in running
