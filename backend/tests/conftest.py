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
