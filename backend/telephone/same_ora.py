"""
Il punto in cui una telefonata diventa una conversazione di ORA.

    VOICE IS NOT A SEPARATE ASSISTANT.
    STESSA SESSIONE, STESSO MODELLO DELLA VITA, STESSO AGENTE.

Questo file è piccolo apposta, e la sua piccolezza è il punto. Quando lo
Sprint 3.2 farà diventare parole il parlato di una telefonata, quelle parole
non entreranno in un motore nuovo: entreranno **esattamente dove entra una
frase scritta nell'app**, cioè in `AICoreOrchestrator`. Stessa sessione,
stesso Personal Life Model, stessa autorità, stessa Life Search, stessi
strumenti, stessa disciplina epistemica.

C'è una tentazione ovvia da evitare, ed è la ragione per cui questo adattatore
esiste già adesso, vuoto di logica: costruire «la conversazione telefonica»
come una cosa a parte, perché al telefono i turni sono più corti e il tempo
stringe. Sarebbe un secondo ORA, con una seconda memoria di quello che è
stato detto e una seconda idea di cosa può fare — e due ORA sono zero ORA.

La differenza fra telefono e app non è cognitiva. È di trasporto, e il
trasporto sta in `carrier.py`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.telephone.same_ora")


async def a_turn_of_conversation(
    db,
    *,
    owner_id: str,
    session_id: str,
    words: str,
    origin: str = "phone",
) -> Optional[Dict[str, Any]]:
    """
    Una frase detta al telefono, dentro la conversazione di sempre.

    È l'equivalente esatto, lato server, di quello che l'app fa quando una
    persona scrive o detta: non c'è nessun ramo che guardi da dove arrivano le
    parole, e se un giorno ne comparisse uno, ci sarebbe un test a dirlo.

    `origin` viaggia come provenienza — serve a ORA per sapere che sta
    parlando in una telefonata e non in una chat, il che cambia come si dicono
    le cose, non cosa si può fare. Esattamente come `voice` nello Sprint 1.

    Torna `None` quando non c'è niente da dire: una frase vuota non è un
    turno, e inventarne uno riempirebbe la conversazione di silenzi.
    """
    said = (words or "").strip()
    if not said or not owner_id:
        return None

    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    orchestrator = AICoreOrchestrator(db)
    try:
        if session_id:
            return await orchestrator.message(
                user_id=owner_id, session_id=session_id, text=said,
            )
        return await orchestrator.start(
            user_id=owner_id, text=said, origin=origin, entry_point=origin,
        )
    except Exception as e:
        # Un turno che non riesce non è un turno inventato: si dice che non
        # c'è risposta, e chi sta al telefono se ne accorge e lo dice.
        logger.info("turno telefonico non riuscito: %s", type(e).__name__)
        return None
