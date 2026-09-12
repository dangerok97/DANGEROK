"""
Telefonare, come capacità della conversazione.

    PREPARARE NON È CHIAMARE.

Quello che ORA può fare da dentro una conversazione è *preparare* una
telefonata: scrivere a chi, perché, e cosa potrebbe accettare. Comporre il
numero è un'altra cosa e passa da un'altra porta, dove c'è una persona che
legge quello che ORA sta per dire e dice di sì.

La separazione non è burocrazia. Una capacità che compone il numero da sola
significa che una frase detta male in chat — o una riga di contesto letta
storta — fa squillare il telefono di un estraneo. Il sì non è un attrito da
ridurre: è il punto.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from conversation_engine.ai_core.models import Observation

logger = logging.getLogger("ora.telephone.caps")


def _fail(code: str, detail: str = "") -> Observation:
    return Observation(
        kind="tool", name="prepare_a_phone_call", status="failed",
        payload={
            "capability": "prepare_a_phone_call",
            "status": "error",
            "error": code,
            "detail": detail[:200],
        },
    )


async def prepare_a_phone_call(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    """
    Scrive la telefonata che ORA farebbe, e non la fa.

    Torna a chi ragiona una cosa da raccontare alla persona: chiamerei questo
    numero, direi questa frase per prima, potrei accettare queste cose, e
    tutto il resto te lo riporterei indietro. Poi si aspetta.
    """
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return _fail("NOT_CONFIGURED")

    from telephone.models import Mandate
    from telephone.service import TelephoneService

    service = TelephoneService(db)
    permission = await service.may_i_call(uid)

    #     DIRE CHE NON SI PUÒ È UNA RISPOSTA; TACERLO NO.
    #
    # Se non c'è un operatore, chi ragiona deve saperlo adesso — e dirlo — non
    # scoprirlo dopo aver chiesto alla persona il permesso per una cosa che
    # non sarebbe comunque successa.
    if not permission["provider_ready"]:
        return Observation(
            kind="tool", name="prepare_a_phone_call", status="partial",
            payload={
                "capability": "prepare_a_phone_call",
                "status": "unavailable",
                "reason": permission["why_not"] or "non c'è modo di telefonare",
                "say_it_like_this": (
                    "Di' che al telefono non ci puoi ancora andare, e perché, "
                    "in una riga. Non proporre di riprovare più tardi: non è "
                    "una cosa che passa da sola."
                ),
            },
        )

    if permission["denied"]:
        return Observation(
            kind="tool", name="prepare_a_phone_call", status="partial",
            payload={
                "capability": "prepare_a_phone_call",
                "status": "refused_before",
                "reason": "questa persona aveva già detto di no alle telefonate",
            },
        )

    try:
        mandate = Mandate(
            why_calling=str(arguments.get("why_calling") or "").strip(),
            may_agree_to=[
                str(x)[:160] for x in (arguments.get("may_agree_to") or [])
            ][:8],
            must_bring_back=[
                str(x)[:160] for x in (arguments.get("must_bring_back") or [])
            ][:8],
            minutes=int(arguments.get("minutes") or 5),
        )
    except Exception as e:
        return _fail("INVALID_INPUT", f"mandato non valido: {type(e).__name__}")

    call = await service.prepare(
        uid,
        to_number=str(arguments.get("to_number") or ""),
        calling_whom=str(arguments.get("calling_whom") or ""),
        mandate=mandate,
        session_ref=str(runtime.get("session_id") or ""),
    )
    if not call.to_number:
        return _fail(
            "INVALID_INPUT",
            "numero non italiano: questo pilota chiama solo numeri nazionali",
        )

    from telephone.briefing import disclosure

    return Observation(
        kind="tool", name="prepare_a_phone_call", status="ok",
        payload={
            "capability": "prepare_a_phone_call",
            "status": "prepared",
            "call_id": call.id,
            "to_number": call.to_number,
            "calling_whom": call.calling_whom,
            "first_words": disclosure(str(runtime.get("user_name") or "")),
            "why_calling": mandate.why_calling,
            "may_agree_to": mandate.may_agree_to,
            "must_bring_back": mandate.must_bring_back,
            # Perché non è ancora successo niente, e cosa manca.
            "nothing_has_happened_yet": True,
            "how_to_say_it": (
                "Racconta che cosa faresti: chi chiami, cosa dici per prima "
                "cosa, che cosa puoi accettare e che cosa gli riporteresti "
                "indietro. Poi chiedi se vuole che chiami — e aspetta. Non "
                "dire che hai chiamato, non dire che stai chiamando, e non "
                "promettere un esito: non è ancora squillato niente."
            ),
        },
    )
