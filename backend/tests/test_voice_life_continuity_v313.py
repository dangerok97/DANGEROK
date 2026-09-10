"""
V3.13 Sprint 1 closeout — la stessa ORA deve sapere le stesse cose.

    SAME ORA = SAME LIFE KNOWLEDGE.
    USER TEMPORAL INTENT DEFINES THE RETRIEVAL HORIZON.
    EMPTY FIRST RETRIEVAL != ORA DOES NOT KNOW.

Tre difetti veri, trovati parlando invece che scrivendo — e nessuno dei tre
era della voce.

Il primo: «che cosa avevi trovato sul dentista?» ha avuto per risposta che non
risultava nessuna informazione su un dentista, mentre di quel dentista ORA
aveva l'appuntamento, due mail dello studio, il disaccordo sull'orario e
un'iniziativa che aveva prodotto lei stessa il giorno prima. Nessuno stava
mentendo: la conversazione poteva raggiungere soltanto memorie e note, e lì
dentro davvero non c'era niente.

Il secondo: «quando parto per Vibo?» ha avuto per risposta che non risultava
nessuna partenza, mentre la partenza era in calendario a dieci giorni. Lo
strumento, senza un intervallo, guardava una settimana.

Il terzo: la stessa frase detta due volte a nove minuti di distanza ha messo
in calendario due impegni identici, uno che finiva alle 19:15 e uno alle
19:30.

Quello che si verifica qui non è che l'AI risponda bene — quello si guarda su
una vita vera, e infatti è così che sono stati trovati. Si verifica che le
strade esistano: che la conversazione possa arrivare al modello della vita,
che una parola sul tempo diventi una finestra, e che lo stesso impegno resti
uno.
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
FRONTEND = HERE.parent / "frontend"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in (
        "life_objects", "documents", "ingestion_events",
        "connected_situation_links", "calendar_event_drafts",
        "life_search_cache", "opportunities",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


async def _a_situation(db, uid, *, title, kind="HOME"):
    ref = f"lo_{uuid.uuid4().hex[:12]}"
    await db.life_objects.insert_one({
        "id": ref, "user_id": uid, "title": title, "type": kind,
        "status": "active", "ai_summary": f"{title}, in corso.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return ref


async def _a_draft(db, uid, *, title, start, end=None):
    ref = f"ced_{uuid.uuid4().hex[:12]}"
    await db.calendar_event_drafts.insert_one({
        "id": ref, "user_id": uid, "title": title,
        "start_datetime": start.isoformat(),
        "end_datetime": (end or (start + timedelta(hours=1))).isoformat(),
        "timezone": "Europe/Rome", "status": "confirmed",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return ref


# ---------------------------------------------------------------------------
# La conversazione arriva alla vita
# ---------------------------------------------------------------------------

def test_the_conversation_can_reach_the_life_model():
    """
    §1 + §3: una domanda su cosa ORA sa deve poter raggiungere la Vita.

    La conversazione aveva un solo modo di cercare qualcosa di personale —
    `search_life_memory`, che legge memorie e note — e una vita è molto più
    grande di quello. Adesso c'è la strada verso la ricerca di V3.12, e non
    è un secondo motore: è quella.
    """
    async def body():
        client, db = await _db()
        try:
            from conversation_engine.ai_core.tools.registry import ToolRegistry

            registry = ToolRegistry(db)
            names = set(getattr(registry, "_tools", {}).keys())
            assert "search_my_life" in names, (
                "la conversazione non ha modo di guardare nella vita"
            )
            spec = registry._tools["search_my_life"]
            assert spec.side_effect == "READ_ONLY"
            assert spec.classification == "personal"
            # E la descrizione deve dire perché non basta l'altra: è l'unica
            # cosa che fa scegliere bene a chi legge il contratto.
            said = spec.description.lower()
            assert "search_life_memory" in said
            assert "small corner" in said
        finally:
            client.close()

    _run(body())


def test_what_ora_already_found_comes_back_through_the_conversation():
    """
    §4: quello che ORA aveva scoperto deve poter tornare quando lo si chiede.

    Nessuna parola-chiave e nessuna regola di dominio: si chiede con le parole
    della persona e torna quello che appartiene a quella parte della vita.
    """
    async def body():
        client, db = await _db()
        uid = f"vc_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools.registry import ToolRegistry

            situation = await _a_situation(
                db, uid, title="Cura dei denti", kind="HEALTH",
            )
            await db.documents.insert_one({
                "id": f"doc_{uuid.uuid4().hex[:8]}", "user_id": uid,
                "display_title": "Preventivo Studio Bianchi",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

            registry = ToolRegistry(db)
            found = await registry._search_my_life(
                {"query": "Studio Bianchi"}, {"user_id": uid, "db": db},
            )
            assert found.status == "ok"
            assert "found" in found.payload
            assert found.payload["grounding"] == "PERSONAL_CONTEXT"
            # Non si pretende che il giudizio giri qui: si pretende che la
            # strada arrivi fino in fondo e riporti la forma giusta.
            assert isinstance(found.payload["found"], list)
            assert situation
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_conversation_did_not_grow_a_second_search_engine():
    """
    §3: riusare V3.12, non riscriverlo.

    Lo strumento nuovo chiama `search_a_life` e non sa fare altro: nessuna
    query sulle collezioni della vita, nessun punteggio, nessuna sua idea di
    cosa appartenga a cosa.
    """
    source = (HERE / "conversation_engine" / "ai_core" / "tools" / "registry.py").read_text(
        encoding="utf-8",
    )
    tree = ast.parse(source)
    body = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_search_my_life"
    ]
    assert body, "lo strumento non esiste"
    running = ast.unparse(body[0])
    assert "search_a_life" in running
    for forbidden in ("life_objects", "documents", "find(", "aggregate", "score"):
        assert forbidden not in running, (
            f"la conversazione si è costruita una sua ricerca: {forbidden}"
        )


# ---------------------------------------------------------------------------
# Quanto lontano guardare
# ---------------------------------------------------------------------------

def test_the_question_decides_how_far_the_calendar_looks():
    """
    §5 + §6: l'intenzione temporale definisce l'orizzonte.

    «Cosa ho domani» e «quando parto» non hanno la stessa portata, e una
    finestra che non c'entra con la domanda risponde niente — che si legge
    come «non ce l'hai in calendario».
    """
    from conversation_engine.ai_core.tools.calendar_caps import (
        _MAX_WINDOW_DAYS,
        _window_for,
    )

    now = datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc)

    today = _window_for("today", now)
    assert today[0].hour == 0 and (today[1] - today[0]).days == 1

    tomorrow = _window_for("tomorrow", now)
    assert tomorrow[0].day == 11 and (tomorrow[1] - tomorrow[0]).days == 1

    # La prossima volta che succede una cosa può essere fra dieci giorni: è
    # esattamente il caso che rispondeva «non risulta».
    nxt = _window_for("next_occurrence", now)
    assert (nxt[1] - nxt[0]).days == _MAX_WINDOW_DAYS
    assert (nxt[1] - now).days > 30

    # Una parola che non è una di queste non inventa nessuna finestra.
    assert _window_for("", now) is None
    assert _window_for("quando parto per vibo", now) is None


def test_nobody_widened_the_default_window_instead_of_fixing_it():
    """
    §5: non si risolveva alzando 7 a 30.

    Sarebbe stato un numero diverso davanti allo stesso difetto: la finestra
    continuerebbe a non avere niente a che vedere con la domanda, e la
    prossima cosa a undici giorni sparirebbe di nuovo.
    """
    from conversation_engine.ai_core.tools import calendar_caps

    assert calendar_caps._DEFAULT_WINDOW_DAYS == 7


def test_no_domain_word_decides_a_temporal_horizon():
    """
    §5 + §6: nessun «Vibo», nessun «viaggio», nessun «notaio» nel codice che
    sceglie quanto lontano guardare. Le parole ammesse dicono che genere di
    momento si cerca, e potrebbero essere la vita di chiunque.
    """
    from conversation_engine.ai_core.tools.calendar_caps import _HOW_FAR

    assert set(_HOW_FAR) == {
        "today", "tomorrow", "next_days", "next_occurrence", "broad_future",
    }
    source = (
        HERE / "conversation_engine" / "ai_core" / "tools" / "calendar_caps.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
            "_window_for",
        ):
            running = ast.unparse(node).lower()
            for word in ("vibo", "viaggio", "partenza", "notaio", "dentista"):
                assert word not in running, f"l'orizzonte conosce «{word}»"


# ---------------------------------------------------------------------------
# Lo stesso impegno resta uno
# ---------------------------------------------------------------------------

def test_the_same_commitment_asked_twice_stays_one():
    """
    §10: la durata non fa di un impegno un altro impegno.

    Trovato sul calendario vero: la stessa frase detta due volte a nove
    minuti di distanza ha prodotto due «Chiamare il notaio» alle 19:00, uno
    che finiva alle 19:15 e uno alle 19:30. L'idempotenza a valle riconosce
    l'atto dall'impronta dei parametri, e fra i parametri c'è la fine: due
    minuti di differenza sono bastati a far sembrare nuovo un impegno che
    c'era già.
    """
    async def body():
        client, db = await _db()
        uid = f"vc_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            start = datetime.now(timezone.utc) + timedelta(days=2)
            first = await _a_draft(
                db, uid, title="Chiamare il notaio", start=start,
                end=start + timedelta(minutes=15),
            )

            # La stessa cosa, chiesta di nuovo, con una durata scelta diversa.
            twin = await calendar_caps._already_have_one(
                db, uid, title="Chiamare il notaio", start=start.isoformat(),
            )
            assert twin is not None and twin["id"] == first
            assert twin.get("_starts_at_the_same_time") is True

            # Un impegno con lo stesso nome a un'ora diversa resta un altro
            # discorso: quello è uno spostamento, e lo decide chi ragiona.
            moved = await calendar_caps._already_have_one(
                db, uid, title="Chiamare il notaio",
                start=(start + timedelta(hours=3)).isoformat(),
            )
            assert moved is not None
            assert not moved.get("_starts_at_the_same_time")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_something_already_in_the_calendar_is_said_not_written_again():
    """
    §11: la risposta giusta è «è già in agenda», senza una seconda scrittura.
    """
    source = (
        HERE / "conversation_engine" / "ai_core" / "tools" / "calendar_caps.py"
    ).read_text(encoding="utf-8")
    assert '"operation": "already_created"' in source
    assert "_starts_at_the_same_time" in source
    assert "Non crearne un secondo" in source
    # E deve dire anche cosa NON e' successo: con «ok» e basta, alla prova
    # la risposta e' stata «ti ho aggiunto il promemoria» per un promemoria
    # che c'era gia' e che nessuno aveva appena scritto.
    assert '"created_now": False' in source
    assert 'non dire «ho ' in source


def test_a_cancelled_commitment_does_not_count_as_already_there():
    """
    Quello che qualcuno ha cancellato non è qualcosa che ha già.

        «C'È GIÀ» È UN'AFFERMAZIONE SUL MONDO, NON SU UNA RIGA.
    """
    async def body():
        client, db = await _db()
        uid = f"vc_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            start = datetime.now(timezone.utc) + timedelta(days=2)
            ref = await _a_draft(db, uid, title="Chiamare il notaio", start=start)
            await db.calendar_event_drafts.update_one(
                {"id": ref}, {"$set": {"status": "cancelled"}},
            )
            twin = await calendar_caps._already_have_one(
                db, uid, title="Chiamare il notaio", start=start.isoformat(),
            )
            assert twin is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# La stessa ORA, da qualunque parte le si parli
# ---------------------------------------------------------------------------

def test_voice_and_text_reach_the_same_knowledge_by_the_same_road():
    """
    §8: la modalità di ingresso non cambia cosa ORA può sapere.

    Non c'è niente da verificare a valle, e questo è il punto: la voce
    consegna delle parole a `sendWords`, che è la funzione del testo, e da lì
    in poi esiste un solo percorso. Se un giorno comparisse un ramo che
    guarda da dove arrivano le parole, questo test se ne accorge.
    """
    screen = (
        FRONTEND / "src" / "components" / "ora" / "OraConversationScreen.tsx"
    ).read_text(encoding="utf-8")
    code = screen.replace("/*", "\n//").split("\n")
    running = "\n".join(
        line for line in code if not line.strip().startswith(("//", "*"))
    )
    assert "useVoice(" in running
    assert "sendWords(words)" in running
    # Nessuna scelta di strumenti, contesto o memoria che dipenda dalla voce.
    for forbidden in ("startedByVoice.current ?", "if (startedByVoice"):
        assert forbidden not in running.replace(
            "origin: startedByVoice.current", "",
        ), f"la voce cambia il percorso: {forbidden}"


def test_the_voice_has_no_search_of_its_own():
    """
    §3 + §8: la voce non si è costruita un modo suo di sapere le cose.

    Guardato sul codice che gira, non sui commenti: là dentro la parola
    «memoria» compare apposta, per dire che non ce n'è nessuna.
    """
    for name in ("speech.ts", "useVoice.ts"):
        source = (FRONTEND / "src" / "voice" / name).read_text(encoding="utf-8")
        running = source
        while "/*" in running and "*/" in running:
            head, rest = running.split("/*", 1)
            running = head + rest.split("*/", 1)[1]
        running = "\n".join(
            line for line in running.split("\n")
            if not line.strip().startswith("//")
        ).lower()
        for forbidden in ("search", "memor", "fetch(", "api.", "lifesearch"):
            assert forbidden not in running, (
                f"{name}: la voce sa qualcosa per conto suo ({forbidden})"
            )
