"""
Chi ripassa a chiudere le applicazioni rimaste a metà.

    UN RECUPERO CHE NESSUNO CHIAMA NON RECUPERA NIENTE.

La V3.15.2 ha insegnato al livello di applicazione a riconciliarsi con il
calendario: guardare dov'è l'appuntamento adesso e chiudere il record di
conseguenza. Ma restava una funzione che nessuno invocava, e un record appeso
sarebbe rimasto appeso finché qualcuno non se ne fosse accorto a mano.

Questo file è l'unico posto in cui quella funzione viene chiamata da sola.

    UNA VOLTA ALL'AVVIO, E POI OGNI MINUTO.

All'avvio perché è il momento in cui è **certo** che ci sia qualcosa da
recuperare: se il processo precedente è morto in mezzo a due scritture, il suo
`pending` è lì che aspetta proprio adesso. Poi a intervalli, perché un processo
può anche non morire — può solo perdere la rete per dieci secondi.

    E NON BLOCCA NIENTE.

La scansione dell'avvio non si aspetta: parte come attività a sé e il backend
finisce di alzarsi mentre lei lavora. Un recupero lento non deve ritardare la
prima richiesta di nessuno, e un recupero rotto non deve impedire al server di
partire.

    UN ERRORE SU UN RECORD NON FERMA IL GIRO.

Ogni passata è avvolta: qualunque cosa succeda dentro, si annota e si aspetta
il minuto dopo. Un ciclo che muore al primo intoppo è peggio di nessun ciclo,
perché sembra che ci sia.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Optional

logger = logging.getLogger("ora.telephone.recovery")

# Ogni quanto si ripassa. Un minuto: abbastanza spesso che un record appeso
# non resti tale a lungo, abbastanza raro che su un database senza niente da
# fare sia una domanda al minuto e nient'altro.
EVERY_S = 60

_task: Optional[asyncio.Task] = None


def start_recovery(db) -> None:
    """
    Accende il giro. Torna subito.

    Se è già acceso non ne accende un secondo: due cicli sullo stesso database
    si contenderebbero gli stessi record — e anche se la rivendicazione atomica
    li terrebbe onesti, sarebbe lavoro doppio per niente.
    """
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_keep_looking(db))
    logger.info("recupero applicazioni: acceso (ogni %ds)", EVERY_S)


async def stop_recovery() -> None:
    """
    Spegne il giro, senza aspettare che finisca il lavoro.

        CANCELLARE NON PERDE NIENTE.

    Ogni cosa da fare è durevole in Mongo, e una rivendicazione presa quando
    il processo muore torna libera appena scade. Quello che si perde è latenza,
    non lavoro.
    """
    global _task
    if _task is None:
        return
    _task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await _task
    _task = None
    logger.info("recupero applicazioni: spento")


async def _keep_looking(db) -> None:
    """Una passata adesso, e poi una ogni minuto finché non ci fermano."""
    await _one_pass(db, "avvio")
    while True:
        try:
            await asyncio.sleep(EVERY_S)
        except asyncio.CancelledError:
            raise
        await _one_pass(db, "periodica")


async def _one_pass(db, quale: str) -> int:
    """
    Una scansione sola. Non solleva mai.

    Torna quanti record ha chiuso, che è quasi sempre zero — ed è il numero
    che si spera di leggere.
    """
    try:
        from telephone.application import recover_stale

        chiusi = await recover_stale(db)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        #     IL GIRO SOPRAVVIVE A QUELLO CHE GLI SUCCEDE DENTRO.
        logger.info("scansione %s non riuscita: %s", quale, type(e).__name__)
        return 0
    if chiusi:
        logger.info(
            "scansione %s: %d applicazioni chiuse (%s)",
            quale, len(chiusi),
            ", ".join(sorted({c.application_status for c in chiusi})),
        )
    return len(chiusi)
