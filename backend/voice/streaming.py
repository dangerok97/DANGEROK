"""Incremental TTS of an already decided reply. No conversation or tools here."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import time
from contextlib import aclosing

from voice.providers import VOICE_DIRECTION, _error_status

logger = logging.getLogger("ora.voice.stream")
FIRST_AUDIO_S = 8.0
GAP_S = 8.0
_blocked: dict[tuple[str, str], float] = {}


async def _pcm(text: str, key: str, model: str, voice: str):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    stream = None
    try:
        stream = await client.aio.models.generate_content_stream(
            model=model,
            contents=f"{VOICE_DIRECTION}\n\nTesto:\n{text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice),
                )),
                http_options=types.HttpOptions(timeout=15000),
            ),
        )
        complete = False
        async for reply in stream:
            for candidate in reply.candidates or []:
                finish = str(getattr(candidate, "finish_reason", "") or "")
                if finish and not finish.endswith("STOP"):
                    raise RuntimeError("incomplete_speech")
                complete |= finish.endswith("STOP")
                for part in getattr(candidate.content, "parts", None) or []:
                    blob = getattr(part, "inline_data", None)
                    if not blob or not blob.data:
                        continue
                    mime = (blob.mime_type or "").lower()
                    rate = re.search(r"rate=(\d+)", mime)
                    if not mime.startswith("audio/pcm") and not mime.startswith("audio/l16"):
                        raise RuntimeError("unsupported_speech_format")
                    if rate and int(rate.group(1)) != 24000:
                        raise RuntimeError("unsupported_speech_rate")
                    raw = blob.data if isinstance(blob.data, bytes) else base64.b64decode(blob.data, validate=True)
                    if raw:
                        yield raw
        if not complete:
            raise RuntimeError("incomplete_speech")
    finally:
        if stream is not None:
            await stream.aclose()
        await client.aio.aclose()


async def speech_events(text: str):
    """First PCM is forwarded immediately; never restart a partially heard reply."""
    model = (os.environ.get("ORA_VOICE_STREAM_MODEL") or "gemini-3.1-flash-tts-preview").strip()
    voice = (os.environ.get("ORA_VOICE_NAME") or "Algieba").strip()
    start = time.monotonic()
    deadline = start + FIRST_AUDIO_S
    # The second account has been verified in production. A failed slot cools
    # independently of ordinary buffered synthesis and of other models.
    for name in ("GEMINI2_API_KEY", "GEMINI_API_KEY"):
        key = (os.environ.get(name) or "").strip()
        slot = (name, model)
        if not key or time.monotonic() < _blocked.get(slot, 0):
            continue
        heard = False
        total = 0
        frames = 0
        try:
            async with aclosing(_pcm(text, key, model, voice)) as source:
                async with asyncio.timeout(max(30, min(300, len(text) * .12))):
                    while True:
                        timeout = GAP_S if heard else max(.001, deadline - time.monotonic())
                        try:
                            raw = await asyncio.wait_for(anext(source), timeout=timeout)
                        except StopAsyncIteration:
                            break
                        if not heard:
                            heard = True
                            logger.info("first_audio_ms=%s model=%s voice=%s", int((time.monotonic()-start)*1000), model, voice)
                        total += len(raw)
                        frames += 1
                        yield {"type": "audio", "data": base64.b64encode(raw).decode("ascii"),
                               "sample_rate": 24000, "encoding": "pcm_s16le"}
            if not heard or total % 2:
                raise RuntimeError("incomplete_speech")
            _blocked.pop(slot, None)
            logger.info("complete_ms=%s frames=%s bytes=%s", int((time.monotonic()-start)*1000), frames, total)
            yield {"type": "done"}
            return
        except Exception as error:
            status = _error_status(error)
            logger.info("stream unavailable slot=%s status=%s kind=%s", name, status, type(error).__name__)
            _blocked[slot] = time.monotonic() + (300 if status in (400, 401, 402, 403, 404, 429) else 15)
            if heard:
                yield {"type": "error", "code": "speech_interrupted"}
                return
            if time.monotonic() >= deadline:
                break
    yield {"type": "error", "code": "speech_unavailable"}
