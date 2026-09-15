"""
Chi sa ricevere l'esito di una telefonata, dominio per dominio.

    OTTO DOVERI, E CHI NE SALTA UNO NON E' UN ADATTATORE.

Il calendario li ha imparati uno alla volta, ognuno dopo un difetto vero: il
legame prima della chiamata perché cercare l'evento dopo sposta quello
sbagliato; l'autorità perché un mandato in prosa non si può verificare; la
riconciliazione perché un processo che muore fra due scritture lascia un
forse; il conflitto perché un calendario sbagliato è peggio di uno vecchio.

Un secondo dominio non deve riscoprirli. Questo file li scrive una volta:

    1. `remembers`   com'era l'oggetto quando si è deciso di telefonare
    2. `authority`   che cosa si può accettare, in forma verificabile
    3. `look`        dov'è l'oggetto adesso, nello stato canonico
    4. `translate`   dall'esito confermato ai campi veri — puro, senza rete
    5. `apply`       la scrittura, e solo dopo tutti i controlli
    6. `reconcile`   che cosa è successo, per un'applicazione rimasta a metà
    7. `conflict`    l'oggetto è ancora quello di allora?
    8. `says`        come si racconta a una persona che non c'era

Il legame in sé — quale telefonata, quale oggetto, prima di comporre il numero
— non è un dovere del dominio: sta in `binding.py`, uguale per tutti. Quello
che il dominio ci mette è `remembers`: quali campi dell'oggetto vanno
fotografati adesso, perché è su quelli che dopo si dirà se stiamo ancora
parlando della stessa cosa. Sono diversi per ognuno — un appuntamento è il suo
orario, un impegno è il suo stato — e nessun altro li sa.

Idempotenza e presentazione non sono doveri del dominio: la prima sta nella
chiave del record, la seconda nel livello che racconta. Un adattatore che se
le rifacesse in casa sarebbe un secondo motore.

    E NIENTE `if` SPARSI NEL RUNTIME.

Chi applica non sa che cosa sia un calendario. Chiede al registro chi sa fare
`(dominio, operazione)` e riceve qualcuno che risponde a quel contratto, o
niente — e «niente» è una risposta: un dominio senza adattatore non scrive.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class DomainAdapter(Protocol):
    """
    Il contratto che ogni dominio rispetta per intero.

    Non è una classe da ereditare: è la forma che un modulo deve avere. Chi
    applica non conosce nessun dominio per nome, e questo è l'unico motivo per
    cui aggiungerne uno non tocca il motore.
    """

    DOMAIN: str
    OPERATIONS: Tuple[str, ...]

    def remembers(self, row: Dict[str, Any]) -> Dict[str, str]:
        """Che cosa fotografare dell'oggetto, per riconoscerlo dopo."""
        ...

    def translate(self, binding, outcome) -> Tuple[Dict[str, str], str]:
        """Dall'esito ai campi veri, o al motivo per cui non si può. Puro."""
        ...

    async def look(self, db, *, binding) -> Optional[Dict[str, Any]]:
        """Dov'è l'oggetto adesso, secondo lo stato canonico."""
        ...

    async def apply(self, db, *, call, binding, outcome):
        """La scrittura, dopo autorità, identità e traduzione."""
        ...

    async def reconcile(self, db, *, call, binding, outcome):
        """Che cosa è successo davvero, per un'applicazione appesa."""
        ...

    def says(self, operation: str, fields: Dict[str, str]) -> str:
        """Come si racconta, in italiano, a chi non c'era."""
        ...


#     IL REGISTRO E' UNA TABELLA, NON UN FRAMEWORK.
#
# Dominio e operazione insieme, perche' «calendario» non basta: sapere
# spostare non vuol dire sapere disdire, e un dominio che dichiarasse
# un'operazione che non sa fare la sbaglierebbe in silenzio.
_WHO_KNOWS_HOW: Dict[str, Tuple[str, ...]] = {
    "calendar": ("reschedule", "book", "cancel"),
    # Impegni e scadenze: quello che ORA tiene aperto e che una telefonata
    # puo' chiudere o rimandare.
    "commitments": ("complete", "postpone", "cancel"),
    # Le sessioni di studio pianificate, che una telefonata puo' spostare.
    "study": ("reschedule", "complete", "cancel"),
}


def _module_for(domain: str):
    nome = (domain or "").strip()
    if nome == "calendar":
        from telephone.domains import calendar

        return calendar
    if nome == "commitments":
        from telephone.domains import commitments

        return commitments
    if nome == "study":
        from telephone.domains import study

        return study
    return None


def adapter_for(domain: str, operation: str = ""):
    """
    L'adattatore di questo dominio per questa operazione, o niente.

        «NIENTE» E' UNA RISPOSTA, NON UN GUASTO.

    Un dominio che non c'e', o un'operazione che quel dominio non sa fare,
    tornano `None` — e chi applica lo tratta come un motivo per fermarsi.
    Sollevare qui vorrebbe dire far cadere una telefonata per una cosa che si
    sapeva gia' prima di comporre il numero.
    """
    sa_fare = _WHO_KNOWS_HOW.get((domain or "").strip())
    if sa_fare is None:
        return None
    if operation and operation.strip() not in sa_fare:
        return None
    return _module_for(domain)


def known_domains() -> Dict[str, List[str]]:
    """Che cosa si sa applicare, oggi. Per poterlo dire in un rapporto."""
    return {d: list(ops) for d, ops in _WHO_KNOWS_HOW.items()}


def follows_the_contract(adapter) -> List[str]:
    """
    Che cosa manca a questo adattatore per essere un adattatore.

        UN CONTRATTO CHE NESSUNO VERIFICA E' UNA CONVENZIONE.

    Torna l'elenco dei doveri assenti — vuoto quando li ha tutti. Serve alle
    prove, ed e' il modo in cui un dominio nuovo scopre di averne dimenticato
    uno prima che se ne accorga una persona al telefono.
    """
    doveri = ("DOMAIN", "OPERATIONS", "remembers", "translate", "look",
              "apply", "reconcile", "detect_conflict", "says")
    return [d for d in doveri if not hasattr(adapter, d)]


def every_adapter() -> List[Any]:
    """
    Tutti gli adattatori dichiarati, caricati davvero.

    Serve alle prove: un dominio elencato nel registro il cui modulo non
    esiste sarebbe una promessa che si scopre soltanto durante una telefonata.
    """
    return [m for m in (_module_for(d) for d in _WHO_KNOWS_HOW) if m is not None]
