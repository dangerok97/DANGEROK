"""
V3.13 Sprint 3.1 — il filo telefonico, provato sulle rotte vere.

    IL TRASPORTO TELEFONICO NON È UNA VOCE. È UN ATTUATORE.
    NIENTE DI QUELLO CHE PASSA DI LÌ RESTA LÌ.

Le prove dello Sprint 3 guardavano l'autorità, il mandato e l'esito. Queste
guardano il filo: che le quattro porte esistano dove sono già scritte nel
pannello del fornitore, che rispondano quello che l'operatore si aspetta, che
non facciano niente quando qualcuno bussa a caso, e che l'audio non lasci
tracce da nessuna parte.
"""

from __future__ import annotations

import ast
import os
import sys
import uuid
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)


def _code_only(text: str) -> str:
    """Il file senza la sua prosa: una guardia non deve misurare un commento."""
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


# ---------------------------------------------------------------------------
# Dove stanno le porte
# ---------------------------------------------------------------------------

def test_the_carrier_routes_are_not_under_api():
    """
    §G: le rotte di Vonage non finiscono sotto `/api`.

    Non è una preferenza estetica. Gli indirizzi sono già scritti nel pannello
    del fornitore — `/vonage/answer`, `/vonage/event`, `/vonage/fallback` — e
    montarle sotto `/api` per simmetria con tutto il resto significherebbe
    rompere una configurazione che funziona. Una configurazione che funziona
    non si rompe per ordine.

    E c'è una ragione più profonda: quelle porte non hanno una sessione. Le
    chiama un operatore telefonico, non un browser; non c'è un JWT di ORA da
    controllare, e stare sotto `/api` suggerirebbe il contrario.
    """
    import server

    paths = {getattr(r, "path", "") for r in server.app.routes}
    for needed in ("/vonage/answer", "/vonage/event", "/vonage/fallback", "/vonage/socket"):
        assert needed in paths, f"manca la porta {needed}"
        assert f"/api{needed}" not in paths, (
            f"{needed} è finita anche sotto /api: gli indirizzi del pannello si romperebbero"
        )

    # E quelle verso la persona restano dove sono sempre state, autenticate.
    assert "/api/telephone/prepare" in paths
    assert "/telephone/prepare" not in paths, (
        "una porta verso la persona è uscita da /api: perderebbe l'autenticazione"
    )


# ---------------------------------------------------------------------------
# Che cosa rispondono
# ---------------------------------------------------------------------------

def test_the_answer_webhook_returns_a_valid_ncco(shared_client):
    """
    §G: il copione è un NCCO valido, anche quando la chiamata non si conosce.

    Vonage non capisce gli errori: un 500 o un JSON storto lasciano la persona
    dall'altra parte con un telefono aperto e muto. Quindi qui si risponde
    sempre con un copione — quello che apre l'audio se la telefonata è nostra,
    quello che saluta e chiude se non lo è.
    """
    answer = shared_client.get("/vonage/answer?call_id=tel_inesistente")
    assert answer.status_code == 200
    script = answer.json()
    assert isinstance(script, list) and script, "un NCCO vuoto lascia la linea muta"
    assert script[0]["action"] == "talk", (
        "una chiamata sconosciuta riceve un copione che apre l'audio"
    )

    # Il ripiego è sempre lo stesso, e non prova a recuperare niente.
    spare = shared_client.get("/vonage/fallback")
    assert spare.status_code == 200
    assert spare.json()[0]["action"] == "talk"


