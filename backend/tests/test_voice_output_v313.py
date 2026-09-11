"""
Chi dà voce a una risposta, e cosa succede quando non può nessuno.

    LA CONVERSAZIONE NON DEVE CONOSCERE IL FORNITORE.
    SE NESSUNO PARLA, LA RISPOSTA SI LEGGE — E NON SI FERMA NIENTE.

La voce del browser legge l'italiano e si sente che lo sta leggendo. Va
benissimo come rete di sicurezza e non va bene come voce di ORA, quindi qui
c'è un contratto e non un fornitore: qualcuno sa trasformare delle parole in
byte di audio, e sa dire se adesso può.

Quello che si verifica non è come suona — quello si ascolta — ma le tre cose
che il codice possiede: che il contratto sia rispettato, che un fallimento
diventi silenzio e non un errore in faccia a qualcuno, e che il nome di chi
parla non arrivi da nessuna parte dove qualcuno potrebbe affezionarcisi.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

HERE = Path(_BACKEND)


def _run(coro):
    return _loop_harness.run(coro)


# ---------------------------------------------------------------------------
# Il contratto
# ---------------------------------------------------------------------------

def test_a_voice_is_a_contract_not_a_vendor():
    """
    §10: `speak`, `stop`, `is_available` — e chi chiama non sa altro.
    """
    from voice.providers import GeminiSpeech, OpenAISpeech, SpeechOutputProvider

    assert hasattr(SpeechOutputProvider, "speak")
    assert hasattr(SpeechOutputProvider, "is_available")
    for make in (GeminiSpeech, OpenAISpeech):
        provider = make()
        assert isinstance(provider.name, str) and provider.name
        assert callable(provider.is_available)
        assert callable(provider.speak)


def test_without_a_key_nobody_claims_to_be_able_to_speak(monkeypatch):
    """
    Dire di poter parlare e non riuscirci è peggio che non dirlo: chi chiama
    aspetta, non sente niente, e nel frattempo la voce di sistema è stata
    zitta per educazione.
    """
    for name in ("GEMINI_API_KEY", "GEMINI2_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    from voice.providers import GeminiSpeech, OpenAISpeech, a_voice

    assert GeminiSpeech().is_available() is False
    assert OpenAISpeech().is_available() is False
    assert a_voice() is None


def test_a_depleted_account_is_not_an_absent_provider(monkeypatch):
    """
    §2: la ragione per cui la voce di ORA non si è mai sentita.

    Il ragionamento del prodotto prova due account Google e passa al secondo
    quando il primo finisce il credito. La voce ne guardava uno solo — il
    primo, quello esaurito — e concludeva ogni volta che nessuno poteva
    parlare. Il secondo aveva credito e i modelli giusti, e non gli è mai
    stato chiesto niente.
    """
    from voice.providers import _GEMINI_KEYS, GeminiSpeech

    assert _GEMINI_KEYS == ("GEMINI_API_KEY", "GEMINI2_API_KEY")

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI2_API_KEY", "seconda")
    provider = GeminiSpeech()
    assert provider.is_available() is True
    assert [name for name, _ in provider.keys] == ["GEMINI2_API_KEY"]

    # E con tutte e due, si prova nell'ordine: prima la principale.
    monkeypatch.setenv("GEMINI_API_KEY", "prima")
    assert [name for name, _ in GeminiSpeech().keys] == [
        "GEMINI_API_KEY", "GEMINI2_API_KEY",
    ]


def test_when_nobody_can_speak_the_answer_is_silence_not_an_error(monkeypatch):
    """
    §11: `None` vuol dire «parla tu», e il browser sa cosa fare.

    Non un'eccezione e non un 500: una risposta che non si sente è una
    risposta che si legge, ed è la stessa. Quello che non deve succedere è
    che la conversazione si fermi.
    """
    # Tutte e tre: da quando la voce prova anche il secondo account Google,
    # toglierne una sola lascia qualcuno che puo' ancora parlare — e il test
    # misurava il silenzio mentre ORA cantava.
    for name in ("GEMINI_API_KEY", "GEMINI2_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    from voice.providers import say_it

    async def body():
        assert await say_it("Per domani non vedo impegni.") is None
        # E niente da dire non fa nemmeno provare.
        assert await say_it("   ") is None

    _run(body())


def test_a_provider_that_fails_hands_over_instead_of_raising(monkeypatch):
    """
    Un fornitore che va giù non porta giù la voce: si prova il prossimo, e se
    non c'è nessuno tocca al browser.
    """
    from voice import providers

    class Broken:
        name = "broken"

        def is_available(self):
            return True

        async def speak(self, text, *, language="it"):
            raise RuntimeError("giù")

    class Works:
        name = "works"

        def is_available(self):
            return True

        async def speak(self, text, *, language="it"):
            return providers.Spoken(
                audio=b"suono", mime="audio/wav", voice="v", provider=self.name,
            )

    async def body():
        monkeypatch.setattr(providers, "_ORDER", (Broken, Works))
        try:
            spoken = await providers.say_it("ciao")
        except Exception as e:  # pragma: no cover - è esattamente ciò che si vieta
            raise AssertionError(f"un fornitore rotto ha fermato la voce: {e}")
        assert spoken is not None and spoken.provider == "works"

    _run(body())


def test_raw_sound_becomes_a_file_a_browser_can_play():
    """
    Quarantaquattro byte davanti al suono, e diventa un file.

    Senza l'intestazione WAV il PCM di Gemini o non si sente affatto o si
    sente alla velocità sbagliata — e «la voce di ORA parla come un chipmunk»
    è il genere di difetto che nessun test sui byte prende, se i byte non li
    guarda nessuno.
    """
    from voice.providers import _as_wav

    made = _as_wav(b"\x00\x01" * 100, rate=24000)
    assert made[:4] == b"RIFF"
    assert made[8:12] == b"WAVE"
    assert made[12:16] == b"fmt "
    assert b"data" in made[:44]
    assert len(made) == 44 + 200
    # E il ritmo dichiarato è quello vero: 24000 Hz, mono, 16 bit.
    import struct

    channels, rate = struct.unpack("<HI", made[22:28])
    assert channels == 1 and rate == 24000


# ---------------------------------------------------------------------------
# Cosa non deve uscire da qui
# ---------------------------------------------------------------------------

def test_nothing_of_what_was_said_is_kept():
    """
    Quello che una persona chiede alla propria assistente non diventa un file
    su un disco perché l'ha chiesto a voce.
    """
    for name in ("providers.py", "router.py"):
        source = (HERE / "voice" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        running = ast.unparse(tree)
        for forbidden in ("open(", "insert_one", "update_one", "write(", "db["):
            assert forbidden not in running, (
                f"voice/{name}: la voce conserva qualcosa ({forbidden})"
            )


def test_the_endpoint_says_it_cannot_rather_than_failing():
    """
    §11: 204, non 500. Un errore qui diventerebbe un avviso sullo schermo per
    una cosa che si risolve da sola parlando con l'altra voce.
    """
    source = (HERE / "voice" / "router.py").read_text(encoding="utf-8")
    assert "status_code=204" in source
    assert "no-store" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        assert not (
            isinstance(node, ast.Raise)
        ), "l'endpoint della voce alza un'eccezione invece di cedere la parola"


def test_the_voice_decides_nothing_about_what_to_say():
    """
    Qui non si ragiona: il testo arriva già deciso da chi ragiona, e questo
    lo trasforma in suono. Se un giorno comparisse una chiamata al modello
    dentro la voce, sarebbe un secondo assistente che parla per primo.
    """
    source = (HERE / "voice" / "providers.py").read_text(encoding="utf-8")
    for forbidden in ("_ask_model", "get_manager", "ContextBroker", "search_a_life"):
        assert forbidden not in source, f"la voce ha cominciato a pensare: {forbidden}"


def test_the_words_are_not_rewritten_only_the_delivery():
    """
    §9: la stessa risposta, con una prosodia diversa. Le istruzioni al
    fornitore parlano di come dirla, mai di cosa dire.
    """
    source = (HERE / "voice" / "providers.py").read_text(encoding="utf-8")
    assert "Parla in italiano" in source
    assert "mai da call" in source
    # Il testo che si manda è quello che arriva, tagliato solo in lunghezza.
    assert "text[:MAX_CHARS]" in source
    for forbidden in ("summar", "riassum", "rewrite", "riscriv"):
        assert forbidden not in source.lower(), (
            f"la voce riscrive quello che deve dire: {forbidden}"
        )


def test_a_key_is_not_a_voice(monkeypatch):
    """
    §11: avere una chiave configurata non vuol dire saper parlare.

    Su un account senza credito residuo la differenza fra le due cose è un
    giro di rete a vuoto prima di ogni frase — in una conversazione parlata,
    un ritardo a ogni turno. Il primo no viene ricordato per qualche minuto, e
    poi si riprova: una carta si ricarica, e ORA non deve restare muta fino al
    riavvio.
    """
    from voice import providers

    monkeypatch.setenv("GEMINI_API_KEY", "finta")
    providers._last_failure = 0.0
    assert providers.a_voice() is not None, "con una chiave dovrebbe almeno provarci"

    providers._remember_failure()
    assert providers._recently_failed() is True
    assert providers.a_voice() is None, "continua a promettere una voce che non c'è"

    # Passato il tempo, ci riprova.
    providers._last_failure = 1.0
    assert providers._recently_failed() is False
    assert providers.a_voice() is not None
    providers._last_failure = 0.0


def test_the_logs_carry_a_type_never_a_word_of_what_was_said():
    """
    §4: diagnostica utile, senza chiavi, senza audio e senza trascrizioni.

    Un file di log è il posto dove le cose sopravvivono a chi le ha scritte.
    Qui dentro passa tutto quello che una persona chiede alla propria
    assistente, e passa anche la chiave che permette di chiederlo.

    Quello che si guarda sono gli argomenti, non la frase: «audio illeggibile»
    è un'etichetta e va benissimo, `logger.info(..., text)` no. E di
    un'eccezione si scrive il tipo e mai il messaggio, perché là dentro i
    fornitori mettono volentieri url, quote e dettagli di fatturazione.
    """
    import ast as _ast

    source = (HERE / "voice" / "providers.py").read_text(encoding="utf-8")
    tree = _ast.parse(source)
    seen = 0
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Call):
            continue
        if not _ast.unparse(node.func).startswith("logger."):
            continue
        seen += 1
        for argument in node.args[1:]:
            written = _ast.unparse(argument)
            # `name` è il nome della variabile d'ambiente — «GEMINI2_API_KEY» —
            # e serve a sapere quale account è finito. Il suo contenuto non
            # passa di qui e non deve passarci mai.
            assert written in ("type(e).__name__", "provider.name", "name"), (
                f"un log porta con sé qualcosa che non è un tipo: {written}"
            )
    assert seen, "nessun log da controllare: la guardia non guarda niente"
