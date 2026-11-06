"""The calls source of Aggiornamenti was failing on every read (6/11 logs:
«activity calls source failed: ValueError»): recent() returns three values."""
import logging
from datetime import datetime, timezone

import pytest

from test_phone_identity_conflict import db  # noqa: F401  (fixture)


@pytest.mark.asyncio
async def test_the_calls_source_reads_without_failing(db, caplog):  # noqa: F811
    from activity.presentation import _call_rows

    with caplog.at_level(logging.WARNING, logger="ora.activity"):
        rows = await _call_rows(db, "owner", datetime.now(timezone.utc))
    assert rows == []
    assert "calls source failed" not in caplog.text
