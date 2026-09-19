"""
«Chiama la mia ragazza e dille che la amo.»

    ORA HA RISPOSTO «NON HO LA CAPACITÀ TECNICA». NON ERA VERO.

Lo strumento c'era; al modello nessuno l'aveva detto in chiaro, e la sua
descrizione parlava solo di dentisti. E anche se l'avesse usato, il runtime
sapeva spostare, prenotare, disdire e chiedere — non portare una frase.

Queste prove tengono ferme tre cose. La chat sa che può telefonare quando lo
strumento c'è, e non lo promette quando non c'è. Un messaggio è un tipo di
telefonata suo, che non tocca niente nel mondo canonico. E il messaggio lo
sente solo la persona giusta: chi parla non lo conosce finché non ha detto al
backend con chi sta parlando.
"""

from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_post_call_application_v315 import FintoDb  # noqa: E402

UID = "u1"
GIULIA = {
    "id": "con_giulia", "user_id": UID, "name": "Giulia Test",
    "phone": "+39 333 0000042", "kind": "person", "relationship": "ragazza",
}
RICHIESTA = "Chiama la mia ragazza e dille che la amo"


@pytest.fixture
def mondo(monkeypatch):
    """Una rubrica con Giulia, un operatore pronto, nessun modello, niente web."""
    import preparation.contacts as risolutore
    import preparation.readiness as valutatore
    from telephone.service import TelephoneService

    async def nessun_modello(_prep):
        return None

    async def niente(self, db, *, owner_id, who):
        return []

    async def pronto(self, owner_id, **_k):
        return {"denied": False, "provider_ready": True, "why_not": ""}

    monkeypatch.setattr(valutatore, "_what_the_model_sees", nessun_modello)
    monkeypatch.setattr(risolutore.PublicWeb, "look_for", niente)
    monkeypatch.setattr(TelephoneService, "may_i_call", pronto)

    #     NESSUNA PROVA COMPONE DAVVERO.
    import telephone.carrier as operatore

    composti = []

    async def componi(*, to_number, call_id, minutes):
        composti.append({"to": to_number, "call_id": call_id})
        return {"call_ref": f"ref_{len(composti)}"}

    monkeypatch.setattr(operatore, "place", componi)

    db = FintoDb()
    db.composti = composti
    db.contacts.righe.append(dict(GIULIA))
    return db


async def _chiedi(db, detto, **argomenti):
    """Lo strumento della chat, con la frase vera della persona accanto."""
    from telephone.caps import prepare_a_phone_call

    oss = await prepare_a_phone_call(
        argomenti, {"user_id": UID, "db": db, "user_message": detto},
    )
    return oss.payload


# ---------------------------------------------------------------------------
# 1 · La chat sa che può telefonare — solo se può
# ---------------------------------------------------------------------------

def test_the_chat_is_told_it_can_phone_when_the_tool_is_there():
    from conversation_engine.ai_core.prompt import what_ora_can_do

    detto = what_ora_can_do([{"capability": "prepare_a_phone_call"}])["phone"]
    assert "CAN phone" in detto
    assert "private people" in detto
    assert "Never say you cannot make phone calls" in detto


def test_without_the_tool_no_call_is_promised():
    from conversation_engine.ai_core.prompt import what_ora_can_do

    detto = what_ora_can_do([{"capability": "web_search"}])["phone"]
    assert "cannot place phone calls" in detto
    assert "CAN" not in detto


def test_the_real_catalogue_offers_the_phone_to_the_model():
    """Lo strumento non è nascosto: il modello lo vede."""
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    visibili = {t["capability"] for t in ToolRegistry().list_public()}
    assert "prepare_a_phone_call" in visibili


