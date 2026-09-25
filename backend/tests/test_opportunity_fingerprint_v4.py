import pytest

from opportunities.changes import fingerprint


@pytest.mark.parametrize("source", ["situations", "disagreements", "money", "unavailable_sources"])
def test_a_change_in_each_evaluated_source_requires_new_review(source):
    before = {source: []}
    after = {source: ["new fact or recovered source"]}
    assert fingerprint(before) != fingerprint(after)


def test_raw_clock_does_not_defeat_review_deduplication():
    assert fingerprint({"now": "2026-09-25T10:00:00Z"}) == fingerprint({"now": "2026-09-25T10:00:01Z"})
