"""
V3.13 Sprint 3 — ORA al telefono.

    UNA CHIAMATA È UN'AZIONE CHE RAGGIUNGE UNA PERSONA.
    NON AVER CAPITO È UN ESITO.
    PREPARARE NON È CHIAMARE.

Quello che si verifica qui non è che la telefonata funzioni: quella si prova
telefonando, e senza un operatore non si può. Si verifica ciò che il codice
possiede, e sono le cose che farebbero danno: che una chiamata non parta da
sola, che ORA non accetti a nome di qualcuno cose che non le sono state
permesse, che si dichiari per quello che è, e che da una telefonata capita a
metà non nasca un appuntamento inventato.
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


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    await db.phone_calls.delete_many({"owner_id": uid})


# ---------------------------------------------------------------------------
# Una chiamata non parte mai da sola
# ---------------------------------------------------------------------------

def test_a_phone_call_is_a_capability_that_never_starts_by_itself():
    """
    §1: l'autorità è quella che c'è, e telefonare è sotto il suo tetto.

    `phone.call` raggiunge una persona ed è difficilmente reversibile — non
    per il costo, che è un centesimo, ma perché dall'altra parte c'è qualcuno
    che adesso sa una cosa e forse l'ha già segnata sul suo registro. Non
    esiste un annulla, e quindi non esiste un percorso in cui parta da sola.
    """
    async def body():
        client, db = await _db()
        uid = f"tel_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import _NEVER_AUTONOMOUS
            from agent.capabilities import CapabilityResolver

            assert "phone.call" in _NEVER_AUTONOMOUS, (
                "una telefonata può partire da sola"
            )

            resolved = await CapabilityResolver(db).resolve(uid, "phone.call")
            assert resolved.known
            assert resolved.writes, "telefonare non risulta un'azione sul mondo"
            assert resolved.reaches_third_party
            assert resolved.reversibility == "hardly"
            assert not resolved.financial, (
                "telefonare non è un'azione economica: se lo diventasse, "
                "sarebbe perché qualcuno ha aggiunto un pagamento"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_nothing_in_the_conversation_can_dial_a_number():
    """
    §1: la capacità della conversazione prepara, e si ferma.

    Una capacità che compone il numero da sola significa che una frase letta
    storta fa squillare il telefono di un estraneo. Il sì non è un attrito da
    ridurre: è il punto.
    """
    caps = _code_only((HERE / "telephone" / "caps.py").read_text(encoding="utf-8"))
    for dialling in ("carrier", "nexmo", "httpx", "place("):
        assert dialling not in caps, f"la capacità compone il numero: {dialling}"

    # E chi compone il numero pretende un sì su *questa* chiamata.
    router = _code_only((HERE / "telephone" / "router.py").read_text(encoding="utf-8"))
    assert "payload.get('confirmed')" in router.replace('"', "'")
    assert "carrier.place(" in router, "nessuno compone il numero: allora non si chiama"

    # E il numero si compone in un posto solo: si è già cambiato operatore due
    # volte, e ogni volta è costato questo file e nient'altro.
    carrier = _code_only((HERE / "telephone" / "carrier.py").read_text(encoding="utf-8"))
    assert "nexmo.com" in carrier
    for elsewhere in ("service.py", "briefing.py", "models.py", "same_ora.py"):
        other = (HERE / "telephone" / elsewhere).read_text(encoding="utf-8")
        for named in ("nexmo", "vonage", "twilio", "telnyx"):
            assert named not in other.lower(), (
                f"telephone/{elsewhere} conosce l'operatore: non deve"
            )


def test_only_italian_numbers():
    """
    §Vincoli: national calls only.

    Non è una precauzione sui costi: è che questo pilota è stato pensato,
    provato e autorizzato per un paese solo, e un prefisso diverso è una cosa
    di cui nessuno ha discusso.
    """
    from telephone.service import _national

    #     UN NUMERO SCRITTO COME LO SCRIVE UN OPERATORE È UN NUMERO.
    #
    # Le quattro forme in cui una persona o un fornitore scrivono lo stesso
    # numero devono arrivare allo stesso posto. La terza — prefisso
    # internazionale, solo cifre, senza il più — è quella che i fornitori di
    # telefonia usano davvero, ed era l'unica che tornava vuota: la chiamata
    # si fermava con «numero non italiano» prima di raggiungere la rete, il
    # che sembra un rifiuto di merito e non lo è.
    assert _national("+39 333 1234567") == "+393331234567"
    assert _national("3331234567") == "+393331234567"
    assert _national("393331234567") == "+393331234567"
    assert _national("0039 333 1234567") == "+393331234567"
    assert _national("06 12345678") == "+390612345678"
    # E tutto il resto non è un numero da chiamare.
    assert _national("+1 415 555 0100") == ""
    assert _national("+44 20 7946 0000") == ""
    # E la forma senza più non deve aprire una porta all'estero: un tedesco
    # scritto come lo scrive un operatore resta fuori.
    assert _national("4915112345678") == ""
    assert _national("+4915112345678") == ""
    assert _national("") == ""
    assert _national("pronto") == ""


# ---------------------------------------------------------------------------
# Dichiararsi non è una formalità
# ---------------------------------------------------------------------------

def test_ora_says_what_it_is_before_anything_else():
    """
    §2: presentarsi come assistente AI, e non dipendere dalla generazione.

    Chi risponde ha il diritto di sapere nella prima frase che dall'altra
    parte c'è una macchina, e quel diritto non si mette a carico di una
    probabilità: la frase è scritta nel codice e parte per prima.
    """
    from telephone.briefing import disclosure

    said = disclosure("Francesco")
    assert said == "Buongiorno, sono ORA, l'assistente AI di Francesco."
    assert "assistente AI" in said

    # Anche senza un nome, la dichiarazione resta.
    assert "assistente AI" in disclosure("")

    # E il ponte la fa dire per prima, non la lascia decidere al modello.
    bridge = _code_only((HERE / "telephone" / "bridge.py").read_text(encoding="utf-8"))
    assert "say_this_first" in bridge
    assert "greet" in bridge

    # La disciplina vieta di fingersi umana, per iscritto.
    briefing = (HERE / "telephone" / "briefing.py").read_text(encoding="utf-8")
    assert "risposta è no — sei un assistente AI" in briefing
    assert "non dici mai di essere un familiare" in briefing


def test_the_call_is_never_recorded_quietly():
    """
    §Vincoli: no hidden recording claims.

    Registrare una telefonata senza dirlo è una cosa che non si fa, e il modo
    più sicuro di non farla è non accenderla.
    """
    #     IL MODO PIÙ SICURO DI NON REGISTRARE È NON AVERE IL COMANDO.
    #
    # Con questo operatore la registrazione non è un parametro della chiamata:
    # è un comando a sé, `record_start`. Non esiste da nessuna parte, e questa
    # prova esiste perché non compaia un giorno «solo per il debug».
    for name in ("carrier.py", "router.py", "bridge.py", "service.py"):
        code = _code_only((HERE / "telephone" / name).read_text(encoding="utf-8"))
        for recording in ("record_start", "record_stop", "recording", "record="):
            assert recording not in code, (
                f"telephone/{name} può registrare la telefonata: {recording}"
            )


# ---------------------------------------------------------------------------
# Il mandato
# ---------------------------------------------------------------------------

def test_the_mandate_is_a_closed_list():
    """
    §8: niente impegni non autorizzati.

    Al telefono non c'è tempo di chiedere: dall'altra parte una persona
    aspetta una risposta adesso, e «ci devo pensare» detto male diventa un sì.
    Quindi quello che si può accettare si decide prima di comporre il numero,
    e in linea non si allarga mai.
    """
    from telephone.models import Mandate

    mandate = Mandate(
        why_calling="Spostare la visita di giovedì",
        may_agree_to=["un appuntamento fra giovedì e sabato, la mattina"],
    )
    assert mandate.allows("un appuntamento fra giovedì e sabato, la mattina")
    assert mandate.allows("  UN APPUNTAMENTO FRA GIOVEDÌ E SABATO, LA MATTINA  ")
    # Tutto quello che non è nell'elenco è già vietato: non serve elencarlo.
    assert not mandate.allows("un appuntamento lunedì pomeriggio")
    assert not mandate.allows("una pulizia dentale")
    assert not mandate.allows("")

    # Un mandato vuoto è valido, e vuol dire che questa chiamata serve solo a
    # chiedere.
    only_asking = Mandate(why_calling="Chiedere quanto costa una visita")
    assert only_asking.may_agree_to == []
    assert not only_asking.allows("qualunque cosa")


def test_what_ora_agreed_to_is_checked_against_the_mandate_afterwards():
    """
    §8: il mandato si controlla anche dopo.

    Prima serve a impedire; dopo serve a sapere. Se un giorno il modello
    accettasse qualcosa fuori mandato, l'unico modo di accorgersene è
    guardare — e accorgersene è la condizione per poterlo dire alla persona
    invece di scoprirlo dal dentista.
    """
    async def body():
        client, db = await _db()
        uid = f"tel_{uuid.uuid4().hex[:8]}"
        try:
            from telephone.models import CallOutcome, Mandate, PhoneCall
            from telephone.service import TelephoneService

            call = PhoneCall(
                owner_id=uid,
                mandate=Mandate(
                    why_calling="Spostare la visita",
                    may_agree_to=["un orario fra giovedì e sabato"],
                ),
                outcome=CallOutcome(
                    understood=True,
                    in_a_line="Spostata a venerdì",
                    # Concreto, e dentro il permesso astratto. Il primo
                    # controllo confrontava stringhe e segnalava questo come
                    # una violazione: un falso allarme su un controllo di
                    # sicurezza è peggio di nessun controllo.
                    agreed_to=["venerdì 18 alle 10", "una pulizia dentale"],
                    outside_the_mandate=["una pulizia dentale"],
                ),
            )
            service = TelephoneService(db)
            checked = service.kept_the_mandate(call)
            assert checked["checked"]
            assert not checked["kept"]
            assert checked["outside_the_mandate"] == ["una pulizia dentale"], (
                "un appuntamento dentro il mandato viene segnalato come violazione"
            )

            # E quando il mandato è vuoto, la rete sotto è il codice: una
            # chiamata che poteva solo chiedere non può aver accettato niente.
            call.mandate = Mandate(why_calling="Chiedere quanto costa")
            call.outcome.outside_the_mandate = []
            only_asking = service.kept_the_mandate(call)
            assert not only_asking["kept"]
            assert set(only_asking["outside_the_mandate"]) == {
                "venerdì 18 alle 10", "una pulizia dentale",
            }
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# L'esito
# ---------------------------------------------------------------------------

def test_an_outcome_without_a_confirmed_time_is_not_a_calendar_entry():
    """
    §F + §13: non inventare conferme.

    «Facciamo giovedì?» «eh, giovedì ho pieno, vediamo» non è un appuntamento
    di giovedì, ed è esattamente la trascrizione da cui un estrattore
    disattento tira fuori un giovedì. Servono due cose perché da una
    telefonata nasca una riga in agenda: aver capito, e avere un momento.
    """
    from telephone.models import CallOutcome

    assert not CallOutcome().worth_writing_down()
    # Capito, ma senza un orario: è una cosa da dire, non da scrivere.
    assert not CallOutcome(
        understood=True, in_a_line="Richiamano loro"
    ).worth_writing_down()
    # Un orario, ma senza aver capito: peggio ancora.
    assert not CallOutcome(
        understood=False, when="2026-09-17T11:00:00+02:00"
    ).worth_writing_down()
    # Tutte e due: allora sì.
    assert CallOutcome(
        understood=True, in_a_line="Spostata", when="2026-09-17T11:00:00+02:00"
    ).worth_writing_down()


def test_a_call_that_said_nothing_says_so():
    """§11: una chiamata senza parole produce un esito, non un vuoto."""
    async def body():
        client, db = await _db()
        uid = f"tel_{uuid.uuid4().hex[:8]}"
        try:
            from telephone.models import Mandate, PhoneCall
            from telephone.service import TelephoneService

            call = PhoneCall(owner_id=uid, mandate=Mandate(why_calling="Chiedere"))
            outcome = await TelephoneService(db).read_what_happened(call)
            assert outcome.understood is False
            assert outcome.unclear
            assert not outcome.worth_writing_down()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Nessun secondo di niente
# ---------------------------------------------------------------------------

def test_the_phone_does_not_bring_a_second_brain():
    """
    §NON costruire un secondo agente.

    Il modello in linea è una bocca e un orecchio. Non ha una memoria sua, non
    ha un archivio suo, non ha uno scheduler suo, e non scrive da nessuna
    parte: quello che sa gli è stato messo in mano prima di comporre il
    numero, e quello che ne esce lo legge dopo il motore di sempre.
    """
    bridge = _code_only((HERE / "telephone" / "bridge.py").read_text(encoding="utf-8"))
    for forbidden in (
        "insert_one", "update_one", "delete_", "db.", "memories",
        "life_objects", "financial_facts", "calendar", "scheduler", "cron",
    ):
        assert forbidden not in bridge, f"il ponte fa una cosa che non è sua: {forbidden}"

    # E la lettura dell'esito passa dal gestore dei modelli di sempre, non da
    # un secondo fornitore.
    service = _code_only((HERE / "telephone" / "service.py").read_text(encoding="utf-8"))
    assert "from llm.manager import ProviderManager" in service
    assert "openai" not in service.lower(), "il servizio parla con un fornitore per conto suo"

    # L'autorità non viene ricalcolata: si chiede a chi decide già tutto.
    assert "from agent.authority import AuthorityService" in service
    assert "class AuthorityService" not in service
    for judging in ("_at_least_as_cautious", "apply_ceiling", "has_grant =", "def _grant"):
        assert judging not in service, f"il telefono giudica per conto suo: {judging}"


def test_the_public_doors_do_nothing_on_their_own():
    """
    §A + §G: le rotte dell'operatore sono pubbliche, e inerti.

        UNA PORTA PUBBLICA CHE AGISCE SU QUALUNQUE COSA È UNA PORTA APERTA.

    Qui non c'è una password da chiedere: chi bussa è un operatore telefonico,
    non un browser, e non ha una sessione di ORA. La protezione è strutturale
    invece che segreta — queste porte sanno agire **soltanto** su una
    telefonata che ORA ha davvero composto e sta aspettando. Un riferimento
    sconosciuto non produce un errore e non produce un effetto: produce un
    copione che saluta e chiude.
    """
    code = _code_only(
        (HERE / "telephone" / "vonage_router.py").read_text(encoding="utf-8")
    )
    assert "_the_call_we_are_waiting_for" in code
    # Tutte e quattro le porte passano di lì: il copione, il ripiego, gli
    # stati e l'audio.
    assert code.count("_the_call_we_are_waiting_for(") >= 4, (
        "una delle porte pubbliche agisce senza guardare di che chiamata si tratta"
    )
    assert "EXPECTING" in code, "una chiamata già finita accetterebbe ancora eventi"

    # E l'audio non si apre nemmeno: un websocket verso una telefonata che non
    # esiste è una porta che qualcuno può tenere aperta.
    audio = code.split("async def socket")[1][:900]
    assert "close(code=4404)" in audio
    assert audio.index("close(code=4404)") < audio.index("accept()"), (
        "il websocket viene accettato prima di sapere se la chiamata esiste"
    )


def test_the_live_voice_bridge_is_not_wired_yet_and_says_so():
    """
    §E: in 3.1 si prova il filo, non la voce.

    `bridge.py` esiste — contiene il collegamento al modello che ascolta e
    risponde in linea, e la disciplina sui turni e sulle interruzioni — ma non
    è collegato a niente: il trasporto di Vonage porta PCM binario a 16 kHz,
    e quel ponte era scritto per pacchetti base64 dentro JSON. Farlo combaciare
    è lo Sprint 3.2.

    Questa prova esiste perché quel file non venga scambiato per qualcosa che
    funziona. Se un giorno qualcuno lo collega, questa prova fallisce, e
    fallire qui è il modo giusto di accorgersene.
    """
    vonage = _code_only(
        (HERE / "telephone" / "vonage_router.py").read_text(encoding="utf-8")
    )
    assert "LiveVoice" not in vonage, (
        "il ponte è stato collegato: aggiorna questa prova e la documentazione"
    )
    # E il file dice per iscritto che non è collegato, così chi lo apre lo sa.
    bridge = (HERE / "telephone" / "bridge.py").read_text(encoding="utf-8")
    assert "Sprint 3.2" in bridge, (
        "il ponte non dichiara di non essere collegato"
    )


def test_the_carrier_events_are_translated_into_our_words():
    """
    §G: gli stati dell'operatore, tradotti una volta sola.

    Il resto del telefono non conosce i nomi degli stati di nessun fornitore:
    riceve «squilla», «ha risposto», «è finita». È la ragione per cui cambiare
    operatore — due volte, ormai — è costato un file e non tre.
    """
    from telephone.carrier import read_event

    answered = read_event({"status": "answered", "uuid": "abc-123"})
    assert answered["what"] == "answered"
    assert answered["call_ref"] == "abc-123"

    assert read_event({"status": "ringing"})["what"] == "ringing"
    assert read_event({"status": "started"})["what"] == "ringing"

    # Come è finita: la parola dell'operatore diventa una delle nostre.
    for status, ours in (
        ("completed", "they_hung_up"),
        ("cancelled", "we_hung_up"),
        ("busy", "busy"),
        ("timeout", "no_answer"),
        ("unanswered", "no_answer"),
        # «rifiutata dalla rete» non è «non ha risposto nessuno»: il primo
        # tentativo vero è tornato `rejected/restricted`, e tradurlo in
        # «no_answer» dava la colpa alla persona chiamata per una cosa
        # successa prima che il suo telefono squillasse.
        ("rejected", "failed"),
        ("failed", "failed"),
    ):
        ended = read_event({"status": status, "uuid": "abc-123"})
        assert ended["what"] == "ended", f"«{status}» non risulta una fine"
        assert ended["ended_how"] == ours, f"«{status}» tradotto male"

    # E il perché viaggia con lo stato, quando l'operatore lo dice: senza
    # quella parola, un rifiuto della rete e un telefono spento sono
    # indistinguibili, e si sistemano in posti diversi.
    refused = read_event({"status": "rejected", "reason": "restricted", "uuid": "x"})
    assert refused["why"] == "restricted"
    assert refused["ended_how"] == "failed"

    # E qualcosa che non conosciamo non diventa niente di pericoloso.
    assert read_event({"status": "bridged"})["what"] == "something_else"
    assert read_event({})["what"] == "something_else"


def test_the_script_opens_the_audio_and_records_nothing():
    """
    §A + §G: il copione dice una cosa sola, e non registra.

    Un NCCO è un'istruzione, non una conversazione: qui dice «collega questa
    chiamata a un websocket verso ORA», e basta. Non fa parlare nessuno, non
    suona attesa, e soprattutto non contiene nessuna azione di registrazione —
    il modo più sicuro di non registrare è non avere il comando.
    """
    import json as _json

    from telephone.carrier import ncco_for, ncco_when_something_broke

    script = ncco_for("tel_prova")
    assert isinstance(script, list) and len(script) == 1
    step = script[0]
    assert step["action"] == "connect"
    endpoint = step["endpoint"][0]
    assert endpoint["type"] == "websocket"
    assert endpoint["uri"].startswith("wss://")
    assert "/vonage/socket?call_id=tel_prova" in endpoint["uri"]
    assert endpoint["content-type"].startswith("audio/l16")

    # Nel copione non viaggia niente della vita di nessuno: solo riferimenti.
    written = _json.dumps(script, ensure_ascii=False)
    for leaking in ("perche", "mandate", "why_calling", "owner"):
        assert leaking not in written, f"il copione racconta qualcosa: {leaking}"

    # Il ripiego dice che non si può e chiude: un copione vuoto lascerebbe una
    # persona con un telefono muto, aperto e a pagamento.
    spare = ncco_when_something_broke()
    assert spare[0]["action"] == "talk"
    assert len(spare) == 1

    #     IL MODO PIÙ SICURO DI NON REGISTRARE È NON AVERE IL COMANDO.
    for name in ("carrier.py", "vonage_router.py", "router.py", "service.py"):
        code = _code_only((HERE / "telephone" / name).read_text(encoding="utf-8"))
        for recording in ("record", "recording"):
            assert recording not in code.lower(), (
                f"telephone/{name} può registrare la telefonata: {recording}"
            )
