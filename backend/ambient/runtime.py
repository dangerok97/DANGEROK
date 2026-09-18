"""
The thing that wakes ORA when nobody is looking.

    THE RUNTIME DECIDES WHEN ORA WAKES.
    THE AI DECIDES WHAT THAT WAKE MEANS.

Sprint 1 could decide "check again at 07:15" and had no way to be there at
07:15. This is that: a small loop that asks the database what is due, takes
exactly one thing at a time, hands it to whatever knows how to do it, and
goes back to sleep.

It is deliberately stupid. It does not know what an opportunity is, cannot
read a life, never calls a model, and has no opinion about whether anything
matters — it is an alarm clock with a lease. Every judgement belongs to the
services it invokes, and the day this file starts branching on what it finds
is the day the runtime has become the product.

Three properties are worth stating because they are easy to lose:

* One wake, one worker. The claim is atomic in the database, so two backend
  processes racing produce one winner and one `None`.
* An empty life costs nothing. No wakes due means one indexed query and a
  sleep — no model call, no snapshot, no work.
* A dead worker recovers itself. Claims carry a lease; when it expires the
  wake is eligible again, without anybody noticing the process died.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.ambient.runtime")

# How often the loop looks. Infrastructure, not product: it bounds how late a
# wake can be, and has nothing to say about how often anybody is disturbed.
#
# Deve essere piu' fitto della cadenza piu' stretta fra le sorgenti — il
# calendario, ogni sessanta secondi — altrimenti «ogni minuto» diventa «ogni
# volta che il loop passa», che e' un'altra cosa.
TICK_SECONDS = float(os.environ.get("AMBIENT_TICK_SECONDS", "10"))

# How many wakes one tick will process before yielding. A backlog is drained
# over several ticks rather than in one long blocking sweep.
MAX_PER_TICK = 5

# Technical retry backoff, capped. Code's business entirely — a provider being
# down is not something to ask a model about.
RETRY_BASE_SECONDS = 60
RETRY_MAX_SECONDS = 3600

# How often the loop casts the safety net, in ticks. Derived from the sweep
# cadence rather than set separately, so there is one place that decides how
# often the system looks — and it is not the same place that decides how often
# any one person is looked at.
def _fallback_every_ticks() -> int:
    from ambient.eligibility import SWEEP_INTERVAL_HOURS

    return max(1, int((SWEEP_INTERVAL_HOURS * 3600) / max(1.0, TICK_SECONDS)))

# Ogni quanti giri si guarda se e' arrivato qualcosa da collocare — una
# carta, un messaggio. Lento di proposito: e' manutenzione, e su una vita
# ferma non costa niente perche' non trova niente da fare.
def _relations_every_ticks() -> int:
    minutes = float(os.environ.get("ORA_RELATIONS_EVERY_MINUTES", "10"))
    return max(1, int((minutes * 60) / max(1.0, TICK_SECONDS)))


_task: Optional[asyncio.Task] = None
_stopping = False
_worker_id = ""

_stats: Dict[str, int] = {
    "ticks": 0,
    "wakes_claimed": 0,
    "wakes_completed": 0,
    "wakes_retried": 0,
    "wakes_failed": 0,
    "empty_ticks": 0,
    "fallback_sweeps": 0,
    "fallback_scheduled": 0,
    "relations_carte": 0,
    "relations_messaggi": 0,
    "relations_chiamate": 0,
    "sources_looked_at": 0,
    "sources_read": 0,
    "sources_failed": 0,
    # Letture rimandate perché c'era una telefonata che parlava.
    "sources_deferred_for_call": 0,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def runtime_enabled() -> bool:
    """
    Off unless asked for.

    A background loop that starts itself in every test run, every CI job and
    every developer's terminal is a loop that will eventually do something
    surprising in one of them.
    """
    return os.environ.get("AMBIENT_RUNTIME", "").strip().lower() in ("1", "true", "on")


def worker_id() -> str:
    global _worker_id
    if not _worker_id:
        _worker_id = f"w_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    return _worker_id


async def tick(db, *, now: Optional[datetime] = None, limit: int = MAX_PER_TICK) -> Dict[str, int]:
    """
    One pass: take what is due, do it, record what happened.

    Separated from the loop so it can be driven by a test clock. The loop only
    decides when to call this; everything that matters happens here, which is
    what makes the runtime testable without waiting in real time.
    """
    from ambient.repository import AmbientRepository

    repo = AmbientRepository(db)
    handled = {"claimed": 0, "completed": 0, "retried": 0, "failed": 0}
    moment = now or _now()

    for _ in range(max(1, limit)):
        wake = await repo.claim_due(worker_id=worker_id(), now=moment)
        if wake is None:
            break

        handled["claimed"] += 1
        _stats["wakes_claimed"] += 1
        logger.info("wake_claimed reason=%s attempt=%s", wake.reason, wake.attempts)

        try:
            outcome = await _handle(db, wake)
        except Exception as exc:
            outcome = None
            logger.info("wake handler soft-fail: %s", type(exc).__name__)
            await _retry(repo, wake, error=type(exc).__name__, now=moment)
            handled["retried"] += 1
            _stats["wakes_retried"] += 1
            continue

        if outcome is not None and outcome.retry_after_seconds is not None:
            # A technical failure: the model was unreachable, the channel was
            # down. Nothing was decided, so nothing is recorded as a decision.
            await repo.release(
                wake.id,
                when=(moment + timedelta(seconds=outcome.retry_after_seconds)).isoformat(),
                error=outcome.error or "retry",
            )
            handled["retried"] += 1
            _stats["wakes_retried"] += 1
            logger.info("wake_retry reason=%s in=%ss", wake.reason, outcome.retry_after_seconds)
            continue

        result = outcome.result if outcome else ""
        await repo.complete(wake.id, result=result)
        handled["completed"] += 1
        _stats["wakes_completed"] += 1
        logger.info("wake_completed reason=%s result=%s", wake.reason, result)

    if not handled["claimed"]:
        _stats["empty_ticks"] += 1
    _stats["ticks"] += 1
    return handled


def _a_call_is_live() -> bool:
    """
    Se in questo processo c'è una telefonata che sta parlando.

    Senza importare niente: se il modulo delle telefonate non è mai stato
    caricato, nessuna telefonata può essere in corso — e questo giro di sfondo
    non deve pagare l'import del runtime vocale per scoprirlo.
    """
    import sys

    vocale = sys.modules.get("telephone.live")
    if vocale is None:
        return False
    try:
        return vocale.calls_in_progress() > 0
    except Exception:  # pragma: no cover
        return False


async def read_sources(db, *, now: Optional[datetime] = None) -> Dict[str, int]:
    """
    Read the connected instruments that are due. Deterministic, no model.

        THE USER DOES NOT SYNCHRONISE THEIR LIFE. ORA DOES.

    Here rather than in a scheduler of its own for the same reason `sweep` is
    here: this loop already ticks, already survives a restart, already
    tolerates one pass failing. A second loop would be a second thing to
    start, stop, and get wrong on shutdown.

    The runtime still knows nothing about what it is reading. It calls this,
    counts what came back and goes to sleep; which sources are due, how often,
    and what to do when one fails all belong to the package that owns them.
    """
    from connected.polling import poll_once

    try:
        handled = await poll_once(db, now=now)
    except Exception as exc:
        logger.info("auto-sync soft-fail: %s", type(exc).__name__)
        return {"looked_at": 0}
    for key in ("looked_at", "read", "failed"):
        _stats[f"sources_{key}"] += int(handled.get(key, 0))
    if handled.get("looked_at"):
        logger.info("auto_sync %s", handled)
    return handled


async def keep_relations_current(db) -> Dict[str, Any]:
    """
    Colloca quello che e' arrivato: quale carta appartiene a quale casa, quale
    messaggio riguarda quale situazione.

        UN SISTEMA CHE COLLEGA SOLO QUANDO LO INTERROGHI NON HA CAPITO
        NIENTE FINCHE' NON GLI PARLI.

    Qui e non in un ciclo suo, per la stessa ragione di `sweep` e di
    `read_sources`: questo giro c'e' gia', sopravvive gia' a un riavvio, e
    tollera gia' che un passaggio fallisca. Il runtime non sa cosa stia
    collocando — chiama, conta, e va a dormire.
    """
    try:
        from lifesearch.maintenance import keep_relations_current as run

        done = await run(db)
    except Exception as exc:
        logger.info("relation maintenance soft-fail: %s", type(exc).__name__)
        return {"persone": 0}
    for key in ("carte", "messaggi", "chiamate"):
        _stats[f"relations_{key}"] += int(done.get(key, 0))
    return done


async def sweep(db) -> Dict[str, Any]:
    """
    Cast the safety net: is anybody owed a look that never happened?

    Deterministic and cheap. It never reaches a model — it counts, and when
    something is genuinely waiting it arranges a wake and lets the ordinary
    pipeline handle it. A database full of people with nothing pending
    contributes nothing to the cost, because the candidate set comes from the
    collections that already say otherwise.
    """
    from ambient.eligibility import EligibilityService

    try:
        result = await EligibilityService(db).sweep()
    except Exception as exc:
        logger.info("ambient sweep soft-fail: %s", type(exc).__name__)
        return {"ran": False}
    if result.get("scheduled"):
        _stats["fallback_scheduled"] += int(result["scheduled"])
    _stats["fallback_sweeps"] += 1
    return result


async def _handle(db, wake) -> Any:
    """
    Hand the wake to whatever knows what to do with it.

    A dispatch table and nothing else. The runtime does not know what any of
    these mean — it knows which service owns each reason.
    """
    from ambient.service import AmbientService

    service = AmbientService(db)
    if wake.reason == "delivery_recheck":
        return await service.recheck_delivery(wake)
    if wake.reason in ("opportunity_revisit", "state_changed", "ambient_review"):
        return await service.review_life(wake)
    if wake.reason == "retry":
        return await service.retry_delivery(wake)
    return await service.review_life(wake)


async def _retry(repo, wake, *, error: str, now: datetime) -> None:
    """Exponential backoff with a ceiling. Never asked of a model."""
    delay = min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** max(0, wake.attempts - 1)))
    await repo.release(wake.id, when=(now + timedelta(seconds=delay)).isoformat(), error=error)


async def _loop() -> None:
    from deps import db

    logger.info("ambient runtime started worker=%s tick=%ss", worker_id(), TICK_SECONDS)

    # One deterministic pass before anything else: release leases held by
    # workers that no longer exist, and expire plans whose moment went by
    # while this process was away. No model is reached and nothing is sent —
    # what survives is re-examined by the ordinary path, one at a time.
    try:
        from ambient.eligibility import recover_after_downtime

        recovered = await recover_after_downtime(db)
        if any(recovered.values()):
            logger.info("ambient_recovery %s", recovered)
    except Exception as exc:
        logger.info("ambient recovery soft-fail: %s", type(exc).__name__)

    ticks = 0
    while not _stopping:
        try:
            # Two passes, in this order and for this reason: reading the
            # world can produce a wake, and doing it before the wakes are
            # drained means what just arrived is handled in the same tick
            # rather than a tick later.
            #     UNA TELEFONATA IN CORSO HA LA PRECEDENZA.
            # Le letture delle fonti aprono connessioni nuove, e una
            # connessione nuova ferma questo processo per mezzo secondo
            # mentre carica i certificati. Sul gate V3.20 è successo due
            # volte durante l'apertura di una telefonata: due strappi da più
            # di un secondo nella voce, con otto secondi di audio pronti. Le
            # fonti si leggono a telefonata finita — qualche decina di secondi
            # dopo — e nient'altro cambia.
            if _a_call_is_live():
                _stats["sources_deferred_for_call"] += 1
            else:
                await read_sources(db)
            await tick(db)
            ticks += 1
            # Le relazioni: piu' lente delle letture, piu' rapide della rete
            # di sicurezza. Su una vita ferma questo passaggio non trova
            # niente e non chiama nessuno.
            if ticks % _relations_every_ticks() == 0:
                await keep_relations_current(db)
            if ticks % _fallback_every_ticks() == 0:
                await sweep(db)
        except Exception as exc:
            # The loop must outlive anything that happens inside it.
            logger.info("ambient tick soft-fail: %s", type(exc).__name__)
        try:
            await asyncio.sleep(TICK_SECONDS)
        except asyncio.CancelledError:
            break
    logger.info("ambient runtime stopped")


def start_runtime() -> bool:
    """Started by the application lifecycle, which owns the database client."""
    global _task, _stopping
    if not runtime_enabled():
        return False
    if _task is not None and not _task.done():
        return False
    _stopping = False
    try:
        _task = asyncio.get_running_loop().create_task(_loop())
    except RuntimeError:
        return False
    return True


async def stop_runtime() -> None:
    """
    Stop without draining.

    Nothing is lost by cancelling: every wake is durable in Mongo, and one
    that was claimed when the process died becomes eligible again when its
    lease expires. Only latency is at stake.
    """
    global _task, _stopping
    _stopping = True
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except (asyncio.CancelledError, Exception):
        pass
    _task = None


def runtime_stats() -> Dict[str, Any]:
    return {**_stats, "worker_id": _worker_id, "running": bool(_task and not _task.done())}


def reset_stats_for_test() -> None:
    for key in _stats:
        _stats[key] = 0
