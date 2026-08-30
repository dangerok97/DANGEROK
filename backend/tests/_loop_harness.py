"""
One event loop for the suites that expect one, owned explicitly.

Half the suites here run a coroutine with `asyncio.run()`, which builds a loop,
runs it, closes it, and then — this is the part that matters — calls
`asyncio.set_event_loop(None)` on the way out. The other half were written
against `asyncio.get_event_loop()`, which auto-creates a loop only until
something has called `set_event_loop` even once. After that the policy stops
guessing and raises.

So the second kind of suite passed alone and failed after the first kind, in
the same process, with `RuntimeError: There is no current event loop`. Nothing
about the code under test was involved: one test was changing the result of
another through a process-global slot.

The fix is to stop reading that slot. This module holds its own loop and calls
`run_until_complete` on the object directly, so what any other suite does to
the policy is no longer anybody's business. The loop is created once and kept
for the whole session, which is what those suites already assumed — Motor
clients and anything else built inside one call stay usable in the next.

It is deliberately not a `try/get_event_loop/except/new_event_loop` dance
copied into every file. That shape hides the failure instead of removing it,
and it quietly swaps loops underneath objects that were bound to the old one.
"""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine, Optional

_loop: Optional[asyncio.AbstractEventLoop] = None


def get_loop() -> asyncio.AbstractEventLoop:
    """The session's loop, built on first use."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Run one coroutine to completion on the session's loop.

    `set_event_loop` is re-asserted every time because a suite that used
    `asyncio.run()` in between will have cleared it, and library code that
    reaches for the current loop while we are not running should find ours
    rather than nothing. Errors are not caught here: a coroutine that raises
    must raise, and a loop that is already running must say so.
    """
    loop = get_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def pending_tasks() -> list:
    """Tasks still alive on the session's loop, for the harness to complain about."""
    if _loop is None or _loop.is_closed():
        return []
    return [t for t in asyncio.all_tasks(_loop) if not t.done()]


def close() -> None:
    """Shut the loop down at the end of the session, async generators included."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = None
        return
    try:
        _loop.run_until_complete(_loop.shutdown_asyncgens())
    finally:
        _loop.close()
        _loop = None
