"""
Dare una voce a una risposta, senza sapere di chi sia la voce.

    LA CONVERSAZIONE NON DEVE CONOSCERE IL FORNITORE.

La voce di sistema del browser sa leggere l'italiano e si sente che lo sta
leggendo: scandisce, non respira, e mette l'accento dove capita. Va benissimo
come rete di sicurezza — c'e' sempre, non costa niente, funziona offline — e
non va bene come voce di ORA.

Quindi qui c'e' un contratto e non un fornitore: `SpeechOutputProvider` dice
soltanto che qualcuno sa trasformare delle parole in dei byte di audio e sa
dire se in questo momento puo' farlo. Sotto ci sono le implementazioni che
questo progetto ha gia' le chiavi per usare, e sopra non c'e' niente che sappia
come si chiamano. Il giorno che se ne aggiunge una migliore si aggiunge qui,
e nessuna schermata cambia.

Nessuna delle implementazioni tiene niente: l'audio nasce, viene mandato e
sparisce. Quello che una persona ha chiesto alla propria assistente non
diventa un file su un disco perche' l'ha chiesto a voce.
"""

from __future__ import annotations

import base64
import logging
import os
import struct
from dataclasses import dataclass
from typing import Optional, Protocol

logger = logging.getLogger("ora.voice")

# Quanto puo' essere lunga una cosa detta ad alta voce. Non e' una regola di
# stile: e' quanto audio si e' disposti a far generare e scaricare in una
# volta. Le risposte di ORA sono corte per altre ragioni.
MAX_CHARS = 1200

# Quanto si aspetta prima di rinunciare e lasciare la parola alla voce di
# sistema. Una voce piu' bella che arriva in ritardo e' una voce peggiore.
TIMEOUT_S = float(os.environ.get("ORA_VOICE_TIMEOUT_S", "12"))


@dataclass
class Spoken:
    """Delle parole, diventate suono."""

    audio: bytes
    mime: str
    voice: str
    provider: str


class SpeechOutputProvider(Protocol):
    """Chi sa dire una frase ad alta voce."""

    name: str

    def is_available(self) -> bool:
        """Se adesso, con quello che c'e' configurato, puo' parlare."""

    async def speak(self, text: str, *, language: str = "it") -> Optional[Spoken]:
        """Le parole come suono, o niente se non ce l'ha fatta."""


# ---------------------------------------------------------------------------


# Le chiavi di Gemini, nell'ordine in cui si provano.
#
#     UN ACCOUNT ESAURITO NON E' UN FORNITORE ASSENTE.
#
# Questa e' la ragione per cui la voce di ORA non si e' mai sentita. Il
# ragionamento del prodotto prova due account Google e passa al secondo quando
# il primo finisce il credito; la voce ne guardava uno solo — il primo, quello
# esaurito — e concludeva ogni volta che nessuno poteva parlare. Il secondo
# account aveva credito e i modelli giusti, e non gli e' mai stato chiesto
# niente. Due righe di catena, e mesi di voce robotica.
_GEMINI_KEYS = ("GEMINI_API_KEY", "GEMINI2_API_KEY")


class GeminiSpeech:
    """
    La voce di Gemini.

    Torna PCM grezzo a 24 kHz: nessun browser sa cosa farsene, quindi gli si
    mette davanti l'intestazione di un WAV. Sono quarantaquattro byte e sono
    la differenza fra un file che si sente e un rumore.
    """

    name = "gemini"

    def __init__(self) -> None:
        self.keys = [
            (name, (os.environ.get(name) or "").strip())
            for name in _GEMINI_KEYS
            if (os.environ.get(name) or "").strip()
        ]
        self.model = (
            os.environ.get("ORA_VOICE_MODEL") or "gemini-2.5-flash-preview-tts"
        ).strip()
        # La voce di ORA e' Kore, e non l'ha scelta il codice.
        #
        #     UNA VOCE SI SCEGLIE ASCOLTANDOLA.
        #
        # Il valore precedente era stato messo qui leggendo la descrizione che
        # il fornitore pubblica accanto a ogni voce — «warm», «gentle»,
        # «soft» — che e' un modo educato di tirare a indovinare. Sei
        # campioni della stessa frase italiana sono stati generati e
        # ascoltati, e la scelta e' quella. Resta in una riga di
        # configurazione perche' un giorno qualcuno potrebbe riascoltarle.
        self.voice = (os.environ.get("ORA_VOICE_NAME") or "Kore").strip()

    def is_available(self) -> bool:
        return bool(self.keys)

    async def speak(self, text: str, *, language: str = "it") -> Optional[Spoken]:
        if not self.is_available():
            return None
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return None

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice,
                    ),
                ),
            ),
            http_options=types.HttpOptions(timeout=int(TIMEOUT_S * 1000)),
        )

        for name, key in self.keys:
            client = genai.Client(api_key=key)
            try:
                answer = await client.aio.models.generate_content(
                    model=self.model, contents=text[:MAX_CHARS], config=config,
                )
            except Exception as e:
                # Il nome della variabile d'ambiente, non il suo contenuto:
                # serve a sapere quale account e' finito, e non e' un segreto.
                logger.info("voce gemini via %s: %s", name, type(e).__name__)
                continue
            raw = _first_audio(answer)
            if raw:
                return Spoken(
                    audio=_as_wav(raw), mime="audio/wav",
                    voice=self.voice, provider=self.name,
                )
        return None