def test_the_event_webhook_accepts_every_state_and_acts_on_none(shared_client):
    """
    §G: gli stati si accettano tutti; se ne agisce solo su quelli nostri.

    L'operatore manda `started`, `ringing`, `answered`, `completed` e una
    dozzina d'altri. Nessuno di questi deve poter far esplodere niente, e
    nessuno deve produrre un effetto su una telefonata che ORA non ha
    composto. Rispondere sempre 200 è corretto: un webhook che dà errore viene
    ritentato, e ritentare un evento che non ci riguarda non aiuta nessuno.
    """
    for state in (
        "started", "ringing", "answered", "completed", "busy",
        "cancelled", "failed", "rejected", "timeout", "unanswered", "machine",
    ):
        got = shared_client.post(
            "/vonage/event?call_id=tel_inesistente",
            json={"status": state, "uuid": "non-nostro", "conversation_uuid": "x"},
        )
        assert got.status_code == 200, f"lo stato «{state}» rompe la porta"
        assert got.json() == {"ok": True}

    # Anche un corpo che non è JSON, o che è vuoto: capita, e non è un evento.
    assert shared_client.post("/vonage/event", json={}).status_code == 200
    assert shared_client.post(
        "/vonage/event", content=b"non json", headers={"Content-Type": "application/json"},
    ).status_code == 200


# ---------------------------------------------------------------------------
# Chi può far partire una telefonata
# ---------------------------------------------------------------------------

def test_no_call_starts_without_an_explicit_yes(shared_client):
    """
    §B: una telefonata non parte senza autorizzazione esplicita.

    Due porte separate, e fra le due una persona. `place` senza `confirmed`
    non è un errore di validazione: è il punto dell'intera funzione.
    """
    got = shared_client.post("/api/telephone/tel_qualunque/place", json={})
    # Senza autenticazione non si arriva nemmeno a discuterne.
    assert got.status_code in (401, 403), (
        "la porta che compone il numero è raggiungibile senza autenticazione"
    )

    # E la regola sta nel codice, prima di qualunque chiamata all'operatore.
    router = _code_only((HERE / "telephone" / "router.py").read_text(encoding="utf-8"))
    body = router.split("async def place")[1]
    yes_at = body.index("confirmed")
    dial_at = body.index("dial(")  # V3.21.1a: si compone da `placing.dial`
    assert yes_at < dial_at, (
        "si compone il numero prima di aver controllato il sì"
    )

    # `phone.call` resta fra le cose che non partono mai da sole.
    from agent.authority import _NEVER_AUTONOMOUS

    assert "phone.call" in _NEVER_AUTONOMOUS


def test_the_capability_is_unavailable_until_the_carrier_is_configured():
    """
    §B + §F: senza configurazione ORA sa di non poter telefonare, e lo dice.

    È diverso dal provarci e fallire. Una capacità che risulta disponibile e
    poi non fa niente insegna a chi ragiona che chiedere il permesso è un
    rituale senza conseguenze.
    """
    from telephone.carrier import can_call, why_not

    saved = {
        k: os.environ.get(k)
        for k in (
            "VONAGE_APPLICATION_ID", "VONAGE_PRIVATE_KEY_PATH",
            "VONAGE_FROM_NUMBER", "VONAGE_PUBLIC_BASE_URL",
        )
    }
    try:
        for k in saved:
            os.environ.pop(k, None)
        assert can_call() is False
        missing = why_not()
        for expected in ("applicazione", "chiave", "numero", "indirizzo"):
            assert expected in missing, f"non dice che manca: {expected}"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# La chiave, e l'audio
# ---------------------------------------------------------------------------

def test_the_private_key_never_leaves_the_disk():
    """
    §F + §G: la chiave non finisce in un log, in un database, in una risposta.

        LA CHIAVE NON PASSA DA NESSUNA PARTE DOVE POSSA RESTARE.

    Si legge dal disco al momento di firmare, e quello che gira è un
    lasciapassare che scade in un minuto. Nemmeno il percorso viene registrato:
    un log che dice dove sta una chiave privata è metà del lavoro fatto per
    chi la cerca.
    """
    code = _code_only((HERE / "telephone" / "carrier.py").read_text(encoding="utf-8"))

    # La chiave si legge in un solo posto, e da un percorso di configurazione.
    assert code.count("VONAGE_PRIVATE_KEY_PATH") <= 3
    assert "_private_key" in code

    # Niente di quello che si scrive altrove la contiene, e nessun log la nomina.
    for line in code.splitlines():
        if "logger." in line:
            for leaking in ("key", "path", "private", "token", "jwt"):
                assert leaking not in line.lower(), (
                    f"un log può rivelare la chiave o dove sta: {line.strip()[:80]}"
                )

    # E non finisce in Mongo: il modello della telefonata non ha un posto dove
    # metterla, e questo è il modo più solido di garantirlo.
    call_model = (HERE / "telephone" / "models.py").read_text(encoding="utf-8")
    for leaking in ("private_key", "api_key", "secret", "token"):
        assert leaking not in call_model.lower(), (
            f"il modello della telefonata ha un campo per un segreto: {leaking}"
        )


