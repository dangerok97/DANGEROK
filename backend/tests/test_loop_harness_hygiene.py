"""
Order independence, as a property rather than as a habit.

The suites here are written in two styles. Some run a coroutine with
`asyncio.run()`; some hand one to a shared loop. Both are fine on their own.
What was not fine is that the first style left the process-global current-loop
slot empty, and the second style read that slot — so a suite passed alone and
failed after another suite, in the same process, for reasons that had nothing
to do with the code under test.

These tests assert the thing that has to stay true: what one suite does to
asyncio must not decide what another suite gets.
"""

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

HERE = Path(__file__).resolve().parent


async def _answer():
    await asyncio.sleep(0)
    return 42


def test_the_exact_contamination_no_longer_reaches_us():
    """
    The reproducer, in the shape it actually had.

    `asyncio.run()` calls `set_event_loop(None)` on the way out, and from then
    on the policy refuses to invent a loop rather than quietly making one. Any
    suite that had asked it to invent one got a RuntimeError instead of a test
    result.
    """
    assert _loop_harness.run(_answer()) == 42

    asyncio.run(_answer())  # the other style of suite, running in between

    # The slot is now empty, which is exactly the state that used to break us.
    with pytest.raises(RuntimeError):
        asyncio.get_event_loop()

    # And it no longer decides anything.
    assert _loop_harness.run(_answer()) == 42


def test_the_loop_survives_a_neighbour_that_builds_and_closes_its_own():
    """
    Not just "it still runs" but "it is still the same loop".

    Suites keep Motor clients and other loop-bound objects alive between calls.
    Swapping in a fresh loop when the old one seemed to be gone — which is what
    the local workaround in one file used to do — would leave those objects
    bound to a loop nobody runs any more.
    """
    first = _loop_harness.get_loop()
    asyncio.run(_answer())
    asyncio.run(_answer())
    assert _loop_harness.get_loop() is first
    assert not first.is_closed()


def test_running_order_does_not_change_the_answer():
    """Both orders, same result, in one process."""
    before = [_loop_harness.run(_answer()), asyncio.run(_answer())]
    after = [asyncio.run(_answer()), _loop_harness.run(_answer())]
    assert before == after == [42, 42]


def test_no_suite_touches_the_global_loop_slot():
    """
    Structurally, so this cannot come back by copy-paste.

    The defect was the process-global slot: `get_event_loop()` reads it and
    depends on what someone else left there, `set_event_loop()` writes it and
    decides for everyone. Those two are what made results depend on order, and
    no test file may do either.

    Building a private loop and running it explicitly is a different act — it
    is what `_loop_harness` itself does, and what a test about loop lifetime
    has to do to have two of them. That is allowed, but not everywhere: the
    next test keeps it to the one file whose subject it is.
    """
    offenders = []
    for path in sorted(HERE.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"get_event_loop", "set_event_loop"}):
                offenders.append(f"{path.name}:{node.lineno} {node.func.attr}()")
    assert not offenders, (
        "questi file leggono o scrivono lo slot globale: " + ", ".join(offenders)
    )


def test_only_the_lifecycle_suite_builds_loops_of_its_own():
    """
    `new_event_loop()` is not the bug, but it is how a suite would start
    deciding for itself again. One file needs it, because two application
    lifecycles in one process is precisely what it asserts.
    """
    allowed = {"test_mongo_lifecycle.py", Path(__file__).name}
    builders = []
    for path in sorted(HERE.glob("test_*.py")):
        if path.name in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "new_event_loop"):
                builders.append(f"{path.name}:{node.lineno}")
    assert not builders, "questi file si costruiscono un loop: " + ", ".join(builders)


def test_the_harness_does_not_swallow_what_the_coroutine_raises():
    """
    A quieter harness would be a worse one. Errors come through unchanged.
    """
    class Specific(Exception):
        pass

    async def fails():
        raise Specific("questo deve arrivare al test")

    with pytest.raises(Specific, match="questo deve arrivare"):
        _loop_harness.run(fails())


def test_a_task_left_running_is_visible_rather_than_silent():
    """
    §8: the harness has to be able to say what it is still holding, otherwise
    "no failures" would start meaning "nothing was checked".
    """
    started = asyncio.Event()

    async def forever():
        started.set()
        await asyncio.sleep(3600)

    async def leak():
        task = _loop_harness.get_loop().create_task(forever())
        await started.wait()
        return task

    task = _loop_harness.run(leak())
    try:
        assert task in _loop_harness.pending_tasks()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            _loop_harness.run(task)
    assert task not in _loop_harness.pending_tasks()