def test_the_tool_description_is_not_only_about_dentists():
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    spec = next(t for t in ToolRegistry().list_public()
                if t["capability"] == "prepare_a_phone_call")
    testo = spec["description"]
    for frase in ("la mia ragazza", "Lorenzo", "mia madre", "Marco", "ristorante"):
        assert frase in testo
    assert "Never tell them you cannot make phone calls" in testo
    assert spec["input_schema"].get("required") == []
    for campo in ("counterparty", "message", "preparation_id", "go_ahead"):
        assert campo in spec["input_schema"]["properties"]


# ---------------------------------------------------------------------------
# 2 · Che tipo di telefonata
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase,tipo,messaggio", [
    ("Chiama la mia ragazza e dille che la amo", "deliver_message", "la amo"),
    ("Chiama Lorenzo e digli che arrivo 20 minuti in ritardo", "deliver_message",
     "arrivo 20 minuti in ritardo"),
    ("Chiama mia madre e dille che passo domani", "deliver_message", "passo domani"),
    ("Chiama Marco e chiedigli se viene a cena", "ask", ""),
    ("Chiama Lorenzo e digli di spostare la partita a calcetto", "reschedule", ""),
])
def test_what_kind_of_call(frase, tipo, messaggio):
    from telephone.mission import kind_of_request
    from telephone.requests import the_message_in

    assert kind_of_request(frase) == tipo
    assert the_message_in(frase) == messaggio


# ---------------------------------------------------------------------------
# 3 · Dalla chat alla preparazione
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_private_person_enters_the_preparation(mondo):
    """«La mia ragazza» → Giulia Test dalla rubrica, con il numero da confermare."""
    p = await _chiedi(mondo, RICHIESTA, counterparty="la mia ragazza", message="la amo")

    assert p["status"] == "preparing"
    assert p["what_kind_of_call"] == "deliver_message"
    assert p["contact"]["name"] == "Giulia Test"
    assert p["contact"]["source_label"] == "Rubrica"
    assert p["number_confirmed"] is False
    assert "È questo il numero corretto" in p["say_this"]
    assert p["nothing_has_happened_yet"] is True
    assert mondo["phone_calls"].righe == []


@pytest.mark.asyncio
async def test_the_message_keeps_the_users_words(mondo):
    """
    Fedeltà: fa fede la frase che la persona ha scritto, non la parafrasi.

    Il modello potrebbe passare «vuole sposarti»: vince «la amo».
    """
    p = await _chiedi(mondo, RICHIESTA, counterparty="la mia ragazza",
                      message="Francesco dice che vuole sposarti")
    assert p["message_to_deliver"] == "la amo"


@pytest.mark.asyncio
async def test_a_yes_the_person_did_not_say_is_refused(mondo):
    """Il modello dice «ha confermato»; la persona ha scritto altro."""
    p = await _chiedi(mondo, RICHIESTA, counterparty="la mia ragazza")
    p2 = await _chiedi(mondo, "Giulia Test", preparation_id=p["preparation_id"],
                       number_is_right=True)

    assert p2["number_confirmed"] is False
    assert "non ha ancora confermato" in p2["not_accepted"]


async def _pronta(db):
    p = await _chiedi(db, RICHIESTA, counterparty="la mia ragazza")
    return await _chiedi(db, "sì, è quello", preparation_id=p["preparation_id"],
                         number_is_right=True)


@pytest.mark.asyncio
async def test_confirmed_number_makes_it_ready_with_a_human_summary(mondo):
    p = await _pronta(mondo)

    assert p["status"] == "ready"
    assert p["number_confirmed"] is True
    s = p["summary"]
    assert s.startswith("Chiamerò Giulia Test")
    assert "«la amo»" in s
    assert "Prima mi assicuro di parlare con Giulia" in s
    for tecnico in ("prep_", "deliver_message", "{", "READY"):
        assert tecnico not in s
    assert p["say_this"].endswith("Vuoi che la chiami?")