def test_no_audio_is_ever_persisted():
    """
    §C + §G: dell'audio resta il conteggio, mai il suono.

        QUANTO AUDIO È PASSATO È UN FATTO; L'AUDIO NON LO È.

    Il filo passa migliaia di pacchetti al minuto. Tenerne uno solo, «per il
    debug», significa avere sul disco la voce di una persona che non ha mai
    acconsentito a essere registrata — ed è la ragione per cui qui si contano
    i byte e si lasciano andare.
    """
    code = _code_only(
        (HERE / "telephone" / "vonage_router.py").read_text(encoding="utf-8")
    )

    # Si contano: quanti pacchetti e quanti byte sono passati.
    assert "frames_in += 1" in code
    assert "bytes_in += len(chunk)" in code

    # E non si tiene: nessuna lista che cresce, nessun file, nessuna scrittura
    # del contenuto. Vale per il trasporto e per il runtime.
    runtime = _code_only((HERE / "telephone" / "bridge.py").read_text(encoding="utf-8"))
    for where, source in (("trasporto", code), ("runtime", runtime)):
        # I modi veri di conservare dei byte. `open(` da solo non basta come
        # indizio: `session.open()` apre una linea, non un file, e una guardia
        # che confonde le due cose la si disattiva dopo il terzo falso allarme.
        for keeping in (
            'open("', "open('", "write_bytes", "write_text", "Path(",
            "b''.join", 'b"".join', "append(chunk)", "append(pcm)",
            "wave", "BytesIO", "base64", "insert_one", "gridfs",
        ):
            assert keeping not in source, (
                f"l'audio viene conservato nel {where}: {keeping}"
            )

    # Il pacchetto passa a chi ascolta e finisce lì: non c'è nessuna variabile
    # che lo tenga fra un frame e l'altro.
    assert "await session.hear(chunk)" in code
    assert "await self.ears.hear(pcm)" in runtime

    # Nemmeno un log può portarselo via.
    for line in code.splitlines():
        if "logger." in line:
            assert "chunk" not in line, "un log porta con sé un pezzo di audio"

    # E il modello ha posto per i numeri, non per il suono.
    from telephone.models import PhoneCall

    fields = set(PhoneCall.model_fields)
    assert {"audio_frames", "audio_bytes", "first_audio_ms"} <= fields
    for keeping in ("audio", "recording", "pcm", "samples"):
        assert not any(
            f == keeping or f.endswith("_audio") for f in fields
        ), f"il modello ha un campo per il suono: {keeping}"


# ---------------------------------------------------------------------------
# Stesso ORA
# ---------------------------------------------------------------------------

def test_the_phone_does_not_bring_a_second_conversation():
    """
    §D: VOICE IS NOT A SEPARATE ASSISTANT.

    Quando lo Sprint 3.2 farà diventare parole il parlato di una telefonata,
    quelle parole entreranno **esattamente dove entra una frase scritta
    nell'app**: in `AICoreOrchestrator`. Stessa sessione, stesso Personal Life
    Model, stessa autorità, stessa Life Search.

    La tentazione da evitare è ovvia — costruire «la conversazione telefonica»
    a parte, perché al telefono i turni sono corti e il tempo stringe. Sarebbe
    un secondo ORA, con una seconda memoria di quello che è stato detto e una
    seconda idea di cosa può fare. E due ORA sono zero ORA.
    """
    same = _code_only((HERE / "telephone" / "same_ora.py").read_text(encoding="utf-8"))
    assert "AICoreOrchestrator" in same, (
        "il telefono non passa dal Conversation Engine di sempre"
    )
    assert "orchestrator.message(" in same and "orchestrator.start(" in same

    # Nessun pezzo del telefono si costruisce una conversazione per conto suo.
    for name in (
        "carrier.py", "vonage_router.py", "router.py", "service.py",
        "same_ora.py", "briefing.py", "caps.py",
    ):
        code = _code_only((HERE / "telephone" / name).read_text(encoding="utf-8"))
        for second_brain in (
            "conversation_sessions", "ConversationSession(",
            "class .*Conversation", "history.append", "_prompt =",
        ):
            assert second_brain not in code, (
                f"telephone/{name} si costruisce una conversazione sua: {second_brain}"
            )