class OpenAISpeech:
    """
    La voce di OpenAI. Torna un mp3, che ogni browser sa suonare da solo.
    """

    name = "openai"

    def __init__(self) -> None:
        self.key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        self.model = (os.environ.get("ORA_VOICE_MODEL_OPENAI") or "gpt-4o-mini-tts").strip()
        self.voice = (os.environ.get("ORA_VOICE_NAME_OPENAI") or "alloy").strip()

    def is_available(self) -> bool:
        return bool(self.key)

    async def speak(self, text: str, *, language: str = "it") -> Optional[Spoken]:
        if not self.is_available():
            return None
        try:
            import httpx
        except ImportError:
            return None
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                answer = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {self.key}"},
                    json={
                        "model": self.model,
                        "voice": self.voice,
                        "input": text[:MAX_CHARS],
                        "response_format": "mp3",
                        # Come deve suonare, non cosa deve dire. Il testo non
                        # si tocca: e' parola per parola quello che si legge.
                        "instructions": (
                            "Parla in italiano, con la calma di qualcuno che "
                            "conosce bene la persona a cui sta parlando. Tono "
                            "adulto e tranquillo, mai teatrale e mai da call "
                            "center. Rispetta la punteggiatura e prenditi le "
                            "pause dove ci sono."
                        ),
                    },
                )
                answer.raise_for_status()
                return Spoken(
                    audio=answer.content, mime="audio/mpeg",
                    voice=self.voice, provider=self.name,
                )
        except Exception as e:
            logger.info("voce openai non disponibile: %s", type(e).__name__)
            return None


# ---------------------------------------------------------------------------


def _first_audio(answer) -> bytes:
    """I byte dell'audio dentro una risposta, comunque siano confezionati."""
    try:
        for candidate in getattr(answer, "candidates", None) or []:
            for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
                blob = getattr(part, "inline_data", None)
                data = getattr(blob, "data", None)
                if not data:
                    continue
                return data if isinstance(data, bytes) else base64.b64decode(data)
    except Exception as e:
        logger.info("audio illeggibile: %s", type(e).__name__)
    return b""


def _as_wav(pcm: bytes, *, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    """
    Quarantaquattro byte davanti al suono, e diventa un file.

    Il PCM grezzo non dice quanto veloce vada letto ne' quanti canali abbia:
    senza questa intestazione un browser non lo suona affatto, o lo suona a
    una velocita' che non e' quella.
    """
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack(
        "<IHHIIHH", 16, 1, channels, rate, rate * channels * width,
        channels * width, width * 8,
    )
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


# L'ordine in cui si prova. Il primo che risponde parla; se non risponde
# nessuno, parla il browser — che e' sempre li' e non ha bisogno di niente.
_ORDER = (GeminiSpeech, OpenAISpeech)

# Quanto si ricorda un tentativo andato male prima di riprovarci.
#
#     AVERE UNA CHIAVE NON E' SAPER PARLARE.
#
# Una chiave configurata dice che qualcuno *potrebbe* parlare, e su un
# account senza credito residuo la differenza fra le due cose e' un giro di
# rete a vuoto prima di ogni frase — in una conversazione parlata, un ritardo
# a ogni turno. Quindi il primo no viene ricordato per qualche minuto: chi
# chiede se c'e' una voce migliore riceve la verita' di adesso, non quella
# del file di configurazione. Pochi minuti e non di piu': una carta si
# ricarica, e ORA non deve restare muta fino al riavvio.
_QUIET_FOR_S = float(os.environ.get("ORA_VOICE_RETRY_AFTER_S", "300"))
_last_failure: float = 0.0


def _recently_failed() -> bool:
    import time

    return bool(_last_failure) and (time.time() - _last_failure) < _QUIET_FOR_S


def _remember_failure() -> None:
    import time

    global _last_failure
    _last_failure = time.time()


def a_voice() -> Optional[SpeechOutputProvider]:
    """Chi puo' parlare adesso, o nessuno."""
    if _recently_failed():
        return None
    for make in _ORDER:
        provider = make()
        if provider.is_available():
            return provider
    return None


async def say_it(text: str, *, language: str = "it") -> Optional[Spoken]:
    """
    La frase, detta da chi puo' dirla.

    Torna `None` quando nessuno ci riesce, e quel `None` non e' un errore da
    mostrare: e' il segnale che tocca alla voce del browser. Una risposta che
    si legge c'e' comunque, ed e' la stessa.
    """
    words = (text or "").strip()
    if not words:
        return None
    global _last_failure
    for make in _ORDER:
        provider = make()
        try:
            if not provider.is_available():
                continue
            spoken = await provider.speak(words, language=language)
        except Exception as e:
            # Un fornitore che cade non porta giu' la voce: si prova il
            # prossimo, e se non ce n'e' nessuno tocca al browser. Le
            # implementazioni qui dentro si proteggono gia' da sole; questo
            # vale per la prossima, che non e' ancora stata scritta.
            logger.info("voce %s caduta: %s", provider.name, type(e).__name__)
            continue
        if spoken and spoken.audio:
            _last_failure = 0.0
            return spoken
    _remember_failure()
    return None