@pytest.mark.asyncio
async def test_no_go_ahead_no_call(mondo):
    """Il via libera lo dà la persona, con le sue parole."""
    p = await _pronta(mondo)
    p2 = await _chiedi(mondo, "aspetta un attimo",
                       preparation_id=p["preparation_id"], go_ahead=True)

    assert p2["call_id"] is None
    assert "via libera" in p2["not_accepted"]
    assert mondo["phone_calls"].righe == []


async def _chiedi_in(db, detto, chat, **argomenti):
    """Come `_chiedi`, dentro una chat vera: sessione e turno."""
    from telephone.caps import prepare_a_phone_call

    oss = await prepare_a_phone_call(argomenti, {
        "user_id": UID, "db": db, "user_message": detto,
        "session_id": chat, "reasoning_epoch": f"ep_{detto}",
    })
    return oss.payload


@pytest.mark.asyncio
async def test_final_yes_after_ready_places_the_call(mondo):
    """Sì al riassunto, in un turno successivo → la telefonata parte davvero."""
    p = await _pronta(mondo)
    p2 = await _chiedi_in(mondo, "sì, chiamala", "ces_chat1",
                          preparation_id=p["preparation_id"], go_ahead=True)

    assert p2["status"] == "calling"
    assert p2["say_this"].startswith("Sto chiamando Giulia")
    for tecnico in ("tel_", "call_id", "{", "dialling"):
        assert tecnico not in p2["say_this"]
    assert len(mondo.composti) == 1
    assert mondo.composti[0]["to"] == "+393330000042"
    riga = mondo["phone_calls"].righe[0]
    assert riga["state"] == "dialling"
    assert riga["chat_session_id"] == "ces_chat1"
    assert riga["authority_ref"] == "chat_final_yes"
    assert riga["mandate"]["message"] == "la amo"
    assert riga["mandate"]["recipient"] == "Giulia Test"
    #     IL MOTIVO SI LEGGE A CHIUNQUE. IL MESSAGGIO NO.
    assert "la amo" not in riga["mandate"]["why_calling"]


@pytest.mark.asyncio
async def test_an_untrusted_number_cannot_go_ahead(mondo):
    """Senza numero confermato, nemmeno un sì fa nascere la telefonata."""
    p = await _chiedi(mondo, RICHIESTA, counterparty="la mia ragazza")
    p2 = await _chiedi(mondo, "sì chiamala", preparation_id=p["preparation_id"],
                       go_ahead=True)
    assert p2["call_id"] is None
    assert mondo["phone_calls"].righe == []


@pytest.mark.asyncio
async def test_one_yes_confirms_the_number_not_the_call(mondo):
    """
    Misurato sul vero: un solo «sì» ha confermato il numero E dato il via
    libera, e il riassunto con il messaggio non è mai stato letto.
    """
    p = await _chiedi(mondo, RICHIESTA, counterparty="la mia ragazza")
    p2 = await _chiedi(mondo, "sì", preparation_id=p["preparation_id"],
                       number_is_right=True, go_ahead=True)

    assert p2["number_confirmed"] is True
    assert p2["call_id"] is None
    assert p2["not_accepted"] is None  # non è un errore da ritentare
    assert p2["status"] == "ready"
    assert "«la amo»" in p2["say_this"]
    assert p2["say_this"].endswith("Vuoi che la chiami?")
    assert mondo["phone_calls"].righe == []


@pytest.mark.asyncio
async def test_a_duplicate_final_yes_does_not_call_twice(mondo):
    p = await _pronta(mondo)
    await _chiedi_in(mondo, "sì, chiamala", "ces_chat1",
                     preparation_id=p["preparation_id"], go_ahead=True)
    p3 = await _chiedi_in(mondo, "sì vai", "ces_chat1",
                          preparation_id=p["preparation_id"], go_ahead=True)

    assert len(mondo.composti) == 1
    assert len(mondo["phone_calls"].righe) == 1
    assert p3["say_this"].startswith("Sto già chiamando")


