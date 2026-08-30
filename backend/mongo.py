"""
The Mongo client, owned by the event loop that uses it.

Motor binds a client to a loop on its first await, not at construction:
`AsyncIOMotorClient.io_loop` is a lazy property that calls `get_event_loop()`
once and caches the answer for the life of the object. A client built at
import time therefore belonged to whichever loop touched it first, and every
later use from a different loop failed with "got Future ... attached to a
different loop" — the future is created on the bound loop and awaited on the
current one.

That is a lifetime mismatch, not a race: the resource lived for the life of
the module, while what it can actually serve lives for the life of a loop.
The same mismatch made `shutdown()` a one-way door — it closed the single
global client, so a second startup in the same process found a dead one.

The guarantee, stated plainly
-----------------------------
    THE APPLICATION LIFECYCLE OWNS THE CLIENT.
    EXPLICIT SHUTDOWN RELEASES IT.

There is no automatic reclamation, and this module deliberately does not
pretend otherwise. A registry that hands back a pooled client has to hold it,
the client holds `io_loop`, and that is a strong reference to the very loop a
weak key would need to be free — so a WeakKeyDictionary here collects nothing
and a `weakref.finalize` on the loop never fires. Measured, not assumed:

    registry ─→ client ─→ client._io_loop ─→ loop (the key)

So the registry is an ordinary dict and the release is `close()`, called from
the application's shutdown. A lifecycle that forgets to close is a bug, and
`abandoned()` makes it visible rather than quietly cleaning up after it.

There is no "try the old client and rebuild if it complains": the client
handed out is always the one belonging to the loop asking for it, which is
what makes this correct by construction rather than by recovery. Within one
loop — which is all of production — it is created once and reused, connection
pool included.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

_url: str = ""
_name: str = ""

# Keyed by the loop that owns the client. Ordinary strong references, because
# that is what this actually is: see the module docstring.
_clients: Dict[asyncio.AbstractEventLoop, AsyncIOMotorClient] = {}


def configure(url: str, name: str) -> None:
    """Told once, at import, by whoever already parsed the environment."""
    global _url, _name
    _url, _name = url, name


def _running_loop() -> asyncio.AbstractEventLoop:
    # No fallback to the policy's current loop: a client is only meaningful
    # inside a loop that is actually running, and pretending otherwise is how
    # the binding went wrong in the first place.
    return asyncio.get_running_loop()


def client() -> AsyncIOMotorClient:
    """The client belonging to the running loop, built the first time it asks."""
    if not _url:
        raise RuntimeError("mongo.configure() non è stato chiamato")

    loop = _running_loop()
    existing = _clients.get(loop)
    if existing is not None:
        return existing

    stale = abandoned()
    if stale:
        # Not cleaned up here: closing someone else's client on the way past
        # would hide the fact that a lifecycle ended without releasing it.
        logger.warning(
            "%d client Mongo appartengono a loop già chiusi: "
            "un lifecycle è terminato senza chiamare shutdown",
            len(stale),
        )

    # io_loop is passed explicitly rather than left to Motor's lazy lookup, so
    # the binding is a decision made here instead of a side effect of whoever
    # awaits first.
    made = AsyncIOMotorClient(_url, io_loop=loop)
    _clients[loop] = made
    return made


def database() -> AsyncIOMotorDatabase:
    """The database handle for the running loop."""
    return client()[_name]


def close() -> None:
    """
    Release the client owned by the running loop.

    Called from the application's shutdown. Afterwards a new startup on a new
    loop builds a new client: closing is no longer a one-way door.
    """
    loop = _running_loop()
    made = _clients.pop(loop, None)
    if made is not None:
        made.close()


def close_all() -> None:
    """Every client this process still holds. For teardown, not for request paths."""
    while _clients:
        _, made = _clients.popitem()
        made.close()


def abandoned() -> List[asyncio.AbstractEventLoop]:
    """
    Clients whose loop is already closed — a lifecycle that never released one.

    Reported, not repaired: an automatic sweep would make a missing shutdown
    invisible, and a missing shutdown is worth seeing.
    """
    return [loop for loop in _clients if loop.is_closed()]


def _bound_loop(made: AsyncIOMotorClient) -> Optional[asyncio.AbstractEventLoop]:
    """What loop a client is bound to, for tests that check exactly that."""
    return made._io_loop


def _registry() -> Dict[asyncio.AbstractEventLoop, AsyncIOMotorClient]:
    """A snapshot, for tests. Not for callers who want a client."""
    return dict(_clients)
