"""
V3.13 Sprint 2 — quello che ORA vede, e cosa non diventa per il fatto di
essere stato visto.

    HO VISTO != SO.
    STESSO ARGOMENTO != STESSA SITUAZIONE.
    PARSED TEXT FIRST, VISION WHEN NEEDED.

Un'immagine che arriva in una conversazione è una fonte nuova della vita di
qualcuno. Fino a ieri il percorso finiva contro una riga — `image_vision_
multimodal: "unavailable"` — e una foto senza testo estraibile diventava un
file «failed» di cui non si poteva dire nemmeno cosa fosse.

Quello che si verifica qui non è che il modello guardi bene: quello si guarda
su immagini vere, e senza un modello raggiungibile non si può nemmeno provare.
Si verifica ciò che il codice possiede, e sono le tre cose che possono fare
danno: che un'osservazione non diventi conoscenza da sola, che un legame senza
una ragione specifica non venga scritto, e che quello che una persona ha
mostrato non finisca da nessuna parte dove non doveva.
"""

from __future__ import annotations

import ast
import os
import sys
import uuid
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)



def _code_only(text: str) -> str:
    """
    Il file senza la sua prosa.

    Una guardia strutturale che legge una docstring sta misurando il commento:
    il paragrafo che spiega perché `bool(text.strip())` era sbagliato non deve
    poter far fallire la verifica che `bool(text.strip())` non c'è più.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False):
                node.body = node.body[1:]
    stripped = ast.unparse(tree)
    return "\n".join(
        "" if line.strip().startswith("#") else line.split("#")[0]
        for line in stripped.splitlines()
    )


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("visual_observations", "life_objects", "documents"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


# ---------------------------------------------------------------------------
# Evidenza, non conoscenza
# ---------------------------------------------------------------------------

def test_what_was_seen_is_an_observation_and_says_so():
    """
    §4 + §9: una foto è evidenza, non conoscenza canonica.

    Un'osservazione nasce `seen` e non ha nessuna strada verso la memoria che
    non passi dalla governance. Se un giorno comparisse un campo che la
    promuove da sola, questo test se ne accorge — ed è la scorciatoia più
    facile da scrivere di tutto lo sprint.
    """
    from visual.models import VisualObservation

    seen = VisualObservation(owner_id="u", what_i_see="Una schermata della banca")
    assert seen.standing == "seen"
    assert set(VisualObservation.model_fields["standing"].annotation.__args__) == {
        "seen", "proposed", "transient",
    }, "gli stati di un'osservazione non sono più tre"

    # E quello che il ragionamento riceve dice da dove viene.
    given = seen.for_ai()
    assert "how_i_know" in given
    assert given["how_i_know"].startswith("L'ho visto in un'immagine")


def test_the_answer_to_how_do_you_know_survives_the_image():
    """
    §8: la provenienza resta, e non promette di poter rileggere una cosa che
    non c'è più.

    Una frase che dice «guarda tu stesso» a proposito di un file cancellato è
    una bugia con una data sopra.
    """
    from visual.models import VisualObservation

    seen = VisualObservation(
        owner_id="u", observed_at="2026-09-11T10:00:00+00:00",
        what_i_see="Uno screenshot del conto",
    )
    said = seen.how_ora_knows()
    assert "2026-09-11" in said
    for promise in ("apri", "riapri", "rileggi", "clicca", "guarda il file"):
        assert promise not in said.lower(), f"la provenienza promette «{promise}»"


def test_nothing_technical_reaches_a_person():
    """§19 + §20: niente id, niente percorsi, niente byte in quello che si legge."""
    from visual.models import VisualObservation

    seen = VisualObservation(
        owner_id="u_0ea6", document_ref="doc_abc123", source_ref="doc_abc123",
        content_fingerprint="deadbeef", mime_type="image/png",
        what_i_see="Una schermata", readability="partially_readable",
    )
    read = str(seen.for_human())
    for leak in ("doc_abc123", "deadbeef", "u_0ea6", "image/png", "vis_"):
        assert leak not in read, f"una persona legge «{leak}»"
    # E il grado di leggibilità è in italiano, non un'etichetta.
    assert seen.for_human()["quanto_riesco_a_leggere"] == "si legge in parte"


# ---------------------------------------------------------------------------
# Legare, e non legare
# ---------------------------------------------------------------------------

def test_a_tie_without_a_reason_is_not_written():
    """
    §6: STESSO ARGOMENTO NON VUOL DIRE STESSA SITUAZIONE.

    Un preventivo di mutuo può riguardare l'acquisto di quella casa; una foto
    di una casa qualunque no. La differenza è la frase che dice cosa lega
    questa immagine a *quella* parte di vita — e senza quella frase il legame
    non si scrive, esattamente come in V3.12.
    """
    async def body():
        client, db = await _db()
        uid = f"vs_{uuid.uuid4().hex[:8]}"
        try:
            from visual.service import VisualService

            service = VisualService(db)
            observation = service._read(
                uid,
                {
                    "what_i_see": "Un preventivo di mutuo",
                    "readability": "readable",
                    "about_life": [
                        # Con la ragione: entra.
                        {"ref": "lo_casa", "ties_it_here":
                            "È il preventivo della banca per l'immobile di questa compravendita."},
                        # Senza: cade.
                        {"ref": "lo_lavoro", "ties_it_here": ""},
                        # Con un riferimento vuoto: cade.
                        {"ref": "", "ties_it_here": "Parla di soldi."},
                        # Non un oggetto: cade.
                        "lo_studio",
                    ],
                },
                document_ref="doc_x", session_ref="ses_x",
                mime_type="image/png", mark="abc", uploaded_at="",
            )
            assert [t.ref for t in observation.about_life] == ["lo_casa"]
            assert observation.about_life[0].ties_it_here.startswith("È il preventivo")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_keyword_decides_what_an_image_is_about():
    """
    §3: nessuna regola di classificazione, nessun instradamento per parola.

    La tentazione è ovvia — «se c'è scritto banca allora è denaro» — ed è il
    modo più veloce di legare la foto di una casa qualunque all'acquisto di
    quella casa.
    """
    for name in ("service.py", "seeing.py", "caps.py"):
        source = (HERE / "visual" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        # Le docstring raccontano dove sono stati trovati i difetti: possono
        # nominare la vita di qualcuno. Il codice che gira no.
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    node.body = body[1:]
        running = ast.unparse(tree).lower()
        for word in ("banca", "mutuo", "casa", "notaio", "dentista", "fattura",
                     "bolletta", "scontrino", "biglietto"):
            assert word not in running, f"visual/{name}: il codice conosce «{word}»"


# ---------------------------------------------------------------------------
# La stessa immagine è la stessa immagine
# ---------------------------------------------------------------------------

def test_the_same_image_is_the_same_image():
    """
    §18: due caricamenti della stessa foto sono una osservazione sola.

    L'identità sono i byte — un fatto tecnico — e non quello che ci si vede
    dentro, che è un giudizio e non è affare del codice.
    """
    from visual.models import fingerprint

    same = b"\x89PNG\r\n\x1a\n" + b"contenuto" * 40
    assert fingerprint(same) == fingerprint(bytes(same))
    assert fingerprint(same) != fingerprint(same + b"x")
    # Il nome del file non c'entra: una schermata catturata ne cambia uno
    # ogni volta.
    assert len(fingerprint(same)) == 32


def test_looking_twice_costs_one_look(monkeypatch):
    """
    §18: la seconda volta non si paga, e non si scrive una seconda riga.
    """
    async def body():
        client, db = await _db()
        uid = f"vs_{uuid.uuid4().hex[:8]}"
        try:
            from visual import service as service_mod

            looks = {"n": 0}

            async def fake_look(*args, **kwargs):
                looks["n"] += 1
                return {
                    "what_i_see": "Una schermata",
                    "readability": "readable",
                    "observed_amounts": ["4.000 €"],
                    "about_life": [],
                }

            async def fake_bytes(self, owner, ref):
                return b"immagine-finta", {"mime_type": "image/png", "created_at": ""}

            monkeypatch.setattr(service_mod.VisualService, "_bytes_of", fake_bytes)
            monkeypatch.setattr("visual.seeing.look_at", fake_look)
            monkeypatch.setattr("visual.seeing.can_see", lambda: True)

            service = service_mod.VisualService(db)
            first = await service.look(uid, document_ref="doc_1", session_ref="s")
            second = await service.look(uid, document_ref="doc_1", session_ref="s")

            assert first["ok"] and second["ok"]
            assert first["already_seen"] is False
            assert second["already_seen"] is True, "la stessa immagine è stata guardata due volte"
            assert looks["n"] == 1, f"chiamate al modello: {looks['n']}"
            assert await db.visual_observations.count_documents({"owner_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Quello che non si è potuto leggere, e quello che non si è potuto guardare
# ---------------------------------------------------------------------------

def test_an_unreadable_image_stays_unreadable():
    """
    §14: se il testo è piccolo, tagliato o sfocato, si dice.

    Un importo intravisto in una schermata sfocata, riportato come se fosse
    stampato, diventa un fatto sul conto di qualcuno.
    """
    async def body():
        client, db = await _db()
        uid = f"vs_{uuid.uuid4().hex[:8]}"
        try:
            from visual.service import VisualService

            observation = VisualService(db)._read(
                uid,
                {
                    "what_i_see": "Una schermata, ma non si legge",
                    "readability": "unreadable",
                    "what_i_could_not_read": "Gli importi sono troppo piccoli.",
                    "observed_amounts": [],
                },
                document_ref="d", session_ref="s", mime_type="image/png",
                mark="m", uploaded_at="",
            )
            assert observation.readability == "unreadable"
            assert observation.observed_amounts == []
            assert "troppo piccoli" in observation.what_i_could_not_read

            # E un grado di leggibilità inventato torna «non è chiaro»: il
            # codice non si fida di una parola che non conosce.
            odd = VisualService(db)._read(
                uid, {"readability": "perfetta"},
                document_ref="d", session_ref="s", mime_type="image/png",
                mark="m2", uploaded_at="",
            )
            assert odd.readability == "ambiguous"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_not_having_looked_is_not_having_looked_and_not_understood():
    """
    Due cose diverse, e scriverle uguali le rende indistinguibili dopo.

    «Non riesco a guardare adesso» è una cosa da dire su di sé. «Non si
    capisce» è una cosa da dire sulla foto — e dirla senza averla vista è
    inventare.
    """
    source = (HERE / "visual" / "caps.py").read_text(encoding="utf-8")
    assert '"could_not_look"' in source
    assert "non dire che non si capisce" in source
    # E l'assenza di un'osservazione non produce un'osservazione vuota.
    service = (HERE / "visual" / "service.py").read_text(encoding="utf-8")
    assert 'return {"ok": False, "reason": "unavailable"}' in service


# ---------------------------------------------------------------------------
# Nessuna seconda pipeline, e niente che esca da qui
# ---------------------------------------------------------------------------

def test_the_image_travels_and_does_not_stay():
    """
    §19: niente byte nei log, niente base64 nelle tracce, niente seconda copia.

    I byte stanno in Documents V2. Tenerne una copia accanto all'osservazione
    vorrebbe dire moltiplicare i posti da cui una cosa privata può uscire.
    """
    from visual.models import VisualObservation

    # L'osservazione non ha un campo dove i byte possano finire.
    for field in VisualObservation.model_fields:
        assert "bytes" not in field and "base64" not in field and "blob" not in field, (
            f"l'osservazione conserva l'immagine: {field}"
        )

    for name in ("seeing.py", "service.py", "caps.py"):
        source = (HERE / "visual" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = ast.unparse(node.func)
            if not target.startswith("logger."):
                continue
            written = ast.unparse(node)
            for leak in ("image", "blob", "b64", "base64", "observed_text",
                         "what_i_see", "user"):
                assert leak not in written, (
                    f"visual/{name}: un log porta con sé «{leak}»"
                )


def test_no_second_pipeline_and_no_second_life_model():
    """
    §1: l'immagine è una fonte nuova, non un secondo prodotto.

    Il percorso passa da Documents V2 per i byte, dal registro delle
    capability per essere chiamato, e dalle situazioni che esistono già per
    sapere a cosa potrebbe appartenere. Non ha un suo archivio, non ha un suo
    agente, non ha una sua ricerca.
    """
    service = (HERE / "visual" / "service.py").read_text(encoding="utf-8")
    assert "from documents.service import DocumentService" in service
    for forbidden in ("AgentService", "OpportunityService", "search_a_life",
                      "life_memories", "governed_facts"):
        assert forbidden not in service, f"la vista si è messa in proprio: {forbidden}"

    # E il ragionamento la raggiunge da dove raggiunge tutto il resto.
    registry = (HERE / "conversation_engine" / "ai_core" / "tools" / "registry.py").read_text(
        encoding="utf-8",
    )
    assert 'capability="look_at_image"' in registry
    assert "from visual.caps import look_at_image" in registry


def test_an_image_without_text_is_not_a_broken_file():
    """
    §13: PARSED TEXT FIRST, VISION WHEN NEEDED.

    Un OCR vuoto su una fotografia è la cosa più normale del mondo, e finiva
    come «failed»: la conversazione riceveva un file guasto e rispondeva che
    non poteva farci niente, mentre bastava guardarlo.
    """
    source = (
        HERE / "conversation_engine" / "ai_core" / "files" / "service.py"
    ).read_text(encoding="utf-8")
    assert "look_at_image" in source
    assert '"image_vision_multimodal": "unavailable",  # Gemini chat is text-only today' not in source
    assert "_can_look()" in source


def test_a_file_that_can_be_read_is_read_not_looked_at():
    """
    §13: guardare costa di più e capisce di meno, quando il testo c'è.

    Sta nel contratto dello strumento, dove chi ragiona lo legge prima di
    scegliere — non in un `if` che decide al posto suo.
    """
    registry = (HERE / "conversation_engine" / "ai_core" / "tools" / "registry.py").read_text(
        encoding="utf-8",
    )
    where = registry.index('capability="look_at_image"')
    contract = registry[where:where + 2000]
    assert "get_file_content" in contract
    assert "cost more and understand less" in contract


def test_this_means_the_last_image_they_sent():
    """
    §11: «che cos'è questo?» arriva subito dopo aver mandato qualcosa.

    La lista della sessione tiene la più recente in testa — il caricamento fa
    `insert(0, …)` — e leggerla al contrario significava guardare la prima
    immagine della conversazione. Alla prova, a una domanda su una schermata
    appena mandata, ORA ha risposto descrivendo un disegno di due turni prima:
    tutto giusto tranne l'immagine.
    """
    source = (HERE / "visual" / "caps.py").read_text(encoding="utf-8")
    assert "reversed(" not in source, "torna a guardare la più vecchia"
    assert "for candidate in (await files.list_session_files(uid, sid) or []):" in source

    # E la lista è davvero in quell'ordine: se un giorno cambiasse, questo
    # test lo dice invece di lasciare ORA a descrivere l'immagine sbagliata.
    binder = (
        HERE / "conversation_engine" / "ai_core" / "files" / "service.py"
    ).read_text(encoding="utf-8")
    assert "files.insert(0, cf.lightweight())" in binder

# ---------------------------------------------------------------------------
# L'immagine non si guarda nel vuoto
# ---------------------------------------------------------------------------

def test_what_ora_already_knows_travels_with_the_image():
    """
    §7 + §15: una schermata che mostra i quattromila euro del notaio è una
    novità soltanto se quei quattromila euro non erano già noti.

    Senza questo, chi guarda può solo ripetere — e annunciare come scoperta
    una cosa già in casa è il modo più rapido di far sembrare distratta
    un'assistente che sapeva già tutto.
    """
    async def body():
        client, db = await _db()
        uid = f"vs_{uuid.uuid4().hex[:8]}"
        try:
            from visual.service import VisualService

            await db.life_objects.insert_one({
                "id": "lo_casa", "user_id": uid, "title": "Acquisto di una nuova casa",
                "type": "HOME", "status": "active", "ai_summary": "In corso.",
            })
            around = await VisualService(db)._life_around(uid)

            assert [s["ref"] for s in around["situations"]] == ["lo_casa"]
            assert "nearby" in around, "la vita intorno non arriva a chi guarda"
            # Denaro e impegni entrano da dove stanno già: nessuna seconda
            # lettura scritta qui dentro.
            source = (HERE / "visual" / "service.py").read_text(encoding="utf-8")
            assert "from financial.knowledge import what_ora_knows" in source
            assert "_appointments_that_still_stand" in source
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_cancelled_appointment_is_not_offered_as_context():
    """
    §24: quello che è stato annullato non torna in vita perché è arrivata
    un'immagine.

    Gli impegni che si mettono davanti a chi guarda sono quelli che stanno in
    piedi: si riusa la stessa lettura che filtra annullati e letture superate,
    invece di scriverne una seconda che dimentica di farlo.
    """
    async def body():
        client, db = await _db()
        uid = f"vs_{uuid.uuid4().hex[:8]}"
        try:
            from datetime import datetime, timedelta, timezone

            from opportunities.snapshot import _appointments_that_still_stand

            now = datetime.now(timezone.utc)
            soon = now + timedelta(days=2)
            for status, ingestion in (
                ("confirmed", "processed"),
                ("cancelled", "processed"),
                ("confirmed", "superseded"),
            ):
                await db.ingestion_events.insert_one({
                    "id": f"ing_{uuid.uuid4().hex[:10]}",
                    "user_id": uid,
                    "external_id": f"evt_{uuid.uuid4().hex[:8]}",
                    "source_record_type": "calendar_event",
                    "ingestion_status": ingestion,
                    "ingested_at": now.isoformat(),
                    "normalized_payload": {
                        "title": "Visita", "starts_at": soon.isoformat(),
                        "status": status,
                    },
                })

            standing = await _appointments_that_still_stand(
                db, uid, now, now + timedelta(days=30),
            )
            assert len(standing) == 1, (
                f"un impegno annullato o superato è tornato: {standing}"
            )
        finally:
            await db.ingestion_events.delete_many({"user_id": uid})
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_image_can_be_compared_with_what_is_in_the_calendar():
    """
    §16: una schermata di appuntamento va messa accanto a quelli veri.

    Il codice non decide se sono lo stesso impegno — quella è una lettura, e
    la fa chi guarda. Quello che il codice deve garantire è che gli impegni
    ci siano, e che l'istruzione chieda di dire se conferma, aggiunge,
    contraddice o non c'entra.
    """
    seeing = (HERE / "visual" / "seeing.py").read_text(encoding="utf-8")
    assert "what_ora_already_knows_nearby" in seeing
    assert "contradicts it" in seeing
    assert "already known" in seeing
    # E il calendario non viene toccato da qui: cambiare un impegno è
    # un'azione, e passa dall'Action Engine con la sua autorità.
    for name in ("seeing.py", "service.py", "caps.py"):
        source = (HERE / "visual" / name).read_text(encoding="utf-8")
        for forbidden in ("create_calendar_event", "update_calendar_event",
                          "calendar.write", "ActionIntent"):
            assert forbidden not in source, (
                f"visual/{name} tocca il calendario: {forbidden}"
            )


def test_voice_and_text_see_the_same_image():
    """
    §12: la modalità di ingresso non cambia cosa ORA ha davanti.

    L'osservazione è legata alla sessione, non a come sono arrivate le parole:
    una domanda fatta a voce nella stessa conversazione trova la stessa
    immagine, senza che nessuno debba rimandarla.
    """
    async def body():
        client, db = await _db()
        uid = f"vs_{uuid.uuid4().hex[:8]}"
        try:
            from visual.models import VisualObservation
            from visual.service import VisualService

            service = VisualService(db)
            await service._keep(VisualObservation(
                owner_id=uid, session_ref="ses_uno", document_ref="doc_1",
                content_fingerprint="f1", what_i_see="Una schermata della banca",
            ))
            await service._keep(VisualObservation(
                owner_id=uid, session_ref="ses_due", document_ref="doc_2",
                content_fingerprint="f2", what_i_see="Un'altra cosa",
            ))

            here = await service.seen_in_session(uid, "ses_uno")
            assert [o.what_i_see for o in here] == ["Una schermata della banca"]
            # Il legame è la sessione: non c'è nessun campo che dica da quale
            # modalità è arrivata la domanda, e non deve essercene uno.
            source = (HERE / "visual" / "models.py").read_text(encoding="utf-8")
            for forbidden in ("origin", "voice", "dictation", "modality"):
                assert forbidden not in source.lower(), (
                    f"l'osservazione sa come le hanno parlato: {forbidden}"
                )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_observation_never_becomes_a_financial_fact_by_itself():
    """
    §9 + §15: nessuna scorciatoia da «ho visto un importo» a «so quanto hai
    speso».

    Un importo letto in una schermata è un importo letto in una schermata.
    Diventare un fatto finanziario è una decisione della governance, e da qui
    non parte nessuna strada che la salti.
    """
    for name in ("service.py", "seeing.py", "caps.py"):
        source = (HERE / "visual" / name).read_text(encoding="utf-8")
        for forbidden in ("FinancialFact", "financial_facts", "governed_facts",
                          "life_memories", "confirm_money"):
            assert forbidden not in source, (
                f"visual/{name} scrive dove non deve: {forbidden}"
            )
    # E quello che torna a chi ragiona lo dice a voce alta.
    caps = (HERE / "visual" / "caps.py").read_text(encoding="utf-8")
    assert '"memory_eligible": False' in caps
    assert "non quello che" in caps

# ---------------------------------------------------------------------------
# Dodici caratteri non sono un testo
# ---------------------------------------------------------------------------

def test_ocr_noise_does_not_count_as_having_read_the_file():
    """
    §6: una fattura fotografata male non e' un file letto.

    Questo e' il difetto peggiore trovato in questo sprint, e vale la pena
    scriverlo per intero perche' il meccanismo e' piu' interessante del bug.
    Da `illeggibile.png` l'estrazione e' tornata con dodici caratteri:
    «-- ae / -_- / oe». Nessuna parola, nessuna cifra. Ma la domanda che si
    faceva era `bool(text.strip())`, e dodici caratteri sono veri: il file
    risultava letto. E siccome risultava letto, nessuno lo guardava.

    Alla domanda «quanto devo pagare qui?» ORA non ha trovato un importo in
    quei dodici caratteri, ed e' andata a prenderne uno dall'altra immagine
    della stessa conversazione — quattromila euro, di tutt'altra cosa, detti
    come se fossero la risposta. Un numero falso sui soldi di una persona,
    prodotto senza che nessun modello avesse allucinato niente: la strada
    verso gli occhi era semplicemente chiusa da una riga che diceva di si'.
    """
    from conversation_engine.ai_core.files.service import worth_reading

    # Quello che l'OCR ha tirato fuori davvero da quella fattura.
    assert worth_reading("\u2014\u2014 ae\n\u2014_\u2014\noe") is False
    assert worth_reading("") is False
    assert worth_reading("   \n  ") is False
    assert worth_reading("%%% ### ...") is False
    # E quello che invece e' un testo: una parola basta, una cifra basta.
    assert worth_reading("Studio Bianchi Conferma appuntamento") is True
    assert worth_reading("Saldo disponibile 1.284,60") is True

    # La domanda si fa dove si decide se il file e' stato letto, non in un
    # posto nuovo accanto.
    code = _code_only(
        (HERE / "conversation_engine" / "ai_core" / "files" / "service.py").read_text(
            encoding="utf-8",
        )
    )
    assert "worth_reading(text)" in code
    assert "bool(text.strip())" not in code, (
        "la vecchia domanda e' ancora li': dei caratteri contano come lettura"
    )


def test_an_unreadable_image_is_handed_to_the_eyes_not_declared_broken():
    """
    §6: quello che l'OCR non sa leggere si guarda, e si dice cosi'.

    Il file resta `ready` — non e' rotto, e' solo illeggibile a parole — e la
    nota dice a chi ragiona che cosa e' successo e che cosa puo' fare. Senza
    quella nota il turno finisce in «non posso farci niente», che e' falso:
    l'immagine c'e' e si puo' guardare.
    """
    code = _code_only(
        (HERE / "conversation_engine" / "ai_core" / "files" / "service.py").read_text(
            encoding="utf-8",
        )
    )
    assert "look_at_image" in code
    assert "non è leggibile così" in code
    # Il file resta utilizzabile: un'immagine illeggibile a parole non è un
    # file rotto, ed è per questo che lo stato resta «ready».
    assert "status = 'ready'" in code


# ---------------------------------------------------------------------------
# Un ornamento che esplode non deve portarsi via la prova
# ---------------------------------------------------------------------------

def test_an_all_day_marker_does_not_kill_the_whole_calendar_read():
    """
    §5: confrontare un giorno intero con un appuntamento non deve far cadere
    la lettura del calendario.

    «San Francesco d'Assisi» arriva come `2026-10-04` — senza ora e senza
    fuso — e l'appuntamento delle undici arriva con il suo `+00:00`. Metterli
    in fila sollevava `can't compare offset-naive and offset-aware datetimes`,
    dentro il pezzo che decora gli impegni con le sovrapposizioni. Il
    risultato, visto da fuori, era che l'intera capacita' falliva: alla
    domanda «e' lo stesso appuntamento che ho in calendario?» ORA non riceveva
    meno prove, ne riceveva zero — e ha risposto «si', con certezza» lo
    stesso, dicendo nella stessa frase che le chiamate al calendario avevano
    dato errore.
    """
    from datetime import datetime, timezone

    from conversation_engine.ai_core.tools.calendar_caps import _at_the_same_clock

    naive = datetime(2026, 10, 4)
    aware = datetime(2026, 9, 17, 11, 0, tzinfo=timezone.utc)
    a, b = _at_the_same_clock(naive, aware)
    assert a.tzinfo is not None and b.tzinfo is not None
    assert a > b, "i due istanti non si riescono ancora a mettere in fila"
    assert _at_the_same_clock(None, aware)[0] is None

    # E il calcolo sta dentro una rete: se un giorno sbaglia di nuovo, gli
    # impegni tornano comunque, perche' la prova vale piu' del suo ornamento.
    source = (HERE / "conversation_engine" / "ai_core" / "tools" / "calendar_caps.py").read_text(
        encoding="utf-8",
    )
    body = source.split("conflict_index_pairs")[0]
    assert "conflicts = []" in body and "except Exception" in body[-2500:], (
        "le sovrapposizioni possono ancora portarsi via gli impegni"
    )

# ---------------------------------------------------------------------------
# Una scansione e' una fotografia in una busta
# ---------------------------------------------------------------------------

def test_a_scanned_page_reaches_the_eyes_and_a_readable_pdf_does_not():
    """
    §8: prima il testo, gli occhi quando serve — e «serve» deve poter accadere.

    Un contratto scansionato non ha nessun testo dentro: e' l'immagine di un
    foglio, chiusa in un PDF. Chi estrae non trovava niente, e chi guarda si
    fermava un passo prima — `not_an_image` — perche' la busta non e' una
    fotografia. Cosi' l'unico tipo di documento che avrebbe davvero avuto
    bisogno degli occhi era l'unico a cui non arrivavano.

    Le due meta' contano tutte e due. Una pagina senza testo si disegna e si
    guarda; un PDF che il testo ce l'ha dentro si legge e basta, perche'
    guardarlo sarebbe pagare per vedere in una fotografia quello che si puo'
    avere in chiaro.
    """
    from visual.seeing import first_page_as_an_image, is_a_page, is_an_image

    assert is_a_page("application/pdf") is True
    assert is_a_page("image/png") is False
    assert is_an_image("application/pdf") is False

    # Una pagina vera, fatta qui, senza nessun testo dentro.
    from io import BytesIO

    from PIL import Image, ImageDraw

    sheet = Image.new("RGB", (760, 420), "white")
    ImageDraw.Draw(sheet).text((40, 40), "Totale dovuto 1.274,00 EUR", fill="black")
    envelope = BytesIO()
    sheet.save(envelope, format="PDF", resolution=150)

    drawn = first_page_as_an_image(envelope.getvalue())
    assert drawn is not None, "la busta non si apre: la scansione resta invisibile"
    assert drawn[:8] == b"\x89PNG\r\n\x1a\n", "quello che esce non e' un'immagine"
    assert len(drawn) > 1000

    # Una pagina sola, e la prima: disegnarle tutte sarebbe l'OCR di massa che
    # questo non vuole essere.
    code = _code_only((HERE / "visual" / "seeing.py").read_text(encoding="utf-8"))
    assert "pdf[0]" in code and "for page in pdf" not in code

    # E la scelta di guardare o no si fa su quello che c'e' scritto dentro,
    # con la stessa domanda che vale per le immagini.
    service = _code_only((HERE / "visual" / "service.py").read_text(encoding="utf-8"))
    assert "worth_reading" in service
    assert "the_text_is_there" in service
    assert "first_page_as_an_image" in service


def test_the_fingerprint_of_a_scan_is_the_document_not_the_drawing():
    """
    §10: la stessa scansione ricaricata resta la stessa cosa.

    Se l'impronta fosse quella del disegno, basterebbe che la resa venisse un
    pixel diversa perche' lo stesso PDF risultasse nuovo, e si pagherebbe di
    nuovo per guardare una cosa gia' guardata.
    """
    service = _code_only((HERE / "visual" / "service.py").read_text(encoding="utf-8"))
    body = service.split("mark = fingerprint(")[1][:40]
    assert body.startswith("blob)"), (
        "l'impronta si prende dal disegno invece che dal documento"
    )


# ---------------------------------------------------------------------------
# «Te l'ho gia' detto» non e' una scoperta
# ---------------------------------------------------------------------------

def test_what_ora_already_knows_about_money_is_in_the_room():
    """
    §4: la prova chiave — «cosa cambia rispetto a quello che gia' sapevi?»

    Una schermata del conto con i quattromila euro del notaio arrivava in
    conversazione e ORA li annunciava: «il documento conferma un movimento
    specifico e recente». Ma quei quattromila euro li aveva gia' letti una
    volta sul conto, e i duemilacinquanta dello stipendio glieli aveva
    confermati la persona stessa. Alla domanda su cosa cambiasse non poteva
    rispondere, perche' quello che gia' sapeva non era nella stanza: nessuna
    fonte di contesto portava il denaro, e nessuno strumento veniva chiamato.

    La fonte non legge niente di nuovo — chiede a chi lo sa gia' — e tiene i
    gradi: «me lo hai confermato tu» e «l'ho visto una volta sul conto» sono
    due cose diverse, ed e' quella differenza a permettere una risposta onesta.
    """
    async def body():
        client, db = await _db()
        uid = f"vs_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.context_sources import (
                ContextSourceRegistry,
            )

            registry = ContextSourceRegistry(db)
            assert "money" in registry._sources, (
                "il denaro non e' una fonte di contesto: ORA non sa cosa sapeva"
            )
            facts = await registry._money(uid, None, None)
            assert isinstance(facts, list)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())

    # E il grado con cui lo sa viaggia con il fatto, sempre.
    code = _code_only(
        (HERE / "conversation_engine" / "ai_core" / "context_sources.py").read_text(
            encoding="utf-8",
        )
    )
    money = code.split("async def _money")[1].split("async def _calendar")[0]
    assert "how ORA knows" in money, "il grado si perde per strada"
    assert "'user-confirmed'" in money and "'document-backed'" in money
    assert "'inferred'" in money, "quello che ORA pensa arriva come se lo sapesse"
    assert "what_ora_knows" in money, "qui si rilegge il denaro invece di chiederlo"
    # E niente di questo diventa un fatto nuovo: e' una lettura, non una scrittura.
    for forbidden in ("insert_one", "update_one", "delete_", "FinancialFact("):
        assert forbidden not in money, f"una fonte di contesto scrive: {forbidden}"

def test_a_filter_that_matches_nothing_is_not_knowing_nothing():
    """
    §4: l'ultimo pezzo del delta.

    Il filtro `about` confronta sottostringhe. Chiesto «controlla cosa sapevi
    gia' di questi movimenti», ORA e' andata davvero a cercare — e ha cercato
    la parola «movimenti» dentro «Stipendio ACME SRL» e «Notaio per acquisto
    casa». Non l'ha trovata, il risultato e' tornato vuoto con
    `nothing_known: true`, e ORA ha detto alla persona che quei movimenti «non
    risultavano registrati»: due cose che sapeva benissimo, una confermata
    dalla persona stessa e una letta sul suo conto.

    Il difetto non e' il filtro grossolano — quello e' dichiarato e va bene. E'
    che restringere possa far sparire. Quando la parola non aggancia niente,
    torna tutto, e si dice che la parola non ha agganciato niente.
    """
    async def body():
        client, db = await _db()
        uid = f"vs_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools.financial_caps import _only_about

            everything = {
                "so": [{"cosa": "Stipendio ACME SRL", "quanto": "€2.050"}],
                "ho_letto": [{"cosa": "Notaio per acquisto casa", "quanto": "€4.000"}],
                "devo_chiederti": [],
                "in_arrivo": [],
            }
            # La parola che una persona userebbe non compare in nessuna riga.
            narrowed = _only_about(everything, "movimenti")
            assert not narrowed["so"] and not narrowed["ho_letto"], (
                "il filtro non e' piu' quello: questa prova va riscritta"
            )
            # Restringere su una parola che c'e' invece funziona.
            assert len(_only_about(everything, "notaio")["ho_letto"]) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())

    # E la capacita' non lascia che quel vuoto arrivi a una persona come
    # «non so niente».
    code = _code_only(
        (HERE / "conversation_engine" / "ai_core" / "tools" / "financial_caps.py").read_text(
            encoding="utf-8",
        )
    )
    assert "narrowed_to_nothing" in code
    assert "nothing_matched_that_word" in code
    assert "non dire che non risultava niente" in code, (
        "chi risponde non sa cosa farsene di un filtro a vuoto"
    )

# ---------------------------------------------------------------------------
# Somigliarsi non basta
# ---------------------------------------------------------------------------

def test_a_tie_arrives_with_how_strongly_it_holds():
    """
    §7: ogni conclusione porta con sé il livello delle prove.

    Senza, il giudizio non sa con che forza può parlare, e una coincidenza di
    nome arriva a chi risponde indistinguibile da una prova. Il valore
    prudente è quello di partenza: un legame che non dice quanto regge, regge
    poco — si propone, non si afferma.
    """
    from visual.models import LifeTie, VisualObservation

    tie = LifeTie(ref="lo_casa", ties_it_here="Il bonifico è allo studio del rogito.")
    assert tie.how_strong == "plausible", (
        "un legame senza forza dichiarata parte già come una prova"
    )

    seen = VisualObservation(owner_id="u", what_i_see="Schermata del conto", about_life=[tie])
    given = seen.for_ai()["parts_of_life_it_belongs_to"][0]
    assert given["how_strong"] == "plausible"
    # E con la forza viaggia la frase che quella forza consente: il livello da
    # solo lasciava a chi risponde un passaggio da fare, e il passaggio si
    # saltava.
    assert "rende probabile" in given["you_may_say"]
    assert "stesso evento" in given["you_may_never_say"]


def test_the_same_notary_on_two_different_days_is_not_one_event():
    """
    §8-A: stessa controparte, date diverse → non lo stesso evento.

    Un bonifico allo Studio Notarile Bianchi l'11 settembre e un appuntamento
    presso lo stesso studio il 17 condividono un nome. Possono essere la
    stessa pratica, e possono essere un acconto e una firma, un servizio
    precedente, un'altra pratica con lo stesso studio. Undici non è diciassette,
    e due date diverse non «coincidono temporalmente».
    """
    seeing = (HERE / "visual" / "seeing.py").read_text(encoding="utf-8")
    assert "SAME COUNTERPARTY IS NOT THE SAME EVENT" in seeing
    assert "notary on the 17th share a name" in seeing

    prompt = (
        HERE / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")
    assert "SAME COUNTERPARTY IS NOT THE SAME EVENT" in prompt
    assert "A PLAUSIBLE RELATION IS NOT A VERIFIED ONE" in prompt
    # E la regola dell'identità di un appuntamento sta dove si risponde.
    assert "Is this the same appointment" in prompt
    assert "If all they share is the counterparty" in prompt
    # Che non è una lista di parole vietate: è un livello che si sceglie dopo
    # aver guardato le prove.
    assert "This is not a list of forbidden words" in prompt


def test_the_same_amount_with_another_counterparty_ties_nothing():
    """
    §8-B: stesso importo, controparte diversa → nessuna relazione automatica.

    Quattromila euro sono quattromila euro anche quando vanno da un'altra
    parte. Il codice non ha nessuna regola che leghi due righe perché il
    numero combacia — e non deve averne una, perché sarebbe indistinguibile da
    un caso vero finché non fa danno.
    """
    for name in ("service.py", "seeing.py", "caps.py", "models.py"):
        code = _code_only((HERE / "visual" / name).read_text(encoding="utf-8"))
        for shortcut in (
            "same_amount", "amount ==", "match_amount", "by_amount",
            "counterparty ==", "same_counterparty",
        ):
            assert shortcut not in code, (
                f"visual/{name} lega due cose perché un valore combacia: {shortcut}"
            )


def test_one_counterparty_across_two_situations_is_not_ora_choice():
    """
    §8-C: stessa controparte, due parti di vita → non si sceglie da soli.

    Se lo stesso studio compare nell'acquisto della casa e in una pratica di
    successione, l'immagine non decide quale delle due. Il contratto lo rende
    possibile — i legami sono una lista — e la regola che li governa è sempre
    quella: senza la frase che dice cosa lega questa immagine a *quella* parte
    e non all'altra, il legame non si scrive affatto.
    """
    async def body():
        client, db = await _db()
        uid = f"vs_{uuid.uuid4().hex[:8]}"
        try:
            from visual.service import VisualService

            observation = VisualService(db)._read(
                uid,
                {
                    "what_i_see": "Una fattura dello Studio Bianchi",
                    "readability": "readable",
                    "about_life": [
                        # Due situazioni, stesso studio, nessuna ragione che
                        # distingua: cadono tutte e due.
                        {"ref": "lo_casa", "ties_it_here": ""},
                        {"ref": "lo_successione", "ties_it_here": "   "},
                    ],
                },
                document_ref="doc_x", session_ref="ses_x",
                mime_type="image/png", mark="abc", uploaded_at="",
            )
            assert observation.about_life == [], (
                "ORA ha scelto da sola fra due situazioni che si somigliano"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_seeing_a_thing_again_is_a_second_provenance_not_a_second_fact():
    """
    §8-D + §8-E: vedere una cosa che si era già letta la rafforza come prova,
    e non la promuove come conoscenza.

        FORZA DELL'EVIDENZA != STATO EPISTEMICO.

    Una schermata che mostra i quattromila euro che ORA aveva soltanto letto
    sul conto è una seconda provenienza indipendente: vale la pena dirlo — «lo
    avevo letto sul tuo conto, e adesso lo vedo» — e non è la stessa cosa che
    quel pagamento diventi un fatto confermato della sua vita. Solo la
    governance sposta qualcosa da «penso» a «so», e una fotografia non è la
    governance.
    """
    for name in ("service.py", "seeing.py", "caps.py", "models.py"):
        code = _code_only((HERE / "visual" / name).read_text(encoding="utf-8"))
        for promotion in (
            "FinancialFact", "financial_facts", "governed_facts", "life_memories",
            "confirm_money", "status = 'confirmed'", "grade = 'so'", "promote",
        ):
            assert promotion not in code, (
                f"visual/{name} promuove un'osservazione: {promotion}"
            )
    # E la distinzione è scritta dove si risponde.
    prompt = (
        HERE / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")
    assert "Evidence strength and epistemic status are different things" in prompt
    assert "governance moves something from what you think to what you know" in prompt
    # Né il saldo né lo stipendio si spostano dentro una situazione.
    assert "not an amount available for whatever you were discussing" in prompt
    assert "a salary is an income" in prompt


def test_the_delta_question_can_reach_what_ora_knows_in_their_language():
    """
    §8-F + §3: la domanda delta deve poter arrivare a quello che ORA sa, anche
    quando è scritta con parole diverse da quelle del fatto.

    Questa è la causa esatta del delta rosso. Le fonti si scelgono per
    sovrapposizione di parole fra la domanda e la descrizione della fonte, e
    le descrizioni sono in inglese: una domanda in italiano — «cosa so già dei
    pagamenti per la casa» — non aggancia «money» e la fonte non entra fra le
    sei scelte. ORA andava a cercare davvero, e tornava senza il denaro.

    La soluzione non è una parola chiave né allargare tutto: è che chi ragiona
    nomini l'area, che è l'unica cosa che sa fare e il codice no. Il
    suggerimento è il modo in cui la nomina; il recupero resta del codice.
    """
    from conversation_engine.ai_core.context_sources import ContextSourceRegistry
    from conversation_engine.ai_core.models import ContextNeed

    registry = ContextSourceRegistry(None)
    italian = "cosa so già dei pagamenti per la casa"

    blind = [s.name for s in registry.select(ContextNeed(query=italian), maximum=6)[0]]
    named = [
        s.name
        for s in registry.select(
            ContextNeed(query=italian, source_hints=["money", "situations"]),
            maximum=6,
        )[0]
    ]
    assert "money" in named, "nominare l'area non basta a raggiungere il denaro"
    assert "situations" in named
    # E se un giorno la selezione cieca dovesse bastare da sola, tanto meglio:
    # questa prova resta vera lo stesso, perché è il suggerimento a doverla
    # rendere raggiungibile, non a doverla nascondere.
    assert set(named) >= {"money", "situations"} - set(blind) or "money" in named

    # Chi ragiona deve sapere che può nominarla, e per cosa.
    prompt = (
        HERE / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")
    assert 'source_hints=["money"]' in prompt
    assert "what you already knew" in prompt
    assert "match an English source description on its own" in prompt

def test_the_rule_about_linking_is_its_own_key_where_the_model_looks():
    """
    §7: la guardia sulla forza delle affermazioni deve arrivare dove il
    modello guarda.

        UNA REGOLA IN MEZZO A TRENTA NON È UNA REGOLA.

    Questa prova esiste per una cosa misurata, non immaginata. La stessa
    regola è stata scritta prima nel prompt di sistema, poi dentro
    `epistemic_reminder` insieme ad altre trenta, poi accanto a ogni file
    della sessione: tre volte, e tre volte alla domanda «che cosa vedi qui?»
    su una schermata del conto ORA ha risposto che il bonifico dell'11
    «corrisponde esattamente» all'appuntamento del 17. Undici non è
    diciassette.

    Ha smesso quando la regola è diventata una chiave sua, corta, in cima al
    payload — accanto al messaggio della persona invece che in fondo a un
    elenco. Se un giorno qualcuno la riaccorpa per ordine, il difetto torna
    senza che nessun test se ne accorga: questo se ne accorge.
    """
    import json

    from conversation_engine.ai_core.prompt import build_user_payload

    payload = json.loads(
        build_user_payload(
            user_message="Che cosa vedi qui?",
            recent_turns=[], active_goal=None, context_facts=[],
            tools=[], observations=[],
        )
    )
    rule = payload.get("before_you_link_two_things")
    assert rule, "la regola non è più una chiave sua: è tornata dentro un elenco"
    assert len(rule) < 900, (
        "la regola si è allungata: era corta perché una regola lunga non si legge"
    )

    keys = list(payload.keys())
    assert keys.index("before_you_link_two_things") <= 3, (
        "la regola è scesa in fondo al payload"
    )

    # E dice le tre cose che il gate ha trovato rotte, una per una.
    assert "Same counterparty" in rule and "same event" in rule
    assert "coincide" in rule
    assert "corresponds exactly" in rule
    # Compreso il residuo che è servito un quarto giro a togliere: un
    # pagamento e un appuntamento restano due eventi anche con la stessa
    # controparte e la stessa pratica.
    assert "A payment and an appointment are two separate events" in rule
    assert "do not say it belongs to a particular" in rule


def test_the_four_classes_are_asked_for_by_name():
    """
    §3: già sapevo · rafforzato o confermato · nuovo · ancora incerto.

    Le quattro classi non sono un formato imposto all'interfaccia: sono il
    modo in cui una risposta onesta a «cosa cambia?» si distingue da una
    seconda descrizione della stessa immagine. Chiederle per nome è ciò che
    ha fatto la differenza fra le due.
    """
    prompt = (
        HERE / "conversation_engine" / "ai_core" / "prompt.py"
    ).read_text(encoding="utf-8")
    for klass in (
        "what you already knew",
        "what this confirms or adds detail to",
        "what is genuinely new",
        "what is still uncertain",
    ):
        assert klass in prompt, f"manca una delle quattro classi: {klass}"

    # E il recupero che le rende possibili: la domanda delta non si risponde
    # dal documento, perché parla di una cosa che nel documento non c'è.
    assert "already-known / " in prompt
    assert "confirmed-or-strengthened / new / still-uncertain" in prompt

# ---------------------------------------------------------------------------
# Fra il livello e la frase non deve esserci un passaggio
# ---------------------------------------------------------------------------

def test_a_link_hands_over_the_sentence_it_licenses_not_a_level_to_translate():
    """
    Il solo difetto rimasto dopo il closeout epistemico.

        NON IL LIVELLO: LA FRASE.

    Di ogni legame usciva `how_strong` e, accanto, un paragrafo che spiegava
    come tradurlo in italiano. Tradurre è un passaggio, e un passaggio si
    salta: su cinque esecuzioni di «questo riguarda la casa?», una ha
    risposto che il bonifico dell'11 «si collega strettamente all'appuntamento
    fissato per il 17 settembre». Il livello diceva plausibile; la frase
    diceva certo. Il margine fra i due era il difetto.

    Adesso esce la frase già fatta, per ogni livello, e non c'è più niente da
    tradurre.
    """
    from visual.models import LifeTie

    for level, must_contain in (
        ("observed", "come un fatto"),
        ("supported", "su cosa si regge"),
        ("plausible", "rende probabile"),
        ("unknown", "non lo sai"),
    ):
        tie = LifeTie(ref="lo_casa", ties_it_here="perché sì", how_strong=level)
        licensed = tie.what_it_licenses()
        assert must_contain in licensed["you_may_say"], (
            f"il livello {level} non consegna la frase che consente"
        )

    # E un livello sconosciuto non diventa il più comodo: torna il prudente.
    tie = LifeTie(ref="lo_casa", ties_it_here="x")
    assert "rende probabile" in tie.what_it_licenses()["you_may_say"]


def test_no_strength_licenses_saying_it_is_the_same_event():
    """
    §2: `plausible` non diventa una certezza, e `supported` non diventa «è lo
    stesso evento» — senza una prova di identità.

    Il divieto vale per OGNI livello, anche per `observed`, e non è una
    prudenza in più: è una cosa che questo tipo di dato non può contenere.
    `ref` indica una parte di vita — una pratica — non un appuntamento.
    Nessun campo qui porta un'identità con un evento, quindi nessuna forza
    può licenziarne una.
    """
    from visual.models import LifeTie

    for level in ("observed", "supported", "plausible", "unknown"):
        tie = LifeTie(ref="lo_casa", ties_it_here="perché sì", how_strong=level)
        never = tie.what_it_licenses()["you_may_never_say"]
        assert "stesso evento" in never, f"{level} non nega l'identità con un evento"
        assert "non a un appuntamento" in never
        assert "nessun livello di forza" in never, (
            f"{level} lascia credere che un livello più alto basterebbe"
        )

    # E quello che arriva a chi risponde porta la licenza per ogni legame,
    # invece del paragrafo che spiegava come tradurre un'etichetta.
    from visual.models import VisualObservation

    seen = VisualObservation(
        owner_id="u", what_i_see="Schermata del conto",
        about_life=[LifeTie(ref="lo_casa", ties_it_here="x", how_strong="supported")],
    )
    given = seen.for_ai()
    assert "say_it_no_stronger_than_this" not in given, (
        "il paragrafo da tradurre è tornato: il margine con lui"
    )
    tie_out = given["parts_of_life_it_belongs_to"][0]
    assert "you_may_say" in tie_out and "you_may_never_say" in tie_out


def test_a_document_never_licenses_a_claim_about_a_particular_appointment():
    """
    Lo stesso divieto dove la prova viaggia davvero.

    Nel caso che falliva non c'era nessun legame visivo — `about_life` era
    vuoto, perché la schermata aveva testo estraibile e nessuno l'ha guardata.
    La forza non veniva superata: non era portata affatto. L'unico oggetto in
    quella stanza era il file della sessione, ed è lì che il divieto deve
    stare, perché è lì che chi risponde guarda mentre scrive quella frase.
    """
    from conversation_engine.ai_core.files.models import ContextFile

    handed = ContextFile(
        user_id="u", document_id="d", original_name="banca.png", mime_type="image/png",
    ).lightweight()

    assert "you_may_never_say" in handed, "il documento non porta nessun divieto"
    never = handed["you_may_never_say"]
    assert "APPUNTAMENTO" in never
    assert "nessuna prova di identità con un evento" in never
    assert "stessa controparte e stessa pratica non bastano" in never
    # E quello che invece si può dire resta possibile: il legame con la
    # pratica, che ORA conosce davvero.
    assert "PARTE della sua vita" in handed["how_to_say_it"]


def test_none_of_this_writes_anything(  # noqa: D103
):
    """
    §4: `PENSO` resta `PENSO`, e nessun fatto finanziario nasce da qui.

    Una licenza è una frase: non promuove niente e non scrive niente. Questa
    prova esiste perché il modo più facile di "risolvere" un overclaim
    sarebbe stato registrare il legame come acquisito.
    """
    for name in ("models.py", "service.py", "seeing.py", "caps.py"):
        code = _code_only((HERE / "visual" / name).read_text(encoding="utf-8"))
        for writing in (
            "FinancialFact", "financial_facts", "governed_facts", "life_memories",
            "insert_one", "update_one",
        ):
            if name == "service.py" and writing in ("insert_one", "update_one"):
                # Il servizio scrive la sua osservazione, e solo quella.
                continue
            assert writing not in code, f"visual/{name} scrive: {writing}"

    files_code = _code_only(
        (HERE / "conversation_engine" / "ai_core" / "files" / "models.py").read_text(
            encoding="utf-8",
        )
    )
    for writing in ("FinancialFact", "insert_one", "update_one", "grade", "promote"):
        assert writing not in files_code, f"la licenza del documento scrive: {writing}"