@pytest.mark.asyncio
async def test_the_number_yes_never_dials(mondo):
    """Il sì sul numero, anche con go_ahead nello stesso gesto, non compone."""
    p = await _chiedi(mondo, RICHIESTA, counterparty="la mia ragazza")
    await _chiedi_in(mondo, "sì", "ces_chat1", preparation_id=p["preparation_id"],
                     number_is_right=True, go_ahead=True)
    assert mondo.composti == []


@pytest.mark.asyncio
async def test_the_go_ahead_must_come_in_a_later_turn(mondo):
    """Due chiamate allo strumento nello stesso turno non fanno un sì al riassunto."""
    from telephone.caps import prepare_a_phone_call

    stesso = {"user_id": UID, "db": mondo, "user_message": "sì",
              "session_id": "s1", "reasoning_epoch": "e1"}
    p = await _chiedi(mondo, RICHIESTA, counterparty="la mia ragazza")
    await prepare_a_phone_call({"preparation_id": p["preparation_id"],
                                "number_is_right": True}, stesso)
    o = await prepare_a_phone_call({"preparation_id": p["preparation_id"],
                                    "go_ahead": True}, stesso)
    assert o.payload["call_id"] is None
    assert mondo["phone_calls"].righe == []

    dopo = dict(stesso, reasoning_epoch="e2", user_message="sì, chiamala")
    o = await prepare_a_phone_call({"preparation_id": p["preparation_id"],
                                    "go_ahead": True}, dopo)
    assert o.payload["status"] == "calling"


@pytest.mark.asyncio
async def test_a_trusted_number_is_reused_for_a_message(mondo):
    """Già confermato per Giulia → la volta dopo non si richiede."""
    await _pronta(mondo)
    p = await _chiedi(mondo, "Chiama la mia ragazza e dille che passo alle otto",
                      counterparty="la mia ragazza")
    assert p["number_confirmed"] is True
    assert "già confermato" in p["number_note"]


@pytest.mark.asyncio
async def test_a_business_with_a_number_keeps_the_old_path(mondo):
    """Regressione zero: numero e motivo, senza messaggio, restano diretti."""
    p = await _chiedi(mondo, "chiama lo studio", to_number="+39 06 0000001",
                      calling_whom="Studio Test",
                      why_calling="chiedere se sabato è aperto")
    assert p["status"] == "prepared"
    assert p["call_id"]


# ---------------------------------------------------------------------------
# 4 · Durante la telefonata: il messaggio solo alla persona giusta
# ---------------------------------------------------------------------------

def _chiamata(**cambia):
    from telephone.models import Mandate, PhoneCall

    campi = dict(
        id="tel_giulia", owner_id=UID, to_number="+393330000042",
        calling_whom="Giulia Test",
        mandate=Mandate(why_calling="consegnare un messaggio a Giulia Test",
                        message="la amo", recipient="Giulia Test"),
        state="talking",
    )
    campi.update(cambia)
    return PhoneCall(**campi)


def _sessione(call=None):
    from telephone.dossier import TelephoneCallDossier
    from telephone.live import MissionVoiceSession
    from telephone.mission import packet_for

    call = call or _chiamata()
    fascicolo = TelephoneCallDossier(owner_id=UID, call_id=call.id,
                                     on_behalf_of="Francesco")
    packet = packet_for(call, fascicolo)

    async def send(_pcm):
        return None

    return MissionVoiceSession(None, owner_id=UID, session_ref="s", send=send,
                               call=call, packet=packet)


def test_the_message_is_not_in_what_the_model_reads():
    """
    IL MESSAGGIO NON SI DA' A CHI PARLA FINCHE' NON SA CON CHI PARLA.
    """
    s = _sessione()
    p = s.packet
    assert p.mission_type == "deliver_message"
    assert "la amo" not in p.for_the_model()
    assert "la amo" not in p.say_this_first
    assert p.say_this_first.endswith("Parlo con Giulia?")
    assert "la amo" not in str(s._setup_message())


