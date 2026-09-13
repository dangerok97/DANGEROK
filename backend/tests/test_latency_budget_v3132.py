"""
Chi aspetta ad alta voce aspetta diversamente.

    IL BUDGET STRETTO VALE PER IL PRIMO CAVALLO, NON PER L'ULTIMO.

Venticinque secondi sono la protezione giusta contro un provider morto, e
un'eternità per qualcuno che ha appena finito di parlare al telefono e sente
silenzio. Dieci secondi sono 3,3 volte il peggior turno sano mai misurato sul
primario, e servono a una cosa sola: decidere in fretta di **cambiare
provider**.

    NON A DECIDERE QUANTO VALE UNA RISPOSTA.

Per questo il budget non tocca mai l'ultimo provider disponibile: abbandonare
l'unico rimasto non è una protezione, è silenzio — che è il difetto peggiore
che questo sprint abbia trovato. E per questo niente di tutto ciò vive dentro
`telephone/`: cambia l'attesa, non il cervello.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from tests._loop_harness import run as _run  # noqa: E402

HERE = Path(_BACKEND)

DECISIONE = json.dumps({"response_mode": "answer", "message_to_user": "ok"})


class _Finto:
    def __init__(self, name, *, ritardo=0.0, testo=DECISIONE):
        self.name = name
        self.ritardo = ritardo
        self.testo = testo
        self.chiamate = 0
        self.visto = []

    def is_configured(self):
        return True

    def model_name(self):
        return self.name

    async def chat(self, **k):
        from llm.base import LLMResult

        self.chiamate += 1
        self.visto.append(dict(k))
        if self.ritardo:
            await asyncio.sleep(self.ritardo)
        return LLMResult(text=self.testo, provider=self.name, model=self.name,
                         usage={})


def _manager(**provider):
    from llm.manager import ProviderManager, _RuntimeState

    mgr = ProviderManager()
    mgr._providers = dict(provider)
    ordine = list(provider)
    mgr.ordered_names = lambda pref=None: ordine
    mgr._runtime = {n: _RuntimeState() for n in ordine}
    return mgr


async def _quanto(coro):
    inizio = asyncio.get_running_loop().time()
    out = await coro
    return out, asyncio.get_running_loop().time() - inizio


# ---------------------------------------------------------------------------
# 1-4: quando il budget si applica, e quando no
# ---------------------------------------------------------------------------

def test_the_voice_budget_is_ten_seconds_and_comes_from_where_the_words_entered():
    """
    §25.1: al telefono e a voce si aspetta dieci secondi, altrove no.

    È una tabella, non un ramo: la provenienza governa l'attesa, come già
    governa la forma. Non c'è nessuna logica del telefono qui dentro.
    """
    from conversation_engine.ai_core.loop import _how_long_we_wait
    from llm.manager import VOICE_FIRST_ATTEMPT_S

    assert VOICE_FIRST_ATTEMPT_S == 10.0
    assert _how_long_we_wait("phone") == 10.0
    assert _how_long_we_wait("voice") == 10.0
    for altrove in ("text", "home", "documents", "proactive", "memoria", ""):
        assert _how_long_we_wait(altrove) is None, (
            f"{altrove} non dovrebbe avere un budget stretto"
        )


def test_a_stuck_primary_is_left_after_the_budget_not_after_the_global_deadline():
    """
    §25.2: il primario si impianta, e dopo il budget si passa oltre.

    Misurato prima: un turno vero è arrivato a 34 secondi. Con i venticinque
    globali si sarebbe aspettato venticinque.
    """
    async def body():
        a = _Finto("gemini", ritardo=30)
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        out, passato = await _quanto(mgr.chat(
            system="s", user="u", json_mode=True, latency_budget_s=1.0,
        ))

        assert out.provider == "gemini2"
        assert passato < 3.0, f"ha aspettato {passato:.1f}s invece del budget"
        assert mgr._runtime["gemini"].failure_kind == "timeout"

    _run(body())


def test_a_primary_that_answers_inside_the_budget_is_not_interrupted():
    """
    §25.3: chi risponde dentro il budget non viene toccato.

    Il budget serve a riconoscere chi non finisce, non a punire chi ci mette
    un po' — e i turni che ci mettono un po' sono proprio quelli che contano.
    """
    async def body():
        a = _Finto("gemini", ritardo=0.6)
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        out = await mgr.chat(
            system="s", user="u", json_mode=True, latency_budget_s=2.0,
        )

        assert out.provider == "gemini", "tagliato un provider che stava finendo"
        assert b.chiamate == 0
        assert mgr._runtime["gemini"].state == "healthy"

    _run(body())


def test_the_last_provider_standing_keeps_the_whole_deadline():
    """
    §25.4: l'ultimo cavallo non si stanca.

        ABBANDONARE L'UNICO RIMASTO NON È PROTEZIONE, È SILENZIO.

    Se non c'è nessun altro a cui passare, il budget stretto non si applica:
    si aspetta la protezione globale. Al telefono una risposta lenta è molto
    meglio di nessuna risposta.
    """
    async def body():
        os.environ["LLM_ATTEMPT_DEADLINE_S"] = "8"
        try:
            solo = _Finto("gemini", ritardo=1.5)
            mgr = _manager(gemini=solo)

            out, passato = await _quanto(mgr.chat(
                system="s", user="u", json_mode=True, latency_budget_s=0.3,
            ))

            assert out.provider == "gemini", "l'unico provider è stato tagliato"
            assert passato >= 1.4, "non lo ha aspettato davvero"
            assert mgr._runtime["gemini"].state == "healthy"
        finally:
            os.environ.pop("LLM_ATTEMPT_DEADLINE_S", None)

    _run(body())


def test_the_budget_does_not_apply_to_the_one_we_fell_back_to():
    """
    §25.4bis: e nemmeno al secondo, che è l'ultimo rimasto.

    Il primo viene abbandonato in fretta perché c'è dove andare; il secondo,
    che non ha nessuno dietro, viene aspettato per intero.
    """
    async def body():
        a = _Finto("gemini", ritardo=5)
        b = _Finto("gemini2", ritardo=1.2)
        mgr = _manager(gemini=a, gemini2=b)

        out, passato = await _quanto(mgr.chat(
            system="s", user="u", json_mode=True, latency_budget_s=0.4,
        ))

        assert out.provider == "gemini2", "anche la riserva è stata tagliata"
        # ~0,4 s buttati sul primo più 1,2 s di risposta vera dal secondo.
        assert 1.2 <= passato < 3.0, f"tempi inattesi: {passato:.2f}s"

    _run(body())


# ---------------------------------------------------------------------------
# 5-6: quello che non deve cambiare
# ---------------------------------------------------------------------------

def test_same_ora_whoever_answers_and_whatever_the_budget():
    """
    §25.5: SAME ORA — il budget non tocca una parola di quello che si chiede.

    Stesso prompt di sistema, stesso payload, stesso modo JSON, a chiunque
    risponda e con qualunque attesa. Se un giorno il budget cambiasse anche
    solo una virgola, ORA sarebbe due ORA.
    """
    async def body():
        a = _Finto("gemini", ritardo=5)
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        await mgr.chat(
            system="il sistema di ORA", user="il payload di ORA",
            json_mode=True, latency_budget_s=0.3,
        )

        assert a.visto and b.visto
        assert a.visto[0]["system"] == b.visto[0]["system"] == "il sistema di ORA"
        assert a.visto[0]["user"] == b.visto[0]["user"] == "il payload di ORA"
        assert a.visto[0]["json_mode"] is b.visto[0]["json_mode"] is True

        # E lo stesso vale senza budget: l'insieme di quello che arriva non
        # dipende da quanto siamo disposti ad aspettare.
        senza = _Finto("gemini2")
        mgr2 = _manager(gemini2=senza)
        await mgr2.chat(system="il sistema di ORA", user="il payload di ORA",
                        json_mode=True)
        assert set(senza.visto[0]) == set(b.visto[0])

    _run(body())


def test_without_a_budget_nothing_changed_at_all():
    """
    §25.6: nessun budget passato, comportamento identico a ieri.

    Il parametro è facoltativo e il valore di riposo è `None`: dieci siti di
    chiamata su undici non sono stati toccati, e devono comportarsi come
    prima.
    """
    async def body():
        os.environ["LLM_ATTEMPT_DEADLINE_S"] = "6"
        try:
            a = _Finto("gemini", ritardo=2.0)
            b = _Finto("gemini2")
            mgr = _manager(gemini=a, gemini2=b)

            # Due secondi: sopra un ipotetico budget stretto, sotto la
            # protezione globale. Senza budget, risponde il primario.
            out = await mgr.chat(system="s", user="u", json_mode=True)
            assert out.provider == "gemini"
            assert b.chiamate == 0
        finally:
            os.environ.pop("LLM_ATTEMPT_DEADLINE_S", None)

    _run(body())


# ---------------------------------------------------------------------------
# 7-9: niente appeso, niente tetto di turno, niente nel telefono
# ---------------------------------------------------------------------------

def test_twenty_turns_with_a_tight_budget_leave_nothing_hanging():
    """
    §25.7: venti turni, e nessun compito sopravvissuto.

    `wait_for` annulla e **aspetta che l'annullamento sia completato**: gli
    adattatori sono async nativi, quindi la richiesta HTTP viene davvero
    abortita. Un thread annullato continuerebbe a girare, e il budget sarebbe
    una bugia.
    """
    async def body():
        a = _Finto("gemini", ritardo=30)
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        prima = len(asyncio.all_tasks())
        for _ in range(20):
            out = await mgr.chat(
                system="s", user="u", json_mode=True, latency_budget_s=0.3,
            )
            assert out.provider == "gemini2"
        await asyncio.sleep(0)
        dopo = len(asyncio.all_tasks())

        assert dopo <= prima + 1, f"compiti appesi: {prima} → {dopo}"
        # E il budget si è pagato una volta sola: dal secondo turno il
        # primario era già in panchina.
        assert a.chiamate == 1, (
            f"il primario impantanato è stato richiamato {a.chiamate} volte"
        )

    _run(body())


def test_a_two_step_turn_pays_the_budget_at_each_step_and_has_no_turn_cap():
    """
    §25.8: il budget vale per tentativo, e non esiste un tetto di turno.

        UN TETTO DI TURNO SAREBBE UNA DECISIONE DI ORA, NON DELL'INFRASTRUTTURA.

    Un turno che chiama uno strumento e poi risponde fa due giri di modello.
    Ciascuno ha il suo budget; nessuno somma i due e decide di non rispondere
    a metà strada — interrompere un ragionamento è una cosa che decide ORA.
    """
    async def body():
        a = _Finto("gemini", ritardo=5)
        b = _Finto("gemini2")
        mgr = _manager(gemini=a, gemini2=b)

        # Due passi, come un turno che prima chiede il calendario e poi
        # risponde: ciascuno paga il suo budget sul primario impantanato.
        for passo in (1, 2):
            # Il primario rientra in campo fra un passo e l'altro, come
            # succederebbe a cooldown scaduto.
            mgr._runtime["gemini"].cooldown_until = 0.0
            out, passato = await _quanto(mgr.chat(
                system="s", user=f"payload del passo {passo}", json_mode=True,
                latency_budget_s=0.4,
            ))
            assert out.provider == "gemini2"
            assert passato < 2.0, f"passo {passo}: {passato:.2f}s"

        assert a.chiamate == 2, "il budget non è stato applicato a ogni passo"
        assert b.chiamate == 2
        assert [v["user"] for v in b.visto] == [
            "payload del passo 1", "payload del passo 2",
        ], "i due passi non sono arrivati interi"

    _run(body())


def test_no_latency_policy_lives_inside_the_telephone():
    """
    §25.9: il telefono non sa niente di budget, ed è il punto.

    Se un giorno una durata comparisse lì dentro, sarebbe nato un percorso
    cognitivo del telefono — la cosa che tutto questo sprint esiste per non
    fare. La politica sta in due posti soli: la costante nel manager e la
    tabella nel giro della conversazione.
    """
    import ast as _ast

    for path in sorted((HERE / "telephone").glob("*.py")):
        testo = path.read_text(encoding="utf-8")
        # Solo il codice: i commenti possono benissimo nominarli.
        albero = _ast.parse(testo)
        for nodo in _ast.walk(albero):
            if isinstance(nodo, _ast.Expr) and isinstance(nodo.value, _ast.Constant):
                nodo.value.value = ""
        codice = _ast.unparse(albero)
        for vietato in (
            "latency_budget", "VOICE_FIRST_ATTEMPT", "_how_long_we_wait",
            "LLM_ATTEMPT_DEADLINE",
        ):
            assert vietato not in codice, (
                f"{path.name} conosce la politica di latenza: {vietato}"
            )

    # E la tabella vive in un punto solo.
    loop = (HERE / "conversation_engine" / "ai_core" / "loop.py").read_text(
        encoding="utf-8",
    )
    assert loop.count("def _how_long_we_wait") == 1
