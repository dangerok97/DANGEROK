"""
V3.10 — la scheda di un appuntamento, e il pulsante che lo toglie davvero.

    UN EVENTO DEL CALENDARIO NON E' UNA COSA DA ORGANIZZARE. E' UNA COSA CHE HAI.

Toccare «Visita dentistica — Studio Bianchi» in Home apriva un flusso generico
dell'action engine che chiedeva «vuoi preparare un esame oppure creare un
evento?». Non era un errore di rendering: l'azione primaria della carta era
`/action/open`, cioe' l'action engine senza dirgli di cosa si parlasse. Su un
appuntamento che aveva gia' nome, ora e luogo.

Queste prove tengono ferme tre cose: dove porta il tocco, cosa la scheda
mostra, e cosa vuol dire «eliminato» — che e' una parola che si puo' dire solo
dopo aver riletto il provider e non aver piu' trovato niente.
"""
from __future__ import annotations

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
ACCOUNT = "qa.detail@example.com"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("connector_instances", "ingestion_events", "life_nodes",
                 "calendar_event_drafts", "connected_signals", "agent_receipts",
                 "agent_action_attempts", "permission_consents", "ambient_wakes",
                 "meaningful_changes"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


async def _instance(db, uid):
    instance_id = f"inst_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    await db.connector_instances.insert_one({
        "id": instance_id, "user_id": uid, "connector_id": "calendar_google",
        "status": "connected", "secret_reference": "ref",
        "metadata": {"account_email": ACCOUNT},
        "selected_resource_ids": [ACCOUNT], "cursor": {},
        "created_at": now, "updated_at": now, "last_sync_at": now,
    })
    return instance_id


async def _event_row(db, uid, instance_id, *, external_id, title, starts_at,
                     description="", location=""):
    from ingestion.event_model import IngestionEventRepository
    from ingestion.normalizer import GoogleCalendarNormalizer

    normalized = GoogleCalendarNormalizer(
        connector_id="calendar_google", connector_instance_id=instance_id,
    ).normalize(
        raw={
            "id": external_id, "status": "confirmed", "summary": title,
            "description": description, "location": location,
            "start": {"dateTime": starts_at.isoformat()},
            "end": {"dateTime": (starts_at + timedelta(hours=1)).isoformat()},
            "organizer": {"email": ACCOUNT}, "attendees": [],
            "etag": uuid.uuid4().hex[:8], "updated": starts_at.isoformat(),
        },
        calendar_id=ACCOUNT, calendar_name=ACCOUNT,
    )
    await IngestionEventRepository(db).insert(
        user_id=uid, connector_id="calendar_google",
        connector_instance_id=instance_id, external_id=external_id,
        external_version=normalized.source_hash,
        source_type="calendar_google", source_record_type="calendar_event",
        raw_reference={"calendar_id": ACCOUNT},
        normalized_payload=normalized.to_dict(),
        payload_hash=normalized.source_hash,
        source_created_at=None, source_updated_at=starts_at.isoformat(),
        provenance={"connector_id": "calendar_google"},
        sensitivity="personal", status="processed",
    )
    found = await db.ingestion_events.find_one(
        {"user_id": uid, "external_id": external_id}, {"_id": 0, "id": 1},
    )
    return found["id"]


def _soon(days=4, hour=10):
    from zoneinfo import ZoneInfo

    return (datetime.now(ZoneInfo("Europe/Rome")) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0,
    )


class _Vault:
    async def get(self, ref, *, user_id):
        return {"access_token": "t", "refresh_token": "r",
                "expires_at": "2999-01-01T00:00:00+00:00"}

    async def rotate(self, ref, *, payload):
        return ref


class _Calendar:
    """Un calendario che accetta la cancellazione e poi la conferma."""

    def __init__(self, *, still_there_after_delete=False):
        self.deleted = []
        self.still_there = still_there_after_delete
        self.provider = self
        self.vault = _Vault()

    async def _get_access_token(self, *, user_id, instance):
        return "t"

    async def delete_event(self, *, access_token, calendar_id, event_id):
        self.deleted.append(event_id)
        return True

    async def get_event(self, *, access_token, calendar_id, event_id):
        if self.still_there:
            return {"id": event_id, "status": "confirmed"}
        return {"id": event_id, "status": "cancelled"}


def _install(monkeypatch, calendar):
    import deps

    monkeypatch.setattr(deps, "get_google_calendar_service", lambda: calendar)


async def _allow(db, uid):
    """
    Il permesso sul connettore, che e' un'altra cosa dal consenso all'atto.

    Senza, ogni persona vera risolve come «non permesso» e solo i test sono
    verdi — che e' esattamente il modo in cui le due cose erano andate alla
    deriva una volta.
    """
    from agent.capabilities import _CONNECTOR
    from permissions.service import PermissionService

    capability = "calendar.write"
    await PermissionService(db).grant(
        user_id=uid, capability_id=capability,
        connector_id=_CONNECTOR.get(capability, "calendar_google"),
    )


