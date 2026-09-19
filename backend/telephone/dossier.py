"""
Quello che si prepara mentre il telefono squilla.

    FRA «SQUILLA» E «PRONTO» CI SONO SETTE SECONDI IN CUI NON SUCCEDE NIENTE.

Sono i sette secondi più preziosi della telefonata, perché sono gli unici in
cui nessuno sta aspettando. Quello che si fa qui non si paga più dopo:

- si apre il socket verso chi ascolta (misurato: 560 ms) e verso chi parla
  (787 ms). Aprirli al primo turno significherebbe un secondo e mezzo di
  silenzio in faccia a una persona che ha appena detto «pronto»;
- si legge la vita intorno: le parti aperte, gli impegni che stanno in piedi,
  il mandato di questa chiamata;
- si sveglia la catena dei fornitori. Misurato: il primo turno costa 5.479 ms
  e i successivi 1.510, perché il primo paga il tentativo su un account
  esaurito e lo mette in castigo per un minuto. Pagarlo mentre squilla vuol
  dire non pagarlo mai.

    IL PREFLIGHT È INFRASTRUTTURA, NON COGNIZIONE.

E qui va detto con precisione, perché è la riga sottile di tutto questo file.
Il risveglio della catena **non è una finta domanda dell'utente**: non passa
dal Conversation Engine, non crea una sessione, non scrive un messaggio, non
tocca la memoria, non attiva uno strumento, non consuma autorità e non produce
niente che qualcuno leggerà. È una richiesta tecnica a un fornitore per
scoprire chi risponde — l'equivalente di accendere un motore prima di partire.
Quello che ORA penserà lo penserà quando ci sarà qualcosa da pensare.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.telephone.dossier")

# Quanto si aspetta il risveglio prima di lasciar perdere. Se il telefono
# viene risposto prima, non importa: si continua senza.
WARMUP_TIMEOUT_S = 8


@dataclass
class TelephoneCallDossier:
    """
    Tutto quello che ORA sa prima di dire «pronto».

    Non contiene audio, non contiene chiavi, e non contiene niente che una
    persona non potrebbe sentirsi leggere.
    """

    owner_id: str
    call_id: str
    why_calling: str = ""
    calling_whom: str = ""
    on_behalf_of: str = ""
    opening_line: str = ""
    may_agree_to: List[str] = field(default_factory=list)
    must_bring_back: List[str] = field(default_factory=list)
    situations: List[Dict[str, Any]] = field(default_factory=list)
    already_busy: List[Dict[str, Any]] = field(default_factory=list)
    conversation_ref: str = ""
    # Che cosa ORA può fare durante questa telefonata, secondo l'autorità di
    # sempre. Non è una seconda autorità: è una fotografia di quella.
    authority: Dict[str, Any] = field(default_factory=dict)
    # Quanto è costato prepararsi, pezzo per pezzo.
    prepared_ms: Dict[str, Optional[int]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "why_calling": self.why_calling,
            "calling_whom": self.calling_whom,
            "on_behalf_of": self.on_behalf_of,
            "opening_line": self.opening_line,
            "may_agree_to": list(self.may_agree_to),
            "must_bring_back": list(self.must_bring_back),
            "situations": self.situations[:6],
            "already_busy": self.already_busy[:6],
            "authority": dict(self.authority),
            "prepared_ms": dict(self.prepared_ms),
        }


async def prepare_while_it_rings(db, call) -> TelephoneCallDossier:
    """
    Il fascicolo, mentre il telefono squilla. Nessuna cognizione.

    Ogni pezzo è protetto da sé: una telefonata non deve fallire perché una
    lettura della vita è andata storta, e quello che manca si nota — ORA saprà
    meno, non sbaglierà.
    """
    began = time.perf_counter()
    dossier = TelephoneCallDossier(
        owner_id=call.owner_id,
        call_id=call.id,
        why_calling=call.mandate.why_calling,
        calling_whom=call.calling_whom,
        may_agree_to=list(call.mandate.may_agree_to),
        must_bring_back=list(call.mandate.must_bring_back),
        conversation_ref=call.session_ref,
    )

    # --- chi è la persona per cui si telefona -----------------------------
    step = time.perf_counter()
    try:
        row = await db.users.find_one(
            {"user_id": call.owner_id}, {"_id": 0, "name": 1, "first_name": 1},
        )
        nome = str(
            (row or {}).get("first_name") or (row or {}).get("name") or ""
        ).strip()
        #     «FRANCESCO», NON «FRANCESCO» SCRITTO COME L'HA SCRITTO LUI.
        # Il nome del profilo era tutto minuscolo e la voce lo diceva nelle
        # trascrizioni così: un nome proprio ha la maiuscola.
        dossier.on_behalf_of = nome.title() if nome.islower() else nome
    except Exception as e:
        logger.info("nome non letto: %s", type(e).__name__)
    dossier.prepared_ms["who"] = int((time.perf_counter() - step) * 1000)

    from telephone.briefing import disclosure

    dossier.opening_line = disclosure(dossier.on_behalf_of)

    # --- la vita intorno, da dove sta già ---------------------------------
    step = time.perf_counter()
    try:
        from telephone.briefing import what_ora_brings

        brought = await what_ora_brings(
            db, call.owner_id,
            on_behalf_of=dossier.on_behalf_of,
            calling_whom=call.calling_whom,
            mandate=call.mandate,
        )
        dossier.situations = brought.get("what_this_is_about") or []
        dossier.already_busy = brought.get("already_busy") or []
    except Exception as e:
        logger.info("vita intorno non letta: %s", type(e).__name__)
    dossier.prepared_ms["life"] = int((time.perf_counter() - step) * 1000)

    # --- che cosa è permesso, secondo l'autorità di sempre ----------------
    step = time.perf_counter()
    try:
        from telephone.service import TelephoneService

        permission = await TelephoneService(db).may_i_call(call.owner_id)
        dossier.authority = {
            k: permission.get(k)
            for k in ("capability", "granted", "denied", "needs_explicit_yes")
        }
    except Exception as e:
        logger.info("autorità non letta: %s", type(e).__name__)
    dossier.prepared_ms["authority"] = int((time.perf_counter() - step) * 1000)

    dossier.prepared_ms["total"] = int((time.perf_counter() - began) * 1000)
    return dossier


async def wake_the_providers() -> Dict[str, Any]:
    """
    Sveglia la catena dei modelli. **Non è una domanda di nessuno.**

        QUESTO NON ENTRA NELLA CONVERSAZIONE. MAI.

    Non passa dall'orchestratore, non crea una sessione, non scrive un
    messaggio, non tocca memoria o autorità e non produce output. È una
    richiesta tecnica per scoprire chi risponde — e il suo unico effetto utile
    è mettere in castigo gli account esauriti *prima* che qualcuno stia
    aspettando una risposta.

    Misurato: senza, il primo turno costa 5.479 ms; con, 1.510.
    """
    began = time.perf_counter()
    out: Dict[str, Any] = {"woken": False}
    try:
        from llm.manager import get_manager

        manager = get_manager()
        await asyncio.wait_for(
            manager.chat(system="ok", user="ok", json_mode=False),
            timeout=WARMUP_TIMEOUT_S,
        )
        out["woken"] = True
    except Exception as e:
        # Un risveglio che non riesce non è un problema: vuol dire che il
        # primo turno pagherà quello che avrebbe pagato comunque.
        out["why_not"] = type(e).__name__
    try:
        from llm.manager import get_manager

        status = await get_manager().status()
        out["chain"] = status.get("fallback_chain")
    except Exception:
        pass
    out["took_ms"] = int((time.perf_counter() - began) * 1000)
    return out
