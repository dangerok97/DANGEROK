"""
Quale dei due risponde al telefono.

    UN INTERRUTTORE È UN POSTO SOLO IN CUI SI DECIDE.

C'è un solo punto in tutto il runtime telefonico in cui si sceglie chi parla,
ed è questo. Il trasporto non lo sa, il carrier non lo sa, il servizio non lo
sa: tutti e tre chiamano `the_voice_for()` e ricevono qualcosa che ha `open`,
`hear`, `close` e `how_it_went`, esattamente come prima.

    E IL CLASSICO RESTA LA RISPOSTA GIUSTA FINCHÉ NON LO DICIAMO NOI.

Il valore di partenza è `classic`, e non per prudenza generica: il runtime a
missione sa condurre **una** trattativa alla volta, dentro un mandato scritto
prima. Una telefonata che non è una missione — una domanda aperta, una cosa
che nasce mentre si parla — è ancora roba per ORA intera.

    SE IL RUNTIME NUOVO NON PUÒ APRIRSI, NON SI PERDE LA TELEFONATA.

Manca la chiave, manca il modello, manca la missione: si torna al classico e
la persona dall'altra parte non si accorge di niente. Un flag non è un motivo
per far cadere una chiamata.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("ora.telephone.runtime")

CLASSIC = "classic"
GEMINI_LIVE = "gemini_live"


def which_runtime() -> str:
    """Quale runtime chiede la configurazione. Nel dubbio, il classico."""
    scelto = (os.environ.get("ORA_VOICE_RUNTIME") or CLASSIC).strip().lower()
    return scelto if scelto in (CLASSIC, GEMINI_LIVE) else CLASSIC


def voice_readiness_reason() -> str:
    """Readiness follows the same runtime selection as voice construction."""
    if which_runtime() == GEMINI_LIVE:
        from telephone.live import live_is_configured
        return live_is_configured()
    from telephone import deepgram
    return "" if deepgram.is_configured() else "nessuna voce che possa ascoltare e rispondere in linea"


def the_voice_for(
    db,
    *,
    owner_id: str,
    session_ref: str,
    send: Callable[[bytes], Awaitable[None]],
    clear_transport: Optional[Callable[[], Awaitable[None]]] = None,
    on_said: Optional[Callable[[str, str], Awaitable[None]]] = None,
    dossier=None,
    call=None,
    binding=None,
):
    """
    Chi condurrà questa telefonata.

    Torna sempre qualcosa: se il runtime a missione non è utilizzabile, torna
    il classico e scrive perché. Non solleva, non fa cadere la linea.
    """
    if which_runtime() == GEMINI_LIVE:
        motivo = _why_not_the_mission_one(call, dossier)
        if motivo:
            logger.info("runtime a missione non disponibile (%s): resta il classico", motivo)
        else:
            from telephone.live import MissionVoiceSession

            logger.info("questa telefonata la conduce il runtime a missione")
            return MissionVoiceSession(
                db,
                owner_id=owner_id,
                session_ref=session_ref,
                send=send,
                clear_transport=clear_transport,
                on_said=on_said,
                dossier=dossier,
                call=call,
                binding=binding,
            )

    from telephone.bridge import RealtimeVoiceSession

    return RealtimeVoiceSession(
        db,
        owner_id=owner_id,
        session_ref=session_ref,
        send=send,
        clear_transport=clear_transport,
        on_said=on_said,
        dossier=dossier,
    )


def _why_not_the_mission_one(call, dossier) -> str:
    """Che cosa manca per condurre questa telefonata a missione."""
    if call is None or dossier is None:
        return "non c'è un mandato da cui costruire la missione"
    try:
        from telephone.live import live_is_configured
    except Exception as e:  # pragma: no cover
        return f"non importabile: {type(e).__name__}"
    return live_is_configured()