# ---------------------------------------------------------------------------
# Dove porta il tocco
# ---------------------------------------------------------------------------

def test_an_event_card_opens_the_event_and_not_a_generic_flow():
    """
    §B: il tocco su un appuntamento porta alla sua scheda.

    L'azione primaria era «Organizza» verso `/action/open`. Con quella rotta
    l'action engine parte senza sapere di cosa si parli e chiede «vuoi
    preparare un esame oppure creare un evento?» — di un evento che era gia'
    li'. Qui si tiene fermo che la rotta porti l'identificativo con se'.
    """
    from home.actions_catalog import actions_for
    from home.models import HomeItem

    item = HomeItem(
        id="hi_1", type="event", subtype="google_calendar",
        title="Visita dentistica — Studio Bianchi",
        source_type="google_calendar", source_id="ing_abc",
        start_at=_soon().isoformat(), status="open", confidence=0.9,
        created_at="", updated_at="", location="Studio Bianchi",
    )
    acts = actions_for(item)
    primary = next(a for a in acts if a.primary)
    assert primary.route == "/calendar-event/ing_abc"
    assert primary.kind == "navigate"
    assert not any(
        (a.route or "").startswith("/action/") for a in acts
    ), "una carta di calendario porta ancora all'action engine"


def test_a_visit_from_the_calendar_opens_the_event_too():
    """La stessa cosa quando il titolo la fa classificare come «visita»."""
    from home.actions_catalog import actions_for
    from home.models import HomeItem

    item = HomeItem(
        id="hi_2", type="visit", subtype="medical", title="Visita dentistica",
        source_type="life_node", source_id="node_1",
        start_at=_soon().isoformat(), status="open", confidence=0.8,
        created_at="", updated_at="",
    )
    primary = next(a for a in actions_for(item) if a.primary)
    assert primary.route == "/calendar-event/node_1"


# ---------------------------------------------------------------------------
# Cosa mostra la scheda
# ---------------------------------------------------------------------------