def test_the_delivery_has_its_own_tools():
    from telephone.live import tools_for

    nomi = [f["name"] for f in tools_for("deliver_message")[0]["function_declarations"]]
    assert {"recipient_confirmed", "recipient_not_available",
            "message_delivered", "fail_mission"} <= set(nomi)
    #     NIENTE DA FARSI CONFERMARE: NIENTE `complete_mission`.
    assert "complete_mission" not in nomi


def test_the_packet_forbids_answering_for_him():
    """«Chiedigli se viene stasera»: non si risponde al posto suo."""
    p = _sessione().packet
    vietato = " ".join(p.forbidden_actions)
    assert "rispondere a domande al posto di Francesco" in vietato
    assert "cambiare il significato" in vietato
    assert "a chiunque non sia Giulia" in vietato


@pytest.mark.asyncio
async def test_delivered_before_identity_is_refused():
    """Non si può dire di aver consegnato una cosa che non si conosceva."""
    s = _sessione()
    r = await s._answer_one("message_delivered", {"recipient_reply": "ok"})
    assert r["accepted"] is False
    assert s.outcome is None


@pytest.mark.asyncio
async def test_identity_first_then_the_message_then_the_reply():
    s = _sessione()
    r = await s._answer_one("recipient_confirmed", {"how_they_confirmed": "sì, sono io"})
    assert r["message_to_deliver"] == "la amo"
    assert "senza cambiarne il significato" in r["say_it_like_this"]
    #     IL SENTIMENTO E' DI CHI MANDA, NON DI ORA.
    assert "mi ha chiesto di dirti che ti ama" in r["say_it_like_this"]
    assert "Mai in prima persona" in r["say_it_like_this"]

    r2 = await s._answer_one("message_delivered",
                             {"recipient_reply": "Digli che lo amo anch'io."})
    assert r2["accepted"] is True
    assert s.outcome.status == "success"
    assert s.outcome.delivery == "delivered"
    assert s.outcome.recipient_reply == "Digli che lo amo anch'io."


@pytest.mark.asyncio
async def test_the_wrong_person_never_gets_the_message():
    """Risponde la sorella: niente messaggio, e l'esito lo dice."""
    s = _sessione()
    r = await s._answer_one("recipient_not_available",
                            {"who_answered": "someone_else",
                             "callback_hint": "richiamare dopo le sei"})
    assert "message_to_deliver" not in r
    assert "la amo" not in str(r)
    assert s.outcome.delivery == "recipient_unavailable"
    assert s._recipient_ok is False


# ---------------------------------------------------------------------------
# 5 · Dopo: niente applicazione finta, e una riga umana
# ---------------------------------------------------------------------------

def _con_esito(**esito):
    from telephone.mission import CallMissionOutcome

    c = _chiamata(state="ended", how_it_ended="we_hung_up")
    c.metrics = {"outcome": CallMissionOutcome(mission_id="mis_tel_giulia", **esito).model_dump()}
    return c


@pytest.mark.asyncio
async def test_a_delivered_message_writes_no_application(mondo):
    from telephone.application import APPLICATIONS, apply_the_outcome
    from telephone.mission import CallMissionOutcome

    c = _con_esito(status="success", delivery="delivered")
    fatto = await apply_the_outcome(
        mondo, c, CallMissionOutcome(mission_id="mis_tel_giulia", status="success",
                                     delivery="delivered"))
    assert fatto is None
    assert mondo[APPLICATIONS].righe == []


