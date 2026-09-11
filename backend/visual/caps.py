"""
Guardare, quando è il ragionamento a decidere che serve.

    PARSED TEXT FIRST. VISION WHEN NEEDED.

Non una pipeline che analizza ogni immagine che entra, ma uno strumento che
chi ragiona usa quando la domanda lo richiede: «che cos'è questo?», «riguarda
la casa?», «quanto devo pagare?». Una foto caricata e mai nominata non costa
niente a nessuno.

Quello che torna sono osservazioni — «ho visto» — e mai fatti. Il resto della
conversazione le tratta come tratta qualunque altra evidenza: se ne parla, si
può dire da dove vengono, e per diventare qualcosa di piu' devono passare
dalla governance come tutto il resto.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from conversation_engine.ai_core.models import Observation

logger = logging.getLogger("ora.visual.caps")


def _fail(name: str, code: str, detail: str = "") -> Observation:
    return Observation(
        kind="tool", name=name, status="failed",
        payload={"status": "failed", "failure_kind": code, "detail": detail[:200]},
    )


async def look_at_image(
    arguments: Dict[str, Any], runtime: Dict[str, Any]
) -> Observation:
    """
    Guarda un'immagine di questa conversazione e di' cosa ci si vede.

    Senza `file_id` guarda l'ultima immagine mostrata: «che cos'è questo?»
    arriva quasi sempre subito dopo averla mandata, e far nominare alla
    persona un identificativo per parlare della cosa che ha appena
    condiviso sarebbe un modo di farle fare il lavoro del programma.
    """
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    sid = str(runtime.get("session_id") or "")
    if not uid or db is None:
        return _fail("look_at_image", "NOT_CONFIGURED")

    from conversation_engine.ai_core.files.service import ContextFileService
    from visual.seeing import is_a_page, is_an_image
    from visual.service import VisualService

    files = ContextFileService(db)
    file_id = str(arguments.get("file_id") or "").strip()

    chosen = None
    if file_id:
        chosen = await files.get(uid, file_id)
        if not chosen:
            return _fail("look_at_image", "not_found")
    else:
        #     «QUESTO» È L'ULTIMA COSA CHE HA MANDATO.
        #
        # La lista della sessione tiene la più recente in testa — il caricamento
        # fa `insert(0, …)` — e leggerla al contrario significava guardare la
        # prima immagine della conversazione invece dell'ultima. Alla prova, a
        # una domanda su una schermata appena mandata, ORA ha risposto
        # descrivendo un disegno di due turni prima: tutto giusto, tranne
        # l'immagine.
        for candidate in (await files.list_session_files(uid, sid) or []):
            mime = getattr(candidate, "mime_type", "") or (
                candidate.get("mime_type") if isinstance(candidate, dict) else ""
            )
            # Anche una scansione: una pagina fotografata e chiusa in un PDF
            # e' la cosa che questa persona ha mostrato, tanto quanto una foto.
            # Se il testo c'e' davvero dentro, e' il servizio a dirlo e a non
            # guardarla.
            if is_an_image(str(mime)) or is_a_page(str(mime)):
                chosen = candidate
                break
        if chosen is None:
            return Observation(
                kind="tool", name="look_at_image", status="partial",
                payload={
                    "status": "needs_information",
                    "reason": (
                        "In questa conversazione non c'è nessuna immagine né "
                        "pagina da guardare. Dillo così, e non chiedere di "
                        "rimandarla se non è mai arrivata."
                    ),
                },
            )

    document_ref = str(
        getattr(chosen, "document_id", "")
        or (chosen.get("document_id") if isinstance(chosen, dict) else "")
    )
    if not document_ref:
        return _fail("look_at_image", "not_found")

    seen = await VisualService(db).look(
        uid,
        document_ref=document_ref,
        session_ref=sid,
        what_they_asked=str(arguments.get("what_i_want_to_know") or "")[:400],
    )

    if not seen.get("ok"):
        why = str(seen.get("reason") or "")
        if why == "not_an_image":
            return Observation(
                kind="tool", name="look_at_image", status="partial",
                payload={
                    "status": "wrong_kind",
                    "reason": (
                        "Questo non è un'immagine. Se ha del testo, leggilo con "
                        "get_file_content invece di guardarlo."
                    ),
                },
            )
        if why in ("cannot_look", "unavailable"):
            #     NON AVER GUARDATO NON È AVER GUARDATO E NON AVER CAPITO.
            # La differenza conta: la seconda è una cosa da dire sulla foto,
            # la prima è una cosa da dire su di sé.
            return Observation(
                kind="tool", name="look_at_image", status="partial",
                payload={
                    "status": "could_not_look",
                    "reason": (
                        "Adesso non riesco a guardare le immagini. Dillo "
                        "com'è — non dire che non si capisce, perché non l'hai "
                        "vista — e chiedi di raccontartelo, se serve."
                    ),
                },
            )
        return _fail("look_at_image", why or "failed")

    observation = seen.get("observation") or {}
    return Observation(
        kind="tool",
        name="look_at_image",
        status="ok",
        payload={
            "status": "success",
            "event": "IMAGE_SEEN",
            # Già vista: la stessa immagine non si guarda due volte, e questo
            # dice a chi ragiona che non è arrivato niente di nuovo.
            "already_seen": bool(seen.get("already_seen")),
            "what_i_saw": observation,
            "grounding": "VISUAL_OBSERVATION",
            # E qui la riga che tiene tutto insieme: quello che si vede è
            # evidenza. Diventare conoscenza è un'altra cosa, e passa da dove
            # passa sempre.
            "memory_eligible": False,
            "reason": (
                "Questa è un'osservazione: quello che hai visto, non quello che "
                "sai. Parlane come di una cosa vista — «vedo che…», «sembra…» — "
                "di' quello che non sei riuscito a leggere, e non trattarla "
                "come un fatto stabilito della sua vita."
            ),
        },
        provenance=[document_ref],
    )