def test_a_phone_turn_is_the_same_turn_as_any_other():
    """
    §D: la provenienza cambia, il percorso no.

    `origin` viaggia come provenienza — serve a ORA per sapere che sta
    parlando al telefono e non in chat, il che cambia come si dicono le cose,
    non cosa si può fare. Esattamente come `voice` nello Sprint 1.
    """
    async def body():
        from telephone.same_ora import a_turn_of_conversation

        # Una frase vuota non è un turno, e non ne inventa uno.
        assert await a_turn_of_conversation(
            None, owner_id="u", session_id="s", words="   ",
        ) is None
        assert await a_turn_of_conversation(
            None, owner_id="", session_id="s", words="pronto",
        ) is None

    _run(body())

    same = _code_only((HERE / "telephone" / "same_ora.py").read_text(encoding="utf-8"))
    assert "origin" in same
    # E non c'è nessun ramo che guardi da dove arrivano le parole per decidere
    # *cosa* fare: `origin` viaggia, non comanda.
    assert "if origin ==" not in same and "if origin in" not in same, (
        "il percorso cognitivo si biforca in base a come sono arrivate le parole"
    )


def test_the_authenticated_doors_actually_answer(shared_client):
    """
    §G: le porte verso la persona rispondono davvero, con un'autenticazione vera.

        UN TEST CHE PARLA AL SERVIZIO NON PROVA LA PORTA.

    Questa prova esiste per un difetto che tutte le altre hanno mancato. Il
    router leggeva `user["id"]`, mentre in tutto il prodotto la chiave è
    `user["user_id"]`: ogni richiesta autenticata moriva con un KeyError e un
    500. Nessuna delle prove se n'era accorta perché parlavano tutte a
    `TelephoneService`, che quella chiave non la vede mai — e il difetto è
    saltato fuori al primo tentativo di telefonare sul serio.
    """
    import uuid as _uuid

    import deps

    uid = f"user_{_uuid.uuid4().hex[:12]}"

    async def make():
        await deps.db.users.insert_one(
            {"user_id": uid, "email": f"{uid}@prova.local", "name": "Prova"}
        )

    async def clean():
        await deps.db.users.delete_many({"user_id": uid})

    _run(make())
    try:
        token = deps.make_jwt(uid)
        got = shared_client.get(
            "/api/telephone/available",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert got.status_code == 200, (
            f"la porta autenticata non risponde: {got.status_code} {got.text[:200]}"
        )
        answer = got.json()
        # Dice se si può telefonare, e quando non si può dice perché.
        assert "provider_ready" in answer and "needs_explicit_yes" in answer
        assert answer["needs_explicit_yes"] is True
    finally:
        _run(clean())


def test_a_call_that_went_well_records_no_refusal():
    """
    §G: il motivo del rifiuto si scrive solo se c'è stato un rifiuto.

    Su una telefonata riuscita l'operatore manda comunque `reason: "ok"`, e
    finiva scritto sotto «perché la rete ha rifiutato» — una riga che racconta
    una cosa che non è successa. Trovato sulla prima telefonata riuscita
    davvero, guardando il documento che ne era rimasto.
    """
    code = _code_only(
        (HERE / "telephone" / "vonage_router.py").read_text(encoding="utf-8")
    )
    assert "went_well" in code
    assert 'why_the_network_refused=\'\' if went_well' in code.replace('"', "'"), (
        "una chiamata riuscita registra ancora un motivo di rifiuto"
    )