@pytest.mark.parametrize("esito,atteso", [
    (dict(status="success", delivery="delivered",
          recipient_reply="Digli che lo amo anch'io."),
     "Giulia ti ha risposto: «Digli che lo amo anch'io.»"),
    (dict(status="success", delivery="delivered"), "Messaggio consegnato a Giulia."),
    (dict(status="failed", delivery="recipient_unavailable"),
     "Non sono riuscita a parlare con Giulia: ha risposto un'altra persona."),
    (dict(status="failed", delivery="no_answer"), "Non sono riuscita a parlare con Giulia."),
])
def test_the_history_tells_it_like_a_person(esito, atteso):
    from telephone.history import in_one_line

    assert in_one_line(_con_esito(**esito)) == atteso


@pytest.mark.asyncio
async def test_a_delivered_message_completes_the_plan(mondo):
    """Il piano di una consegna si chiude sull'esito della consegna."""
    from autonomy.orchestrator import _read_the_outcome
    from autonomy.plan import AutonomousActionPlan, remember

    plan = await remember(mondo, AutonomousActionPlan(
        owner_id=UID, source_ref="x", call_id="tel_giulia",
        authority_state="granted", state="executing"))
    fatto = await _read_the_outcome(
        mondo, plan, _con_esito(status="success", delivery="delivered",
                                recipient_reply="grazie"))
    assert fatto.state == "completed"
    assert fatto.history[-1].says == "Giulia ti ha risposto: «grazie»"

    plan2 = await remember(mondo, AutonomousActionPlan(
        owner_id=UID, source_ref="y", call_id="tel_giulia",
        authority_state="granted", state="executing"))
    fallito = await _read_the_outcome(
        mondo, plan2, _con_esito(status="failed", delivery="no_answer"))
    assert fallito.state == "failed"


def test_the_delivery_rules_travel_only_with_a_delivery():
    """Il paragrafo della consegna c'è solo quando la missione è una consegna."""
    testo = str(_sessione()._setup_message()["setup"]["systemInstruction"])
    assert "un messaggio da consegnare" in testo
    assert "recipient_confirmed" in testo
    assert "la amo" not in testo

    from test_live_runtime_v313 import _packet
    from telephone.live import MissionVoiceSession

    async def send(_pcm):
        return None

    altra = MissionVoiceSession(None, owner_id=UID, session_ref="s", send=send,
                                packet=_packet())
    assert "un messaggio da consegnare" not in str(
        altra._setup_message()["setup"]["systemInstruction"])


@pytest.mark.asyncio
async def test_complete_mission_is_redirected_in_a_delivery():
    s = _sessione()
    r = await s._answer_one("complete_mission", {"confirmed_changes": {}})
    assert r["accepted"] is False
    assert "message_delivered" in r["do_this"]


def test_each_kind_of_call_accepts_only_its_own_tools():
    from telephone.live import tools_allowed_for

    assert "complete_mission" not in tools_allowed_for("deliver_message")
    assert "recipient_confirmed" not in tools_allowed_for("reschedule")
    assert "recipient_confirmed" in tools_allowed_for("deliver_message")


@pytest.mark.asyncio
async def test_the_sentence_to_say_carries_name_number_and_source(mondo):
    """
    Misurato sul vero: con i pezzi separati il modello ha detto solo «È questo
    il numero corretto?». La frase pronta porta sempre tutti e tre.
    """
    p = await _chiedi(mondo, RICHIESTA, counterparty="la mia ragazza")
    assert "Giulia Test" in p["say_this"]
    assert "+393330000042" in p["say_this"]
    assert "Rubrica" in p["say_this"]
    assert p["say_this"].endswith("È questo il numero corretto?")
    assert "per intero" in p["how_to_say_it"]
    assert "la mia ragazza" not in p["ora_says"]


# ---------------------------------------------------------------------------
# Trovato dalla prova in app: la richiesta non è una conferma
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_request_itself_never_confirms_the_number(mondo):
    """
    Misurato in app: «Chiama la mia ragazza…» comincia con «chiama», che era
    fra le parole del sì. Il modello ha passato number_is_right=true nello
    stesso turno e il numero è risultato confermato senza che nessuno avesse
    detto niente. Non deve succedere più.
    """
    from preparation.trust import TRUSTED

    p = await _chiedi(mondo, RICHIESTA, counterparty="la mia ragazza",
                      number_is_right=True)
    assert p["number_confirmed"] is False
    p2 = await _chiedi(mondo, RICHIESTA, preparation_id=p["preparation_id"],
                       number_is_right=True)
    assert p2["number_confirmed"] is False
    assert mondo[TRUSTED].righe == []


