"""
Chi ha appena detto di no non si richiama, e chi non risponde non si aspetta.

    UN PROVIDER ESAURITO PER OGGI NON TORNA FRA SESSANTA SECONDI.
    UN PROVIDER LENTISSIMO È PEGGIO DI UN PROVIDER MORTO.

Due cose sole, e nessuna delle due tocca il cervello di ORA: cambia **quando**
si chiede a chi, non che cosa si chiede né cosa si decide.

La prima metà di questo file esiste per una misura: con un cooldown fisso di
sessanta secondi, un account in quota veniva richiamato una volta al minuto per
tutta la giornata, e ogni richiamo costava fra 698 e 2.900 millisecondi a una
persona che stava aspettando. La seconda metà per un'altra: un provider lento
si teneva il turno fino a sessanta secondi, e nessuno interveniva perché non
c'era nessun errore da registrare.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from tests._loop_harness import run as _run  # noqa: E402

DECISIONE = json.dumps({
    "response_mode": "answer",
    "message_to_user": "Oggi è domenica 13 settembre 2026.",
})


class _Finto:
    """Un provider che fa quello che gli si dice, e conta quante volte."""

    def __init__(self, name, *, alza=None, ritardo=0.0, testo=DECISIONE):
        self.name = name
        self.alza = alza
        self.ritardo = ritardo
        self.testo = testo
        self.chiamate = 0

    def is_configured(self):
        return True

    def model_name(self):
        return f"{self.name}-finto"

    async def chat(self, **k):
        from llm.base import LLMResult

        self.chiamate += 1
        if self.ritardo:
            await asyncio.sleep(self.ritardo)
        if self.alza is not None:
            colpa = self.alza() if callable(self.alza) else self.alza
            # Una fabbrica di colpe può decidere che stavolta non ce ne sono.
            if colpa is not None:
                raise colpa
        return LLMResult(
            text=self.testo, provider=self.name, model=self.model_name(),
            usage={},
        )


def _manager(**provider):
    """Un manager vero, con dentro solo i provider di questa prova."""
    from llm.manager import ProviderManager

    mgr = ProviderManager()
    mgr._providers = dict(provider)
    ordine = list(provider)
    mgr.ordered_names = lambda pref=None: ordine
    from llm.manager import _RuntimeState

    mgr._runtime = {n: _RuntimeState() for n in ordine}
    return mgr


# ---------------------------------------------------------------------------
# A — il cooldown che impara
# ---------------------------------------------------------------------------

def test_a_429_on_the_first_provider_is_answered_by_the_second():
    """§22.1: il primario dice 429, e qualcuno risponde lo stesso."""
    async def body():
        from llm.errors import LLMRateLimitError

        a = _Finto("gemini", alza=lambda: LLMRateLimitError("rate_limit"))
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        out = await mgr.chat(system="s", user="u", json_mode=True)

        assert out.provider == "gemini2"
        assert a.chiamate == 1 and b.chiamate == 1
        assert json.loads(out.text)["response_mode"] == "answer"

    _run(body())


def test_a_the_next_turn_does_not_call_the_one_that_just_refused():
    """
    §22.2: e al turno dopo non lo si disturba nemmeno.

        È QUI CHE STANNO I SECONDI.

    Non è una questione di eleganza: ogni richiamo a un provider che non può
    rispondere è tempo che una persona passa in silenzio al telefono.
    """
    async def body():
        from llm.errors import LLMQuotaError

        a = _Finto("gemini", alza=lambda: LLMQuotaError("quota"))
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        for _ in range(4):
            out = await mgr.chat(system="s", user="u", json_mode=True)
            assert out.provider == "gemini2"

        assert a.chiamate == 1, (
            f"il provider in quota è stato richiamato {a.chiamate} volte"
        )
        assert b.chiamate == 4

    _run(body())


def test_a_the_wait_grows_while_the_reason_stays_the_same():
    """
    §22.3: il secondo no vale più del primo.

    Sessanta secondi, poi quattro minuti, poi sedici. E si ferma a due ore:
    una panchina infinita sarebbe un provider spento a mano.
    """
    async def body():
        from llm.errors import LLMQuotaError
        from llm.manager import COOLDOWN_SECONDS, ESCALATION

        a = _Finto("gemini", alza=lambda: LLMQuotaError("quota"))
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        base = COOLDOWN_SECONDS["quota"]
        fattore, tetto = ESCALATION["quota"]
        adesso = [1000.0]
        mgr._clock = lambda: adesso[0]

        attese = []
        for _ in range(5):
            await mgr.chat(system="s", user="u", json_mode=True)
            attese.append(mgr._runtime["gemini"].cooldown_until - adesso[0])
            # Il tempo passa quanto basta perché la panchina finisca.
            adesso[0] += attese[-1] + 1

        assert attese[0] == base
        assert attese[1] == base * fattore
        assert attese[2] == base * fattore ** 2
        assert attese[-1] <= tetto
        assert attese == sorted(attese), "l'attesa non è cresciuta"
        assert a.chiamate == 5, "ogni scadenza dà un'altra possibilità"

    _run(body())


def test_a_a_different_refusal_starts_the_count_again():
    """
    §22.4: chi dice un'altra cosa viene creduto da capo.

    Un provider che era in quota e adesso va in timeout sta descrivendo un
    guasto diverso, e non merita la panchina accumulata dall'altro.
    """
    async def body():
        from llm.errors import LLMNetworkError, LLMQuotaError

        colpe = [LLMQuotaError("quota"), LLMQuotaError("quota"),
                 LLMNetworkError("network")]
        a = _Finto("gemini", alza=lambda: colpe.pop(0))
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        adesso = [1000.0]
        mgr._clock = lambda: adesso[0]

        for _ in range(3):
            await mgr.chat(system="s", user="u", json_mode=True)
            adesso[0] += mgr._runtime["gemini"].cooldown_until - adesso[0] + 1

        stato = mgr._runtime["gemini"]
        assert stato.failure_kind == "network"
        assert stato.consecutive_failures == 1, "il conto non è ripartito"

    _run(body())


def test_a_when_the_cooldown_expires_it_gets_another_chance():
    """§22.5: scaduta la panchina, si rientra in campo."""
    async def body():
        from llm.errors import LLMRateLimitError

        colpa = [LLMRateLimitError("rate_limit")]
        a = _Finto("gemini", alza=lambda: colpa.pop(0) if colpa else None)
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        adesso = [1000.0]
        mgr._clock = lambda: adesso[0]

        primo = await mgr.chat(system="s", user="u", json_mode=True)
        assert primo.provider == "gemini2"

        # Ancora in panchina: non lo si chiama.
        dentro = await mgr.chat(system="s", user="u", json_mode=True)
        assert dentro.provider == "gemini2"
        assert a.chiamate == 1

        # Passa il tempo.
        adesso[0] += 3600
        dopo = await mgr.chat(system="s", user="u", json_mode=True)
        assert dopo.provider == "gemini", "non è mai rientrato"
        assert a.chiamate == 2

    _run(body())


def test_a_our_own_mistake_does_not_bench_a_healthy_provider():
    """
    §22.6: un errore nostro non manda in panchina nessuno.

        PUNIRE L'INNOCENTE È UN MODO DI PERDERE UN PROVIDER BUONO.

    Un guasto del nostro codice — un payload malformato, un attributo che non
    esiste — non dice niente sulla salute di chi l'ha ricevuto. Si alza subito,
    senza failover, così nessuno maschera un nostro difetto rispondendo al
    posto suo, e senza cooldown, così il provider resta disponibile.
    """
    async def body():
        from llm.errors import LLMInternalError

        a = _Finto("gemini", alza=lambda: TypeError("payload sbagliato"))
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        try:
            await mgr.chat(system="s", user="u", json_mode=True)
            raise AssertionError("un errore nostro è passato per un failover")
        except LLMInternalError:
            pass

        assert b.chiamate == 0, "un altro provider ha mascherato il nostro errore"
        stato = mgr._runtime["gemini"]
        assert stato.cooldown_until == 0.0, "messo in panchina per colpa nostra"
        assert stato.consecutive_failures == 0

    _run(body())


def test_a_an_empty_answer_never_escalates():
    """
    §22.7: e una risposta vuota non fa crescere niente.

    Può dipendere da quello che abbiamo mandato noi: l'attesa resta quella
    breve di sempre, anche al quinto tentativo.
    """
    async def body():
        from llm.errors import LLMInvalidResponseError
        from llm.manager import COOLDOWN_SECONDS

        a = _Finto("gemini", alza=lambda: LLMInvalidResponseError("empty"))
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        adesso = [1000.0]
        mgr._clock = lambda: adesso[0]
        attese = []
        for _ in range(4):
            await mgr.chat(system="s", user="u", json_mode=True)
            attese.append(mgr._runtime["gemini"].cooldown_until - adesso[0])
            adesso[0] += attese[-1] + 1

        assert set(attese) == {COOLDOWN_SECONDS["invalid_response"]}

    _run(body())


# ---------------------------------------------------------------------------
# B — la scadenza di un tentativo
# ---------------------------------------------------------------------------

def test_b_a_provider_that_does_not_answer_is_left_behind():
    """
    §23.1: chi non finisce entro la scadenza non si aspetta oltre.

    Misurato: un turno vero è arrivato a 34 secondi, e con il tetto
    dell'adattatore a 60 nessuno sarebbe intervenuto prima di un minuto.
    """
    async def body():
        os.environ["LLM_ATTEMPT_DEADLINE_S"] = "5"
        try:
            a = _Finto("gemini", ritardo=30)
            b = _Finto("gemini2")
            mgr = _manager(gemini=a, gemini2=b)

            comincia = asyncio.get_running_loop().time()
            out = await mgr.chat(system="s", user="u", json_mode=True)
            passato = asyncio.get_running_loop().time() - comincia

            assert out.provider == "gemini2"
            assert passato < 12, f"ha aspettato {passato:.1f}s"
            stato = mgr._runtime["gemini"]
            assert stato.failure_kind == "timeout"
            assert stato.cooldown_until > 0, "il lento non è andato in panchina"
        finally:
            os.environ.pop("LLM_ATTEMPT_DEADLINE_S", None)

    _run(body())


def test_b_a_provider_that_is_simply_slow_is_not_interrupted():
    """
    §23.2: non si interrompe chi sta finendo.

        LA SCADENZA È PER CHI NON FINISCE, NON PER CHI CI METTE UN PO'.

    Un caso complesso può costare qualche secondo in più, e tagliarlo
    significherebbe far fallire proprio i turni che contano.
    """
    async def body():
        os.environ["LLM_ATTEMPT_DEADLINE_S"] = "5"
        try:
            a = _Finto("gemini", ritardo=1.0)
            b = _Finto("gemini2")
            mgr = _manager(gemini=a, gemini2=b)

            out = await mgr.chat(system="s", user="u", json_mode=True)
            assert out.provider == "gemini", "tagliato un provider che stava finendo"
            assert b.chiamate == 0
        finally:
            os.environ.pop("LLM_ATTEMPT_DEADLINE_S", None)

    _run(body())


def test_b_the_deadline_never_gets_short_enough_to_break_a_real_turn():
    """
    §23.3: e non si può configurare una scadenza che rompe i turni sani.

    Un turno sano costa 2,4 secondi sul primario e 5 sulla riserva. Una
    scadenza sotto i cinque secondi non sarebbe una protezione: sarebbe un
    guasto che ci diamo da soli.
    """
    from llm.manager import DEFAULT_ATTEMPT_DEADLINE_S, _attempt_deadline

    prima = os.environ.get("LLM_ATTEMPT_DEADLINE_S")
    try:
        for assurdo in ("0", "0.5", "-3", "non un numero"):
            os.environ["LLM_ATTEMPT_DEADLINE_S"] = assurdo
            assert _attempt_deadline() == DEFAULT_ATTEMPT_DEADLINE_S

        os.environ["LLM_ATTEMPT_DEADLINE_S"] = "40"
        assert _attempt_deadline() == 40.0

        os.environ.pop("LLM_ATTEMPT_DEADLINE_S", None)
        assert _attempt_deadline() == DEFAULT_ATTEMPT_DEADLINE_S
    finally:
        os.environ.pop("LLM_ATTEMPT_DEADLINE_S", None)
        if prima is not None:
            os.environ["LLM_ATTEMPT_DEADLINE_S"] = prima


def test_b_nothing_is_left_hanging_after_many_turns():
    """
    §23.4: e dopo venti turni non resta niente appeso.

        UN COMPITO CHE SOPRAVVIVE A UN TURNO È UNA PERDITA LENTA.

    `wait_for` annulla il lavoro e aspetta che l'annullamento sia completato:
    i gestori di contesto dentro l'adattatore si chiudono, e la connessione con
    loro. Se un giorno smettesse di essere vero, venti turni lo mostrerebbero.
    """
    async def body():
        os.environ["LLM_ATTEMPT_DEADLINE_S"] = "5"
        try:
            a = _Finto("gemini", ritardo=30)
            b = _Finto("gemini2")
            mgr = _manager(gemini=a, gemini2=b)

            prima = len(asyncio.all_tasks())
            for _ in range(20):
                out = await mgr.chat(system="s", user="u", json_mode=True)
                assert out.provider == "gemini2"
            await asyncio.sleep(0)
            dopo = len(asyncio.all_tasks())

            assert dopo <= prima + 1, (
                f"compiti appesi: {prima} prima, {dopo} dopo"
            )
            # E il lento è stato chiamato una volta sola: la panchina ha retto
            # per tutti e venti i turni.
            assert a.chiamate == 1
        finally:
            os.environ.pop("LLM_ATTEMPT_DEADLINE_S", None)

    _run(body())


# ---------------------------------------------------------------------------
# Quello che non deve cambiare
# ---------------------------------------------------------------------------

def test_a_healthy_chain_behaves_exactly_as_before():
    """
    §24: con tutto sano, non è cambiato niente.

    Il primario risponde al primo colpo, nessun altro viene disturbato, e
    quello che torna è la decisione di ORA intatta.
    """
    async def body():
        a = _Finto("gemini")
        b = _Finto("gemini2")
        c = _Finto("mistral")
        mgr = _manager(gemini=a, gemini2=b, mistral=c)

        for _ in range(3):
            out = await mgr.chat(system="s", user="u", json_mode=True)
            assert out.provider == "gemini"

        assert (a.chiamate, b.chiamate, c.chiamate) == (3, 0, 0)
        assert mgr._runtime["gemini"].state == "healthy"
        assert mgr._runtime["gemini"].consecutive_failures == 0
        assert json.loads(out.text)["message_to_user"].startswith("Oggi")

    _run(body())


def test_the_same_words_reach_whoever_answers():
    """
    §24: SAME ORA — a chiunque risponda si chiede la stessa cosa.

    Il failover cambia **chi** risponde, mai cosa gli è stato chiesto: stesso
    prompt di sistema, stesso payload, stesso modo JSON. Se un giorno un
    provider ricevesse qualcosa di diverso, ORA sarebbe due ORA.
    """
    async def body():
        from llm.errors import LLMQuotaError

        visto = {}

        class _Registra(_Finto):
            async def chat(self, **k):
                visto[self.name] = dict(k)
                return await super().chat(**k)

        a = _Registra("gemini", alza=lambda: LLMQuotaError("quota"))
        b = _Registra("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        await mgr.chat(
            system="il sistema di ORA", user="il payload di ORA", json_mode=True,
        )

        assert visto["gemini"]["system"] == visto["gemini2"]["system"]
        assert visto["gemini"]["user"] == visto["gemini2"]["user"]
        assert visto["gemini"]["json_mode"] == visto["gemini2"]["json_mode"] is True

    _run(body())


def test_the_order_of_the_chain_did_not_change():
    """§24: e l'ordine dei provider è quello di sempre."""
    from llm.manager import DEFAULT_PRIORITY

    assert DEFAULT_PRIORITY == (
        "gemini", "gemini2", "groq", "mistral", "openai", "ollama", "emergent",
    )
