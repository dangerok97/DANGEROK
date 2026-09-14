"""
Due cose che un modello non deve indovinare: che giorno è, e chi risponde.

    UNA COSA CHE IL CODICE SA NON SI FA DEDURRE A UN MODELLO.
    UNA RISERVA CHE NON RISPONDE MAI NON È UNA RISERVA.

La prima metà di questo file esiste per una misura: chiedendo sei volte «che
giorno della settimana è oggi?» con la stessa data nel payload, due modelli
su tre hanno risposto un giorno diverso quasi ogni volta, e sempre con
sicurezza. La seconda metà esiste per un'altra misura: il ripiego configurato
era un modello che va in 429 su ogni chiamata, perché il prompt di ORA non ci
sta nel suo tetto al minuto.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import pytest

from tests._loop_harness import run as _run  # noqa: E402


# ---------------------------------------------------------------------------
# Che giorno è
# ---------------------------------------------------------------------------

def test_the_weekday_is_computed_not_guessed():
    """
    §20: il giorno della settimana lo calcola il codice.

    Misurato con la stessa data nel payload: ministral-14b ha risposto
    martedì, martedì, lunedì; ministral-8b mercoledì, mercoledì, martedì;
    gemini2 domenica, che era l'unica giusta. Adesso non c'è niente da
    indovinare.
    """
    from day_names import weekday_name

    # Giorni noti, controllabili a mano su un calendario.
    assert weekday_name(date(2026, 9, 13)) == "Sunday"
    assert weekday_name(date(2026, 9, 14)) == "Monday"
    assert weekday_name(date(2000, 1, 1)) == "Saturday"
    assert weekday_name(date(2024, 2, 29)) == "Thursday"

    # E un momento preciso è il giorno in cui cade.
    assert weekday_name(datetime(2026, 9, 13, 23, 59, tzinfo=timezone.utc)) == "Sunday"


def test_the_weekday_does_not_follow_the_system_language():
    """
    §20: e non cambia se il backend parte in italiano.

        UN VALORE CHE DIPENDE DA UNA VARIABILE D'AMBIENTE NON È DETERMINISTICO.

    `strftime("%A")` segue il locale del processo: su un server avviato in
    italiano avrebbe cominciato a spedire «domenica» dove tutto il resto del
    payload dice «Sunday», e nessuno se ne sarebbe accorto finché un modello
    non avesse risposto in due lingue nella stessa frase.
    """
    import locale

    from day_names import weekday_name

    prima = locale.setlocale(locale.LC_TIME)
    try:
        for tentativo in ("it_IT.UTF-8", "it_IT", "Italian_Italy.1252"):
            try:
                locale.setlocale(locale.LC_TIME, tentativo)
                break
            except locale.Error:
                continue
        assert weekday_name(date(2026, 9, 13)) == "Sunday"
    finally:
        try:
            locale.setlocale(locale.LC_TIME, prima)
        except locale.Error:
            pass


def test_the_payload_carries_the_weekday_next_to_the_date():
    """
    §20: e arriva al modello, in alto, accanto alla data.

    In fondo non servirebbe: è la data di oggi, e si legge insieme a lei.
    """
    from conversation_engine.ai_core.prompt import build_user_payload
    from day_names import weekday_name

    payload = json.loads(
        build_user_payload(
            user_message="che giorno è oggi?",
            recent_turns=[], active_goal=None, context_facts=[],
            tools=[], observations=[],
        )
    )
    oggi = datetime.now(timezone.utc).date()
    assert payload["today"] == oggi.isoformat()
    assert payload["today_weekday"] == weekday_name(oggi)
    assert list(payload).index("today_weekday") <= 2


def test_the_agent_knows_it_too():
    """
    §20: vale per l'agente come per la conversazione.

    Un piano fatto per «giovedì» quando è domenica è sbagliato allo stesso
    modo in tutti e due i posti.
    """
    from day_names import weekday_name
    from agent.service import _what_day_it_is

    detto = _what_day_it_is()
    assert set(detto) == {"today", "today_weekday"}
    assert detto["today_weekday"] == weekday_name(
        date.fromisoformat(detto["today"])
    )


def test_today_is_today_where_the_person_is():
    """
    §28: «oggi» è oggi dove sta la persona, non dove sta il server.

        UN GIORNO SBAGLIATO NON SI VEDE FINCHÉ NON LO SENTI DIRE.

    Misurato alle 00:16 di lunedì 14 settembre: ORA rispondeva «oggi è
    domenica 13». Il payload portava la data UTC, e in Italia fra le ventidue
    e mezzanotte quella è la data di ieri. Nessun modello poteva accorgersene:
    gli avevamo dato la data sbagliata e lui l'aveva letta bene.
    """
    from conversation_engine.ai_core.prompt import build_user_payload
    from day_names import weekday_name

    # Un momento in cui il server e la persona non sono d'accordo: le 00:16
    # di lunedì a Roma sono le 22:16 di domenica a Greenwich.
    a_roma = date(2026, 9, 14)
    a_greenwich = date(2026, 9, 13)
    assert weekday_name(a_roma) == "Monday"
    assert weekday_name(a_greenwich) == "Sunday"

    payload = json.loads(
        build_user_payload(
            user_message="che giorno è oggi?",
            recent_turns=[], active_goal=None, context_facts=[],
            tools=[], observations=[], today_where_they_are=a_roma,
        )
    )
    assert payload["today"] == "2026-09-14"
    assert payload["today_weekday"] == "Monday"


def test_without_a_timezone_nothing_changed():
    """
    §28: e senza fuso si resta su UTC, com'era.

    Il parametro è facoltativo: i canali che non lo passano si comportano
    esattamente come ieri.
    """
    from conversation_engine.ai_core.prompt import build_user_payload
    from day_names import weekday_name

    payload = json.loads(
        build_user_payload(
            user_message="x", recent_turns=[], active_goal=None,
            context_facts=[], tools=[], observations=[],
        )
    )
    oggi_utc = datetime.now(timezone.utc).date()
    assert payload["today"] == oggi_utc.isoformat()
    assert payload["today_weekday"] == weekday_name(oggi_utc)


def test_an_unresolvable_timezone_does_not_break_the_turn():
    """
    §28: se il fuso non si risolve, il turno va avanti lo stesso.

    Sapere dove sta una persona è un vantaggio, non un requisito: senza, si
    torna a UTC invece di fallire.
    """
    async def body():
        from conversation_engine.ai_core.loop import _what_day_it_is_for_them

        class _RotturaSicura:
            users = None

            def __getattr__(self, _):
                raise RuntimeError("database non disponibile")

        # Database irraggiungibile: si torna a UTC invece di far fallire il turno.
        assert await _what_day_it_is_for_them(_RotturaSicura(), "u") is None

        # Nessun utente: il servizio ha un fuso di sistema dichiarato, e una
        # data ragionevole è meglio di nessuna data.
        senza_nessuno = await _what_day_it_is_for_them(None, "")
        assert senza_nessuno is not None
        assert abs((senza_nessuno - datetime.now(timezone.utc).date()).days) <= 1

    _run(body())


# ---------------------------------------------------------------------------
# Chi risponde quando il primario non può
# ---------------------------------------------------------------------------

def test_the_reserve_can_hold_the_prompt_it_will_receive():
    """
    §21: la riserva è scelta sul tetto, non sulla taglia.

        UNA RISERVA CHE NON RISPONDE MAI NON È UNA RISERVA.

    Il ripiego configurato era `mistral-small-latest`, che oggi risolve a
    `mistral-small-2603`: ventimila token al minuto. Il prompt di ORA ne porta
    18.654 — una chiamata sola satura il minuto, e la seconda prende 429.
    Misurato: 429 su ogni tentativo, anche su una richiesta da quattro token.
    """
    from llm.providers.mistral_provider import MistralProvider, _DEFAULT_MODEL

    assert _DEFAULT_MODEL == "ministral-8b-2512"
    for vietato in ("mistral-small", "ministral-14b", "mistral-large"):
        assert vietato not in _DEFAULT_MODEL

    # E senza variabile d'ambiente si ricade su quello, non su un modello che
    # il prompt non ci sta dentro.
    prima = os.environ.pop("MISTRAL_MODEL", None)
    try:
        assert MistralProvider().model_name() == "ministral-8b-2512"
    finally:
        if prima is not None:
            os.environ["MISTRAL_MODEL"] = prima


def test_mistral_is_a_reserve_and_never_the_first_asked():
    """
    §21: resta dietro, dove deve stare.

    La riserva serve quando il percorso primario non può. Se finisse davanti,
    ogni turno di ORA cambierebbe modello senza che nessuno l'abbia deciso.
    """
    from llm.manager import DEFAULT_PRIORITY

    assert "mistral" in DEFAULT_PRIORITY
    assert DEFAULT_PRIORITY.index("mistral") > DEFAULT_PRIORITY.index("gemini")
    assert DEFAULT_PRIORITY.index("mistral") > DEFAULT_PRIORITY.index("gemini2")


def test_when_the_primary_cannot_answer_the_reserve_does():
    """
    §21: il primario cade, e qualcuno risponde lo stesso.

    Non si simula la rete: si sostituiscono i fornitori con due finti, uno che
    va in quota e uno che risponde, e si guarda che la catena arrivi fino in
    fondo — con il JSON intatto, il modo giusto e lo strumento giusto.
    """
    async def body():
        from llm.errors import LLMQuotaError
        from llm.manager import ProviderManager
        from llm.base import LLMResult

        deciso = {
            "response_mode": "tool",
            "user_intent_summary": "vuole sapere gli impegni della settimana",
            "tool_call": {
                "capability": "get_calendar_events",
                "operation": "run",
                "arguments": {"when": "next_week"},
                "reason": "serve il calendario",
            },
            "message_to_user": None,
        }

        class _Esaurito:
            name = "gemini"
            chiamato = 0

            def is_configured(self):
                return True

            def model_name(self):
                return "finto"

            async def chat(self, **k):
                _Esaurito.chiamato += 1
                raise LLMQuotaError("quota")

        class _Riserva:
            name = "mistral"
            chiamato = 0

            def is_configured(self):
                return True

            def model_name(self):
                return "ministral-8b-2512"

            async def chat(self, **k):
                _Riserva.chiamato += 1
                assert k.get("json_mode") is True, "il modo JSON si è perso"
                return LLMResult(
                    text=json.dumps(deciso),
                    provider="mistral",
                    model="ministral-8b-2512",
                    usage={},
                )

        mgr = ProviderManager()
        mgr._providers = {"gemini": _Esaurito(), "mistral": _Riserva()}
        mgr.ordered_names = lambda pref=None: ["gemini", "mistral"]

        out = await mgr.chat(system="s", user="u", json_mode=True)

        assert _Esaurito.chiamato == 1, "il primario non è stato nemmeno provato"
        assert _Riserva.chiamato == 1, "la riserva non è stata raggiunta"
        assert out.provider == "mistral"
        assert out.model == "ministral-8b-2512"

        # Quello che torna è ancora una decisione di ORA, non testo libero.
        d = json.loads(out.text)
        assert d["response_mode"] == "tool"
        assert d["tool_call"]["capability"] == "get_calendar_events"

    _run(body())


def test_the_reserve_is_skipped_while_the_primary_works():
    """
    §21: e finché il primario risponde, la riserva non si tocca.

    Una riserva chiamata quando non serve è un secondo modello che decide al
    posto del primo, a caso.
    """
    async def body():
        from llm.manager import ProviderManager
        from llm.base import LLMResult

        class _Buono:
            name = "gemini"

            def is_configured(self):
                return True

            def model_name(self):
                return "finto"

            async def chat(self, **k):
                return LLMResult(
                    text='{"response_mode": "answer", "message_to_user": "ok"}',
                    provider="gemini", model="finto", usage={},
                )

        class _Riserva:
            name = "mistral"
            chiamato = 0

            def is_configured(self):
                return True

            def model_name(self):
                return "ministral-8b-2512"

            async def chat(self, **k):
                _Riserva.chiamato += 1
                raise AssertionError("la riserva è stata chiamata senza motivo")

        mgr = ProviderManager()
        mgr._providers = {"gemini": _Buono(), "mistral": _Riserva()}
        mgr.ordered_names = lambda pref=None: ["gemini", "mistral"]

        out = await mgr.chat(system="s", user="u", json_mode=True)
        assert out.provider == "gemini"
        assert _Riserva.chiamato == 0

    _run(body())