@pytest.mark.parametrize("detto,via,atteso", [
    ("sì", False, True), ("è quello", False, True), ("chiamala", False, False),
    ("Chiama Giulia", True, False), ("chiamala", True, True),
    ("non è quello", False, False), ("no", True, False),
])
def test_what_counts_as_yes(detto, via, atteso):
    from telephone.caps import _the_person_said_yes

    assert _the_person_said_yes(detto, via_libera=via) is atteso


def test_a_duplicate_note_does_not_hide_the_tool_sentence():
    """Misurato in app: dopo un tentativo ripetuto la persona leggeva «Ok.»."""
    from conversation_engine.ai_core.loop import _the_tool_s_own_sentence

    oss = [
        {"kind": "tool", "name": "prepare_a_phone_call",
         "payload": {"say_this": "Chiamerò Giulia Test. Vuoi che la chiami?"}},
        {"kind": "system", "name": "duplicate_tool_call", "status": "info",
         "payload": {"failure_code": "DUPLICATE_SAME_TURN"}},
    ]
    assert _the_tool_s_own_sentence(oss) == "Chiamerò Giulia Test. Vuoi che la chiami?"


def test_the_phone_sentence_survives_a_later_tool_in_the_same_turn():
    from conversation_engine.ai_core.loop import _the_tool_s_own_sentence

    oss = [
        {"kind": "tool", "name": "prepare_a_phone_call",
         "payload": {"say_this": "Chiamerò Giulia Test. Vuoi che la chiami?"}},
        {"kind": "tool", "name": "situation_mutation", "payload": {"status": "success"}},
    ]
    assert _the_tool_s_own_sentence(oss) == "Chiamerò Giulia Test. Vuoi che la chiami?"
    assert _the_tool_s_own_sentence([]) == ""


def test_the_chat_shows_the_whole_sentence_of_the_phone_tool():
    """
    Misurato in app: il modello diceva solo «È questo il numero corretto?».
    La risposta mostrata porta la frase intera dello strumento.
    """
    from types import SimpleNamespace

    from conversation_engine.ai_core.loop import _compose_user_text

    d = SimpleNamespace(response_mode="ask", message_to_user="",
                        question="È questo il numero corretto?")
    frase = "Ho trovato Giulia Test, +393330000042 (Rubrica). È questo il numero corretto?"
    obs = [{"name": "prepare_a_phone_call", "payload": {"say_this": frase}}]
    assert _compose_user_text(d, obs) == frase
    #     E NESSUN ALTRO STRUMENTO CAMBIA COMPORTAMENTO.
    assert _compose_user_text(d, [{"name": "web_search", "payload": {"say_this": "x"}}]) \
        == "È questo il numero corretto?"


# ---------------------------------------------------------------------------
# V3.21.1a FINAL — attribuzione, apertura, esito in chat
# ---------------------------------------------------------------------------


def test_the_opening_to_a_loved_one_says_ciao():
    from telephone.introduction import Introduction

    riga = Introduction(assistant_for="Francesco", reason_summary="parlare con Asia",
                        asks_for="Asia").opening_line("2026-09-19T10:00:00+02:00")
    assert riga == "Ciao, sono l'assistente di Francesco. Parlo con Asia?"


def test_the_message_is_attributed_to_the_sender():
    """«la amo» è di Francesco: si dice «Francesco mi ha chiesto di dirti che ti ama»."""
    import inspect
    import telephone.live as live

    testo = inspect.getsource(live)
    assert "mi ha chiesto di dirti che ti " in testo
    assert "Mai in prima persona" in testo
    assert "Questo non posso deciderlo per" in testo


