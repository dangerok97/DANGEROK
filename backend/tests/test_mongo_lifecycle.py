"""
The Mongo client belongs to the loop that uses it.

Motor decides which loop a client belongs to on the first await and never
revisits that decision. A client built at import time therefore belonged to
whichever loop touched it first, and everything that ran later on a different
loop got `Future ... attached to a different loop` — which is how a suite
could pass alone and fail after another suite, and why `shutdown()` used to
be a one-way door for the whole process.

What is asserted here is the lifetime rule, not the symptom: a client is
built per running loop, reused within it, closed with it, and never handed to
a loop it does not belong to.
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import weakref
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")

HERE = Path(_BACKEND)


async def _touch():
    """Any real await is enough to make Motor commit to a loop."""
    import deps

    await deps.db.users.find_one({"user_id": "__nobody__"})


def test_a_client_belongs_to_the_loop_that_asked_for_it():
    import mongo

    first = asyncio.new_event_loop()
    second = asyncio.new_event_loop()
    try:
        first.run_until_complete(_touch())
        a = mongo._registry()[first]
        second.run_until_complete(_touch())
        b = mongo._registry()[second]

        assert a is not b, "due loop si sono divisi un client"
        assert mongo._bound_loop(a) is first
        assert mongo._bound_loop(b) is second
    finally:
        for loop in (first, second):
            if loop in mongo._registry():
                loop.run_until_complete(_close_on(loop))
            loop.close()


async def _close():
    import mongo

    mongo.close()


def _close_on(loop):
    return _close()


def test_the_same_loop_gets_the_same_client_every_time():
    """
    Not one per request, and not one per call: the pool is the point.
    """
    import mongo

    loop = asyncio.new_event_loop()
    try:
        seen = []
        for _ in range(4):
            loop.run_until_complete(_touch())
            seen.append(mongo._registry()[loop])
        assert len(set(map(id, seen))) == 1, "un client nuovo a ogni uso"
    finally:
        loop.run_until_complete(_close())
        loop.close()


def test_closing_is_explicit_and_leaves_nothing_behind():
    import mongo

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_touch())
        assert loop in mongo._registry()
        loop.run_until_complete(_close())
        assert loop not in mongo._registry(), "il client e' rimasto nel registro"
    finally:
        loop.close()


def test_a_second_startup_in_the_same_process_gets_a_working_client():
    """
    §9, the sequence that used to be impossible: the old `shutdown()` closed
    the one global client, and nothing could reopen it.
    """
    import mongo
    import server
    from fastapi.testclient import TestClient

    # Per lifecycle, not per process: other suites in the same worker may still
    # hold clients on loops of their own, and counting those would turn this
    # into a test about who else ran first.
    seen = []
    for _ in range(2):
        before = set(mongo._registry())
        with TestClient(server.app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200, response.text
            new_loops = set(mongo._registry()) - before
            assert len(new_loops) == 1, f"loop aggiunti da questo lifespan: {new_loops}"
            loop = new_loops.pop()
            seen.append((loop, mongo._registry()[loop]))

    (first_loop, first_client), (second_loop, second_client) = seen
    assert first_loop is not second_loop, "due lifespan sullo stesso loop"
    assert first_client is not second_client, "il secondo startup ha ereditato un client"
    assert mongo._bound_loop(first_client) is first_loop
    assert mongo._bound_loop(second_client) is second_loop


def test_two_application_lifecycles_do_not_share_a_bound_client():
    """
    Lifecycle A opens, works and closes; lifecycle B opens and works. B must
    not inherit anything A bound.
    """
    import mongo
    import server
    from fastapi.testclient import TestClient

    def one_lifecycle():
        # Read inside the block: shutdown removes the entry, which is the
        # other half of the point.
        before = set(mongo._registry())
        with TestClient(server.app) as app_client:
            assert app_client.get("/api/health").status_code == 200
            added = set(mongo._registry()) - before
            assert len(added) == 1, f"loop aggiunti dal lifespan: {added}"
            loop = added.pop()
            made = mongo._registry()[loop]
            assert mongo._bound_loop(made) is loop
            return loop, made

    first_loop, first_client = one_lifecycle()
    second_loop, second_client = one_lifecycle()

    assert first_loop is not second_loop, "stesso loop per due lifecycle"
    assert first_client is not second_client, "un client condiviso fra due lifecycle"
    assert first_loop not in mongo._registry(), "lo shutdown non ha rilasciato il client"


def test_a_manual_suite_before_the_app_no_longer_poisons_it():
    """
    The reproducer, in the shape it actually had: something awaits `deps.db`
    on the harness loop, and then the app starts its lifespan on the anyio
    portal's loop and calls `create_index` on the same handle.
    """
    import server
    from fastapi.testclient import TestClient

    _loop_harness.run(_touch())   # binds a client to the harness loop

    with TestClient(server.app) as client:   # lifespan on a different loop
        assert client.get("/api/health").status_code == 200


def test_the_binding_is_declared_rather_than_inherited():
    """
    `io_loop=` is passed explicitly. Left to Motor, the binding would be a
    side effect of whoever awaited first — which is the whole bug.
    """
    source = (HERE / "mongo.py").read_text(encoding="utf-8")
    assert "io_loop=loop" in source
    assert "get_running_loop" in source


def test_nothing_recovers_from_a_wrong_loop_by_trying_again():
    """
    §7: correct by construction, not by recovery. A rebuild triggered by
    catching the cross-loop RuntimeError would hide exactly the condition it
    is supposed to make impossible.
    """
    tree = ast.parse((HERE / "mongo.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        caught = ast.unparse(node.type) if node.type else "bare except"
        assert "RuntimeError" not in caught, (
            "mongo.py cattura RuntimeError: il lifecycle sta venendo rattoppato"
        )
        assert node.type is not None, "mongo.py ha un except nudo"


def test_the_handles_callers_import_are_still_one_object_each():
    """
    §8: no migration. `from deps import db` keeps working, and the services
    built at import time keep the handle they were given.
    """
    import deps

    assert deps.db is deps.db
    assert deps.decisions.db is deps.db
    assert deps.life_graph.db is deps.db
    assert callable(deps.client.close)


def test_the_orchestrator_queue_is_released_with_its_loop():
    """
    Found by the same audit, same rule. `asyncio.Queue` binds to the loop it
    is created on; the module kept it past shutdown, so the worker of a second
    lifecycle blocked on a queue belonging to a loop nobody runs any more
    ("<Queue ...> is bound to a different event loop"). Queued work is not
    lost by dropping it — it is still pending in Mongo, which is what the
    shutdown docstring already relied on.
    """
    from life_orchestration import scheduler

    async def lifecycle():
        """Un ciclo intero: avvio, coda, task, arresto."""
        scheduler._started = False
        started = scheduler.start_orchestrator()
        queue = scheduler._get_queue()
        assert queue is scheduler._get_queue(), "una coda nuova a ogni chiamata"
        tasks = [t for t in (scheduler._worker_task, scheduler._recovery_task) if t]
        await scheduler.stop_orchestrator()
        await asyncio.sleep(0)
        return started, queue, tasks

    first_loop = asyncio.new_event_loop()
    try:
        started_a, queue_a, tasks_a = first_loop.run_until_complete(lifecycle())
    finally:
        first_loop.close()

    assert scheduler._queue is None, "la coda e' sopravvissuta allo shutdown"
    assert scheduler._worker_task is None and scheduler._recovery_task is None

    second_loop = asyncio.new_event_loop()
    try:
        started_b, queue_b, tasks_b = second_loop.run_until_complete(lifecycle())
    finally:
        second_loop.close()

    assert queue_a is not queue_b, "due lifecycle si sono divisi una coda"
    # Nessun task del primo ciclo sopravvive nel secondo.
    assert all(t.done() for t in tasks_a), "un task del lifecycle A e' ancora attivo"
    assert not (set(map(id, tasks_a)) & set(map(id, tasks_b)))
    if started_a:
        assert started_b, "il secondo avvio non e' ripartito"


# ---------------------------------------------------------------------------
# What the registry can and cannot promise
# ---------------------------------------------------------------------------

def test_a_client_keeps_its_loop_alive_which_is_why_there_is_no_automatic_cleanup():
    """
    The measurement behind the module's docstring, kept as a test so the
    conclusion cannot quietly rot.

    A pooled client has to be held to be reused; the client holds `io_loop`;
    `io_loop` is the loop. So the registry transitively holds the loop, and a
    weak key over it would never become collectible — which is exactly why an
    earlier draft's `WeakKeyDictionary` + `weakref.finalize(loop, ...)` was a
    guarantee that could not fire.
    """
    import gc

    import mongo

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_touch())
    made = mongo._registry()[loop]

    assert made._io_loop is loop, "il client non trattiene il loop"

    watch_loop = weakref.ref(loop)
    loop.close()
    del loop, made
    for _ in range(5):
        gc.collect()

    survivors = [l for l in mongo._registry() if l is watch_loop()]
    assert watch_loop() is not None, (
        "il loop e' stato raccolto: la premessa di questo modulo e' cambiata, "
        "rileggere mongo.py prima di fidarsi del suo docstring"
    )
    assert survivors, "l'entry e' sparita senza close esplicita"

    # E l'unica cosa che la rilascia davvero.
    mongo.close_all()
    assert not mongo._registry()


def test_a_lifecycle_that_forgets_to_close_is_reported_not_swept():
    """
    §4: meglio una garanzia esplicita vera di una fallback guarantee falsa.
    Un loop chiuso con il client ancora in mano e' un bug, e si vede.
    """
    import mongo

    forgotten = asyncio.new_event_loop()
    try:
        forgotten.run_until_complete(_touch())
        assert not mongo.abandoned(), "un loop ancora aperto non e' abbandonato"
        forgotten.close()
        assert forgotten in mongo.abandoned(), "il lifecycle dimenticato non si vede"
    finally:
        mongo.close_all()
    assert not mongo.abandoned()


def test_nothing_pretends_a_dropped_loop_cleans_itself_up():
    """
    Strutturale: niente weakref sul loop, e nessun finalizer che dichiari una
    garanzia che il grafo dei riferimenti rende impossibile.
    """
    source = (HERE / "mongo.py").read_text(encoding="utf-8")
    assert "WeakKeyDictionary" not in source.split('"""')[2], (
        "il registro e' tornato a una weak key che non puo' funzionare"
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr != "finalize", (
                "weakref.finalize sul loop: non partira' mai, vedi il test sopra"
            )


def test_explicit_close_is_what_the_application_actually_calls():
    """La garanzia dichiarata deve essere quella che il server esercita."""
    server_source = (HERE / "server.py").read_text(encoding="utf-8")
    assert "client.close()" in server_source
    shutdown = server_source.split('@app.on_event("shutdown")')[1].split("\napp.")[0]
    assert "client.close()" in shutdown, "lo shutdown non rilascia il client"
