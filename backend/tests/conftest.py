"""Shared test fixtures for in-process suites.

Motor's AsyncIOMotorClient is instantiated at import-time in `deps.py`
and bound to a single event loop. Once that loop closes (which happens
when `TestClient(server.app)` finishes its lifespan for the first
module), subsequent modules that try to re-open a TestClient hit
"Event loop is closed".

This conftest exposes a SESSION-scoped `client` fixture so all in-process
suites share exactly ONE TestClient + one lifespan cycle.
"""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")

sys.path.insert(0, "/app/backend")

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402


@pytest.fixture(scope="session")
def shared_client():
    """Single TestClient reused across all in-process test modules.

    Modules that already declare their own module-scoped `client` fixture
    continue to work; they just get their own client, which is fine when
    the module is run standalone. When ALL suites are run in the same
    pytest process, opt-in modules use `shared_client` to avoid the
    motor event-loop-closed problem.
    """
    with TestClient(server.app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def _asyncio_session_loop():
    """
    Own the loop the manual suites run on, and account for it at the end.

    Half the suites here use `asyncio.run()`, which clears the process-global
    current-loop slot on its way out; the other half were written against
    `asyncio.get_event_loop()`, which stops auto-creating once that slot has
    been touched. Ordering therefore decided whether a suite passed. They now
    go through `_loop_harness`, which holds its own loop and never consults the
    slot — see that module for the whole story.

    The teardown is the other half of the deal: a loop this harness opened is a
    loop this harness closes, and anything still running on it at the end is
    reported rather than swallowed. Nothing is cancelled quietly, and no
    exception is caught.
    """
    import logging
    import warnings

    import _loop_harness

    yield

    # The Mongo registry holds a client per loop, and holding it is what keeps
    # that loop alive — there is no automatic reclamation to wait for (see
    # mongo.py). Releasing them is the harness's job at the end of a session,
    # exactly as it is the application's job at shutdown.
    try:
        import mongo

        mongo.close_all()
    except Exception:
        logging.getLogger(__name__).exception("chiusura dei client Mongo di test")

    leftover = _loop_harness.pending_tasks()
    if leftover:
        warnings.warn(
            "il loop dei test aveva ancora "
            f"{len(leftover)} task in sospeso a fine sessione: "
            + ", ".join(sorted({repr(t.get_coro()) for t in leftover}))[:800],
            RuntimeWarning,
            stacklevel=1,
        )
    _loop_harness.close()