def _finita(**cambia):
    from telephone.models import Mandate, PhoneCall

    campi = dict(
        id="tel_x", owner_id=UID, to_number="+393330000042",
        calling_whom="Giulia Test", state="ended", how_it_ended="we_hung_up",
        provider_ref="ref_1", chat_session_id="ces_chat1",
        mandate=Mandate(why_calling="consegnare un messaggio a Giulia Test",
                        message="la amo", recipient="Giulia Test"),
        metrics={"outcome": {"status": "success", "delivery": "delivered",
                                     "recipient_reply": "digli che lo amo anch'io"}},
    )
    campi.update(cambia)
    return PhoneCall(**campi)


def test_the_chat_reads_a_delivery_like_a_person():
    from telephone.chat_report import what_to_tell_the_chat

    riga = what_to_tell_the_chat(_finita())
    assert riga == "Messaggio consegnato a Giulia. Ti ha risposto: «digli che lo amo anch'io»"
    assert what_to_tell_the_chat(_finita(state="dialling")) is None
    nessuno = what_to_tell_the_chat(_finita(state="failed", how_it_ended="no_answer",
                                            metrics={}))
    assert nessuno.startswith("Non sono riuscita a parlarle")
    #     «CHIAMATA FINITA» NON E' «CONSEGNATO».
    muta = what_to_tell_the_chat(_finita(metrics={}))
    assert "consegnato" not in muta.lower() or "non" in muta.lower()


@pytest.mark.asyncio
async def test_the_result_is_written_in_the_chat_once():
    from telephone.chat_report import calling_from, tell_the_chat

    db = FintoDb()
    chiamata = _finita()
    db.phone_calls.righe.append(chiamata.model_dump())
    db.conversation_sessions.righe.append({"id": "ces_chat1", "user_id": UID, "history": []})

    assert await calling_from(db, UID, "ces_chat1") is True
    assert await tell_the_chat(db, chiamata) is True
    assert await tell_the_chat(db, _finita()) is False
    storia = db.conversation_sessions.righe[0]["history"]
    assert len(storia) == 1
    assert storia[0]["role"] == "ora"
    assert storia[0]["text"].startswith("Messaggio consegnato a Giulia.")
    assert "tel_" not in storia[0]["text"]
    assert await calling_from(db, UID, "ces_chat1") is False


@pytest.mark.asyncio
async def test_the_chat_keeps_waiting_until_the_line_is_written():
    """Misurato sul vero: la chat ha smesso di aspettare prima che la riga arrivasse."""
    from telephone.chat_report import calling_from
    from telephone.service import TelephoneService

    db = FintoDb()
    db.phone_calls.righe.append(dict(_finita().model_dump(), told_the_chat=True,
                                     chat_told_at=""))
    #     IL POSTO PRESO NON E' ANCORA UNA RIGA SCRITTA.
    assert await calling_from(db, UID, "ces_chat1") is True

    db.phone_calls.righe[0]["chat_told_at"] = "2026-09-19T10:34:53+00:00"
    assert await calling_from(db, UID, "ces_chat1") is False
    #     UNA COPIA VECCHIA SALVATA DOPO NON RIAPRE L'ATTESA.
    await TelephoneService(db).mark(_finita(), "ended")
    assert db.phone_calls.righe[0]["chat_told_at"]
    assert await calling_from(db, UID, "ces_chat1") is False


def test_a_warm_goodbye_counts_as_a_goodbye():
    from telephone.live import FAREWELLS

    assert any(f in "certo, glielo riferisco. ciao!" for f in FAREWELLS)


def test_ad_asia_not_a_asia():
    from telephone.history import a_chi

    assert a_chi("Asia") == "ad Asia"
    assert a_chi("Giulia") == "a Giulia"