def test_the_detail_is_made_of_sentences_and_never_of_identifiers():
    """
    §B: titolo, giorno, ora, posto, da dove arriva. Niente id, niente JSON.

    Il campo note e' quello che rischia di piu': ORA ci scrive dentro la
    propria contabilita' — «Rif. documento ORA: ai_core_conversation» — e su
    una schermata che dice «Note» quella riga e' rumore tecnico mostrato a una
    persona.
    """
    async def body():
        client, db = await _db()
        uid = f"det_{uuid.uuid4().hex[:8]}"
        try:
            from home.calendar_event import event_detail

            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            row_id = await _event_row(
                db, uid, instance_id, external_id="ev_det",
                title="Visita dentistica — Studio Bianchi", starts_at=_soon(),
                location="Studio Bianchi",
                description=(
                    "Portare il referto.\n"
                    "Luogo: Studio Bianchi\n"
                    "Creato da ORA — Life OS\n"
                    "Rif. documento ORA: ai_core_conversation"
                ),
            )

            found = await event_detail(db, uid, row_id)

            assert found["title"] == "Visita dentistica — Studio Bianchi"
            assert found["location"] == "Studio Bianchi"
            assert found["state"] == "in calendario"
            assert found["provider"] == "Google Calendar"
            # Le note della persona restano; la nostra contabilita' no.
            assert found["description"] == "Portare il referto."
            blob = str(found)
            for technical in ("capability", "effect_scope", "connector_id",
                              "normalized_payload", "ingestion_status"):
                assert technical not in blob, f"in scheda compare «{technical}»"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_detail_can_be_asked_for_by_either_name():
    """La Home passa l'id della riga, un link puo' passare quello di Google."""
    async def body():
        client, db = await _db()
        uid = f"det_{uuid.uuid4().hex[:8]}"
        try:
            from home.calendar_event import event_detail

            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            row_id = await _event_row(
                db, uid, instance_id, external_id="ev_two_names",
                title="Visita", starts_at=_soon(),
            )
            by_row = await event_detail(db, uid, row_id)
            by_google = await event_detail(db, uid, "ev_two_names")
            assert by_row and by_google
            assert by_row["title"] == by_google["title"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Eliminare
# ---------------------------------------------------------------------------

def test_deleting_uses_the_provider_identity_and_verifies_before_saying_so(monkeypatch):
    """
    §D/E: cancellare e' un effetto sul calendario di qualcun altro.

    Passa dal manico che l'evento ha su Google — non da un id nostro — e
    quello che torna dice «eliminato» solo dopo che una rilettura non lo ha
    piu' trovato attivo.
    """
    async def body():
        client, db = await _db()
        uid = f"det_{uuid.uuid4().hex[:8]}"
        try:
            from home.calendar_event import delete_event

            calendar = _Calendar()
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            row_id = await _event_row(
                db, uid, instance_id, external_id="ev_del",
                title="Visita dentistica — Studio Bianchi", starts_at=_soon(),
            )

            out = await delete_event(
                db, uid, row_id,
                confirmed_title="Visita dentistica — Studio Bianchi",
            )

            assert out["ok"] is True
            assert out["verified"] is True
            assert out["say_it_as"] == "eliminato"
            assert calendar.deleted == ["ev_del"], (
                "non ha cancellato l'evento che ha su Google"
            )
            row = await db.ingestion_events.find_one(
                {"user_id": uid, "external_id": "ev_del"}, {"_id": 0},
            )
            assert row["normalized_payload"]["status"] == "cancelled"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_nothing_is_called_deleted_while_the_provider_still_has_it(monkeypatch):
    """
    §D: ACCETTATO DAL PROVIDER NON E' SPARITO.

    Google puo' rispondere 204 e avere ancora l'evento — un errore di
    propagazione, un calendario sbagliato, una ricorrenza. La rilettura e'
    l'unica prova, e senza di essa non si dice niente.
    """
    async def body():
        client, db = await _db()
        uid = f"det_{uuid.uuid4().hex[:8]}"
        try:
            from home.calendar_event import delete_event

            calendar = _Calendar(still_there_after_delete=True)
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            row_id = await _event_row(
                db, uid, instance_id, external_id="ev_stuck",
                title="Visita", starts_at=_soon(),
            )

            out = await delete_event(db, uid, row_id, confirmed_title="Visita")

            assert out["ok"] is False
            assert out["reason"] == "not_confirmed_gone"
            assert not out.get("say_it_as")
            row = await db.ingestion_events.find_one(
                {"user_id": uid, "external_id": "ev_stuck"}, {"_id": 0},
            )
            assert row["normalized_payload"]["status"] != "cancelled", (
                "l'archivio dice cancellato di una cosa che c'e' ancora"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_confirmation_given_for_one_event_does_not_delete_another(monkeypatch):
    """
    §D: UNA CONFERMA GENERICA NON VALE PER UN ALTRO EVENTO.

    Il «sì» viaggia con il titolo che la persona aveva davanti. Se non e'
    quello, non si cancella niente — ed e' l'unico modo per cui un sì dato a
    una visita non arrivi alla cena di sabato.
    """
    async def body():
        client, db = await _db()
        uid = f"det_{uuid.uuid4().hex[:8]}"
        try:
            from home.calendar_event import delete_event

            calendar = _Calendar()
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            row_id = await _event_row(
                db, uid, instance_id, external_id="ev_cena",
                title="Cena con Marta", starts_at=_soon(days=5, hour=20),
            )

            out = await delete_event(
                db, uid, row_id, confirmed_title="Visita dentistica",
            )

            assert out["ok"] is False
            assert out["reason"] == "confirmation_does_not_match"
            assert calendar.deleted == [], "ha cancellato l'evento sbagliato"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_deleting_twice_says_the_same_thing_and_does_it_once(monkeypatch):
    """Un pulsante toccato due volte non e' due effetti."""
    async def body():
        client, db = await _db()
        uid = f"det_{uuid.uuid4().hex[:8]}"
        try:
            from home.calendar_event import delete_event

            calendar = _Calendar()
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            row_id = await _event_row(
                db, uid, instance_id, external_id="ev_twice",
                title="Visita", starts_at=_soon(),
            )

            first = await delete_event(db, uid, row_id, confirmed_title="Visita")
            second = await delete_event(db, uid, row_id, confirmed_title="Visita")

            assert first["ok"] and second["ok"]
            assert second["verified"] is True
            assert calendar.deleted == ["ev_twice"], (
                "la seconda pressione ha cancellato di nuovo"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_deleted_event_disappears_from_the_home_screen(monkeypatch):
    """Home, striscia del calendario e prossimi appuntamenti: tutti e tre."""
    async def body():
        client, db = await _db()
        uid = f"det_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events
            from home.calendar_event import delete_event

            calendar = _Calendar()
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            row_id = await _event_row(
                db, uid, instance_id, external_id="ev_home",
                title="Visita dentistica — Studio Bianchi", starts_at=_soon(),
            )

            before, _ = await load_google_calendar_events(db, uid)
            assert [i.title for i in before] == ["Visita dentistica — Studio Bianchi"]

            await delete_event(
                db, uid, row_id,
                confirmed_title="Visita dentistica — Studio Bianchi",
            )

            after, _ = await load_google_calendar_events(db, uid)
            assert after == [], "la Home mostra ancora un evento cancellato"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_our_own_deletion_is_recognised_as_our_own_work(monkeypatch):
    """
    §F: la cancellazione fatta da ORA non e' una novita' del mondo.

    Il sync successivo la rilegge, e senza questa riconoscibilita' la
    tratterebbe come un cambiamento esterno: un goal, una consegna, una
    sveglia — per una cosa che abbiamo appena fatto noi.
    """
    async def body():
        client, db = await _db()
        uid = f"det_{uuid.uuid4().hex[:8]}"
        try:
            from connected.calendar_sensor import _ora_handles
            from home.calendar_event import delete_event

            calendar = _Calendar()
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            row_id = await _event_row(
                db, uid, instance_id, external_id="ev_ours",
                title="Visita", starts_at=_soon(),
            )

            await delete_event(db, uid, row_id, confirmed_title="Visita")

            ours = await _ora_handles(db, uid)
            assert "ev_ours" in ours, (
                "il sensore non riconosce come nostra una cancellazione nostra"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Freschezza
# ---------------------------------------------------------------------------

def test_a_calendar_is_looked_at_every_minute_and_a_mailbox_every_two():
    """
    §A: un quarto d'ora di ritardo e' un calendario che non e' il tuo.

    I numeri sono decisioni di costo — quota del provider, batteria — e non
    giudizi su cosa conti nella vita di qualcuno.
    """
    from connected.polling import interval_for

    assert interval_for("calendar").total_seconds() <= 60
    assert interval_for("email").total_seconds() <= 120
    assert interval_for("calendar") < interval_for("email")


def test_what_is_promised_includes_the_time_the_loop_itself_takes():
    """
    §A/I: «entro un minuto» deve valere nel caso peggiore, non in quello medio.

    Un cambiamento fatto un istante dopo una lettura aspetta la cadenza *piu'*
    il tempo che passa fra un giro e l'altro. Con 60 s di cadenza e un giro
    ogni 15 s fanno 75 s, e misurato sull'account vero facevano 76 e 81: cioe'
    fuori da quello che era stato promesso. Il numero della cadenza e' la
    promessa meno il giro.
    """
    from ambient.runtime import TICK_SECONDS
    from connected.polling import interval_for

    # Il bersaglio tipico del calendario e' 30 s; il cancello duro 60 s.
    promised = {"calendar": 30, "email": 120}
    for kind, limit in promised.items():
        worst = interval_for(kind).total_seconds() + TICK_SECONDS
        assert worst <= limit, (
            f"{kind}: nel caso peggiore si vede dopo {worst:.0f}s, "
            f"promessi {limit}s"
        )


def test_the_loop_looks_more_often_than_the_tightest_cadence():
    """Una cadenza di un minuto con un giro ogni due non e' una cadenza."""
    from ambient.runtime import TICK_SECONDS
    from connected.polling import interval_for

    assert TICK_SECONDS < interval_for("calendar").total_seconds()


def test_a_provider_that_fails_is_asked_less_often_not_more():
    """§A: backoff, con un tetto."""
    from connected.polling import BACKOFF_CAP_MINUTES, interval_for

    steps = [interval_for("calendar", n).total_seconds() for n in range(0, 8)]
    assert steps == sorted(steps)
    assert steps[1] > steps[0]
    # Il tetto e' una garanzia, non un traguardo: partendo da 45 s il
    # raddoppio si ferma a 2880 s e l'ora non la tocca mai. Quello che deve
    # valere e' che non la superi.
    assert max(steps) <= BACKOFF_CAP_MINUTES * 60
    assert steps[-1] > steps[0] * 8, "il backoff cresce troppo poco"


def test_nothing_asks_a_model_when_to_synchronise():
    """
    §A5: la cadenza e' aritmetica, non un giudizio.

    Guardia strutturale: nel modulo che decide quando leggere non deve esserci
    nessuna traccia di una chiamata a un modello. Una riga sola basterebbe a
    trasformare una decisione di costo in una decisione di prodotto presa da
    un modello, e a farla pagare a ogni giro.
    """
    source = (Path(_BACKEND) / "connected/polling.py").read_text(encoding="utf-8")
    for forbidden in ("_ask_model", "interpret_signal", "decide_link",
                      "llm", "gemini", "openai"):
        assert forbidden not in source, (
            f"il polling nomina «{forbidden}»: la cadenza non e' piu' aritmetica"
        )


def test_the_write_path_files_what_it_just_wrote_without_waiting():
    """
    §A3: quello che ORA ha appena scritto non aspetta il prossimo giro.

    Guardia strutturale sul percorso di scrittura: dopo la rilettura ci deve
    essere l'archiviazione immediata. Un minuto di «non c'e' niente» dopo aver
    detto «segnamelo» e' la schermata che dice che non l'hai fatto.
    """
    source = (
        Path(_BACKEND) / "conversation_engine/ai_core/tools/calendar_caps.py"
    ).read_text(encoding="utf-8")
    assert source.count("_file_it_now(") >= 3, (
        "la scrittura non archivia subito quello che ha riletto"
    )
    after_read = source.split("seen, observed = await _read_back")
    for chunk in after_read[1:]:
        head = chunk[:400]
        assert "_file_it_now" in head, (
            "una rilettura non e' seguita dall'archiviazione immediata"
        )


def test_no_manual_sync_button_survives_on_the_connection_screens():
    """
    §A: LA PERSONA NON SINCRONIZZA LA PROPRIA VITA. LO FA ORA.

    Guardia sulle schermate dove si vedono le sorgenti collegate: li' non deve
    esserci niente da premere per andare a prendere i propri dati. La parola
    puo' ancora comparire in un commento che spiega perche' il pulsante non
    c'e' piu', e in un'etichetta di stato — «Sincronizzato ieri» racconta,
    non chiede.
    """
    app = Path(_BACKEND).parent / "frontend"
    screens = [
        app / "app/settings.tsx",
        app / "app/account/permessi.tsx",
    ]
    offenders = []
    for path in screens:
        if not path.exists():
            continue
        inside_comment = False
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1,
        ):
            naked = line.strip()
            if "{/*" in naked or naked.startswith("/*"):
                inside_comment = True
            was_comment = inside_comment
            if "*/" in naked:
                inside_comment = False
            if was_comment or naked.startswith(("//", "*")):
                continue
            if "Sincronizzat" in naked:   # «Sincronizzato ieri»: uno stato
                continue
            if "Sincronizza" in naked:
                offenders.append(f"{path.name}:{number}")
    assert not offenders, f"c'è ancora qualcosa da premere: {offenders}"


# ---------------------------------------------------------------------------
# Un solo modo di togliere un impegno
# ---------------------------------------------------------------------------

async def _draft_for(db, uid, *, draft_id, external_id, title):
    """La bozza che ORA tiene di un evento che ha scritto su Google."""
    await db.calendar_event_drafts.insert_one({
        "id": draft_id, "user_id": uid, "title": title,
        "google_event_id": external_id,
        "google_calendar_id": ACCOUNT,
        "status": "confirmed",
        "start_datetime": _soon().isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def test_the_conversation_delete_uses_the_same_provider_identity(monkeypatch):
    """
    §1: nessun secondo motore di cancellazione.

    `cancel_calendar_event` aveva un percorso suo: cancellava e si fidava
    della risposta. Due percorsi vuol dire due idee di cosa significhi
    «eliminato», e quella con la verifica piu' debole vince sempre, perche' e'
    quella che dice di si' anche quando non e' vero. Adesso la conversazione
    passa dallo stesso posto della scheda: stesso manico del provider, stessa
    rilettura.
    """
    async def body():
        client, db = await _db()
        uid = f"conv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            calendar = _Calendar()
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            await _event_row(db, uid, instance_id, external_id="ev_conv",
                             title="Visita dentistica", starts_at=_soon())
            await _draft_for(db, uid, draft_id="ced_conv",
                             external_id="ev_conv", title="Visita dentistica")

            obs = await calendar_caps.cancel_calendar_event(
                {"calendar_ref": "calendar:ced_conv"},
                {"user_id": uid, "db": db, "user_message": "elimina la visita"},
            )

            assert obs.status == "ok"
            assert obs.payload["operation"] == "cancelled"
            assert obs.payload["verified"] is True
            assert obs.payload["say_it_as"] == "eliminato"
            assert calendar.deleted == ["ev_conv"], (
                "la conversazione non ha cancellato l'evento che ha su Google"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_conversation_never_says_deleted_before_the_reading_confirms(monkeypatch):
    """§1: «eliminato» resta una parola che si dice dopo aver guardato."""
    async def body():
        client, db = await _db()
        uid = f"conv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            calendar = _Calendar(still_there_after_delete=True)
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            await _event_row(db, uid, instance_id, external_id="ev_stubborn",
                             title="Visita", starts_at=_soon())
            await _draft_for(db, uid, draft_id="ced_stub",
                             external_id="ev_stubborn", title="Visita")

            obs = await calendar_caps.cancel_calendar_event(
                {"calendar_ref": "calendar:ced_stub"},
                {"user_id": uid, "db": db, "user_message": "elimina la visita"},
            )

            assert obs.status == "failed"
            assert obs.payload["failure_kind"] == "not_confirmed_gone"
            assert not obs.payload.get("say_it_as")
            assert "non dire" in obs.payload["reason"].lower()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_asking_the_conversation_twice_is_one_deletion(monkeypatch):
    """§1: chiederlo due volte non e' cancellarlo due volte."""
    async def body():
        client, db = await _db()
        uid = f"conv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            calendar = _Calendar()
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            await _event_row(db, uid, instance_id, external_id="ev_twice_conv",
                             title="Visita", starts_at=_soon())
            await _draft_for(db, uid, draft_id="ced_twice",
                             external_id="ev_twice_conv", title="Visita")
            runtime = {"user_id": uid, "db": db, "user_message": "elimina la visita"}

            first = await calendar_caps.cancel_calendar_event(
                {"calendar_ref": "calendar:ced_twice"}, runtime)
            second = await calendar_caps.cancel_calendar_event(
                {"calendar_ref": "calendar:ced_twice"}, runtime)

            assert first.status == "ok" and second.status == "ok"
            assert second.payload["operation"] == "already_cancelled"
            assert calendar.deleted == ["ev_twice_conv"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_the_conversation_deleted_leaves_the_home_screen(monkeypatch):
    """§1: e sparisce anche dalla Home, non solo dalla frase."""
    async def body():
        client, db = await _db()
        uid = f"conv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps
            from home.adapters.google_calendar import load_google_calendar_events

            calendar = _Calendar()
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            await _event_row(db, uid, instance_id, external_id="ev_conv_home",
                             title="Visita dentistica", starts_at=_soon())
            await _draft_for(db, uid, draft_id="ced_home",
                             external_id="ev_conv_home", title="Visita dentistica")

            before, _ = await load_google_calendar_events(db, uid)
            assert [i.title for i in before] == ["Visita dentistica"]

            await calendar_caps.cancel_calendar_event(
                {"calendar_ref": "calendar:ced_home"},
                {"user_id": uid, "db": db, "user_message": "elimina la visita"},
            )

            after, _ = await load_google_calendar_events(db, uid)
            assert after == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_deletion_from_the_conversation_is_our_own_work_too(monkeypatch):
    """§1: e il giro successivo non la scambia per una novita' del mondo."""
    async def body():
        client, db = await _db()
        uid = f"conv_{uuid.uuid4().hex[:8]}"
        try:
            from connected.calendar_sensor import _ora_handles
            from conversation_engine.ai_core.tools import calendar_caps

            calendar = _Calendar()
            _install(monkeypatch, calendar)
            await _allow(db, uid)
            instance_id = await _instance(db, uid)
            await _event_row(db, uid, instance_id, external_id="ev_conv_ours",
                             title="Visita", starts_at=_soon())
            await _draft_for(db, uid, draft_id="ced_ours",
                             external_id="ev_conv_ours", title="Visita")

            await calendar_caps.cancel_calendar_event(
                {"calendar_ref": "calendar:ced_ours"},
                {"user_id": uid, "db": db, "user_message": "elimina la visita"},
            )

            assert "ev_conv_ours" in await _ora_handles(db, uid)
            row = await db.ingestion_events.find_one(
                {"user_id": uid, "external_id": "ev_conv_ours"}, {"_id": 0},
            )
            assert row["ora_originated"] is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_there_is_only_one_place_that_deletes_a_calendar_event():
    """
    Guardia strutturale: il tool della conversazione non cancella da solo.

    Se un domani qualcuno rimette li' una chiamata al provider, questa prova
    lo dice prima che le due idee di «eliminato» ricomincino a divergere.
    """
    source = (
        Path(_BACKEND) / "conversation_engine/ai_core/tools/calendar_caps.py"
    ).read_text(encoding="utf-8")
    tool = source.split("async def cancel_calendar_event(", 1)[1]
    for own_engine in ("delete_remote", "delete_event(access_token",
                       "provider.delete"):
        assert own_engine not in tool, (
            f"il tool cancella ancora per conto suo: «{own_engine}»"
        )
    assert "from home.calendar_event import" in tool


# ---------------------------------------------------------------------------
# Riletture invariate
# ---------------------------------------------------------------------------

async def _ingest(db, uid, instance_id, *, external_id, title, starts_at,
                  status="confirmed"):
    """Una lettura del calendario, fatta passare dal pipeline vero."""
    import deps

    raw = {
        "id": external_id, "status": status, "summary": title,
        "start": {"dateTime": starts_at.isoformat()},
        "end": {"dateTime": (starts_at + timedelta(hours=1)).isoformat()},
        "organizer": {"email": ACCOUNT}, "attendees": [],
        "etag": "e1", "updated": starts_at.isoformat(),
    }
    return await deps.get_ingestion_service().ingest_calendar_events(
        user_id=uid, connector_id="calendar_google",
        connector_instance_id=instance_id, calendar_id=ACCOUNT,
        calendar_name=ACCOUNT, raw_events=[raw],
    )


def test_a_hundred_unchanged_readings_leave_one_row():
    """
    §2: UNA RILETTURA CHE NON HA VISTO NIENTE NON E' UN'OSSERVAZIONE.

    Il calendario si rilegge ogni minuto. Prima ogni rilettura scriveva una
    riga intera e poi la marcava «skipped»: su questo account un compleanno
    ricorrente ne aveva undici, e in tutto c'erano 229 righe in piu' del
    necessario per 43 eventi. Non era solo spazio — quelle righe contavano
    come impegni per chi leggeva, e riempivano la finestra della Home al
    punto che gli appuntamenti veri restavano fuori.
    """
    async def body():
        client, db = await _db()
        uid = f"dedupe_{uuid.uuid4().hex[:8]}"
        try:
            instance_id = await _instance(db, uid)
            when = _soon()
            for _ in range(100):
                await _ingest(db, uid, instance_id, external_id="ev_fermo",
                              title="Compleanno", starts_at=when)

            rows = await db.ingestion_events.count_documents(
                {"user_id": uid, "external_id": "ev_fermo"},
            )
            assert rows == 1, f"cento riletture hanno lasciato {rows} righe"

            row = await db.ingestion_events.find_one(
                {"user_id": uid, "external_id": "ev_fermo"}, {"_id": 0},
            )
            # Quello che serve sapere di una rilettura invariata c'e' ancora,
            # in due campi invece che in cento righe.
            assert row["times_seen_unchanged"] == 99
            assert row["last_seen_at"]
            assert row["provenance"]["connector_id"] == "calendar_google"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_real_change_still_makes_a_new_version():
    """§2: e quando qualcosa cambia davvero, la riga nuova c'e'."""
    async def body():
        client, db = await _db()
        uid = f"dedupe_{uuid.uuid4().hex[:8]}"
        try:
            from ingestion.reading import plain

            instance_id = await _instance(db, uid)
            when = _soon()
            await _ingest(db, uid, instance_id, external_id="ev_mosso",
                          title="Visita", starts_at=when)
            await _ingest(db, uid, instance_id, external_id="ev_mosso",
                          title="Visita", starts_at=when + timedelta(hours=3))

            rows = await db.ingestion_events.find(
                {"user_id": uid, "external_id": "ev_mosso"}, {"_id": 0},
            ).to_list(10)
            assert len(rows) == 2, "un cambiamento vero non ha lasciato traccia"
            alive = [r for r in rows if r["ingestion_status"] != "superseded"]
            assert len(alive) == 1, "la versione precedente non e' stata superata"
            assert alive[0]["supersedes_event_id"]
            # E la riga viva e' quella nuova, non quella di prima.
            moved_to = (when + timedelta(hours=3)).astimezone(timezone.utc)
            seen = str(plain(alive[0]["normalized_payload"])["starts_at"])
            assert seen[:16] == moved_to.isoformat()[:16]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_cancellation_is_a_change_and_is_recorded_as_one():
    """§2: annullato non e' «uguale a prima»."""
    async def body():
        client, db = await _db()
        uid = f"dedupe_{uuid.uuid4().hex[:8]}"
        try:
            from ingestion.reading import plain

            instance_id = await _instance(db, uid)
            when = _soon()
            await _ingest(db, uid, instance_id, external_id="ev_annullato",
                          title="Visita", starts_at=when)
            await _ingest(db, uid, instance_id, external_id="ev_annullato",
                          title="Visita", starts_at=when, status="cancelled")

            alive = await db.ingestion_events.find(
                {"user_id": uid, "external_id": "ev_annullato",
                 "ingestion_status": {"$ne": "superseded"}}, {"_id": 0},
            ).to_list(10)
            assert len(alive) == 1
            assert plain(alive[0]["normalized_payload"])["status"] == "cancelled"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_home_screen_shows_one_card_however_many_times_it_was_read():
    """§2: e in Home resta un appuntamento, non cento."""
    async def body():
        client, db = await _db()
        uid = f"dedupe_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events

            instance_id = await _instance(db, uid)
            when = _soon()
            for _ in range(50):
                await _ingest(db, uid, instance_id, external_id="ev_home_dedupe",
                              title="Visita dentistica", starts_at=when)

            items, _ = await load_google_calendar_events(db, uid)
            assert [i.title for i in items] == ["Visita dentistica"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_restart_does_not_start_the_pile_again():
    """
    §2: e un riavvio non ricomincia il mucchio.

    Il dedupe guarda quello che c'e' nel database, non quello che ricorda un
    processo: e' proprio la differenza fra un archivio e una cache, ed e' la
    ragione per cui questa prova ricostruisce il servizio da zero.
    """
    async def body():
        client, db = await _db()
        uid = f"dedupe_{uuid.uuid4().hex[:8]}"
        try:
            import deps

            instance_id = await _instance(db, uid)
            when = _soon()
            await _ingest(db, uid, instance_id, external_id="ev_riavvio",
                          title="Visita", starts_at=when)

            # Il «riavvio»: si butta via il servizio costruito e se ne fa uno
            # nuovo, come farebbe un processo appena partito.
            deps._ingestion_service = None
            await _ingest(db, uid, instance_id, external_id="ev_riavvio",
                          title="Visita", starts_at=when)

            rows = await db.ingestion_events.count_documents(
                {"user_id": uid, "external_id": "ev_riavvio"},
            )
            assert rows == 1, "dopo il riavvio ha ricominciato a duplicare"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_old_pile_is_collapsed_without_emptying_the_home_screen():
    """
    §2: la correzione ferma la crescita; questa raccoglie quello che c'era.

    Il rischio della raccolta e' uno solo, ed e' esattamente il sintomo che
    doveva togliere: se resta viva la riga sbagliata — la piu' recente di un
    evento fermo e' una riga «skipped», che la Home esclude — il calendario
    resta pieno e la schermata vuota. Quindi la riga che sopravvive e' quella
    che i lettori leggono.
    """
    async def body():
        client, db = await _db()
        uid = f"tidy_{uuid.uuid4().hex[:8]}"
        try:
            from home.adapters.google_calendar import load_google_calendar_events
            from ingestion.tidy import collapse_unchanged_duplicates

            instance_id = await _instance(db, uid)
            when = _soon()
            row_id = await _event_row(db, uid, instance_id, external_id="ev_pile",
                                      title="Visita dentistica", starts_at=when)
            # Il mucchio di prima: copie identiche marcate «skipped», con la
            # data di lettura piu' recente della riga buona.
            keeper = await db.ingestion_events.find_one(
                {"id": row_id}, {"_id": 0},
            )
            for n in range(20):
                copy = dict(keeper)
                copy["id"] = f"ing_copy_{n}"
                copy["ingestion_status"] = "skipped"
                copy["ingested_at"] = f"2099-01-01T00:00:{n:02d}+00:00"
                await db.ingestion_events.insert_one(copy)

            alive_before = await db.ingestion_events.count_documents(
                {"user_id": uid, "ingestion_status": {"$ne": "superseded"}},
            )
            assert alive_before == 21

            out = await collapse_unchanged_duplicates(db, uid)
            assert out["collapsed"] == 20

            alive_after = await db.ingestion_events.count_documents(
                {"user_id": uid, "ingestion_status": {"$ne": "superseded"}},
            )
            assert alive_after == 1
            items, _ = await load_google_calendar_events(db, uid)
            assert [i.title for i in items] == ["Visita dentistica"], (
                "la raccolta ha svuotato la Home"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_tidy_never_touches_a_row_that_says_something_different():
    """Un hash diverso e' un cambiamento vero, e non e' un doppione."""
    async def body():
        client, db = await _db()
        uid = f"tidy_{uuid.uuid4().hex[:8]}"
        try:
            from ingestion.tidy import collapse_unchanged_duplicates

            instance_id = await _instance(db, uid)
            when = _soon()
            await _event_row(db, uid, instance_id, external_id="ev_diverso",
                             title="Visita", starts_at=when)
            await _event_row(db, uid, instance_id, external_id="ev_diverso",
                             title="Visita spostata", starts_at=when + timedelta(hours=2))

            out = await collapse_unchanged_duplicates(db, uid)
            assert out["collapsed"] == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_next_reading_is_counted_from_when_this_one_finished():
    """
    §I: una cadenza contata dall'inizio del giro non e' una cadenza.

    Il giro tocca piu' sorgenti e dura. Contando da quando e' partito,
    l'ultima sorgente letta si ritrova programmata a pochi secondi da adesso
    — misurato sull'account vero: nove secondi, con la cadenza a
    quarantacinque — e la coda non torna mai vuota.
    """
    async def body():
        client, db = await _db()
        uid = f"sched_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import schedule_next

            started = datetime.now(timezone.utc)
            # Una lettura che ha impiegato mezzo minuto.
            finished = started + timedelta(seconds=30)
            when = await schedule_next(
                db, uid, "src_1", "calendar", failed=False, now=finished,
            )
            from connected.polling import interval_for

            cadence = interval_for("calendar").total_seconds()
            gap = (datetime.fromisoformat(when) - finished).total_seconds()
            assert abs(gap - cadence) <= 1, (
                f"programmata {gap:.0f}s dopo la fine invece della cadenza "
                f"di {cadence:.0f}s"
            )
        finally:
            await db.connected_source_attempts.delete_many({"owner_id": uid})
            client.close()

    _run(body())


def test_the_pass_schedules_from_the_end_when_nobody_drives_the_clock():
    """
    Guardia strutturale: in produzione la programmazione usa l'ora vera.

    Con un orologio passato da fuori — una prova — resta quello, perche' li'
    il punto e' proprio che il tempo non scorra da solo.
    """
    source = (Path(_BACKEND) / "connected/polling.py").read_text(encoding="utf-8")
    assert "now=moment if now is not None else _now()" in source, (
        "il giro programma di nuovo dall'istante in cui e' partito"
    )
